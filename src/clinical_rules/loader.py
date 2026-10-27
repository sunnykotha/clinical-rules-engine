"""Load and validate JSON rule-set files."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from clinical_rules.models import RuleSetVersion


class RuleFileError(ValueError):
    """Raised when a rule file cannot be read or validated."""


def load_rule_set(path: str | Path) -> RuleSetVersion:
    """Read a JSON rule set and return a validated model."""
    source = Path(path)
    try:
        raw_text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuleFileError(f"Could not read rule file {source}: {exc}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuleFileError(
            f"Invalid JSON in {source} at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc

    try:
        return RuleSetVersion.model_validate(data)
    except ValidationError as exc:
        details = []
        for item in exc.errors(include_url=False):
            location = ".".join(str(part) for part in item["loc"]) or "<root>"
            details.append(f"{location}: {item['msg']}")
        raise RuleFileError(
            f"Invalid rule data in {source}: " + "; ".join(details)
        ) from exc
