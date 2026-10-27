from datetime import datetime, timezone
from pathlib import Path

from clinical_rules.loader import load_rule_set
from clinical_rules.engine import evaluate_rule_set
from clinical_rules.models import Fact, RuleSetVersion

RULE_FILE = Path(__file__).parents[1] / "rules" / "diabetes-care-gap.json"
AT = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def _load():
    return load_rule_set(RULE_FILE)


def _facts(hba1c=9.1, visit_days_ago=240):
    from datetime import timedelta
    return {
        "hba1c": Fact(name="hba1c", value=hba1c, observed_at=AT - timedelta(days=21)),
        "endocrinology_visit": Fact(
            name="endocrinology_visit",
            value="visit",
            observed_at=AT - timedelta(days=visit_days_ago),
        ),
    }


def test_fires_for_high_hba1c_and_no_recent_visit():
    traces = evaluate_rule_set(_load(), "patient-1", _facts(), AT)
    assert len(traces) == 1
    assert traces[0].outcome == "fired"
    assert traces[0].rule_id == "diabetes-care-gap"
    assert "DIABETES_GAP" in traces[0].explanation
    assert set(traces[0].facts_used) == {"hba1c", "endocrinology_visit"}


def test_does_not_fire_when_hba1c_is_below_threshold():
    traces = evaluate_rule_set(_load(), "patient-1", _facts(hba1c=6.5), AT)
    assert traces[0].outcome == "not_fired"


def test_does_not_fire_when_visit_is_recent():
    traces = evaluate_rule_set(_load(), "patient-1", _facts(visit_days_ago=30), AT)
    assert traces[0].outcome == "not_fired"


def test_missing_fact_obeys_skip_policy_as_unknown():
    traces = evaluate_rule_set(_load(), "patient-1", {"hba1c": Fact(name="hba1c", value=9.1)}, AT)
    assert traces[0].outcome == "unknown"
    assert "unknown" in traces[0].explanation.lower()


def test_inactive_rule_set_produces_not_fired_trace():
    rule_set = _load()
    rule_set.effective_from = __import__("datetime").date(2027, 1, 1)
    traces = evaluate_rule_set(rule_set, "patient-1", _facts(), AT)
    assert traces[0].outcome == "not_fired"
    assert "not effective" in traces[0].explanation


def test_each_trace_identifies_patient_and_evaluation_time():
    traces = evaluate_rule_set(_load(), "patient-42", _facts(), AT)
    assert traces[0].patient_id == "patient-42"
    assert traces[0].evaluated_at == AT


def test_fire_unknown_policy_fires_when_data_is_missing():
    rule_set = _load()
    rule_set.rules[0].unknown_policy = "fire"
    traces = evaluate_rule_set(rule_set, "patient-1", {}, AT)
    assert traces[0].outcome == "fired"
    assert "unknown_policy=fire" in traces[0].explanation


def test_error_unknown_policy_reports_error_outcome():
    rule_set = _load()
    rule_set.rules[0].unknown_policy = "error"
    traces = evaluate_rule_set(rule_set, "patient-1", {}, AT)
    assert traces[0].outcome == "error"
