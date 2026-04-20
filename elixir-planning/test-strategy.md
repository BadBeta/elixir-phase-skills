# Test Strategy — deep reference

Phase-focused deep reference for **testing as a planning concern**. This subskill answers questions that must be decided BEFORE writing tests: what test pyramid fits, what to test at which level, what's mocked vs real, factory architecture, async isolation, CI strategy. The HOW of writing tests (ExUnit syntax, Mox API, assertion patterns) lives in [../elixir-implementing/testing-patterns.md](../elixir-implementing/testing-patterns.md) and `../elixir/testing-reference.md`.

**When to load:** when starting a project (testing infrastructure decisions), when the test suite is slow/flaky/brittle (strategic issues), when introducing a new testing dimension (property testing, browser tests, load tests), or when CI costs are getting out of hand.

**Related:**
- `SKILL.md` — testing is not in the main SKILL.md; this subskill is the primary reference for test strategy at planning level
- [architecture-patterns.md](architecture-patterns.md) §4–5 — hexagonal + layered architecture makes testing easier
- [data-ownership-deep.md](data-ownership-deep.md) — how aggregates shape test boundaries
- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §3–§4 — TDD workflow and ExUnit usage
- `elixir-testing` skill (existing) — deep ExUnit / Mox / Sandbox reference

---

## 1. Rules for test strategy (LLM)

1. **ALWAYS design for testability from the start.** Testability is an architectural property, not an afterthought. If domain logic requires a DB, HTTP client, and framework to test, the architecture is wrong.
2. **ALWAYS test behavior, not implementation.** Tests should survive refactoring. Tests that break when internal functions are renamed are a drag on the team.
3. **ALWAYS pick a deliberate test pyramid.** Know the ratio of unit vs integration vs end-to-end tests. "Test everything at every level" is slow and redundant.
4. **ALWAYS decide the mock boundary.** What's real (DB via sandbox, PubSub, Registry) and what's mocked (HTTP clients, payment gateway, email) — decide once; apply consistently.
5. **NEVER mock modules you own.** Test domain modules with real inputs. Mock only at system boundaries (HTTP, email, hardware, external services).
6. **ALWAYS design factories before writing tests.** Factory module (ExMachina) with sequences and associations — decide upfront; don't hand-build fixtures per test.
7. **PREFER `async: true`** unless the test touches truly global state. Ecto sandbox supports async.
8. **ALWAYS decide the strategy for async tests that spawn processes.** Sandbox allowance pattern vs `{:shared, pid}` mode — choose and document.
9. **ALWAYS document the test strategy.** Where are unit tests? What's the integration boundary? What does a test "require" to run? New contributors need this.
10. **NEVER leave flaky tests.** Flaky tests erode trust in the whole suite. Either fix or mark as `:skip` with an issue to track.
11. **PLAN for test data ownership.** Factories live in `test/support/factory.ex`. Fixtures are versioned. Database seeds are separate from test data.
12. **ALWAYS measure and manage test suite time.** A suite that runs in 60s gets run; a suite that takes 10 minutes gets skipped locally. Tune for speed.

---

## 2. The test pyramid — choose deliberately

Classic test pyramid:

```
                  ┌───────────┐
                  │   E2E     │  ← Few, slow, expensive
                  │  (browser)│     Test critical user flows only
                  └───────────┘
               ┌──────────────────┐
               │   Integration    │  ← Medium count
               │  (controller,    │     Context + DB; contract tests
               │   LiveView,      │     for external adapters
               │   channel)       │
               └──────────────────┘
         ┌─────────────────────────────┐
         │         Unit                │  ← Many, fast, cheap
         │  (pure functions,           │     Bulk of the test suite
         │   context functions,        │     Domain logic coverage
         │   schema validation)        │
         └─────────────────────────────┘
```

### 2.1 Layer by layer

**Unit (many, fast):**
- Pure functions in domain modules
- Changeset validation
- Pipeline transformations
- Entity methods (Order.can_cancel?/1)
- Query builders

**Context / integration (medium count):**
- Context public API functions (use the real DB via sandbox)
- Mox boundaries for external services (HTTP, email)
- Multi-step domain operations that span entities

