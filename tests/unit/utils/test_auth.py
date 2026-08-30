from __future__ import annotations

import json

from src.utils.auth import match_api_key, parse_api_keys


def test_structured_api_key_metadata_is_normalized() -> None:
    parsed = parse_api_keys(json.dumps({"secret-key": {"user_id": "alice", "role": "Admin"}}))

    assert parsed == {"secret-key": {"user_id": "alice", "role": "admin"}}
    assert match_api_key("secret-key", parsed) == {"user_id": "alice", "role": "admin"}


def test_legacy_api_key_mapping_cannot_grant_privileged_role() -> None:
    parsed = parse_api_keys("legacy-key:admin")

    assert parsed["legacy-key"] == {"user_id": "admin", "role": "user"}


def test_raw_configuration_string_is_not_an_api_key() -> None:
    raw = json.dumps({"secret-key": {"user_id": "alice", "role": "admin"}})

    assert match_api_key(raw, parse_api_keys(raw)) is None
