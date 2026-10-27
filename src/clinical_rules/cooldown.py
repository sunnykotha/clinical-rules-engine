"""Per-patient, per-rule alert cooldown tracking."""
from datetime import datetime, timedelta
from clinical_rules.models import Rule


class CooldownTracker:
    """In-memory store. Reuse one instance across evaluations."""

    def __init__(self):
        self._last_fired = {}

    def is_in_cooldown(self, rule: Rule, patient_id: str, evaluated_at: datetime) -> bool:
        if rule.cooldown_days <= 0:
            return False
        previous = self._last_fired.get((patient_id, rule.id))
        if previous is None:
            return False
        current = evaluated_at
        if current.tzinfo is None and previous.tzinfo is not None:
            previous = previous.replace(tzinfo=None)
        elif current.tzinfo is not None and previous.tzinfo is None:
            previous = previous.replace(tzinfo=current.tzinfo)
        return current < previous + timedelta(days=rule.cooldown_days)

    def record_fired(self, rule: Rule, patient_id: str, evaluated_at: datetime) -> None:
        if rule.cooldown_days > 0:
            self._last_fired[(patient_id, rule.id)] = evaluated_at

    def clear(self) -> None:
        self._last_fired.clear()