"""
Shared strict JSON parsing/validation for agent AI output (P0 hardening).

Every agent used to hand-roll `json.loads` + a regex fallback and, on any
parse failure, silently return a hardcoded generic response that looked
exactly like a real one to every downstream caller. `parse_ai_json` still
recovers a JSON object from a chatty response (code fences, leading prose),
but on genuine failure it returns (None, error) instead — callers must
decide how to surface that honestly (see AGENT_ERROR_MARKER below) rather
than fabricate content that pretends to be a real AI result.
"""
from __future__ import annotations

import json
import re
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Agents that fall back to a placeholder dict on parse failure should include
# this key so callers (and any human reviewing the record) can tell it apart
# from a genuine AI result instead of silently treating fabricated content as
# real personalization / analysis.
AGENT_ERROR_MARKER = "_ai_parse_failed"


def parse_ai_json(text: str, schema: Type[T]) -> tuple[Optional[T], Optional[str]]:
    """Return (validated_model, None) on success, (None, error) on failure."""
    if not text or not text.strip():
        return None, "empty AI response"
    stripped = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip(), flags=re.M)

    for open_c, close_c in (("{", "}"), ("[", "]")):
        if open_c in stripped and close_c in stripped:
            start, end = stripped.index(open_c), stripped.rindex(close_c)
            if end > start:
                candidate = stripped[start:end + 1]
                try:
                    data = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                try:
                    return schema.model_validate(data), None
                except Exception as e:                                   # noqa: BLE001
                    return None, f"schema validation failed: {e}"

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e}"
    try:
        return schema.model_validate(data), None
    except Exception as e:                                               # noqa: BLE001
        return None, f"schema validation failed: {e}"
