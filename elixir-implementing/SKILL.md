---
name: elixir-implementing
description: >
  Elixir for idiomatic implementation — the decision tables, templates, and anti-patterns that
  make Claude write functional, idiomatic, best-practices Elixir at the moment of writing. Covers
  the full daily-coding toolkit: pattern matching, pipelines, with/case/cond, Enum/Stream/for,
  multi-clause dispatch, ok/error flow, OTP callback patterns, context boundaries, configuration,
  test-driven development with ExUnit and Mox, and the specific anti-patterns Claude commonly
  produces in Elixir.
  ALWAYS use when writing Elixir code.
  ALWAYS use when deciding between control-flow constructs (if/case/with/multi-clause).
  ALWAYS use when writing GenServer/Task/Agent callbacks or implementing a behaviour.
  ALWAYS use when writing tests or practicing TDD in Elixir.
  ALWAYS use when refactoring Elixir toward idiomatic form.
  For upfront architecture/design work (contexts, supervision shape, project layout) also load
  elixir-planning; this skill defers deep architecture decisions to that skill.
---

# Elixir — Implementing Skill

This skill is optimized for the moment of writing Elixir code. It is one of three Elixir skills:

- **elixir-implementing** (this) — what to type. Rules, decision tables, idiomatic templates, anti-patterns, daily-coding operations.
- **elixir-planning** — what to build before typing. Architectural decisions: contexts, process shape, supervision, project layout.
- **elixir-reviewing** — how to critique existing code. Anti-pattern catalog + review checklist.

The three skills follow the skill-authoring three-modes framework: rules constrain (fire during review), decision tables guide (fire at moment of writing), BAD/GOOD pairs verify (fire during validation). Elixir is implementation-heavy — decision tables carry the most weight in this skill.

### Subskills — deep implementation references

This skill's SKILL.md carries the always-loaded decision tables, top anti-patterns, and core rules. For detail depth on a specific area, load the matching subskill:

| Subskill | Purpose | Load when writing... |
|---|---|---|
| [idioms-reference.md](idioms-reference.md) | Pattern matching (incl. pin operator advanced, `<>` prefix matching, multi-clause default args, assertive matching), guards, `case`/`cond`/`if`, `with` chains, pipelines, `for` comprehensions, captures, IO lists, error handling, **Enum** (common + 30+ functions), **Stream** (custom streams via `Stream.resource`/`transform`, Enum-vs-Stream decision), **advanced reduce** (`map_reduce`, `flat_map_reduce`, `scan`, multi-accumulator), **recursion** (TCO, accumulator-reverse, tree traversal, mutual), **Protocols** (`defprotocol`, `defimpl`, `@derive`, Enumerable/Collectable/Inspect patterns, consolidation), **Behaviours** (`@callback`/`@optional_callbacks`, `@impl`, `use` + `defoverridable`, Mox), **Imperative→Elixir translation** tables | Daily Elixir code — idiomatic control flow, transforms, polymorphism |
| [data-reference.md](data-reference.md) | Maps, structs, keywords, tuples, lists, MapSet, binaries, IO lists — complexity table + call patterns | Anything touching data-structure manipulation |
| [otp-callbacks.md](otp-callbacks.md) | GenServer/Task/Agent/`:gen_statem` callback templates, supervisor child specs, Registry via-tuples, ETS calls, **GenStage/Broadway/Flow templates** | GenServer/Task/supervisor/streaming code |
| [ecto-patterns.md](ecto-patterns.md) | Schemas, changesets, queries, migrations, Multi, custom types, schemaless changesets | Any Ecto code — schema or query |
| [testing-patterns.md](testing-patterns.md) | ExUnit, Mox, sandbox setup, factories, LiveView/Channel/Oban test helpers, property tests | Any test file |
| [type-and-docs.md](type-and-docs.md) | `@spec`, `@type`, `@doc`, `@moduledoc`, doctests, Dialyzer config, built-in types, **`binary`/`String.t`/`iodata` decision**, **closed vs open map types**, **`dynamic()` gradual typing** | Adding types and documentation |
| [networking-patterns.md](networking-patterns.md) | `:gen_tcp`/`:gen_udp` templates, acceptor loops, protocol framing (length-prefix, line, TLV), Ranch/Thousand Island handlers, TLS, HTTP clients | TCP/UDP/HTTP code |
| [code-style.md](code-style.md) | `.formatter.exs` template, Credo check catalog, module organization, function ordering, sigil selection, `defdelegate` decision, readable-code patterns, style BAD/GOOD | Any Elixir code — ensures style-compliant output |
| [production-patterns.md](production-patterns.md) | Production Phoenix patterns (schema base, kit modules, response cache, policy, controller context injection, HTTP SSL fallback, Oban telemetry reporter), NimbleOptions, Mix custom tasks & quality aliases, library authoring conventions | Writing production-ready app code or publishing a library to Hex |

**For architecture-level decisions** (which constructs/processes/contexts to use BEFORE writing code), load `elixir-planning`. **For critique of existing code**, load `elixir-reviewing`.

**How to navigate this skill while coding:**

1. **Starting a feature?** — Read §1 (Rules) and §3 (TDD workflow). Write a failing test before any implementation.
2. **At the keyboard, choosing between constructs?** — Jump to §2 (Master "Which Construct?" table). Find your intent in the left column.
3. **Unsure how to structure a specific pattern?** — §5 has idiomatic templates for the patterns Claude most often gets wrong.
4. **Validating what you wrote?** — Cross-check against §7 (Anti-patterns BAD/GOOD).
5. **Testing *is* part of writing code, not after.** §3 and §4 are core, not optional.

**Final section layout:**

| § | Section | Mode |
|---|---|---|
| 1 | Rules for Writing Elixir | Rules |
| 2 | Master "Which Construct?" Decision Guide | Decision ⭐ |
| 3 | TDD Workflow | Rules + Decision |
| 4 | Testing Essentials | Decision + Templates |
| 5 | Critical Patterns Claude Commonly Gets Wrong | Templates + BAD/GOOD |
| 6 | Idiomatic Elixir Constructs | Decision + Templates |
| 7 | Anti-patterns Claude Commonly Produces | BAD/GOOD ⭐ |
| 8 | Daily Operations — Error, Modules, Naming, Docs | Rules + Templates |
| 9 | OTP Key Decisions | Decision ⭐ |
| 10 | Architecture Key Decisions | Decision |
| 11 | Domain Handoffs to Specialized Skills | Routing |
| 12 | Quick References — Stdlib Cheat Sheets | Lookup |
| 13 | Related Skills | Navigation |

---

## 1. Rules for Writing Elixir (LLM)

