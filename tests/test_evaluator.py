from datetime import datetime, timezone, timedelta

import pytest

from clinical_rules.evaluator import evaluate_condition
from clinical_rules.models import Condition, Fact


NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)


def evaluate(data, facts, at=NOW):
    return evaluate_condition(Condition.model_validate(data), facts, at)


@pytest.mark.parametrize(("operator", "value", "expected", "outcome"), [
    ("eq", 5, 5, True),
    ("ne", 5, 4, True),
    ("gt", 6, 5, True),
    ("gte", 5, 5, True),
    ("lt", 4, 5, True),
    ("lte", 5, 5, True),
])
def test_scalar_comparisons(operator, value, expected, outcome):
    result = evaluate({"operator": operator, "fact": "x", "value": expected}, {"x": Fact(name="x", value=value)})
    assert result.outcome is outcome
    assert "x" in result.facts_used
    assert result.explanation


def test_missing_fact_is_unknown_not_false():
    result = evaluate({"operator": "gt", "fact": "hba1c", "value": 8}, {})
    assert result.outcome is None
    assert "missing" in result.explanation.lower()


def test_explicit_null_fact_is_unknown():
    result = evaluate({"operator": "gt", "fact": "hba1c", "value": 8}, {"hba1c": Fact(name="hba1c")})
    assert result.outcome is None


def test_exists_true_for_present_value():
    result = evaluate({"operator": "exists", "fact": "visit"}, {"visit": Fact(name="visit", value="recorded")})
    assert result.outcome is True


def test_exists_unknown_for_null_fact():
    result = evaluate({"operator": "exists", "fact": "visit"}, {"visit": Fact(name="visit")})
    assert result.outcome is None


def test_within_last_days_true_for_recent_observation():
    recent = Fact(name="visit", value="yes", observed_at=NOW - timedelta(days=20))
    result = evaluate({"operator": "within_last_days", "fact": "visit", "within_days": 180}, {"visit": recent})
    assert result.outcome is True


def test_within_last_days_false_for_old_observation():
    old = Fact(name="visit", value="yes", observed_at=NOW - timedelta(days=200))
    result = evaluate({"operator": "within_last_days", "fact": "visit", "within_days": 180}, {"visit": old})
    assert result.outcome is False


def test_within_last_days_unknown_without_timestamp():
    result = evaluate({"operator": "within_last_days", "fact": "visit", "within_days": 180}, {"visit": Fact(name="visit", value="yes")})
    assert result.outcome is None


def test_count_observations():
    events = [Fact(name="visit", value="one"), Fact(name="visit", value="two"), Fact(name="visit")]
    result = evaluate({"operator": "count", "fact": "visit", "minimum_count": 2}, {"visit": events})
    assert result.outcome is True


def test_count_missing_is_unknown():
    result = evaluate({"operator": "count", "fact": "visits", "minimum_count": 1}, {})
    assert result.outcome is None


def test_and_or_not_three_valued_logic():
    facts = {"a": Fact(name="a", value=10), "b": Fact(name="b", value=0)}
    gt_a = {"operator": "gt", "fact": "a", "value": 5}
    gt_b = {"operator": "gt", "fact": "b", "value": 5}
    assert evaluate({"operator": "AND", "children": [gt_a, gt_b]}, facts).outcome is False
    assert evaluate({"operator": "OR", "children": [gt_a, gt_b]}, facts).outcome is True
    assert evaluate({"operator": "NOT", "children": [gt_b]}, facts).outcome is True


def test_and_with_unknown_and_true_is_unknown():
    result = evaluate({"operator": "AND", "children": [
        {"operator": "gt", "fact": "missing", "value": 8},
        {"operator": "gt", "fact": "a", "value": 5},
    ]}, {"a": Fact(name="a", value=10)})
    assert result.outcome is None


def test_or_with_unknown_and_false_is_unknown():
    result = evaluate({"operator": "OR", "children": [
        {"operator": "gt", "fact": "missing", "value": 8},
        {"operator": "gt", "fact": "a", "value": 5},
    ]}, {"a": Fact(name="a", value=1)})
    assert result.outcome is None


def test_nested_trace_explains_facts_and_children():
    result = evaluate({"operator": "AND", "children": [
        {"operator": "gt", "fact": "hba1c", "value": 8},
        {"operator": "eq", "fact": "smoker", "value": True},
    ]}, {"hba1c": Fact(name="hba1c", value=9.1), "smoker": Fact(name="smoker", value=True)})
    assert result.outcome is True
    assert result.facts_used == ("hba1c", "smoker")
    assert len(result.child_results) == 2
    assert all(child.explanation for child in result.child_results)


def test_future_observation_is_not_within_window():
    future = Fact(name="visit", value="yes", observed_at=NOW + timedelta(days=1))
    result = evaluate({"operator": "within_last_days", "fact": "visit", "within_days": 180}, {"visit": future})
    assert result.outcome is False
