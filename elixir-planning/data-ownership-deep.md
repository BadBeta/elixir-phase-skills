# Data Ownership & Consistency — deep reference

Phase-focused deep reference for the hardest data questions in planning: **who owns what**, **how do aggregates stay consistent**, **what happens when an operation crosses contexts**, **how is multi-tenancy enforced**, and **how do we design for retries without duplicating effects**.

**When to load:** when designing a new data model, when two contexts seem to need the same table, when planning multi-tenancy, when a workflow crosses context boundaries, or when an operation will be retried (Oban, webhooks, event handlers).

**Related:**
- `SKILL.md §7` — data ownership overview + decision tables
- [architecture-patterns.md](architecture-patterns.md) — how data ownership fits with architectural styles
- [integration-patterns.md](integration-patterns.md) — sagas, process managers, event sourcing for cross-context flows
- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §10.4 — implementing context-level Ecto queries

---

## 1. Rules for data ownership planning (LLM)

1. **ALWAYS assign each table to exactly ONE owning context.** That context is the only writer. Other contexts read through its public API.
2. **NEVER let two contexts write to the same table.** This is the single most damaging violation of modular design.
3. **ALWAYS identify aggregate boundaries.** An aggregate is the transactional consistency unit. Operations within an aggregate are atomic; operations across aggregates are eventual.
4. **ALWAYS design for retries.** Any operation that can be retried (Oban, webhook handler, event handler, distributed call) must be idempotent.
5. **ALWAYS choose a tenancy strategy at project start.** Row-level, schema-per-tenant, or database-per-tenant — retrofitting any of these is painful.
6. **NEVER put tenant scoping logic scattered across contexts.** Enforce at the repo / data layer. Contexts shouldn't remember to filter.
7. **PREFER merging contexts over cross-context transactions.** If two aggregates always change together, they belong in one context.
8. **ALWAYS distinguish "strong consistency required" from "eventual consistency acceptable."** The answer dictates whether you can use async, saga, or must keep in one transaction.
9. **ALWAYS design event-sourced aggregates around the consistency boundary.** Aggregate = command target = event producer = consistency unit.
10. **NEVER store the same data in two places** unless you have a clear replication / sync story. Multiple sources of truth is the bug factory.
11. **ALWAYS plan the ownership migration path.** If data ownership is changing (extracting a context, moving a table), the migration is hard — plan it before starting.

---

## 2. Data ownership — the core rule

### 2.1 The rule

**Every persistent data item (table, document, stream, etc.) is owned by exactly one context. That context is the only one allowed to write to it.** Other contexts read through the owning context's public API.

```elixir
# Accounts OWNS the users table — only Accounts writes
defmodule MyApp.Accounts do
  def create_user(attrs), do: ...
  def update_user(user, attrs), do: ...
  def get_user!(id), do: Repo.get!(User, id)
end

# Orders REFERENCES users (foreign key), never writes
defmodule MyApp.Orders do
  def create_order(user_id, items) do
    user = MyApp.Accounts.get_user!(user_id)   # Read via owner's API
    # ... create order with user_id foreign key
  end
end
```

**Why this matters:**
- Schema changes affect one context at a time
- Invariants are enforced at one place (the owning context)
- Data migrations are scoped to the owner
- Team ownership is clear
- Boundary is enforceable (reviewable, testable)

### 2.2 Cross-context foreign keys are fine

Foreign keys from Orders to Accounts are fine:

```sql
orders
  id: integer
  user_id: integer REFERENCES users(id)  -- FK to another context's table — OK
  ...
```

But the FK doesn't grant write permission. Orders can reference user_id; it cannot write to the users table.

### 2.3 Reading across contexts

Always through the owning context's public API — never via `Repo.preload` across contexts.

```elixir
# BAD — Orders preloads from Accounts
def list_orders_with_users do
  Order |> preload(:user) |> Repo.all()    # User belongs to Accounts
end

# GOOD — Orders asks Accounts for the data it needs
def list_orders_with_users do
  orders = Repo.all(Order)
  user_ids = Enum.map(orders, & &1.user_id) |> Enum.uniq()
  users = MyApp.Accounts.list_users_by_ids(user_ids) |> Map.new(&{&1.id, &1})
  Enum.map(orders, &Map.put(&1, :user, Map.get(users, &1.user_id)))
end
```

