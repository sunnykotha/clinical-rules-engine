from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class LogicalOperator(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class ComparisonOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EXISTS = "exists"
    WITHIN_LAST_DAYS = "within_last_days"
    COUNT = "count"


class UnknownPolicy(str, Enum):
    SKIP = "skip"
    FIRE = "fire"
    ERROR = "error"


class Fact(StrictModel):
    name: str = Field(min_length=1)
    value: Any = None
    observed_at: datetime | None = None
    unit: str | None = None
    source: str | None = None


class Condition(StrictModel):
    """A leaf comparison or a logical node containing child conditions."""
    operator: LogicalOperator | ComparisonOperator
    fact: str | None = None
    value: Any = None
    children: list[Condition] = Field(default_factory=list)
    within_days: int | None = Field(default=None, ge=0)
    minimum_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_shape(self) -> Condition:
        if self.operator in (LogicalOperator.AND, LogicalOperator.OR, LogicalOperator.NOT):
            if self.fact is not None or self.value is not None or self.within_days is not None or self.minimum_count is not None:
                raise ValueError("Logical conditions cannot define fact, value, or time/count parameters")
            if self.operator == LogicalOperator.NOT and len(self.children) != 1:
                raise ValueError("NOT requires exactly one child condition")
            if self.operator in (LogicalOperator.AND, LogicalOperator.OR) and not self.children:
                raise ValueError(f"{self.operator.value} requires at least one child condition")
        else:
            if not self.fact:
                raise ValueError("Comparison conditions require a non-empty fact name")
            if self.children:
                raise ValueError("Comparison conditions cannot contain child conditions")
            if self.operator == ComparisonOperator.WITHIN_LAST_DAYS and self.within_days is None:
                raise ValueError("within_last_days requires within_days")
            if self.operator == ComparisonOperator.COUNT and self.minimum_count is None:
                raise ValueError("count requires minimum_count")
            if self.operator != ComparisonOperator.WITHIN_LAST_DAYS and self.within_days is not None:
                raise ValueError("within_days is only valid with within_last_days")
            if self.operator != ComparisonOperator.COUNT and self.minimum_count is not None:
                raise ValueError("minimum_count is only valid with count")
        return self


class AlertAction(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: int = Field(ge=1, le=5)
    issue: str = Field(min_length=1)
    mutually_exclusive_group: str | None = None


class Rule(StrictModel):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: int = Field(ge=1)
    condition: Condition
    action: AlertAction
    unknown_policy: UnknownPolicy = UnknownPolicy.SKIP
    cooldown_days: int = Field(default=0, ge=0)
    effective_from: date
    effective_to: date | None = None
    triggers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_effective_dates(self) -> Rule:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        return self


class RuleSetVersion(StrictModel):
    id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    effective_from: date
    effective_to: date | None = None
    rules: list[Rule]

    @model_validator(mode="after")
    def validate_rule_set(self) -> RuleSetVersion:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("Rule IDs must be unique within a rule set version")
        return self


class EvaluationTrace(StrictModel):
    rule_id: str
    rule_version: str
    patient_id: str
    evaluated_at: datetime
    outcome: str = Field(pattern="^(fired|suppressed|not_fired|unknown|error)$")
    explanation: str = Field(min_length=1)
    facts_used: list[str] = Field(default_factory=list)
    child_traces: list[EvaluationTrace] = Field(default_factory=list)
