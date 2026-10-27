import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from clinical_rules.engine import evaluate_rule_set
from clinical_rules.loader import RuleFileError, load_rule_set
from clinical_rules.models import (
    AlertAction,
    ComparisonOperator,
    Condition,
    Fact,
    LogicalOperator,
    Rule,
    RuleSetVersion,
    UnknownPolicy,
)

AT = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
RULE_FILE = Path(__file__).parents[1] / "rules" / "diabetes-care-gap.json"


def _worked_example():
    hba1c = Fact(
        name="hba1c",
        value=9.1,
        observed_at=AT - timedelta(days=21),
        unit="%",
        source="lab",
    )
    old_visit = Fact(
        name="endocrinology_visit",
        value="visit",
        observed_at=AT - timedelta(days=240),
        source="encounter",
    )
    recent_er = Fact(
        name="emergency_visit",
        value="emergency visit",
        observed_at=AT - timedelta(days=5),
        source="encounter",
    )

    care_gap = Rule(
        id="diabetes-care-gap",
        version="1.0",
        description="High HbA1c without a recent endocrinology visit",
        priority=2,
        condition=Condition(
            operator=LogicalOperator.AND,
            children=[
                Condition(
                    operator=ComparisonOperator.GT,
                    fact="hba1c",
                    value=8,
                ),
                Condition(
                    operator=LogicalOperator.NOT,
                    children=[
                        Condition(
                            operator=ComparisonOperator.WITHIN_LAST_DAYS,
                            fact="endocrinology_visit",
                            within_days=180,
                        )
                    ],
                ),
            ],
        ),
        action=AlertAction(
            code="DIABETES_GAP",
            message="Follow-up with endocrinology is overdue",
            issue="diabetes-care",
            severity=2,
            mutually_exclusive_group="diabetes-status",
        ),
        unknown_policy=UnknownPolicy.SKIP,
        cooldown_days=30,
        effective_from=date(2026, 1, 1),
    )

    uncontrolled = Rule(
        id="uncontrolled-diabetes-recent-er",
        version="1.0",
        description="High HbA1c with a recent emergency visit",
        priority=1,
        condition=Condition(
            operator=LogicalOperator.AND,
            children=[
                Condition(
                    operator=ComparisonOperator.GT,
                    fact="hba1c",
                    value=8,
                ),
                Condition(
                    operator=ComparisonOperator.WITHIN_LAST_DAYS,
                    fact="emergency_visit",
                    within_days=30,
                ),
            ],
        ),
        action=AlertAction(
            code="UNCONTROLLED_DIABETES",
            message="Prompt clinical review is indicated",
            issue="diabetes-care",
            severity=5,
            mutually_exclusive_group="diabetes-status",
        ),
        unknown_policy=UnknownPolicy.SKIP,
        cooldown_days=30,
        effective_from=date(2026, 1, 1),
    )

    rule_set = RuleSetVersion(
        id="clinical-guidelines",
        version="1.0",
        effective_from=date(2026, 1, 1),
        rules=[care_gap, uncontrolled],
    )
    facts = {
        "hba1c": hba1c,
        "endocrinology_visit": old_visit,
        "emergency_visit": recent_er,
    }
    return rule_set, facts


def test_worked_example_selects_higher_severity_alert():
    rule_set, facts = _worked_example()
    traces = evaluate_rule_set(rule_set, "patient-100", facts, AT)
    by_id = {trace.rule_id: trace for trace in traces}

    assert by_id["uncontrolled-diabetes-recent-er"].outcome == "fired"
    assert by_id["diabetes-care-gap"].outcome == "suppressed"
    assert "uncontrolled-diabetes-recent-er" in by_id["diabetes-care-gap"].explanation


def test_worked_example_trace_explains_both_decisions_and_facts():
    rule_set, facts = _worked_example()
    traces = evaluate_rule_set(rule_set, "patient-100", facts, AT)
    by_id = {trace.rule_id: trace for trace in traces}

    high = by_id["uncontrolled-diabetes-recent-er"]
    low = by_id["diabetes-care-gap"]

    assert high.patient_id == "patient-100"
    assert high.evaluated_at == AT
    assert "hba1c" in high.facts_used
    assert "emergency_visit" in high.facts_used
    assert high.explanation
    assert "hba1c" in low.facts_used
    assert "endocrinology_visit" in low.facts_used
    assert low.explanation


def test_example_json_rule_file_loads():
    rule_set = load_rule_set(RULE_FILE)
    assert rule_set.id == "clinical-guidelines"
    assert any(rule.id == "diabetes-care-gap" for rule in rule_set.rules)


def test_malformed_json_is_rejected_with_clear_error(tmp_path):
    bad_file = tmp_path / "malformed.json"
    bad_file.write_text('{"id": "broken", "rules": [', encoding="utf-8")

    with pytest.raises(RuleFileError, match="JSON|json|line|column"):
        load_rule_set(bad_file)


def test_invalid_rule_schema_is_rejected(tmp_path):
    bad_file = tmp_path / "invalid-schema.json"
    bad_file.write_text(
        json.dumps({
            "id": "broken",
            "version": "1.0",
            "effective_from": "2026-01-01",
            "unexpected_field": True,
            "rules": [],
        }),
        encoding="utf-8",
    )

    with pytest.raises(RuleFileError):
        load_rule_set(bad_file)


def test_hba1c_alone_does_not_fire_recent_er_rule():
    rule_set, facts = _worked_example()
    facts.pop("emergency_visit")
    traces = evaluate_rule_set(rule_set, "patient-101", facts, AT)
    by_id = {trace.rule_id: trace for trace in traces}

    assert by_id["uncontrolled-diabetes-recent-er"].outcome == "unknown"