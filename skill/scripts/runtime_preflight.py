#!/usr/bin/env python3
"""Content-free contract check for a connected benchmark runtime."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
HELP_SCOUT_CONTRACT = json.loads(
    (CONTRACTS / "help-scout.json").read_text(encoding="utf-8")
)
HELP_SCOUT_CORRELATION_CONTRACT = json.loads(
    (CONTRACTS / "help-scout-correlation.json").read_text(encoding="utf-8")
)
RUNTIME_PREFLIGHT_CONTRACT = json.loads(
    (CONTRACTS / "runtime-preflight.json").read_text(encoding="utf-8")
)

HELP_SCOUT_CAPABILITIES = frozenset(
    [
        HELP_SCOUT_CONTRACT["requiredCapability"],
        *HELP_SCOUT_CONTRACT["requiredTargetCapabilities"],
        HELP_SCOUT_CORRELATION_CONTRACT["requiredCapability"],
    ]
)
HELP_SCOUT_CORRELATION_OUTPUT_MODE = HELP_SCOUT_CORRELATION_CONTRACT[
    "requiredOutputMode"
]
GATEWAY_TOOLS = frozenset(RUNTIME_PREFLIGHT_CONTRACT["gatewayTools"])
HELP_SCOUT_TARGET_OUTPUT_MODES = frozenset(
    RUNTIME_PREFLIGHT_CONTRACT["targetOutputModes"]
)
INPUT_KEYS = {
    "helpScoutCapabilities",
    "helpScoutTargetOutputModes",
    "helpScoutCorrelationOutputMode",
    "gatewayTools",
}

RUNTIME_CONTRACT_MISMATCH = {
    "ok": False,
    "error": "runtime_contract_mismatch",
}
MAX_INPUT_BYTES = 16_384


def evaluate_runtime_contract(payload: Any) -> dict[str, bool | str]:
    """Compare discovered names with the exact reviewed surface."""

    if type(payload) is not dict or set(payload) != INPUT_KEYS:
        return RUNTIME_CONTRACT_MISMATCH.copy()

    capabilities = payload["helpScoutCapabilities"]
    target_output_modes = payload["helpScoutTargetOutputModes"]
    correlation_output_mode = payload["helpScoutCorrelationOutputMode"]
    tools = payload["gatewayTools"]
    if (
        type(capabilities) is not list
        or type(target_output_modes) is not list
        or type(tools) is not list
    ):
        return RUNTIME_CONTRACT_MISMATCH.copy()
    if (
        type(correlation_output_mode) is not str
        or correlation_output_mode != HELP_SCOUT_CORRELATION_OUTPUT_MODE
    ):
        return RUNTIME_CONTRACT_MISMATCH.copy()
    if any(
        type(value) is not str
        for value in capabilities + target_output_modes + tools
    ):
        return RUNTIME_CONTRACT_MISMATCH.copy()
    if (
        len(capabilities) != len(set(capabilities))
        or len(target_output_modes) != len(set(target_output_modes))
        or len(tools) != len(set(tools))
    ):
        return RUNTIME_CONTRACT_MISMATCH.copy()
    if (
        set(capabilities) != HELP_SCOUT_CAPABILITIES
        or set(target_output_modes) != HELP_SCOUT_TARGET_OUTPUT_MODES
        or set(tools) != GATEWAY_TOOLS
    ):
        return RUNTIME_CONTRACT_MISMATCH.copy()

    return {"ok": True}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if not raw or len(raw) > MAX_INPUT_BYTES:
            raise ValueError("runtime contract input is invalid")
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        result = RUNTIME_CONTRACT_MISMATCH.copy()
    else:
        result = evaluate_runtime_contract(payload)

    print(json.dumps(result, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