**Controller / LiveView (few):**
- HTTP request/response shape
- LiveView mount/handle_event flows
- Authorization at the interface layer

**End-to-end (very few):**
- Critical user flows through the whole stack (Wallaby, headless browser)
- Smoke tests for deploy health

### 2.2 The anti-pyramid

```
                  ┌──────────────────┐
                  │  Unit (few)      │
                  └──────────────────┘
              ┌────────────────────────┐
              │  Integration (many)    │
              └────────────────────────┘
         ┌──────────────────────────────┐
         │  E2E (everything)            │
         └──────────────────────────────┘
```

Slow. Flaky. Expensive. Hard to maintain. **Test pyramid right-side up.**

### 2.3 Planning your pyramid

Decide proportions based on:

| Factor | Favors unit-heavy | Favors integration-heavy |
|---|---|---|
| Domain complexity | High (many business rules) | Low (thin CRUD) |
| External dependencies | Few (simple app) | Many (complex integrations) |
| UI surface | Small (API) | Large (web app, LiveView) |
| Team's testing maturity | High | Low (integration is easier to start) |
| Test run budget | Small (fast feedback loop) | Large (CI matters more than local) |

### 2.4 Worked example — SaaS web app

- **Unit (~60%):** Changeset validations, context pure functions (calculation, rules, state transitions), query builders, workers (Oban)
- **Integration (~30%):** Context public API (with DB sandbox), controller tests (with `ConnCase`), LiveView (with `LiveViewTest`), external-adapter contract tests (Mox)
- **E2E (~10%):** Critical user signup-and-first-action flow (Wallaby), deploy smoke test

---

## 3. What to test at each level

Decision framework for where each piece of code gets tested.

### 3.1 By module type

| Module type | Test layer |
|---|---|
| Pure domain module (no DB, no framework) | **Unit** — plain ExUnit, no setup |
| Ecto schema (changeset) | **Unit** — test changeset in isolation |
| Context public API function (hits DB) | **Integration** — `DataCase`, Ecto sandbox, real DB |
| Context function calling external service | **Integration** — Mox the external; real DB |
| Controller action | **Integration** — `ConnCase`, hits the context |
| LiveView | **Integration** — `LiveViewTest`, hits the context |
| Channel | **Integration** — `ChannelCase` |
| Oban worker | **Integration** — real DB; Mox external |
| GenServer (domain process) | **Unit** for pure logic via instructions pattern; **Integration** for process mechanics |
| External adapter (behaviour implementation) | **Contract test** — optionally integration-test against real service in CI |

### 3.2 What NOT to test

- **Pure pass-through** (context `defdelegate` to internal module): test the internal module, not the delegate
- **Generated code** (Phoenix generators): trust the generator; test the business logic you added
- **Framework behavior** (Phoenix plugs, Ecto itself): trust them
- **Internal private functions**: test through the public API

### 3.3 Coverage is not the goal

Chasing line coverage produces brittle tests that assert on implementation. Aim for:
- **Behavior coverage** — every documented behavior has a test
- **Boundary coverage** — every boundary (context API, external adapter) has tests
- **Edge-case coverage** — known edge cases have tests (empty list, nil, zero, max value)

A 100% line-coverage suite full of mocks + implementation assertions is worse than a 70% suite that tests real behavior.

---

## 4. The mock boundary

### 4.1 The principle

**Mock at system boundaries. Never within your own domain.**

```
┌────────────────────────────────────────────────────┐
│ Your application                                   │
│                                                    │
│  Context A → Context B → Infrastructure adapter   │
│  (test with real calls)     ↑                      │
│                             │                      │
│                         (Mock here)                │
│                             │                      │
└─────────────────────────────┼──────────────────────┘
                              ↓
                     External system
                  (HTTP API, email,
                   hardware, payment)
```

### 4.2 What to mock

