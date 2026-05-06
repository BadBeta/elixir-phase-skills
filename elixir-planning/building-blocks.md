# Building Blocks — A Planning-First Concept

**A "building block" is a module whose public API is composable, testable in isolation, and free of hidden inputs.** Property tests work on building blocks. Generative testing works on building blocks. They compose without surprises because every constraint they impose is at the boundary, not the implementation.

This subskill turns the building-block concept into a **planning-time decision**: every new module starts as "is this a building-block, or an orchestrator?" before any code is typed. The Archdo `Archdo.Blackbox` analyzer enforces it post-write; this subskill is the design lens that makes that enforcement easy to satisfy.

> **Architecture cross-reference:** building-blocks compose into contexts; the context's *orchestrator shell* connects them to side effects. See `architecture-patterns.md` §4.6 for the orchestrator pattern.

---

## 1. Rules for Building Blocks (LLM)

1. **ALWAYS classify a new module as `building_block` / `orchestrator` / `interface`** before writing code. The classification dictates the rules below — you can't deviate from a building-block's discipline mid-implementation without leaks.
2. **ALWAYS run the §3 checklist on every public function in a building-block module** before declaring the module done. Six structural axes plus one input-guard axis — each has a concrete pass/fail criterion.
3. **NEVER mix orchestrator concerns into a building-block module.** A single `Logger.info/1`, `Repo.insert/1`, `DateTime.utc_now/0`, or `Application.get_env/2` reduces the whole module to "near-block" status. Move those calls to the orchestrator that calls into the building-block.
4. **ALWAYS prefer `extract` over `refactor in place`** when a module mixes pure and impure functions and the pure ones don't depend on the impure ones — splitting yields a clean building-block plus a small orchestrator shell.
5. **NEVER weaken the checklist for "small enough" or "internal" modules.** Internal modules score against the same six axes; the cost of a hidden `Application.get_env` is identical whether the module is 10 lines or 1000.
6. **ALWAYS write the building-block's tests as property tests** (StreamData) when the inputs have an obvious generator. The whole reason to invest in building-block discipline is that property tests become trivial — if you're not getting that payoff, you've left a leak somewhere.
7. **ALWAYS document the input domain in the `@spec`.** A building-block's input space is closed by definition (constrained types or constrained guards); the `@spec` makes it consumable to Dialyzer and to property generators.
8. **NEVER hide a building-block behind a `defp`-only API.** Building-blocks earn their value at the public boundary — they're the units of composition. Test-only or helper-only "building-blocks" inside a single module miss the point.
9. **ALWAYS aggregate at the context level.** A *context* is a building-block when every module under its namespace is a building-block (orchestrators excluded — they live OUTSIDE the building-block context, often as a sibling `MyApp.Orders.Workflow` next to `MyApp.Orders`). See §6 Context-as-building-block.
10. **ALWAYS measure refactor distance** (Archdo `refactor_distance/1`) on candidate modules before promising to "make it pure later". Distance ≥ 5 is honestly an orchestrator that should be named as such; distance 1–2 is a 30-minute refactor.

---

## 2. The Three Module Classifications

Every module gets exactly one classification at planning time. Pick deliberately; mixing is the root cause of every "this module is hard to test" complaint.

| Classification | Example | Hidden input | Side effects | Tests look like |
|---|---|---|---|---|
| **Building block** | `MyApp.Pricing`, `MyApp.OrderRules`, `MyApp.Tokens`, `MyApp.SlugGen` | None — every value comes from arguments | None — return data only | Property tests, plain ExUnit, no setup |
| **Orchestrator** | `MyApp.Orders.Workflow`, `MyApp.Accounts.Registration`, `MyApp.Webhooks.Dispatcher` | Repo, Application env, clock, PubSub, telemetry | Persists, broadcasts, schedules, logs | DataCase + Mox at boundaries |
| **Interface** | `MyAppWeb.UserController`, `MyApp.Workers.SendEmail`, `MyApp.CLI.Run` | Conn / Job / argv / socket | Translates input ↔ output, delegates to orchestrator | ConnCase / Channel / Worker test |

**Rule of thumb sizes:**
- A typical Phoenix context owns 1–3 building-block modules + 1 orchestrator module + Ecto schemas.
- A typical Nerves firmware owns many small building-blocks + 1 orchestrator GenServer per device subsystem.
- An umbrella subapp can BE a single building-block when its public API is all pure (e.g., a parser library).

