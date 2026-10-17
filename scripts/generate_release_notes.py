#!/usr/bin/env python3
"""Build a structured commit summary for a version tag release."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], check=check, capture_output=True, text=True)
    return result.stdout.strip()


def classify(message: str) -> str:
    subject = message.splitlines()[0] if message else ""
    if re.search(r"\bbreaking change\b", message, re.IGNORECASE) or re.match(
        r"^[a-z]+(?:\([^)]*\))?!:", subject, re.IGNORECASE
    ):
        return "breaking"
    match = re.match(r"^([a-z]+)(?:\([^)]*\))?:", subject, re.IGNORECASE)
    kind = match.group(1).lower() if match else ""
    if kind in {"feat", "feature", "add"}:
        return "features"
    if kind in {"fix", "bugfix", "security", "hardening", "perf", "refactor"}:
        return "fixes"
    return "other"


def render_section(title: str, commits: list[tuple[str, str]]) -> str:
    lines = [f"### {title}"]
    if not commits:
        lines.append("- No changes were classified in this category.")
    else:
        lines.extend(f"- `{sha[:7]}` {subject}" for sha, subject in commits)
    return "\n".join(lines)


def main() -> None:
    tag = os.environ["GITHUB_REF_NAME"]
    current = git("rev-parse", tag)
    previous_result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", "--match", "v*", f"{current}^"],
        check=False,
        capture_output=True,
        text=True,
    )
    previous = previous_result.stdout.strip() if previous_result.returncode == 0 else None

    if previous:
        log_range = f"{previous}..{tag}"
        commits_output = git("log", "--no-merges", "-z", "--format=%H%x1f%s%x1f%b", log_range)
    else:
        commits_output = git("log", "--no-merges", "-z", "--format=%H%x1f%s%x1f%b", tag)

    groups: dict[str, list[tuple[str, str]]] = {
        "features": [],
        "breaking": [],
        "fixes": [],
        "other": [],
    }
    for record in commits_output.split("\x00"):
        sha, separator, remainder = record.partition("\x1f")
        if not separator:
            continue
        subject, _, body_text = remainder.partition("\x1f")
        if sha and subject:
            groups[classify(f"{subject}\n{body_text}")].append((sha, subject))

    previous_label = previous or "the beginning of history"
    body = [
        f"## AgentDrift MCP ({tag})",
        "",
        f"Changes summarized from `{previous_label}` through `{tag}`.",
        "",
        render_section("What's New", groups["features"]),
        "",
        render_section("Breaking Changes & Upgrades", groups["breaking"]),
        "",
        render_section("Bug Fixes & Hardening", groups["fixes"]),
        "",
        render_section("Additional Changes", groups["other"]),
        "",
        "### Distribution",
        "- Install from PyPI: `pip install --upgrade agentdrift-mcp`",
        "- Run the MCP server: `uvx --from agentdrift-mcp agentdrift-mcp`",
        "",
        "### Full Changelog & Contributors",
        "GitHub-generated release notes follow, including the full comparison and contributor acknowledgements.",
    ]
    Path("release-notes.md").write_text("\n".join(body) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
