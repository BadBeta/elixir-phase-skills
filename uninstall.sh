#!/usr/bin/env bash
# elixir-phase-skills uninstaller. Leaves BB-skill-core intact.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-${HOME}/.claude}"
HOOKS_DIR="${CLAUDE_HOME}/hooks"
SKILLS_DIR="${CLAUDE_HOME}/skills"
SETTINGS="${CLAUDE_HOME}/settings.json"
FRAGMENT="${SCRIPT_DIR}/settings-fragment.json"
MERGE="${CLAUDE_HOME}/install/merge_settings.py"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

echo "elixir-phase-skills uninstall"
rm -f "${HOOKS_DIR}/bb-rationale-marker-elixir.py"
rm -f "${HOOKS_DIR}/bb-anti-slop-patterns.d/elixir.json"
rm -f "${HOOKS_DIR}/bb-skill-triggers.d/elixir.json"

for sk in elixir-planning elixir-implementing elixir-reviewing phoenix phoenix-liveview; do
    rm -rf "${SKILLS_DIR}/${sk}"
done

if [ -f "${SETTINGS}" ] && [ -f "${MERGE}" ]; then
    cp -p "${SETTINGS}" "${SETTINGS}.bak.$(date +%Y%m%d-%H%M%S)"
    tmp="$(mktemp)"
    python3 "${MERGE}" unmerge "${SETTINGS}" "${FRAGMENT}" > "${tmp}"
    mv "${tmp}" "${SETTINGS}"
fi

rm -f "${CLAUDE_HOME}/elixir-phase-skills.VERSION"
echo "done."