**The classification is part of the moduledoc:**

```elixir
defmodule MyApp.Pricing do
  @moduledoc """
  Building block — pure pricing math.

  Inputs are validated `Decimal`s; outputs are `{:ok, Decimal.t()}` /
  `{:error, atom()}`. No DB, no clock, no logger. Property-tested
  in `test/my_app/pricing_property_test.exs`.
  """
end
```

---

## 3. The Building-Block Checklist ⛔

Run this on every public function in a candidate building-block module **before declaring the module done**. Each axis has a concrete pass/fail. Failing any axis means the function is not a building-block. Failing any function in the module means the module is not a building-block.

### 3.1 Six structural axes (Archdo Blackbox)

#### ✅ Axis 1 — Input closure
**Definition:** Every value the function reads comes from its argument list.

**Fail signals:**
- `Application.get_env/2,3`, `Application.fetch_env/2`, `Application.compile_env/2,3`
- `Process.get/1`, `Process.put/2`
- `:persistent_term.get/1`
- `:ets.lookup/2`, `:ets.tab2list/1`

**Pass:** Zero hits of the above in the function body. If you need configuration, take it as an argument or in `state` passed by the orchestrator.

```elixir
# FAIL — hidden input
def discount(price), do: price * (1 - Application.get_env(:my_app, :default_rate))

# PASS — input is closed
def discount(price, rate) when is_struct(price, Decimal) and is_float(rate),
  do: Decimal.mult(price, Decimal.from_float(1 - rate))
```

#### ✅ Axis 2 — Determinism
**Definition:** Same inputs always produce same outputs.

**Fail signals:**
- `DateTime.utc_now/0`, `DateTime.now/1`, `NaiveDateTime.utc_now/0`, `Date.utc_today/0`, `Time.utc_now/0`
- `System.system_time/0,1`, `System.monotonic_time/0,1`, `System.os_time/0,1`, `System.unique_integer/0,1`
- `:rand.uniform/0,1`, `:rand.uniform_real/0`
- `:erlang.system_time`, `:erlang.unique_integer`, `:erlang.monotonic_time`, `:os.timestamp/0`

**Pass:** Zero hits of the above. If you need "now", accept a `now :: DateTime.t()` argument from the orchestrator and pass it down. If you need randomness, accept a `seed` or `rng_state` argument.

```elixir
# FAIL — non-deterministic
def expires_at(ttl_seconds), do: DateTime.add(DateTime.utc_now(), ttl_seconds, :second)

# PASS — orchestrator passes "now"
def expires_at(now, ttl_seconds) when is_struct(now, DateTime) and is_integer(ttl_seconds),
  do: DateTime.add(now, ttl_seconds, :second)
```

#### ✅ Axis 3 — Output completeness (`@spec`)
**Definition:** A complete `@spec` on every public function describes the entire output domain.

**Fail signals:** Missing `@spec`, or `@spec` returning `any()` / `term()`.

**Pass:** Every public function has a `@spec` that names the success and failure shapes specifically.

```elixir
# FAIL — no spec
def parse(input), do: # ...

# FAIL — too loose
@spec parse(String.t()) :: any()
def parse(input), do: # ...

# PASS — fully described
@spec parse(String.t()) :: {:ok, Address.t()} | {:error, :invalid_format | :empty_input}
def parse(input), do: # ...
```

#### ✅ Axis 4 — Totality
**Definition:** Every input the type allows produces an output (no `FunctionClauseError`).

**Fail signals:** Multi-clause function whose patterns are all *specific* — e.g., `def f(:a)`, `def f(:b)` — with no catch-all clause.

**Pass:** Either single-clause with bare arguments, OR multi-clause with a catch-all (`def f(_)` returning `{:error, _}`).

```elixir
# FAIL — no catch-all; f(:c) raises FunctionClauseError
def role(:admin), do: 100
def role(:member), do: 50

# PASS — catch-all returns errors-as-values
def role(:admin), do: 100
def role(:member), do: 50
def role(_), do: {:error, :unknown_role}
```

#### ✅ Axis 5 — Side-effect freedom
**Definition:** The only output is the return value.

**Fail signals:**
- `Logger.{debug,info,notice,warning,error}/1,2`
- `Phoenix.PubSub.broadcast/3,4`, `Phoenix.PubSub.local_broadcast/3,4`
- `Repo.{insert,update,delete}/{1,2}` (and bang variants)
- `:telemetry.execute/3`
- `:ets.insert/2`, `:ets.delete/2`

