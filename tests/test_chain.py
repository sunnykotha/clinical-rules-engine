from datetime import datetime, timedelta, timezone
from pathlib import Path

from clinical_rules.chain import evaluate_rule_chain
from clinical_rules.loader import load_rule_set
from clinical_rules.models import Fact

RULE_FILE = Path(__file__).parents[1] / "rules" / "diabetes-care-gap.json"
AT = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def _facts(high_hba1c=True, old_visit=True):
    return {
        "hba1c": Fact(
            name="hba1c",
            value=9.1 if high_hba1c else 6.0,
            observed_at=AT - timedelta(days=21),
        ),
        "endocrinology_visit": Fact(
            name="endocrinology_visit",
            value="visit",
            observed_at=AT - timedelta(days=240 if old_visit else 20),
        ),
    }


def _chain_rules(circular=False):
    original = load_rule_set(RULE_FILE)
    base = original.rules[0]
    root = base.model_copy(update={
        "id": "root-rule",
        "triggers": ["child-rule"],
    })
    child = base.model_copy(update={
        "id": "child-rule",
        "triggers": ["root-rule"] if circular else [],
    })
    return original.model_copy(update={"rules": [root, child]})


def test_fired_rule_triggers_child_in_trace():
    result = evaluate_rule_chain(
        _chain_rules(), "root-rule", "patient-1", _facts(), AT
    )
    assert result.outcome == "fired"
    assert len(result.child_traces) == 1
    assert result.child_traces[0].rule_id == "child-rule"
    assert result.child_traces[0].outcome == "fired"


def test_circular_trigger_is_detected_without_infinite_loop():
    result = evaluate_rule_chain(
        _chain_rules(circular=True), "root-rule", "patient-1", _facts(), AT
    )
    child = result.child_traces[0]
    assert child.rule_id == "child-rule"
    assert child.outcome == "fired"
    cycle = child.child_traces[0]
    assert cycle.rule_id == "root-rule"
    assert cycle.outcome == "error"
    assert "Circular rule trigger detected" in cycle.explanation


def test_non_firing_rule_does_not_trigger_child():
    result = evaluate_rule_chain(
        _chain_rules(), "root-rule", "patient-1",
        _facts(high_hba1c=False, old_visit=False), AT
    )
    assert result.outcome == "not_fired"
    assert result.child_traces == []


def test_unknown_root_rule_reports_clear_error():
    import pytest
    with pytest.raises(ValueError, match="Unknown root rule ID"):
        evaluate_rule_chain(
            _chain_rules(), "missing-rule", "patient-1", _facts(), AT
        )


def test_missing_trigger_target_is_traced_as_error():
    original = load_rule_set(RULE_FILE)
    root = original.rules[0].model_copy(update={
        "id": "root-rule",
        "triggers": ["missing-child"],
    })
    rules = original.model_copy(update={"rules": [root]})
    result = evaluate_rule_chain(
        rules, "root-rule", "patient-1", _facts(), AT
    )
    assert result.outcome == "fired"
    assert result.child_traces[0].outcome == "error"
    assert "unknown triggered rule" in result.child_traces[0].explanation