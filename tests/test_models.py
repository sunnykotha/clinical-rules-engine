from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from clinical_rules.models import (
    AlertAction,
    ComparisonOperator,
    Condition,
    EvaluationTrace,
    Fact,
    LogicalOperator,
    Rule,
    RuleSetVersion,
    UnknownPolicy,
)


def sample_rule(**overrides):
    data = {
        "id": "diabetes-care-gap",
        "version": "1.0",
        "description": "Identify a diabetes care gap",
        "priority": 2,
        "condition": {
            "operator": "AND",
            "children": [
                {"operator": "gt", "fact": "hba1c", "value": 8.0},
                {"operator": "within_last_days", "fact": "endocrinology_visit", "within_days": 180},
            ],
        },
        "action": {
            "code": "DIABETES_GAP",
            "message": "Diabetes follow-up may be needed",
            "severity": 2,
            "issue": "diabetes-care",
        },
        "unknown_policy": "skip",
        "cooldown_days": 30,
        "effective_from": "2026-01-01",
    }
    data.update(overrides)
    return data


def test_fact_accepts_clinical_observation():
    fact = Fact(
        name="hba1c",
        value=9.1,
        observed_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
        unit="%",
    )
    assert fact.value == 9.1
    assert fact.unit == "%"


def test_condition_supports_logical_tree_and_comparison():
    condition = Condition.model_validate(sample_rule()["condition"])
    assert condition.operator == LogicalOperator.AND
    assert condition.children[0].operator == ComparisonOperator.GT


def test_not_requires_exactly_one_child():
    with pytest.raises(ValidationError, match="NOT requires exactly one"):
        Condition(operator="NOT", children=[])


def test_comparison_requires_fact_name():
    with pytest.raises(ValidationError, match="fact name"):
        Condition(operator="gt", value=8)


def test_time_window_requires_days():
    with pytest.raises(ValidationError, match="requires within_days"):
        Condition(operator="within_last_days", fact="visit")


def test_count_requires_minimum_count():
    with pytest.raises(ValidationError, match="requires minimum_count"):
        Condition(operator="count", fact="er_visits")


def test_rule_defaults_and_effective_dates():
    rule = Rule.model_validate(sample_rule())
    assert rule.unknown_policy == UnknownPolicy.SKIP
    assert rule.cooldown_days == 30
    assert rule.effective_from == date(2026, 1, 1)


def test_rule_rejects_invalid_effective_range():
    with pytest.raises(ValidationError, match="effective_to"):
        Rule.model_validate(sample_rule(effective_to="2025-12-31"))


def test_rule_rejects_unknown_fields():
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Rule.model_validate(sample_rule(unexpected_field=True))


def test_rule_set_rejects_duplicate_rule_ids():
    rule = Rule.model_validate(sample_rule())
    with pytest.raises(ValidationError, match="unique"):
        RuleSetVersion(
            id="clinical-rules",
            version="1",
            effective_from=date(2026, 1, 1),
            rules=[rule, rule],
        )


def test_trace_accepts_a_fired_rule():
    trace = EvaluationTrace(
        rule_id="diabetes-care-gap",
        rule_version="1.0",
        patient_id="patient-1",
        evaluated_at=datetime(2026, 10, 27, tzinfo=timezone.utc),
        outcome="fired",
        explanation="HbA1c exceeded the configured threshold",
        facts_used=["hba1c"],
    )
    assert trace.outcome == "fired"
    assert trace.facts_used == ["hba1c"]


def test_action_severity_must_be_in_range():
    with pytest.raises(ValidationError):
        AlertAction(
            code="X",
            message="Test",
            severity=9,
            issue="test",
        )
