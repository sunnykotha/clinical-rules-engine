"""Execute clinical rules and resolve competing alerts."""
from datetime import date, datetime, timezone
from typing import Mapping

from clinical_rules.cooldown import CooldownTracker
from clinical_rules.evaluator import evaluate_condition
from clinical_rules.models import EvaluationTrace, Fact, Rule, RuleSetVersion, UnknownPolicy


def _as_fact_map(facts: Mapping[str, Fact | list[Fact] | None]):
    return dict(facts)


def _rule_is_active(rule: Rule, on_date: date) -> bool:
    return rule.effective_from <= on_date and (
        rule.effective_to is None or on_date <= rule.effective_to
    )


def _rank(rule: Rule):
    return (rule.priority, -rule.action.severity, rule.id)


def evaluate_rule_set(
    rule_set: RuleSetVersion,
    patient_id: str,
    facts: Mapping[str, Fact | list[Fact] | None],
    evaluated_at: datetime | None = None,
    cooldown_tracker: CooldownTracker | None = None,
) -> list[EvaluationTrace]:
    """Evaluate rules, apply cooldowns, then resolve competing alerts.

    Reuse the same CooldownTracker across evaluations to enforce cooldowns.
    Only alerts that survive conflict resolution start a cooldown.
    """
    at = evaluated_at or datetime.now(timezone.utc)
    on_date = at.date()
    fact_map = _as_fact_map(facts)
    ordered_rules = sorted(rule_set.rules, key=_rank)
    rule_by_id = {rule.id: rule for rule in ordered_rules}
    traces: list[EvaluationTrace] = []

    ruleset_active = rule_set.effective_from <= on_date and (
        rule_set.effective_to is None or on_date <= rule_set.effective_to
    )

    for rule in ordered_rules:
        if not ruleset_active:
            outcome = "not_fired"
            explanation = f"Rule set '{rule_set.id}' is not effective on {on_date.isoformat()}"
            used = []
        elif not _rule_is_active(rule, on_date):
            outcome = "not_fired"
            explanation = f"Rule '{rule.id}' is not effective on {on_date.isoformat()}"
            used = []
        else:
            result = evaluate_condition(rule.condition, fact_map, at)
            used = list(result.facts_used)
            if result.outcome is True:
                outcome = "fired"
                explanation = (
                    f"Rule '{rule.id}' fired: {result.explanation}. "
                    f"Action: {rule.action.code} — {rule.action.message}"
                )
            elif result.outcome is False:
                outcome = "not_fired"
                explanation = f"Rule '{rule.id}' did not fire: {result.explanation}"
            elif rule.unknown_policy == UnknownPolicy.FIRE:
                outcome = "fired"
                explanation = (
                    f"Rule '{rule.id}' fired under unknown_policy=fire: "
                    f"{result.explanation}. Action: {rule.action.code} — "
                    f"{rule.action.message}"
                )
            elif rule.unknown_policy == UnknownPolicy.ERROR:
                outcome = "error"
                explanation = (
                    f"Rule '{rule.id}' could not be evaluated because required "
                    f"data is unknown: {result.explanation}"
                )
            else:
                outcome = "unknown"
                explanation = (
                    f"Rule '{rule.id}' skipped because required data is unknown: "
                    f"{result.explanation}"
                )

        traces.append(EvaluationTrace(
            rule_id=rule.id,
            rule_version=rule.version,
            patient_id=patient_id,
            evaluated_at=at,
            outcome=outcome,
            explanation=explanation,
            facts_used=used,
        ))

    # Suppress candidate alerts already in cooldown.
    if cooldown_tracker is not None:
        for index, trace in enumerate(traces):
            if trace.outcome != "fired":
                continue
            rule = rule_by_id[trace.rule_id]
            if cooldown_tracker.is_in_cooldown(rule, patient_id, at):
                traces[index] = trace.model_copy(update={
                    "outcome": "suppressed",
                    "explanation": (
                        f"Rule '{rule.id}' alert suppressed by cooldown "
                        f"({rule.cooldown_days} days) for patient '{patient_id}'."
                    ),
                })

    # Resolve same-issue alerts and mutually exclusive groups.
    fired = [trace for trace in traces if trace.outcome == "fired"]
    suppressed_by: dict[str, str] = {}

    for candidate in fired:
        rule = rule_by_id[candidate.rule_id]
        for other in fired:
            if other.rule_id == candidate.rule_id:
                continue
            other_rule = rule_by_id[other.rule_id]
            same_issue = rule.action.issue == other_rule.action.issue
            same_group = (
                rule.action.mutually_exclusive_group is not None
                and rule.action.mutually_exclusive_group
                == other_rule.action.mutually_exclusive_group
            )

            if same_issue:
                other_wins = (
                    other_rule.action.severity > rule.action.severity
                    or (
                        other_rule.action.severity == rule.action.severity
                        and _rank(other_rule) < _rank(rule)
                    )
                )
                if other_wins:
                    suppressed_by[candidate.rule_id] = other.rule_id
                    break

            if same_group and not same_issue and _rank(other_rule) < _rank(rule):
                suppressed_by[candidate.rule_id] = other.rule_id
                break

    resolved: list[EvaluationTrace] = []
    for trace in traces:
        winner_id = suppressed_by.get(trace.rule_id)
        if winner_id:
            winner = rule_by_id[winner_id]
            resolved.append(trace.model_copy(update={
                "outcome": "suppressed",
                "explanation": (
                    f"Rule '{trace.rule_id}' alert was suppressed by "
                    f"higher-ranked conflicting rule '{winner_id}' "
                    f"(action {winner.action.code})."
                ),
            }))
        else:
            resolved.append(trace)

    # Start cooldown only for alerts actually emitted.
    if cooldown_tracker is not None:
        for trace in resolved:
            if trace.outcome == "fired":
                cooldown_tracker.record_fired(
                    rule_by_id[trace.rule_id], patient_id, at
                )

    return resolved


evaluate_rules = evaluate_rule_set