| Boundary | Mock? | How |
|---|---|---|
| HTTP client to external API | **YES** | Behaviour + Mox |
| Email sending | **YES** | Behaviour + Mox |
| Payment gateway | **YES** | Behaviour + Mox |
| Push notification sender | **YES** | Behaviour + Mox |
| Hardware (Nerves) | **YES** | Behaviour + Mox |
| File system (for test isolation) | **Sometimes** | `@tag :tmp_dir` or Mox |
| Clock (when tests care about time) | **Sometimes** | Inject a clock behaviour |
| Random / UUID generation (when deterministic tests needed) | **Sometimes** | Inject a generator behaviour |
| Database via Repo | **NO** | Ecto sandbox (real DB, isolated) |
| Phoenix.PubSub | **NO** | Real PubSub — fast, deterministic |
| Registry | **NO** | Real Registry |
| ETS | **NO** | Real ETS |
| Your own domain modules | **NEVER** | Test directly with real inputs |
| Your own contexts | **NEVER** | Test directly |

### 4.3 Why "never mock your own code"

Mocking your own domain:
- **Hides bugs** — mock says `{:ok, user}`; real code says `{:error, :not_found}`; production breaks
- **Duplicates work** — you write the mock AND the real code
- **Brittle** — refactoring internal API breaks tests that mock it
- **Tests lie** — tests pass; production doesn't

The fix is hexagonal architecture. Put external dependencies behind behaviours. Test domain with real domain; mock only at the behaviour boundary.

### 4.4 Designing for mockability

**Wrap every external boundary in a behaviour** during planning — don't retrofit:

```elixir
defmodule MyApp.Mailer do
  @callback send_welcome(User.t()) :: :ok | {:error, term()}
  @callback send_password_reset(User.t(), String.t()) :: :ok | {:error, term()}
end

# Real impl
defmodule MyApp.Mailer.Swoosh do
  @behaviour MyApp.Mailer
  # ...
end

# Mock for tests
Mox.defmock(MyApp.Mailer.Mock, for: MyApp.Mailer)

# Config selects
config :my_app, :mailer, MyApp.Mailer.Swoosh        # prod
config :my_app, :mailer, MyApp.Mailer.Mock          # test

# Dispatcher
defmodule MyApp.MailerDispatcher do
  defp impl, do: Application.get_env(:my_app, :mailer)
  def send_welcome(user), do: impl().send_welcome(user)
end
```

See [architecture-patterns.md](architecture-patterns.md) §4 for the full hexagonal pattern.

### 4.5 Contract tests for adapters

When you mock an adapter, occasionally run **contract tests** against the real service to verify the mock matches reality.

```elixir
# Normal tests — always run, use Mox
test "registration sends welcome email (mocked)" do
  Mox.expect(MailerMock, :send_welcome, fn _user -> :ok end)
  # ...
end

# Contract tests — tagged :external, run nightly or pre-release
@tag :external
test "Mailer.Swoosh actually delivers via Swoosh" do
  # Uses a real test account, verifies the full integration
end

# In test_helper.exs — exclude by default
ExUnit.configure(exclude: [external: true])
# Run contract tests: mix test --include external
```

---

## 5. Factory architecture

### 5.1 Use ExMachina (or equivalent)

Build factories in `test/support/factory.ex`. Factories handle:
- Default attribute values
- Sequences for unique fields
- Associations (building or inserting related records)
- Overrides for specific test needs

```elixir
defmodule MyApp.Factory do
  use ExMachina.Ecto, repo: MyApp.Repo

  def user_factory do
    %MyApp.Accounts.User{
      email: sequence(:email, &"user-#{&1}@example.com"),
      name: "Test User",
      password_hash: Bcrypt.hash_pwd_salt("secret-pw-123")
    }
  end

  def admin_factory, do: struct!(user_factory(), role: :admin)

  def order_factory do
    %MyApp.Orders.Order{
      user: build(:user),
      items: [build(:order_item)],
      status: :pending,
      total: Decimal.new("99.99")
    }
  end
end
```

### 5.2 Factory API

```elixir
insert(:user)                                        # Persist to DB
insert(:user, email: "custom@example.com")           # With overrides
insert_list(5, :user)                                # Many
build(:user)                                         # Struct only, not persisted
params_for(:user)                                    # Map (atom keys)
string_params_for(:user)                             # Map (string keys) — for controller tests
```

