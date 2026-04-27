# elixir-phase-skills

Three-phase Elixir skill family + Elixir-specific hooks. Layers on top of [BB-skill-core](https://github.com/BadBeta/BB-skill-core).

| Skill | Purpose |
|---|---|
| `elixir-planning` | Architecture, contexts, supervision tree, OTP design, deployment strategy |
| `elixir-implementing` | Idiomatic patterns, decision tables, BAD/GOOD pairs, TDD with ExUnit |
| `elixir-reviewing` | PR review, debugging (recon, observer, sys.trace), profiling (Benchee, fprof) |

Plus:

- `bb-rationale-marker-elixir.py` — flags `# §§` rationale markers left in committed code
- `bb-anti-slop-patterns.d/elixir.json` — Elixir anti-slop patterns (try/rescue for ok/error, Process.sleep in tests, String.to_atom on user input, etc.)
- `bb-skill-triggers.d/elixir.json` — keyword → skill mappings for Elixir/Phoenix/OTP topics

## Install

```bash
git clone https://github.com/BadBeta/elixir-phase-skills.git
cd elixir-phase-skills
./install.sh
```

If `BB-skill-core` is not already installed, the script offers to clone and install it from GitHub. Set `BB_NONINTERACTIVE=1` to skip the prompt and fail-fast.

Override:
- `CLAUDE_HOME` — install root (default `$HOME/.claude`)
- `BB_CORE_REPO` — git URL for `BB-skill-core`

## Uninstall

```bash
./uninstall.sh
```

Removes only the Elixir-pack files. `BB-skill-core` and other language packs are untouched.

## Coexistence

Both `rust-phase-skills` and `elixir-phase-skills` can be installed side-by-side. They drop their own per-language fragments into `~/.claude/hooks/bb-anti-slop-patterns.d/` and `~/.claude/hooks/bb-skill-triggers.d/`, which the core hooks merge at runtime.

## Version compatibility

Pinned in `REQUIRES_CORE`. The installer refuses if `BB-skill-core` is older than this minimum.
