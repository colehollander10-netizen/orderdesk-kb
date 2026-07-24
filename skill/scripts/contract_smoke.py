#!/usr/bin/env python3
"""Portable skill checks with explicit opt-in local/integration probes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PUBLIC = SKILL / "scripts" / "public_kb.py"
HELP_SCOUT_MANIFEST = SKILL / "contracts" / "help-scout.json"
INVESTIGATION_MANIFEST = SKILL / "contracts" / "investigation.json"
HELP_SCOUT_CORRELATION_MANIFEST = SKILL / "contracts" / "help-scout-correlation.json"
RUNTIME_PREFLIGHT_MANIFEST = SKILL / "contracts" / "runtime-preflight.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_public(command: str, query: str | None = None) -> dict:
    argv = [sys.executable, str(PUBLIC), command]
    if command in ("search", "triage"):
        argv.extend(["--limit", "2"])
    completed = subprocess.run(
        argv,
        input=None if query is None else json.dumps(query) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    require(completed.returncode == 0, completed.stderr.strip())
    return json.loads(completed.stdout)


def check_links() -> None:
    files = [SKILL / "SKILL.md", *(SKILL / "references").glob("*.md")]
    for source in files:
        text = source.read_text()
        for target in re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", text):
            require(
                (source.parent / target).resolve().is_file(),
                f"broken link: {source} -> {target}",
            )


def check_runtimes() -> None:
    expected = [
        Path.home() / ".codex" / "skills" / "orderdesk",
        Path.home() / ".claude" / "skills" / "orderdesk",
        Path.home() / ".claude" / ".agents" / "skills" / "orderdesk",
    ]
    canonical = SKILL.resolve()
    for runtime in expected:
        require(runtime.is_symlink(), f"runtime is not a symlink: {runtime}")
        require(runtime.resolve() == canonical, f"runtime points elsewhere: {runtime}")


def check_text_contract() -> None:
    text = "\n".join(path.read_text() for path in SKILL.rglob("*.md"))
    for stale in (
        "named Order Desk reviewer has approved",
        "result shape includes masking status",
        'no "medium"',
    ):
        require(stale not in text, f"stale safety phrase found: {stale}")
    require((SKILL / "agents" / "openai.yaml").is_file(), "agents/openai.yaml missing")
    for required in (
        "one positive Help Scout ticket number",
        "slack_search",
        "notion_search",
        "code_context",
        "s3_log_lookup",
        "Investigation Plan",
        "Source Ledger",
        "Support can answer",
        "Insufficient evidence — abstain",
        "Customer-reply drafting is outside `/orderdesk`",
        "Never create, save, or send a Help Scout draft",
    ):
        require(required in text, f"required skill contract missing: {required}")
    for forbidden in (
        "**Customer copy:**",
        "Separate customer-copy follow-up",
        "After a separate customer-copy request",
        "A later customer-copy request",
        "reply coaching",
        "paste-ready customer follow-ups",
    ):
        require(forbidden not in text, "customer-copy mode is outside this skill")
    governed_text = (SKILL / "references" / "governed-context.md").read_text()
    for tool in ("slack_search", "notion_search", "notion_page", "code_context"):
        require(f"`{tool}`" in governed_text, f"required governed tool missing: {tool}")
    require("`s3_log_lookup` is conditional" in governed_text, "S3 Logs availability boundary is missing")
    require("synthetic vertical slice" in governed_text, "synthetic-only S3 proof boundary is missing")
    require("aws_log_lookup" not in text, "nonexistent AWS log tool is still advertised")
    require("Cole explicitly" not in text, "skill still hardcodes a personal operator")


def check_help_scout_contract() -> None:
    skill_text = " ".join((SKILL / "SKILL.md").read_text().split())
    help_scout_text = " ".join(
        (SKILL / "references" / "help-scout.md").read_text().split()
    )
    for label, text in (("skill", skill_text), ("reference", help_scout_text)):
        for required in ("helpscout.support-context.typed-facts.v1", "helpscout.support-context.complete-target.v1", "helpscout.support-context.readable-masked-target.v3", "readable_masked_transcript", "typed_facts_fallback", "complete target conversation", "masked", "raw Help Scout prose never reaches the model", "target.attachmentEvidence", "excludedUnrecognizedThread", "exact receipt arithmetic", "technical blocker"):
            require(required in text, f"Help Scout contract missing from {label}: {required}")
    for required in ("helpscout.support-correlation.opaque-handle.v1", "opaque-correlation-envelope", "before accepting or passing a correlation handle", "mark correlation unavailable", "prior_case_handling", "Never create, save, or send a Help Scout draft"):
        require(required in help_scout_text or required in skill_text, f"Help Scout correlation contract missing: {required}")


def check_multisource_reporting_contract() -> None:
    skill_text = " ".join((SKILL / "SKILL.md").read_text().split())
    governed_text = " ".join(
        (SKILL / "references" / "governed-context.md").read_text().split()
    )
    brief_text = " ".join(
        (SKILL / "references" / "internal-brief.md").read_text().split()
    )
    public_kb_text = " ".join(
        (SKILL / "references" / "public-kb.md").read_text().split()
    )

    for required in (
        "no match within the bounded search",
        "not a comprehensive Slack absence",
        "no title match in the bounded query",
        "page bodies remained unchecked",
        "Code context remained unchecked",
        "generic S3 browsing is forbidden",
        "raw log lines never reach the model",
    ):
        require(
            required in governed_text,
            f"governed coverage contract missing: {required}",
        )

    for required in (
        "Investigation Plan",
        "Help Scout target:",
        "Help Scout history:",
        "Public KB:",
        "Slack:",
        "Notion:",
        "Code context:",
        "S3 Logs:",
        "checked, planned, skipped, unavailable, or stopped",
        "retrieval time",
        "Public KB freshness",
        "Reply Boundary",
    ):
        require(required in brief_text, f"brief coverage contract missing: {required}")

    require("public-KB freshness" not in skill_text or "Public KB" in skill_text, "top-level coverage contract drift")


def check_manifest_contract() -> dict:
    manifest = json.loads(HELP_SCOUT_MANIFEST.read_text(encoding="utf-8"))
    require(manifest.get("schemaVersion") == 1, "Help Scout manifest schema mismatch")
    require(
        manifest.get("requiredCapability")
        == "helpscout.support-context.typed-facts.v1",
        "Help Scout manifest capability mismatch",
    )
    require(
        manifest.get("requiredTargetCapabilities") == [
            "helpscout.support-context.complete-target.v1",
            "helpscout.support-context.readable-masked-target.v3",
        ],
        "Help Scout manifest target capabilities mismatch",
    )
    require(
        manifest.get("requiredTargetOutputModes") == [
            "readable_masked_transcript",
            "typed_facts_fallback",
        ],
        "Help Scout manifest target output modes mismatch",
    )
    require(
        manifest.get("requiredOutputMode") == "readable-masked-target-or-typed-fallback-and-typed-history-facts",
        "Help Scout manifest output mode mismatch",
    )
    require(
        manifest.get("requiredSafety")
        == {
            "rawProseModelVisible": False,
            "maskedTargetProseModelVisible": True,
            "internalNotesUsedAsEvidence": False,
            "attachmentsAccessed": True,
            "failClosed": True,
        },
        "Help Scout manifest safety contract is not closed",
    )
    return manifest


def check_investigation_manifest() -> dict:
    manifest = json.loads(INVESTIGATION_MANIFEST.read_text(encoding="utf-8"))
    require(manifest.get("schemaVersion") == 1, "investigation schema mismatch")
    require(manifest.get("entrypoint") == {"input": "positive_help_scout_ticket_number", "output": "internal_investigation_brief"}, "investigation entrypoint mismatch")
    require(manifest.get("replyDrafting") == "outside_skill", "reply drafting boundary mismatch")
    require(manifest.get("sources") == {"help_scout_target": {"requiredTool": "helpscout_get_support_context", "mandatory": True, "outputModes": ["readable_masked_transcript", "typed_facts_fallback"], "completeProviderPages": True}, "public_kb": {"claimKinds": ["documented_behavior"], "requiredTool": "public_kb.py"}, "helpscout_history": {"claimKinds": ["prior_case_handling"], "requiredTool": "helpscout_get_support_context"}, "slack": {"claimKinds": ["recent_team_context"], "requiredTool": "slack_search"}, "notion": {"claimKinds": ["intended_process"], "requiredTool": "notion_search"}, "code_context": {"claimKinds": ["implementation_behavior"], "requiredTool": "code_context"}, "s3_logs": {"claimKinds": ["runtime_event"], "requiredTool": "s3_log_lookup", "status": "conditional"}}, "investigation source/tool contract mismatch")
    require(manifest.get("claimSourceRoutes") == {"documented_behavior": ["public_kb"], "prior_case_handling": ["helpscout_history"], "recent_team_context": ["slack"], "intended_process": ["notion"], "implementation_behavior": ["code_context"], "runtime_event": ["s3_logs"]}, "investigation ordered routes mismatch")
    require(manifest.get("runtimePreflight") == {"scope": "whole_product_benchmark", "before": "ticket_selection_or_body_read", "onMismatch": "runtime_contract_mismatch", "contentFree": True}, "runtime preflight mismatch")
    require(manifest.get("replyDrafting") == "outside_skill", "reply drafting boundary mismatch")
    require(manifest.get("requiredBriefSections") == ["Question / Scope", "Investigation Plan", "What I Checked", "Coverage and Freshness", "Route", "Source Ledger", "Evidence Status", "Likely Pattern", "Similar Tickets", "Conflicts", "Unknowns", "Public KB Links", "Suggested Next Step", "Reply Boundary"], "investigation brief sections mismatch")
    require(manifest.get("stopErrors") == ["support_context_blocked", "runtime_contract_mismatch", "policy_denied", "scope_denied", "unsafe_query", "masking_failed", "audit_failed", "handle_integrity_failed", "credential_boundary_failed"], "investigation stop errors mismatch")
    require(manifest.get("safety") == {"governedToolsOnly": True, "rawPrivateContentModelVisible": False, "operationalIdentifiersModelVisible": False, "opaqueHandleTransitOnly": True, "opaqueHandlesFinalBriefVisible": False, "rawLogLinesModelVisible": False, "humanOnlyExactLogEvidenceSeparate": True, "privateSourceSubagents": False, "writesAllowed": False, "genericLogBrowsingAllowed": False}, "investigation safety contract mismatch")
    correlation = json.loads(HELP_SCOUT_CORRELATION_MANIFEST.read_text(encoding="utf-8"))
    require(correlation.get("schemaVersion") == 1, "correlation schema mismatch")
    require(correlation.get("requiredCapability") == "helpscout.support-correlation.opaque-handle.v1", "correlation capability mismatch")
    require(correlation.get("requiredOutputMode") == "opaque-correlation-envelope", "correlation output mode mismatch")
    require(correlation.get("envelope") == {"variants": {"available": ["state", "correlationHandle", "lookupKinds"], "not_found": ["state", "lookupKinds"], "unavailable": ["state", "lookupKinds"], "blocked": ["state", "lookupKinds"]}}, "correlation envelope mismatch")
    require(correlation.get("safety") == {"operationalIdentifiersModelVisible": False, "boundedTimeWindowPrivate": True, "rawTicketProseModelVisible": False, "opaqueHandleTransitOnly": True, "opaqueHandleLogged": False, "opaqueHandlePersisted": False}, "correlation safety mismatch")
    return manifest


def check_runtime_preflight_manifest() -> list[str]:
    manifest = json.loads(RUNTIME_PREFLIGHT_MANIFEST.read_text(encoding="utf-8"))
    require(
        manifest.get("schemaVersion") == 1,
        "runtime preflight schema mismatch",
    )
    require(
        manifest.get("ordering") == "unordered_exact",
        "runtime preflight ordering mismatch",
    )
    target_output_modes = manifest.get("targetOutputModes")
    require(
        target_output_modes == [
            "readable_masked_transcript",
            "typed_facts_fallback",
        ],
        "runtime preflight target output modes mismatch",
    )
    tools = manifest.get("gatewayTools")
    require(
        type(tools) is list
        and len(tools) == 10
        and all(type(tool) is str and tool for tool in tools)
        and len(tools) == len(set(tools))
        and {
            "slack_search",
            "notion_search",
            "notion_page",
            "code_context",
            "s3_log_lookup",
        }.issubset(tools),
        "runtime preflight gateway tools mismatch",
    )
    return tools


def check_help_scout_integration(root: Path, manifest: dict) -> None:
    executable = root.expanduser().resolve() / "bin" / "help-scout-mcp.js"
    require(executable.is_file(), f"Help Scout contract CLI missing: {executable}")
    completed = subprocess.run(
        [str(executable), "contract"],
        capture_output=True,
        text=True,
        check=False,
    )
    require(
        completed.returncode == 0,
        completed.stderr.strip() or "Help Scout contract command failed",
    )
    actual = json.loads(completed.stdout)
    require(
        actual.get("schemaVersion") == manifest["schemaVersion"],
        "Help Scout schema version mismatch",
    )
    require(
        actual.get("capability") == manifest["requiredCapability"],
        "Help Scout capability mismatch",
    )
    require(
        actual.get("targetCapabilities") == manifest["requiredTargetCapabilities"],
        "Help Scout target capabilities mismatch",
    )
    require(
        actual.get("targetOutputModes")
        == manifest["requiredTargetOutputModes"],
        "Help Scout target output modes mismatch",
    )
    require(
        actual.get("outputMode") == manifest["requiredOutputMode"],
        "Help Scout output mode mismatch",
    )
    correlation = json.loads(
        HELP_SCOUT_CORRELATION_MANIFEST.read_text(encoding="utf-8")
    )
    require(
        actual.get("correlationCapability")
        == correlation["requiredCapability"],
        "Help Scout correlation capability mismatch",
    )
    require(
        actual.get("correlationOutputMode")
        == correlation["requiredOutputMode"],
        "Help Scout correlation output mode mismatch",
    )
    require(
        actual.get("safety") == manifest["requiredSafety"],
        "Help Scout safety contract mismatch",
    )


def check_gateway_integration(root: Path, expected_tools: list[str]) -> None:
    executable = root.expanduser().resolve() / "bin" / "orderdesk-context-mcp.js"
    require(executable.is_file(), f"gateway contract CLI missing: {executable}")
    completed = subprocess.run(
        ["node", str(executable), "tools"],
        capture_output=True,
        text=True,
        check=False,
    )
    require(
        completed.returncode == 0,
        completed.stderr.strip() or "gateway tools command failed",
    )
    actual = json.loads(completed.stdout)
    require(
        actual == expected_tools,
        "gateway governed tool contract mismatch",
    )


def check_local_contracts() -> dict:
    health = run_public("health")
    require(health["pages"] > 0 and health["sections"] > 0, "KB index is empty")

    search = run_public("search", "Order Desk folders workflow")
    require(search.get("mode") in {"lexical", "semantic", "hybrid"}, "invalid search mode")
    require(isinstance(search.get("hits"), list), "search hits missing")

    ask = run_public("ask", "How do Order Desk folders work?")
    require(
        ask.get("confidence") in {"high", "medium", "low", "none"},
        "invalid ask confidence",
    )

    triage = run_public("triage", "Shopify order import folder workflow")
    require(
        "boundary" in triage and isinstance(triage.get("sources"), list),
        "triage contract drift",
    )
    require("freshness_note" in triage, "triage freshness note missing")
    for source in triage["sources"]:
        dates = source.get("source_dates")
        require(isinstance(dates, dict), "triage source dates missing")
        require(
            set(dates) == {"published_at", "modified_at", "fetched_at"},
            "triage source date contract drift",
        )

    return health


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument(
        "--local",
        action="store_true",
        help="check machine-local runtime symlinks and the generated public KB",
    )
    result.add_argument(
        "--help-scout-root",
        type=Path,
        help="invoke an installed Help Scout bridge's machine-readable contract",
    )
    result.add_argument(
        "--gateway-root",
        type=Path,
        help="invoke an installed gateway's machine-readable tool contract",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    check_links()
    check_text_contract()
    check_help_scout_contract()
    check_multisource_reporting_contract()
    investigation_manifest = check_investigation_manifest()
    gateway_tools = check_runtime_preflight_manifest()
    manifest = check_manifest_contract()
    payload = {"ok": True, "skill": str(SKILL), "portable": True, "investigationSchemaVersion": investigation_manifest["schemaVersion"]}
    if args.local:
        check_runtimes()
        payload["kb_health"] = check_local_contracts()
    if args.help_scout_root:
        check_help_scout_integration(args.help_scout_root, manifest)
        payload["help_scout_integration"] = True
    if args.gateway_root:
        check_gateway_integration(args.gateway_root, gateway_tools)
        payload["gateway_integration"] = True
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"contract smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
