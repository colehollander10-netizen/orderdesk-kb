#!/usr/bin/env python3
"""Offline/current-local contract checks for the canonical Order Desk skill."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ROOT = SKILL.parent
PUBLIC = SKILL / "scripts" / "public_kb.py"


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

    help_scout = ROOT.parent / "help-scout-mcp" / "bin" / "help-scout-mcp.js"
    completed = subprocess.run(
        [str(help_scout), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    require(completed.returncode == 0, "Help Scout CLI help failed")
    require("--query-stdin" in completed.stdout, "Help Scout stdin query support missing")
    require("--include-body" in completed.stdout, "Help Scout body opt-in missing")
    require("--ticket-number" in completed.stdout, "number-first CLI lookup missing")
    cli_source = help_scout.read_text()
    for required in (
        "requirePrivateBodyReadOptIn(parseBoolArg(\"--include-body\"))",
        "getThreadsByTicketNumber",
    ):
        require(required in cli_source, f"Help Scout operator diagnostic contract missing: {required}")
    mcp_source = (help_scout.parents[1] / "lib" / "mcp.js").read_text()
    for required in (
        "helpscout_get_support_context",
        "targetTicketNumber",
        "historySelectionHandle: historySelections.issue(conversation.number)",
        "historicalSelectionHandles",
        "SUPPORT_HISTORY_SELECTION_TTL_MS = 5 * 60 * 1000",
        "historicalTicketNumbers is not accepted; use Stage 0 history selection handles",
        "selectionReservation = historySelections?.reserve?.(",
        "selectionReservation?.commit()",
        "selectionReservation?.release?.()",
        "const readResults = await Promise.allSettled([",
        "MCP support context is fact-only",
        'bodyOutput: "typed facts only"',
        'internalNoteBodies: "not used as evidence"',
        'attachments: "not accessed"',
        "Customer/staff message bodies may be inspected locally to derive typed facts but are never returned or model-visible",
        "support_context_blocked",
        "supportContextAuditMeta",
        "sanitizeForModel(result)",
        "genericFailedToolResult()",
    ):
        require(required in mcp_source, f"Help Scout fact-only MCP contract missing: {required}")
    reserve_match = re.search(
        r"function reserve\(handles\) \{(?P<body>.*?)\n\s{2}\}\n\n\s{2}return Object\.freeze",
        mcp_source,
        flags=re.DOTALL,
    )
    require(reserve_match is not None, "Help Scout selection reservation missing")
    require(
        "entries.delete(handle)" in reserve_match.group("body")
        and "delete selection.reservation" in reserve_match.group("body"),
        "Help Scout history handles do not support commit and release",
    )
    reserve_position = mcp_source.find("selectionReservation = historySelections?.reserve?.(")
    read_position = mcp_source.find("const readResults = await Promise.allSettled([", reserve_position)
    commit_position = mcp_source.find("selectionReservation?.commit()", read_position)
    release_position = mcp_source.find("selectionReservation?.release?.()", commit_position)
    require(
        0 <= reserve_position < read_position < commit_position < release_position,
        "Help Scout history handles do not reserve before reads, commit after success, and release on failure",
    )
    fact_schema_source = (
        help_scout.parents[1] / "lib" / "support-fact-schema.js"
    ).read_text()
    for required in (
        'contextState: routeReady ? "full" : "partial"',
        'contextState: "blocked"',
        "routeReady: false",
        "safeFactsExtracted",
        "missingEvidence",
        "ruleIds",
        "candidate.safeFactsExtracted >= 3",
        '"no_safe_body_facts"',
    ):
        require(required in fact_schema_source, f"Help Scout fact schema missing: {required}")
    extractor_source = (
        help_scout.parents[1] / "lib" / "support-fact-extractor.js"
    ).read_text()
    for required in (
        'thread?.type === "note"',
        "stripPrivateBodyStructure(thread?.body",
        'missingEvidence.push("no_safe_body_facts")',
    ):
        require(required in extractor_source, f"Help Scout fact extractor missing: {required}")
    audit_source = (help_scout.parents[1] / "lib" / "audit.js").read_text()
    for required in (
        'error.code = "audit_failed"',
        'error: "support_context_blocked"',
        "isSafeSupportFactRecord(fact)",
        'full: facts.filter((fact) => fact.contextState === "full").length',
        'partial: facts.filter((fact) => fact.contextState === "partial").length',
        'blocked: facts.filter((fact) => fact.contextState === "blocked").length',
    ):
        require(required in audit_source, f"Help Scout policy/audit gate missing: {required}")
    client_source = (help_scout.parents[1] / "lib" / "client.js").read_text()
    for required in (
        "DEFAULT_HELP_SCOUT_REQUEST_TIMEOUT_MS = 10_000",
        "controller.abort()",
        "this.clearTimeout(timer)",
        'upstreamSignal?.removeEventListener("abort", cancel)',
        '"helpscout_request_timeout"',
    ):
        require(required in client_source, f"Help Scout timeout contract missing: {required}")
    cli_input_source = (help_scout.parents[1] / "lib" / "cli-input.js").read_text()
    for required in (
        "SEARCH_QUERY_MAX_LENGTH = 256",
        "SEARCH_PAGE_MAX = 20",
        "SEARCH_RESULT_LIMIT = 5",
    ):
        require(required in cli_input_source, f"Help Scout search contract missing: {required}")
    return health


def main() -> int:
    check_links()
    check_runtimes()
    check_text_contract()
    check_help_scout_contract()
    check_multisource_reporting_contract()
    health = check_local_contracts()
    print(json.dumps({"ok": True, "skill": str(SKILL), "kb_health": health}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"contract smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