**Pragmatic exception in smaller apps:** `preload` across contexts is a common violation. It works. It's inferior architecture but not a bug. Flag it for reviewers, but don't block small PRs on it.

### 2.4 When two contexts seem to need the same table

This is the hardest ownership question. Three options:

1. **One owns it; the other reads through the API.** Default answer. Pick the context that logically creates the rows.
2. **The data belongs in a shared kernel.** Rare but valid — e.g., `MyApp.Shared.Money`, `MyApp.Shared.Address` — shared value types used by multiple contexts.
3. **The split is wrong; merge the contexts.** If both contexts *always* touch the data together, they're one context pretending to be two.

**Never:** have two contexts both writing to the same table. That's the "shared database" anti-pattern from microservices, imported into a monolith.

### 2.5 Decision: who owns this data?

Ask:
1. **Who creates it?** First writer usually owns it.
2. **Who's the authority on its invariants?** The context with the business rules.
3. **Which team works on it?** Match ownership to team (Conway's Law).
4. **Which feature changes it most?** That context probably owns it.

---

## 3. Aggregates — the consistency boundary

### 3.1 What is an aggregate?

An **aggregate** is a cluster of entities that must stay consistent as a unit. The **aggregate root** is the entry point — you load the root; you save the root; all invariants are enforced at the root.

Ecto maps this to schemas with `has_many` / `has_one` and `cast_assoc` / `cast_embed`.

### 3.2 Canonical example — Order + OrderItems

```elixir
defmodule MyApp.Orders.Order do
  use Ecto.Schema
  import Ecto.Changeset

  schema "orders" do
    field :status, Ecto.Enum, values: [:pending, :confirmed, :shipped, :cancelled]
    field :total, :decimal
    has_many :items, MyApp.Orders.OrderItem, on_replace: :delete
    timestamps()
  end

  def changeset(order, attrs) do
    order
    |> cast(attrs, [:status])
    |> cast_assoc(:items, required: true, with: &MyApp.Orders.OrderItem.changeset/2)
    |> validate_at_least_one_item()
    |> validate_consistent_totals()
  end
end

# The context operates on the aggregate ROOT
defmodule MyApp.Orders do
  def place_order(attrs) do
    %Order{}
    |> Order.changeset(attrs)
    |> Repo.insert()
  end

  def add_item(%Order{} = order, item_attrs) do
    order
    |> Order.changeset(%{items: order.items ++ [item_attrs]})
    |> Repo.update()
  end
end
```

### 3.3 Aggregate rules

1. **Load / save through the root.** Never load an OrderItem without its Order.
2. **One aggregate per transaction.** `Repo.insert(order)` saves the root + all children atomically.
3. **Different aggregates communicate through events or sagas.** No cross-aggregate multi-step transactions.
4. **Invariants enforced at the root.** `validate_at_least_one_item` is on Order.changeset, not OrderItem.changeset.
5. **Foreign keys across aggregates, not object graphs.** An Order has a user_id pointing at Accounts — but doesn't `has_one :user`.

### 3.4 How big should an aggregate be?

**Small aggregates are easier to reason about.** But "small" is relative to consistency requirements.

Aggregate size heuristics:
- **If removing a child leaves the parent invalid → they're the same aggregate** (Order requires ≥1 item)
- **If the child has independent lifecycle → different aggregate** (Comment on Post — comments can exist, be edited, deleted independently; often separate aggregate)
- **If invariants span two entities atomically → same aggregate** (InventoryItem count + reservation must sum correctly → same aggregate)
- **If cross-entity operation can tolerate eventual consistency → separate aggregates** (Order placed + Inventory reduced don't need the same transaction — use saga or PubSub)

### 3.5 Aggregate design — worked examples

**E-commerce:**

| Aggregate | Root | Children | Why |
|---|---|---|---|
| Order | Order | OrderItems, ShippingAddress | Items and total must stay consistent |
| Product | Product | Variants, Prices, Inventory | Variants and inventory are per-product |
| Customer | Customer | Addresses, PaymentMethods | All owned by customer; lifecycle tied |
| Review | Review | — | Standalone; references Product by FK |

**SaaS app:**

| Aggregate | Root | Children | Why |
|---|---|---|---|
| User | User | EmailAddresses, Sessions | Auth data tied to user |
| Organization | Organization | Members, Settings | Org-wide consistency |
| Subscription | Subscription | Invoices (recent) | Billing state must be coherent |

**Healthcare:**

| Aggregate | Root | Children | Why |
|---|---|---|---|
| Patient | Patient | Contacts, Allergies | Core identity + immediate medical refs |
| Encounter | Encounter | Observations, Diagnoses | Single clinical episode atomicity |
| Medication | Medication | — | Catalog entity; reference-only |

### 3.6 Anti-pattern: the mega-aggregate

```elixir
# BAD — User aggregate pulling in everything related to a user
defmodule MyApp.Accounts.User do
  schema "users" do
    has_many :orders, MyApp.Orders.Order              # Wrong: Orders is a different aggregate!
    has_many :reviews, MyApp.Catalog.Review           # Wrong: Review is a different aggregate!
    has_many :notifications, MyApp.Notifications.Notification  # Wrong!
    # ...
  end
end
```

**Why bad:**
- User changes now conflict with Order changes
- `Repo.insert(user)` with `cast_assoc(:orders)` would update all orders too
- Locks held longer (row locks on all the children)
- Tests need to set up massive fixtures

**Fix:** Use foreign keys (orders.user_id) but not associations in the schema. Don't `has_many :orders` in User. The Orders context handles orders.

### 3.7 When NOT to use cast_assoc / cast_embed

`cast_assoc` is for cases where children are logically part of the parent. If children have independent lifecycle, use separate changesets + explicit ordering:

```elixir
# When Order and Refund are the same aggregate — use cast_assoc
cast_assoc(changeset, :refunds)

# When Order and Review are different aggregates — use separate operations
with {:ok, order} <- Orders.place_order(attrs),
     {:ok, _review} <- Catalog.create_review(%{order_id: order.id, ...}) do
  ...
end
```

---

## 4. Cross-context transactions

### 4.1 The question

An operation spans multiple aggregates / contexts. How do we maintain invariants?

```elixir
# "When an order is placed, reserve stock, charge payment, create order"
# These are three aggregates in three contexts.
```

### 4.2 Option 1: merge if they're always together

If this flow is the canonical way these contexts are used, they're not really three contexts:

```elixir
# Instead of Catalog + Billing + Orders:
defmodule MyApp.Orders do
  # Owns orders, owns stock reservations (stock_holds), owns payment attempts (payment_attempts)
  def place_order(...), do: Repo.transaction(fn -> ... end)   # Atomic across all three
end
```

**Use when:** the flow is THE flow. No one reserves stock without placing an order; no one attempts payment without placing an order.

### 4.3 Option 2: saga (compensating actions)

When contexts are genuinely separate, use a saga — sequence of operations with explicit rollback.

```elixir
defmodule MyApp.OrderSaga do
  def place_order(user_id, items) do
    with {:ok, reservation} <- MyApp.Catalog.reserve_stock(items),
         {:ok, payment} <- MyApp.Billing.charge(user_id, total(items)),
         {:ok, order} <- MyApp.Orders.create(user_id, items, payment.id) do
      {:ok, order}
    else
      {:error, :payment_failed} ->
        MyApp.Catalog.release_stock(reservation)
        {:error, :payment_failed}
      {:error, :out_of_stock} ->
        {:error, :out_of_stock}
      {:error, :order_failed} = err ->
        MyApp.Catalog.release_stock(reservation)
        MyApp.Billing.refund(payment.id)
        err
    end
  end
end
```

**Use when:** contexts are properly separate; operations can fail independently; compensations are well-defined.

### 4.4 Option 3: eventual consistency

Accept that different contexts will be briefly inconsistent.

```elixir
def place_order(user_id, items) do
  with {:ok, order} <- MyApp.Orders.create(user_id, items) do
    # Order is created. Stock and payment happen async — may fail, may retry.
    Oban.insert(MyApp.Workers.ReserveStock.new(%{order_id: order.id}))
    Oban.insert(MyApp.Workers.ChargePayment.new(%{order_id: order.id}))
    {:ok, order}
  end
end
```

**Use when:** briefly inconsistent is OK; side effects will happen eventually (guaranteed by Oban); user sees a "processing" state.

### 4.5 Option 4: process manager (event sourced)

In event-sourced systems, a process manager orchestrates multi-aggregate workflows by listening to events and emitting commands.

```elixir
defmodule MyApp.OrderFulfillmentProcess do
  use Commanded.ProcessManagers.ProcessManager

  def handle(%{}, %OrderPlaced{} = event) do
    [%CapturePayment{order_id: event.order_id, amount: event.total}]
  end

  def handle(%{payment_captured: true}, %StockReserved{} = event) do
    [%CompleteFulfillment{order_id: event.order_id}]
  end
end
```

**Use when:** event sourcing is already in place; workflow is long-lived; timeouts / retries should be declarative.

### 4.6 Cross-context decision

| Operation characteristic | Strategy |
|---|---|
| Always happens together, short duration | Merge contexts; `Ecto.Multi` |
| Separate contexts, atomic required, short duration | Saga with compensating actions |
| Eventually consistent is acceptable | Async via Oban |
| Event sourcing already used, long-lived workflow | Process manager |
| You can't decide — it keeps oscillating | The contexts are probably wrong. Re-examine boundaries. |

---

## 5. Idempotency — design for retries

### 5.1 Why

Any operation that can be retried MUST be idempotent. Retries happen at:

- Oban workers (`max_attempts: 5` — will run up to 5 times)
- Webhook handlers (provider retries on non-2xx)
- Event handlers / projectors (may replay events)
- Distributed / HTTP calls (network may retry)
- Saga compensations (may be interrupted mid-compensation and retried)

### 5.2 What "idempotent" means

**Executing the operation N times produces the same effect as executing it once.** Side effects visible to the outside world happen at most once (or cleanly repeat).

### 5.3 The three patterns

**Pattern 1: Check state first**

```elixir
def charge_order(order_id) do
  order = Orders.get_order!(order_id)
  case order.payment_status do
    :charged -> {:ok, order}   # Already done
    :pending ->
      with {:ok, result} <- PaymentGateway.charge(order.total, order.token) do
        Orders.mark_charged(order, result.transaction_id)
      end
  end
end
```

**Pattern 2: Unique constraint / on-conflict**

```elixir
# Database-level dedup
def record_event(event_id, data) do
  %Event{id: event_id, data: data}
  |> Repo.insert(on_conflict: :nothing)   # Silently skip if already inserted
end

# Oban unique constraint
%{order_id: order.id}
|> ChargeWorker.new(unique: [period: 300, keys: [:order_id]])
|> Oban.insert()
```

**Pattern 3: External idempotency key**

```elixir
# Stripe charge with idempotency key
def charge_order(order) do
  PaymentGateway.charge(order.total, order.token,
    idempotency_key: "order-#{order.id}-#{order.charge_attempt}"
  )
end
```

External services (Stripe, Square) support an idempotency key. Same key = returns cached result; never double-charge.

### 5.4 Levels of idempotency

| Level | Guarantee | Use |
|---|---|---|
| **Strong** | N runs = 1 effect. No visible difference. | Financial ops, event recording, webhook ACK |
| **Weak** | N runs = idempotent side effect, but observable (e.g., N log lines) | Log-level idempotency, analytics |
| **None** | N runs = N effects | Fire-and-forget audits — usually a bug to have this when retryable |

Aim for **strong** idempotency on everything retryable. Financial operations especially.

### 5.5 Designing for idempotency from the start

Plan before implementing:

1. **Identify every retryable operation.** Is it in Oban? A webhook? An event handler? A saga compensation?
2. **Decide the idempotency key.** Is it the business ID (order_id)? A generated request ID? An external service's transaction ID?
3. **Decide where to enforce it.** At the DB (unique constraint)? In-memory (check-state-first)? At the external service (idempotency_key parameter)?
4. **Design the schema to support it.** Do you need an `idempotency_key` column? A `status` column with a state machine? A unique index?

**Retrofitting idempotency is painful.** Plan it in.

### 5.6 Saga compensation must also be idempotent

Compensating actions run when the primary fails. If compensation is also interrupted, it too may retry.

```elixir
# BAD — compensation may over-release if interrupted and retried
def release_stock(reservation_id) do
  reservation = Repo.get!(Reservation, reservation_id)
  # ... adds items back to stock, deletes reservation ...
  # If this crashes halfway, retry may release stock twice
end

# GOOD — idempotent compensation
def release_stock(reservation_id) do
  case Repo.get(Reservation, reservation_id) do
    nil -> :ok
    %{status: :released} -> :ok   # Already released
    %{status: :held} = r -> do_release(r)
  end
end
```

---

## 6. Eventual consistency

### 6.1 When to accept it

Asynchronous cross-context communication implies eventual consistency. Different contexts may temporarily disagree about current state.

**Accept for:**
- Non-critical reads (dashboards, analytics, search)
- Notification delivery
- Projections (read models derived from events)
- Cache invalidation

**Require strong consistency for:**
- Financial operations (use `Ecto.Multi` or saga)
- Regulatory / compliance records (use event sourcing or Multi)
- Data that must be coherent on read (use Multi or single aggregate)

### 6.2 Making eventual consistency livable

**Design principles:**

1. **Show clear state indicators.** "processing" / "confirmed" / "failed" UI states so users understand.
2. **Design handlers to be idempotent** — they may process the same event twice.
3. **Use optimistic UI updates** — show expected state immediately, correct via PubSub on confirmation.
4. **Bound the inconsistency window.** "All events processed within 5s" is a SLA. Monitor it.
5. **Plan for detection.** Reconciliation jobs that detect drift between contexts (daily / hourly).
6. **Plan for replay.** If a projection gets wrong, can you rebuild it from events?

### 6.3 Pattern: eventual consistency with optimistic UI

```elixir
# LiveView — optimistic update, corrected by PubSub later
def handle_event("add_to_cart", %{"product_id" => id}, socket) do
  # 1. Optimistic local update (user sees it immediately)
  cart = [id | socket.assigns.cart]
  socket = assign(socket, cart: cart)

  # 2. Async server operation
  MyApp.ShoppingCart.add_async(socket.assigns.user_id, id)

  {:noreply, socket}
end

def handle_info({:cart_updated, canonical_cart}, socket) do
  # 3. Reconcile — server is the truth
  {:noreply, assign(socket, cart: canonical_cart)}
end
```

### 6.4 Reconciliation jobs

For critical data, periodically reconcile across contexts:

```elixir
defmodule MyApp.Workers.ReconcileInventory do
  use Oban.Worker, queue: :default

  @impl Oban.Worker
  def perform(_job) do
    # Compare Orders' reservations with Catalog's stock_holds
    drift = find_drift()
    if drift != [] do
      MyApp.Observability.alert_drift(drift)
      Enum.each(drift, &repair_drift/1)
    end
    :ok
  end
end

# Schedule daily
{Oban.Plugins.Cron,
  crontab: [
    {"0 2 * * *", MyApp.Workers.ReconcileInventory}
  ]}
```

---

## 7. Multi-tenancy — three strategies

### 7.1 Decision matrix

| Approach | Isolation | Complexity | When |
|---|---|---|---|
| **Row-level** (tenant_id column) | Low — shared tables | Low | Most SaaS apps; simplest start |
| **Schema-per-tenant** (Postgres schemas) | Medium | Medium | Stronger isolation; moderate tenant count (<1000) |
| **Database-per-tenant** | High | High | Regulatory requirement; wildly different data sizes; separate backups |

**Choose at project start. Retrofitting is painful.**

### 7.2 Row-level tenancy (default)

Every table has a `tenant_id` column. Enforce at the data layer.

```elixir
# Schema
defmodule MyApp.Catalog.Product do
  use Ecto.Schema
  schema "products" do
    field :tenant_id, :integer
    field :name, :string
    # ...
  end
end

# Repo-level enforcement via prepare_query
defmodule MyApp.Repo do
  use Ecto.Repo, otp_app: :my_app

  @impl true
  def prepare_query(_operation, query, opts) do
    case opts[:tenant_id] || Process.get(:current_tenant_id) do
      nil -> {query, opts}
      tenant_id -> {where(query, tenant_id: ^tenant_id), opts}
    end
  end
end

# Set once at request boundary
plug :set_tenant

defp set_tenant(conn, _) do
  Process.put(:current_tenant_id, conn.assigns.current_user.tenant_id)
  conn
end
```

**Pros:**
- Simple schema
- All tenants share one DB, one set of migrations
- Cheap to add tenants

**Cons:**
- Weaker isolation (bug in prepare_query = data leak)
- Indexes include tenant_id (all indexes become composite)
- Large-tenant queries can affect small-tenant performance

### 7.3 Schema-per-tenant

Each tenant gets a Postgres schema. All tables exist per-schema.

```elixir
defmodule MyApp.Repo do
  def tenant_prefix(tenant_id), do: "tenant_#{tenant_id}"
end

defmodule MyApp.Catalog do
  def list_products(tenant_id) do
    Product |> Repo.all(prefix: Repo.tenant_prefix(tenant_id))
  end

  def create_product(tenant_id, attrs) do
    %Product{}
    |> Product.changeset(attrs)
    |> Repo.insert(prefix: Repo.tenant_prefix(tenant_id))
  end
end
```

**Pros:**
- Strong isolation (table-level)
- Per-tenant backups / restores possible
- Large tenants don't affect small ones

**Cons:**
- Migrations must run per-schema (framework often doesn't support cleanly)
- Connection pool per tenant is complex
- At 10K+ tenants, Postgres schema count becomes a management burden

### 7.4 Database-per-tenant

Each tenant has its own database. Full isolation.

```elixir
# Each tenant has its own Repo — dynamically configured
defmodule MyApp.TenantRepos do
  def repo_for(tenant_id) do
    # Look up tenant config; start a dynamic Ecto.Repo if needed
  end
end
```

**Pros:**
- Maximum isolation
- Per-tenant DB resources (size, backup, performance)
- Compliance (patient data, PCI) may require this

**Cons:**
- Operational complexity: one DB per tenant
- Migrations must run across N databases
- Connection pools × N = resource management nightmare at scale

### 7.5 Architectural rules for multi-tenancy

1. **Choose strategy early.** Row-level is the default; escalate only for demonstrated need.
2. **Tenant scoping is infrastructure, not domain.** Enforce in the repo / data layer — contexts shouldn't remember to filter.
3. **Pass tenant_id explicitly OR set once at the interface boundary.** Don't scatter resolution throughout.
4. **Tenant-specific supervision** (for schema/DB per tenant): each tenant may need its own process subtree.
5. **Test with multiple tenants.** The #1 multi-tenancy bug is data leaking between tenants.

### 7.6 Test for leaks

Every tenant-scoped module should have a test that creates data in one tenant and verifies other tenants can't see it.

```elixir
test "tenant isolation — product listing" do
  t1 = insert(:tenant)
  t2 = insert(:tenant)
  _ = insert(:product, tenant_id: t1.id, name: "T1 Product")
  _ = insert(:product, tenant_id: t2.id, name: "T2 Product")

  products_t1 = MyApp.Catalog.list_products(tenant_id: t1.id)
  products_t2 = MyApp.Catalog.list_products(tenant_id: t2.id)

  assert length(products_t1) == 1
  assert Enum.all?(products_t1, &(&1.tenant_id == t1.id))
  assert length(products_t2) == 1
  assert Enum.all?(products_t2, &(&1.tenant_id == t2.id))
end
```

---

## 8. Data ownership migration path

### 8.1 When you need to move a table between contexts

Signs the current owner is wrong:
- The "owner" rarely changes the data but others do
- The business rules live in a different context
- The data is coupled more tightly to another context's aggregate

### 8.2 Migration steps

1. **Decide the target owner.** Agree on it before any code change.
2. **Add the table's code to the target context** (schemas, changesets, queries).
3. **Move write operations one at a time.** Start with new write paths, work backward.
4. **Keep the old context's API intact** during migration (delegates to new owner).
5. **After all writes moved, remove old context's writers.**
6. **Update other contexts' reads** to go through the new owner.
7. **Remove the delegation shim from the old context.**

### 8.3 Migration example

```elixir
# BEFORE — Billing context owned payments
defmodule MyApp.Billing do
  def create_payment(attrs), do: Repo.insert(Payment.changeset(%Payment{}, attrs))
end

# DURING — Payments context owns it; Billing delegates
defmodule MyApp.Payments do
  def create(attrs), do: Repo.insert(Payment.changeset(%Payment{}, attrs))
end

defmodule MyApp.Billing do
  defdelegate create_payment(attrs), to: MyApp.Payments, as: :create
end

# AFTER — callers updated, shim removed
defmodule MyApp.Payments do
  def create(attrs), do: Repo.insert(Payment.changeset(%Payment{}, attrs))
end
# MyApp.Billing no longer has payment functions
```

### 8.4 Migration anti-patterns

**Anti-pattern 1: big-bang move.** Rename module, update all callers in one PR. High risk; hard to review.

**Anti-pattern 2: stopping halfway.** Both contexts write to the same table during transition. Hard-to-detect bugs.

**Anti-pattern 3: moving data without moving responsibility.** The table lives in the new context but the business rules live in the old one. No progress.

---

## 9. Event sourcing and data ownership

Event sourcing changes how ownership works.

### 9.1 Events as the source of truth

In an event-sourced context:
- **Events are owned by the aggregate that emitted them.** Each event has a single writer (the aggregate).
- **Projections are derived views.** A projection belongs to the context that queries it.
- **Events cross contexts via subscription.** Other contexts subscribe to the event stream and build their own projections.

### 9.2 Aggregate = command target = event producer = consistency unit

```
Command (PlaceOrder) → Aggregate (Order) → Event (OrderPlaced)
                                  |
                                  ↓
                          [Event Store (authoritative)]
                                  |
                   ┌──────────────┼──────────────┐
                   ↓              ↓              ↓
              Projection:    Projection:    Projection:
              OrderList      SearchIndex    SalesDashboard
              (Orders ctx)   (Search ctx)   (Analytics ctx)
```

Each projection is owned by its context. Orders context owns the OrderList projection. Search context owns the SearchIndex projection. They all read the same event stream.

### 9.3 Who writes to the event store?

**Only the aggregate's command path.** Other contexts subscribe and read, but do not write events on behalf of another aggregate.

### 9.4 Cross-aggregate consistency

Cross-aggregate flows in event-sourced systems use **process managers** (see [integration-patterns.md](integration-patterns.md) §8.2). Each aggregate stays consistent internally; the process manager coordinates across them.

---

## 10. Data ownership anti-patterns

### 10.1 Shared database, shared writers

```elixir
# BAD — two contexts writing to the same table
defmodule MyApp.Accounts do
  def update_last_login(user_id), do: Repo.update_all(...)
end

defmodule MyApp.Analytics do
  def track_login(user_id) do
    Repo.update_all(...)    # Also writes users table!
    # ...
  end
end
```

**Fix:** One context owns the write; the other is a consumer (via PubSub, event, or explicit API).

### 10.2 Cross-context preload

```elixir
# BAD — Orders reaches into Accounts via preload
orders = Order |> preload(:user) |> Repo.all()
# `User` is Accounts' internal schema. Orders shouldn't know the schema exists.

# GOOD — Orders asks Accounts for the data
orders = Orders.list_recent()
user_ids = Enum.map(orders, & &1.user_id) |> Enum.uniq()
users = Accounts.list_users_by_ids(user_ids)
```

### 10.3 "God context" owning too much

```elixir
defmodule MyApp.Admin do    # Owns users, products, orders, analytics — everything
  def list_users, do: ...
  def create_product, do: ...
  def process_payment, do: ...
  def send_notification, do: ...
end
```

**Fix:** Split by domain. Accounts, Catalog, Billing, Notifications — each owns its data.

### 10.4 Cross-context transactions

```elixir
# BAD — reaching into multiple contexts' data in one transaction
Repo.transaction(fn ->
  Repo.insert!(%Order{...})           # Orders data
  Repo.update!(%Product{stock: ...})  # Catalog data
  Repo.insert!(%Payment{...})         # Billing data
end)
```

**Fix:** Saga, eventual consistency, or merge the contexts.

### 10.5 Missing tenant scoping

```elixir
# BAD — context function doesn't scope by tenant
defmodule MyApp.Catalog do
  def list_products, do: Repo.all(Product)   # Returns products from ALL tenants!
end
```

**Fix:** Enforce at the data layer (prepare_query), OR pass tenant_id explicitly — but never scatter filters.

### 10.6 Not-idempotent retryable operation

```elixir
# BAD — Oban worker charges on every retry
def perform(%{args: %{"order_id" => id}}) do
  order = Orders.get_order!(id)
  PaymentGateway.charge(order.total, order.token)
end
```

**Fix:** Check state first, or use an idempotency key.

### 10.7 Object-per-entity in DB when one row would do

Storing each attribute as a separate row + process:

```elixir
# BAD — one row per setting (EAV pattern)
settings_rows = [
  %Setting{user_id: 1, key: "theme", value: "dark"},
  %Setting{user_id: 1, key: "timezone", value: "UTC"},
  # ... 20 rows per user for settings
]

# GOOD — one row with a JSON blob or dedicated columns
%UserSettings{user_id: 1, settings: %{"theme" => "dark", "timezone" => "UTC"}}
```

EAV (Entity-Attribute-Value) is usually wrong in relational DBs. Use JSON/JSONB or dedicated columns.

---

## 11. Data ownership design worked example

### 11.1 Requirements

E-commerce app with:
- Customers can sign up, manage profile, place orders
- Products have variants, prices, inventory
- Orders trigger payment processing and shipping
- Team wants to add analytics later (possibly in another process)

### 11.2 Context decomposition

| Context | Owns | Reads through API |
|---|---|---|
| Accounts | users, sessions, email_addresses | — |
| Catalog | products, variants, categories, inventory | — |
| Orders | orders, order_items, shipping_addresses | Accounts (user_id), Catalog (product_id) |
| Billing | payment_attempts, invoices, refunds | Orders (order_id) |
| Shipping | shipments, tracking_events | Orders (order_id) |
| Analytics | (reads only; owns no source data) | Everything via events/PubSub |

### 11.3 Aggregate boundaries

| Aggregate | Root | Children | Rationale |
|---|---|---|---|
| User | User | EmailAddresses, Sessions | Auth atomic |
| Product | Product | Variants, Prices, Inventory | Stock + price coherent per product |
| Order | Order | OrderItems, ShippingAddress | Items + total + shipping atomic |
| PaymentAttempt | PaymentAttempt | — | One attempt per row |
| Shipment | Shipment | TrackingEvents | Shipment coherent with its events |

### 11.4 Cross-context flows

**Order placement saga:**

```elixir
defmodule MyApp.OrderPlacement do
  def place(user_id, items) do
    with {:ok, user} <- Accounts.get_user(user_id),
         {:ok, reservation} <- Catalog.reserve_stock(items),
         {:ok, order} <- Orders.create(user_id, items, reservation.id) do
      # Async: payment, shipping initiation
      Oban.insert(Workers.ProcessPayment.new(%{order_id: order.id}))
      {:ok, order}
    else
      {:error, _} = err ->
        # Saga handles compensation
        err
    end
  end
end
```

**Event-driven flow after order:**

```
OrderPlaced (Orders)
  → Payments subscribes → captures payment
  → Shipping subscribes → creates shipment when payment succeeds
  → Analytics subscribes → records metric
```

### 11.5 Multi-tenancy

Row-level with `tenant_id` on every table. Enforced in `MyApp.Repo.prepare_query`. Tenant set via plug at request boundary.

### 11.6 Idempotency plan

| Operation | Idempotency mechanism |
|---|---|
| `Catalog.reserve_stock` | Unique constraint on `(order_id, reservation_key)` |
| `Billing.charge` | External idempotency_key = `order-#{order_id}-#{attempt}` |
| `Shipping.create_shipment` | Unique on `order_id` (one shipment per order) |
| Oban workers | `unique: [period: 300, keys: [:order_id]]` |

### 11.7 Consistency requirements

| Data | Consistency |
|---|---|
| User + sessions | Strong (same aggregate) |
| Order + items | Strong (same aggregate) |
| Order → payment | Eventual (async) |
| Order → shipping | Eventual (async) |
| Order → analytics | Eventual (async) |

This is sufficient for planning the data layer. Implementation follows.

---

## 12. Cross-references

### Within this skill

- `SKILL.md §7` — data ownership overview and decision tables
- [architecture-patterns.md](architecture-patterns.md) §6–7 — event-driven + CQRS context ownership
- [integration-patterns.md](integration-patterns.md) §6, §8 — Oban for idempotent retries; sagas and process managers
- [process-topology.md](process-topology.md) — supervision for multi-tenancy

### In other skills

- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §10.4 — context-level query patterns, preload
- [../elixir-reviewing/SKILL.md](../elixir-reviewing/SKILL.md) §7.1 — reviewing data ownership violations
- `event-sourcing` skill — Commanded aggregates, projections, process managers
- `../elixir/ecto-reference.md` — Ecto changeset/query reference
- `../elixir/ecto-examples.md` — Multi-tenancy, preloading, Multi examples

---

**End of data-ownership-deep.md.** For architectural style selection, see [architecture-patterns.md](architecture-patterns.md). For cross-context communication mechanisms, see [integration-patterns.md](integration-patterns.md).