### 5.3 Factory design rules

1. **One factory module.** `MyApp.Factory` — all factories. Don't split across files (makes discovery hard).
2. **`@moduledoc false`** — factories are test-only.
3. **Use `sequence/2` for unique fields.** Hardcoded emails = collisions.
4. **Associations via `build/1`**, not by hardcoding. `user: build(:user)`.
5. **Factory complexity → trait pattern.** If the same factory has many variants, use composable traits:

```elixir
def user_factory, do: %User{email: sequence(:email, &"u-#{&1}@x.com"), active: true}
def admin_trait(user), do: %{user | role: :admin}
def inactive_trait(user), do: %{user | active: false}

# In test:
admin = insert(:user) |> admin_trait()
```

### 5.4 Fixtures vs factories

- **Factory** (ExMachina): generates fresh, unique data per test. Default choice.
- **Fixture** (seeded data, loaded once): for static reference data (countries, currencies). Load in `setup_all` or a shared setup.
- **Avoid "golden" fixtures** with hardcoded IDs — they couple tests to state and break when you add new ones.

### 5.5 Factory anti-patterns

```elixir
# BAD — hardcoded unique field (collision risk)
def user_factory, do: %User{email: "test@example.com"}

# GOOD — sequence
def user_factory, do: %User{email: sequence(:email, &"u-#{&1}@x.com")}

# BAD — factory that hits external services
def user_factory do
  user = %User{email: sequence(:email, ...)}
  Bamboo.TestAdapter.send_email(welcome_email(user))   # Factory shouldn't send email!
  user
end

# GOOD — factory creates data only; side effects happen in the test
# If the test wants to verify welcome email is sent, it calls Accounts.register
```

---

## 6. Async isolation design

### 6.1 What "async: true" means

```elixir
defmodule MyApp.AccountsTest do
  use MyApp.DataCase, async: true  # ← This
  # ...
end
```

ExUnit runs this test module in parallel with other `async: true` modules. **Dramatically** speeds up the suite.

### 6.2 When async: true is safe

- Test doesn't touch globally-named processes (named GenServers, `:global` registrations)
- Test doesn't modify `Application.put_env` / other global config
- Test doesn't share ETS tables with other tests
- Tests that touch the DB use Ecto sandbox (allows per-test isolation)

### 6.3 When async: true is NOT safe

- Tests that set `Application.put_env` for shared keys
- Tests that mock-wire a named GenServer (`set_mox_global()`)
- Tests that share a globally-named ETS table
- Tests that share file-system state without per-test isolation

### 6.4 Ecto sandbox — async DB

Ecto's sandbox supports async tests. Each test gets its own transaction, rolled back at the end.

```elixir
# test_helper.exs — manual mode means each test checks out explicitly
Ecto.Adapters.SQL.Sandbox.mode(MyApp.Repo, :manual)

# DataCase setup — per-test checkout
setup tags do
  pid = Ecto.Adapters.SQL.Sandbox.start_owner!(MyApp.Repo, shared: not tags[:async])
  on_exit(fn -> Ecto.Adapters.SQL.Sandbox.stop_owner(pid) end)
  :ok
end
```

**Rule:** every DB-touching test module uses `async: true` unless it relies on truly global state.

### 6.5 Sandbox allowance for spawned processes

When a test spawns a process (GenServer, Oban, Task) that needs DB access, allow it explicitly:

```elixir
test "async worker processes the order" do
  order = insert(:order)
  # The worker runs in a spawned process — allow it to use the sandbox connection
  {:ok, pid} = MyApp.Workers.ProcessOrder.start_link(order.id)
  Ecto.Adapters.SQL.Sandbox.allow(MyApp.Repo, self(), pid)
  # ... assertions
end
```

### 6.6 Sandbox modes — decision

| Mode | Behavior | When |
|---|---|---|
| `:manual` | Each test explicitly checks out | Default |
| `:auto` | Auto-checkout on first query | Simple sync tests (less common) |
| `{:shared, pid}` | All processes share the owner's connection | Non-async tests; LiveView tests; channel tests |

