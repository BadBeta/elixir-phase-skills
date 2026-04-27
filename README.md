# elixir-phase-skills

Replacement for the previous monolithic `elixir` skill. Layers on top of [BB-skill-core](https://github.com/BadBeta/BB-skill-core).

## Skills optimized for different development phases

Software work happens in distinct phases — planning architecture, implementing the design, reviewing what was built — and each phase wants a different *kind* of guidance. Planning is dominated by architectural decision tables and structural trade-offs (contexts, supervision shape, OTP boundaries). Implementing wants idiomatic templates, BAD/GOOD pairs, and "which construct?" tables that fire at the moment of writing (`with` vs `case` vs `cond`, `GenServer` vs `Task` vs `Agent`). Reviewing wants severity-classified checklists, debugging playbooks (recon, observer, sys.trace), and refactor templates.

When that all lives in a single skill, the LLM loads ~3000 mixed lines and applies whatever fragment surfaces — planning advice trips during implementation, review heuristics misfire on greenfield code, and the truly relevant section drowns in the rest. Phase-targeted skills make the right form of guidance fire at the right moment:

| Skill | Loaded when | Primary content |
|---|---|---|
| `elixir-planning` | Architecture, contexts, supervision tree, deployment | Numbered planning rules, OTP design tables, context-boundary patterns |
| `elixir-implementing` | At-the-keyboard coding | Pattern matching, `with` chains, OTP callback templates, BAD/GOOD pairs, TDD with ExUnit |
| `elixir-reviewing` | After-the-fact inspection | Severity-classified checklists, debugging + profiling playbooks, refactor templates |

The phases overlap intentionally — implementing references planning for "why this shape," reviewing references implementing for "what should I see here" — but each is optimized for one moment in the work. `phoenix` and `phoenix-liveview` ship alongside since they're inseparable from idiomatic Elixir web work.

## Hooks

Skills loaded ≠ skills applied. Putting knowledge into context doesn't ensure the LLM walks the decision tables, reads the BAD/GOOD pairs, or recalls the rules at the right edit site.

The `BB-skill-core` hook stack closes that gap. The skill-enforcement hook (PreToolUse) blocks mutating tools — Edit, Write, mutating Bash — until a relevant Skill has been invoked in the recent window. Orientation operations (`ls`, `pwd`, `git status/log/diff`, file reads) are exempt; the gate only fires when the LLM is about to *change* something. The `[use-skills]` marker activates this enforcement for a session; `[no-skills]` opts out.

Combined with the anti-slop scanner (PostToolUse) and the post-generator scanner (one-shot after `mix phx.new` / `mix igniter.new`), the stack catches what the skills warn about even when the LLM didn't re-attend to the relevant section — at the exact moment the file was written. The Phoenix `runtime.exs` port-bug, `unless ... else` shapes, `Process.sleep` in tests, `String.to_atom` on user input — all caught mechanically as code-level enforcement of skill knowledge. Skills become checkpoints, not just context.

## TDD

`[TDD]` in any prompt activates session-wide TDD enforcement. New public `def` declarations in `.ex` / `.exs` files trigger a forceful reminder unless one of these structural exemptions silences it:

- A test in the same project was edited within the last 15 minutes (test-first cycle in flight)
- The file co-locates tests (`defmodule …Test` or `doctest`)
- The function's name already appears in any file under `test/`
- The function's name exists in `git log -S` history (rename, move, module split)
- The file is a Rustler NIF loader stub (`use Rustler` + `:erlang.nif_error/1`)

The exemptions matter: TDD enforcement fires only on genuinely new behavior. Refactors are silent. When the gate does fire, the message is the full reminder every time — no fade — because the cost of a missed reminder is high and the cost of a noticed one is small. Use `[no-TDD]` to cancel mid-session.

## Plans

For long-running, milestone-structured projects (a `PLAN.md` with `M1:` / `M2:` / `M3:` … markers), `bb-milestone-skill-report.py` (PreToolUse) blocks edits to project files until `milestone_skill_report.md` has an entry for the active milestone listing which skill sections were considered before starting it.

This is the strongest skill-engagement mechanism in the stack — not a passive reminder, not an "always cite" suggestion, but a hard gate on the next file edit. The LLM cannot start implementing M3 without first writing, visibly and verifiably, which skill sections were *relevant* to that milestone — not "all loaded skills," just the ones that apply. If a relevant skill hasn't been loaded yet, it gets loaded. If a loaded skill doesn't apply to this milestone, it gets omitted (a milestone about background-job retry semantics shouldn't drag in `phoenix-liveview` for the sake of completeness). The plan and the relevant skill fragments are pulled into a single scan-able artifact that proves "the right knowledge was on the table when the work began."

`bb-milestone-commit-check.py` complements this by gating `M\d+:`-prefixed commits — the milestone must be marked DONE in `PLAN.md` before its commit is allowed.

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

Both `rust-phase-skills` and `elixir-phase-skills` can be installed side-by-side. They drop their own per-language fragments into `~/.claude/hooks/bb-anti-slop-patterns.d/`, `bb-skill-triggers.d/`, and `bb-post-generator-patterns.d/`, which the core hooks merge at runtime.

## Pack contents

- `elixir-planning/`, `elixir-implementing/`, `elixir-reviewing/` — the three phase skills
- `phoenix/`, `phoenix-liveview/` — the framework skills (bundled because they're inseparable from idiomatic Elixir web work)
- `hooks/bb-rationale-marker-elixir.py` — flags `# §§` rationale markers left in committed code
- `hooks/bb-anti-slop-patterns.d/elixir.json` — 18 Elixir anti-slop patterns (try/rescue for ok/error, `Process.sleep` in tests, `String.to_atom` on user input, the three `else`-shape smells, etc.)
- `hooks/bb-skill-triggers.d/elixir.json` — 110 keyword → skill mappings for Elixir / Phoenix / OTP / Ash / Nerves / Membrane topics
- `hooks/bb-post-generator-patterns.d/elixir.json` — checks for `mix phx.new` / `mix igniter.new` output (Phoenix `runtime.exs` port + secret_key_base guards)

Extensions covered: `.ex`, `.exs`, `.heex`, `.leex`.
