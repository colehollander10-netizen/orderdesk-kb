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
        "slack_conversations",
        "notion_search",
        "bitbucket_file",
        "Support can answer",
        "Insufficient evidence — abstain",
        "Source Ledger",
        "Customer copy means text",
        "Logs are a planned governed source",
        "Never create, save, or send a Help Scout draft",
    ):
        require(required in text, f"required skill contract missing: {required}")
    require("Cole explicitly" not in text, "skill still hardcodes a personal operator")


def check_help_scout_contract() -> None:
    skill_text = " ".join((SKILL / "SKILL.md").read_text().split())
    help_scout_text = " ".join(
        (SKILL / "references" / "help-scout.md").read_text().split()
    )
    capability = "helpscout.support-context.typed-facts.v1"
    for label, text in (("skill", skill_text), ("reference", help_scout_text)):
        require(capability in text, f"Help Scout capability missing from {label}")
        require(
            "before calling `helpscout_get_support_context`" in text,
            f"Help Scout capability order missing from {label}",
        )
        require("technical blocker" in text, f"Help Scout blocker missing from {label}")

    fact_only_contract = (
        "fact-only",
        "raw Help Scout prose never reaches the model",
        "closed enums, counts, missing-evidence codes, and rule IDs",
        "zero or more safe facts",
        "not route-ready",
        "fixed missing-evidence codes",
        "zero-fact partial does not produce history search terms",
        "actual closed safe public term",
        "partial is not `masking_failed`",
        "internal notes and attachments are ignored",
        "operator-only local diagnostic",
        "never model context",
        "not a fallback",
        "metadata and handles remain bounded",
        "blocked stops the workflow safely",
    )
    for required in fact_only_contract:
        require(
            required.casefold() in help_scout_text.casefold(),
            f"required Help Scout contract missing: {required}",
        )

    for required in (
        "A named real Help Scout ticket is the intake artifact",
        "Proceed without a second approval prompt",
        "shortlist at most five unique metadata candidates",
        "metadata-only search to locate the target",
        "helpscout_get_support_context",
        "`targetTicketNumber`",
        "`historicalSelectionHandles`",
        "earlier Stage-0 metadata results",
        "process-local",
        "expire after five minutes",
        "one-time",
        "expired, unissued, or reused handles fail before source inspection",
        "raw Help Scout prose never reaches the model",
        "internal notes and attachments are ignored",
        "operator-only local diagnostic",
        "not a fallback",
        "full",
        "partial",
        "blocked",
        "zero-fact partial",
        "policy, scope, masking, audit, or source-read failure",
    ):
        require(
            required in skill_text,
            f"required named-ticket workflow missing: {required}",
        )

    require(
        "Do not put it—or any customer, order, store, email, domain" in help_scout_text,
        "Help Scout contract does not forbid raw identifiers in history queries",
    )
    for stale in (
        "includeTargetBodies",
        "targetConversationId",
        "historicalConversationIds",
        "historicalTicketNumbers",
        "threads --conversation-id <",
        "25 threads per ticket",
        "25-threads-per-ticket",
        "800 characters per body",
        "only model-visible MCP body path",
        "For CLI fallback",
        "CLI fallback is not an atomic",
    ):
        require(stale not in help_scout_text, f"stale Help Scout contract found: {stale}")
    for stale in (
        "includeTargetBodies",
        "historicalTicketNumbers",
        "800 characters per body",
        "only model-visible MCP body path",
        "For CLI fallback",
    ):
        require(stale not in skill_text, f"stale top-level Help Scout contract found: {stale}")

    require(
        "no automatic CLI body fallback" in help_scout_text,
        "Help Scout contract does not forbid automatic CLI body fallback",
    )
    require(
        "notes never contribute evidence, and attachments are not accessed"
        in help_scout_text,
        "Help Scout contract does not exclude notes and attachments from evidence",
    )


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
        "no match within the checked window",
        "not a workspace-wide search",
        "searches approved page titles only",
        "no title match in the bounded query",
        "page bodies remained unchecked",
        "Bitbucket remained unchecked",
        "Do not infer code behavior or code absence",
    ):
        require(
            required in governed_text,
            f"governed coverage contract missing: {required}",
        )

    for required in (
        "bounded conversation/time/message window",
        "title-only query and result cap",
        "safe failure code and remained unchecked",
        "Public KB freshness",
        "health checked at",
        "newest and oldest `fetched_at`",
        "Always retain this freshness line",
        "Never use bare `not found` for Slack or Notion",
    ):
        require(required in brief_text, f"brief coverage contract missing: {required}")

    for required in (
        "bounded Slack window",
        "title-only Notion search",
        "Bitbucket remained unchecked",
        "Never turn limited discovery into comprehensive absence",
        "public-KB freshness record",
    ):
        require(required in skill_text, f"top-level coverage contract missing: {required}")

    require(
        "every multi-source brief" in public_kb_text,
        "public KB multi-source freshness contract missing",
    )


def check_manifest_contract() -> dict:
    manifest = json.loads(HELP_SCOUT_MANIFEST.read_text(encoding="utf-8"))
    require(manifest.get("schemaVersion") == 1, "Help Scout manifest schema mismatch")
    require(
        manifest.get("requiredCapability")
        == "helpscout.support-context.typed-facts.v1",
        "Help Scout manifest capability mismatch",
    )
    require(
        manifest.get("requiredOutputMode") == "typed-facts",
        "Help Scout manifest output mode mismatch",
    )
    require(
        manifest.get("requiredSafety")
        == {
            "rawProseModelVisible": False,
            "internalNotesUsedAsEvidence": False,
            "attachmentsAccessed": False,
            "failClosed": True,
        },
        "Help Scout manifest safety contract is not closed",
    )
    return manifest


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
        actual.get("outputMode") == manifest["requiredOutputMode"],
        "Help Scout output mode mismatch",
    )
    require(
        actual.get("safety") == manifest["requiredSafety"],
        "Help Scout safety contract mismatch",
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
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    check_links()
    check_text_contract()
    check_help_scout_contract()
    check_multisource_reporting_contract()
    manifest = check_manifest_contract()
    payload = {"ok": True, "skill": str(SKILL), "portable": True}
    if args.local:
        check_runtimes()
        payload["kb_health"] = check_local_contracts()
    if args.help_scout_root:
        check_help_scout_integration(args.help_scout_root, manifest)
        payload["help_scout_integration"] = True
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"contract smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
