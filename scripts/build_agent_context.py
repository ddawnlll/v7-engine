#!/usr/bin/env python3
"""
build_agent_context.py — Task-Based Agent Context Compiler

Reads the .agent/ and docs/audits/ context files and produces a
MINIMAL context document for a given task. Filters findings, decisions,
and questions to only those relevant to the task scope.

Usage:
    python scripts/build_agent_context.py --task TASK_ID [--output PATH]

Examples:
    python scripts/build_agent_context.py --task AUDIT-DATA-PIPELINE-001
    python scripts/build_agent_context.py --task AUDIT-DATA-PIPELINE-001 --output /tmp/agent-context.md

Design:
    - Reads FINDINGS_LEDGER.md, DECISIONS.md, OPEN_QUESTIONS.md
    - Selects entries whose scope matches the task's scope keywords
    - Builds a structured context document with only relevant entries
    - Falls back to ALL entries if no scope match found (safe default)

Exit codes:
    0: success
    1: task not found in CURRENT_TASK.md
    2: required context file missing
"""

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# ── File paths ──────────────────────────────────────────────────────────────

FILES = {
    "project_context": REPO_ROOT / "docs" / "project_context.md",
    "decisions": REPO_ROOT / "docs" / "decisions" / "DECISIONS.md",
    "findings": REPO_ROOT / "docs" / "audits" / "FINDINGS_LEDGER.md",
    "open_questions": REPO_ROOT / "docs" / "audits" / "OPEN_QUESTIONS.md",
    "current_task": REPO_ROOT / ".agent" / "CURRENT_TASK.md",
    "handoff": REPO_ROOT / ".agent" / "HANDOFF.md",
    "evidence_reqs": REPO_ROOT / ".agent" / "EVIDENCE_REQUIREMENTS.md",
}


# ── Parsers ─────────────────────────────────────────────────────────────────


def read_findings(path: Path):
    """Parse FINDINGS_LEDGER.md into a list of finding dicts."""
    text = path.read_text()
    findings = []
    blocks = re.split(r"\n## F-", text)[1:]  # skip header
    for block in blocks:
        block = "F-" + block.strip()
        m = re.search(r"^## (F-\d+) — (.+)$", block, re.MULTILINE)
        if not m:
            continue
        fid = m.group(1)
        title = m.group(2)
        scope_m = re.search(r"\*\*Scope:\*\*\s*(.+)$", block, re.MULTILINE)
        scope = scope_m.group(1).strip() if scope_m else ""
        severity_m = re.search(r"\*\*Severity:\*\*\s*(.+)$", block, re.MULTILINE)
        severity = severity_m.group(1).strip() if severity_m else ""
        findings.append({"id": fid, "title": title, "scope": scope, "severity": severity, "text": block})
    return findings


def read_decisions(path: Path):
    """Parse DECISIONS.md into a list of decision dicts."""
    text = path.read_text()
    decisions = []
    blocks = re.split(r"\n## DEC-", text)[1:]
    for block in blocks:
        block = "DEC-" + block.strip()
        m = re.search(r"^## (DEC-\d+) — (.+)$", block, re.MULTILINE)
        if not m:
            continue
        did = m.group(1)
        title = m.group(2)
        status_m = re.search(r"\*\*Status:\*\*\s*`(.+?)`", block)
        status = status_m.group(1) if status_m else ""
        scope_m = re.search(r"\*\*Scope:\*\*\s*(.+)$", block, re.MULTILINE)
        scope = scope_m.group(1).strip() if scope_m else ""
        decisions.append({"id": did, "title": title, "status": status, "scope": scope, "text": block})
    return decisions


def read_questions(path: Path):
    """Parse OPEN_QUESTIONS.md into a list of question dicts."""
    text = path.read_text()
    questions = []
    blocks = re.split(r"\n## Q-", text)[1:]
    for block in blocks:
        block = "Q-" + block.strip()
        m = re.search(r"^## (Q-\d+) — (.+)$", block, re.MULTILINE)
        if not m:
            continue
        qid = m.group(1)
        title = m.group(2)
        scope_m = re.search(r"\*\*Scope:\*\*\s*(.+)$", block, re.MULTILINE)
        scope = scope_m.group(1).strip() if scope_m else ""
        questions.append({"id": qid, "title": title, "scope": scope, "text": block})
    return questions


