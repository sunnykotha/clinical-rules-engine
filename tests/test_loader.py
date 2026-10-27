import json
from pathlib import Path

import pytest

from clinical_rules.loader import RuleFileError, load_rule_set


RULE_FILE = Path(__file__).parents[1] / "rules" / "diabetes-care-gap.json"


def test_loads_valid_rule_set():
    rule_set = load_rule_set(RULE_FILE)
    assert rule_set.id == "clinical-guidelines"
    assert rule_set.version == "1.0"
    assert len(rule_set.rules) == 1
    assert rule_set.rules[0].id == "diabetes-care-gap"


def test_malformed_json_has_location_in_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"id": ', encoding="utf-8")
    with pytest.raises(RuleFileError, match=r"Invalid JSON.*line 1"):
        load_rule_set(path)


def test_missing_required_field_is_reported(tmp_path):
    data = json.loads(RULE_FILE.read_text(encoding="utf-8"))
    del data["rules"][0]["priority"]
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuleFileError, match=r"priority"):
        load_rule_set(path)


def test_invalid_operator_is_reported(tmp_path):
    data = json.loads(RULE_FILE.read_text(encoding="utf-8"))
    data["rules"][0]["condition"]["children"][0]["operator"] = "bogus"
    path = tmp_path / "operator.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuleFileError, match=r"operator"):
        load_rule_set(path)


def test_duplicate_rule_ids_are_reported(tmp_path):
    data = json.loads(RULE_FILE.read_text(encoding="utf-8"))
    data["rules"].append(data["rules"][0].copy())
    path = tmp_path / "duplicates.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuleFileError, match=r"Rule IDs must be unique"):
        load_rule_set(path)


def test_missing_file_has_clear_error(tmp_path):
    with pytest.raises(RuleFileError, match=r"Could not read rule file"):
        load_rule_set(tmp_path / "absent.json")
