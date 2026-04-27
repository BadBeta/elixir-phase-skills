# elixir-phase-skills

Replacement for the previous monolithic `elixir` skill. In addition it needs [BB-skill-core](https://github.com/BadBeta/BB-skill-core) which install hooks common to all languages.

## Optimized for different development phases

Software work with Claude have phases of planning, implementing the plan, and then reviewing what was done. For each phase Claude is best served with a different *kind* of guidance. 

Planning by architectural decision tables and structural trade-offs (contexts, supervision shape, OTP boundaries). Implementing wants guidance that fires at the moment of writing like idiomatic templates, BAD/GOOD pairs, and "which construct?" tables. For reviewing severity-classified checklists, debugging playbooks and refactor templates work best.

With everything in a fat single major skill as before the LLM loads ~3000 mixed lines and segment will misfire: Planning advice trips during implementation, review heuristics on greenfield code, and the parts best focused on the current phase drowns between the others. Phase-targeted skills aim to give the right guidance at the right moment.

The phases intentionally overlap somewhat. Implementing references planning for "why this shape," reviewing references implementing for "what should I see here", and especially important parts can be repeated across two or all. 

The phoenix and phoenix-liveview skills were put in with the elixir skills but are not upgraded to phased. That will come later.

## Hooks

Getting the right skills invoked before Claude needs them can be a challenge. And having the skills invoked is not the same as the skills being actively used and applied. Claude is both lazy and arrogant.

The `BB-skill-core` hook stack closes that gap. The skill-enforcement hook (PreToolUse) blocks mutating tools like edit, write and mutating Bash until a relevant Skill has been invoked. The `[use-skills]` marker activates this enforcement for a session; `[no-skills]` opts out. It also activates some other hooks to help active use of the skills.

For important code decisions Claude it told to place a §§ marker in comment and cite any relevant decisions table or guidance in the skill for it's decisions. This is to promote active use of skills, and the comments can easily be scripted away later.

Another hook runs an anti-slop scanner that aims to catch some easy to detect issues that the skills warn about even if Claude ignored the skill. It fires before the offending slop is written to file, and thus while a better implementation can still be made with all context available. 

## TDD

`[TDD]` in any prompt activates session-wide TDD enforcement. New public `def` declarations in `.ex` / `.exs` files trigger a forceful reminder unless one of these structural exemptions silences it:

- A test in the same project was edited within the last 15 minutes (test-first cycle in flight)
- The file co-locates tests (`defmodule …Test` or `doctest`)
- The function's name already appears in any file under `test/`
- The function's name exists in `git log -S` history (rename, move, module split)
- The file is a Rustler NIF loader stub (`use Rustler` + `:erlang.nif_error/1`)

The exemptions aim to make TDD enforcement only fire on genuinely new behavior. Refactors should be silent. When the gate does fire, the message is the full annoying reminder every time on purpose. Because the cost of a missed reminder is high and the cost of a noticed one is small. Use `[no-TDD]` to cancel mid-session.

## Plans

For long-running, milestone-structured projects (ask for a milestone plan during planning) the hooks will force writing a skeleton milestone_skill_report.md with which skill sections were considered before starting the next step. 

This is not about reporting file as such. It is that writing this forces Claude to focus, work and use the relevant skills section before implementing. This is the strongest skill-engagement mechanism in the stack for long projects. 

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

The installs are namespaced 'bb' and purely additive, and should not affect any existing hooks or other installs. Likewise adding more languages will not affect the already installed ones. 

## Pack contents

- `elixir-planning/`, `elixir-implementing/`, `elixir-reviewing/` — the three phase skills
- `phoenix/`, `phoenix-liveview/` — the framework skills (bundled because they're inseparable from idiomatic Elixir web work)
- `hooks/bb-rationale-marker-elixir.py` — flags `# §§` rationale markers left in committed code
- `hooks/bb-anti-slop-patterns.d/elixir.json` — 18 Elixir anti-slop patterns
- `hooks/bb-skill-triggers.d/elixir.json` — keyword → skill mappings for Elixir and Phoenix 
- `hooks/bb-post-generator-patterns.d/elixir.json` — checks for `mix phx.new` / `mix igniter.new` output (Phoenix `runtime.exs` port + secret_key_base guards)

Extensions covered: `.ex`, `.exs`, `.heex`, `.leex`.

Claude has summarized a more detailed user guide which should be up to datish.