def read_current_task(path: Path):
    """Parse CURRENT_TASK.md for task ID and scope."""
    text = path.read_text()
    m = re.search(r"## Task ID:\s*(\S+)", text)
    task_id = m.group(1) if m else "UNKNOWN"
    scope_lines = []
    in_scope = False
    for line in text.split("\n"):
        if line.startswith("### Scope"):
            in_scope = True
            continue
        if in_scope and line.startswith("###"):
            break
        if in_scope and line.strip():
            scope_lines.append(line.strip())
    scope_text = " ".join(scope_lines)
    return {"task_id": task_id, "scope": scope_text}


# ── Scope matching ──────────────────────────────────────────────────────────


def scope_keywords(scope_text: str) -> set:
    """Extract meaningful keywords from a scope text."""
    stopwords = {"the", "a", "an", "in", "of", "to", "for", "and", "or", "is",
                 "are", "was", "were", "be", "been", "being", "have", "has",
                 "had", "do", "does", "did", "will", "would", "can", "could",
                 "shall", "should", "may", "might", "this", "that", "these",
                 "those", "it", "its", "with", "on", "at", "by", "from",
                 "as", "but", "not", "no", "all", "each", "every", "both",
                 "neither", "nor", "so", "if", "then", "than", "too", "very",
                 "just", "about", "up", "down", "out", "off", "over", "under",
                 "again", "further", "once", "here", "there", "when", "where",
                 "why", "how", "which", "who", "whom", "what"}
    words = re.findall(r'[a-zA-Z][a-zA-Z0-9_/.-]+', scope_text.lower())
    return {w.lower() for w in words if w.lower() not in stopwords and len(w) > 2}


def scope_relevance(scope_text: str, task_keywords: set) -> int:
    """Count how many task keywords appear in the scope text."""
    scope_lower = scope_text.lower()
    return sum(1 for kw in task_keywords if kw in scope_lower)


def filter_entries(entries, task_keywords: set, min_relevance: int = 1):
    """Filter entries by scope relevance. Returns (relevant, others)."""
    scored = [(e, scope_relevance(e.get("scope", ""), task_keywords)) for e in entries]
    relevant = [e for e, s in scored if s >= min_relevance]
    others = [e for e, s in scored if s < min_relevance]
    return relevant, others


# ── Context building ────────────────────────────────────────────────────────


