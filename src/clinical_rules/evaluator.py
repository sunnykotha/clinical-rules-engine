"""Evaluate clinical condition trees using three-valued logic."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping

from clinical_rules.models import ComparisonOperator, Condition, Fact, LogicalOperator


Outcome = bool | None


@dataclass(frozen=True)
class ConditionResult:
    """Outcome and human-readable evidence for a condition evaluation."""

    outcome: Outcome
    explanation: str
    facts_used: tuple[str, ...] = ()
    child_results: tuple["ConditionResult", ...] = ()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _fact_value(fact: Fact) -> object | None:
    return fact.value


def _dedupe(items: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def evaluate_condition(
    condition: Condition,
    facts: Mapping[str, Fact | list[Fact] | None],
    evaluated_at: datetime | None = None,
) -> ConditionResult:
    """Evaluate a condition. Missing or incomplete data yields unknown (None)."""
    at = evaluated_at or _now_utc()

    if isinstance(condition.operator, LogicalOperator):
        children = tuple(evaluate_condition(child, facts, at) for child in condition.children)
        outcomes = [child.outcome for child in children]
        if condition.operator == LogicalOperator.AND:
            outcome = False if False in outcomes else (True if all(x is True for x in outcomes) else None)
            explanation = "AND: at least one condition is false" if outcome is False else (
                "AND: all conditions are true" if outcome is True else "AND: result is unknown because data is missing"
            )
        elif condition.operator == LogicalOperator.OR:
            outcome = True if True in outcomes else (False if all(x is False for x in outcomes) else None)
            explanation = "OR: at least one condition is true" if outcome is True else (
                "OR: all conditions are false" if outcome is False else "OR: result is unknown because data is missing"
            )
        else:
            child_outcome = outcomes[0]
            outcome = None if child_outcome is None else not child_outcome
            explanation = "NOT: child result is unknown" if outcome is None else f"NOT: child condition is {str(child_outcome).lower()}"
        used = _dedupe([name for child in children for name in child.facts_used])
        return ConditionResult(outcome, explanation, used, children)

    fact_name = condition.fact or ""
    raw = facts.get(fact_name)
    if raw is None:
        return ConditionResult(None, f"Fact '{fact_name}' is missing", (fact_name,))
    if isinstance(raw, list):
        if condition.operator == ComparisonOperator.COUNT:
            count = sum(1 for item in raw if item.value is not None)
            outcome = count >= (condition.minimum_count or 0)
            return ConditionResult(outcome, f"Fact '{fact_name}' count is {count}; minimum required is {condition.minimum_count}", (fact_name,))
        if len(raw) == 0:
            if condition.operator == ComparisonOperator.EXISTS:
                return ConditionResult(False, f"No observations exist for fact '{fact_name}'", (fact_name,))
            return ConditionResult(None, f"Fact '{fact_name}' has no observations", (fact_name,))
        # A list of observations is treated as event history for time-window checks.
        if condition.operator == ComparisonOperator.WITHIN_LAST_DAYS:
            cutoff = at - timedelta(days=condition.within_days or 0)
            valid_times = [item.observed_at for item in raw if item.observed_at is not None]
            if not valid_times:
                return ConditionResult(None, f"Observation dates for '{fact_name}' are missing", (fact_name,))
            found = any(cutoff <= observed <= at for observed in valid_times)
            return ConditionResult(found, f"Fact '{fact_name}' {'has' if found else 'has no'} observation in the last {condition.within_days} days", (fact_name,))
        # For ordinary comparisons, use the most recently observed non-null value.
        dated = [item for item in raw if item.value is not None]
        if not dated:
            return ConditionResult(None, f"Values for fact '{fact_name}' are missing", (fact_name,))
        raw = max(dated, key=lambda item: item.observed_at or datetime.min.replace(tzinfo=timezone.utc))

    if condition.operator == ComparisonOperator.COUNT:
        return ConditionResult(None, f"Fact '{fact_name}' is not an observation list required for count", (fact_name,))

    value = _fact_value(raw)
    if condition.operator == ComparisonOperator.EXISTS:
        if value is None:
            return ConditionResult(None, f"Fact '{fact_name}' has no value, so existence is unknown", (fact_name,))
        return ConditionResult(True, f"Fact '{fact_name}' exists", (fact_name,))

    if condition.operator == ComparisonOperator.WITHIN_LAST_DAYS:
        if raw.observed_at is None:
            return ConditionResult(None, f"Observation date for '{fact_name}' is missing", (fact_name,))
        observed = raw.observed_at
        if observed.tzinfo is None and at.tzinfo is not None:
            observed = observed.replace(tzinfo=at.tzinfo)
        if at.tzinfo is None and observed.tzinfo is not None:
            at = at.replace(tzinfo=observed.tzinfo)
        found = at - timedelta(days=condition.within_days or 0) <= observed <= at
        return ConditionResult(found, f"Fact '{fact_name}' {'was observed' if found else 'was not observed'} within the last {condition.within_days} days", (fact_name,))

    if value is None:
        return ConditionResult(None, f"Value for fact '{fact_name}' is missing", (fact_name,))

    expected = condition.value
    try:
        if condition.operator == ComparisonOperator.EQ:
            outcome = value == expected
        elif condition.operator == ComparisonOperator.NE:
            outcome = value != expected
        elif condition.operator == ComparisonOperator.GT:
            outcome = value > expected
        elif condition.operator == ComparisonOperator.GTE:
            outcome = value >= expected
        elif condition.operator == ComparisonOperator.LT:
            outcome = value < expected
        elif condition.operator == ComparisonOperator.LTE:
            outcome = value <= expected
        else:
            return ConditionResult(None, f"Unsupported comparison operator '{condition.operator}'", (fact_name,))
    except (TypeError, ValueError) as exc:
        return ConditionResult(None, f"Cannot compare fact '{fact_name}' with configured value: {exc}", (fact_name,))

    symbol = {
        ComparisonOperator.EQ: "==",
        ComparisonOperator.NE: "!=",
        ComparisonOperator.GT: ">",
        ComparisonOperator.GTE: ">=",
        ComparisonOperator.LT: "<",
        ComparisonOperator.LTE: "<=",
    }[condition.operator]
    return ConditionResult(outcome, f"Fact '{fact_name}' value {value!r} {symbol} {expected!r} evaluated to {str(outcome).lower()}", (fact_name,))
