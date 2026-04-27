#!/usr/bin/env python3
"""
Rationale marker hook for Claude Code — Elixir.

PostToolUse hook for Elixir files (.ex, .exs):
- Write: new file with defmodule → require at least one §§ marker
- Edit: new code adds try/rescue, if/else, or cross-context call →
  require a §§ marker justifying the decision

The marker documents which skill decision drove the code choice.
Without it, there's no traceable record of conscious decision-making.

§§ replaces an earlier six-underscore (______) sentinel that could
collide with section-divider comments in real code. See
anti-slop-scan.py for the full rationale.

[use-skills] gated: this hook is silent in casual sessions. It only
fires when the latest user prompt (or the active plan file) contains
the `[use-skills]` marker — same gating shape as skill-enforcement.py.
This keeps the marker requirement aligned with the user's "strict mode"
boundary instead of nagging on prototype-level edits.

Companion file: rationale-marker-rust.py for Rust patterns.

Fails open: any exception exits 0 so the session is never bricked.
"""

import json
import os
import re
import sys

USE_MARKER = "[use-skills]"
NO_MARKER = "[no-skills]"

# Write = new file creation (module marker check).
# Edit = modifications (boundary crossing check only).
WRITE_TOOLS = {"Write"}
EDIT_TOOLS = {"Edit"}

# Module declarations — Elixir only for now.
# Extend to other languages when their phased skills adopt the marker convention.
MODULE_PATTERNS = {
    ".ex":  re.compile(r"^\s*defmodule\s+", re.MULTILINE),
    ".exs": re.compile(r"^\s*defmodule\s+", re.MULTILINE),
}

# The rationale marker sentinel — doubled section sign.
# Matches `§§` anywhere; the surrounding hook expects it inside a
# comment-opener position when used as a marker.
MARKER = re.compile(r"§§")

# Paths exempt from the check
EXEMPT_PATTERNS = [
    re.compile(r"_test\.(ex|exs|rs|py|go)$"),
    re.compile(r"\.test\.(ts|tsx|js)$"),
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)test/"),
    re.compile(r"/config/"),
    re.compile(r"mix\.exs$"),
    re.compile(r"\.claude/"),
]


# Elixir cross-context call patterns that suggest a boundary crossing.
# These fire on Edit too — boundary crossings happen when adding calls.
BOUNDARY_CROSSING_PATTERNS = [
    # Reaching into another context's internals: Archdo.Compiled.Diagram.foo()
    # (3+ segments with a non-boundary internal module)
    re.compile(
        r"(?:__aliases__|alias).*?"
        r"(?:Compiled\.Diagram[^I]|Compiled\.Graph\.|Mcp\.Tools\.\w+\.\w+|"
        r"Rules\.\w+\.\w+\.\w+)"
    ),
]

# Simpler: detect cross-context qualified calls added in new_string
CROSS_CONTEXT_CALL = re.compile(
    r"\b[A-Z]\w+\.[A-Z]\w+\.[A-Z]\w+\.\w+\("  # A.B.C.func( — 3+ level deep call
)


