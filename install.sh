#!/usr/bin/env bash
# elixir-phase-skills installer. Depends on BB-skill-core.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-${HOME}/.claude}"
HOOKS_DIR="${CLAUDE_HOME}/hooks"
SKILLS_DIR="${CLAUDE_HOME}/skills"
SETTINGS="${CLAUDE_HOME}/settings.json"
FRAGMENT="${SCRIPT_DIR}/settings-fragment.json"
BB_CORE_REPO="${BB_CORE_REPO:-https://github.com/BadBeta/BB-skill-core.git}"

CORE_SENTINEL="${HOOKS_DIR}/bb-anti-slop-scan.py"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }

echo "elixir-phase-skills install"
echo "  source:    ${SCRIPT_DIR}"
echo "  install:   ${CLAUDE_HOME}"
echo

if [ ! -f "${CORE_SENTINEL}" ]; then
    echo "BB-skill-core is not installed (missing ${CORE_SENTINEL})."
    if [ "${BB_NONINTERACTIVE:-}" = "1" ]; then
        echo "Install BB-skill-core first." >&2
        exit 1
    fi
    printf "Clone and install BB-skill-core from %s ? [Y/n] " "${BB_CORE_REPO}"
    read -r reply
    case "${reply}" in
        ""|y|Y|yes|Yes) ;;
        *) echo "Aborting. Install BB-skill-core first." ; exit 1 ;;
    esac
    command -v git >/dev/null 2>&1 || { echo "git is required to clone core" >&2; exit 1; }
    tmp_core="$(mktemp -d)"
    trap 'rm -rf "${tmp_core}"' EXIT
    git clone --depth 1 "${BB_CORE_REPO}" "${tmp_core}/BB-skill-core"
    bash "${tmp_core}/BB-skill-core/install.sh"
    if [ ! -f "${CORE_SENTINEL}" ]; then
        echo "Core install did not produce ${CORE_SENTINEL}; aborting." >&2
        exit 1
    fi
fi

if [ -f "${SCRIPT_DIR}/REQUIRES_CORE" ] && [ -f "${CLAUDE_HOME}/BB-skill-core.VERSION" ]; then
    required="$(tr -d '[:space:]' < "${SCRIPT_DIR}/REQUIRES_CORE")"
    have="$(tr -d '[:space:]' < "${CLAUDE_HOME}/BB-skill-core.VERSION")"
    if [ "${have}" \< "${required}" ]; then
        echo "BB-skill-core ${have} < required ${required}; upgrade core first." >&2
        exit 1
    fi
fi

mkdir -p "${HOOKS_DIR}/bb-anti-slop-patterns.d"
mkdir -p "${HOOKS_DIR}/bb-skill-triggers.d"
mkdir -p "${SKILLS_DIR}"

echo "[1/4] copying elixir-pack hooks…"
cp -p "${SCRIPT_DIR}/hooks/bb-rationale-marker-elixir.py" "${HOOKS_DIR}/"
chmod +x "${HOOKS_DIR}/bb-rationale-marker-elixir.py" 2>/dev/null || true

echo "[2/4] copying drop-in fragments…"
cp -p "${SCRIPT_DIR}/hooks/bb-anti-slop-patterns.d/elixir.json" "${HOOKS_DIR}/bb-anti-slop-patterns.d/"
cp -p "${SCRIPT_DIR}/hooks/bb-skill-triggers.d/elixir.json" "${HOOKS_DIR}/bb-skill-triggers.d/"

echo "[3/4] copying elixir skills…"
for sk in elixir-planning elixir-implementing elixir-reviewing; do
    src="${SCRIPT_DIR}/${sk}"
    if [ -d "${src}" ]; then
        rm -rf "${SKILLS_DIR}/${sk}"
        cp -R "${src}" "${SKILLS_DIR}/${sk}"
    fi
done

echo "[4/4] merging settings…"
MERGE="${CLAUDE_HOME}/install/merge_settings.py"
if [ ! -f "${MERGE}" ]; then
    echo "Cannot find ${MERGE} — re-run BB-skill-core/install.sh." >&2
    exit 1
fi
cp -p "${SETTINGS}" "${SETTINGS}.bak.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
tmp="$(mktemp)"
python3 "${MERGE}" merge "${SETTINGS}" "${FRAGMENT}" > "${tmp}"
mv "${tmp}" "${SETTINGS}"

[ -f "${SCRIPT_DIR}/VERSION" ] && cp -p "${SCRIPT_DIR}/VERSION" "${CLAUDE_HOME}/elixir-phase-skills.VERSION"

echo
echo "elixir-phase-skills installed."