def build_context(task_id: str) -> str:
    """Build a structured context document for the given task."""

    # Read all files
    for key, path in FILES.items():
        if not path.exists():
            print(f"ERROR: Required file not found: {path}", file=sys.stderr)
            sys.exit(2)

    # Read current task for scope
    task = read_current_task(FILES["current_task"])
    task_keywords = scope_keywords(task["scope"] + " " + task_id)

    # Parse all entries
    findings = read_findings(FILES["findings"])
    decisions = read_decisions(FILES["decisions"])
    questions = read_questions(FILES["open_questions"])

    # Filter by relevance
    relevant_findings, extra_findings = filter_entries(findings, task_keywords)
    relevant_decisions, extra_decisions = filter_entries(decisions, task_keywords)
    relevant_questions, extra_questions = filter_entries(questions, task_keywords)

    # If nothing matched, include everything (safe default)
    if not relevant_findings and not relevant_decisions and not relevant_questions:
        relevant_findings = findings
        relevant_decisions = decisions
        relevant_questions = questions
        selection_note = "⚠️  No task-specific scope match — showing ALL entries."
    else:
        selection_note = (
            f"📋 Showing {len(relevant_findings)} findings, "
            f"{len(relevant_decisions)} decisions, "
            f"{len(relevant_questions)} questions relevant to scope."
        )

    # Build context document
    lines = []
    lines.append(f"# Agent Context — Task: {task_id}")
    lines.append("")
    lines.append(f"*Generated by `build_agent_context.py`*")
    lines.append("")
    lines.append(selection_note)
    lines.append("")
    lines.append("---")
    lines.append("")

    # Project overview (concise)
    proj_text = FILES["project_context"].read_text()
    summary_match = re.search(r"## What Is This\?(.+?)(?=\n##|\Z)", proj_text, re.DOTALL)
    if summary_match:
        lines.append("## Project")
        lines.append(summary_match.group(1).strip())
        lines.append("")

    # Current task
    lines.append("## Current Task")
    lines.append(f"**ID:** {task['task_id']}")
    lines.append(f"**Scope:** {task['scope']}")
    lines.append("")
    lines.append(f"Full: `.agent/CURRENT_TASK.md`")
    lines.append("")

    # Handoff summary
    handoff_text = FILES["handoff"].read_text()
    completed_match = re.search(r"## Work Completed\n\n(.+?)(?=\n##|\Z)", handoff_text, re.DOTALL)
    next_match = re.search(r"## Recommended Next Action\n\n(.+?)(?=\n##|\Z)", handoff_text, re.DOTALL)
    if completed_match:
        lines.append("## Previous Handoff")
        lines.append(completed_match.group(1).strip()[:2000])
        lines.append("")
    if next_match:
        lines.append("**Recommended next:**")
        lines.append(next_match.group(1).strip()[:1000])
        lines.append("")

    # Relevant decisions
    if relevant_decisions:
        lines.append("## Relevant Locked Decisions")
        lines.append("")
        for d in relevant_decisions:
            lines.append(f"### {d['id']} — {d['title']}")
            lines.append(f"**Status:** `{d['status']}`")
            lines.append(f"**Scope:** {d['scope']}")
            # Extract rationale and evidence
            rationale_m = re.search(r"\*\*Rationale:\*\*\n(.+?)(?=\n\*\*|\Z)", d["text"], re.DOTALL)
            if rationale_m:
                lines.append(f"**Rationale:** {rationale_m.group(1).strip()[:500]}")
            evidence_m = re.search(r"\*\*Evidence:\*\*\n(.+?)(?=\n\*\*|\Z)", d["text"], re.DOTALL)
            if evidence_m:
                lines.append(f"**Evidence:** {evidence_m.group(1).strip()[:300]}")
            lines.append("")

    # Relevant findings
    if relevant_findings:
        lines.append("## Relevant Findings (Confirmed)")
        lines.append("")
        for f in relevant_findings:
            lines.append(f"### {f['id']} — {f['title']}")
            lines.append(f"**Severity:** {f['severity']}")
            lines.append(f"**Scope:** {f['scope']}")
            # Extract evidence
            evidence_m = re.search(r"\*\*Evidence:\*\*\n(.+?)(?=\n\*\*|\Z)", f["text"], re.DOTALL)
            if evidence_m:
                lines.append(f"**Evidence:** {evidence_m.group(1).strip()[:500]}")
            impact_m = re.search(r"\*\*Impact:\*\*\n(.+?)(?=\n\*\*|\Z)", f["text"], re.DOTALL)
            if impact_m:
                lines.append(f"**Impact:** {impact_m.group(1).strip()[:300]}")
            lines.append("")

    # Relevant open questions
    if relevant_questions:
        lines.append("## Relevant Open Questions")
        lines.append("")
        for q in relevant_questions:
            lines.append(f"### {q['id']} — {q['title']}")
            lines.append(f"**Scope:** {q['scope']}")
            lines.append("")

    # Evidence requirements summary
    lines.append("## Evidence Requirements (Summary)")
    lines.append("")
    lines.append("See `.agent/EVIDENCE_REQUIREMENTS.md` for full checklist.")
    lines.append("Key requirements:")
    lines.append("- Real data verification only — synthetic results are not accepted")
    lines.append("- Confidence scores (0.00–1.00) on every finding")
    lines.append("- Before/after comparison for performance changes")
    lines.append("- Handoff must be rewritten with completed work")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Context compiled for task `{task_id}` at build time.*")

    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Build a minimal task-specific agent context document.",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Task ID (e.g., AUDIT-DATA-PIPELINE-001). Used for scope filtering.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: stdout).",
    )
    args = parser.parse_args()

    context = build_context(args.task)

    if args.output:
        Path(args.output).write_text(context)
        print(f"Context written to {args.output}")
    else:
        print(context)


if __name__ == "__main__":
    main()