**For async tests:** manual + explicit allowance.
**For LiveView/channel tests:** shared mode often needed because LiveView spawns a separate process.

### 6.7 Mox async modes

```elixir
set_mox_private()      # Default — expectations only in owning process. Works with async.
set_mox_global()       # All processes share — requires async: false
set_mox_from_context() # Auto-pick based on tag
```

**Rule:** default to `set_mox_private()` + `allow/3` for spawned processes. Use `set_mox_global()` only when you can't track all spawned processes — and disable async for that module.

---

## 7. CI strategy

### 7.1 What runs where

| Check | Where | When |
|---|---|---|
| Compile with warnings-as-errors | Every commit | Pre-merge |
| Unit + integration tests | Every commit | Pre-merge |
| mix format check | Every commit | Pre-merge |
| mix credo --strict | Every commit | Pre-merge |
| Dialyzer | Every commit | Pre-merge (cached PLT) |
| Test coverage (threshold) | Every commit | Pre-merge |
| External contract tests (`:external` tag) | Nightly | Scheduled |
| Browser tests (Wallaby) | Pre-release | Tagged |
| Load tests | Ad-hoc / release | Manual |
| Security scan (Sobelow, Dependabot) | Every commit | Pre-merge |

### 7.2 CI performance targets

- **Fast feedback (< 5 min):** Unit tests pass or fail
- **Full CI (< 15 min):** All pre-merge checks green
- **Nightly (< 60 min):** Contract tests, longer integrations, load smoke

### 7.3 Parallelization strategy

- **Elixir async tests:** `ExUnit.configure(max_cases: System.schedulers_online() * 2)`
- **CI job-level:** split test suite across multiple CI workers (Dialyzer, tests, formatter in parallel)
- **Matrix testing:** Elixir/OTP version matrix (if supporting multiple)

### 7.4 CI pitfalls

- **Flaky tests fail the build randomly.** Zero tolerance. Fix immediately or `@tag :skip` with a ticket.
- **Slow suite discourages running locally.** Target < 30s for the fast subset; full suite < 5 min if possible.
- **External dependencies in CI.** Avoid — use Mox. Reserve real API calls for scheduled contract tests.

---

## 8. Property-based testing

### 8.1 When to use

Property tests generate many inputs; verify invariants hold for all of them. Use for:

- **Parsers / serializers** — encode then decode is identity
- **Sort / reverse** — reverse is own inverse; sort is ordered; length preserved
- **Set operations** — union, intersection, difference invariants
- **State machines** — valid sequences of operations preserve invariants
- **Anything with an obvious mathematical inverse or invariant**

### 8.2 When NOT to use

- **Simple CRUD** — example-based tests are clearer
- **UI / LiveView** — no obvious invariants
- **One-off business rules** — not worth the infrastructure

### 8.3 Shape

```elixir
use ExUnitProperties

property "sort is idempotent" do
  check all list <- list_of(integer()), max_runs: 200 do
    sorted = MySort.sort(list)
    assert sorted == MySort.sort(sorted)
  end
end

property "encode then decode is identity" do
  check all value <- term() do
    {:ok, decoded} = value |> MyCodec.encode() |> MyCodec.decode()
    assert value == decoded
  end
end
```

### 8.4 Design for property testing

- **Identify invariants upfront** during design. What must ALWAYS be true?
- **Design generators for your domain types.** ExMachina factories + `StreamData` adapters.
- **Shrink on failure** — StreamData shows you the minimal failing input.

### 8.5 Property testing is planning-level

Deciding *which* invariants to property-test is a planning decision. It shapes the domain API — testable invariants become documented properties, inform the design, catch bugs that example-based tests miss.

---

## 9. Testing the boundaries — contract tests

### 9.1 The problem

Mox gives you unit-test speed with a fake implementation. But the fake might not match the real adapter. When Stripe's API changes and your adapter no longer translates correctly, Mox tests still pass.

### 9.2 The fix

**Contract tests** — run the real adapter against the real (or staging) external service. Verify the adapter translates correctly.

