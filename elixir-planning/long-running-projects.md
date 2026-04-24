# Long-Running Elixir Projects — Session Handoff and Milestone Management

This subskill covers the meta-workflow that sits *above* individual
features: how to run an Elixir project that spans multiple sessions,
dozens of milestones, and months of elapsed time. The plan →
implement → review triad in the main `elixir-planning` /
`elixir-implementing` / `elixir-reviewing` skills handles a single
feature well; it does not answer:

- When do I update `continue.md`?
- What belongs in `PLAN.md` vs. `continue.md` vs. commit messages?
- How do I write a commit message that's useful for future-me in six
  months?
- What invariants should I verify at milestone boundaries?
- When does a pending-items list need pruning vs. amending?

This file answers those questions. Load when starting, restarting, or
continuing a multi-session Elixir project.

## The three-document model

A healthy long-running project maintains three coordinated documents:

| Document | Audience | Cadence | Truth-time |
|---|---|---|---|
| `PLAN.md` | Any engineer (incl. future-you) | Edit at milestone-start and milestone-end | Intent (slow-moving) |
| `continue.md` | Future-you picking up cold | Rewrite at every milestone finish | Current state (snapshot) |
| Commit messages | Anyone running `git log` | Every commit | Historical record |

Each document has a distinct job. Mixing them (putting `continue.md`
content in commit messages, putting commit-level detail in
`continue.md`) signals the system is drifting.

### `PLAN.md` — the design intent

What it contains:

- The problem you're solving (once, at top).
- Scope — MVP, explicitly out-of-scope, appendix-to-scope.
- Design decisions with rationale (not just "we did X" but "we did X
  because Y").
- A §12-style "out-of-scope milestones" / "pending items" list.
- Single-source-of-truth policy (what file owns each kind of
  invariant — e.g. "all Ecto validations live in the schema module",
  "all timeouts live in `config/runtime.exs`", "all role names live
  in `MyApp.Config`").

What it does NOT contain:

- Current milestone status (that belongs in `continue.md`).
- Blow-by-blow commit history (that belongs in `git log`).
- Solved-and-shipped design debates (move to an `ARCHIVE.md` or
  delete once the code is the source of truth).

**Edit cadence.** Touch `PLAN.md` at milestone-start (to record any
design decisions that were not obvious before implementation) and at
milestone-end (to mark shipped items as DONE). A `PLAN.md` that
hasn't been touched in ten milestones is stale, not durable.

### `continue.md` — the session handoff

One-paragraph summary at the top. Then sections that a cold-start
reader needs:

1. **Project location** — path and git branch.
2. **One-line summary** — what the project *is*.
3. **Current status snapshot** — commits, tests passing, Credo clean,
   Dialyzer clean (if used).
4. **What works live** — numbered list, specific enough to reproduce.
5. **Project layout** — directory tree with one-line-per-file purpose.
6. **Supervision tree diagram** — so a reader knows the process
   topology (even a text sketch is fine).
7. **How to run things** — exact commands:
   - `mix deps.get`
   - `mix ecto.setup` (or `mix ecto.reset`)
   - `mix test`
   - `iex -S mix phx.server` (or whatever the entry point is)
   - Any OS-level preconditions (Postgres running, Redis up, etc.)
8. **Architectural invariants** — the load-bearing ones,
   grep-verifiable where possible. Examples:
   - "Every `Repo.*` call lives in a context module; grep `Repo\.` in
     `lib/my_app_web/` returns nothing."
   - "Every `String.to_atom/1` call is on a trusted source or inside
     a `RULE-EXCEPTION:` comment."
   - "Every timeout value is a reference into `MyApp.Config`, not a
     literal integer."
9. **Non-obvious lessons learned** — bugs that cost real debugging
   and how they manifested.
10. **Remaining items** — pointing at `PLAN.md §12`, not duplicating.
11. **Recommended next step** — one paragraph, opinionated.

**Edit cadence.** Rewrite `continue.md` at every milestone finish.
Not amend — rewrite the relevant sections. Staleness in `continue.md`
is worse than staleness in `PLAN.md` because `continue.md` claims to
describe *now*.

### Commit messages — the historical record

Structure:

```
<short title>: <one-line summary>

<2-5 sentence paragraph explaining why, not what>

<optional bullet list of concrete changes>

<verification — tests run, credo output, manual check>

Co-Authored-By: ... (if applicable)
```

The `why` is the load-bearing part. "Fixes bug" is not a commit
message; "Fixes supervisor-restart loop — the GenServer crashed on
`handle_info/2` for an unexpected message; added a catch-all clause
that logs and continues" is. The `what` is in the diff; don't repeat
it in prose.

For milestone commits, the title follows `M<N>: <one-line intent>`.
The N lets `git log --oneline | head -20` read like a table of
contents.

## Milestone-boundary checklist

Before committing what you consider a "milestone finish," walk this
list. If any answer is "I'll do it later," it's not a milestone.

1. **Does the public API have a failing test that now passes?**
   Tests-first discipline at milestone scope. If the milestone added
   `Accounts.register_user/1`, there's an ExUnit test that exercises
   it through the context boundary. The TDD state hook is a backstop;
   this checklist is the foreground check.
2. **Does `mix credo --strict` pass with zero warnings?**
3. **Does `mix format --check-formatted` pass?**
4. **Does `mix test` pass including any `@tag :integration` /
   `@tag :external` suites that require Docker/external services?**
5. **Does `mix dialyzer` pass (if the project uses it)?** Spec
   regressions are cheap to catch here and expensive to catch later.
6. **Is the new public API documented?** Every `def` has a `@doc`
   and a `@spec`. Private helpers have `@spec` too if they're
   non-trivial. `@moduledoc` on every new module.
7. **Did you update `continue.md`?** Specifically: commit count,
   "what works live" list, project layout if any new file appeared.
8. **Did you update `PLAN.md`?** Mark pending items as DONE, append
   new follow-ups discovered during the milestone.
9. **Is the commit message complete?** Title, why, bullets, verification.
10. **Did you run the long test?** For Phoenix: a LiveView test that
    spans mount → event → update → assert. For OTP: a process-
    lifecycle test that spans start → work → crash → restart. For
    Nerves: a flash-and-boot smoke test. The hermetic unit tests
    prove isolation; the long test proves the thing works.

One pre-commit run, not a loop. If something fails, fix it and
re-run.

## SSOT invariant verification

For any project that declares an SSOT policy, run the invariant check
at milestone boundaries. Useful Elixir greps:

```bash
# 1. No Repo calls outside context modules (if you've declared this).
grep -rn 'Repo\.' lib/my_app_web/ lib/my_app/*/ --include='*.ex' \
  | grep -v ':moduledoc' \
  | grep -v '@doc'

# 2. Every String.to_atom/1 is on trusted input or annotated.
grep -rn 'String\.to_atom(' lib/ --include='*.ex' \
  | grep -v 'String\.to_existing_atom'

# 3. Magic durations outside config.
grep -rn ':timer\.\|Process\.send_after\|\:timeout' lib/ --include='*.ex' \
  | grep -v 'config/'

# 4. Hardcoded role/permission strings outside a Config / Role module.
grep -rn '"admin"\|"editor"\|"viewer"' lib/ --include='*.ex'

# 5. Raw SQL strings outside migrations.
grep -rn 'SELECT\|INSERT\|UPDATE\|DELETE' lib/ --include='*.ex'

# 6. Application.get_env outside the Config module (if you follow the
#    §10.5.1 centralization pattern).
grep -rn 'Application\.get_env\|Application\.fetch_env\|Application\.compile_env' \
  lib/ --include='*.ex'
```

Anything surfaced should either be justified (a `RULE-EXCEPTION:`
comment), moved into the SSOT file, or referenced from it. Doing
this ONCE per milestone keeps drift low; skipping it for three
milestones produces a fix-it-all sprint.

Add to `continue.md` §8 (architectural invariants) the exact grep
commands that *should return nothing* or *return a known small list*.
Verification becomes a scripted check, not a memory exercise.

## Ecto-specific milestone invariants

When your project uses Ecto, there's an additional class of
invariant-drift to watch for:

- **Migrations are never edited after deployment.** Fresh migrations
  only. Grep recent commits for changes to older migration files —
  every hit is either a genuine `pre-deploy` fix or a bug.
- **Schema and changeset live together.** The module
  `lib/my_app/accounts/user.ex` defines `defstruct` AND
  `changeset/2`. If someone's added changeset logic in a separate
  module, check if that was deliberate (it rarely should be).
- **Every NOT NULL column has either a schema-level default or a
  changeset-level `validate_required/2`.** Otherwise you get
  `Ecto.ConstraintError` at runtime, which is a UX regression.
- **Every many-to-many join table has a constraint migration.** Not
  just a schema `many_to_many`. The DB needs the enforcement.
- **Every `belongs_to` has a foreign-key migration with
  `:on_delete` configured.** Silent orphan rows are a long-tail bug
  class.

Add these to your milestone verification if Ecto is in scope.

## Pending items — prune vs. amend

A pending-items list in `PLAN.md §12` decays without discipline. Two
failure modes:

1. **Hoarding.** Every idea goes on the list; the list grows without
   bound; nothing is ever removed. Readers can't tell "maybe someday"
   from "next milestone."
2. **Silent drift.** Items are implemented without being marked DONE.
   `PLAN.md` claims a feature is pending that actually shipped three
   milestones ago.

Counter-measures:

- **Explicit DONE annotation, inline.** Don't remove the item —
  append `**DONE in M15** (commit hash, one-line summary).` That
  preserves the original framing (useful for future readers who want
  to know what the original scope was) while showing status.
- **Age-out.** Any item unshipped after ~10 milestones should be
  re-examined. If it's still desirable, restate it with current
  context. If it's no longer desirable, move it to a `DEFERRED.md`
  or delete with a note.
- **Numbering is immutable.** If the list numbers items 1-10, don't
  renumber when you drop one. `#3 (removed — superseded by #7)` keeps
  cross-references stable.
- **Separate "original" from "appended-later."** If the milestone
  arc has multiple phases (initial scope, then discovered items),
  keep them in separate lists so the original intent is legible.

## Commit-message style for long-running refactors

A multi-commit refactor (e.g., "address code review findings M15")
is NOT a series of independent commits. It's one logical change
broken up for review. The commit messages should reflect that.

Two styles that work:

### Style A: one-shot commit

```
Address code-review findings from M15 review pass

Works through all 8 findings from the elixir-reviewing sweep on the
GenServer + Phoenix context milestone. No behavior change for
existing callers; one breaking surface change (error-tuple shape).

### Error evolution (R1, S3)
...

### Supervision tree reshape (R2)
...
```

Single commit, structured sections for each grouped finding. Good
for review passes where findings interact.

### Style B: series with shared prefix

```
M15-review-1/N: typed error struct for Accounts (S3)
M15-review-2/N: @spec on all public context fns (R1)
M15-review-3/N: bounded mailbox on Queue GenServer (R2)
...
```

Shared prefix, explicit N-of-M counter, one finding per commit. Good
when findings are orthogonal and a reviewer might want to approve
some but not others.

Pick one, don't mix.

## Cross-session handoff checklist

Before closing a session (closing the terminal, ending the Claude
window, merging the PR), run:

1. **Is the working tree clean?** `git status` should be empty. No
   half-finished files. If there's in-progress work, commit as
   `WIP: <topic>` so future-you can find it.
2. **Are all commits pushed?** (If the project has a remote.)
3. **Does `continue.md` describe the current state?** Even one stale
   sentence burns future-you's trust in the document.
4. **Is the next action explicit?** `continue.md` §11 "Recommended
   next step" is the first thing future-you reads. Make it
   unambiguous.
5. **Are there any open questions you need to resolve before future-
   you can proceed?** Those belong in `continue.md` under a
   "Blockers / open questions" section, not in your head.

If future-you can't pick up the project from a cold read of
`continue.md` + `PLAN.md` + `git log`, something is missing. The
answer is almost always in one of those three places; the question
is whether you put it there.

## Autonomous-mode warnings for long-running work

In autonomous / milestone-by-milestone sessions, specific failure
modes compound over many milestones:

- **Citation leakage.** Inline comments like `# M15 fix for bug #42`
  rot. See anti-slop pair `planning-citation-in-source`.
- **Stale `continue.md`.** Each session updates at the end but never
  reads at the start. Cold-reads of your own doc are how you notice
  it's lying.
- **Accumulated pending items.** Every milestone appends to §12,
  never prunes. By milestone 20 the list is unreadable.
- **Commit-message decay.** Early milestones have `M1: full
  rationale`; late ones have `M17: fix`. The style drift is visible
  from `git log --oneline`.
- **SSOT violation creep.** Each milestone adds one "harmless"
  magic-number inline. Eight milestones later, the SSOT file is
  worthless.
- **TDD gate erosion.** Tests get written alongside implementation
  instead of first. The `tdd-state-hook` is a backstop; the
  milestone-boundary discipline is the foreground defense. See
  `elixir-implementing §0.5` (autonomous-mode warning) for why this
  matters more in long-running work than in one-shot tasks.

The counter to all of these is the milestone-boundary checklist
above. Run it every time. Taking 5 minutes at each milestone
boundary saves hours of bit-rot reconstruction later.

## When a project hibernates

If you know a project is about to pause (vacation, context switch,
"back in a month"), invest in extra handoff quality BEFORE closing
the last session. Specifically:

1. **Re-read `continue.md` cold.** Pretend it's a project you've
   never seen. What confuses you? Fix those spots.
2. **Freeze a known-good state.** Tag the commit (`git tag
   milestone-M17-shipped`) so you can return to a known reference.
3. **Record the tooling state.** Which Elixir / OTP / Phoenix / Ash
   versions did this build against? `mix.lock` pins them but
   `continue.md` should name the major versions explicitly so a
   cold reader knows what they need.
4. **Record discovered-but-unrecorded context.** Anything in your
   head that isn't in a file. Dump it into `continue.md`
   "Non-obvious lessons learned."
5. **Write the next-session kickoff prompt.** A literal paragraph
   you can paste into a new session: "We're resuming project X.
   Read `continue.md`, then tackle item Y."
6. **Pin any flaky tests as `@tag :skip` with a reason comment.**
   Future-you restarting with a green suite is much better than
   future-you debugging someone-else's code (which is what
   six-month-ago-you is) with a failing suite. Unpinning and fixing
   goes in an early milestone on return.

Hibernation-quality handoff is over-investment in ongoing development
but rational before a long pause. The test: can a version of you
from three months ago pick up where you left off in under 15
minutes? If not, one more read of `continue.md` is warranted.

## Related

- `test-strategy.md` — planning-time test pyramid decisions
- `process-topology.md` — supervision tree design
- `growing-evolution.md` — evolving an Elixir project over time
- `../elixir-implementing/SKILL.md §0` — the TDD gate that fires at
  every public function
- `../elixir-reviewing/SKILL.md §12b (Harvesting Findings)` — the
  review-time feedback loop into the implementing catalog
- `../../rust-planning/long-running-projects.md` — the Rust sibling of
  this subskill (same philosophy, language-specific tooling)
