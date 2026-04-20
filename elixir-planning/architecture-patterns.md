# Architecture Patterns — deep reference

Phase-focused deep reference for the architectural styles covered in `SKILL.md §4` and `§12`. This subskill exists to give planning-mode depth on hexagonal, layered, modular-monolith, event-driven, and CQRS patterns in Elixir — with worked examples, common mistakes, and migration paths.

**When to load this:** when you're planning the architecture of a new project or a substantial refactor, and the SKILL.md decision tables point you at a specific style that needs more detail.

**Related:**
- `SKILL.md §4, §12` — the overview and decision tree
- [process-topology.md](process-topology.md) — how the architectural style maps to supervision trees
- [integration-patterns.md](integration-patterns.md) — inter-context communication patterns used by each style
- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §10 — implementing contexts and boundaries (the code-level view)

---

## 1. Rules for applying architectural styles (LLM)

1. **ALWAYS start with contexts + supervision + behaviours** — the Elixir default IS modular monolith + hexagonal + layered simultaneously. Most apps never need anything more. See §3.
2. **NEVER adopt a style because it's "sophisticated."** Each style solves a specific problem. If you don't have that problem, the style is overhead.
3. **ALWAYS name the problem before picking the style.** If you can't describe the problem in one sentence, you don't have a justifying problem yet.
4. **NEVER apply a single style uniformly to every context.** Different contexts can use different styles. The `Accounts` context might be simple CRUD; the `Orders` context might be event-sourced. Both live in the same app.
5. **ALWAYS draw the supervision tree when designing.** If your architectural style doesn't have a clear supervision-tree expression, you're not thinking in BEAM terms.
6. **PREFER composition of simple styles over one complex style.** Layered + hexagonal + PubSub beats "enterprise event-driven CQRS microservices."
7. **ALWAYS design for replaceability at boundaries.** Behaviours (ports) + adapters is the default way to express boundaries in Elixir. If you can't swap an implementation without touching business logic, the boundary is missing.
8. **NEVER couple domain to framework.** Phoenix is infrastructure. Ecto is infrastructure. Logic should not depend on them directly — it should depend on domain contracts (behaviours) that infrastructure implements.
9. **NEVER split a modular monolith to gain "coupling" benefits** — OTP supervision and behaviours give you loose coupling without network hops. Split only for different languages, compliance isolation, separate teams/release cycles, or extreme scaling differences.

---

## 2. Style decision tree

When you have an architectural problem, walk the tree top-down.

```
What's the actual problem?

1. "I'm starting a new Elixir project and don't know where to put things."
   → Modular monolith (default). Go to §3. DO NOT read further.

2. "I need to swap external dependencies (DB, APIs, hardware) for test or future migration."
   → Hexagonal. Go to §4. (You'll also use the modular monolith as the container.)

3. "I want clear separation between UI/input, domain logic, and infrastructure."
   → Layered. Go to §5. (Compatible with modular monolith + hexagonal.)

4. "Contexts need to react to events from other contexts without tight coupling."
   → Event-driven. Go to §6. Pick the variant that fits:
     - Minimal coupling, loss OK            → Event Notification (6.1)
     - Subscribers shouldn't call back      → Event-Carried State Transfer (6.2)
     - Need audit trail / replay / compliance → Event Sourcing (6.3)

5. "Read patterns diverge from write patterns in one context."
   → CQRS. Go to §7. Pick the level:
     - Standard CRUD with distinct queries  → Level 1: Light CQRS (7.1)
     - Queries contend with writes          → Level 2: Separated Read Path (7.2)
     - Multiple very different read stores  → Level 3: Full CQRS + Projections (7.3)

6. "I need to split for a CONCRETE non-tech reason (language, compliance, team, scaling asymmetry)."
   → Microservices. Go to §8. (Rarely justified in Elixir.)

7. "My question isn't here."
   → The existing styles don't fit? Describe the problem in issue/doc form and get
     another pair of eyes. Don't invent a new style — you're probably missing one of the above.
```

---

## 3. Modular monolith (the Elixir default)

The Elixir default. One Mix application. Multiple contexts (boundary modules). One supervision tree. One deployable.

### 3.1 What it gives you

| Concern | Modular monolith solves it via |
|---|---|
| Fault isolation | Supervision trees |
| Loose coupling | Contexts (public API) + behaviours (ports) |
| Independent scaling | Process pools, `Task.async_stream`, Broadway |
| Service discovery | Registry / `:pg` / named processes |
| Observability | `:telemetry` events per context |
| Deploy simplicity | One Mix release, zero network hops |