```elixir
defmodule MyApp.Billing.PaymentGateway.StripeContractTest do
  use ExUnit.Case

  @moduletag :external

  test "Stripe.charge with valid token returns domain-shape result" do
    # Use Stripe test card
    assert {:ok, result} = MyApp.Billing.PaymentGateway.Stripe.charge(100_00, "tok_visa")
    assert is_binary(result.transaction_id)
    assert %DateTime{} = result.captured_at
  end

  test "Stripe.charge with invalid token returns :card_declined" do
    assert {:error, :card_declined} =
             MyApp.Billing.PaymentGateway.Stripe.charge(100_00, "tok_chargeDeclined")
  end
end

# In test_helper.exs:
ExUnit.configure(exclude: [external: true])

# Run contract tests nightly:
# mix test --only external
```

### 9.3 What contract tests verify

- **Input validation** — does the adapter handle the input correctly?
- **Output translation** — does the adapter convert external types to domain types?
- **Error mapping** — are external errors mapped to the behaviour's error types?
- **Breaking API changes** — catches when the external service changes its API

### 9.4 When to run

- **Nightly** in CI against staging / sandbox environment
- **Pre-release** — before shipping to production
- **Ad-hoc** — when changing adapter code

**Not on every commit** — contract tests are slow and can fail due to external outages.

---

## 10. Performance and load testing

### 10.1 Two levels

**Microbenchmarks** — with Benchee, compare implementations of a specific function:

```elixir
Benchee.run(%{
  "impl_a" => fn -> MyApp.Search.query_a("elixir") end,
  "impl_b" => fn -> MyApp.Search.query_b("elixir") end
}, warmup: 2, time: 5, memory_time: 2)
```

**Load tests** — entire system under load. Tools: `Locust`, `k6`, `wrk`. Measure p50 / p95 / p99 latency and throughput.

### 10.2 When to plan each

- **Microbenchmarks** — when picking between implementations with different complexity characteristics (e.g., `Enum.reduce` vs `for`); when profiling finds a hot function
- **Load tests** — before going live with a new feature; during capacity planning; after performance changes

### 10.3 Load test strategy

- **Define SLO** — e.g., p95 < 200ms at 1000 req/sec
- **Test against staging, not production** (obviously)
- **Ramp up gradually** to find the knee
- **Monitor telemetry** during the test to identify bottlenecks
- **Don't blindly chase bigger numbers** — optimize for your actual load profile

See [../elixir-reviewing/profiling-playbook-deep.md](../elixir-reviewing/profiling-playbook-deep.md) (when written) for profiling.

---

## 11. Test database strategy

### 11.1 One test DB or per-module?

- **One test DB** (default): Ecto sandbox handles isolation. Fast CI startup.
- **Per-module DB** (rare): Required if modules have truly incompatible schemas or data.

Default to one test DB; sandbox handles isolation.

### 11.2 Migrations

Run migrations at CI start:

```bash
MIX_ENV=test mix ecto.create
MIX_ENV=test mix ecto.migrate
```

For faster local dev:

```elixir
# test_helper.exs
Ecto.Adapters.SQL.Sandbox.mode(MyApp.Repo, :manual)
# Don't re-migrate unless schema changed
```

### 11.3 Seed data

- **Avoid seed data for tests.** Factories per test > global seeds.
- **Exception:** reference data that never changes (countries, currencies).
- **Load in `setup_all`** for module-wide reference data.

### 11.4 Multi-tenant test strategy

When testing a multi-tenant app:

```elixir
test "users from one tenant don't see another tenant's data" do
  t1 = insert(:tenant)
  t2 = insert(:tenant)
  _ = insert(:user, tenant_id: t1.id)
  _ = insert(:user, tenant_id: t2.id)

  t1_users = MyApp.Accounts.list_users(tenant_id: t1.id)
  assert length(t1_users) == 1
  assert Enum.all?(t1_users, &(&1.tenant_id == t1.id))
end
```

**Every tenant-scoped function needs a leak test.** Cross-tenant data leaks are the #1 multi-tenancy bug.