def is_use_skills_active(transcript_path):
    """
    True iff the latest typed user message (in `transcript_path`)
    contains `[use-skills]` and not `[no-skills]`. Mirrors the
    gating logic in skill-enforcement.py so the two hooks fire on
    the same trigger boundary.

    Conservative: returns False on any failure to read the
    transcript (so the hook stays silent rather than nagging on
    its own implementation bug).
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return False
    try:
        latest_text = ""
        with open(transcript_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "user":
                    continue
                msg = rec.get("message") or {}
                if msg.get("role") != "user":
                    continue
                content = msg.get("content")
                text = ""
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    parts = []
                    for block in content:
                        if (
                            isinstance(block, dict)
                            and block.get("type") == "text"
                        ):
                            parts.append(block.get("text", ""))
                    text = "\n".join(parts)
                if text.strip():
                    latest_text = text  # keep updating; final value is the latest
    except Exception:
        return False
    if NO_MARKER in latest_text:
        return False
    return USE_MARKER in latest_text


def handle(data):
    if not is_use_skills_active(data.get("transcript_path") or ""):
        return None

    tool_name = data.get("tool_name") or ""
    tool_input = data.get("tool_input") or {}

    if tool_name in WRITE_TOOLS:
        return handle_write(tool_input)
    elif tool_name in EDIT_TOOLS:
        return handle_edit(tool_input)
    return None


def handle_write(tool_input):
    """New file: require at least one marker per module declaration."""
    path = tool_input.get("file_path") or ""
    content = tool_input.get("content") or ""

    if not path or not content:
        return None

    for pat in EXEMPT_PATTERNS:
        if pat.search(path):
            return None

    ext = ""
    if "." in path:
        ext = "." + path.rsplit(".", 1)[-1].lower()

    mod_pat = MODULE_PATTERNS.get(ext)
    if mod_pat is None:
        return None

    if not mod_pat.search(content):
        return None

    if MARKER.search(content):
        return None

    mod_count = len(mod_pat.findall(content))
    plural = "s" if mod_count > 1 else ""

    return (
        f"New file with {mod_count} module{plural} but no rationale marker. "
        "Add at least one `# §§ <skill>: §<sec> — <why>` comment "
        "documenting the primary skill decision that shaped this module. "
        "Examples:\n"
        "  # §§ elixir-implementing: §10.1 — context boundary module\n"
        "  # §§ elixir-planning: §8.6 — DynamicSupervisor for per-device workers\n"
        "  # §§ elixir-implementing: §2.4 — rescue at system boundary\n\n"
        "The marker is dev-time scaffolding swept before ship. It traces "
        "which skill fragment drove the decision — making reviews cheaper "
        "and catching 'wrote code without consulting the skill' drift."
    )


# Patterns in new_string that require a rationale marker
MARKER_REQUIRED_PATTERNS = [
    {
        "pattern": CROSS_CONTEXT_CALL,
        "message": (
            "Cross-context or deep internal call added without a rationale marker. "
            "A qualified call like `Archdo.Compiled.Diagram.foo()` crosses a context "
            "boundary — especially if it bypasses the boundary module. Add a marker:\n"
            "  # §§ elixir-planning: §6.4 — calling internal module, no facade\n"
            "  # §§ elixir-reviewing: §7.1 — intentional bypass\n\n"
            "If the call goes through the context's public API, no marker needed."
        ),
    },
    {
        "pattern": re.compile(r"\bif\b[^,\n]+\bdo\b\s*\n.*?\belse\b", re.DOTALL),
        "message": (
            "`if/else` with value-returning branches added without a rationale marker. "
            "Elixir skill §2.1: when both branches return values, prefer "
            "`case bool do true -> ...; false -> ... end` (strict match) or "
            "multi-clause function dispatch. `if/else` tests truthiness, not "
            "literal boolean — `nil` falls into else. Add a marker if this is intentional:\n"
            "  # §§ elixir-implementing: §2.1 — if/else OK here, truthy semantics intended\n\n"
            "If the condition is a shape/type check, use multi-clause function instead."
        ),
    },
    {
        "pattern": re.compile(r"\btry\b\s+do\b", re.DOTALL),
        "message": (
            "`try` block added without a rationale marker. Every try/rescue/catch "
            "is a conscious decision — document WHY this call can't use ok/error "
            "tuples or let-it-crash. Add a marker:\n"
            "  # §§ elixir-implementing: §2.4 — rescue at system boundary, external lib raises\n"
            "  # §§ elixir-implementing: §2.4 — catch :exit, calling process we don't own\n"
            "  # §§ elixir-reviewing: §7.5 — wrapping third-party lib that raises on invalid input\n\n"
            "If this is a boundary adapter wrapping an external dependency, the marker "
            "documents that. If it's not at a boundary, the marker forces you to reconsider."
        ),
    },
]


def handle_edit(tool_input):
    """Edit: if new_string introduces a boundary crossing or try block, require a marker."""
    path = tool_input.get("file_path") or ""
    new_string = tool_input.get("new_string") or ""

    if not path or not new_string:
        return None

    for pat in EXEMPT_PATTERNS:
        if pat.search(path):
            return None

    # Only check Elixir files for now
    if not path.endswith((".ex", ".exs")):
        return None

    # Already has a marker in the new code? All good.
    if MARKER.search(new_string):
        return None

    # Check each pattern that requires a marker
    for check in MARKER_REQUIRED_PATTERNS:
        if check["pattern"].search(new_string):
            return check["message"]

    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    try:
        msg = handle(data)
    except Exception:
        return 0
    if msg:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": msg,
            },
        }
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
