---
name: elixir-reviewing
description: >
  Elixir code inspection — reviewing PRs and diffs, debugging bugs, and profiling performance.
  Covers the full audit toolkit: review checklists by area (architecture, control flow, OTP,
  testing, security, performance, configuration), severity classification, the debugging
  playbook (crashes, mailbox buildup, memory growth, slow response, flaky tests, Dialyzer
  warnings), the profiling playbook (:timer.tc, Benchee, fprof/eprof/tprof, :observer, memory
  analysis), performance pitfall catalog, refactor templates, and review-comment style.
  ALWAYS use when reviewing Elixir pull requests, diffs, or existing modules.
  ALWAYS use when debugging Elixir bugs — crashes, memory growth, mailbox buildup, flaky tests.
  ALWAYS use when profiling Elixir performance — finding bottlenecks, measuring, optimizing.
  ALWAYS use when asked to audit, critique, review, debug, or profile Elixir code.
  For designing from scratch load elixir-planning; for writing code load elixir-implementing.
---

# Elixir — Reviewing Skill

The skill for **inspecting existing Elixir code**. Three distinct modes, all covered here:

- **Review** — proactive audit of a PR or diff, looking for structural and stylistic issues
- **Debug** — reactive investigation of a specific bug or crash
- **Profile** — reactive investigation of a performance problem

This skill is the third in the Elixir family. The three divide labor by phase:

| Phase | Skill | Question it answers |
|---|---|---|
| Plan (before writing) | **[elixir-planning](../elixir-planning/SKILL.md)** | What to build, how to structure it |
| Implement (at keyboard) | **[elixir-implementing](../elixir-implementing/SKILL.md)** | How to type it idiomatically |
| Inspect (after writing) | **elixir-reviewing** (this) | What's wrong with it / where's the bug / why is it slow |

**Primary mode:** decision tables (where to look, what to flag, which tool) + BAD/GOOD pairs. Anti-pattern catalogs live in the other two skills; this skill cross-references them and frames each pattern as "flag if you see this" rather than "don't output this."

## How to use this skill

1. **Reviewing a PR / diff?** — Read §1 (Rules), §3 (Workflow), §7 (Checklists). Scan the diff against each checklist.
2. **Debugging a specific bug?** — §4 (Workflow), §8 (Playbook — find the symptom).
3. **Profiling performance?** — §5 (Workflow), §9 (Playbook — pick the right tool), §10 (Common pitfalls).
4. **Writing review comments?** — §6 (Severity), §12 (Comment style).
5. **Unsure if something is worth flagging?** — §6 Severity Classification.

### Subskills — deep inspection references

The core SKILL.md carries the always-loaded rules, severity guidance, workflow, checklists, and a tight playbook. For extended depth on a specific area, load the matching subskill:

| Subskill | Purpose | Load when... |
|---|---|---|
| [anti-patterns-catalog.md](anti-patterns-catalog.md) | Organized anti-patterns by category (code, process/OTP, Ecto/data, architecture/design, testing, security, config) with BAD/GOOD for each | General review / scanning a diff for named anti-patterns |
| [debugging-playbook-deep.md](debugging-playbook-deep.md) | Symptom → diagnosis flow for crashes, mailbox buildup, memory growth, slow response, flaky tests, Dialyzer warnings, CPU pegging | Investigating a specific bug |
| [profiling-playbook-deep.md](profiling-playbook-deep.md) | Tool selection + usage: `:timer.tc`, Benchee, fprof/eprof/cprof/tprof, `:recon`, `:observer`, telemetry, memory analysis | Measuring or optimizing performance |
| [performance-catalog.md](performance-catalog.md) | 32 common pitfalls with symptom → root cause → fix (data structures, Enum/Stream, OTP, Ecto, memory, serialization, Phoenix) | Looking for performance issues in a review |
| [security-audit-deep.md](security-audit-deep.md) | Security checklist: input validation, injection, auth/authz, logging, crypto (incl. `:crypto` primitive decision table), Phoenix/Ecto-specific pitfalls | Conducting a security review |

**Cross-skill references:** for WHAT to write (implementation) → `elixir-implementing`. For WHY it's shaped that way (architecture) → `elixir-planning`.

---

## 1. Rules for Reviewing, Debugging, and Profiling Elixir (LLM)

1. **ALWAYS separate severity from correctness.** A review finds *many* things; not all are worth blocking on. Use §6 to classify each finding as block / request-change / suggest / nitpick.
2. **ALWAYS start debugging with the smallest-scope tool** — `IO.inspect` or `dbg` before reaching for tracing, profiling, or Observer. Most bugs are found by inspecting values at suspect points.
3. **ALWAYS start profiling by measuring, not guessing.** Use `:timer.tc` for one-off timing, Benchee for comparisons, `mix profile.*` for finding the slow function. Never "optimize" without evidence.
4. **ALWAYS use `System.monotonic_time` for duration measurement** — never `System.system_time` (NTP sync causes jumps).
5. **NEVER use `:dbg` or `:erlang.trace` in production** — no safety limits, can crash nodes under load. Use `:recon_trace` or Rexbug with explicit message count limits.
6. **ALWAYS read the symptom before reading the code.** What does "slow" mean — p50, p99, tail? What does "crash" mean — which error, which stack frame, how often? A vague symptom wastes time.
7. **ALWAYS suggest the idiomatic refactor** when flagging an anti-pattern. "This is bad" without "do this instead" is low-value feedback.
8. **ALWAYS cross-reference elixir-implementing and elixir-planning** when flagging a finding — point reviewers to the section that explains *why* the idiomatic form is better.
9. **PREFER letting the supervisor restart a crashing process** over adding defensive `rescue` clauses. Before suggesting new error handling, ask whether the existing supervision tree already handles it.
10. **NEVER flag style issues that `mix format` or `mix credo` would catch.** Reviews are for things tools miss: architecture, idioms, subtle correctness, testability, performance.
11. **ALWAYS flag missing tests and `@spec` on public functions** — these are easy to add, compound in value over time, and are the strongest signal that a change was thought through.
12. **PREFER benchmark-driven refactor suggestions over intuition.** "This could be faster" is weak; "this is 40% slower in the linked Benchee run" is actionable.

---

## 2. The Three Modes of Inspection

The three modes of this skill are not interchangeable. Each has a different question, different tools, different output.

| Mode | Question | Primary artifact | Primary output |
|---|---|---|---|
| **Review** | "What's wrong with this diff?" | PR / branch diff | Comments with severity + suggested fix |
| **Debug** | "Why is this bug happening?" | Failing test, crash report, observed misbehavior | Root cause + the minimum fix |
| **Profile** | "Why is this slow / heavy?" | Production telemetry, benchmark, complaint | Identified bottleneck + measured improvement |

**They share one method:** read existing code, form hypotheses about what is wrong, verify with evidence (static — read the code; dynamic — run it with inspection). They differ in what "wrong" means and what "evidence" means.

**Choose the right mode:**

- Pre-merge, proactive → **Review**
- Post-merge, something's broken → **Debug**
- Post-merge, something's slow → **Profile**

Mixing modes wastes time: full review on a bug report, ad-hoc debugging on a PR diff, micro-optimization without measurement.

---

## 3. Review Workflow (PR / diff review)

### 3.1 Step-by-step

1. **Read the PR description.** What is the stated intent? Does the diff match?
2. **Read the tests first.** Tests describe behavior; code describes implementation. If the tests are missing or weak, that's the first finding.
3. **Scan the diff for architectural smells** (§7.1) — wrong layer, cross-context `Repo` calls, framework references from domain. These are block-severity by default.
4. **Scan for correctness issues** (§7.2–§7.5) — control flow, pipelines, error handling, pattern matching.
5. **Scan for OTP/process issues** (§7.6) — unsupervised work, blocking callbacks, call vs cast, state shape.
6. **Scan for security issues** (§7.8) — `String.to_atom` on user input, SQL injection via interpolation, leaked secrets in logs, unvalidated external data.
7. **Scan for testing gaps** (§7.7) — missing tests, tests that check implementation details, `Process.sleep` for async behavior.
8. **Scan for documentation gaps** — missing `@spec` / `@doc` / `@moduledoc` on public API.
9. **Scan for performance** (§7.9, §10) — obvious quadratic patterns, N+1 queries, GenServer bottlenecks, string concat in loops.
10. **Classify each finding** (§6) — block / request-change / suggest / nitpick.
11. **Write review comments** (§12) — specific, actionable, linked to the skill section that explains *why*.
12. **Check that the suggested fix is correct** before posting. An incorrect suggestion is worse than no suggestion.

### 3.2 Review decision — what to flag

