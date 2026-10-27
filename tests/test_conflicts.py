from datetime import date, datetime, timezone
from pathlib import Path

from clinical_rules.engine import evaluate_rule_set
from clinical_rules.loader import load_rule_set

RULE_FILE = Path(__file__).parents[1] / "rules" / "diabetes-care-gap.json"
AT = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def _loaded():
    return load_rule_set(RULE_FILE)


def _facts():
    from datetime import timedelta
    from clinical_rules.models import Fact

    return {
        "hba1c": Fact(name="hba1c", value=9.1, observed_at=AT - timedelta(days=21)),
        "endocrinology_visit": Fact(
            name="endocrinology_visit",
            value="visit",
            observed_at=AT - timedelta(days=240),
        ),
    }


def test_priority_is_evaluated_first_and_lower_priority_group_alert_suppressed():
    rule_set = _loaded()
    care_gap = rule_set.rules[0]
    urgent = care_gap.model_copy(
        update={
            "id": "uncontrolled-diabetes",
            "priority": 1,
            "action": care_gap.action.model_copy(
                update={
                    "code": "UNCONTROLLED_DIABETES",
                    "message": "Uncontrolled diabetes with recent emergency care",
                    "severity": 4,
                    "issue": "diabetes-care",
                }
            ),
        }
    )
    rule_set.rules = [care_gap, urgent]

    traces = evaluate_rule_set(rule_set, "patient-1", _facts(), AT)

    assert [trace.rule_id for trace in traces] == [
        "uncontrolled-diabetes",
        "diabetes-care-gap",
    ]
    assert traces[0].outcome == "fired"
    assert traces[1].outcome == "suppressed"
    assert "uncontrolled-diabetes" in traces[1].explanation


def test_same_issue_suppresses_lower_severity_even_if_its_priority_is_higher():
    rule_set = _loaded()
    low = rule_set.rules[0].model_copy(
        update={
            "id": "lower-severity",
            "priority": 1,
            "action": rule_set.rules[0].action.model_copy(update={"severity": 2}),
        }
    )
    high = low.model_copy(
        update={
            "id": "higher-severity",
            "priority": 2,
            "action": low.action.model_copy(
                update={"code": "HIGHER", "severity": 5}
            ),
        }
    )
    rule_set.rules = [low, high]

    traces = evaluate_rule_set(rule_set, "patient-1", _facts(), AT)
    by_id = {trace.rule_id: trace for trace in traces}

    assert by_id["higher-severity"].outcome == "fired"
    assert by_id["lower-severity"].outcome == "suppressed"


def test_different_issues_without_exclusive_group_can_both_fire():
    rule_set = _loaded()
    first = rule_set.rules[0]
    second = first.model_copy(
        update={
            "id": "other-issue",
            "priority": 1,
            "action": first.action.model_copy(
                update={
                    "code": "OTHER",
                    "issue": "other-condition",
                    "mutually_exclusive_group": None,
                }
            ),
        }
    )
    rule_set.rules = [first, second]

    traces = evaluate_rule_set(rule_set, "patient-1", _facts(), AT)
    assert all(trace.outcome == "fired" for trace in traces)


def test_same_exclusive_group_suppresses_lower_priority_alert():
    rule_set = _loaded()
    first = rule_set.rules[0]
    second = first.model_copy(
        update={
            "id": "priority-one",
            "priority": 1,
            "action": first.action.model_copy(update={"code": "PRIORITY_ONE"}),
        }
    )
    rule_set.rules = [first, second]

    traces = evaluate_rule_set(rule_set, "patient-1", _facts(), AT)
    by_id = {trace.rule_id: trace for trace in traces}

    assert by_id["priority-one"].outcome == "fired"
    assert by_id["diabetes-care-gap"].outcome == "suppressed"


def test_unmatched_rule_does_not_suppress_fired_alert():
    rule_set = _loaded()
    first = rule_set.rules[0]
    unmatched = first.model_copy(
        update={
            "id": "not-matching",
            "priority": 1,
            "condition": first.condition.model_copy(
                update={
                    "children": [
                        first.condition.children[0].model_copy(
                            update={"value": 100}
                        )
                    ]
                }
            ),
            "action": first.action.model_copy(update={"code": "NO_MATCH"}),
        }
    )
    rule_set.rules = [first, unmatched]

    traces = evaluate_rule_set(rule_set, "patient-1", _facts(), AT)
    by_id = {trace.rule_id: trace for trace in traces}

    assert by_id["diabetes-care-gap"].outcome == "fired"
    assert by_id["not-matching"].outcome == "not_fired"
