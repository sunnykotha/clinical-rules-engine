from datetime import datetime, timedelta, timezone
from pathlib import Path

from clinical_rules.cooldown import CooldownTracker
from clinical_rules.engine import evaluate_rule_set
from clinical_rules.loader import load_rule_set
from clinical_rules.models import Fact

RULE_FILE = Path(__file__).parents[1] / "rules" / "diabetes-care-gap.json"
START = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)


def _rules():
    return load_rule_set(RULE_FILE)


def _facts():
    return {
        "hba1c": Fact(
            name="hba1c", value=9.1, observed_at=START - timedelta(days=21)
        ),
        "endocrinology_visit": Fact(
            name="endocrinology_visit", value="visit",
            observed_at=START - timedelta(days=240),
        ),
    }


def test_first_alert_fires_then_repeated_alert_is_suppressed():
    tracker = CooldownTracker()
    first = evaluate_rule_set(_rules(), "p1", _facts(), START, tracker)
    assert first[0].outcome == "fired"

    later = evaluate_rule_set(
        _rules(), "p1", _facts(), START + timedelta(days=2), tracker
    )
    assert later[0].outcome == "suppressed"
    assert "cooldown" in later[0].explanation.lower()


def test_alert_fires_again_after_cooldown_expires():
    tracker = CooldownTracker()
    evaluate_rule_set(_rules(), "p1", _facts(), START, tracker)
    later = evaluate_rule_set(
        _rules(), "p1", _facts(), START + timedelta(days=31), tracker
    )
    assert later[0].outcome == "fired"


def test_cooldown_is_independent_per_patient():
    tracker = CooldownTracker()
    evaluate_rule_set(_rules(), "p1", _facts(), START, tracker)
    p2 = evaluate_rule_set(
        _rules(), "p2", _facts(), START + timedelta(days=1), tracker
    )
    assert p2[0].outcome == "fired"


def test_zero_cooldown_does_not_suppress_repeated_alerts():
    tracker = CooldownTracker()
    rule_set = _rules()
    rule_set.rules[0].cooldown_days = 0
    assert evaluate_rule_set(
        rule_set, "p1", _facts(), START, tracker
    )[0].outcome == "fired"
    assert evaluate_rule_set(
        rule_set, "p1", _facts(), START + timedelta(days=1), tracker
    )[0].outcome == "fired"


def test_clear_resets_cooldown_history():
    tracker = CooldownTracker()
    evaluate_rule_set(_rules(), "p1", _facts(), START, tracker)
    tracker.clear()
    later = evaluate_rule_set(
        _rules(), "p1", _facts(), START + timedelta(days=1), tracker
    )
    assert later[0].outcome == "fired"