---

## 12. Testing GenServers and OTP processes

### 12.1 Test pure logic separately

If the GenServer uses the instructions pattern (see [process-topology.md](process-topology.md) §8), test the pure domain module without starting a process:

```elixir
test "workflow advance emits notify instruction" do
  workflow = Workflow.new([:alice, :bob])
  {instructions, _workflow} = Workflow.advance(workflow, :alice, :approve)
  assert Enum.member?(instructions, {:notify, :bob, :task_assigned})
end
```

Fast. No process. No mocking.

### 12.2 Test GenServer shell with `start_supervised!`

For the process mechanics (messages, state), use `start_supervised!`:

```elixir
test "counter increments via call" do
  pid = start_supervised!({MyApp.Counter, []})   # Auto-stopped at test end
  assert MyApp.Counter.increment(pid) == 1
  assert MyApp.Counter.increment(pid) == 2
end
```

### 12.3 Test async behavior with `assert_receive`

```elixir
test "worker sends :done when finished" do
  MyApp.Worker.start(self())
  assert_receive {:done, _result}, 500   # Wait up to 500ms
end
```

**Never** `Process.sleep` then assert. `assert_receive` waits only as long as needed.

### 12.4 Test Registry / DynamicSupervisor patterns

```elixir
test "can register and look up per-entity processes" do
  {:ok, _} = MyApp.GameSupervisor.start_game("game_1")
  assert {:ok, _pid} = MyApp.GameRegistry.lookup("game_1")
  assert MyApp.GameServer.call("game_1", :status) == :pending
end
```

---

## 13. When the test strategy is wrong — signals

### 13.1 Pain points → strategy fixes

| Symptom | Strategy issue |
|---|---|
| Tests break on every refactor | Testing implementation instead of behavior |
| Slow suite (>5 min) | Over-reliance on integration tests; no async; heavy setup |
| Flaky tests | Global state leakage; `Process.sleep` where `assert_receive` belongs; async mis-configuration |
| Can't test a rule without 10 modules | Missing behaviour boundary; domain depends on infrastructure |
| Bugs that tests miss | Not testing at the right layer; integration gap |
| Mocks always match the code | Mocking your own code; mocks are tautological |
| Adapter breaks silently when external API changes | Missing contract tests |
| Coverage is high but production still breaks | Testing coverage, not behavior |
| Tests in CI work; tests locally fail | Environment-dependent setup; missing test helpers |

### 13.2 Strategy evolution

Test strategy should evolve as the app grows:

- **Stage 1 (MVP):** Unit tests for core logic; a handful of integration tests. Pragmatic factories.
- **Stage 2 (growing):** Full test pyramid. Mox at all external boundaries. Contract tests for paid adapters.
- **Stage 3 (mature):** Property-based for core algorithms. Load tests per major feature. E2E for critical flows.

Don't over-invest at Stage 1. Don't under-invest at Stage 3.

---

## 14. Cross-references

### Within this skill

- [architecture-patterns.md](architecture-patterns.md) §4–5 — hexagonal + layered testability
- [data-ownership-deep.md](data-ownership-deep.md) §3 — aggregates as test boundaries
- [process-topology.md](process-topology.md) §8 — instructions pattern for testable domain
- [otp-design.md](otp-design.md) — GenServer testability via pure modules
- [growing-evolution.md](growing-evolution.md) — how test strategy evolves with app stage

### In other skills

- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §3 — TDD workflow (red/green/refactor)
- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §4 — ExUnit, Mox, Sandbox syntax
- [../elixir-reviewing/SKILL.md](../elixir-reviewing/SKILL.md) §7.7 — test-quality review checklist
- `elixir-testing` skill — deep ExUnit / Mox / Sandbox reference
- `../elixir/testing-reference.md` — quick reference for test helpers, assertions
- `../elixir/testing-examples.md` — worked examples (CaseTemplate, factories, LiveView testing)

---

**End of test-strategy.md.** For test CODE patterns (ExUnit, Mox, assertions), see [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §4. For the `elixir-testing` skill, load it when you need deep testing patterns.