| Observation | Action |
|---|---|
| Architectural smell (see §7.1) | Flag. Severity: block if it crosses a boundary; request-change if it reinforces a bad pattern |
| Control-flow anti-pattern (see §7.2) | Flag. Severity: request-change or suggest depending on reach |
| Missing `@spec` / `@doc` on new public function | Flag. Severity: request-change |
| Missing test for new behavior | Flag. Severity: block |
| Test that asserts implementation, not behavior | Flag. Severity: request-change — brittle test, blocks future refactors |
| Style inconsistency `mix format` / `credo` would catch | **Do NOT flag.** Let the tools handle it |
| `mix credo` finding already present | **Do NOT flag in the PR** — raise it separately or add to baseline |
| Taste preference with no evidence of harm | **Do NOT flag** — save capital for real findings |
| Security issue | Flag. Severity: block |
| Performance issue with no measurement | Flag as question: "have you measured this?" — do not block on speculation |
| Performance issue with measurement | Flag. Severity depends on impact |

### 3.3 What to check in every review

- [ ] Tests exist for the new behavior, and they pass
- [ ] Tests assert behavior, not internal calls
- [ ] `@spec` and `@doc` on every new or modified public function
- [ ] No `@moduledoc` missing on public modules (`@moduledoc false` is fine for internal)
- [ ] No cross-context `Repo` calls (see §7.1)
- [ ] No `String.to_atom(user_input)` (see §7.8)
- [ ] No `try/rescue` for expected failures (see §7.4)
- [ ] No `Process.sleep` in tests (see §7.7)
- [ ] Idempotent for retried operations (Oban workers, webhook handlers — see §7.6)
- [ ] Timeouts set where appropriate (see §7.9)

---

## 4. Debugging Workflow (finding a specific bug)

### 4.1 Step-by-step

1. **Reproduce the bug** — a bug you can't reproduce can't be fixed with confidence. If you can't reproduce, the first goal is to find a reproduction. Try: exact inputs from the report, similar inputs, boundary conditions, concurrent access.
2. **Write the failing test** (TDD-for-bugs) — the reproduction IS a regression test. See `elixir-implementing` §3.6.
3. **Read the error** — full stack trace, module, function, line. Is it an exception (raise), exit signal (`:exit`), crash (supervisor restart)?
4. **Form a hypothesis** about which code path produces the bug.
5. **Verify with evidence** — add `IO.inspect`/`dbg` at the hypothesized point. Run. Is the value what you expected?
6. **If the hypothesis is wrong**, widen the inspection outward. Walk backwards through the call chain.
7. **For process-level bugs** (timeouts, mailbox buildup, crashes), use `:sys.trace`, `:observer`, or `Process.info`.
8. **For concurrent/flaky bugs**, check test async isolation, shared state, timing assumptions.
9. **Once found, consider whether other places have the same bug.** A single bug often has family members.
10. **Commit the failing test alongside the fix** so the bug is guarded against regression.

### 4.2 Debug decision — which tool

| Question | Tool | Load for detail |
|---|---|---|
| What is this value at this point? | `IO.inspect/2` or `dbg/1` | — |
| What does this pipeline produce at each step? | `dbg()` at the end of the pipeline | — |
| Can I pause execution and inspect? | `IEx.pry/0` (needs `iex -S mix`) | — |
| What messages is this GenServer receiving? | `:sys.trace(pid, true)` | — |
| What is this process's state right now? | `:sys.get_state(pid)` | — |
| How long is this process's mailbox? | `Process.info(pid, :message_queue_len)` | — |
| What's the memory / CPU use of each process? | `:observer.start()` (GUI) or `:recon.proc_count/2` | — |
| What pattern of calls is hitting this module in prod? | `:recon_trace.calls(...)` with a message limit | — |
| Why does this test fail intermittently? | See §8.5 (flaky tests) | — |

### 4.3 Start small, escalate only when needed

- **First reach**: `IO.inspect` / `dbg`. Most bugs found here.
- **Next**: `IEx.pry` or `break!` to pause execution.
- **Next**: `:sys.trace` or `:sys.get_state` for OTP processes.
- **Next**: `:observer` for system-wide view.
- **Last resort**: `:recon_trace` or Rexbug for production tracing (with message limits!).

**NEVER skip straight to tracing/profiling when a single `IO.inspect` would show the bug.**

---

## 5. Profiling Workflow (finding a performance problem)

### 5.1 Step-by-step

1. **Define what "slow" means.** p50, p95, p99? Per-request? Whole-pipeline? Steady-state or cold-start? A vague "slow" wastes time.
2. **Measure before changing anything.** Set a baseline: `Benchee`, `:timer.tc`, `:telemetry` histogram. Without a baseline you cannot prove you made it faster.
3. **Profile to find the bottleneck** — which function / process is actually slow? Don't guess.
4. **Form a hypothesis** — *why* is this slow? Common causes in §10.
5. **Apply one change at a time.** Measure after each. If the change didn't help, revert it.
6. **Verify the improvement** at the same level the symptom was observed (e.g., if users complained about request latency, measure request latency — not just the inner function).
7. **Keep the measurement in CI** as a regression guard, or at minimum document the baseline and improvement.

### 5.2 Profile decision — which tool

| Need | Tool | Notes |
|---|---|---|
| One-off duration of a block | `:timer.tc(fn -> ... end)` | Returns `{microseconds, result}`. No warmup — misleading alone |
| Compare two implementations | `Benchee.run(%{...})` | Warmup, statistics, memory |
| Find which function in a call tree is slow | `mix profile.fprof` | High overhead, detailed — use for dev, not prod |
| Time spent per function | `mix profile.eprof` | Moderate overhead — profile tests or dev requests |
| Call counts only | `mix profile.cprof` | Low overhead — which functions are called most |
| Unified modern profiler | `mix profile.tprof` | OTP 27+, lower overhead — prefer for large code bases |
| System-wide CPU/memory per process | `:observer.start()` (GUI) | Interactive |
| Programmatic top-N processes | `:recon.proc_count(:memory, 10)` / `:recon.proc_count(:message_queue_len, 10)` | Safe in prod |
| ETS table sizes | `:ets.i()` or iterate `:ets.all()` | |
| Detect binary memory leaks | `:recon.bin_leak(10)` | Forces GC, returns top binary-hoarders |
| Production request-level timing | `:telemetry.span/3` + telemetry handlers | Low overhead, production-safe |

### 5.3 Rules specific to profiling

- **Always warm up before measuring.** The BEAM JIT (OTP 24+) needs several runs to reach steady state. Benchee handles this; `:timer.tc` does not.
- **Always measure at the right granularity.** Micro-benchmarking a function that's called once per hour is wasted effort. Macro-benchmark the request / job / pipeline first, then zoom in.
- **Never optimize without profiling first.** You'll optimize the wrong thing.
- **Beware the heisenberg effect.** Heavy profilers (fprof, especially under tracing) change timing characteristics — microbenchmark results may not match production.
- **Production profiling must be bounded.** Message-limit every trace. A runaway trace can exhaust a node.

---

## 6. Severity Classification

Every review finding needs a severity. Without it, the reviewer defaults to "everything is equally important" — which devalues every comment.