**Pass:** Zero hits of the above. Move them to the orchestrator. The building-block returns descriptions of effects (e.g., `{:emit, event}`); the orchestrator executes them.

```elixir
# FAIL — logs as a side effect
def validate(attrs) do
  case do_validate(attrs) do
    {:ok, _} = ok -> ok
    {:error, e} -> Logger.warning("validation failed: #{inspect(e)}"); {:error, e}
  end
end

# PASS — return events; orchestrator logs them
def validate(attrs), do: do_validate(attrs)
# In orchestrator:
case Pricing.validate(attrs) do
  {:ok, _} = ok -> ok
  {:error, e} = err -> Logger.warning("validation failed: #{inspect(e)}"); err
end
```

#### ✅ Axis 6 — Errors as values
**Definition:** Failures return `{:error, reason}` tuples — never raise.

**Fail signals:** Any `raise/1,2` call in the function body.

**Pass:** Zero `raise` calls. If a precondition is violated, return `{:error, :precondition_violated}` or pattern-match upfront and document the precondition in the `@spec` / guard.

```elixir
# FAIL — raises on bad input
def parse_age(s) do
  case Integer.parse(s) do
    {n, ""} when n >= 0 -> {:ok, n}
    _ -> raise ArgumentError, "invalid age: #{s}"
  end
end

# PASS — errors as values
@spec parse_age(String.t()) :: {:ok, non_neg_integer()} | {:error, :invalid_age}
def parse_age(s) do
  case Integer.parse(s) do
    {n, ""} when n >= 0 -> {:ok, n}
    _ -> {:error, :invalid_age}
  end
end
```

### 3.2 Seventh axis — Input guard (constrained domain)

**Definition:** Every clause's input space is constrained — by guards, by specific patterns, or by being the explicit `{:error, _}` fallback.

**Fail signal:** A clause has bare-variable arguments (`def f(x, opts)`), no `when` guard, and the body doesn't return `{:error, _}` — meaning the function accepts any input shape with no validation.

**Pass:** At least one of:
- A `when` guard in the clause head (`def f(x) when is_integer(x) and x > 0`)
- All argument patterns are specific (`def f(%MyStruct{}) `, `def f(:atom_a)`)
- The clause is a final `{:error, _}` literal fallback

```elixir
# FAIL — accepts any input
def discount(price, rate), do: # ...

# PASS — guards constrain the domain
def discount(%Decimal{} = price, rate)
    when is_float(rate) and rate >= 0.0 and rate <= 1.0,
    do: # ...

def discount(_, _), do: {:error, :invalid_input}
```

### 3.3 Module-level checklist (aggregate)

A module is a building-block when:

- [ ] At least one public function exists (DSL/behaviour-only modules are NOT building-blocks; they are configuration).
- [ ] Every public function passes axes 1–6 above (each axis ≥ 1.0; geometric product ≥ 0.9 in Archdo's metric).
- [ ] Every public function (with arity > 0) passes axis 7 — input domain is constrained.
- [ ] The moduledoc names the classification: `"Building block — ..."`.
- [ ] A property test file exists at `test/<module>_property_test.exs` (the payoff).

If any box fails, the module is NOT a building-block. Either refactor (see §5) or rename the moduledoc to "Orchestrator" or "Interface" honestly.

### 3.4 Context-level checklist (aggregate)

A context is a building-block when:

- [ ] Every module under the context namespace (`MyApp.Catalog`, `MyApp.Catalog.*`) passes the module-level checklist OR has no public API (DSL config / behaviour declaration).
- [ ] The orchestrator (if any) lives OUTSIDE the context namespace, e.g., `MyApp.Orders.Workflow` for the `MyApp.Orders` building-block context.
- [ ] The context's public API surface is intentional — no leaks via `defdelegate` to internal impure helpers.

---

## 4. Decision: Is This Module a Building Block?

Walk this at the moment of creating the module:

```
Q1. Does the module need to read from outside its arguments?
    (Application env, ETS, persistent_term, Process dict)
    YES → orchestrator. Stop, name it accordingly.
    NO  → continue.

Q2. Does the module produce side effects?
    (DB writes, logs, telemetry, PubSub, ETS writes)
    YES → orchestrator. Stop.
    NO  → continue.

Q3. Does the module need "now" / random / unique ID?
    YES → it's a building-block IF the caller supplies these as args.
          Otherwise it's an orchestrator that calls a building-block.
    NO  → continue.

Q4. Can every input shape be handled by the function?
    (Either constrain via guards, or have a {:error, _} fallback.)
    YES → continue.
    NO  → add the constraint or the fallback first.

Q5. Will I write a property test for this?
    YES → great, you have a building-block.
    NO  → ask why. If "it's too coupled to do that", you have an
          orchestrator pretending to be pure. Reclassify or refactor.
```

**Heuristic — when in doubt:** look at the imports. A building-block module typically imports / aliases:

- Other building-blocks (your own pure modules)
- Pure stdlib (Decimal, MapSet, Enum, String, Integer, …)
- Schemas / structs (data-only)

It does NOT import / alias:

- `MyApp.Repo`
- `Phoenix.PubSub` / `MyApp.Mailer`
- `Logger` (in function bodies — `require Logger` at module level is fine if unused at runtime)
- `Application`

If your candidate building-block reaches for any module in the second list, it's an orchestrator.

---

## 5. Refactor Decisions When a Module Mixes Pure and Impure

When you have a candidate module that's PARTIALLY a building-block, Archdo's `Blackbox.boundary_suggestion/1` returns one of three verdicts. Use the same logic at planning time:

### 5.1 `:building_block` — already there
Nothing to do. Promote the moduledoc, add a property test if missing.

### 5.2 `{:extract, leaky_fns, pure_fns}` — split is clean
The pure functions don't call the leaky ones. Extract `leaky_fns` into an orchestrator (typically `MyApp.Catalog.Workflow` or similar), leaving `pure_fns` as a building-block.

```elixir
# BEFORE — mixed
defmodule MyApp.Catalog do
  def calculate_total(items, rate), do: # pure math
  def normalize_sku(sku), do: # pure
  def list_products, do: Repo.all(Product)        # impure
  def insert_product(attrs), do: Repo.insert(...) # impure
end

# AFTER — extract leaves a building-block
defmodule MyApp.Catalog do
  @moduledoc "Building block — catalog math + normalization."
  def calculate_total(items, rate), do: # ...
  def normalize_sku(sku), do: # ...
end

defmodule MyApp.Catalog.Workflow do
  @moduledoc "Orchestrator — catalog persistence + queries."
  alias MyApp.{Catalog, Repo}
  alias MyApp.Catalog.Product

  def list_products, do: Repo.all(Product)
  def insert_product(attrs) do
    # Build the changeset with the pure building-block:
    Product.changeset(%Product{}, attrs) |> Repo.insert()
  end
end
```

### 5.3 `{:refactor_in_place, breakdown}` — pure subset depends on impure
Pure functions call leaky helpers — extracting one without the other breaks callers. Two strategies:

**Strategy A: Inject the impure dependency.** Change the pure function's signature to take the result of the impure call as an argument. The orchestrator does the impure call and threads the result in.

```elixir
# BEFORE — pure helper depends on Application
def discount(price), do: rate = Application.get_env(:my_app, :rate); price * (1 - rate)

# AFTER — config injected
def discount(price, rate) when is_float(rate), do: price * (1 - rate)
# Orchestrator:
def apply_discount(price), do: discount(price, Application.get_env(:my_app, :rate))
```

**Strategy B: Re-evaluate whether a building-block is the right design here.** Sometimes the answer is "this whole module IS a small orchestrator and that's fine". Don't force building-block discipline on intrinsically stateful code (cache invalidation, scheduler, retry executor).

### 5.4 Refactor distance — the ROI ranking

Archdo's `Blackbox.refactor_distance/1` returns the count of failed axes across all public functions. Use it to rank candidate modules:

| Distance | Effort | Action |
|---|---|---|
| 0 | None | Promote moduledoc to "Building block — ..." |
| 1–2 | 30 min | Refactor next sprint; usually one missing `@spec` or one `Logger` to move |
| 3–5 | Half day | Worth doing if the module is on a hot test path or a re-used boundary |
| 6+ | More | Re-evaluate classification; this is probably an orchestrator masquerading |

---

## 6. Context as a Building-Block

A context (`MyApp.Catalog`, `MyApp.Accounts`, …) is a building-block when every module under its namespace is a building-block. The orchestrator lives OUTSIDE — typically as a sibling module like `MyApp.Catalog.Workflow` or in a higher orchestration layer like `MyApp.Workflows.PlaceOrder`.

### 6.1 Canonical building-block context layout

```
lib/my_app/catalog.ex                    # Building-block — public API
lib/my_app/catalog/product.ex            # Building-block — schema + changesets (pure)
lib/my_app/catalog/price_calculator.ex   # Building-block — math
lib/my_app/catalog/sku_normalizer.ex     # Building-block — pure transforms
lib/my_app/catalog/workflow.ex           # Orchestrator — Repo, telemetry, PubSub
```

In this layout the **context** (`MyApp.Catalog`) is a building-block; its workflow is its orchestrator.

### 6.2 When a context CAN'T be a building-block

Some contexts are intrinsically orchestrators:
- Authentication / session (mutates DB on every login)
- Background-job dispatch (enqueues, schedules)
- Real-time connection lifecycle (PubSub subscribe/publish)

Don't fight this — name them honestly. `MyApp.Sessions` IS an orchestrator context. The skill rule is to MAXIMIZE building-block coverage, not to force every context into purity.

### 6.3 What to maximize

For a typical Phoenix app:
- Aim for ≥ 60% of modules under `lib/my_app/` to be building-blocks.
- Aim for ≥ 80% of "domain logic" modules (excluding `_web/`, `Mailer`, `Repo`, schemas+migrations) to be building-blocks.
- Use `Archdo.Blackbox.context_verdict/2` quarterly to track drift.

### 6.4 Converting an existing context into a building-block — workflow

This is the section to read when you have an *existing* context (typically generated by `mix phx.gen.context` or grown organically) that mixes pure logic with `Repo` calls, `Logger`, etc. It's a six-step workflow. Follow it in order — skipping steps produces messy migrations.

#### Step 1 — Run Archdo's verdict on the context

```bash
# Get a per-module breakdown of what's leaking and where:
mix archdo --paths lib/my_app/catalog --format compact \
  | grep -E "CE-54|CE-55|CE-56|CE-57"
```

Or in IEx:

```elixir
file_asts = MyApp.Project.file_asts("lib/my_app/catalog")
Archdo.Blackbox.context_verdict(file_asts, "MyApp.Catalog")
# => {:leaks_at, ["MyApp.Catalog", "MyApp.Catalog.Workflow"]}
```

This gives you a **list of leaky modules** in the context. That list IS the work plan.

#### Step 2 — Per-module: classify the function set

For each leaky module, run `Blackbox.score_module/1` and group its public functions:

```elixir
ast = "lib/my_app/catalog.ex" |> File.read!() |> Code.string_to_quoted!()
Archdo.Blackbox.score_module(ast)
# => [{name, arity, score, components}, ...]
```

Group functions into three sets:

| Set | Criterion | Destination |
|---|---|---|
| **Pure set** (P) | score ≥ 0.9 | Stays in the context module (or a building-block submodule) |
| **Leaky-and-decoupled set** (L₁) | score < 0.9 AND doesn't call P | Moves to `<Context>.Workflow` (orchestrator) |
| **Leaky-and-coupled set** (L₂) | score < 0.9 AND calls P, OR P calls L₂ | Refactor in place: invert the dependency by passing values as args |

#### Step 3 — Decide the public-API contract for the context

Before moving anything, choose one of two API stances:

**Stance A: Context = building-block; orchestrator separate.**
The `MyApp.Catalog` module exposes only pure functions. Callers that need persistence call `MyApp.Catalog.Workflow` directly.

**Stance B: Context = facade that delegates to both.**
`MyApp.Catalog` keeps its public API (callers don't change), but its body is *only* `defdelegate` calls — pure ones to itself, impure ones to `MyApp.Catalog.Workflow`. The context module isn't itself a building-block under this stance, but every module under its namespace except itself is.

**Pick A** when you control all callers and can update them in one PR. **Pick B** when you have many call sites or external API stability matters. Stance B is the safer migration path; you can later promote to Stance A by renaming.

#### Step 4 — Extract leaky-decoupled functions to `<Context>.Workflow`

Move the L₁ set wholesale to `lib/my_app/<context>/workflow.ex`. Update its callers (or use Stance B `defdelegate`). The pure set in the context module is now a building-block on the structural axes — but may still fail input-guard.

```elixir
# BEFORE
defmodule MyApp.Catalog do
  def calculate_total(items, rate), do: # pure
  def list_products, do: Repo.all(Product)        # impure (no P deps)
end

# AFTER
defmodule MyApp.Catalog do
  @moduledoc "Building block — catalog math + normalization."
  def calculate_total(items, rate), do: # pure
end

defmodule MyApp.Catalog.Workflow do
  @moduledoc "Orchestrator — catalog persistence + queries."
  def list_products, do: Repo.all(Product)
end
```

#### Step 5 — Refactor the leaky-coupled set in place (L₂)

For each L₂ function, identify what it reads from the environment (Application env, clock, randomness, ETS) and **lift that read to the caller**. The function takes the value as an argument; the orchestrator does the read.

```elixir
# BEFORE — pure helper depends on Application
defp tax_amount(price), do: Decimal.mult(price, Application.get_env(:my_app, :tax_rate))

# AFTER — config injected; helper is now pure
defp tax_amount(price, rate), do: Decimal.mult(price, rate)

# In Workflow:
def calculate_total_with_tax(items) do
  rate = Application.get_env(:my_app, :tax_rate)
  Catalog.calculate_total(items, rate)
end
```

Apply this systematically until every public function in the building-block layer scores ≥ 0.9 on `Blackbox.score_module/1`.

#### Step 6 — Add the input-guard layer

The structural score (axes 1–6) measures *what the function does*. Axis 7 (input guard) measures *what the function accepts*. After steps 4–5, run:

```elixir
Archdo.Blackbox.module_verdict(ast)
# => :building_block        — done
# => {:leaks_at, [{:fn_name, 2, :unguarded_input}, ...]} — work remaining
```

For each `:unguarded_input` finding: add a `when` guard, switch to specific patterns in the head, or add an explicit `def f(_, _), do: {:error, :invalid_input}` fallback.

```elixir
# BEFORE — accepts any input
def discount(price, rate), do: Decimal.mult(price, Decimal.from_float(1 - rate))

# AFTER — input-guarded
def discount(%Decimal{} = price, rate)
    when is_float(rate) and rate >= 0.0 and rate <= 1.0,
    do: Decimal.mult(price, Decimal.from_float(1 - rate))

def discount(_, _), do: {:error, :invalid_input}
```

When `Blackbox.module_verdict/1` returns `:building_block` for every module under the namespace, `Blackbox.context_verdict/2` flips to `:building_block`. **You're done.**

### 6.5 Handling Phoenix-generated `get_X!/1` patterns

`mix phx.gen.context` produces a getter shape that's borderline:

```elixir
def get_product!(id), do: Repo.get!(Product, id)
```

This fails axis 1 (Repo is hidden via Repo module, but the lookup itself is pure-shaped) — the function is fundamentally an orchestrator wrapper. **Move it to `Workflow`.** Keep `Product.changeset/2` (pure) in the building-block layer. Same for `list_products/0` and `update_product/2` — these are persistence orchestration, not domain rules.

A typical Phoenix-generated context after the conversion:

```
lib/my_app/catalog.ex                # building-block — composition + delegations
lib/my_app/catalog/product.ex        # building-block — schema + changeset rules
lib/my_app/catalog/price_rules.ex    # building-block — pure pricing math
lib/my_app/catalog/sku_normalizer.ex # building-block — pure string transforms
lib/my_app/catalog/workflow.ex       # orchestrator — get_X!/list_X/create/update/delete
```

If you used Stance B (§6.3 step 3), `lib/my_app/catalog.ex` keeps the original `mix phx.gen.context` API:

```elixir
defmodule MyApp.Catalog do
  defdelegate list_products(), to: MyApp.Catalog.Workflow
  defdelegate get_product!(id), to: MyApp.Catalog.Workflow
  defdelegate create_product(attrs), to: MyApp.Catalog.Workflow
  defdelegate update_product(p, attrs), to: MyApp.Catalog.Workflow
  defdelegate delete_product(p), to: MyApp.Catalog.Workflow
  # Pure additions live here directly:
  def calculate_total(items, rate), do: PriceRules.total(items, rate)
end
```

Callers don't change. The context isn't a building-block (it has facade delegations to `Workflow`), but every module under it — including `PriceRules`, `Product`, `SkuNormalizer` — is. That's the realistic, achievable target for most Phoenix codebases.

### 6.6 The "context = building-block context + workflow context" pattern at scale

For larger contexts, a single `Workflow` module accumulates too many functions. Split the orchestrator into a sibling NAMESPACE rather than a single module:

```
lib/my_app/catalog.ex                       # building-block — public domain API
lib/my_app/catalog/product.ex               # building-block
lib/my_app/catalog/price_rules.ex           # building-block
lib/my_app/catalog/inventory_rules.ex       # building-block
lib/my_app/catalog_orchestration.ex         # orchestrator facade
lib/my_app/catalog_orchestration/queries.ex # Repo reads
lib/my_app/catalog_orchestration/persistence.ex  # Repo writes + telemetry
lib/my_app/catalog_orchestration/import.ex  # external HTTP catalog fetch + parse + persist
```

**Naming convention:** `MyApp.<Context>` is pure; `MyApp.<Context>Orchestration` (or `MyApp.<Context>.Workflow`, or `MyApp.<Context>Server` for stateful) is the impure side. Pick one convention per project and stick to it.

### 6.7 Context-conversion checklist

Before declaring an existing context converted:

- [ ] Ran `Blackbox.context_verdict/2` initially; recorded the leaky-module list as the work plan.
- [ ] For each leaky module: classified P / L₁ / L₂ sets (§6.4 step 2).
- [ ] Picked Stance A or Stance B for the public API (§6.4 step 3) and committed to it for the whole conversion.
- [ ] Extracted every L₁ function to `Workflow` (or the orchestration namespace).
- [ ] Refactored every L₂ function in place by lifting environmental reads to arguments.
- [ ] Added input guards / specific patterns / `{:error, _}` fallbacks until `module_verdict/1` returns `:building_block` for every building-block-layer module.
- [ ] Updated moduledocs to declare `"Building block — ..."` or `"Orchestrator — ..."`.
- [ ] Wrote at least one property test per building-block module.
- [ ] Re-ran `context_verdict/2` and confirmed `:building_block`.
- [ ] Updated callers (Stance A) OR added `defdelegate` (Stance B).
- [ ] CE-54/55/56/57 are silent on the context's modules in `mix archdo`.

### 6.8 Anti-patterns specific to context-level conversion

```elixir
# BAD — calling Workflow from inside the building-block layer
defmodule MyApp.Catalog do
  alias MyApp.Catalog.Workflow

  def total_with_persistence(items) do
    Workflow.persist_calculation(items)   # Direction is BACKWARDS
    calculate_total(items, default_rate())
  end
end

# GOOD — building-block returns a value; Workflow orchestrates
defmodule MyApp.Catalog do
  def calculate_total(items, rate), do: # pure math
end

defmodule MyApp.Catalog.Workflow do
  def total_with_persistence(items, rate) do
    total = MyApp.Catalog.calculate_total(items, rate)
    persist_calculation(items, total)
    total
  end
end
```

The dependency direction MUST be: **`Workflow` calls into the building-block, never the other way.** Building-blocks don't import `Workflow`; `Workflow` imports the building-block. If you find an import in the wrong direction, you've split the context wrong — re-classify the function in question.

```elixir
# BAD — orchestrator hidden inside a "building-block" via a callback
defmodule MyApp.Catalog do
  @moduledoc "Building block"
  @callback persist(t()) :: {:ok, t()} | {:error, term()}

  def save(struct, persistor), do: persistor.persist(struct)
end
```

A behaviour callback parameter doesn't make the function pure — its observable behavior depends on the supplied module's effects. If the function's purpose is "do a side effect via the injected module", it's an orchestrator regardless of how the dependency is named.

---

## 7. Worked Example — Refactoring `Accounts.register_user/1`

**Before — orchestrator with embedded pure logic:**

```elixir
defmodule MyApp.Accounts do
  alias MyApp.{Repo, Mailer}
  alias MyApp.Accounts.User

  def register_user(attrs) do
    # Validate (pure, but mixed with impure below)
    cs = User.changeset(%User{}, attrs)

    if cs.valid? do
      hashed = Bcrypt.hash_pwd_salt(cs.changes.password)
      cs = Ecto.Changeset.put_change(cs, :hashed_password, hashed)

      with {:ok, user} <- Repo.insert(cs),
           :ok <- Mailer.deliver_welcome(user) do
        Logger.info("user registered", user_id: user.id)
        :telemetry.execute([:accounts, :registered], %{count: 1}, %{user_id: user.id})
        {:ok, user}
      end
    else
      {:error, cs}
    end
  end
end
```

This module fails axes: input_closure (Application via Mailer), determinism (Bcrypt salt is random), side_effect_free (Repo, Mailer, Logger, telemetry).

**After — extract building-block + orchestrator:**

```elixir
# BUILDING BLOCK
defmodule MyApp.Accounts.UserRules do
  @moduledoc "Building block — user validation + password-prep rules."
  alias MyApp.Accounts.User

  @spec changeset_for_registration(map(), salt :: String.t()) ::
          {:ok, Ecto.Changeset.t()} | {:error, :invalid}
  def changeset_for_registration(attrs, salt)
      when is_map(attrs) and is_binary(salt) do
    cs = User.changeset(%User{}, attrs)

    case cs.valid? do
      true -> {:ok, Ecto.Changeset.put_change(cs, :hashed_password, hash(cs.changes.password, salt))}
      false -> {:error, :invalid}
    end
  end

  def changeset_for_registration(_, _), do: {:error, :invalid}

  @spec hash(String.t(), String.t()) :: String.t()
  defp hash(password, salt), do: # ...pure hash given salt...
end

# ORCHESTRATOR
defmodule MyApp.Accounts.Registration do
  @moduledoc "Orchestrator — drives UserRules + Repo + Mailer + telemetry."
  alias MyApp.{Repo, Mailer}
  alias MyApp.Accounts.UserRules

  def register(attrs) do
    salt = Bcrypt.gen_salt()  # impure; fed to building-block

    with {:ok, cs} <- UserRules.changeset_for_registration(attrs, salt),
         {:ok, user} <- Repo.insert(cs),
         :ok <- Mailer.deliver_welcome(user) do
      :telemetry.execute([:accounts, :registered], %{count: 1}, %{user_id: user.id})
      {:ok, user}
    end
  end
end
```

`UserRules` is now a building-block: property-testable, no DB, no clock, no logger. `Registration` is the small impure shell that connects it to side effects.

---

## 7.5 Why building-blocks: the composition payoff

The point of building-block discipline isn't purity for its own sake — it's that building-blocks are the substrate composition primitives need. Every composition pattern (`SKILL.md` §4.7, `elixir-implementing/SKILL.md` §5.10) delivers its full payoff only on top of building-blocks:

- **Railway / `with`-chain** trusts that each step returns ok/error and never raises — that's axis 6.
- **`Result.map` / functor** trusts that the mapped function is pure — axes 1, 5, 6.
- **Applicative validation** trusts that validators are independent and pure — axes 1, 5, 6.
- **Effects-as-data** is the *only* way for a building-block to communicate "this should happen" — it exists to satisfy axis 5.
- **Capability passing** IS the technique that delivers axis 1.
- **Smart constructors** push axis 7 from N consumers to 1 constructor.
- **Subject-position discipline** is what makes building-block functions snap into pipelines.

A module that scores high on the seven axes BUT has no callers composing with it is structurally a building-block but architecturally inert. Conversely, a module that lots of code wants to compose with BUT fails the axes is a hot composition target whose impurity is poisoning every consumer. **Track building-block coverage AND composability density together** (`SKILL.md` §4.7.7) — the former says "is the module composition-ready," the latter says "does composition actually happen."

## 8. Cross-References

- **Archdo enforcement:**
  - `Archdo.Blackbox.score_module/1` — six-axis scoring per public function
  - `Archdo.Blackbox.module_verdict/1` — module-level building-block verdict
  - `Archdo.Blackbox.context_verdict/2` — context-level aggregate
  - `Archdo.Blackbox.boundary_suggestion/1` — extract / refactor-in-place advice
  - `Archdo.Blackbox.refactor_distance/1` — ROI ranking metric
  - Rules: CE-54 (BlackboxQuadrant), CE-55 (UntestedBuildingBlock), CE-56 (EffectLeak), CE-57 (UnguardedBuildingBlock)
- **elixir-planning sister docs:**
  - `architecture-patterns.md` §4.6 — orchestrator pattern in detail
  - `process-topology.md` — when an orchestrator IS a process (GenServer-shaped)
  - `test-strategy.md` — property-test placement; building-blocks are the natural target
- **elixir-implementing:**
  - SKILL.md §1 rule 15 — pure functions in callbacks
  - SKILL.md §10.4 — protocols vs behaviours (building-blocks often expose protocols)
  - testing-patterns.md §Property-Based Tests — the payoff

---

## 9. Appendix — One-line Rule of Thumb

> **A building-block is what's left when you remove every reason a function might "depend on the environment".** Keep doing that until your module is irreducibly about one thing — that's the unit other code composes with.
