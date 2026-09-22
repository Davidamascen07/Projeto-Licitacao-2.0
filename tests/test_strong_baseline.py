from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from evaluation.freeze_strong_baseline import freeze


ROOT = Path(__file__).resolve().parents[1]


def audit_payload() -> dict:
    return json.loads(
        (ROOT / "output" / "decision_audit_2026-08-07.json").read_text(encoding="utf-8")
    )


def test_strong_baseline_freezes_only_resolved_audit():
    frozen = freeze(audit_payload())
    assert frozen["counts"]["total"] == 171
    assert frozen["counts"]["golden"] == 46
    assert frozen["counts"]["surgical_review"] == 6
    assert frozen["policy"]["delivery_is_execution"] is False
    assert sum(row["origin"] == "SURGICAL_REVIEW" for row in frozen["decisions"]) == 6


def test_strong_baseline_refuses_unresolved_decision():
    payload = copy.deepcopy(audit_payload())
    payload["decisions"][0]["internal_status"] = "UNRESOLVED"
    with pytest.raises(ValueError, match="bloqueantes"):
        freeze(payload)