| Severity | Meaning | Examples |
|---|---|---|
| **Block** (must fix before merge) | Correctness bug, security issue, missing test, architectural violation | `String.to_atom(user_input)`; domain module importing web; business logic in controller; no test for new feature |
| **Request-change** (should fix, negotiable) | Clear idiom violation, missing `@spec`/`@doc`, brittle test, sub-optimal pattern | `length(list) > 0`; if/else for structural dispatch; `try/rescue` for ok/error flow; test asserting mock was called |
| **Suggest** (nice to have, author's call) | Refactor that would improve readability / maintainability | Extract a helper; prefer `for` comprehension over `reduce`; use `Map.new/2` instead of `Enum.reduce` into `%{}` |
| **Nitpick** (take-it-or-leave-it) | Style, naming, comment wording — things that don't affect behavior | Prefer `current_user` to `user`; this docstring could be clearer |
| **Question** (need info) | Clarification needed before you can assess | "Have you measured this?" / "Why not use existing X?" |

**Rules:**

1. Each block-severity finding must be fixed before merge.
2. Prefer suggest over request-change when you're unsure. Request-change is a stronger claim.
3. Explicitly label nitpicks as "(nit)" so the author can safely ignore them.
4. Don't block on taste. Block on facts.
5. Don't block on things the author didn't touch. File a separate issue.

**Severity by PR size:**

- Small PR (<100 LoC) — pick your battles; probably only block-severity comments + a handful of suggests
- Medium PR (100–500 LoC) — full review; classify everything
- Large PR (500+ LoC) — ask for a split first. Reviewing large PRs well is hard; reviewing them badly is worse than not reviewing them

---

## 7. Review Checklists — What to Flag

> **Depth:** For the consolidated catalog of named anti-patterns organized by category (code / process / Ecto / architecture / testing / security / config), each with a BAD/GOOD pair — load [anti-patterns-catalog.md](anti-patterns-catalog.md). Use that when you spot something "off" and want to name it; use this §7 when you want to scan a diff systematically by area.

Each subsection is a scanning checklist. Read left to right: "if you see this" → "flag it because" → "suggest this" → "severity". Links to the owning skill sections explain *why* for the author.

### 7.1 Architectural review

Full reference: `elixir-planning` §14. Flag these if you see them in a diff.

| If you see... | Suggest instead | Severity | Why — see |
|---|---|---|---|
| Directories like `lib/my_app/models/`, `services/`, `helpers/` | Contexts (`lib/my_app/accounts.ex` + `lib/my_app/accounts/*.ex`) | Block | planning §14.1 |
| Domain module aliasing `MyAppWeb.*`, `Phoenix.*`, `Routes.*` | Keep domain framework-agnostic; move URL generation to interface layer | Block | planning §14.2 |
| Controller / LiveView / CLI calling `Repo.X` directly | Call the owning context's public API | Block | planning §14.3 |
| Business logic in a controller action, LiveView handler, or CLI handler | Move to a context function; interface translates + delegates + formats | Block | planning §14.3 |
| `Plug.Router` route block calls another Plug module's `call/2` directly with raw opts (e.g. `get "/", do: Handler.call(conn, [])`) | Pre-initialize at compile time: `@handler_opts Handler.init([])` and `get "/", do: Handler.call(conn, @handler_opts)`. Bypassing `init/1` drops opt normalization — a latent trap that breaks silently the moment `init/1` stops being a no-op | Block | implementing production-patterns §Plug.Router dispatch |
| Two contexts writing to the same table | One owns it; the other reads through owner's API or uses PubSub | Block | planning §14.11 |
| `Repo.preload(:other_context_association)` across contexts | Ask the owning context for assembled data | Request-change | planning §14.12 |
| One context's internal module called from another context | Go through the owning context's public API | Request-change | planning §6.4 |
| `defdelegate` pass-through in a context | Fine if pure pass-through; flag if the context should add telemetry/logging | Nitpick | planning §6.7 |
| Business logic in a GenServer `handle_call` | Extract to pure module; GenServer delegates | Request-change | planning §14.6 |
| Feature being added to a growing "god context" | Does it belong? Consider split criteria | Suggest | planning §6.2 |
| Introducing an umbrella split for "it feels big" | Keep single-app; add contexts | Request-change | planning §14.7 |
| Adding a new inter-context call via PubSub before trying direct function calls | Can direct calls work? Escalate only when justified | Suggest | planning §9.9 |
| Adding Oban / GenStage / event sourcing without a triggering problem | Use the simplest mechanism; escalate only when needed | Request-change | planning §9.9 |
| Missing `@moduledoc` on a public module | Add `@moduledoc` or explicit `@moduledoc false` | Request-change | implementing §8.5 |
| Missing `@spec` on a new public function | Add `@spec` | Request-change | implementing §6.10 |
| `@impl true` implementation with no explicit `@spec` | Add `@spec` on the implementation too — `@impl` links to the behaviour spec but doesn't substitute | Suggest | implementing type-and-docs rule 1 |
| Behaviour callback overloaded with a "reflection" atom (e.g. `execute(:list_instructions, a, b)`) | Give reflection its own callback (`instructions/0`, `describe/0`) | Request-change | planning §4.9 |
| Union type variant with `{:tag, nil}` payload sentinel | Use bare atom: `:tag` — don't carry a nil payload | Nitpick | implementing type-and-docs §Union types |
| Public `@spec` uses a loose type (`atom()`, `map()`, `[term()]`) where a named `@type` is already defined in scope | Reuse the named alias: `MyMod.instruction()`, `MyMod.t()`, `[MyMod.entry()]` | Suggest | implementing type-and-docs rule 7 |
| `@moduledoc` / `@doc` asserts a behaviour (binds to both X and Y, rejects Z, accepts ranges A..B) not exercised by a test | Add a test that pins the claim, OR update the doc to match the code. Stale docs mislead worse than missing docs do | Request-change | implementing type-and-docs rule 13 |
| Two moduledocs that describe the same subsystem disagree (e.g., `App.Application` says "binds IPv4 only" while `Plugs.RequireLoopback` says "binds IPv4 + IPv6") | Reconcile both moduledocs against the code as one atomic change. Cross-file contradictions are Rule 13 distributed — harder to spot, same defect | Block | implementing type-and-docs rule 14 |
| Plug's `init/1` / `call/2` uses `Plug.opts()` when the plug actually accepts specific keys | Define a narrow `@type opts :: [...]` and use it in both specs | Suggest | implementing type-and-docs §Plug signature |
| New feature is a library candidate but uses `Application.compile_env` | For library code, use runtime `get_env` or config-via-args | Block (if library) | planning §10.3 |
| Public context function's moduledoc claims atomicity ("both X and Y, or neither") across a DB write AND a non-DB side effect (process-registration, PubSub broadcast, external API call), but the code just does them sequentially and doesn't roll back | Wrap both in `Ecto.Multi.run/3` so the DB row rolls back on side-effect failure, OR remove the atomicity claim and document the recoverable orphan state. Either way: the moduledoc must match the code — this is Rule 13 applied to a specific anti-pattern | Request-change | implementing type-and-docs rule 13 |
| Moduledoc references a future milestone ("M9 will add Broadway" / "in M12 this becomes atomic") after that milestone has already merged | Rewrite the claim in the present tense describing current behaviour. Milestone-references belong in commit messages and a plan doc, not in each module's `@moduledoc` where they silently decay into lies | Suggest during a rollout; Request-change three milestones after the referenced one merged | implementing type-and-docs rule 13 |
| LiveView `handle_info` handler for a PubSub message reloads the whole collection from the DB to derive a counter / display state that could be updated from the message content + existing assigns | Change the **broadcast payload** to carry everything the subscriber needs (e.g., `{:device_state_changed, id, old, new}` not `{:device_state_changed, id, new}`) so the LV can update assigns in O(1) instead of re-querying. Never pay N queries per message | Request-change | phoenix-liveview rule 2 + implementing production-patterns |

### 7.2 Control flow review

Full reference: `elixir-implementing` §7.1. Flag these patterns when you see them.

| If you see... | Suggest instead | Severity |
|---|---|---|
| `if is_map(x) and Map.has_key?(x, :type)` or similar shape-discriminating `if` | Multi-clause function with pattern matching | Request-change |
| `if opts[:flag] do ... else ... end` with value-returning branches | `case Keyword.get(opts, :flag, false) do true -> ...; false -> ... end` | Suggest |
| Nested `case` (2+ levels) on ok/error results | `with` chain | Request-change |
| `with` containing a single clause | Plain `case` | Nitpick |
| `if user != nil do ... if user.name != nil ...` (nil-check cascades) | Multi-clause on shape: `def greet(%{name: name}) when is_binary(name), do: ...; def greet(nil), do: ...` | Request-change |
| `cond` without a `true -> default` branch | Add explicit default; otherwise `CondClauseError` on fall-through | Block |
| `case x do 1 -> :one; 1.0 -> :one_float end` | Use guards (`n == 1`) — integer literal ≠ float literal | Request-change |
| `case` where every branch returns an error-shape (identity case) | Replace with direct return | Suggest |
| `unless x, do: a(), else: b()` | Invert: `if x, do: b(), else: a()` | Nitpick |

### 7.3 Pipelines review

Full reference: `elixir-implementing` §5.1, §7.2.

| If you see... | Suggest instead | Severity |
|---|---|---|
| `name \|> String.upcase()` (single-step pipe) | Direct call: `String.upcase(name)` | Request-change |
| Multiple `\|>` on one line: `list \|> Enum.map(f) \|> Enum.sum()` | One pipe per line | Nitpick |
| `data \|> (fn x -> ... end).()` | `data \|> then(&(…))` | Request-change |
| `Enum.reduce_while(...) \|> case do ... end` (single-step pipe into case) | Assign to `result`, then `case result do` | Request-change |
| Piping a literal list: `["a", "b", "c"] \|> Enum.map(&...)` | Direct call: `Enum.map(["a","b","c"], ...)` | Suggest |
| Pipe chain of 5+ steps without intermediate names | Consider extracting the middle into a named helper | Suggest |
| `if cond, do: func(data), else: data` inside a pipeline flow | `maybe_X/2` multi-clause helper or `then(&if/1)` | Suggest |

### 7.4 Collections / iteration review

Full reference: `elixir-implementing` §6.4–§6.5, §7.3.

| If you see... | Suggest instead | Severity |
|---|---|---|
| `Enum.each(xs, fn x -> result = ... end)` then using `result` | `Enum.map` or `Enum.reduce` — `each` rebind doesn't escape | Block (correctness bug) |
| `length(list) > 0` or `length(list) == 0` (O(n)) | `list == []` / pattern match `[_ \| _]` / `[]` | Request-change |
| `Enum.filter(xs, pred) \|> Enum.map(f)` (two passes) | `for x <- xs, pred.(x), do: f.(x)` | Suggest |
| `Enum.reject(xs, pred) ++ Enum.filter(xs, pred)` (two filters for partition) | `Enum.split_with(xs, pred)` — one pass | Request-change |
| `Enum.reduce(xs, %{}, fn ... -> Map.put(...) end)` | `Map.new/2` or `for ..., into: %{}, do: ...` | Suggest |
| `Enum.map(xs, fn x -> Mod.fun(x) end)` (anon fn wrapping named fn) | `Enum.map(xs, &Mod.fun/1)` | Nitpick |
| Manual index tracking: `Enum.reduce(xs, {[], 0}, ...)` | `Enum.with_index/1,2` | Request-change |
| `Enum.reduce(xs, "", &(&2 <> &1))` (string concat in loop, O(n²)) | IO list + `IO.iodata_to_binary/1`, or `Enum.map_join/3` | Block (performance) |
| `Enum.map/filter/etc.` on a large dataset or stream | `Stream.*` + terminal `Enum.*` | Suggest (performance) |
| `Enum.find` + `if` pattern | `Enum.find_value/2` or `Enum.find/2` with match | Suggest |
| `Enum.group_by(xs, &key/1) \|> Enum.(each\|map)(fn {k, group} -> f(k, length(group)) end)` (materializes per-key lists just to count them) | `Enum.frequencies_by(xs, &key/1) \|> Enum.each/map(...)` — one pass, integer counts, no intermediate list allocation | Request-change on hot paths; Suggest otherwise |

### 7.5 Error handling review

Full reference: `elixir-implementing` §7.4, §8.1–§8.2.

| If you see... | Suggest instead | Severity |
|---|---|---|
| `try do ... rescue ArgumentError -> ...` around `String.to_integer` / similar | Use `Integer.parse/1` / `Integer.parse/2` which returns ok/error | Request-change |
| `try do GenServer.call(...) rescue _ -> ...` (rescue around GenServer.call) | `catch :exit, _` — GenServer.call raises exits, not exceptions | Block |
| Non-bang function named `X` that `raise`s on error | Rename to `X!`, add a non-raising `X` returning ok/error | Request-change |
| `rescue _ -> nil` (swallow all errors) | Rescue specific exceptions; for truly unknown, let the supervisor restart | Block |
| `raise "..."` inside a non-bang public function | Return `{:error, reason}` | Request-change |
| Bang function with no non-bang counterpart in a library | Provide both where it makes sense | Suggest |
| `catch` for expected business failures | Return ok/error tuples | Request-change |
| Missing `{:error, reason}` shape documentation in `@spec` | Tighten the `@spec` with concrete error types | Request-change |
| Operation in Oban / webhook / event handler that's not idempotent | Make idempotent (see planning §7.3) | Block |
| Compound error reason squashing distinct failures (e.g. `{:out_of_range_or_wrong_type, v}`) | Split into distinct tags: `{:wrong_type, v}` + `{:out_of_range, v, range}` | Request-change |
| Public module mixes raise and `{:error, _}` for same failure class (e.g. `describe/1` raises but `execute/4` returns `{:error, _}`) | Pick one per boundary. Safe name returns ok/error; `!` variant raises | Request-change |
| `with` chain validates data inputs before dispatch key, forcing dummy data for reflection calls | Validate dispatch key first; reflection paths then bypass data validation | Suggest |
| `with` chain mixes sentinel-valued short-circuits (`:noop`, `:skip`) and `{:error, _}` tuples, with an `else` clause `:noop -> :noop; other -> other` passing everything else through untyped | Give `:noop` / `:skip` explicit `else` clauses separately from `{:error, _}=e -> e`, OR split into two functions: a "should-we-run" predicate on top, a `with` chain only for actual work. Current shape lets future `{:error, _}` returns leak unreviewed into callers | Suggest |

### 7.6 Process / OTP review

Full reference: `elixir-implementing` §9, `elixir-planning` §8.

| If you see... | Suggest instead | Severity |
|---|---|---|
| `spawn(...)` or `spawn_link(...)` for long-running work | Supervised Task (`Task.Supervisor.start_child/2`) or GenServer | Block |
| GenServer callback doing I/O (HTTP, DB, `Process.sleep`) | Offload to a Task; use `handle_continue/2` for init | Request-change |
| Business logic in `handle_call`/`handle_cast`/`handle_info` | Extract to pure module; callback delegates | Request-change |
| `GenServer.call(pid, :msg)` without explicit timeout | Pass `timeout` arg explicitly (default 5000ms is often wrong) | Request-change |
| `GenServer.call` to a variable pid without `catch :exit` | Wrap with `try ... catch :exit, _ -> {:error, :down}` — the process may die mid-call | Request-change |
| Hardcoded timeout literal like `GenServer.call(pid, msg, 30_000)` | Extract to `@default_X_timeout` module attribute | Suggest |
| Registry + DynamicSupervisor under `:one_for_one` | Dedicated `:one_for_all` sub-supervisor so both restart together when Registry dies | Block |
| GenServer with large state (> ~100KB) | Move large data to ETS / `:persistent_term` | Request-change |
| GenServer just wrapping a map (get/put) | Use ETS directly (no serialization bottleneck) | Suggest |
| Registry-registered process called as `GenServer.call(:name, msg)` | Use `{:via, Registry, {Reg, name}}` or helper `via/1` | Block |
| Unsupervised `Task.async(fn -> ... end) \|> Task.await/2` in a GenServer callback | `Task.Supervisor.async_nolink/3` + handle `:DOWN` | Request-change |
| Agent-per-entity (simulating objects) | Pure functional modules for thought concerns; processes only for runtime concerns | Request-change |
| Missing catch-all clause in `handle_info` | Add `def handle_info(msg, state) do Logger.warning(...); {:noreply, state} end` | Request-change |
| Missing `@impl` on behaviour callback | Add `@impl true` (or `@impl BehaviourModule`) | Request-change |
| Raw `%{}` / `Map.put` on a struct (silently accepts typos) | Struct update `%{struct \| field: val}` | Request-change |
| No `format_status/1` on GenServer holding secrets | Implement `format_status/1` to scrub tokens/passwords | Request-change |
| GenServer calls `:net_kernel.monitor_nodes(true)` in `init/1` without replaying `Node.list()` in `handle_continue/2` | Node connections that formed before this GenServer started are invisible — monitor_nodes only delivers future events. Retro-scan pattern: `{:ok, state, {:continue, {:retro_nodeup, Node.list()}}}` then fire the same handler. Same pattern applies to `Process.monitor/1` against a pre-existing DynamicSupervisor's children | Request-change if the GenServer drives business logic from nodeup; Suggest if audit-only |
| Synchronous call into another OTP app's API inside `init/1` (e.g. `:fuse.install/2`, shared `:ets.new/2`, `:persistent_term.put/2` for boot config) | Defer to `handle_continue/2`. Listing the dep in `extra_applications` gives a partial order within the current app but not across apps — a GenServer in app A doing `B.init_table/1` in its own `init/1` can race with app B's own boot | Request-change |

### 7.7 Testing review

Full reference: `elixir-implementing` §3–§4.

| If you see... | Suggest instead | Severity |
|---|---|---|
| New public function without a test | Add tests — block until done | Block |
| Test using `Process.sleep` before asserting on async behavior | `assert_receive pattern, timeout` | Request-change |
| Test asserting a specific internal function was called | Test observable behavior, not call sequence | Request-change |
| `use MyApp.DataCase` with `async: false` for no clear reason | Use `async: true` — Ecto sandbox supports it | Suggest |
| Test calls `handle_call` directly | Test via the client API | Request-change |
| `Mox.stub` where `expect` is appropriate (must-be-called behavior) | Use `expect` — stub gives no verification | Request-change |
| Mocking a module the project owns (Accounts, Pricing) | Test directly; mock only system boundaries | Block |
| No `setup :verify_on_exit!` with Mox | Add `setup :verify_on_exit!` in test module | Request-change |
| Test using `assert result == {:ok, ...}` (stringified) | `assert {:ok, %User{...}} = result` (pattern match, better failure) | Suggest |
| Factory creating hardcoded unique values | Use `sequence(:email, &"user-#{&1}@x.com")` | Request-change |
| Test with 10+ lines of setup for a pure function test | The function needs a boundary — pure tests shouldn't need this much setup | Suggest (architectural) |
| Test that "sometimes" fails | Never leave flaky tests — find the root cause | Block |
| Parametrized test loop using `@attr bad` rebinding to smuggle the loop variable into each generated `test` | Use a single `test` with `for` loop inside the body (rich assertion messages), or `unquote(Macro.escape(bad))` in the test body (which IS inside a quote) | Suggest | implementing testing-patterns §Parametrized Tests |
| Canonicalizer / validator / parser function with only example-based tests | Add StreamData property tests. Tables miss adversarial edge cases — port suffixes, case variants, IPv4-mapped IPv6, trailing whitespace, Unicode homoglyphs | Suggest | implementing testing-patterns §Property-Based |
| Duplicated fixture data / lookup maps across multiple tests in the same file (e.g., same `valid_pairs = %{...}` copied into two tests) | Extract to a `@module_attribute` or a `setup` callback that returns it in the context | Suggest | implementing testing-patterns |

### 7.8 Security review

> **Depth:** For the full security audit checklist (input validation/injection, authn/authz, logging, crypto, Phoenix/Ecto-specific, dependency & operational concerns), load [security-audit-deep.md](security-audit-deep.md).

Commonly overlooked. Flag any of these.

| If you see... | Suggest instead | Severity |
|---|---|---|
| `String.to_atom(user_input)` or `Jason.decode!(json, keys: :atoms)` | `String.to_existing_atom/1`, or decode to string keys and convert explicitly | Block (atom table exhaustion) |
| SQL built with string interpolation (raw query) | Parameterized query via `Ecto.Query` or `Ecto.Adapters.SQL.query/3,4` with args | Block (SQL injection) |
| User-supplied data passed to `:erlang.binary_to_term/1,2` | Use `:safe` mode or prefer JSON / well-defined format | Block |
| Untrusted HTML interpolated into a template | Use LiveView's default safe rendering; only `raw/1` with known-safe content | Block (XSS) |
| Secrets, tokens, passwords in logs or error messages | Filter via `Logger.metadata`, `format_status/1`, or redact explicitly | Block |
| Secrets in `config/config.exs` or `config/dev.exs` | Move to `config/runtime.exs` + env vars | Block |
| Secret committed in a migration / seed / test file | Block; rotate the secret; move to env | Block |
| `File.read!("/user/#{user_input}")` (path interpolation) | Validate path; use `Path.expand/1` + check it stays within a safe root | Block (path traversal) |
| External HTTP call without timeout | Set `receive_timeout`; default may be infinite | Request-change |
| Endpoint without CSRF protection (non-API) | Phoenix's `:protect_from_forgery` plug | Block |
| Cookie without `secure`, `http_only`, `same_site` | Set them in endpoint config | Block (production) |
| No rate limiting on auth / password-reset / OTP endpoints | Add rate limiting (Plug, ex_rated, Hammer, or custom) | Request-change |
| Auth check in the controller, not in the context | Auth is cross-cutting — a plug or the context's public API should enforce it | Request-change |

### 7.9 Performance review (scan level)

**Flag obvious issues here. For measured performance investigation, use §9 (Profiling Playbook).**

| If you see... | Suggest instead | Severity |
|---|---|---|
| N+1 query pattern: `Enum.map(xs, fn x -> Repo.get!(...) end)` | `Repo.preload/2,3` or batch query | Block |
| `Enum.reduce(xs, "", &(&1 <> &2))` in a hot path | IO list pattern | Block (O(n²)) |
| GenServer on the hot path serving reads | ETS `:public` + `read_concurrency: true` | Request-change |
| `length/1` used for "is non-empty" checks | Pattern match `[_ \| _]` vs `[]` (O(1)) | Request-change |
| `Enum.sort` followed by `Enum.take(1)` or `Enum.take(-1)` | `Enum.min`, `Enum.max`, `Enum.min_by`, `Enum.max_by` | Request-change |
| Large data in `Application.get_env` on a hot path | `:persistent_term` | Suggest |
| `Ecto.Repo` per-request query building with identical queries | Consider compile-time query module or `prepare: :named` | Suggest |
| Repeated `Jason.decode!` of the same JSON in a loop | Decode once outside the loop | Request-change |
| `Task.async` + `Task.await` for bounded parallelism | `Task.async_stream` with `max_concurrency` | Suggest |
| Missing index on a queried foreign key | Add index in migration | Request-change (if queried often) |
| Streaming large files via `File.read!` | `File.stream!` + `Stream.*` | Request-change |

### 7.10 Configuration review

Full reference: `elixir-implementing` §8.6, `elixir-planning` §10.

| If you see... | Suggest instead | Severity |
|---|---|---|
| `System.get_env(...)` in `config/config.exs` | Move to `config/runtime.exs` | Request-change |
| `Application.compile_env` in a library | Runtime `get_env` or accept config via options | Block (if library) |
| Missing default in `Application.get_env(:app, :key)` | Provide default (`get_env(:app, :key, default)`), or use `fetch_env!` if required | Request-change |
| Config value read on every call (hot path) | Cache in module attribute (app), `:persistent_term` (library hot path), or `Application.compile_env` (app) | Suggest |
| Application code uses `Application.get_env` for a value that's truly frozen at compile time (no `runtime.exs` override, no test `put_env`) | Switch to `Application.compile_env` — Dialyzer sees the concrete type, missing-key crashes at compile, recompile triggers on config change. **Don't blindly switch:** if `config/runtime.exs` or any test overrides the key at runtime, `compile_env` silently freezes the default and breaks those flows. Verify both paths before changing | Suggest | implementing §10.5 |
| `config/runtime.exs` parses an env var with `String.to_integer/1`, `String.to_atom/1`, etc. on raw input | Wrap with explicit validation: `case Integer.parse(val) do {n, ""} when n in range -> n; _ -> raise "VAR_NAME must be X, got: #{inspect(val)}" end`. A raw conversion exception at boot gives ops a stacktrace instead of a message | Request-change | implementing production-patterns §runtime.exs |
| `runtime.exs` splits a comma-separated env var and `String.to_atom/1` on each element (`NODEPULSE_NODES="a@h1,b@h2"` → list of atoms) | Even for operator-controlled inputs this is unbounded atom creation on typos. Validate each element against a regex like `~r/^[a-z][\w]*@[\w\-.]+$/i` BEFORE converting, OR cap the list size, OR use `String.to_existing_atom/1` with a raise-on-unknown fallback. A CI pipeline accidentally generating a list of 10k node names can permanently exhaust the atom table | Block if from CI/untrusted; Request-change if strictly operator-controlled | implementing production-patterns §runtime.exs |
| Hardcoded URLs / credentials / secrets | Move to config + env var | Block |
| Test config imported into runtime code | Keep `config/test.exs` isolated; production should never import test config | Block |

---

## 8. Debugging Playbook — by symptom

> **Depth:** For expanded symptom → diagnosis flow with concrete investigation steps, classification tables for crash reasons, and specific fixes, load [debugging-playbook-deep.md](debugging-playbook-deep.md).

Each subsection: **symptom → likely causes → investigation steps → fix pattern**.

### 8.1 Crash / unexpected exit

```
Symptom: process is crashing, supervisor is restarting it, stack trace in logs
```

| Likely cause | Investigation | Fix |
|---|---|---|
| Exception in `init/1` | Read the stack trace; check `init/1` for unwrapped fallible ops | Use `{:ok, state, {:continue, :setup}}` to defer expensive init |
| Unhandled `handle_info` message | Grep for `handle_info`, add catch-all clause | `def handle_info(msg, state) do Logger.warning("unexpected: #{inspect(msg)}"); {:noreply, state} end` |
| Linked task crash propagating | Task uses `async` (linked) instead of `async_nolink` | Switch to `Task.Supervisor.async_nolink/3` + handle `:DOWN` |
| `MatchError` in `handle_call` | A pattern in the function head or body didn't match | Add missing clause; return `{:error, reason}` instead of pattern-matching happy path |
| `FunctionClauseError` on a public fn | Input shape didn't match any clause | Add validating clause at the top or a fallback clause |
| `:timeout` exit from GenServer.call | Callee slow or busy | Profile callee; extract work to Task; increase timeout only after understanding why |
| Infinite supervisor restart loop | Child crashes immediately on startup; `max_restarts` exceeded | Look at `init/1`; check for missing config; guard against startup with no DB |

**Tools to reach for:**

```elixir
# 1. Read the full stack trace — Elixir shows it in Logger output
# 2. Check the process's last known state
:sys.get_state(pid)
# 3. Trace the process to see messages arriving
:sys.trace(pid, true)
# ... reproduce ...
:sys.trace(pid, false)
# 4. See what's in the mailbox right now
Process.info(pid, :message_queue_len)
Process.info(pid, :messages)        # actual messages (copy — heavy!)
```

### 8.2 Memory growth / leaks

```
Symptom: memory usage growing over time, OOM eventually
```

| Likely cause | Investigation | Fix |
|---|---|---|
| Large binaries retained via references | `:recon.bin_leak(10)` — forces GC, shows processes holding binary refs | Copy binary to detach: `:binary.copy(bin)` |
| Process mailbox growing unbounded | `:recon.proc_count(:message_queue_len, 10)` | Add backpressure (GenStage), or selective receive, or shed load |
| ETS table growing unbounded | `:ets.info(table, :size)` / `:ets.info(table, :memory)` | Add TTL, explicit eviction, or bounded cache |
| Process state accumulating (`[x \| state]` forever) | `:erlang.process_info(pid, :total_heap_size)` | Bound the state; drop old entries |
| `Process.put` leaking per-request data | Check process dictionary usage | Use per-request context maps instead |
| Large number of short-lived processes | `:erlang.system_info(:process_count)` over time | Pool the work (Task.async_stream with max_concurrency) |

**Top-N processes by memory:**

```elixir
:recon.proc_count(:memory, 20)        # Top 20 by memory
:recon.proc_count(:message_queue_len, 20)  # Top 20 by mailbox length
:recon.proc_count(:reductions, 20)    # Top 20 by CPU work
```

**Global memory breakdown:**

```elixir
:erlang.memory()
# [total, processes, processes_used, system, atom, atom_used, binary, code, ets]
```

### 8.3 Mailbox buildup

```
Symptom: a GenServer is falling behind; its mailbox is growing
```

| Cause | Symptom | Fix |
|---|---|---|
| Work per message is too slow | `message_queue_len` growing steadily | Offload heavy work to Task; use `handle_continue` for post-reply work |
| GenServer is the bottleneck for reads | High call rate, reads serialized | Move reads to ETS |
| Sync call blocking the callee | Callee itself blocked on another slow call | Make outer call async via `:noreply` + `GenServer.reply/2` |
| Producer sending faster than consumer processes | Classic PubSub / event-stream overload | Migrate to GenStage / Broadway for backpressure |
| `Process.send_after` flood | Scheduled messages piling up during lag | Coalesce timers; cancel before re-scheduling |

**Investigation:**

```elixir
# Is the mailbox growing over time?
for _ <- 1..5 do
  IO.inspect(Process.info(pid, :message_queue_len))
  Process.sleep(1000)
end

# What kind of messages are piling up?
Process.info(pid, :messages) |> elem(1) |> Enum.take(20)
```

### 8.4 Slow response / timeout

```
Symptom: requests or GenServer.call timing out, or response times high
```

| Likely cause | Investigation | Fix |
|---|---|---|
| N+1 queries | Enable `Ecto.DevLogger`; count queries per request | Batch with `Repo.preload` or explicit query |
| External HTTP call without timeout | Check adapters (`Req`, `Finch`, `HTTPoison`) for `receive_timeout` | Set timeout explicitly |
| GenServer serialization bottleneck | `message_queue_len` growing | ETS for reads; PartitionSupervisor for shards |
| Missing DB index | `EXPLAIN ANALYZE` the slow query | Add index in migration |
| Connection pool exhaustion | `:telemetry` for `[:ecto, :repo, :query]` with `:queue_time` | Increase `pool_size`; reduce per-request queries |
| Slow serialization (JSON, term_to_binary) | Profile at the serialization call site | Stream-encode; use `:erlang.term_to_iovec/1,2` |
| Inner timeout exceeding outer | Check timeout cascade — outer must be > middle > inner | Fix timeouts: endpoint > GenServer.call > HTTP client |

**Measure where the time goes:**

```elixir
# Quick timing of a single call
{microseconds, result} = :timer.tc(fn -> suspected_slow_call() end)

# Statistical view
Benchee.run(%{"candidate" => fn -> suspected_slow_call() end}, warmup: 2, time: 5)

# Per-query visibility
# config/dev.exs:
config :my_app, MyApp.Repo, log: :debug
```

### 8.5 Flaky test

```
Symptom: test passes alone, fails in suite; random failures
```

| Likely cause | Fix |
|---|---|
| Shared global state (named GenServer, Application env, `:ets` table) | Use `start_supervised!` per test; avoid global names; explicitly reset state |
| Race condition: `Process.sleep` before assertion | Replace with `assert_receive pattern, 500` |
| Ecto sandbox: spawned process doesn't have DB access | `Ecto.Adapters.SQL.Sandbox.allow(Repo, self(), spawned_pid)` |
| Wall-clock assertion against `DateTime.utc_now` | `assert_in_delta` with tolerance, or inject a clock module |
| Async mode but test uses named GenServer | Either use `async: false` or use a unique name per test |
| Factory sequence collision | Use `sequence/2` for unique fields |
| Test pollution via `:persistent_term` | Set + `on_exit` to erase, or use a per-test namespace |
| DB migration race in parallel CI | Run migrations serially before parallel tests |

**Find which test flakes:**

```bash
# Run in a repeatable order to isolate
mix test --seed 0 --max-failures 1

# Identify which earlier test pollutes the later one
mix test --trace --seed 12345   # pick a seed that reproduces
```

### 8.6 Dialyzer warnings

```
Symptom: Dialyzer flags contracts, missing callbacks, unreachable patterns, etc.
```

| Warning pattern | Usual cause | Fix |
|---|---|---|
| `Function X has no local return` | Function always raises, no branch returns | Add a return path, or mark with `@spec` returning `no_return()` |
| `Function X will never be called` | Typo in callback name / `@impl` mismatch | Correct name, add `@impl` |
| `The pattern can never match the type` | Redundant clause or wrong `@spec` | Remove dead clause; fix `@spec` |
| `The call … will never return since it differs in arguments from the success typing` | `@spec` mismatched actual behavior | Align `@spec` with implementation |
| `Unmatched return` | Discarded return value from a fallible function | Explicitly match `{:ok, _} = ...` or `_ = ...` |
| Missing `@impl` | Callback not annotated | Add `@impl true` or `@impl BehaviourModule` |

**Dialyzer is slow for first-time PLT build (~10 minutes). After that incremental checks are fast. Run regularly in CI; fix warnings one at a time — do not baseline.**

### 8.7 Dev server won't start / compilation errors

| Symptom | Investigation | Fix |
|---|---|---|
| Module redefined warnings | Two modules defined with same name in different files | Rename one; check generators |
| "module X is not available" | Module not compiled yet or wrong path | Check `lib/` structure, `mix.exs` paths |
| Cyclic dependency | `mix xref graph` | Break cycle — extract shared module to a lower layer |
| `(CompileError) undefined function` | Called a function that doesn't exist | Check spelling; verify `alias` / `import` |
| Circular aliases / imports | Compile error "module X does not exist" despite existing | Reorder; break cycle |
| Phoenix endpoint crashes on start | Missing config, migration, or dependent process | Read the actual crash message; usually the first line is the truth |

### 8.8 Diagnostic escalation ladder

**Always start at step 1. Escalate only if it doesn't reveal the bug.**

1. **`IO.inspect` / `dbg`** — inspect values at suspected points
2. **`IEx.pry`** — pause execution and inspect bindings (`iex -S mix`)
3. **Test reproduction** — write a failing test that isolates the bug
4. **`:sys.trace` / `:sys.get_state`** — OTP process internals
5. **Logger at `:debug` level** — turn up the dials temporarily
6. **`:observer.start()`** — GUI system overview
7. **`:recon.*`** — production-safe process inspection
8. **`:recon_trace.calls/2` with message limit** — production tracing (ALWAYS set a limit)

---

## 9. Profiling Playbook — picking the right tool

> **Depth:** For complete tool-selection decision table, usage templates for each profiler (`:timer.tc`, Benchee, fprof/eprof/cprof/tprof, `:recon`, `:observer`, telemetry), memory analysis recipes, and common profiling traps, load [profiling-playbook-deep.md](profiling-playbook-deep.md).


### 9.1 Which profiler?

| Need | Tool | Overhead | When |
|---|---|---|---|
| Time one expression | `:timer.tc/1` | Negligible | Quick sanity check. Unreliable without warmup |
| Compare two implementations | `Benchee.run/2` | Low | **Default for microbenchmarks.** Warmup, statistics, memory |
| Find the slow function in a call tree | `mix profile.fprof` | **High** | Dev/CI only; not production |
| Aggregate time per function | `mix profile.eprof` | Moderate | Slightly cheaper than fprof; ok for focused profiling |
| Just count calls | `mix profile.cprof` | Low | "What's called most?" |
| Modern unified profiler | `mix profile.tprof` | Low–moderate | OTP 27+; prefer for large codebases |
| Per-request production timing | `:telemetry.span/3` + handler | Very low | Always-on, production-safe |
| System-wide interactive view | `:observer.start()` | Moderate | Dev only; GUI |
| Top-N processes programmatically | `:recon.proc_count(:memory \| :message_queue_len \| :reductions, N)` | Low | Production-safe |
| Find binary memory leaks | `:recon.bin_leak(N)` | Moderate (forces GC) | Periodic in prod |

### 9.2 `Benchee` — the default microbench

```elixir
Benchee.run(
  %{
    "impl_a" => fn -> my_function_a() end,
    "impl_b" => fn -> my_function_b() end
  },
  warmup: 2,               # 2 seconds of warmup per input (BEAM JIT settles)
  time: 5,                 # 5 seconds of measurement per input
  memory_time: 2,          # measure memory too
  inputs: %{                # optional: run each variant across multiple inputs
    "small" => 1..100,
    "large" => 1..10_000
  }
)
```

**Rules:**

- Always `warmup` on OTP 24+ (JIT); 2 seconds is fine for most code
- Use `inputs` when performance depends on input size — catches O(n) vs O(n²)
- Add `memory_time` if memory is suspected; it measures heap allocations
- Benchee results are comparative, not absolute — use the same machine, same load

### 9.3 `mix profile.*` — when

```bash
# Profile a one-off expression (the :do: form)
mix profile.fprof -e 'MyApp.Cold.start()'
mix profile.eprof -e 'MyApp.Search.query("long search string")'

# Profile a test
mix profile.fprof --profile test/my_app/orders_test.exs
```

**Which one?**

- `fprof` — most detailed, shows per-call time with calling context. **Highest overhead**; use in dev/CI to find the slow function.
- `eprof` — aggregate time per function. Lower overhead than fprof.
- `cprof` — just counts calls. Lowest overhead. Use to find "what's called most."
- `tprof` (OTP 27+) — unified interface, lower overhead than fprof. **Prefer this on OTP 27+.**

**Read the output:** Look for the functions with the highest `OWN` (self) time, not `ACC` (accumulated). High `ACC` just means "it called something slow"; high `OWN` means "this function itself is slow."

### 9.4 `:observer` — GUI system view

```elixir
# In IEx (dev)
:observer.start()
# - Applications tab: supervision tree visualization
# - Processes tab: sortable list by memory, reductions, mailbox
# - ETS tab: table sizes
# - Load charts: CPU, memory, IO
```

**Not for production.** Observer is an interactive tool for development. In production, use `:recon` + `:telemetry`.

### 9.5 `:recon` — production-safe

```elixir
# Top processes by memory
:recon.proc_count(:memory, 10)

# Top processes by mailbox length
:recon.proc_count(:message_queue_len, 10)

# Top processes by CPU reductions
:recon.proc_count(:reductions, 10)

# Binary memory leak detection (forces GC, then ranks)
:recon.bin_leak(10)

# Safe tracing with message limit (CRUCIAL in prod)
:recon_trace.calls({MyModule, :my_function, :return_trace}, 100)
# Automatically stops after 100 traces
:recon_trace.clear()
```

**Rule:** `:recon_trace` always sets a message limit. **Never use `:dbg.tp` / `:erlang.trace` in production** — they have no limits and can crash the node under load.

### 9.6 Telemetry — always-on, zero-overhead production measurement

```elixir
# Emit a span around the work
:telemetry.span([:my_app, :orders, :fulfill], %{order_id: order.id}, fn ->
  result = do_fulfill(order)
  {result, %{items: length(order.items)}}
end)

# Handle events and feed them to a metrics store
:telemetry.attach(
  "orders-fulfill",
  [:my_app, :orders, :fulfill, :stop],
  fn _event, %{duration: d}, _meta, _config ->
    :telemetry_metrics.histogram(:orders_fulfill_duration, d)
  end,
  nil
)
```

**Production-grade profiling:** telemetry → metrics backend (Prometheus, StatsD, PromEx). Gives you always-on p50/p95/p99 latency per operation with no overhead.

### 9.7 Memory profiling — specific symptoms

| Symptom | Command | What to look for |
|---|---|---|
| Total memory growing | `:erlang.memory()` over time | Which category (processes/binary/ets) is growing |
| Specific process growing | `:erlang.process_info(pid, [:memory, :total_heap_size, :heap_size])` | Growing heap = accumulating state |
| Binary memory large | `:recon.bin_leak(10)` | Who's holding large binary refs |
| ETS large | `for t <- :ets.all(), do: {t, :ets.info(t, :memory)}` | Sort by size |
| Atom table growing | `:erlang.system_info(:atom_count)` | Unsafe `to_atom`? |

### 9.8 Profiling decision tree

```
Where is the slowness?
├── I don't know → telemetry on request level, find the slow operation
├── Known operation → Benchee to measure, fprof/eprof/tprof to find the hot function
├── One specific function → Benchee with `warmup` + `inputs` at multiple sizes
└── Multiple processes → :observer (dev) or :recon.proc_count (prod)

What's causing memory growth?
├── Don't know which category → :erlang.memory() over time
├── Binaries → :recon.bin_leak/1
├── A specific process → :erlang.process_info(pid, [:memory, :total_heap_size])
├── ETS → :ets.info(table, :memory)
└── Atom table → stop calling String.to_atom/1 on user input
```

---

## 10. Common Elixir Performance Pitfalls

> **Depth:** For the full 32-entry catalog organized by area (data structures, Enum/Stream, OTP, Ecto, memory/binary, serialization, Phoenix, process design), with symptom → root cause → fix → evidence, load [performance-catalog.md](performance-catalog.md).

The top performance issues Claude should flag on sight. Cross-references elixir-implementing §7 where applicable.

### 10.1 String building

```elixir
# BAD — O(n²) due to repeated <> copy
Enum.reduce(rows, "", fn row, acc -> acc <> format(row) <> "\n" end)

# GOOD — IO list, single conversion
rows
|> Enum.map(fn row -> [format(row), "\n"] end)
|> IO.iodata_to_binary()
```

### 10.2 List operations

```elixir
# BAD — O(n) per iteration (length/1 traverses)
for i <- 0..(length(list) - 1), do: Enum.at(list, i)

# GOOD
Enum.with_index(list)

# BAD — repeated ++ appends build O(n²) work
Enum.reduce(items, [], fn item, acc -> acc ++ [item] end)

# GOOD — prepend, then reverse
items
|> Enum.reduce([], fn item, acc -> [item | acc] end)
|> Enum.reverse()
```

### 10.3 Database / N+1

```elixir
# BAD — N+1 query pattern
users = Repo.all(User)
Enum.map(users, fn u -> u.orders end)          # Hits DB for each user

# GOOD — preload
users =
  User
  |> preload(:orders)
  |> Repo.all()

# GOOD — bulk query with join
from(u in User, preload: [:orders]) |> Repo.all()
```

### 10.4 Process bottlenecks

```elixir
# BAD — GenServer.call for every read serializes all readers
def get(key), do: GenServer.call(__MODULE__, {:get, key})

# GOOD — direct ETS read, no serialization
def get(key) do
  case :ets.lookup(:my_cache, key) do
    [{^key, v}] -> {:ok, v}
    [] -> :error
  end
end
```

### 10.5 Configuration on hot paths

```elixir
# BAD — Application.get_env on every call (ETS lookup — fast but not free)
def tick do
  interval = Application.get_env(:my_app, :tick_interval, 1000)
  # ...
end

# GOOD (library) — :persistent_term on hot path
def tick do
  interval = :persistent_term.get({__MODULE__, :tick_interval}, 1000)
  # ...
end

# GOOD (application) — compile_env bakes it in
@tick_interval Application.compile_env!(:my_app, :tick_interval)
def tick, do: do_tick(@tick_interval)
```

### 10.6 Inspect / term operations

```elixir
# BAD — inspect on hot path (slow formatting)
Logger.info("state: #{inspect(state)}")    # inspect runs even if level disabled

# GOOD — lazy, only runs if level enabled
Logger.info(fn -> "state: #{inspect(state)}" end)

# BAD — Jason encode/decode round-trip to copy data
copy = data |> Jason.encode!() |> Jason.decode!()

# GOOD — direct copy (if that's what you need)
copy = data
```

### 10.7 Binary matching / parsing

```elixir
# BAD — building up a binary with <>
parse(<<>>, acc), do: acc
parse(<<byte, rest::binary>>, acc), do: parse(rest, acc <> <<byte>>)   # O(n²)

# GOOD — reverse + binary collect at end, or IO list
parse(<<>>, acc), do: IO.iodata_to_binary(Enum.reverse(acc))
parse(<<byte, rest::binary>>, acc), do: parse(rest, [byte | acc])

# BEST — binary comprehension
for <<byte <- binary>>, into: <<>>, do: process_byte(byte)
```

### 10.8 JSON encoding

```elixir
# BAD — Jason.encode!(%{huge: ...}) in a tight loop
for item <- many_items, do: Jason.encode!(item)

# GOOD — stream if result is to be written
items
|> Stream.map(&Jason.encode!/1)
|> Stream.intersperse("\n")
|> Stream.into(File.stream!("out.jsonl"))
|> Stream.run()
```

### 10.9 Task scheduling

```elixir
# BAD — Task.async + Task.await for unbounded parallelism
tasks = Enum.map(urls, &Task.async(fn -> fetch(&1) end))
Enum.map(tasks, &Task.await/1)

# GOOD — bounded parallelism with Task.async_stream
urls
|> Task.async_stream(&fetch/1, max_concurrency: 10, timeout: 10_000)
|> Enum.map(fn
  {:ok, result} -> result
  {:exit, reason} -> {:error, reason}
end)
```

---

## 11. Suggested Refactor Templates

When flagging a finding, include the refactor. These are the top recurring fixes — copy/adapt them into review comments.

### 11.1 Extract pure function from GenServer

```elixir
# BEFORE
def handle_call({:apply_discount, code}, _from, state) do
  discount =
    case code do
      "SAVE10" -> Decimal.new("0.10")
      "SAVE20" -> Decimal.new("0.20")
      _ -> Decimal.new("0")
    end
  new_total = Decimal.mult(state.total, Decimal.sub(1, discount))
  {:reply, {:ok, new_total}, %{state | total: new_total}}
end

# AFTER — extract a pure module
defmodule MyApp.Pricing do
  def apply_discount(total, code), do: Decimal.mult(total, Decimal.sub(1, rate(code)))
  defp rate("SAVE10"), do: Decimal.new("0.10")
  defp rate("SAVE20"), do: Decimal.new("0.20")
  defp rate(_), do: Decimal.new("0")
end

def handle_call({:apply_discount, code}, _from, state) do
  new_total = MyApp.Pricing.apply_discount(state.total, code)
  {:reply, {:ok, new_total}, %{state | total: new_total}}
end
```

### 11.2 Replace try/rescue with ok/error

```elixir
# BEFORE
def parse(s) do
  try do
    {:ok, String.to_integer(s)}
  rescue
    ArgumentError -> {:error, :invalid}
  end
end

# AFTER
def parse(s) do
  case Integer.parse(s) do
    {int, ""} -> {:ok, int}
    {_, _rest} -> {:error, :trailing}
    :error -> {:error, :invalid}
  end
end
```

### 11.3 Replace nested case with with

```elixir
# BEFORE
case validate_email(params) do
  {:ok, email} ->
    case validate_password(params) do
      {:ok, pw} ->
        case create_user(email, pw) do
          {:ok, user} -> {:ok, user}
          {:error, r} -> {:error, r}
        end
      {:error, r} -> {:error, r}
    end
  {:error, r} -> {:error, r}
end

# AFTER
with {:ok, email} <- validate_email(params),
     {:ok, pw} <- validate_password(params),
     {:ok, user} <- create_user(email, pw) do
  {:ok, user}
end
```

### 11.4 Replace if/else dispatch with multi-clause

```elixir
# BEFORE
def handle(msg) do
  if is_map(msg) and Map.has_key?(msg, :type) do
    if msg.type == :error, do: handle_error(msg), else: handle_ok(msg)
  end
end

# AFTER
def handle(%{type: :error} = msg), do: handle_error(msg)
def handle(%{type: _} = msg), do: handle_ok(msg)
```

### 11.5 Replace single-step pipe into case

```elixir
# BEFORE
Enum.reduce_while(xs, {:ok, []}, fn ... end)
|> case do
  {:ok, acc} -> {:ok, Enum.reverse(acc)}
  {:error, _} = e -> e
end

# AFTER
result =
  Enum.reduce_while(xs, {:ok, []}, fn ... end)

case result do
  {:ok, acc} -> {:ok, Enum.reverse(acc)}
  {:error, _} = e -> e
end
```

### 11.6 Replace context-crossing Repo call

```elixir
# BEFORE — controller calling Repo directly
def index(conn, _) do
  products = Repo.all(Product)
  render(conn, :index, products: products)
end

# AFTER — through context
def index(conn, _) do
  products = MyApp.Catalog.list_products()
  render(conn, :index, products: products)
end
```

### 11.7 Replace spawn with supervised Task

```elixir
# BEFORE
spawn(fn -> send_notification(user) end)

# AFTER
Task.Supervisor.start_child(MyApp.TaskSupervisor, fn ->
  send_notification(user)
end)

# In application.ex:
children = [
  {Task.Supervisor, name: MyApp.TaskSupervisor},
  # ...
]
```

### 11.8 Replace Process.sleep with assert_receive

```elixir
# BEFORE
send(pid, :work)
Process.sleep(100)
assert :done == GenServer.call(pid, :state)

# AFTER
send(pid, :work)
assert_receive {:completed, _}, 500
```

### 11.9 Tighten @spec

```elixir
# BEFORE — vague
@spec fetch(any()) :: any()
def fetch(id), do: ...

# AFTER — specific
@spec fetch(pos_integer()) :: {:ok, User.t()} | {:error, :not_found}
def fetch(id), do: ...
```

---

## 12. Review Comment Style

How to phrase feedback so it's actionable and not annoying.

### 12.1 Good review comment structure

```
[severity] [location] [observation]

[why it matters — 1 sentence]

[suggested fix — code snippet or link]

[link to the skill section for context]
```

### 12.2 Examples

**Bad comment:**
> "This is wrong."

**Good comment:**
> **[request-change]** `lib/my_app/orders.ex:45` — `length(orders) > 0` is O(n); on a large list this scans the whole thing.
> Use pattern-match for O(1): `if match?([_ | _], orders), do: ...`
> (See `elixir-implementing` §7.3.)

**Bad comment:**
> "You should add tests."

**Good comment:**
> **[block]** `register/1` is a new public function without tests. Please add tests covering:
>
> - happy path (valid attrs → `{:ok, user}`)
> - invalid email (→ changeset error)
> - duplicate email (→ constraint error)
> - mailer failure (via `Mox.expect`)

**Bad comment:**
> "Why are you doing it this way?"

**Good comment:**
> **[question]** `lib/my_app/workers/charge.ex:12` — is there a reason this uses `stub` instead of `expect`?
> With `stub`, a test passes even if the function is never called. If the charge MUST happen, `expect` would catch a regression where the call is accidentally removed.

### 12.3 Review-comment rules

1. **Lead with severity** — `[block]`, `[request-change]`, `[suggest]`, `[nit]`, `[question]`. The author reads the tag first.
2. **Say what, not just that it's wrong.** "This is wrong" is worthless; "`length/1` is O(n)" is actionable.
3. **Suggest the fix.** Paste the refactor; don't make the author guess.
4. **Link to the reason.** Pointing at `elixir-implementing` §7.3 or `elixir-planning` §14 tells the author *why* without bloating the PR thread.
5. **Don't pile nitpicks on a junior.** If you have 10 nitpicks, pick 3. Save the rest for a follow-up.
6. **Avoid sarcasm, rhetorical questions, "obviously".** They don't improve the PR; they damage trust.
7. **Praise the good.** A "this is a nice refactor of the error-handling path" costs nothing and keeps reviews from feeling like an interrogation.

### 12.4 When the code is bad but the author can't fix it now

Sometimes a PR introduces a pattern that's wrong, but fixing it properly would grow the PR beyond its scope.

- **Block** if it's a correctness/security bug — scope be damned.
- **Don't block** if it's a pre-existing stylistic issue the PR only touches.
- **Request-change** with "let's file a follow-up issue" for anything in between.
- **File the follow-up yourself** if you care about it happening. Don't leave it to the author.

---

## 13. Related Skills

### Elixir family

- **[elixir-planning](../elixir-planning/SKILL.md)** — architectural decisions (what to build, how to structure). This skill (`elixir-reviewing`) references planning §14 for architectural anti-patterns.
- **[elixir-implementing](../elixir-implementing/SKILL.md)** — writing idiomatic code. This skill cross-references implementing §7 (anti-patterns Claude produces), §8 (daily operations), §9 (OTP).
- **`elixir`** — the original comprehensive Elixir skill with many reference subfiles. See `debugging-profiling.md` for deeper debugging / profiling reference beyond what's here.
- **`elixir-testing`** — deep testing reference (property-based, LiveView, channels, Oban testing, ExVCR, Wallaby). Useful when reviewing tests that go beyond the implementing skill's §4 coverage.

### Claude Code slash commands

- **`/review`** — slash command for general PR review. This skill provides the Elixir-specific domain knowledge; the command provides the workflow frame.
- **`/security-review`** — slash command for security-specific audit. §7.8 is the Elixir-specific security checklist; combine with the broader security-review command.

### Framework / domain

When reviewing code from these domains, load the specialized skill alongside this one:

- **`phoenix`** — Phoenix contexts, controllers, plugs, router, channels.
- **`phoenix-liveview`** — LiveView lifecycle, streams, hooks.
- **`ash`** — Ash Framework resources, policies, actions.
- **`state-machine`** — `gen_statem`, `GenStateMachine`, AshStateMachine.
- **`event-sourcing`** — Commanded aggregates, projections, process managers.
- **`otp`** — deeper OTP patterns (GenStage, Broadway, hot upgrades, distribution).
- **`nerves`** — embedded Elixir / firmware review patterns.
- **`rust-nif`** — Rustler NIF review.
- **`elixir-deployment`** — Mix releases, Docker, Kubernetes observability in deploy-related PRs.

---

**End of SKILL.md.** This skill inspects code that already exists — in review, in debug, or in profile mode. For writing new code idiomatically, load `elixir-implementing`. For designing new systems, load `elixir-planning`. The three skills together cover plan → implement → review as a complete development cycle.
