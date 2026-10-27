"""Rule chaining with path-based circular-trigger detection."""
from datetime import datetime, timezone
from typing import Mapping

from clinical_rules.cooldown import CooldownTracker
from clinical_rules.engine import evaluate_rule_set
from clinical_rules.models import EvaluationTrace, Fact, Rule, RuleSetVersion


def evaluate_rule_chain(
    rule_set: RuleSetVersion,
    root_rule_id: str,
    patient_id: str,
    facts: Mapping[str, Fact | list[Fact] | None],
    evaluated_at: datetime | None = None,
    cooldown_tracker: CooldownTracker | None = None,
) -> EvaluationTrace:
    """Evaluate one root rule and recursively follow its triggers.

    A triggered rule runs only if its parent fires. Circular paths are stopped
    and represented as error child traces. A shared tracker can enforce cooldowns.
    """
    at = evaluated_at or datetime.now(timezone.utc)
    rules_by_id = {rule.id: rule for rule in rule_set.rules}

    if root_rule_id not in rules_by_id:
        raise ValueError(f"Unknown root rule ID: '{root_rule_id}'")

    def visit(rule_id: str, path: tuple[str, ...]) -> EvaluationTrace:
        rule = rules_by_id[rule_id]

        # Guard against cycles before evaluating a rule already on this path.
        if rule_id in path:
            return EvaluationTrace(
                rule_id=rule.id,
                rule_version=rule.version,
                patient_id=patient_id,
                evaluated_at=at,
                outcome="error",
                explanation=(
                    "Circular rule trigger detected: "
                    + " -> ".join((*path, rule_id))
                ),
                facts_used=[],
                child_traces=[],
            )

        single_rule_set = rule_set.model_copy(update={"rules": [rule]})
        result = evaluate_rule_set(
            single_rule_set,
            patient_id,
            facts,
            at,
            cooldown_tracker,
        )[0]

        if result.outcome != "fired":
            return result

        next_path = (*path, rule_id)
        children: list[EvaluationTrace] = []

        for triggered_id in rule.triggers:
            if triggered_id not in rules_by_id:
                children.append(EvaluationTrace(
                    rule_id=triggered_id,
                    rule_version="unknown",
                    patient_id=patient_id,
                    evaluated_at=at,
                    outcome="error",
                    explanation=(
                        f"Rule '{rule.id}' references unknown triggered rule "
                        f"'{triggered_id}'."
                    ),
                    facts_used=[],
                    child_traces=[],
                ))
                continue

            children.append(visit(triggered_id, next_path))

        return result.model_copy(update={"child_traces": children})

    return visit(root_rule_id, ())