from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime

from .cooldown import CooldownTracker
from .engine import evaluate_rule_set
from .models import EvaluationTrace, Fact, RuleSetVersion

FactCollection = Fact | list[Fact] | None
PatientInput = tuple[str, Mapping[str, FactCollection]]
PatientResult = tuple[str, list[EvaluationTrace]]


def evaluate_patients(
    rule_set: RuleSetVersion,
    patients: Iterable[PatientInput],
    evaluated_at: datetime | None = None,
    cooldown_tracker: CooldownTracker | None = None,
) -> Iterator[PatientResult]:
    """Evaluate patients lazily, yielding each patient's traces immediately."""
    for patient_id, facts in patients:
        yield patient_id, evaluate_rule_set(
            rule_set=rule_set,
            patient_id=patient_id,
            facts=facts,
            evaluated_at=evaluated_at,
            cooldown_tracker=cooldown_tracker,
        )