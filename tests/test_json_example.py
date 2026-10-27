from datetime import datetime, timedelta, timezone
from pathlib import Path

from clinical_rules.engine import evaluate_rule_set
from clinical_rules.loader import load_rule_set
from clinical_rules.models import Fact

AT = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
EXAMPLE_FILE = (
    Path(__file__).parents[1]
    / "rules"
    / "diabetes-worked-example.json"
)


def test_two_rule_example_loads_from_json():
    rule_set = load_rule_set(EXAMPLE_FILE)
    assert len(rule_set.rules) == 2
    assert {rule.id for rule in rule_set.rules} == {
        "uncontrolled-diabetes-recent-er",
        "diabetes-care-gap",
    }


def test_json_example_fires_high_severity_and_suppresses_care_gap():
    rule_set = load_rule_set(EXAMPLE_FILE)
    facts = {
        "hba1c": Fact(
            name="hba1c",
            value=9.1,
            observed_at=AT - timedelta(days=21),
        ),
        "endocrinology_visit": Fact(
            name="endocrinology_visit",
            value="visit",
            observed_at=AT - timedelta(days=240),
        ),
        "emergency_visit": Fact(
            name="emergency_visit",
            value="emergency visit",
            observed_at=AT - timedelta(days=5),
        ),
    }

    traces = evaluate_rule_set(
        rule_set=rule_set,
        patient_id="patient-json-example",
        facts=facts,
        evaluated_at=AT,
    )
    by_id = {trace.rule_id: trace for trace in traces}

    assert by_id["uncontrolled-diabetes-recent-er"].outcome == "fired"
    assert by_id["diabetes-care-gap"].outcome == "suppressed"
    assert "hba1c" in by_id["uncontrolled-diabetes-recent-er"].facts_used
    assert "emergency_visit" in by_id[
        "uncontrolled-diabetes-recent-er"
    ].facts_used
    assert by_id["diabetes-care-gap"].explanation