1. **ALWAYS write the test first** — red → green → refactor. A feature without a test is incomplete. See §3.
2. **ALWAYS reach for the decision table** (§2) when choosing between `if`, `case`, `cond`, `with`, and multi-clause functions. Structural dispatch = multi-clause; 2+ chained ok/error ops = `with`; boolean side-effect with no value = `if`; every common choice has a table row.
3. **NEVER use `if`/`else` for structural dispatch.** Multi-clause functions with pattern matching handle shape/type branching. `if` is only for a simple boolean guard with no value-returning else branch.
4. **NEVER use `try`/`rescue` for expected failures.** Return `{:ok, _}` / `{:error, _}` tuples and match them. Reserve `rescue` for genuine exceptional cases at system boundaries. For calling processes you don't own, prefer `catch :exit`.
5. **ALWAYS use `with` to chain 2+ `{:ok, _}` / `{:error, _}` operations.** Do not nest `case` statements. For a single operation, `case` is correct.
6. **NEVER write imperative loops.** There are no `for`/`while` loops with mutable state in Elixir. Use `Enum.map` / `filter` / `reduce`, `for` comprehensions, or tail recursion.
7. **NEVER rebind inside `Enum.each` to accumulate** — rebinding does not escape the anonymous function. Use `Enum.map` / `Enum.reduce` to collect results.
8. **ALWAYS design functions for pipe-ability.** Data first; return transformed data; mutation APIs return the subject so callers can chain.
9. **NEVER pipe a single step.** `name |> String.upcase()` → `String.upcase(name)`. Pipelines exist for 2+ transformations.
10. **NEVER end a pipeline with `|> case do`** if the pipeline is a single step. Assign the result to an intermediate variable, then `case` on it. Pipe-to-case is only idiomatic at the end of a genuinely multi-step pipeline.
11. **ALWAYS prefer pattern matching in function heads** over `case` in the body when dispatching on argument shape or type.
12. **ALWAYS use guard clauses** to constrain function heads rather than validating inside the body.
13. **ALWAYS build strings with IO lists** (`[a, ", ", b]`) or interpolation (`"#{a}, #{b}"`), never by repeated `<>` concatenation in a loop (that's O(n²)).
14. **ALWAYS use `@spec` on every public function** and `@doc` / `@moduledoc` describing purpose — use `@doc false` / `@moduledoc false` for intentionally undocumented internals.
15. **ALWAYS put business logic in pure functions.** GenServer callbacks delegate to pure functions and only handle process mechanics.
16. **ALWAYS supervise long-running processes.** Never `spawn` / `spawn_link` for work that outlives its caller — use a Task.Supervisor, DynamicSupervisor, or permanent child under your app supervisor.
17. **ALWAYS choose the narrowest OTP construct.** Preference order: pure function → struct module → Task → Agent → GenServer → gen_statem. Don't reach for GenServer when a pure function suffices. See §10.
18. **ALWAYS go through context modules.** Controllers, LiveViews, CLI commands, GenServer callbacks, and scripts never call `Repo` directly — they call `Accounts.register_user/1`, `Catalog.get_product!/1`, etc.
19. **ALWAYS use `@impl true`** on every behaviour callback implementation. It catches typos and missing callbacks at compile time.
20. **ALWAYS use `%{struct | key: val}`** for struct updates, not `Map.put(struct, key, value)`. The update syntax raises on unknown keys, catching typos at compile time.
21. **ALWAYS use the latest stable dependency versions** and follow the library's recommended `mix.exs` setup. Don't hand-craft configurations that would break the standard installation flow.
22. **ALWAYS run `mix format`, `mix credo --strict`, and the test suite** before declaring a change done. Fix warnings; do not suppress them.

---

## 2. Master "Which Construct?" Decision Guide

This is the single most important section to consult at the moment of writing. Each row maps an **intent** (what you're trying to do) to the idiomatic construct and the common anti-pattern to avoid. Read left-to-right when you're about to type code: "I need to X" → use Y, not Z.

### 2.1 Control flow

| When you need to... | Use this | NOT this |
|---|---|---|
| Branch on the *shape* of data (struct type, tuple tag, map keys) | Multi-clause function with pattern in head | `if is_struct(x, Mod)` / `case ... do` |
| Branch on **membership** in a compile-time list/set | Multi-clause with `when x in @list` guard + catch-all | `if x in @list, do: yes(), else: no()` |
| Branch on a **computed value** (size, length, type check) | Multi-clause with guard on the computation | `case byte_size(v) do n when ... -> ... end` |
| Chain 2+ `{:ok, _}` / `{:error, _}` operations | `with ... do ... else ... end` | Nested `case`, nested `if` |
| Handle a single ok/error result | `case ... do` | `with` with one clause, `if` |
| Boolean side-effect, no value returned | `if cond, do: side_effect()` | `case bool do true -> ...; false -> ... end` |
| Boolean branch, both paths return values | `case bool do true -> ...; false -> ... end` | `if/else` (truthy, not strict) |
| Multiple boolean conditions (else-if chain) | `cond do ... end` | Nested `if/else` |
| Dispatch on value range / thresholds | `cond do` or multi-clause with guards | `if a < x, do: ...; if x < b, do: ...` |
| Early-exit from a reducer | `Enum.reduce_while/3` with `{:cont, acc}` / `{:halt, acc}` | `Enum.reduce` with `throw`/`catch` |
| Lookup-then-act with fallback | Multi-clause function or `case Map.fetch/2` | `map[:key] != nil` check |
| Check for `nil` | Multi-clause on the value, or `case` on `Map.fetch/2` | `if x == nil` / `if is_nil(x)` |
| Dispatch on one field of a large struct | Pattern-match just that field, or guard `struct.field` | Destructure whole struct in head |
| Execute a block conditionally in a pipeline | `then(&if/1)` or a `maybe_X/N` helper | Break the pipeline with `case` |
| Exit early on first error in a pipeline | `with` chain | `Enum.reduce_while` + `case` on result |

### 2.2 Collection operations

| When you need to... | Use this | NOT this |
|---|---|---|
| Transform each element | `Enum.map/2` with function capture `&fun/1` | `Enum.map(xs, fn x -> fun(x) end)` |
| Filter a list by predicate | `Enum.filter/2` | `Enum.reduce` that conditionally conses |
| Filter AND transform in one pass | `for x <- xs, pred.(x), do: transform(x)` | `xs \|> Enum.filter(pred) \|> Enum.map(t)` |
| Reduce to single value | `Enum.reduce/3` | manual recursion |
| Build a map from an enumerable | `Map.new/2` or `for x <- xs, into: %{}, do: {k, v}` | `Enum.reduce(xs, %{}, fn ... end)` |
| Build a MapSet | `MapSet.new/1,2` or `for ..., into: MapSet.new()` | `Enum.reduce` into a list then dedupe |
| Build a concatenated binary | IO list + `IO.iodata_to_binary/1`, or `Enum.map_join/3` | `Enum.reduce(..., "", &<>/2)` — O(n²) |
| Early-exit accumulation | `Enum.reduce_while/3` | `throw`/`catch`, flag variable |
| Iterate with index | `Enum.with_index/1,2` | `for i <- 0..length(xs)-1` |
| Process items in parallel (side effects) | `Task.async_stream/3,5` with `ordered: false` | `Enum.map(&Task.async/1) \|> Enum.map(&Task.await/1)` |
| Dedupe by key | `Enum.uniq_by/2` | `MapSet` + manual loop |
| Partition by predicate | `Enum.split_with/2` | Two `Enum.filter` passes |
| Group by derived key | `Enum.group_by/2,3` | `Enum.reduce` into `Map.update` |
| Chunk into batches | `Enum.chunk_every/2,4` | manual recursion |
| Count by frequency | `Enum.frequencies/1` / `Enum.frequencies_by/2` | `Enum.group_by` + `map_size` per bucket |
| Process large/infinite data lazily | `Stream.*` + one `Enum.*` at the end | `Enum.*` on full collection |
| Pattern-match while iterating (silent skip on mismatch) | `for {:ok, v} <- results, do: v` | `Enum.filter(...) \|> Enum.map(...)` |

### 2.3 Pattern matching and dispatch

| When you need to... | Use this | NOT this |
|---|---|---|
| Extract a field from a struct | Pattern match: `def f(%User{name: name} = u)` | `u.name` (fine for access, not for asserting presence) |
| Assert a map key exists | Match: `%{key: v} = map` or in head | `Map.get(map, :key) \|\| raise` |
| Match against an existing variable | Pin: `case x do ^expected -> ...` | Bare name (rebinds!) |
| Check non-empty list | `match?([_ \| _], xs)` or pattern in head | `length(xs) > 0` (O(n)) |
| Check empty map | `map == %{}` or `map_size(map) == 0` | `%{} = map` (matches ANY map) |
| Match JSON / params (string keys) | `%{"key" => v} = params` | `%{key: v}` — atom ≠ string |
| Match internal data (atom keys) | `%{key: v} = internal_map` | `%{"key" => v}` |
| Constrain by type / range in a head | Guard clause: `when is_integer(n) and n > 0` | Body `if` + validation |
| Match against a `0` or `nil` base case | Separate clause: `def f(0)`, `def f(nil)` | Body `if x == 0` |

### 2.4 Error handling

| Situation | Use |
|---|---|
| Can you check the condition BEFORE the call? | Check first (`Process.whereis/1`, `Map.fetch/2`) |
| Calling a process you don't own? | `try ... catch :exit, _` at the boundary |
| Input from untrusted / external source? | `rescue` specific exception at the boundary (e.g. `:erlang.binary_to_term` on network bytes) |
| Error is an expected business case? | Return `{:ok, _}` / `{:error, _}` from the function |
| Everything else? | Let it crash — the supervisor handles it |

| When you need to... | Use this | NOT this |
|---|---|---|
| Return success + data | `{:ok, value}` | `value` (can't distinguish from nil / :ok) |
| Return failure with a reason | `{:error, reason}` (atom or struct) | `nil`, raise, boolean false |
| Side-effect success (no data) | `:ok` | `{:ok, nil}` |
| Fail-fast on wrong input in a script | Bang variant (`File.read!/1`) | `case` + raise |
| Offer both strict and lenient API | Pair: `fetch/1` (ok/error) + `fetch!/1` (raises) | Only bang, or only non-bang |
| Wrap an external library that raises | `try/rescue` at the adapter boundary, convert to ok/error | Let exceptions leak out of your context |
| Propagate unknown errors | Let them crash; supervisor restarts | Catch-all `rescue _` |

### 2.5 Strings and binaries

| When you need to... | Use this | NOT this |
|---|---|---|
| Build a string from parts | Interpolation `"#{a} and #{b}"` | `a <> " and " <> b` |
| Build a string in a loop | IO list + `IO.iodata_to_binary/1` | `Enum.reduce(xs, "", &<>/2)` |
| Join list into string with separator | `Enum.join(xs, ", ")` or `Enum.map_join/3` | `Enum.reduce` with `<>` |
| Parse a known binary layout | Binary pattern matching `<<a::8, b::16, rest::binary>>` | `String.split` on byte boundaries |
| Convert integer to string | `Integer.to_string/1,2` | `"#{n}"` (allocates, slower) |
| Convert to atom from user input | `String.to_existing_atom/1` | `String.to_atom/1` (exhausts atom table) |
| Coerce unknown-type value for display | `inspect/1` | `to_string/1` (raises for some types) |
| Compare case-insensitively | `String.downcase/1` both sides | manual `String.equivalent?` check |

### 2.6 Data updates

| When you need to... | Use this | NOT this |
|---|---|---|
| Update an existing struct field | `%{struct \| field: value}` | `Map.put(struct, :field, value)` |
| Update an existing map key (known present) | `%{map \| key: value}` | `Map.put(map, :key, value)` |
| Set / create a map key (maybe absent) | `Map.put(map, key, value)` | `%{map \| key: value}` (raises if absent) |
| Update a nested field | `put_in(data, [path], value)` or `update_in/3` | Manual get-modify-put chain |
| Increment a counter in a map | `Map.update(map, :k, 1, & &1 + 1)` | Get + 1 + Put |
| Merge two maps (right wins) | `Map.merge/2` | `Enum.reduce(other, map, & Map.put(&2, ...))` |
| Merge with custom conflict resolution | `Map.merge/3` | Manual reduce |
| Delete a key | `Map.delete/2` | `Map.drop(map, [key])` for one key |
| Check key presence (nil is a valid value) | `Map.has_key?/2` or `Map.fetch/2` | `map[:key] != nil` |

### 2.7 Function design

| When you need to... | Use this | NOT this |
|---|---|---|
| Expose a function unchanged from another module | `defdelegate name(args), to: Other` | `def name(args), do: Other.name(args)` |
| Accept optional config | Keyword list last arg + `Keyword.validate!/2` | Multiple overloads with many args |
| Provide a default for an arg | `def f(x, opts \\ [])` | Multiple clauses setting defaults |
| Return transformed data in a pipeline | First arg = data, return new data | Mutation-style (non-existent in Elixir) |
| Chain mutation-like configuration | Return the subject: `mock \|> expect(...) \|> allow(...)` | Separate `config_X` / `config_Y` calls |
| Implement a callback from a behaviour | Mark with `@impl true` above the function | Bare `def` (loses compile-time check) |
| Disambiguate multiple behaviours | `@impl SomeBehaviour` | `@impl true` when ambiguous |

### 2.8 Module boundaries

| When you need to... | Use this | NOT this |
|---|---|---|
| Expose domain API from a context | `def` with `@doc` + `@spec` | Thin wrappers that forward to internal modules unchanged |
| Hide an internal helper | `defp` | `def` + `@doc false` (still callable) |
| Swap implementations (test/prod) | `@callback` behaviour + `Application.compile_env` | `if Mix.env() == :test` |
| Provide data-level polymorphism | Protocol (`defprotocol` + `defimpl`) | Giant `case` on struct type |
| Reuse a default implementation | `use Module` with `defoverridable` | Copy-paste |
| Share constants across modules | Module with `defmacro` or `def` returning value | Global mutable state |

### 2.9 Process and concurrency

| When you need to... | Use this | NOT this |
|---|---|---|
| Fire-and-forget async side effect | `Task.Supervisor.start_child/2` | `spawn/1` (unsupervised) |
| Await parallel results | `Task.async_stream/3,5` | Manual `Task.async` + `Task.await` list |
| Long-running stateful worker | GenServer | Infinite-loop `spawn` |
| Shared read-heavy state (no single writer bottleneck) | ETS (`:public`, `read_concurrency: true`) | GenServer.call for every read |
| Cross-process counter | `:counters` / `:atomics` | GenServer.call for `+1` |
| Rarely-changing global config | `:persistent_term` | `Application.get_env` on hot path |
| Serialize access to an external resource | GenServer (one writer) | Multiple processes racing to the resource |
| Explicit state machine with transitions | `:gen_statem` | GenServer with large `case` on state |
| Supervise dynamically created workers | DynamicSupervisor + Registry | Named GenServers per entity |
| Scheduled / periodic work | `Process.send_after` loop, or Oban for persistence | `:timer.sleep` in a loop |
| Pub/sub within a node | Registry with `:duplicate` keys, or `Phoenix.PubSub` | `Process.send` to a list of pids you maintain |
| Backpressured pipeline | GenStage / Broadway | Manual message passing |
| Optional call to a maybe-missing process | `GenServer.whereis/1` + `try ... catch :exit` | `GenServer.call` without guard |

### 2.10 Pipelines

| When you need to... | Use this | NOT this |
|---|---|---|
| Apply 2+ transformations | Pipeline: `data \|> step1() \|> step2()` | `step2(step1(data))` (less readable for chains) |
| Apply exactly 1 function | Direct call: `String.upcase(name)` | `name \|> String.upcase()` |
| Branch at the end of a pipeline (multi-step) | Pipe into `case`: `... \|> case do ...` | Assign to var, then `case` |
| Branch after a single call | Assign to `result`, then `case` | `single_call() \|> case do` (single-step pipe) |
| Optionally apply a step | `maybe_X/2` helper: multi-clause with `true`/`false` arg | `if` inside the pipeline |
| Inspect without changing value | `tap(&IO.inspect/1)` | Assign to var, inspect, reuse |
| Transform for a single non-pipable step | `then/2`: `data \|> then(&some_fn.(&1, extra))` | Break pipeline, assign, call, re-enter |
| Log / emit telemetry mid-pipeline | `tap(&Logger.info/1)` | Pipeline break |

### 2.11 Testing

| When you need to... | Use this | NOT this |
|---|---|---|
| Test a pure function | ExUnit `test` with input → expected output | Setup `start_supervised!` when not needed |
| Test the happy path | `assert {:ok, value} = function(...)` | `assert function(...) == {:ok, ...}` (worse failure messages) |
| Test an error case | `assert {:error, _} = function(bad)` | `assert_raise` unless the function really raises |
| Test a changeset error | `errors_on/1` helper: `%{field: ["msg"]} = errors_on(cs)` | Dig into `cs.errors` manually |
| Mock an external service | Define `@callback` → `Mox.defmock` → `expect` | Monkey-patch module, redefine at runtime |
| Isolate DB writes per test | `Ecto.Adapters.SQL.Sandbox` with `async: true` | Truncate tables between tests |
| Test a GenServer | Test the client API (`MyServer.call/1`) against a `start_supervised!` instance | Call `handle_call` directly |
| Wait for an async message | `assert_receive pattern, 500` | `Process.sleep(500) && assert ...` |
| Use fresh data per test | Factory (`insert(:user)`) | Fixture module with shared instances |
| Property test invariants | `StreamData` with `check all` | Hand-generate edge cases |
| Assert function shouldn't be called | `refute_called` equivalent: `Mox.expect` N=0 | Omit and hope |

---

## 3. TDD Workflow — Red / Green / Refactor

Testing is not a phase that happens after writing code. It is the loop you code inside. Every change to behavior is driven by a failing test.

### 3.1 The core cycle

1. **RED** — Write a failing test that describes the behavior you want. Run it. Confirm the failure message matches your expectation (if the test passes immediately, the test is wrong or the behavior already exists).
2. **GREEN** — Write the *minimum* code that makes the test pass. Do not gold-plate. Resist the urge to handle edge cases that aren't in a test yet — write those tests first.
3. **REFACTOR** — With tests green, improve the code: extract helpers, rename, remove duplication, tighten types. Re-run tests after each structural change.
4. **Go back to RED** for the next behavior.

### 3.2 Canonical TDD example

```elixir
# STEP 1 — RED: Write the test first (MyApp.Pricing does not yet exist)
defmodule MyApp.PricingTest do
  use ExUnit.Case, async: true

  describe "discount/2" do
    test "applies a percentage discount" do
      assert MyApp.Pricing.discount(100_00, 0.10) == 90_00
    end

    test "clamps the discount to the item price (never negative)" do
      assert MyApp.Pricing.discount(50_00, 1.50) == 0
    end

    test "returns price unchanged for a zero discount" do
      assert MyApp.Pricing.discount(75_00, 0.0) == 75_00
    end
  end
end
# Run: mix test test/my_app/pricing_test.exs — ALL THREE FAIL (module undefined)

# STEP 2 — GREEN: Minimum implementation
defmodule MyApp.Pricing do
  @spec discount(non_neg_integer(), float()) :: non_neg_integer()
  def discount(price_cents, rate) when rate >= 0 do
    max(0, price_cents - round(price_cents * rate))
  end
end
# Run again — three tests pass.

# STEP 3 — REFACTOR: No duplication yet, spec is correct, naming clear.
# Nothing to clean up. Move on to the next test case.
```

### 3.3 Decision: write tests first or after?

| Write tests FIRST | Write tests AFTER | Skip tests |
|---|---|---|
| New public API function | UI / LiveView layout changes | One-off scripts with no reuse |
| Bug fix (reproduce bug as failing test first) | HEEx template tweaks | Exploratory prototyping / spikes |
| Business logic with rules and edge cases | Performance optimization (benchmark instead) | Temporary debug output |
| Refactor (write characterization tests of current behavior first) | Pure visual CSS changes | Throwaway migrations to data format |
| Any changeset validation | | |
| Any multi-step `with` chain | | |
| Any function that crosses a context boundary | | |

**Default:** tests first. The cost of "write test after" is usually missing edge cases; the cost of "write test first" is about 20 seconds of extra typing.

### 3.4 Outside-in TDD

Start from the public context API; let the test failures guide you inward into the private helpers.

```elixir
# 1. Write a context-level test FIRST (mock external boundaries with Mox)
test "register/1 creates user, sends welcome email, emits :user_registered event" do
  Mox.expect(MyApp.Mailer.Mock, :send_welcome, fn %User{email: "a@b.com"} -> :ok end)

  assert {:ok, %User{email: "a@b.com"}} =
           Accounts.register(%{email: "a@b.com", password: "secret-pw-123"})

  assert_receive {:user_registered, %User{email: "a@b.com"}}
end

# 2. This test tells you the shape of Accounts.register/1 — its inputs, outputs, side effects
# 3. Implement register/1 as a context function. It probably uses:
#    - a changeset (write the changeset function → covered by changeset tests)
#    - Repo.insert (not mocked — uses DB via sandbox)
#    - the mailer behaviour (mocked)
#    - PubSub / Phoenix.PubSub.broadcast (may or may not be mocked)
# 4. Write unit tests for any extracted helpers as you go — each helper gets its own red/green cycle
```

### 3.5 Property-based TDD

For invariant-driven code, define the invariant *before* the implementation.

```elixir
use ExUnitProperties

# Invariant 1: encoding is reversible
property "encode then decode is the identity" do
  check all value <- term() do
    assert value == value |> MyCodec.encode() |> MyCodec.decode() |> elem(1)
  end
end

# Invariant 2: sort preserves length and orders ascending
property "sort output is always ordered and same length as input" do
  check all list <- list_of(integer()) do
    sorted = MySort.sort(list)
    assert length(sorted) == length(list)
    assert sorted == Enum.sort(list)
  end
end
```

Properties are particularly strong for: parsers, serializers, compression, sorting, set operations, anything with an obvious mathematical inverse or invariant.

### 3.6 Bug-fix TDD

The strongest form of TDD: reproduce every bug as a failing test *before* fixing it.

```
1. User reports: "deleting a user with orphan posts crashes."
2. Write a test that creates a user, creates posts, deletes the user, and asserts the expected behavior (e.g., {:error, :has_orphans} or cascade delete).
3. Confirm the test fails with the actual bug (MatchError / FunctionClauseError / etc.).
4. Fix the code. Test goes green.
5. Commit: both the bug-reproducing test AND the fix. The test prevents regression.
```

### 3.7 Fast feedback loops while iterating

```bash
# Run only the test you're writing — 50ms feedback
mix test test/my_app/pricing_test.exs:18

# Re-run only the tests that failed last run
mix test --failed

# Only tests affected by recent changes
mix test --stale

# Stop at first failure — keeps output readable
mix test --max-failures 1

# Continuous re-run on file changes (requires {:mix_test_watch, "~> 1.2", only: :dev})
mix test.watch
```

### 3.8 TDD anti-patterns (BAD/GOOD)

```elixir
# BAD — Testing implementation details (brittle, breaks on refactor)
test "Accounts.register calls Repo.insert" do
  # Asserting the internal function sequence. Refactoring breaks this
  # test even when the behavior is unchanged.
end

# GOOD — Test the observable behavior
test "Accounts.register persists the user and returns {:ok, user}" do
  assert {:ok, %User{id: id}} = Accounts.register(@valid_attrs)
  assert Repo.get(User, id)
end
```

```elixir
# BAD — Writing the implementation first, then reverse-engineering tests.
# Tests become tautological: they assert exactly what the code does, not what it should do.
def calculate_total(cart), do: Enum.sum(Enum.map(cart.items, & &1.price))
test "calculate_total returns Enum.sum(Enum.map(cart.items, & &1.price))" do
  # Rubber stamp. Catches nothing.
end

# GOOD — Test describes WHAT should happen; implementation describes HOW.
test "calculate_total sums item prices" do
  cart = %Cart{items: [%Item{price: 100}, %Item{price: 250}]}
  assert calculate_total(cart) == 350
end
test "calculate_total is zero for an empty cart" do
  assert calculate_total(%Cart{items: []}) == 0
end
```

```elixir
# BAD — Mocking what you don't own (internal modules), so mocks lie
Mox.defmock(MyApp.Pricing.Mock, for: MyApp.Pricing)  # You own Pricing — test it directly!

# GOOD — Mock only at system boundaries (external APIs, databases via sandbox, mailers, payment gateways)
Mox.defmock(MyApp.Mailer.Mock, for: MyApp.Mailer)   # Good: mailer crosses the process + network boundary
```

```elixir
# BAD — One test asserting five unrelated things (fails cascade, hard to diagnose)
test "user flow" do
  # create user, send email, update profile, delete, verify audit log
end

# GOOD — Small focused tests, one behavior each
describe "register/1" do
  test "creates a user with hashed password" do ... end
  test "sends a welcome email" do ... end
  test "emits a :user_registered event" do ... end
end
```

### 3.9 TDD rules (LLM)

1. **ALWAYS run the test before implementing** — confirm red is red for the *right reason*.
2. **ALWAYS write the minimum** to go green. Write the next test before generalizing.
3. **NEVER test private functions directly** — test via the public API. If the private is complex enough to test independently, it belongs in its own module.
4. **NEVER assert implementation details** (which internal function was called, in what order). Assert observable behavior.
5. **ALWAYS reproduce every bug as a failing test** before fixing. The test is the regression guard.
6. **PREFER many small `describe` blocks** over long flat test modules. Group by function-under-test.
7. **PREFER `async: true`** on every test module that does not touch shared global state (named GenServers, global application env, `:global` registrations). Ecto sandbox is async-safe.

---

## 4. Testing Essentials

This section gives you everything you need for daily testing. For deep LiveView / channel testing, property-testing generators beyond the basics, ExVCR, or Wallaby browser tests, load `elixir-testing`.

> **Depth:** For complete ExUnit/Mox/sandbox/factory templates + LiveView/Channel/Oban helpers, load [testing-patterns.md](testing-patterns.md). For test strategy (pyramid, mock boundaries), load `../elixir-planning/test-strategy.md`.

### 4.1 Test case templates — pick the right one

| Template | When to use | async safe? |
|---|---|---|
| `ExUnit.Case` | Pure unit tests (no DB, no Phoenix) | Yes |
| `MyApp.DataCase` | Anything that hits the database via Repo | Yes (with Sandbox) |
| `MyAppWeb.ConnCase` | Controller, plug, JSON API tests | Yes (with Sandbox) |
| `MyAppWeb.ChannelCase` | Phoenix channel tests | Yes |
| `MyAppWeb.LiveViewCase` (or reuse ConnCase) | LiveView tests | Yes |

```elixir
defmodule MyApp.AccountsTest do
  use MyApp.DataCase, async: true   # <-- DB-backed, parallel-safe

  import MyApp.Factory                # ExMachina factories
  alias MyApp.Accounts

  describe "register/1" do
    # tests here
  end
end
```

### 4.2 Which assertion? — decision table

| When you need to... | Use this | NOT this |
|---|---|---|
| Assert function returned success + shape | `assert {:ok, %User{id: id}} = fun(...)` | `assert match?({:ok, %User{}}, fun(...))` (no diff on failure) |
| Assert specific equality | `assert x == y` | `assert x === y` unless you need strict `1 !== 1.0` |
| Assert value is truthy / falsy | `assert value` / `refute value` | `assert value == true` |
| Assert substring or regex match | `assert x =~ "substr"` / `assert x =~ ~r/pat/` | `assert String.contains?(x, "substr")` |
| Assert membership | `assert x in [:a, :b]` or `assert x in 1..10` | `assert Enum.member?([...], x)` |
| Assert float equality | `assert_in_delta 0.1 + 0.2, 0.3, 1.0e-6` | `assert 0.1 + 0.2 == 0.3` (false!) |
| Assert function raises | `assert_raise ArgumentError, fn -> parse!("bad") end` | `try/rescue` in the test |
| Assert a message arrived | `assert_receive {:event, _}, 500` | `Process.sleep(500)` then check mailbox |
| Assert a message did NOT arrive | `refute_receive :x, 100` | Inspect mailbox manually |
| Assert a log line was produced | `assert capture_log(fn -> ... end) =~ "msg"` | Check Logger state |
| Assert changeset error message | `assert %{field: ["msg"]} = errors_on(cs)` | Dig into `cs.errors` manually |
| Explicit unreachable branch | `flunk("should not happen")` | `assert false` |

**Why pattern-match assertions win:**

```elixir
# GOOD — pattern match extracts and asserts shape, best failure messages
assert {:ok, %User{id: id, email: "a@b.com"}} = Accounts.create_user(valid_attrs)
# Now `id` is bound for use below

# OK but worse failures
assert match?({:ok, %User{email: "a@b.com"}}, Accounts.create_user(valid_attrs))

# BAD — stringified inspect, no structural diff
assert inspect(result) == "{:ok, %User{email: \"a@b.com\"}}"
```

### 4.3 Setup patterns

```elixir
# Basic — return a context map merged into each test's context
setup do
  %{user: insert(:user), product: insert(:product)}
end

test "ships order", %{user: user, product: product} do
  # use user, product
end

# Named setup functions (shared across describes)
setup [:create_user, :verify_on_exit!]

defp create_user(_context), do: %{user: insert(:user)}

# Setup with @tag access
setup tags do
  if tags[:admin] do
    %{user: insert(:admin)}
  else
    %{user: insert(:user)}
  end
end

@tag :admin
test "admin can delete", %{user: user} do ... end

# start_supervised! — process is auto-stopped when the test ends
setup do
  pid = start_supervised!({MyWorker, initial_state: []})
  %{worker: pid}
end

# setup_all — runs ONCE per module, not per test (use sparingly — breaks async isolation)
setup_all do
  start_supervised!({Phoenix.PubSub, name: TestPubSub})
  %{pubsub: TestPubSub}
end

# on_exit — cleanup hook, runs after each test even on failure
setup context do
  :telemetry.attach("#{context.test}", @events, &handler/4, nil)
  on_exit(fn -> :telemetry.detach("#{context.test}") end)
  :ok
end

# Temp directory — ExUnit creates and cleans up
@tag :tmp_dir
test "writes a file", %{tmp_dir: tmp_dir} do
  File.write!(Path.join(tmp_dir, "test.txt"), "hello")
end
```

### 4.4 Mox — mocking system boundaries

**Mox is the official, Dialyzer-safe, async-safe mocking library. Always use Mox; never `:meck`, never monkey-patch, never redefine modules at runtime.**

**What should (and shouldn't) be mocked:**

| Boundary type | Mock? | Example |
|---|---|---|
| External network service | Yes | HTTP client, payment gateway, S3, SendGrid |
| OS process / port (email, push notification) | Yes | Mailer, FCM / APNS sender |
| Non-determinism you don't control | Yes | Clock, random, UUID generator |
| Your own domain modules (Accounts, Pricing, Orders) | **No** | Test directly — mocking your own code makes tests lie |
| Database via `Repo` | **No** | Use `Ecto.Adapters.SQL.Sandbox` (real DB, isolated) |
| Phoenix.PubSub | **No** | Use real PubSub in tests — it's fast and deterministic |
| Private helpers inside the same module | **No** | Test via the public API |

**Which Mox API? — decision table:**

| When you need to... | Use this | NOT this |
|---|---|---|
| Assert a function WAS called, verify call count and args | `expect(Mock, :fn, fn args -> ret end)` | `stub` (no verification) |
| Assert a function was called exactly N times | `expect(Mock, :fn, N, fn args -> ret end)` | `expect` + counting |
| Allow any number of calls (incl. zero), no verification | `stub(Mock, :fn, fn args -> ret end)` | `expect` for "maybe called" |
| Stub all callbacks of a behaviour from a real impl | `stub_with(Mock, RealImplementation)` | Many individual `stub/3` calls |
| Assert a function must NOT be called | `expect(Mock, :fn, 0, fn _ -> flunk("...") end)` | Just omit (no guarantee) |
| Let a spawned process use the current test's mocks | `allow(Mock, self(), pid)` | `set_mox_global()` if you can avoid it |
| Lazy pid resolution (process started later) | `allow(Mock, self(), fn -> GenServer.whereis(Name) end)` | Eager pid lookup |
| Run tests that spawn processes across multiple testers | `set_mox_global()` — requires `async: false` | Trying to chase pids with `allow/3` |

**Canonical Mox setup (the whole pattern in one example):**

```elixir
# 1. Behaviour — the contract
defmodule MyApp.Mailer do
  @callback send_welcome(User.t()) :: :ok | {:error, term()}
end

# 2. Real impl (behind a behaviour)
defmodule MyApp.Mailer.Swoosh do
  @behaviour MyApp.Mailer
  @impl true
  def send_welcome(user), do: # ... SMTP ...
end

# 3. test_helper.exs
Mox.defmock(MyApp.Mailer.Mock, for: MyApp.Mailer)

# 4. config/test.exs
config :my_app, :mailer, MyApp.Mailer.Mock

# 5. Dispatcher (runtime lookup — important for library-style code)
defmodule MyApp.MailerDispatcher do
  defp impl, do: Application.get_env(:my_app, :mailer, MyApp.Mailer.Swoosh)
  def send_welcome(user), do: impl().send_welcome(user)
end

# 6. In the test
import Mox
setup :verify_on_exit!        # ALWAYS — fails the test if expectations unmet

test "register sends welcome email" do
  expect(MyApp.Mailer.Mock, :send_welcome, fn %User{email: "a@b.com"} -> :ok end)
  assert {:ok, %User{}} = Accounts.register(%{email: "a@b.com", password: "pw"})
end
```

**Async mode — decision table:**

| Test scenario | Mox mode | `async:` |
|---|---|---|
| Single process uses the mock (most tests) | `set_mox_private()` (default) | `true` |
| Spawned process needs same expectations | `set_mox_private()` + `allow/3` | `true` |
| Many processes (can't track them all) | `set_mox_global()` | `false` |
| Auto-pick based on test tag | `set_mox_from_context()` in setup | either |

### 4.5 Ecto Sandbox — database isolation

```elixir
# test_helper.exs (typical Phoenix app already has this)
Ecto.Adapters.SQL.Sandbox.mode(MyApp.Repo, :manual)

# DataCase setup (per test)
setup tags do
  pid = Ecto.Adapters.SQL.Sandbox.start_owner!(MyApp.Repo, shared: not tags[:async])
  on_exit(fn -> Ecto.Adapters.SQL.Sandbox.stop_owner(pid) end)
  :ok
end

# If a test spawns a process that needs DB access:
Ecto.Adapters.SQL.Sandbox.allow(MyApp.Repo, self(), spawned_pid)

# Sandbox modes:
# :manual  (default in test_helper.exs)    — must check out explicitly
# :auto                                    — auto-checkout on first query (simple sync)
# {:shared, pid}                           — all processes share one connection (async: false only)
```

**Rule:** every Ecto-touching test module uses `async: true` unless it relies on global state. The sandbox guarantees per-test isolation.

### 4.6 Factories — ExMachina

**Factories keep test data DRY, independent, and readable. Don't hand-build structs when you'll use the same shape in more than two tests.**

**Which factory function? — decision table:**

| When you need... | Use this | Returns |
|---|---|---|
| A persisted row in the DB | `insert(:user)` | struct with `:id` set |
| A persisted row with overrides | `insert(:user, email: "x@y.com")` | struct |
| Many persisted rows | `insert_list(5, :user)` | list of structs |
| A struct in memory only (not persisted) | `build(:user)` | struct, no `:id` |
| Attrs map (atom keys) for changeset testing | `params_for(:user)` | `%{email: "...", ...}` |
| Attrs map (string keys) for controller testing | `string_params_for(:user)` | `%{"email" => "...", ...}` |
| Guaranteed unique field per call (avoid collisions) | `sequence(:email, &"user-#{&1}@x.com")` | string — used inside factory |
| Association in a factory | `build(:user)` | set the assoc to a built struct |

**Canonical factory module:**

```elixir
defmodule MyApp.Factory do
  use ExMachina.Ecto, repo: MyApp.Repo

  def user_factory do
    %User{
      email: sequence(:email, &"user-#{&1}@example.com"),
      name: "Test User",
      password_hash: Bcrypt.hash_pwd_salt("secret-pw-123")
    }
  end

  def admin_factory do
    struct!(user_factory(), role: :admin)
  end

  def post_factory do
    %Post{title: "Test Post", body: "Body", author: build(:user)}
  end
end
```

### 4.7 Property testing with StreamData

```elixir
use ExUnitProperties

property "Enum.reverse is its own inverse" do
  check all list <- list_of(integer()), max_runs: 200 do
    assert list == list |> Enum.reverse() |> Enum.reverse()
  end
end

# Top generators: integer(), positive_integer(), float(), boolean(), atom(:alphanumeric),
# binary(), string(:ascii), string(:printable), list_of(gen), map_of(key, val), tuple({gen1, gen2}),
# one_of([gen1, gen2]), member_of([:a, :b, :c]), constant(value), term()

# Generator composition
map(gen, fn x -> transform(x) end)         # Transform
filter(gen, fn x -> predicate(x) end)      # Filter (use sparingly — can be slow)
bind(gen, fn x -> another_gen end)         # Dependent generation

# Multi-value generation
gen all x <- integer(), y <- string(:ascii) do
  {x, y}
end
```

**When to reach for properties:** anything with an obvious invariant (round-trips, sort/reverse, parser/serializer, merge operations, set operations, mathematical functions).

### 4.8 Controller and LiveView testing (essentials)

```elixir
# --- Controller ---
test "GET /products returns 200", %{conn: conn} do
  insert(:product, name: "Widget")
  conn = get(conn, ~p"/products")
  assert html_response(conn, 200) =~ "Widget"
end

test "POST /products with invalid returns 422", %{conn: conn} do
  conn = post(conn, ~p"/products", product: %{name: ""})
  assert json_response(conn, 422)["errors"]["name"] == ["can't be blank"]
end

# --- LiveView ---
import Phoenix.LiveViewTest

test "user can add a comment", %{conn: conn} do
  post = insert(:post)
  {:ok, view, _html} = live(conn, ~p"/posts/#{post}")

  view
  |> form("#comment-form", comment: %{body: "Nice!"})
  |> render_submit()

  assert has_element?(view, "[data-test=comment]", "Nice!")
end

# Full LiveView testing (render_async, hooks, file uploads, etc.) — see elixir-testing skill
```

### 4.9 Common commands

```bash
mix test                              # All tests
mix test test/path/file_test.exs      # One file
mix test test/path/file_test.exs:42   # One test (at line 42)
mix test --failed                     # Re-run only last failures
mix test --stale                      # Re-run only changed modules
mix test --trace                      # Show each test name as it runs
mix test --max-failures 1             # Stop at first failure
mix test --only slow                  # Only @tag :slow
mix test --exclude integration        # Exclude @tag :integration
mix test --cover                      # Coverage report
mix test --seed 123                   # Reproducible ordering (for debugging flaky tests)
```

### 4.10 Diagnosing async test failures

| Symptom | Likely cause | Fix |
|---|---|---|
| Passes alone, fails with others | Shared global state (named GenServer, Application env) | Use `async: false`, OR isolate state per test |
| Random / intermittent failure | Race condition, timing | Replace `Process.sleep` with `assert_receive pattern, timeout` |
| DBConnection errors | Spawned process not allowed by sandbox | `Ecto.Adapters.SQL.Sandbox.allow(Repo, self(), pid)` |
| Time-dependent failure | Wall-clock assertion | Use `assert_in_delta` with tolerance, or inject a clock |
| Factory uniqueness collisions | Hard-coded values, no `sequence/2` | Use `sequence(:email, &"user-#{&1}@example.com")` |

---

## 5. Critical Patterns Claude Commonly Gets Wrong

These are the patterns that separate idiomatic Elixir from "Elixir-shaped imperative code." Each subsection gives the idiomatic template first, then variations, then a common-mistake BAD/GOOD.

### 5.1 Pipelines — the subject-first discipline

**Idiomatic template:**

```elixir
# A pipeline is a sequence of transformations on a primary subject.
# The subject is always the first argument of each step.
raw_input
|> String.trim()
|> String.split("\n")
|> Enum.reject(&(&1 == ""))
|> Enum.map(&parse_line/1)
|> Enum.group_by(& &1.category)
|> Map.new(fn {k, v} -> {k, length(v)} end)
```

**Rules of thumb:**

- 2+ transformations → pipeline
- Exactly 1 → direct call
- The first value in the pipeline is the *subject*; every function after must take it as its first argument
- One pipe per line; never `a |> b() |> c()` inlined

**Variations:**

```elixir
# tap/1 — side effect without breaking the pipeline (returns input unchanged)
order
|> calculate_total()
|> tap(&Logger.debug("Total: #{&1}"))
|> apply_tax()

# then/2 — when the next step is not first-arg-compatible
cfg
|> Map.get(:timeout, 5_000)
|> then(&Process.send_after(self(), :check, &1))

# Conditional step — maybe_X/2 helper, keeps pipeline flat
data
|> transform()
|> maybe_validate(opts[:validate])
|> finalize()

defp maybe_validate(data, true), do: validate(data)
defp maybe_validate(data, _), do: data

# Piping into case — only at the END of a multi-step pipeline
conn
|> fetch_session("user_token")
|> case do
  nil -> assign(conn, :current_user, nil)
  token -> assign(conn, :current_user, Accounts.get_user_by_token(token))
end
```

**BAD/GOOD:**

```elixir
# BAD — single-step pipe
name |> String.upcase()
# GOOD — direct call
String.upcase(name)
```

```elixir
# BAD — piping into a lone reduce_while + case (single step)
Enum.reduce_while(items, {:ok, []}, fn item, {:ok, acc} ->
  case validate(item) do
    {:ok, v} -> {:cont, {:ok, [v | acc]}}
    {:error, _} = e -> {:halt, e}
  end
end)
|> case do
  {:ok, acc} -> {:ok, Enum.reverse(acc)}
  {:error, _} = error -> error
end

# GOOD — intermediate variable, then case
result =
  Enum.reduce_while(items, {:ok, []}, fn item, {:ok, acc} ->
    case validate(item) do
      {:ok, v} -> {:cont, {:ok, [v | acc]}}
      {:error, _} = e -> {:halt, e}
    end
  end)

case result do
  {:ok, acc} -> {:ok, Enum.reverse(acc)}
  {:error, _} = error -> error
end
```

```elixir
# BAD — piping into an anonymous function (awkward)
data |> (fn x -> x * 2 end).()
# GOOD — use then/1
data |> then(&(&1 * 2))
```

```elixir
# BAD — multiple pipes on one line
list |> Enum.map(&process/1) |> Enum.sum()
# GOOD — one pipe per line
list
|> Enum.map(&process/1)
|> Enum.sum()
```

### 5.2 Pattern matching in function heads

**Idiomatic template:**

```elixir
# Multi-clause dispatch on data shape — most powerful Elixir feature.
# Each clause handles a specific case. The compiler warns on unmatched cases.
def handle_event(%Click{x: x, y: y}), do: on_click(x, y)
def handle_event(%Submit{form: form}), do: on_submit(form)
def handle_event(%KeyDown{key: "Escape"}), do: cancel()
def handle_event(%KeyDown{key: key}), do: on_key(key)
def handle_event(unknown), do: {:error, {:unknown_event, unknown}}

# Guards refine the match
def process(n) when is_integer(n) and n > 0, do: :positive
def process(n) when is_integer(n) and n < 0, do: :negative
def process(0), do: :zero
def process(n) when is_float(n), do: :float
def process(_), do: :not_a_number
```

**Canonical shapes:**

```elixir
# Tagged tuples — result dispatch
def handle({:ok, value}), do: process(value)
def handle({:error, reason}), do: log_error(reason)

# Nested destructure — pull deep fields in the head
def city(%User{address: %Address{city: city}}), do: {:ok, city}
def city(_), do: {:error, :no_city}

# Pin to match against an existing variable (NOT bind)
expected_id = 42
case event do
  %{user_id: ^expected_id} -> :match
  _ -> :no_match
end

# Keep the whole struct bound while also destructuring fields
def greet(%User{name: name} = user), do: "Hello #{name}, id=#{user.id}"
```

**BAD/GOOD:**

```elixir
# BAD — if/else dispatching on shape
def handle(msg) do
  if is_map(msg) and Map.has_key?(msg, :type) do
    if msg.type == :error, do: handle_error(msg), else: handle_ok(msg)
  end
end

# GOOD — multi-clause with pattern
def handle(%{type: :error} = msg), do: handle_error(msg)
def handle(%{type: _} = msg), do: handle_ok(msg)
```

```elixir
# BAD — forgetting the pin, variable rebinds and matches ANYTHING
target = 42
case x do
  target -> :match     # Always matches; `target` rebinds to x
end

# GOOD — pin operator
target = 42
case x do
  ^target -> :match
  _ -> :no_match
end
```

```elixir
# BAD — %{} matches ANY map, not just empty
def classify(%{}), do: :empty
# GOOD — guard for empty map
def classify(map) when map_size(map) == 0, do: :empty
def classify(_), do: :non_empty
```

### 5.3 with — chaining ok/error operations

**Idiomatic template:**

```elixir
def create_order(user_id, product_id, qty) do
  with {:ok, user} <- Users.get(user_id),
       {:ok, product} <- Products.get(product_id),
       :ok <- validate_stock(product, qty),
       {:ok, order} <- insert_order(user, product, qty) do
    {:ok, order}
  end
end
```

**When to use else:**

Only when you need to *transform* the error on the way out. Otherwise omit the `else` — the first non-matching value is returned as-is.

```elixir
def create_order(user_id, product_id, qty) do
  with {:ok, user} <- Users.get(user_id),
       {:ok, product} <- Products.get(product_id),
       :ok <- validate_stock(product, qty),
       {:ok, order} <- insert_order(user, product, qty) do
    {:ok, order}
  else
    {:error, :not_found} -> {:error, :resource_not_found}
    {:error, :insufficient_stock} -> {:error, :out_of_stock}
    # Any other {:error, _} falls through unchanged
  end
end
```

**Tagged-tuple with — label each clause for precise error handling:**

```elixir
# Use when several steps can return the same error shape and you need
# to distinguish which step failed.
with {:user, {:ok, user}} <- {:user, fetch_user(id)},
     {:auth, :ok} <- {:auth, authorize(user, action)},
     {:save, {:ok, result}} <- {:save, save(user)} do
  {:ok, result}
else
  {:user, {:error, _}} -> {:error, :user_not_found}
  {:auth, {:error, _}} -> {:error, :unauthorized}
  {:save, {:error, changeset}} -> {:error, changeset}
end
```

**BAD/GOOD:**

```elixir
# BAD — nested case
def register(params) do
  case validate_email(params) do
    {:ok, email} ->
      case validate_password(params) do
        {:ok, password} ->
          case create_user(email, password) do
            {:ok, user} -> {:ok, user}
            {:error, reason} -> {:error, reason}
          end
        {:error, reason} -> {:error, reason}
      end
    {:error, reason} -> {:error, reason}
  end
end

# GOOD — with chain
def register(params) do
  with {:ok, email} <- validate_email(params),
       {:ok, password} <- validate_password(params),
       {:ok, user} <- create_user(email, password) do
    {:ok, user}
  end
end
```

```elixir
# BAD — with for a single op (overkill, harder to read)
with {:ok, user} <- Accounts.fetch(id) do
  process(user)
end

# GOOD — case for a single op
case Accounts.fetch(id) do
  {:ok, user} -> process(user)
  {:error, _} = e -> e
end
```

### 5.4 Comprehensions — `for` when it wins over pipelines

Use `for` when you're doing one or more of:

- Pattern-matching generators (silent skip on non-match)
- Collecting into a specific type (`into:`)
- Accumulator with tuple/map state (`reduce:`)
- Multiple generators (Cartesian / nested iteration)
- Binary iteration (`<<byte <- data>>`)
- Deduplication (`uniq: true`)

```elixir
# Pattern in generator — skip non-successful results silently
for {:ok, value} <- results, do: value

# into: MapSet — build a set in one pass
for app <- apps, module <- Application.spec(app, :modules), into: MapSet.new(), do: module

# Binary comprehension — iterate bytes
for <<byte <- string>>, byte not in ?\s..?~, into: "", do: <<byte>>

# reduce: — tuple accumulator in one pass
for {name, field} <- fields, reduce: {[], []} do
  {keep, drop} ->
    case field.writable do
      :always -> {[name | keep], drop}
      _ -> {keep, [name | drop]}
    end
end

# Multiple generators — cross product
for x <- 1..3, y <- 1..3, x <= y, do: {x, y}
#=> [{1,1}, {1,2}, {1,3}, {2,2}, {2,3}, {3,3}]

# uniq: true — inline deduplication
for type_expr <- args, var <- collect_vars(type_expr), uniq: true, do: var
```

### 5.5 Recursion — the third iteration tool

> **Depth:** [idioms-reference.md](idioms-reference.md) §Recursion — Last Call Optimization (LCO) explained with tail-position precision table, body-vs-tail trade-offs with modern BEAM/JIT performance nuance, accumulator-reverse pattern, binary-pattern recursion, tree traversal, mutual recursion, recursion-vs-`reduce_while` decision, wrapping recursive walkers as lazy streams.

Recursion is **a first-class iteration tool in Elixir**, not a fallback. A tail-recursive function with pattern matching is the functional equivalent of an imperative `while` loop — constant stack, pattern-dispatch on the state.

**When recursion is the right answer:**

- **Long-running loops** — GenServer message loops, TCP accept loops, retry loops. Elixir's idiomatic `while (true)`.
- **Early termination** with halt conditions spanning multiple accumulators (simple cases fit `Enum.reduce_while`).
- **Tree / graph / AST traversal** where the structure is genuinely recursive.
- **Binary decoders** — `<<byte, rest::binary>> = data; decode(rest)` is the dominant BEAM-optimized pattern for parsers.
- **Parsers and walkers** where each element shapes what you do with the next.
- **Infinite / lazy generation** — wrapped in `Stream.iterate`/`Stream.unfold`/`Stream.resource`.
- **Custom enumeration** — implementing `Enumerable`.

**Tail vs body recursion — both are first-class.** The Erlang Efficiency Guide (*Seven Myths of Erlang Performance*) explicitly says: *"Use the version that makes your code cleaner (hint: it is usually the body-recursive version)."* Since R12B, body-recursive list construction uses the same memory as tail + reverse. The stdlib's `:lists.map/2`, `:lists.filter/2`, and list comprehensions are all body-recursive by choice.

**When each is right:**

| Situation | Prefer |
|---|---|
| Unbounded / adversarial input (user lists, streams) | **Tail** — guaranteed constant stack |
| Long-running process loop | **Tail** — MUST (never terminates) |
| Known-bounded structure (tree, AST, expression grammar, recurrence) | **Body** — clearer, often the better choice |
| List transformation where order matters | Either — body-recursive is often cleaner; tail + reverse is explicit |
| Modern OTP (24+) with JIT, performance matters | Benchmark — JIT has reversed some pre-JIT rules of thumb |

**The while-loop analogy:**

```elixir
# Imperative: while (running) { msg = receive(); handle(msg); }
def loop(state) do
  receive do
    :stop -> :ok
    msg -> msg |> handle(state) |> loop()      # tail call — constant stack
  end
end

# Imperative: while (!done) { if (try_work()) break; sleep(); }
def retry(attempt \\ 1) do
  case work() do
    {:ok, r} -> {:ok, r}
    {:error, _} when attempt >= @max -> {:error, :exhausted}
    {:error, _} -> Process.sleep(backoff(attempt)); retry(attempt + 1)
  end
end
```

**Tail-position gotchas** (where LCO silently DOESN'T apply — see idioms-reference for full list):

- `with ... else ...` — the `else` clause keeps the result for re-matching; final call is NOT tail.
- `try do ... end` — the protected `do` body is NOT tail position (stacktrace is kept).
- Arithmetic / construction around the call: `[x | recur(t)]` is body-recursive (fine for bounded input; not "broken").

**BAD/GOOD:**

```elixir
# Body-recursive — fine for reasonable inputs; stdlib :lists.map works exactly this way
def double_all([]), do: []
def double_all([h | t]), do: [h * 2 | double_all(t)]

# Tail-recursive + reverse — use when input may be unbounded
def double_all(list), do: do_double_all(list, [])
defp do_double_all([], acc), do: Enum.reverse(acc)
defp do_double_all([h | t], acc), do: do_double_all(t, [h * 2 | acc])

# Usually clearest — let Enum handle bounded-list work
def double_all(list), do: Enum.map(list, &(&1 * 2))
```

**Real anti-patterns (these ARE broken):**

```elixir
# BAD — O(n²) from append in accumulator
defp build([], acc), do: acc
defp build([h | t], acc), do: build(t, acc ++ [process(h)])   # ++ on left operand!

# BAD — reimplementing Enum.map
def each_squared(list), do: do_each_squared(list, [])
defp do_each_squared([], acc), do: Enum.reverse(acc)
defp do_each_squared([h | t], acc), do: do_each_squared(t, [h * h | acc])
# → just write: Enum.map(list, &(&1 * &1))
```

### 5.6 Guards — constraints at the function boundary

```elixir
# Combine guard clauses with `when` — comma = AND, `when ... when ...` = OR
def valid?(x) when is_integer(x) and x >= 0 and x <= 100, do: true
def valid?(_), do: false

# Multiple when = OR — cleaner than long `or` chains
def is_escape_char(c)
    when c in 0x2061..0x2064
    when c in [0x061C, 0x200E, 0x200F]
    when c in 0x202A..0x202E,
    do: true

# Custom guards (defguard) — reusable, composable
defguard is_positive_int(n) when is_integer(n) and n > 0
defguard is_non_empty_str(s) when is_binary(s) and byte_size(s) > 0

def create(%{age: age, name: name}) when is_positive_int(age) and is_non_empty_str(name) do
  {:ok, %User{age: age, name: name}}
end

# Allowed in guards (partial list): is_*, ==, !=, <, >, in, and/or/not,
# +, -, *, /, abs, div, rem, round, trunc, byte_size, elem, hd, tl, length,
# map_size, tuple_size, is_map_key, Bitwise operators (after `import Bitwise`)

# NOT allowed in guards: String.length, Enum.*, any user-defined function
# (except via defguard)
```

**Idiomatic use — guard on struct field without binding the whole struct:**

```elixir
# When you care about one field of a large struct, guard on dot-access
def active?(strategy) when strategy.enabled? and strategy.version >= 2, do: true
def active?(_), do: false
```

### 5.7 IO lists — building binaries without O(n²)

```elixir
# Nested lists of binaries, integers (bytes), or other IO lists.
# Accepted by File.write/2, IO.puts/1, :gen_tcp.send/2, etc.

# Build by prepending (O(1))
iolist = ["last", ", ", "middle", ", ", "first"]
# Flatten only when you need a real binary
binary = IO.iodata_to_binary(iolist)

# Build a CSV row without concatenation
row = [name, ",", amount_str, ",", date, "\n"]

# Join with separator via map_join
csv = Enum.map_join(rows, "\n", fn row -> Enum.join(row, ",") end)

# Build via comprehension
headers = for {k, v} <- headers, into: "", do: "#{k}: #{v}\r\n"
```

**BAD/GOOD:**

```elixir
# BAD — O(n²) — each <> copies the entire growing string
Enum.reduce(rows, "", fn row, acc -> acc <> format(row) <> "\n" end)

# GOOD — IO list, single binary at the end
rows
|> Enum.map(fn row -> [format(row), "\n"] end)
|> IO.iodata_to_binary()

# ALSO GOOD — map_join for a simple case
Enum.map_join(rows, "\n", &format/1)
```

### 5.8 Struct updates — the `%{struct | field: v}` syntax

```elixir
# Update existing key — compile-time check that the field exists
%User{name: "Jane", age: 30}
|> then(fn u -> %{u | age: u.age + 1} end)

# Struct update with multiple fields
%{user | name: new_name, updated_at: DateTime.utc_now()}

# Nested update via put_in/update_in
put_in(order.shipping.address.city, "New City")
update_in(order.items, &Enum.map(&1, fn item -> %{item | price: item.price * 0.9} end))
```

**BAD/GOOD:**

```elixir
# BAD — Map.put silently accepts typos
%{user | nmae: "Jane"}     # Compile error: key :nmae not in struct User
Map.put(user, :nmae, "Jane")  # No error! Silently adds :nmae to the struct

# GOOD — update syntax for existing fields
%{user | name: "Jane"}
```

---

## 6. Idiomatic Elixir Constructs

> **Depth:** [idioms-reference.md](idioms-reference.md) has full syntax reference + examples for every construct below. This section is an index — load the subskill for templates.

| Construct | When | Depth |
|---|---|---|
| `if` / `unless` | Boolean guard with side effect, no else value | idioms §`case`/`cond`/`if` |
| `case` | Dispatch on one value's shape; can pipe into at end of multi-step pipeline | idioms §`case`/`cond`/`if` |
| `cond` | Multiple independent booleans, no single subject | idioms §`case`/`cond`/`if` |
| `with` | Chain 2+ ok/error steps — BUT note `with ... else` breaks LCO | idioms §`with` Chains |
| Multi-clause function | Dispatch on argument shape/type | idioms §Pattern Matching in Function Heads |
| Guards | Constrain function head; custom via `defguard` | idioms §Guards |
| `Enum` | Bounded collection transformations — see function reference | idioms §`Enum` |
| `Stream` | Lazy / I/O-sourced / infinite / stop-early | idioms §`Stream` |
| `for` comprehension | Filter + transform in one pass; `into:`, `reduce:`, `uniq:`, binary | idioms §`for` Comprehensions |
| `&` capture | Function reference when arity matches | idioms §Captures |
| Recursion | Long-running loops, trees, binary decoders, state machines | idioms §Recursion |
| Protocols | Dispatch on data type | idioms §Protocols |
| Behaviours | Dispatch on module identity (swap at config time) | idioms §Behaviours |

### Three templates worth keeping inline

**Piping into `case` (end of multi-step pipeline only):**

```elixir
resource
|> lookup_transitions(action_name)
|> Enum.find(&match_transition?(&1, state, target))
|> case do
  nil -> {:error, :no_matching_transition}
  t -> {:ok, apply_transition(t)}
end
```

**`cond` with binding in condition (priority resolution):**

```elixir
cond do
  val = Map.get(overrides, key) -> val
  val = Map.get(config, key) -> val
  true -> default
end
```

**Keyword options + validation:**

```elixir
def start_link(opts) do
  opts = Keyword.validate!(opts, [name: __MODULE__, timeout: 5_000, retries: 3])
  GenServer.start_link(__MODULE__, opts, name: opts[:name])
end
```

---

## 7. Anti-patterns Claude Commonly Produces (BAD/GOOD)

Targeted at the specific mistakes that appear in LLM-generated Elixir. Each pair is a pattern Claude is prone to emit; the GOOD side is what idiomatic code looks like.

### 7.1 Control flow

```elixir
# BAD — if/else chain dispatching on data shape
def handle(msg) do
  if is_map(msg) and Map.has_key?(msg, :type) do
    if msg.type == :error, do: handle_error(msg), else: handle_ok(msg)
  end
end

# GOOD — multi-clause with pattern in head
def handle(%{type: :error} = msg), do: handle_error(msg)
def handle(%{type: _} = msg), do: handle_ok(msg)
```

```elixir
# BAD — truthy if for config-driven dispatch, missing edge case (what if opt is false?)
defp do_initialize(opts) do
  if opts[:open] do
    do_open_index(opts)
  else
    do_create_index(opts)
  end
end

# GOOD — strict case with explicit default
defp do_initialize(opts) do
  case Keyword.get(opts, :open, false) do
    true -> do_open_index(opts)
    false -> do_create_index(opts)
  end
end
```

```elixir
# BAD — nested case instead of with
def register(params) do
  case validate_email(params) do
    {:ok, email} ->
      case validate_password(params) do
        {:ok, password} ->
          case create_user(email, password) do
            {:ok, user} -> {:ok, user}
            {:error, r} -> {:error, r}
          end
        {:error, r} -> {:error, r}
      end
    {:error, r} -> {:error, r}
  end
end

# GOOD — with chain; errors propagate automatically
def register(params) do
  with {:ok, email} <- validate_email(params),
       {:ok, password} <- validate_password(params),
       {:ok, user} <- create_user(email, password) do
    {:ok, user}
  end
end
```

```elixir
# BAD — nil check with if
def greet(user) do
  if user != nil do
    if user.name != nil, do: "Hello, #{user.name}", else: "Hello, anon"
  else
    "Hello, guest"
  end
end

# GOOD — multi-clause on shape
def greet(%{name: name}) when is_binary(name), do: "Hello, #{name}"
def greet(%{}), do: "Hello, anon"
def greet(nil), do: "Hello, guest"
```

```elixir
# BAD — cond with implicit fall-through (if no branch matches: CondClauseError)
cond do
  x > 10 -> :large
  x > 5 -> :medium
end

# GOOD — explicit `true -> default` at the bottom
cond do
  x > 10 -> :large
  x > 5 -> :medium
  true -> :small
end
```

### 7.2 Pipelines

```elixir
# BAD — single-step pipe
name |> String.upcase()
# GOOD
String.upcase(name)
```

```elixir
# BAD — pipe into a lone case after a single step
Enum.reduce_while(xs, {:ok, []}, fn ... end)
|> case do
  {:ok, acc} -> {:ok, Enum.reverse(acc)}
  {:error, _} = e -> e
end

# GOOD — intermediate variable, direct case
result = Enum.reduce_while(xs, {:ok, []}, fn ... end)

case result do
  {:ok, acc} -> {:ok, Enum.reverse(acc)}
  {:error, _} = e -> e
end
```

```elixir
# BAD — multiple pipes inlined on one line
list |> Enum.map(&f/1) |> Enum.filter(&g/1) |> Enum.sum()

# GOOD — one pipe per line
list
|> Enum.map(&f/1)
|> Enum.filter(&g/1)
|> Enum.sum()
```

```elixir
# BAD — piping into an anonymous function with immediate invoke
data |> (fn x -> x * 2 end).()

# GOOD — then/1
data |> then(&(&1 * 2))
```

### 7.3 Enum / iteration

```elixir
# BAD — Enum.each to accumulate (rebinding doesn't escape the closure!)
result = []
Enum.each(items, fn item -> result = [process(item) | result] end)
result  # still []

# GOOD — Enum.map or Enum.reduce
result = Enum.map(items, &process/1)
```

```elixir
# BAD — length(list) > 0 to check non-empty (O(n) traversal)
if length(list) > 0, do: process(list)

# GOOD — pattern match on shape (O(1))
case list do
  [] -> :empty
  [_ | _] -> process(list)
end
# Or guard:
def process([_ | _] = list), do: # ...
```

```elixir
# BAD — Enum.map wrapping an existing function with an anonymous fn
Enum.map(users, fn user -> User.name(user) end)

# GOOD — function capture
Enum.map(users, &User.name/1)
```

```elixir
# BAD — imperative index tracking with reduce
{result, _i} = Enum.reduce(list, {[], 0}, fn x, {acc, i} ->
  {[{i, process(x)} | acc], i + 1}
end)
Enum.reverse(result)

# GOOD — Enum.with_index
list
|> Enum.with_index()
|> Enum.map(fn {x, i} -> {i, process(x)} end)
```

```elixir
# BAD — two passes for partition
good = Enum.filter(xs, &valid?/1)
bad = Enum.reject(xs, &valid?/1)

# GOOD — split_with in one pass
{good, bad} = Enum.split_with(xs, &valid?/1)
```

```elixir
# BAD — Enum.reduce into a map when Map.new/2 is clearer
Enum.reduce(pairs, %{}, fn {k, v}, acc -> Map.put(acc, k, v * 2) end)

# GOOD — Map.new/2
Map.new(pairs, fn {k, v} -> {k, v * 2} end)
```

### 7.4 Error handling

```elixir
# BAD — try/rescue for an expected failure
def parse_int(s) do
  try do
    {:ok, String.to_integer(s)}
  rescue
    ArgumentError -> {:error, :invalid}
  end
end

# GOOD — Integer.parse returns ok/error directly
def parse_int(s) do
  case Integer.parse(s) do
    {int, ""} -> {:ok, int}
    {_, _rest} -> {:error, :trailing_chars}
    :error -> {:error, :invalid}
  end
end
```

```elixir
# BAD — rescue to catch GenServer.call exits (it doesn't — call raises :exit, not an exception)
try do
  GenServer.call(pid, :status)
rescue
  _ -> {:error, :down}
end

# GOOD — catch :exit, at the boundary only
try do
  GenServer.call(pid, :status)
catch
  :exit, _ -> {:error, :down}
end
```

```elixir
# BAD — non-bang function that raises on error (surprising!)
def deliver_now(email) do
  if email.to == [] do
    raise "no recipients"   # Caller expects {:ok, _} | {:error, _}!
  end
  # ...
end

# GOOD — non-bang returns tuples, bang variant raises
def deliver_now(email) do
  case validate_and_send(email) do
    {:ok, r} -> {:ok, r}
    {:error, _} = e -> e
  end
end
def deliver_now!(email), do: deliver_now(email) |> ok!()
```

```elixir
# BAD — broad rescue that swallows everything
def risky do
  do_work()
rescue
  _ -> nil
end

# GOOD — rescue specific exceptions
def risky do
  do_work()
rescue
  File.Error -> {:error, :io}
  MatchError -> {:error, :malformed}
end
```

### 7.5 Data manipulation

```elixir
# BAD — Map.put for a struct field (silently adds unknown keys with typos)
Map.put(user, :nmae, "Jane")   # No error — :nmae silently added

# GOOD — update syntax (compile error if :nmae not in struct)
%{user | name: "Jane"}
```

```elixir
# BAD — rebinding in a chain
data = Map.put(data, :step1, compute_step1(data))
data = Map.put(data, :step2, compute_step2(data))
data = Map.put(data, :step3, compute_step3(data))

# GOOD (independent steps) — Map.merge with all at once
Map.merge(data, %{
  step1: compute_step1(data),
  step2: compute_step2(data),
  step3: compute_step3(data)
})

# GOOD (dependent steps) — pipeline with then/1 or a proper helper
data
|> then(&Map.put(&1, :step1, compute_step1(&1)))
|> then(&Map.put(&1, :step2, compute_step2(&1)))
|> then(&Map.put(&1, :step3, compute_step3(&1)))
```

```elixir
# BAD — O(n²) string concatenation in a loop
Enum.reduce(rows, "", fn row, acc -> acc <> format(row) <> "\n" end)

# GOOD — IO list, one conversion
rows
|> Enum.map(fn row -> [format(row), "\n"] end)
|> IO.iodata_to_binary()
```

### 7.6 Pattern matching gotchas

```elixir
# BAD — forgot the pin; variable rebinds and matches anything
expected = :ok
case result do
  expected -> :matched    # ALWAYS matches; `expected` rebinds to result
end

# GOOD — pin operator
case result do
  ^expected -> :matched
  _ -> :no_match
end
```

```elixir
# BAD — %{} matches ANY map, not just empty
def classify(%{}), do: :empty   # Matches %{a: 1, b: 2} too!

# GOOD — guard
def classify(m) when map_size(m) == 0, do: :empty
def classify(_), do: :non_empty
```

```elixir
# BAD — atom keys pattern-matched against string-keyed params
params = %{"name" => "Jane"}
%{name: n} = params             # MatchError! Atom :name != string "name"

# GOOD — match with the correct key type at the boundary
%{"name" => n} = params         # External data → string keys
%{name: n} = internal_map       # Internal data → atom keys
```

### 7.7 Atoms and safety

```elixir
# DANGEROUS — user input becomes permanent atoms (atom table exhaustion, ~1M limit)
String.to_atom(user_input)
Jason.decode!(json, keys: :atoms)

# SAFE — use to_existing_atom, or keep as strings
String.to_existing_atom(user_input)
Jason.decode!(json)             # Default keys: :strings
```

### 7.8 Function and API design

```elixir
# BAD — boolean parameters obscure intent at call sites
fetch_users(true, false)        # What do these mean?

# GOOD — keyword options
fetch_users(active: true, preload: false)

# BETTER for distinct modes — separate named functions
fetch_active_users()
```

```elixir
# BAD — @spec on public function missing or too loose
def fetch(id), do: ...          # No @spec — callers don't know the return shape

# GOOD — @spec that matches actual behavior
@spec fetch(pos_integer()) :: {:ok, User.t()} | {:error, :not_found}
def fetch(id), do: ...
```

```elixir
# BAD — Application.get_env in module body of a LIBRARY (captured at compile time)
defmodule MyLib.Client do
  @api_key Application.get_env(:my_lib, :api_key)   # Baked in at compile!
  def call, do: request(@api_key)
end

# GOOD — read at runtime; consumers can configure after compilation
defmodule MyLib.Client do
  def call, do: request(Application.get_env(:my_lib, :api_key))
end
```

### 7.9 Process / OTP

```elixir
# BAD — spawn for long-running work (unsupervised)
spawn(fn -> loop() end)

# GOOD — supervised Task
Task.Supervisor.start_child(MyApp.TaskSupervisor, fn -> loop() end)
```

```elixir
# BAD — business logic in GenServer callback
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

# GOOD — pure function for domain logic, GenServer for process mechanics only
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

```elixir
# BAD — GenServer.call to a Registry-registered process using the raw atom
GenServer.call(:my_worker, :ping)
# ** (EXIT) no process associated with the given name

# GOOD — use the same via tuple the process was registered with
GenServer.call({:via, Registry, {MyApp.Registry, :my_worker}}, :ping)
# BEST — provide a `via/1` helper in the module
GenServer.call(MyApp.WorkerRegistry.via(:my_worker), :ping)
```

```elixir
# BAD — GenServer with huge state (100KB+ blob) copied on every call
def init(_), do: {:ok, %{huge_cache: load_giant_map()}}

# GOOD — ETS for large or concurrent-read data
def init(_) do
  :ets.new(:my_cache, [:named_table, :public, read_concurrency: true])
  populate_cache()
  {:ok, %{}}
end
```

### 7.10 Tests

```elixir
# BAD — asserting on inspect output (no structural diff, brittle)
assert inspect(result) == "{:ok, %User{email: \"a@b.com\"}}"

# GOOD — pattern-match assertion
assert {:ok, %User{email: "a@b.com"}} = result
```

```elixir
# BAD — Process.sleep for async behavior (flaky)
send(pid, :go)
Process.sleep(100)
assert :done == GenServer.call(pid, :state)

# GOOD — wait for a specific message
send(pid, :go)
assert_receive {:done, _}, 500
```

```elixir
# BAD — testing via module-global state (breaks async: true)
setup do
  :ets.insert(:shared_cache, {:key, "value"})  # Bleeds across tests!
  :ok
end

# GOOD — per-test state via start_supervised! or context
setup do
  cache = start_supervised!({MyApp.Cache, []})
  %{cache: cache}
end
```

```elixir
# BAD — Mox.stub for something the code MUST call
stub(MyApp.Mailer.Mock, :send_welcome, fn _ -> :ok end)
# If the code doesn't call send_welcome, the test still passes. That's usually wrong.

# GOOD — expect, which verifies the call happened
expect(MyApp.Mailer.Mock, :send_welcome, fn _ -> :ok end)
```

---

## 8. Daily Operations

> **Depth:** For `@spec`/`@type`/`@doc`/`@moduledoc`/doctests/Dialyzer, load [type-and-docs.md](type-and-docs.md). For Ecto schemas/changesets/queries/migrations/Multi, load [ecto-patterns.md](ecto-patterns.md). For TCP/UDP/protocol-framing code, load [networking-patterns.md](networking-patterns.md).

The code-maintenance toolkit: error handling, module structure, naming, docs, configuration, logging. Each subsection leads with the decision and shows the idiomatic shape.

### 8.1 ok/error tuple conventions

| When the function... | Returns |
|---|---|
| Succeeds with data | `{:ok, value}` |
| Succeeds with no meaningful data (side effect confirmed) | `:ok` |
| Fails with a known reason | `{:error, atom_reason}` or `{:error, struct_or_map}` |
| Fails with compound context | `{:error, {reason, details}}` |
| Cannot fail (infallible) | Return the value directly |
| Fails loudly because the caller guaranteed valid input | `!`-suffixed version that raises |

**Canonical pairs:**

```elixir
# Non-bang returns ok/error — caller decides how to handle failure
def fetch(id) do
  case lookup(id) do
    nil -> {:error, :not_found}
    val -> {:ok, val}
  end
end

# Bang raises — failure is a programmer error, fail fast
def fetch!(id) do
  case fetch(id) do
    {:ok, val} -> val
    {:error, reason} -> raise "fetch/1 failed: #{inspect(reason)}"
  end
end
```

### 8.2 Error handling decision tree

| Situation | Strategy |
|---|---|
| Condition is checkable before the call | Check first (`Process.whereis`, `Map.fetch`), don't catch |
| Calling a process you don't control | `catch :exit, _` at the boundary |
| Untrusted external input (network bytes, user blob) | `rescue` specific exception at the adapter boundary |
| Expected business failure | Return `{:error, reason}`; caller matches |
| Programmer error in script / seed | Use bang variant, let it crash |
| Anything else inside a supervised process | Let it crash — supervisor restarts |

### 8.3 Module structure — the canonical template

```elixir
defmodule MyApp.Accounts.User do
  @moduledoc """
  User aggregate — identity, authentication, profile.
  """

  use Ecto.Schema                          # 1. use
  import Ecto.Changeset                    # 2. import
  alias MyApp.{Repo, Accounts.Token}       # 3. alias
  require Logger                           # 4. require

  @behaviour MyApp.Identifiable            # 5. @behaviour

  @type t :: %__MODULE__{}                 # 6. @type / @typedoc
  @type role :: :admin | :member | :guest

  @roles [:admin, :member, :guest]         # 7. module attributes (constants)
  @derive {Jason.Encoder, only: [:id, :email, :name]}

  # 8. schema / defstruct
  schema "users" do
    field :email, :string
    field :name, :string
    field :role, Ecto.Enum, values: @roles
    timestamps(type: :utc_datetime_usec)
  end

  # 9. public API with @doc + @spec
  @doc "Creates a changeset for user registration."
  @spec changeset(t(), map()) :: Ecto.Changeset.t()
  def changeset(user, attrs), do: ...

  # 10. callback implementations
  @impl MyApp.Identifiable
  def id(%__MODULE__{id: id}), do: id

  # 11. private helpers (defp) at the bottom
  defp validate_email_format(cs), do: ...
end
```

**Order:** `@moduledoc` → `use` → `import` → `alias` → `require` → `@behaviour` → `@type` → attributes → schema/struct → public functions → private helpers.

### 8.4 Naming

| Kind | Style | Example |
|---|---|---|
| Module | PascalCase | `MyApp.OrderProcessor` |
| Function | snake_case | `process_order/2` |
| Private helper | snake_case, often with `do_` prefix for recursive or `maybe_` for conditional | `do_process/2`, `maybe_notify/1` |
| Predicate | ends with `?` | `valid?/1`, `empty?/1` |
| Raising variant | ends with `!` | `fetch!/1`, `parse!/1` |
| Atom identifier | snake_case | `:not_found`, `:invalid_email` |
| Module attribute | snake_case | `@default_timeout` |
| Variable | snake_case | `current_user`, `email_pid` |
| Type | lowercase, ends `t()` for the main struct type | `user :: t()` |

**Function naming patterns:**

- `get_foo/1` — pure lookup, returns value or `nil` / default
- `fetch_foo/1` — returns `{:ok, value}` / `{:error, reason}`
- `fetch_foo!/1` — returns value or raises
- `list_foos/0,1` — returns a list (possibly empty)
- `create_foo/1` — inserts new; returns `{:ok, struct}` / `{:error, changeset}`
- `update_foo/2` — updates existing; same return shape
- `delete_foo/1` — deletes
- `foo?/1` — predicate returning boolean

### 8.5 Documentation

**Minimum every public module must have:**

```elixir
defmodule MyApp.Orders do
  @moduledoc """
  Order aggregate — cart → payment → fulfillment.

  ## Overview

  One-paragraph summary. What problem does this module solve?

  ## Examples

      iex> MyApp.Orders.place_order(%{...})
      {:ok, %Order{id: _}}
  """

  @doc """
  Places a new order.

  ## Parameters
    * `attrs` — order attributes (must include `:user_id`, `:items`)

  ## Examples

      iex> MyApp.Orders.place_order(%{user_id: 1, items: []})
      {:error, :empty_cart}
  """
  @spec place_order(map()) :: {:ok, Order.t()} | {:error, term()}
  def place_order(attrs), do: ...
end
```

**Doctest rule:** put `iex>` examples in `@doc` when the function is pure and has easily demonstrable output. Doctests become tests automatically via `doctest MyApp.Orders` in your test file.

### 8.6 Configuration — where each kind lives

| Config type | File | Loaded when |
|---|---|---|
| Compile-time, known at build (e.g., `Application.compile_env`) | `config/config.exs` | Compile time |
| Dev-specific overrides | `config/dev.exs` | Compile time (dev only) |
| Test-specific overrides (Mox wiring, reduced pool sizes) | `config/test.exs` | Compile time (test only) |
| Production secrets, per-env env vars | `config/runtime.exs` | Boot time (after release assembly) |
| Library defaults (when writing a library) | `config/config.exs` (minimal) — callers override | Compile time |

**Rules:**

- Libraries use `Application.get_env/3` at runtime — callers configure after compilation
- Applications can use `Application.compile_env/3` for values set at build
- Never put `System.get_env/1` in `config/config.exs` for production values — use `runtime.exs`

```elixir
# config/runtime.exs (Mix release pattern)
import Config
if config_env() == :prod do
  config :my_app, MyApp.Repo,
    url: System.fetch_env!("DATABASE_URL"),
    pool_size: String.to_integer(System.get_env("POOL_SIZE", "10"))

  config :my_app, MyAppWeb.Endpoint,
    secret_key_base: System.fetch_env!("SECRET_KEY_BASE")
end
```

### 8.7 Logger — levels and structured logging

| Level | Use for |
|---|---|
| `Logger.debug/1` | Detail useful during development, disabled in prod |
| `Logger.info/1` | Lifecycle events (startup, shutdown, job completed) |
| `Logger.notice/1` | Unusual but normal (rate limit hit, fallback used) |
| `Logger.warning/1` | Recovered error, degraded service |
| `Logger.error/1` | Unrecovered error, alert-worthy |

```elixir
# Prefer structured metadata — searchable in log aggregators
Logger.info("order completed", order_id: order.id, total_cents: order.total_cents)

# Lazy-evaluation for expensive messages — the closure only runs if level is enabled
Logger.debug(fn -> "state: #{inspect(build_heavy_state(), pretty: true)}" end)

# Never: Logger.info("order #{inspect(order)}") — all of inspect runs even if debug is off
```

### 8.8 Mix commands — daily use

```bash
# Compile with warnings as errors (catches undefined functions, unused vars, etc.)
mix compile --warnings-as-errors

# Format + credo + test — the pre-commit trio
mix format
mix credo --strict
mix test

# Focused test runs
mix test path/file_test.exs:42
mix test --failed
mix test --stale

# Dependency operations
mix deps.get                  # Install deps from mix.lock
mix deps.update --all         # Update all deps (respecting version constraints)
mix deps.tree                 # See dependency graph

# Build a production release (Mix releases)
MIX_ENV=prod mix release

# Ecto
mix ecto.create
mix ecto.migrate
mix ecto.rollback --step 1
mix ecto.gen.migration add_users

# Phoenix
mix phx.gen.schema Blog.Post posts title:string body:text
mix phx.server
mix phx.routes
```

### 8.9 IEx — the development REPL

```elixir
# iex -S mix      — start IEx with your project loaded
# iex --dbg pry   — enable IEx.pry/0 for interactive breakpoints

# Helpers (typed in IEx)
h Enum.map/2                  # Docs for a function
i value                       # Type info for a value
v()                           # Last result; v(3) for the result 3 commands ago
r MyModule                    # Recompile a module
recompile                     # Recompile the whole project
s Enum.map/2                  # Show @spec
t String                      # Show @type definitions in a module
exports Module                # List public functions
```

**Remote shell (production release):**

```bash
iex --sname debug --cookie $COOKIE --remsh myapp@localhost
```

---

## 9. OTP — Key Decisions for Implementers

> **Depth:** For callback templates (GenServer `init/handle_call/cast/info/continue`, Task/Agent patterns, Registry via-tuples, ETS calls, `:gen_statem` skeleton, supervisor child-specs), load [otp-callbacks.md](otp-callbacks.md). For architectural OTP decisions (WHICH construct to choose, supervision-tree shape), load `../elixir-planning/otp-design.md` and `../elixir-planning/process-topology.md`.

When implementing code that involves processes, the first decision is always *do I need a process at all?* Most code doesn't. The rest of this section walks through the decisions that DO need a process.

### 9.1 Do you need a process at all?

| Situation | Process? |
|---|---|
| Pure data transformation | No — pure function |
| Stateless request/response | No — pure function |
| State that lives for one function call | No — pass as arg, return new state |
| State shared across calls within one process | No — struct module + threading through calls |
| State shared across MULTIPLE processes | Yes |
| State that must survive a crash | Yes (supervised) |
| Serializing access to a resource (writer) | Yes (GenServer) |
| Concurrent independent work | Maybe Task; Yes if long-running |
| Scheduled / periodic work | Yes (GenServer with `Process.send_after`, or Oban) |
| Cross-node messaging | Yes (GenServer or similar) |

**If you need a process, pick the narrowest construct.**

### 9.2 Which OTP construct? — decision table

| Need | Use | Why |
|---|---|---|
| One-off concurrent side-effect work | `Task.Supervisor.start_child/2` | Supervised, no state |
| Parallel map with bounded concurrency | `Task.async_stream/3,5` | Built-in concurrency control + backpressure |
| Long-running worker holding state | `GenServer` | Standard behaviour, well-tooled |
| Explicit state machine with transitions | `:gen_statem` | Cleaner than huge `case` in GenServer |
| Single-value concurrent update (counter, cache) | `Agent` | Lightweight; wraps GenServer |
| Read-heavy shared data (many readers, one writer) | ETS (`:public`, `read_concurrency: true`) | Avoids GenServer bottleneck |
| Atomic counters / gauges | `:counters` / `:atomics` | Lock-free, very fast |
| Rarely-changing global config | `:persistent_term` | O(1) reads; expensive writes |
| Backpressured data pipeline | GenStage / Broadway | Designed for flow control |
| Persistent job queue with retries | Oban | Durable, observable |
| Name-based dispatch across many processes | Registry (`:via` tuples) | Per-process naming without atoms |
| Many transient processes (one per user/session) | DynamicSupervisor + Registry | Start/stop dynamically, find by key |
| Pub/sub within a node | `Registry` with `:duplicate` keys, or `Phoenix.PubSub` | Native dispatch |

### 9.3 GenServer — canonical template

```elixir
defmodule MyApp.Counter do
  use GenServer
  require Logger

  # --- Client API (public) ---
  @doc "Starts the counter under a supervisor."
  def start_link(opts) do
    {name, opts} = Keyword.pop(opts, :name, __MODULE__)
    GenServer.start_link(__MODULE__, opts, name: name)
  end

  @spec increment(GenServer.server()) :: non_neg_integer()
  def increment(server \\ __MODULE__), do: GenServer.call(server, :increment)

  @spec get(GenServer.server()) :: non_neg_integer()
  def get(server \\ __MODULE__), do: GenServer.call(server, :get)

  # --- Server callbacks (private — delegate to pure logic) ---
  @impl true
  def init(opts) do
    initial = Keyword.get(opts, :initial, 0)
    {:ok, %{count: initial}}
  end

  @impl true
  def handle_call(:increment, _from, state) do
    new_state = %{state | count: state.count + 1}
    {:reply, new_state.count, new_state}
  end

  def handle_call(:get, _from, state), do: {:reply, state.count, state}

  @impl true
  def handle_info(msg, state) do
    Logger.warning("Unexpected message: #{inspect(msg)}")
    {:noreply, state}
  end
end
```

### 9.4 call vs cast — decision table

| Use call when... | Use cast when... |
|---|---|
| The caller needs a reply (value, confirmation) | Fire-and-forget (logging, metrics, notifications) |
| Consistency matters and caller should block until done | High throughput; losing a message is acceptable |
| You want natural backpressure (slow server = slow caller) | Independent side effect (PubSub broadcast) |
| Failure should propagate to the caller | The server can handle failure internally |

**Default to `call`.** `cast` silently drops messages when the mailbox overflows; `call` gives you a crash with a meaningful timeout.

### 9.5 GenServer callback returns — decision table

| Return | Meaning |
|---|---|
| `{:reply, reply, state}` | Normal reply, continue |
| `{:reply, reply, state, timeout}` | Reply, then `:timeout` message if no activity in `timeout` ms |
| `{:reply, reply, state, :hibernate}` | Reply, then compact memory (for rarely-used long-lived processes) |
| `{:reply, reply, state, {:continue, term}}` | Reply, then invoke `handle_continue/2` before next message |
| `{:noreply, state}` | No reply yet — will reply later via `GenServer.reply/2` |
| `{:stop, reason, reply, state}` | Reply, then terminate with `reason` |
| `{:stop, reason, state}` (no reply) | Terminate without reply |

**`handle_continue/2` — use it when `init/1` has expensive work:**

```elixir
@impl true
def init(opts) do
  {:ok, %{}, {:continue, :load_data}}   # Return fast, keep supervision snappy
end

@impl true
def handle_continue(:load_data, state) do
  data = MyApp.Data.load_all()          # Expensive, runs AFTER init returns
  {:noreply, %{state | data: data}}
end
```

### 9.6 GenServer rules (LLM)

1. **ALWAYS provide a client API** — callers use `MyServer.get/1`, not `GenServer.call(pid, :get)`
2. **NEVER block in a callback** — no HTTP, no DB queries, no `Process.sleep`. Offload via `Task` or `handle_continue`
3. **NEVER put business logic in callbacks** — delegate to pure functions
4. **ALWAYS set explicit timeouts on `GenServer.call`** — the default 5000ms is often wrong
5. **ALWAYS use the same via-tuple to call** a process that was registered with one
6. **ALWAYS implement `format_status/1`** on GenServers holding sensitive data (tokens, passwords)
7. **PREFER `handle_continue/2`** over crashing `init/1` for expensive initialization

### 9.7 Supervisor strategies — decision table

| Strategy | Restarts | Use when |
|---|---|---|
| `:one_for_one` | Only the crashed child | Children are independent (most common) |
| `:rest_for_one` | Crashed child + all started AFTER it | Later children depend on earlier ones |
| `:one_for_all` | All children | Children are tightly coupled (crash together) |

**Canonical layout:**

```elixir
defmodule MyApp.Application do
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      MyAppWeb.Telemetry,             # 1. Instrumentation first
      MyApp.Repo,                     # 2. DB
      {Phoenix.PubSub, name: MyApp.PubSub},    # 3. PubSub
      {Task.Supervisor, name: MyApp.TaskSupervisor},
      MyApp.WorkerRegistry,           # 5. Registry BEFORE DynamicSupervisor
      MyApp.WorkerSupervisor,         # 6. Dynamic workers
      MyAppWeb.Endpoint               # 7. HTTP endpoint LAST
    ]
    Supervisor.start_link(children, strategy: :one_for_one, name: MyApp.Supervisor)
  end
end
```

**Ordering rule:** Infrastructure (Telemetry, Repo, PubSub) first → domain workers → HTTP endpoints last. HTTP endpoint depending on everything below it.

### 9.8 DynamicSupervisor + Registry — canonical template

```elixir
# Registry — must start BEFORE DynamicSupervisor
defmodule MyApp.WorkerRegistry do
  def child_spec(_), do: Registry.child_spec(keys: :unique, name: __MODULE__)
  def via(id), do: {:via, Registry, {__MODULE__, id}}
end

# DynamicSupervisor — starts worker children on demand
defmodule MyApp.WorkerSupervisor do
  use DynamicSupervisor
  def start_link(_), do: DynamicSupervisor.start_link(__MODULE__, :ok, name: __MODULE__)

  @impl true
  def init(:ok), do: DynamicSupervisor.init(strategy: :one_for_one)

  def start_worker(id, opts \\ []) do
    DynamicSupervisor.start_child(__MODULE__, {MyApp.Worker, [id: id] ++ opts})
  end
end

# Worker registers via the Registry helper
defmodule MyApp.Worker do
  use GenServer
  def start_link(opts) do
    id = Keyword.fetch!(opts, :id)
    GenServer.start_link(__MODULE__, opts, name: MyApp.WorkerRegistry.via(id))
  end

  # Client always calls via() — never the raw id atom
  def call(id, msg), do: GenServer.call(MyApp.WorkerRegistry.via(id), msg)
  # ...
end

# In application.ex (Registry MUST be before DynamicSupervisor):
children = [MyApp.WorkerRegistry, MyApp.WorkerSupervisor]
```

### 9.9 Task — when and how

| Need | Use |
|---|---|
| Fire-and-forget side effect, supervised | `Task.Supervisor.start_child(MyApp.TaskSupervisor, fn -> ... end)` |
| Await a single result, linked | `Task.async/1` + `Task.await/2` |
| Await a result WITHOUT link (handle :DOWN yourself) | `Task.Supervisor.async_nolink/3` |
| Parallel map with concurrency control | `Task.async_stream/3,5` |
| Many small CPU-bound transforms | `Task.async_stream(ordered: false, max_concurrency: schedulers)` |

```elixir
# Parallel map, default ordered, auto concurrency
urls
|> Task.async_stream(&fetch/1, timeout: 10_000)
|> Enum.map(fn
  {:ok, result} -> result
  {:exit, reason} -> {:error, reason}
end)

# Ordered: false when order doesn't matter — slightly faster
files
|> Task.async_stream(&process/1, ordered: false, max_concurrency: 8)
|> Stream.run()
```

**`async` vs `async_nolink` inside a GenServer:**

```elixir
# PREFER async_nolink so task crash doesn't kill the GenServer
def handle_call(:start_fetch, _from, state) do
  task = Task.Supervisor.async_nolink(MyApp.TaskSupervisor, fn -> fetch() end)
  {:reply, :ok, %{state | task_ref: task.ref}}
end

def handle_info({ref, result}, %{task_ref: ref} = state) do
  Process.demonitor(ref, [:flush])
  {:noreply, %{state | task_ref: nil, last_result: result}}
end

def handle_info({:DOWN, ref, :process, _pid, _reason}, %{task_ref: ref} = state) do
  {:noreply, %{state | task_ref: nil}}
end
```

### 9.10 ETS — when to choose it over GenServer

| Situation | Table options |
|---|---|
| High-read, low-write cache, multiple readers | `[:named_table, :public, read_concurrency: true]` |
| Many writers to different keys | Add `write_concurrency: true` |
| Only the owner writes, many readers | `[:named_table, :protected, read_concurrency: true]` |
| Only the owner reads and writes | `[:named_table, :private]` |
| Sorted access by key | `:ordered_set` instead of `:set` (default) |

```elixir
# Owner creates the table in init/1
def init(_) do
  :ets.new(:my_cache, [:named_table, :public, read_concurrency: true])
  {:ok, %{}}
end

# Readers from ANY process use the table directly — no GenServer bottleneck
def get(key) do
  case :ets.lookup(:my_cache, key) do
    [{^key, value}] -> {:ok, value}
    [] -> :error
  end
end

# Atomic increment without a GenServer
:ets.update_counter(:stats, :requests, {2, 1}, {:requests, 0})
```

**Rule:** if your GenServer is *just* wrapping a map with `get`/`put`, replace it with ETS.

### 9.11 Process state — what to store

| Store in state | Store elsewhere |
|---|---|
| Small (<10KB) working state | Large blobs → ETS |
| Configuration refs (pids, atoms, module names) | Caches → ETS / :persistent_term |
| Task references awaiting results | Counters → :counters / :atomics |
| Per-instance identity (user_id, session_id) | Shared app config → Application env |
| State that must survive only while process is alive | State that must survive crash → DB / persistent term |

### 9.12 Common OTP anti-patterns

```elixir
# BAD — GenServer.call for reads on a hot path (bottleneck)
def get(key), do: GenServer.call(__MODULE__, {:get, key})
# Every reader serializes through the GenServer.

# GOOD — direct ETS read
def get(key) do
  case :ets.lookup(:my_table, key) do
    [{^key, v}] -> {:ok, v}
    [] -> :error
  end
end
```

```elixir
# BAD — partial state update (crash between steps = corrupt state)
def handle_call(:transfer, _from, state) do
  state = update_in(state.a, & &1 - 100)
  external_api_call()                      # May crash here
  state = update_in(state.b, & &1 + 100)
  {:reply, :ok, state}
end

# GOOD — compute new state fully, then return atomically
def handle_call(:transfer, _from, state) do
  :ok = external_api_call()                # If this crashes, state is unchanged
  new_state =
    state
    |> update_in([:a], & &1 - 100)
    |> update_in([:b], & &1 + 100)
  {:reply, :ok, new_state}
end
```

```elixir
# BAD — starting a Registry and DynamicSupervisor under :one_for_one
# If Registry crashes, the DynamicSupervisor's children can't re-register
children = [
  {Registry, keys: :unique, name: MyApp.Registry},
  {DynamicSupervisor, name: MyApp.DynSup}
]
Supervisor.init(children, strategy: :one_for_one)  # WRONG

# GOOD — :rest_for_one so Registry restart cascades to DynSup
Supervisor.init(children, strategy: :rest_for_one)
```

---

## 10. Architecture — Key Decisions While Implementing

> **Depth:** For upfront project design (umbrella vs single, context splits, data ownership across bounded contexts, architectural styles, resilience patterns, growing from small to large), load `elixir-planning` and in particular its `architecture-patterns.md`, `data-ownership-deep.md`, and `integration-patterns.md`.

When you're implementing code, you encounter architectural decisions at a smaller scale: where does this function live, which module owns this data, should this be a behaviour? This section covers those in-the-moment decisions. For upfront project design (umbrella vs single, context split planning, data ownership across bounded contexts), load `elixir-planning`.

### 10.1 Context modules — the public API boundary

**Contexts are the public API of a domain.** Controllers, LiveViews, CLI, scheduled jobs → call the context. Contexts → call Ecto / internal modules.

```elixir
defmodule MyApp.Catalog do
  @moduledoc "Product catalog — public API for all product operations."
  alias MyApp.Catalog.{Product, PriceCalculator}
  alias MyApp.Repo

  # Thin pass-through → defdelegate
  defdelegate get_product!(id), to: Product, as: :fetch!

  # Wrapper with added logic → regular def
  def calculate_price(product, qty) do
    product
    |> PriceCalculator.total(qty)
    |> tap(fn total -> :telemetry.execute([:catalog, :priced], %{total: total}) end)
  end
end
```

```elixir
# Internal modules — @moduledoc false, never called from outside the context
defmodule MyApp.Catalog.PriceCalculator do
  @moduledoc false
  def total(product, qty), do: Decimal.mult(product.price, qty)
end
```

**Rules:**

- The context module file lives directly under `lib/my_app/`: `lib/my_app/catalog.ex`
- Internal modules live in a subdirectory: `lib/my_app/catalog/product.ex`, `lib/my_app/catalog/price_calculator.ex`
- Cross-context calls go through the context public API, never into internals

### 10.2 Behaviour vs protocol — the polymorphism decision

Elixir has two polymorphism mechanisms. Elixir-wide rule: **default to a plain module** — introduce either mechanism only when a real second implementation or test double exists.

> **Depth:** [idioms-reference.md](idioms-reference.md) §Protocols and §Behaviours — full templates including `@derive`, `@fallback_to_any`, `@undefined_impl_description`, `Enumerable`/`Collectable`/`Inspect` implementation patterns, `use` + `defoverridable`, Mox integration, consolidation, common anti-patterns. **Architectural decision** (behaviour design, contract evolution, protocol-on-struct strategy pattern): `../elixir-planning/architecture-patterns.md` §4.7–4.11.

**Quick decision:**

| When you need to... | Use |
|---|---|
| Dispatch on **module identity** chosen at config time (which mailer, which HTTP client) | Behaviour |
| Dispatch on **data type** (polymorphic serialization, iteration, inspection) | Protocol |
| Testable with Mox | Behaviour (Mox requires a behaviour) |
| Single implementation chosen per environment (test vs prod) | Behaviour + `Application.compile_env` |
| Many implementations, auto-dispatched by struct type | Protocol (`@derive` friendly) |
| Add behaviour to a type you don't own | Protocol (implement `defimpl` from your module) |
| Runtime-pluggable per-entity behaviour (not per-env) | Protocol-on-struct (see planning §4.6) |

### 10.3 Behaviours — define, implement, test

**Define the contract:**

```elixir
defmodule MyApp.Mailer do
  @type result :: :ok | {:error, term()}

  @callback send_welcome(User.t()) :: result()
  @callback send_reset(User.t(), token :: String.t()) :: result()

  @callback batch_send([User.t()]) :: result()
  @optional_callbacks batch_send: 1
end
```

**Implement it:**

```elixir
defmodule MyApp.Mailer.Swoosh do
  @behaviour MyApp.Mailer

  @impl true
  def send_welcome(user), do: # real Swoosh call
  @impl true
  def send_reset(user, token), do: # real Swoosh call
end
```

**`@impl` is mandatory** — the compiler catches typos (`hanle_call` vs `handle_call`) and missing implementations at compile time.

**Wire config — swap per environment:**

```elixir
# config/config.exs
config :my_app, :mailer, MyApp.Mailer.Swoosh

# config/test.exs
config :my_app, :mailer, MyApp.Mailer.Mock     # Mox.defmock/2

# Call site
@mailer Application.compile_env!(:my_app, :mailer)
def notify(user), do: @mailer.send_welcome(user)
```

**Testing with Mox:**

```elixir
# test/test_helper.exs
Mox.defmock(MyApp.Mailer.Mock, for: MyApp.Mailer)

# In a test
expect(MyApp.Mailer.Mock, :send_welcome, fn %User{email: "a@b.c"} -> :ok end)
assert :ok = MyApp.Onboarding.run(user)
```

**Defaults via `use`** when most implementations would share the same code:

```elixir
defmodule MyApp.Worker do
  @callback perform(map()) :: :ok | {:error, term()}
  @callback retry_delay(attempt :: non_neg_integer()) :: pos_integer()

  defmacro __using__(_) do
    quote do
      @behaviour MyApp.Worker
      @impl true
      def retry_delay(attempt), do: trunc(:math.pow(2, attempt) * 1_000)
      defoverridable retry_delay: 1
    end
  end
end
```

### 10.4 Protocols — define, implement, derive

**Define:**

```elixir
defprotocol MyApp.Printable do
  @spec print(t()) :: iodata()
  def print(term)
end
```

**Implement for structs:**

```elixir
defmodule MyApp.User do
  defstruct [:name, :email]

  defimpl MyApp.Printable do
    def print(%{name: n, email: e}), do: [n, " <", e, ">"]
  end
end
```

**Implement for built-in types** (`Atom`, `BitString`, `Integer`, `List`, `Map`, `Tuple`, etc.):

```elixir
defimpl MyApp.Printable, for: BitString do
  def print(s) when is_binary(s), do: s
end

defimpl MyApp.Printable, for: [Integer, Float] do
  def print(n), do: to_string(n)
end
```

**`@derive` — compile-time generated implementation:**

```elixir
defmodule MyApp.User do
  # @derive MUST come BEFORE defstruct
  @derive {Jason.Encoder, only: [:id, :name, :email]}    # selective JSON encoding
  @derive {Inspect, only: [:id, :name]}                   # hide password from logs
  defstruct [:id, :name, :email, :password_hash]
end
```

For foreign structs you don't own:

```elixir
require Protocol
Protocol.derive(Jason.Encoder, SomeLib.Thing, only: [:id])
```

**Anti-patterns:** `@derive` after `defstruct` (compiler warns, may not apply); `defimpl for: Map` expecting to match structs (structs dispatch separately); introducing a behaviour when a protocol fits (strategy-module is a behaviour; type-dispatch is a protocol).

### 10.5 Config strategy — when to use which

| Value | File | API |
|---|---|---|
| Known at compile time, application-owned | `config/config.exs` | `Application.compile_env(:my_app, :key)` |
| Runtime env var, per-deployment | `config/runtime.exs` | `System.fetch_env!/1`, `Application.get_env/2` |
| Library consumer configures at runtime | Caller's `config/*.exs` | `Application.get_env/3` (NEVER `compile_env` in a library) |
| Feature flag, toggleable at runtime | Database / FunWithFlags / Flagsmith | Library-specific |

```elixir
# Application code — compile_env is fine
defmodule MyApp.Cache do
  @ttl Application.compile_env!(:my_app, [:cache, :ttl])
  def ttl, do: @ttl
end

# LIBRARY code — use get_env so consumers can reconfigure after compilation
defmodule MyLib.Client do
  def api_key, do: Application.get_env(:my_lib, :api_key)
end
```

**Default for app-owned config: `compile_env`** — **but only when the value is truly frozen at compile time.** Reach for `get_env` when ANY of these are true:

- `config/runtime.exs` overrides the key from an env var (compile_env freezes the default; runtime.exs never takes effect).
- Tests override the key with `Application.put_env/3` (same reason — compile_env ignores runtime writes).
- The value can change during a running node (feature flag, per-request override).

If none of those apply, `compile_env` wins for three reasons:

1. **Dialyzer visibility** — `compile_env` embeds the concrete type; `get_env` returns `any()`.
2. **Fail-fast misconfiguration** — a missing required key crashes at compile, not at first use.
3. **Recompile trigger** — the compiler re-runs modules that depend on changed compile-env keys.

```elixir
# BAD — app-owned constant read on every call, returns any()
def default_timeout, do: Application.get_env(:my_app, :default_timeout, 5_000)

# GOOD — value is truly constant, no runtime.exs override, no test swap
@default_timeout Application.compile_env(:my_app, :default_timeout, 5_000)
def default_timeout, do: @default_timeout
```

```elixir
# When runtime.exs overrides the value, stay on get_env
# config/runtime.exs:
#   if config_env() == :prod do
#     config :my_app, port: System.get_env("MY_APP_PORT", "4040") |> parse_port()
#   end
#
# GOOD — get_env reflects the runtime.exs override at boot
def port, do: Application.get_env(:my_app, :port, 4040)
```

**Diagnostic:** before switching `get_env` to `compile_env`, grep for the key in `config/runtime.exs` AND in every test file. If either overrides it at runtime, leave `get_env` in place and document the choice in a moduledoc line — future reviewers will ask, and the answer should be findable.

### 10.6 Ecto — the implementation boundary

**Never call `Repo` from a boundary layer (controller, LiveView, CLI). Always go through a context.**

```elixir
# BAD — Repo from a controller
def index(conn, _) do
  products = Repo.all(Product)
  render(conn, :index, products: products)
end

# GOOD — controller calls context
def index(conn, _) do
  products = Catalog.list_products()
  render(conn, :index, products: products)
end
```

**Context-level query function template:**

```elixir
defmodule MyApp.Catalog do
  import Ecto.Query

  @spec list_products(keyword()) :: [Product.t()]
  def list_products(opts \\ []) do
    opts = Keyword.validate!(opts, category: nil, in_stock: nil, limit: 50)

    Product
    |> maybe_filter_by_category(opts[:category])
    |> maybe_filter_by_stock(opts[:in_stock])
    |> limit(^opts[:limit])
    |> order_by([p], desc: p.inserted_at)
    |> Repo.all()
  end

  defp maybe_filter_by_category(q, nil), do: q
  defp maybe_filter_by_category(q, c), do: where(q, [p], p.category == ^c)

  defp maybe_filter_by_stock(q, nil), do: q
  defp maybe_filter_by_stock(q, in_stock?), do: where(q, [p], p.in_stock == ^in_stock?)
end
```

### 10.7 Struct vs map — decision table

| When you have... | Use |
|---|---|
| Known fields at compile time, owned by you | Struct (`defstruct`, `@enforce_keys`) |
| Dynamic keys, or shape varies | Map |
| External data (JSON, form params) at the boundary | Map with string keys — convert to struct inside |
| "Object-like" data with validation rules | Embedded Ecto schema (`embedded_schema`) |
| Parsed configuration | Struct with `@enforce_keys` |
| Options argument | Keyword list, validated with `Keyword.validate!/2` |

**Struct template:**

```elixir
defmodule MyApp.Settings do
  @enforce_keys [:env, :url]                      # Fail fast if these are missing
  defstruct [:env, :url, timeout: 5_000, retries: 3]

  @type t :: %__MODULE__{
          env: :dev | :staging | :prod,
          url: String.t(),
          timeout: non_neg_integer(),
          retries: non_neg_integer()
        }

  @spec new(keyword()) :: t()
  def new(attrs), do: struct!(__MODULE__, attrs)
end
```

### 10.8 Function placement — where does this code live?

| This function... | Belongs in |
|---|---|
| Transforms a domain struct (pure) | The struct's module (e.g., `User.full_name/1`) |
| Queries the DB for domain data | Context module (e.g., `Accounts.get_user!/1`) |
| Orchestrates multiple contexts or external services | Context module (e.g., `Accounts.register/1` calls Mailer) |
| Is a shared helper (string, number, date) | `MyApp.Utils.Foo` or dedicated helper module |
| Cross-cuts many modules (auth, rate limit, telemetry) | Plug / middleware / separate module |
| Is test-only | `test/support/*.ex` |
| Is a DSL / macro | Separate module, well-documented, usually internal |

### 10.9 File / module layout — canonical Phoenix-app example

```
lib/
  my_app/
    application.ex            # Application supervisor
    accounts.ex               # Accounts context (public API)
    accounts/
      user.ex                 # User schema + changeset
      session.ex              # Session schema
      authenticator.ex        # Password hashing (internal)
    catalog.ex
    catalog/
      product.ex
      price_calculator.ex
    orders.ex
    orders/
      order.ex
      line_item.ex
      workflow.ex
    mailer.ex                 # Behaviour
    mailer/
      swoosh.ex               # Real impl
  my_app_web/
    endpoint.ex
    router.ex
    controllers/...
    live/...
config/
  config.exs
  dev.exs
  test.exs
  runtime.exs
test/
  my_app/accounts_test.exs
  my_app/catalog_test.exs
  my_app_web/controllers/...
  support/
    data_case.ex
    factory.ex
    conn_case.ex
test_helper.exs
mix.exs
```

---

## 11. Domain Handoffs — When to Load a Specialized Skill

This skill covers idiomatic Elixir writing. For domain-specific depth, load the specialized skill for that domain. Each handoff row tells you the trigger ("I'm now writing X") and what to load.

| When you're implementing... | Load this skill (in addition) |
|---|---|
| Phoenix controllers, routers, views, plugs, forms, contexts end-to-end | `phoenix` |
| LiveView — mount/handle_event, streams, uploads, hooks, async assigns | `phoenix-liveview` |
| Ash Framework — resources, actions, policies, extensions | `ash` |
| Nerves firmware — VintageNet, device trees, OTA, hardware GPIO | `nerves` |
| Rust NIFs via Rustler — bindings, encoders, resources, dirty schedulers | `rust-nif` |
| State machines — `gen_statem`, `GenStateMachine`, AshStateMachine | `state-machine` |
| Event sourcing — Commanded, aggregates, projections, process managers | `event-sourcing` |
| Non-trivial testing — property-based depth, LiveView tests, channels, Oban tests, ExVCR, Wallaby | `elixir-testing` |
| OTP deep-dive — GenStage, Broadway, hot upgrades, distribution patterns | `otp` |
| Desktop apps — Elixir Desktop, Tauri integration | `elixir-desktop` / `tauri-elixir` |
| Membrane streaming pipelines | `membrane` |
| Code generation / project patching / Mix tasks (Igniter) | `igniter` |
| Production deployment — Mix releases, Docker, Kubernetes, observability | `elixir-deployment` |
| Livebook notebooks (smart cells, Kino, VegaLite) | `livebook` |
| Multi-node Elixir + microcontrollers (AtomVM, RPC bridges) | `erpc` |
| TCP/UDP socket programming, protocol framing, binary protocols | For now, the `elixir` skill's `networking.md` file — `elixir-implementing` does not duplicate that content |
| Ecto deep — custom types, CTEs, window functions, multi-tenancy | For now, the `elixir` skill's `ecto-*.md` files — covered here at §10.6 level for daily use |

**How to load:** mention the skill in a system reminder or invoke via the Skill tool. The trigger phrases in each skill's description auto-activate them.

**Rule of thumb:** This skill has enough for 80% of daily Elixir coding. For the remaining 20% (specialized domain depth), load the relevant specialized skill *in addition to* this one — they work together.

---

## 12. Quick References — Stdlib Cheat Sheets

> **Depth:** [stdlib-cheatsheet.md](stdlib-cheatsheet.md) — dense signature lookups for `Enum`, `Map`, `Keyword`, `List`, `String`, `File`/`Path`/`System`, `Regex`, `Date`/`Time`, `Process`, Erlang stdlib picks (`:timer`, `:queue`, `:ets`, `:persistent_term`, `:crypto`, `:rand`, `:math`), `JSON`/`Jason`, `URI`/`Base`, `Access`/nested data, `Logger`, supervision child specs. Load when you need a call signature fast and don't need the full reference.

For the full stdlib reference (every function with parameters and examples), load the parent `elixir` skill's `quick-references.md`.

---

## 13. Related Skills

### Elixir family (recommended companions)

- **`elixir-planning`** — Upfront architecture: project layout, context splitting, supervision shape, data ownership, umbrella-vs-single decisions. Load before starting a new project or major restructure.
- **`elixir-reviewing`** — Review checklist, anti-pattern catalog, "is this idiomatic?" decision trees. Load when reviewing PRs or auditing existing code.
- **`elixir`** — The original comprehensive Elixir skill with many reference subfiles (architecture-reference, language-patterns, ecto-reference, otp-reference, networking, etc.). Use for deep topic dives that this concise skill doesn't cover.
- **`elixir-testing`** — Deep testing reference: property-based depth, ExVCR, Wallaby, channel / LiveView testing at the full API level, OTP process testing patterns. `elixir-implementing` covers the daily 80%; load this for the 20%.

### Framework and domain skills

- **`phoenix`** — Phoenix framework architecture, controllers, plugs, forms, router, channels, PubSub, security.
- **`phoenix-liveview`** — LiveView specifics: lifecycle, components, streams, uploads, hooks, async.
- **`ash`** — Ash Framework: declarative resources, policies, actions, extensions.
- **`state-machine`** — `gen_statem`, `GenStateMachine`, AshStateMachine patterns.
- **`event-sourcing`** — Commanded library, aggregates, projections, process managers.
- **`otp`** — Deep OTP: GenStage, Broadway, hot upgrades, distribution.
- **`nerves`** — Embedded Elixir firmware.
- **`rust-nif`** — Rustler NIFs.
- **`igniter`** — Code generation and project patching.
- **`elixir-deployment`** — Mix releases, Docker, Kubernetes, observability.

### Cross-reference summary (for trivial queries — avoid loading unless needed)

- **Phoenix:** contexts are the public API boundary; routes → controllers → contexts → schemas. Plugs are composable middleware.
- **LiveView:** `mount → handle_params → render`; use streams for large collections; assign everything in `mount/3`.
- **Ash:** resources declare data + behavior; policies authorize; actions mutate.
- **OTP deep:** `gen_statem` for complex FSMs; PartitionSupervisor to shard one-GenServer bottlenecks; `:persistent_term` for hot-path config.
- **Ecto deep:** `Repo.transact/2` (not `transaction/2`); validations run before DB, constraints after; `Multi` for atomic multi-step; composable query functions with pipes.

---

**End of SKILL.md.** This skill is optimized for the moment of writing Elixir — decision tables first, templates second, rules and BAD/GOOD as validators. For upfront design, load `elixir-planning` (when available) alongside this skill. For review, load `elixir-reviewing` (when available).