Everything microservices claim to solve, BEAM + modular monolith solves at lower cost.

### 3.2 Canonical structure

```
my_app/
├── lib/
│   ├── my_app/
│   │   ├── application.ex             # Supervision tree
│   │   ├── repo.ex
│   │   ├── accounts.ex                # Context: public API
│   │   ├── accounts/
│   │   │   ├── user.ex                # Schema (internal — @moduledoc false)
│   │   │   ├── session.ex
│   │   │   └── password_reset.ex
│   │   ├── catalog.ex                 # Another context
│   │   ├── catalog/
│   │   │   ├── product.ex
│   │   │   └── category.ex
│   │   ├── orders.ex
│   │   ├── orders/
│   │   │   ├── order.ex
│   │   │   ├── line_item.ex
│   │   │   └── workflow.ex
│   │   ├── mailer.ex                  # Behaviour (port)
│   │   └── mailer/
│   │       └── swoosh.ex              # Adapter
│   └── my_app_web/                    # Interface layer
│       ├── endpoint.ex
│       ├── router.ex
│       ├── controllers/
│       └── live/
├── config/
├── test/
└── mix.exs
```

**Rules:**

- `lib/my_app/` is the domain. `lib/my_app_web/` is the interface.
- Each context is a single file (`accounts.ex`) with internal modules in a subdirectory (`accounts/`).
- Internal modules are `@moduledoc false` and never called from outside the context.
- The only cross-context communication is through public APIs (`Accounts.register/1`).

### 3.3 When modular monolith is not enough

Very few cases. Watch for these smells:

| Smell | What it actually means | Action |
|---|---|---|
| Large team stepping on each other's files | You need clearer context boundaries, or separate CI test targets | Add contexts; use CODEOWNERS |
| Different subsystems have wildly different deploy cadences | You might need separate releases from one umbrella | Consider umbrella (one repo, multiple release targets) |
| One subsystem is 100× the CPU / memory of the rest | Separate process tree under its own supervisor; possibly separate release | Plan an umbrella or separate deploy |
| Different languages needed (Python ML, Rust compute) | NIF via Rustler, or separate service | Separate service only if NIF is inadequate |
| Regulatory isolation (PCI, HIPAA) | Separate deploy for the regulated subsystem | Microservice, reluctantly |

**Never split for:**

- "It feels big" → add contexts
- "We want loose coupling" → use behaviours
- "We want fault isolation" → use supervision

### 3.4 Context design within a modular monolith

See `SKILL.md §6` for the full decision framework. Summary:

**Create a new context when:**
- Different business domain (Accounts vs Catalog)
- Different team ownership
- Distinct data lifecycle
- Different consistency requirements

**Merge contexts when:**
- Operations always happen in the same transaction
- Entities share an aggregate root
- Constant cross-context calls (you have a boundary misalignment)

---

## 4. Hexagonal Architecture (Ports & Adapters)

**Hexagonal** = put every external dependency behind a contract. Domain talks to contracts. Adapters implement them.

### 4.1 The concepts in Elixir terms

| Hexagonal concept | Elixir implementation |
|---|---|
| **Port** (the contract) | `@callback` behaviour |
| **Adapter** (the implementation) | Module implementing the behaviour |
| **Domain core** | Context modules, pure functions |
| **Driving adapter** (input) | Phoenix controller, LiveView, CLI, GraphQL |
| **Driven adapter** (output) | Repo, HTTP client, email, file I/O, hardware, pubsub |
| **Selection** | `Application.compile_env` (app) or `Application.get_env` (library) |

**Elixir gets hexagonal for free via behaviours. You do not need a framework.**

### 4.2 Canonical hexagonal example — payment gateway

