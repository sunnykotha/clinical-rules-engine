from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from clinical_rules.engine import evaluate_rule_set
from clinical_rules.loader import load_rule_set
from clinical_rules.models import Fact

RULE_FILE = Path(__file__).parents[1] / "rules" / "diabetes-care-gap.json"
JUNE = datetime(2026, 6, 15, 12, tzinfo=timezone.utc)


def _rules():
    return load_rule_set(RULE_FILE)


def _facts():
    return {
        "hba1c": Fact(
            name="hba1c",
            value=9.1,
            observed_at=JUNE - timedelta(days=21),
        ),
        "endocrinology_visit": Fact(
            name="endocrinology_visit",
            value="visit",
            observed_at=JUNE - timedelta(days=170),
        ),
    }


def test_rule_set_inactive_before_effective_date():
    rule_set = _rules().model_copy(update={
        "effective_from": date(2026, 7, 1),
    })
    result = evaluate_rule_set(
        rule_set, "patient-1", _facts(), JUNE
    )
    assert all(trace.outcome == "not_fired" for trace in result)
    assert "not effective" in result[0].explanation


def test_rule_set_inactive_after_expiration_date():
    rule_set = _rules().model_copy(update={
        "effective_from": date(2026, 1, 1),
        "effective_to": date(2026, 6, 30),
    })
    result = evaluate_rule_set(
        rule_set,
        "patient-1",
        _facts(),
        datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    assert all(trace.outcome == "not_fired" for trace in result)


def test_rule_inactive_before_its_effective_date():
    rule_set = _rules()
    rule = rule_set.rules[0].model_copy(update={
        "effective_from": date(2026, 7, 1),
    })
    rule_set = rule_set.model_copy(update={"rules": [rule]})
    result = evaluate_rule_set(
        rule_set, "patient-1", _facts(), JUNE
    )
    assert result[0].outcome == "not_fired"
    assert "not effective" in result[0].explanation


def test_rule_inactive_after_its_expiration_date():
    rule_set = _rules()
    rule = rule_set.rules[0].model_copy(update={
        "effective_from": date(2026, 1, 1),
        "effective_to": date(2026, 6, 14),
    })
    rule_set = rule_set.model_copy(update={"rules": [rule]})
    result = evaluate_rule_set(
        rule_set, "patient-1", _facts(), JUNE
    )
    assert result[0].outcome == "not_fired"


def test_historical_timestamp_controls_time_window_evaluation():
    rule_set = _rules()
    june_result = evaluate_rule_set(
        rule_set, "patient-1", _facts(), JUNE
    )
    december_result = evaluate_rule_set(
        rule_set,
        "patient-1",
        _facts(),
        datetime(2026, 12, 15, 12, tzinfo=timezone.utc),
    )

    # The endocrinology visit was 170 days before June, but over 180 days
    # before December. The same historical facts produce different results.
    assert june_result[0].outcome == "not_fired"
    assert december_result[0].outcome == "fired"


def test_effective_date_boundaries_are_inclusive():
    rule_set = _rules().model_copy(update={
        "effective_from": date(2026, 1, 1),
        "effective_to": date(2026, 6, 15),
    })
    result = evaluate_rule_set(
        rule_set, "patient-1", _facts(), JUNE
    )
    assert result[0].outcome in {"fired", "not_fired", "unknown"}
    assert "not effective" not in result[0].explanation