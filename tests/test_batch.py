from datetime import datetime, timedelta, timezone
from pathlib import Path

from clinical_rules.batch import evaluate_patients
from clinical_rules.loader import load_rule_set
from clinical_rules.models import Fact

AT = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
RULE_FILE = Path(__file__).parents[1] / "rules" / "diabetes-care-gap.json"


def _patients(count, facts):
    for number in range(count):
        yield f"patient-{number}", facts


def _facts():
    return {
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
    }


def test_batch_evaluation_is_lazy():
    rule_set = load_rule_set(RULE_FILE)
    results = evaluate_patients(rule_set, _patients(100_000, _facts()), AT)

    first_id, first_traces = next(results)
    second_id, second_traces = next(results)

    assert first_id == "patient-0"
    assert second_id == "patient-1"
    assert first_traces
    assert second_traces


def test_batch_evaluates_100000_patients():
    rule_set = load_rule_set(RULE_FILE)
    facts = _facts()
    count = 0
    fired = 0
    last_id = None

    for patient_id, traces in evaluate_patients(
        rule_set, _patients(100_000, facts), AT
    ):
        count += 1
        last_id = patient_id
        fired += sum(trace.outcome == "fired" for trace in traces)

    assert count == 100_000
    assert last_id == "patient-99999"
    assert fired == 100_000