```elixir
# === PORT (behaviour — the contract owned by the domain) ===
defmodule MyApp.Billing.PaymentGateway do
  @moduledoc "Port — billing context contracts for payment gateways."

  @callback charge(amount :: Decimal.t(), token :: String.t()) ::
              {:ok, %{transaction_id: String.t(), captured_at: DateTime.t()}}
              | {:error, :card_declined | :card_expired | :payment_failed | term()}

  @callback refund(transaction_id :: String.t()) ::
              :ok | {:error, :not_found | :already_refunded | term()}
end

# === DRIVEN ADAPTER — Stripe ===
defmodule MyApp.Billing.PaymentGateway.Stripe do
  @behaviour MyApp.Billing.PaymentGateway

  @impl true
  def charge(amount, token) do
    case Stripe.Charge.create(%{amount: amount, source: token, currency: "usd"}) do
      {:ok, charge} -> {:ok, to_domain_result(charge)}
      {:error, err} -> {:error, to_domain_error(err)}
    end
  end

  @impl true
  def refund(transaction_id) do
    case Stripe.Refund.create(%{charge: transaction_id}) do
      {:ok, _} -> :ok
      {:error, %{code: "charge_already_refunded"}} -> {:error, :already_refunded}
      {:error, _} -> {:error, :refund_failed}
    end
  end

  # --- Translation layer (anti-corruption) ---
  defp to_domain_result(charge) do
    %{transaction_id: charge.id, captured_at: DateTime.utc_now()}
  end

  defp to_domain_error(%{code: "card_declined"}), do: :card_declined
  defp to_domain_error(%{code: "expired_card"}), do: :card_expired
  defp to_domain_error(_), do: :payment_failed
end

# === DRIVEN ADAPTER — Mock (for tests) ===
# Generated by Mox.defmock(MyApp.Billing.PaymentGateway.Mock, for: MyApp.Billing.PaymentGateway)

# === SELECTION ===
# config/config.exs
config :my_app, :payment_gateway, MyApp.Billing.PaymentGateway.Stripe

# config/test.exs
config :my_app, :payment_gateway, MyApp.Billing.PaymentGateway.Mock

# === DOMAIN (uses the port, not the adapter) ===
defmodule MyApp.Billing do
  @gateway Application.compile_env!(:my_app, :payment_gateway)

  @spec charge_order(Order.t()) :: {:ok, Order.t()} | {:error, term()}
  def charge_order(order) do
    with {:ok, result} <- @gateway.charge(order.amount, order.payment_token),
         {:ok, order} <- mark_charged(order, result.transaction_id) do
      {:ok, order}
    end
  end
end
```

**Key points:**

- The port (`MyApp.Billing.PaymentGateway`) is owned by the domain (`MyApp.Billing`).
- The adapter (`Stripe`) lives outside the domain — in `lib/my_app/billing/payment_gateway/stripe.ex` or `lib/my_app/infrastructure/payment_gateway/stripe.ex`.
- Adapter translates Stripe's data model into the domain's data model (anti-corruption layer).
- Domain code never sees Stripe types — only domain types.
- Tests use Mox against the same behaviour → zero changes to domain code.

### 4.3 When to apply hexagonal

**Apply hexagonal at every external boundary** (not just the "important" ones):

| External dependency | Port behaviour | Typical adapters |
|---|---|---|
| Database | `Ecto.Adapter` (built-in) | Postgres, MySQL, SQLite |
| HTTP client | `MyApp.HTTPClient` | `Req`, `Finch`, `HTTPoison` |
| Email | `MyApp.Mailer` | `Swoosh`, `Bamboo`, `SendGrid`-direct |
| Payment | `MyApp.PaymentGateway` | Stripe, Adyen, Mock |
| Push notifications | `MyApp.Notifier` | APNS, FCM, null |
| Hardware (Nerves) | `MyApp.SensorReader` | I2C/SPI adapter, mock |
| AI / LLM | `MyApp.LLM` | OpenAI, Anthropic, Bedrock, local |
| S3 / object storage | `MyApp.ObjectStore` | AWS S3, MinIO, local fs |
| SMS | `MyApp.SMS` | Twilio, Vonage |
| Analytics | `MyApp.Analytics` | Segment, Mixpanel, null |

**Do NOT create a port for:**
- Standard library (`String`, `Enum`, `File` when used normally)
- Internal context-to-context calls (use the context's public API directly)
- One-off reads of simple resources (unless the read is fallible and you want to swap it)

### 4.4 Hexagonal rules

1. **The port is owned by the domain that uses it.** Do not put `MyApp.PaymentGateway` in a generic `lib/common/` — put it in `lib/my_app/billing/`.
2. **The adapter translates to domain types at the boundary.** Never let foreign types leak into domain code.
3. **The port is as small as possible.** If `Billing` uses `charge/2` and `refund/1`, do not add `subscribe/2` and `list_transactions/1` to the same behaviour just because Stripe supports them.
4. **Config selects the adapter.** `Application.compile_env` for apps; `Application.get_env` for libraries (see [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §8.6).
5. **Test with Mox against the same behaviour.** One behaviour, N adapters, including a Mock for tests. Zero changes to domain code between environments.

### 4.5 Common mistakes with hexagonal

**Mistake 1: The "generic Repo" anti-port.**

```elixir
# BAD — port too generic; adapter does too much
defmodule MyApp.Storage do
  @callback store(key :: term(), value :: term()) :: :ok
  @callback fetch(key :: term()) :: {:ok, term()} | {:error, :not_found}
end
```

This port tries to abstract "storage" generically. The adapter (`Storage.Ecto`, `Storage.ETS`) would end up with wildly different semantics and error modes. Instead, put specific domain operations behind specific ports: `MyApp.Accounts.UserRepo`, `MyApp.Catalog.ProductSearch`.

**Mistake 2: Port in the wrong place.**

```elixir
# BAD — port under infrastructure
defmodule MyApp.Infrastructure.PaymentGateway do
  @callback charge(...) :: ...
end

# GOOD — port under the domain that uses it
defmodule MyApp.Billing.PaymentGateway do
  @callback charge(...) :: ...
end
```

The port is a domain contract. It belongs in the domain directory.

**Mistake 3: Adapter leaks foreign types.**

```elixir
# BAD — adapter returns Stripe's native type
@impl true
def charge(amount, token) do
  Stripe.Charge.create(%{amount: amount, source: token})  # returns {:ok, %Stripe.Charge{}}
end
# Domain code now depends on %Stripe.Charge{} — hexagonal benefit lost

# GOOD — adapter translates to domain type
@impl true
def charge(amount, token) do
  case Stripe.Charge.create(%{amount: amount, source: token}) do
    {:ok, %Stripe.Charge{} = charge} -> {:ok, to_domain_result(charge)}
    {:error, err} -> {:error, to_domain_error(err)}
  end
end
```

**Mistake 4: Using a protocol when you should use a behaviour.**

Protocols dispatch on data type. Behaviours dispatch on module identity chosen at config time. For external adapters (you want to swap at runtime/config-time based on environment), use a behaviour. Use a protocol when you want different data types to share an interface (Enumerable, Jason.Encoder).

### 4.6 Migration path — retrofitting hexagonal

If you have an existing codebase with direct Stripe calls in your domain, here's the migration:

1. **Add a behaviour** defining the operations the domain actually uses (not everything Stripe does).
2. **Create the Stripe adapter** that implements the behaviour. Move translation logic here.
3. **Add config selection** — `Application.compile_env(:my_app, :payment_gateway, MyApp.Billing.PaymentGateway.Stripe)`.
4. **Replace direct calls** in the domain with calls through the port.
5. **Add a Mox mock** for tests; switch test config.
6. **Delete test HTTP mocks** — now tests don't hit Stripe at all.

This is the single highest-leverage refactor for most Elixir codebases.

---

## 5. Layered architecture

**Layered** = dependencies point one direction. Interface → Domain → Infrastructure.

### 5.1 The three layers

```
┌─────────────────────────────────────┐
│ Interface (driving adapters)        │ ← Phoenix, CLI, LiveView, GraphQL, Oban worker entry
├─────────────────────────────────────┤
│ Domain (contexts, pure logic)       │ ← Accounts, Catalog, Orders, …
├─────────────────────────────────────┤
│ Infrastructure (driven adapters)    │ ← Repo, HTTP clients, Mailer, Cache, Ports
└─────────────────────────────────────┘

Dependencies point downward. Interface → Domain → Infrastructure.
Never upward. Never sideways (Interface → Infrastructure directly).
```

### 5.2 Layer responsibilities

**Interface layer:**
- Translate input (HTTP params, CLI args, GraphQL args, channel payloads)
- Call the domain (context public API)
- Format output (render HTML, JSON, LiveView assigns, channel replies)
- **NO business logic.**
- **NO direct `Repo` calls.**
- **NO framework-free modules here** — this layer IS the framework layer.

**Domain layer:**
- Business rules (validations, calculations, workflows)
- State transitions (when is an order cancellable? what makes a cart checkoutable?)
- Orchestration across infrastructure (`with {:ok, user} <- Users.find(…), :ok <- Mailer.send(…)`)
- **NO framework references.** No `Phoenix.*`, no `Routes.*`, no `Plug.*`.
- **NO direct HTTP / email / file I/O** — call through behaviours.

**Infrastructure layer:**
- Adapters (Repo usage, HTTP clients, mailers, cache, hardware)
- Framework integration (Phoenix endpoints, Phoenix.PubSub, Oban)
- Cross-cutting concerns (telemetry, logging)
- **Implements domain behaviours** — does not define them.

### 5.3 Layered + hexagonal + modular monolith = the Elixir default

The three styles combine naturally:

- **Modular monolith** is the unit (one app, one deploy)
- **Layered** is the inside of the app (interface → domain → infrastructure)
- **Hexagonal** is how the domain connects to infrastructure (via behaviours)

You get all three by default if you:
1. Use one Mix app (`modular monolith`)
2. Keep `lib/my_app/` (domain) and `lib/my_app_web/` (interface) separate (`layered`)
3. Put external dependencies behind behaviours (`hexagonal`)

This is 98% of Elixir applications. Everything else is an elaboration.

### 5.4 Violations and how to fix them

**Violation 1: Controller doing business logic.**

```elixir
# BAD — business logic in the interface layer
def create(conn, %{"order" => params}) do
  changeset = Order.changeset(%Order{}, params)
  if total = calculate_total(params["items"]) && total > 1000 do
    # Discount logic in a controller!
    discounted = apply_bulk_discount(params)
    # ...
  end
end

# GOOD — interface translates + delegates
def create(conn, %{"order" => params}) do
  case MyApp.Orders.place_order(params) do
    {:ok, order} -> redirect(conn, to: ~p"/orders/#{order.id}")
    {:error, changeset} -> render(conn, :new, changeset: changeset)
  end
end
```

**Violation 2: Domain importing framework.**

```elixir
# BAD — domain depends on Phoenix
defmodule MyApp.Orders do
  alias MyAppWeb.Router.Helpers, as: Routes    # VIOLATION
  import Phoenix.Controller                     # VIOLATION

  def complete_order(order) do
    url = Routes.order_url(MyAppWeb.Endpoint, :show, order)  # URL in domain!
    Mailer.send_completion_email(order.user.email, url)
  end
end

# GOOD — domain returns data; interface builds URLs
defmodule MyApp.Orders do
  def complete_order(order) do
    with {:ok, order} <- mark_completed(order) do
      MyApp.Mailer.queue_completion_email(order)
      {:ok, order}
    end
  end
end

# Then — the mailer or the caller builds URLs using Routes
```

**Violation 3: Interface calling Repo directly.**

```elixir
# BAD
def index(conn, _) do
  products = Repo.all(Product)       # Controller doing Repo — skipping context
  render(conn, :index, products: products)
end

# GOOD
def index(conn, _) do
  products = MyApp.Catalog.list_products()
  render(conn, :index, products: products)
end
```

**Violation 4: Domain calling HTTP / email / I/O directly.**

```elixir
# BAD
defmodule MyApp.Accounts do
  def register(attrs) do
    with {:ok, user} <- Repo.insert(User.changeset(%User{}, attrs)) do
      HTTPoison.post("https://api.mailgun.net/v3/...", {:form, [...]})  # direct HTTP!
      {:ok, user}
    end
  end
end

# GOOD — domain calls through a behaviour
defmodule MyApp.Accounts do
  def register(attrs) do
    with {:ok, user} <- Repo.insert(User.changeset(%User{}, attrs)),
         :ok <- MyApp.Mailer.send_welcome(user) do
      {:ok, user}
    end
  end
end
```

### 5.5 Test what each layer means

**Interface layer tests** use `Phoenix.ConnTest`, `LiveViewTest`, etc. They hit the actual router and framework.

**Domain layer tests** should use plain `ExUnit.Case` with NO framework imports. If you can't test a context function without starting Phoenix, your layering is wrong.

**Infrastructure tests** are usually Mox-based (behaviours + mocks). The real adapter is integration-tested occasionally.

**The testability test**: can you test a domain function with `use ExUnit.Case` (not `MyAppWeb.ConnCase`)? If not, the domain depends on the interface layer. Find out where and cut it.

---

## 6. Event-driven architecture

Three distinct patterns, often conflated. Distinguish them during design.

### 6.1 Event Notification

**Publisher broadcasts that something happened. Subscribers decide what to do. Event carries minimal data.**

```elixir
# Publisher — "this happened"
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:order_completed, order_id})

# Subscriber — fetches what it needs
def handle_info({:order_completed, order_id}, state) do
  order = MyApp.Orders.get_order!(order_id)    # Callback to source for data
  send_confirmation(order)
  {:noreply, state}
end
```

**Trade-offs:**
- ✅ Simple; publisher fully decoupled from subscribers
- ✅ Small payloads; no serialization concerns
- ❌ Subscriber must call back to source for data (coupling to source context)
- ❌ N subscribers = N callbacks = potential N+1 query amplification

**Use when:** the callback to source is cheap; subscribers are few; data is read-mostly.

### 6.2 Event-Carried State Transfer

**Event carries all the data subscribers need. No callback required.**

```elixir
event = %{
  order_id: order.id,
  customer_email: order.customer.email,
  items: Enum.map(order.items, &%{name: &1.name, qty: &1.quantity, price: &1.price}),
  total: order.total,
  completed_at: DateTime.utc_now()
}
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:order_completed, event})

# Subscriber — has everything
def handle_info({:order_completed, event}, state) do
  send_confirmation(event.customer_email, event)   # No callback needed
  {:noreply, state}
end
```

**Trade-offs:**
- ✅ Subscribers fully decoupled from source — no runtime dependency
- ✅ Scales to many subscribers without N+1
- ❌ Event payload is larger
- ❌ Publisher must anticipate what subscribers need
- ❌ Event schema evolution is harder (subscribers may depend on fields)

**Use when:** subscribers outnumber callbacks; events cross context boundaries; you can't afford callback coupling.

### 6.3 Event Sourcing

**Events ARE the source of truth. Current state is derived by replaying events.**

```
Standard:  DB row is truth; events are notifications.
Sourced:   Event log is truth; current state is a projection.
```

```elixir
# Commands are intentions
%PlaceOrder{customer_id: 42, items: [...]}

# Aggregate validates command and emits events
def execute(%Order{status: :new}, %PlaceOrder{customer_id: id, items: items}) do
  [%OrderPlaced{order_id: generate_id(), customer_id: id, items: items, placed_at: DateTime.utc_now()}]
end

# Events are applied to reconstruct state
def apply(%Order{} = order, %OrderPlaced{order_id: id, items: items}) do
  %{order | id: id, items: items, status: :placed}
end

# Projections build read models from events (one per query pattern)
project(%OrderPlaced{} = event, fn multi ->
  Ecto.Multi.insert(multi, :listing, %OrderListingEntry{...})
end)
```

**Trade-offs:**
- ✅ Perfect audit trail (events are immutable history)
- ✅ Replay / debug by replaying events
- ✅ Multiple read models from one event stream
- ✅ Time-travel (rebuild state at any point in history)
- ❌ Significantly more complex than standard Ecto
- ❌ Schema evolution requires event versioning
- ❌ Eventual consistency between events and projections
- ❌ Storage grows indefinitely (unless you snapshot)

**Use when:**
- Perfect audit trail is a business / regulatory requirement
- Complex long-lived processes (insurance claims, multi-step workflows, loan origination)
- Undo / replay capabilities needed
- Multiple very different read views of the same data

**DON'T use when:** standard CRUD fits. Event sourcing is not "better CRUD" — it's a different paradigm with significant operational overhead. Most apps should not event-source most contexts.

See the `event-sourcing` skill for Commanded implementation details.

### 6.4 Event-driven decision

```
Do you need async coupling between contexts?
├── No (synchronous is fine) → Direct function calls (not event-driven)
├── Fire-and-forget notification, loss OK → Event Notification (§6.1)
├── Subscribers shouldn't call back to source → Event-Carried State Transfer (§6.2)
├── Need backpressure between producer and consumer → GenStage / Broadway (see integration-patterns.md)
├── Events must survive crashes → Oban (see integration-patterns.md)
└── Events ARE the source of truth → Event Sourcing (§6.3)
```

### 6.5 Common event-driven mistakes

**Mistake 1: Using Event Notification when data is expensive to fetch.**

Subscriber callback → source becomes an N+1 query amplifier. Switch to Event-Carried State Transfer (larger payloads, but one fetch at publish time instead of N fetches at subscribe time).

**Mistake 2: Assuming events arrive in order across nodes.**

`Phoenix.PubSub` and `:pg` do not guarantee cross-node ordering. If your logic depends on ordering, either stay single-node or use an ordered store (Kafka, EventStore).

**Mistake 3: Using PubSub when you actually need persistence.**

PubSub events are lost if subscribers are down. If your "notification" MUST be delivered, you need Oban or an event store, not PubSub.

**Mistake 4: Event-sourcing everything.**

Event sourcing has real operational cost. Event-source the contexts that need it (Orders, Payments, Compliance-adjacent) and leave Accounts / Catalog / Settings as normal CRUD.

---

## 7. CQRS — Command Query Responsibility Segregation

Three levels of escalating complexity.

### 7.1 Level 1: Light CQRS (default — most apps already do this)

Same context has **query functions** (reads) and **command functions** (writes). Same database.

```elixir
defmodule MyApp.Catalog do
  # === Queries (reads) ===
  def list_products, do: Repo.all(Product)
  def get_product!(id), do: Repo.get!(Product, id)
  def search_products(query), do: Product.search(query) |> Repo.all()

  # === Commands (writes) ===
  def create_product(attrs) do
    %Product{} |> Product.changeset(attrs) |> Repo.insert()
  end
  def update_product(product, attrs) do
    product |> Product.changeset(attrs) |> Repo.update()
  end
  def delete_product(product), do: Repo.delete(product)
end
```

**This is CQRS.** Queries return data. Commands return ok/error. Same DB serves both. **Most apps never need more.**

### 7.2 Level 2: Separated Read Path

Extract query modules. Optionally use read replicas.

```elixir
# Write path: standard context
defmodule MyApp.Catalog do
  def create_product(attrs), do: ...
  def update_product(product, attrs), do: ...

  # Delegate reads to the query module
  defdelegate top_sellers(limit \\ 10), to: MyApp.Catalog.Queries
  defdelegate category_analytics(category), to: MyApp.Catalog.Queries
end

# Read path: specialized query module
defmodule MyApp.Catalog.Queries do
  @moduledoc false
  import Ecto.Query

  def top_sellers(limit) do
    from(p in Product,
      join: oi in OrderItem, on: oi.product_id == p.id,
      group_by: p.id,
      order_by: [desc: count(oi.id)],
      limit: ^limit,
      select: %{product: p, sales_count: count(oi.id)}
    ) |> Repo.all()
  end
end
```

**Optional read replica for heavy reads:**

```elixir
# config/runtime.exs
config :my_app, MyApp.ReadRepo,
  url: System.fetch_env!("READ_DATABASE_URL"),
  read_only: true

# Query module uses read replica
def top_sellers(limit), do: from(...) |> MyApp.ReadRepo.all()
```

**Use when:**
- Dashboard/reporting queries are slow and contend with writes
- Search needs a different data structure (e.g., Elasticsearch indexed separately)
- Analytics need pre-aggregated data
- Read traffic is 10× or more the write traffic

### 7.3 Level 3: Full CQRS + Projections (with event sourcing)

Writes go to an event store. Reads come from purpose-built projections (materialized views).

```
Command → Aggregate → Event Store (append-only)
                            ↓
         ┌──────────────────┼──────────────────┐
         ↓                  ↓                  ↓
   ProductList        ProductSearch        SalesDashboard
   (Ecto table)       (Elasticsearch)      (TimescaleDB)
```

- Each projection is optimized for a specific query pattern
- Projections are rebuildable from the event log (disaster recovery!)
- Eventual consistency between the event store and projections

Full implementation: see the `event-sourcing` skill (Commanded library).

**Use when:**
- Event sourcing is already in use (Level 3 depends on Level 2 of event sourcing)
- Multiple very different read views of the same data
- Read/write scaling needs are dramatically different
- Eventual consistency between read models is acceptable

### 7.4 CQRS decision

| Signal | Level | Approach |
|---|---|---|
| Standard web app, moderate traffic | Light (1) | Queries and commands in same context, same DB |
| Complex reporting alongside CRUD | Separated (2) | Query modules; optional read replica |
| Dashboard queries contend with writes | Separated (2) | Read replica; pre-aggregated tables |
| Full audit trail + different read stores | Full (3) | Event sourcing + projections |
| "Should I use CQRS?" uncertainty | Light (1) | You're probably already doing it |

### 7.5 CQRS anti-patterns

**Anti-pattern 1: Level 2 without measurement.**

Extracting query modules "just in case" adds indirection. Only separate when you can point to a concrete pain (slow dashboard, read/write contention, different store needed).

**Anti-pattern 2: Level 3 without event sourcing.**

Level 3 (projections) assumes the event store is the source of truth. If you're still using a standard DB, you don't have projections — you have caches. Use Level 2 with a proper cache invalidation strategy instead.

**Anti-pattern 3: Different database per context "because CQRS."**

CQRS is about read/write separation within a context, not cross-context data splitting. Different contexts can have different tables, but they should still live in the same database (for transactions, backups, migrations). Only split databases for genuine scaling or compliance reasons.

---

## 8. Microservices — why Elixir rarely needs them

OTP provides fault isolation (supervision), independent scaling (process pools), loose coupling (contexts + PubSub), service discovery (Registry, `:pg`). **The Elixir default is the modular monolith.**

### 8.1 Legitimate reasons to split

| Signal | Why separate service |
|---|---|
| **Different language needed** | GPU service in Python/CUDA, web in Elixir |
| **Regulatory/compliance isolation** | Payment processing must be PCI-isolated |
| **Wildly different scaling needs** | Video transcoding vs. web API |
| **Separate teams with separate release cycles** | Org-driven |
| **Legacy system integration** | Wrap legacy behind an API boundary |

### 8.2 Illegitimate reasons to split

Do NOT split for:

| Claim | Real solution |
|---|---|
| "It's getting big" | Add contexts |
| "We want loose coupling" | Use behaviours and PubSub |
| "We want fault isolation" | Use supervision trees |
| "We want independent scaling" | Process pools, `Task.async_stream`, Broadway |
| "Microservices are modern" | Elixir is already ahead of this trend |

### 8.3 If you must split

Do it right:

- **Communicate via well-defined APIs** (HTTP/gRPC) — not shared databases
- **Each service owns its data** (separate databases)
- **Async integration via message broker** (Kafka, RabbitMQ) — Broadway consumes
- **For Elixir-to-Elixir within a trusted network**: `:erpc` is an option
- **Distributed tracing** is mandatory across service boundaries
- **Backward-compatible API evolution** — once you split, you can't refactor across boundaries

**The cost of a split is permanent.** Merging back is ~10× harder than splitting forward.

---

## 9. Styles combine per context

Different contexts in the same application can use different styles.

```
Typical large Elixir app (modular monolith):

┌──────────────────────────────────────────────────┐
│  Accounts context          Orders context         │
│  ├─ Light CQRS             ├─ Event sourcing      │
│  ├─ Direct Ecto            │  (Commanded)         │
│  └─ Request-response       ├─ Full CQRS           │
│                            │  (projections)       │
│  Catalog context           ├─ Event-driven        │
│  ├─ Separated read path    │  (process managers)  │
│  │  (search index)         └─ Sagas for workflows │
│  └─ Event-carried state                           │
│     transfer (PubSub)      Notifications context  │
│                            ├─ Event notification  │
│                            │  (subscribes PubSub) │
│                            └─ Oban for delivery   │
│                                                    │
│  ─── All in one Mix release, one supervision ──   │
│  ─── tree, one deployment                    ──   │
└──────────────────────────────────────────────────┘
```

**The boundary module (context) is what enables this — callers don't know or care what style is used internally.** Start simple; evolve individual contexts into richer patterns as their domains demand.

**Migration path for individual contexts:**

1. Start every context as plain Ecto CRUD (Light CQRS)
2. When a specific context needs separated reads, move it to Separated Read Path
3. When a specific context needs audit/replay, move it to Event Sourcing
4. When a specific context needs multiple read stores, move it to Full CQRS

Each migration affects only the affected context. Callers don't change.

---

## 10. Cross-references

### Within this skill

- `SKILL.md §4` — architectural principles (the eleven)
- `SKILL.md §12` — architectural styles overview + decision tree
- [process-topology.md](process-topology.md) — how styles map to supervision trees
- [integration-patterns.md](integration-patterns.md) — inter-context mechanisms (GenStage, Oban, event sourcing) used by event-driven and CQRS styles
- [data-ownership-deep.md](data-ownership-deep.md) — aggregate design, multi-tenancy across styles
- [otp-design.md](otp-design.md) — OTP choices per style
- [test-strategy.md](test-strategy.md) — testing architecture per style (hexagonal testability)
- [growing-evolution.md](growing-evolution.md) — evolving styles as the app grows

### In other skills

- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §10 — implementing contexts and boundaries (code templates)
- [../elixir-reviewing/SKILL.md](../elixir-reviewing/SKILL.md) §7.1 — architectural review checklist
- `../elixir/architecture-reference.md` — the general reference; this subskill is planning-phase framing of the same material

---

**End of architecture-patterns.md.** This subskill is for planning-mode deep walkthroughs. For the decision tables, see `SKILL.md`. For code-level templates, see [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md).
