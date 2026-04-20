# Integration Patterns — deep reference

Phase-focused deep reference for how contexts (and services) communicate with each other and with external systems. Expands `SKILL.md §9` with the six inter-context mechanisms in depth, capacity planning, failure modes, and migration paths.

**When to load:** when designing how two contexts will talk to each other, when picking between PubSub/GenStage/Oban/event sourcing, when an existing mechanism is failing (mailbox buildup, event loss, throughput ceiling), or when integrating with external systems.

**Related:**
- `SKILL.md §9` — the six mechanisms summary + decision guide
- [architecture-patterns.md](architecture-patterns.md) — how integration patterns fit into architectural styles
- [process-topology.md](process-topology.md) — where each mechanism's processes live in the supervision tree
- [otp-design.md](otp-design.md) — the underlying OTP primitives
- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9 — implementation code for GenStage, Oban, etc.

---

## 1. Rules for picking an integration pattern (LLM)

1. **ALWAYS start with direct function calls.** Escalate to async only when a concrete justification exists.
2. **ALWAYS name the problem before picking the mechanism.** PubSub vs GenStage vs Oban solves *different* problems — if you don't know which you have, stop.
3. **NEVER use PubSub for data that must not be lost.** PubSub drops events when subscribers are down or overwhelmed.
4. **NEVER use GenStage for UI fan-out.** LiveView updates are fast consumers with low volume — PubSub is fine.
5. **ALWAYS use Broadway over raw GenStage** when consuming from an external message broker (Kafka, SQS, RabbitMQ).
6. **ALWAYS use Oban for async work that must survive restarts** — emails, webhooks, billing. In-memory tasks are not acceptable.
7. **ALWAYS make retryable operations idempotent.** Oban workers, webhook handlers, and event handlers may execute multiple times.
8. **NEVER adopt event sourcing to "get loose coupling."** It's a major commitment with operational overhead. Use it for audit/replay requirements.
9. **PREFER escalation over pre-selection.** Direct call → PubSub → GenStage → Oban → Event sourcing. Each escalation adds complexity.
10. **ALWAYS plan for the error path.** What happens if the call times out, the subscriber is down, the queue is full, the external broker is unreachable? The design must answer.

---

## 2. Pattern 1: Direct function calls (the default)

The simplest mechanism. Context A calls Context B's public API.

### 2.1 Shape

```elixir
defmodule MyApp.ShoppingCart do
  alias MyApp.Catalog

  def add_item(cart, product_id) do
    product = Catalog.get_product!(product_id)   # Through public API
    # ...
  end
end
```

### 2.2 Properties

| Property | Value |
|---|---|
| Persistence | None |
| Backpressure | N/A (synchronous) |
| Cross-node | No |
| Delivery | Exactly once (return value or exception) |
| Failure mode | Caller blocks; caller sees exception |
| Complexity | Trivial |

### 2.3 When to use

**Almost always, for cross-context calls that need a result synchronously.**

- The caller needs the return value immediately
- The operation is fast enough to block on
- Loss is not acceptable — the call must succeed or fail visibly
- You don't need decoupling beyond context boundaries

### 2.4 When NOT to use

- The callee is slow (>100ms) and the caller is latency-sensitive
- The call is fire-and-forget — caller doesn't need the result
- The callee can be down while the caller continues

### 2.5 Cross-context data — reference, don't preload

Foreign keys at the schema level are fine. Preloading across context boundaries is not.

```elixir
# BAD — preloading :orders from the Accounts context
defmodule MyApp.Accounts do
  def get_user_with_orders(id), do: User |> preload(:orders) |> Repo.get(id)
end

# GOOD — expose a domain operation
defmodule MyApp.Orders do
  def list_recent_for_user(user_id), do: ...
end
```

---

## 3. Pattern 2: PubSub (fire-and-forget events)

Decoupled async communication. Publisher doesn't know subscribers.

### 3.1 Two options

**`Phoenix.PubSub`** (if Phoenix is a dep):
```elixir
Phoenix.PubSub.subscribe(MyApp.PubSub, "orders")
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:order_completed, order})
```

**`:pg`** (built-in Erlang, OTP 23+, no deps):
```elixir
:pg.join(:my_scope, "orders", self())
for pid <- :pg.get_members(:my_scope, "orders") do
  send(pid, {:order_completed, order})
end
```

**Choose Phoenix.PubSub** if Phoenix is already a dep; **choose `:pg`** for library / non-Phoenix apps.

### 3.2 Properties

| Property | Value |
|---|---|
| Persistence | **None** — subscribers down when event fires miss it forever |
| Backpressure | **None** — fast publisher overwhelms slow subscriber; mailbox grows unbounded |
| Cross-node | Yes (both Phoenix.PubSub and `:pg`) |
| Delivery | At-most-once; no confirmation; no ordering across nodes |
| Failure mode | Silent loss; subscriber mailbox accumulation |
| Complexity | Low |

### 3.3 When to use

- **UI updates** (LiveView broadcasting to connected clients)
- **Notifications** where occasional loss is acceptable
- **Decoupling contexts** when the subscriber can tolerate missed events
- **In-process event fan-out** with a small number of subscribers

### 3.4 When NOT to use

- **Data must not be lost** — use Oban
- **Producer can be faster than consumer** — use GenStage
- **Need ordered delivery across nodes** — PubSub doesn't guarantee this
- **Need confirmation of delivery** — PubSub doesn't provide it

### 3.5 Shape — Event Notification vs Event-Carried State Transfer

These are two distinct PubSub patterns covered in [architecture-patterns.md](architecture-patterns.md) §6.

**Event Notification** (minimal payload):
```elixir
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:order_completed, order_id})

# Subscriber calls back for data
def handle_info({:order_completed, order_id}, state) do
  order = MyApp.Orders.get_order!(order_id)   # N+1 risk if many subscribers
  send_confirmation(order)
  {:noreply, state}
end
```

**Event-Carried State Transfer** (full payload):
```elixir
event = %{
  order_id: order.id,
  customer_email: order.customer.email,
  items: Enum.map(order.items, &serialize_item/1),
  total: order.total
}
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:order_completed, event})

# No callback needed
def handle_info({:order_completed, event}, state) do
  send_confirmation(event.customer_email, event)
  {:noreply, state}
end
```

**Choose Event Notification when:** callback is cheap; few subscribers; data is read-mostly.

**Choose Event-Carried State Transfer when:** many subscribers; callback cost multiplies; decoupling from source is a priority.

### 3.6 Subscriber design

Subscribers are GenServers. Subscribe in `init/1`; handle events in `handle_info/2`.

```elixir
defmodule MyApp.Notifications.OrderListener do
  use GenServer

  def start_link(_), do: GenServer.start_link(__MODULE__, :ok, name: __MODULE__)

  @impl true
  def init(:ok) do
    Phoenix.PubSub.subscribe(MyApp.PubSub, "orders")
    {:ok, %{}}
  end

  @impl true
  def handle_info({:order_completed, order_or_event}, state) do
    # Idempotent: handle the case where we receive the same event twice
    send_confirmation(order_or_event)
    {:noreply, state}
  end
end
```

**Rules:**
- Subscribe in `init/1`, not post-startup (missing events otherwise)
- Handle unknown messages with a catch-all (future event types won't crash you)
- Make handling idempotent (for retry safety, though PubSub doesn't retry)
- Keep handlers fast — slow handler → mailbox buildup → crash

### 3.7 Common PubSub mistakes

**Mistake 1: Using PubSub when you need persistence.**

```
User registers → PubSub.broadcast(:user_registered) → Mailer subscriber
```

If the Mailer subscriber is down or restarting, the welcome email is never sent. **Use Oban for "this must happen."**

**Mistake 2: Large payload PubSub + many nodes.**

Cross-node PubSub copies the message to every subscribed node. A 1MB event × 10 nodes × 100 broadcasts/sec = 1 GB/sec network load. Cap payload size; use Event Notification (id only) for cross-node events.

**Mistake 3: Subscriber that can't keep up.**

Mailbox grows indefinitely. Eventually OOM. Either:
- Make the handler faster (offload to Task / Oban)
- Switch to GenStage (backpressure)
- Drop messages explicitly (selective receive, keep only recent)

---

## 4. Pattern 3: Registry for per-entity subscriptions

When PubSub topics are too coarse, use `Registry` with `:duplicate` keys for per-entity dispatch.

### 4.1 Shape

```elixir
# Subscribe to specific entity events
Registry.register(MyApp.EventRegistry, {:order, order_id}, [])

# Broadcast only to subscribers of a specific entity
Registry.dispatch(MyApp.EventRegistry, {:order, order_id}, fn entries ->
  for {pid, _} <- entries, do: send(pid, {:order_updated, order})
end)

# Supervision tree — Registry with duplicate keys
children = [
  {Registry, keys: :duplicate, name: MyApp.EventRegistry},
  # ...
]
```

### 4.2 When to use

- **Per-entity subscriptions** (LiveView watching one specific order, user, device)
- **Scale with many entities** (100K orders, each with few subscribers)
- **More efficient than broad PubSub** — only dispatches to subscribers of the specific entity

### 4.3 Limitations

- **Single-node only.** Cross-node needs `:pg` or Phoenix.PubSub.
- **No persistence.** Subscriber crash → need to re-register.
- **No backpressure.** Slow subscriber can still accumulate mailbox.

### 4.4 Combined with PubSub

Often you want both: Phoenix.PubSub for broadcast, Registry for per-entity.

```elixir
# LiveView subscribes to BOTH
@impl true
def mount(%{"id" => id}, _session, socket) do
  Phoenix.PubSub.subscribe(MyApp.PubSub, "orders")              # Broadcast events
  Registry.register(MyApp.OrderRegistry, {:order, id}, [])      # Per-order events
  # ...
end
```

---

## 5. Pattern 4: GenStage / Broadway (backpressure pipelines)

When **producer rate can exceed consumer throughput**, PubSub and plain messaging don't work — mailboxes grow unbounded. **GenStage inverts control**: consumers request N items when ready; producers emit only that many.

### 5.1 The demand-driven model

```
Producer ──(buffers events)──> Consumer (requests N via demand)
         <──(emits N items)──
```

- Producer holds a buffer
- Consumer has `max_demand` — how many events it can hold in flight
- Consumer asks for items when ready
- If consumer is slow, producer's buffer fills; upstream feels backpressure

### 5.2 Shape (raw GenStage)

```elixir
# Producer
defmodule MyApp.OrderProducer do
  use GenStage

  def start_link(_), do: GenStage.start_link(__MODULE__, :ok, name: __MODULE__)

  def init(:ok), do: {:producer, %{queue: :queue.new(), demand: 0}}

  def notify(event), do: GenStage.cast(__MODULE__, {:notify, event})

  def handle_cast({:notify, event}, state) do
    dispatch_events(%{state | queue: :queue.in(event, state.queue)}, [])
  end

  def handle_demand(demand, state), do: dispatch_events(%{state | demand: state.demand + demand}, [])

  defp dispatch_events(state, events) do
    # ... pop from queue up to demand, emit
  end
end

# Consumer
defmodule MyApp.OrderProcessor do
  use GenStage

  def start_link(_), do: GenStage.start_link(__MODULE__, :ok)
  def init(:ok), do: {:consumer, :ok, subscribe_to: [{MyApp.OrderProducer, max_demand: 10}]}

  def handle_events(events, _from, state) do
    Enum.each(events, &process_order/1)
    {:noreply, [], state}
  end
end
```

### 5.3 Broadway — declarative wrapper

Broadway wraps GenStage with declarative config, built-in batching, fault tolerance, graceful shutdown, telemetry, and adapters for message brokers.

```elixir
defmodule MyApp.Pipeline do
  use Broadway

  def start_link(_opts) do
    Broadway.start_link(__MODULE__,
      name: __MODULE__,
      producer: [module: {BroadwayKafka.Producer, hosts: [...], topics: ["events"]}],
      processors: [default: [concurrency: 10]],
      batchers: [default: [batch_size: 100, batch_timeout: 1000, concurrency: 5]]
    )
  end

  @impl true
  def handle_message(_processor, message, _context) do
    Message.update_data(message, &process_event/1)
  end

  @impl true
  def handle_batch(_batcher, messages, _batch_info, _context) do
    # Bulk insert to DB
    data = Enum.map(messages, & &1.data)
    MyApp.Repo.insert_all(Event, data)
    messages
  end
end
```

### 5.4 When to use GenStage

- **Producer rate can exceed consumer throughput**
- **Data loss unacceptable** (PubSub drops under load; GenStage backpressures)
- **Multi-stage transformation** (producer → filter → transform → persist)
- **I/O-bound processing** where concurrency control matters
- **Bounded parallelism** (max N items in flight at a time)

### 5.5 When to use Broadway over GenStage

- **Consuming from external message broker** (Kafka, SQS, RabbitMQ, Redis Streams, Google Pub/Sub)
- **Need batching** (accumulate N messages, flush to DB together)
- **Want declarative concurrency config**
- **Need built-in fault tolerance and graceful shutdown**

### 5.6 When NOT to use GenStage

- **Fan-out to UI** (LiveView) — consumers are fast, volume is low → PubSub is fine
- **Occasional loss OK** → PubSub
- **No transformation** — just broadcast and forget → PubSub
- **In-memory only, short-lived** — use Task.async_stream

### 5.7 Broadway vs Oban

Different problems:

| Need | Broadway | Oban |
|---|---|---|
| Consume from Kafka / RabbitMQ | ✅ | Not its job |
| In-process job queue | ❌ | ✅ |
| Persistent (survives restart) | Depends on broker | ✅ (PostgreSQL) |
| Batching to DB | ✅ | ❌ |
| Scheduled / cron jobs | ❌ | ✅ |
| Retries with backoff | Manual | ✅ |

Broadway is for ingesting streams. Oban is for persistent deferred work. Use both together if appropriate.

---

## 6. Pattern 5: Oban (persistent job queue)

Oban is a PostgreSQL-backed job queue. Jobs survive restarts.

### 6.1 Shape

```elixir
# Worker definition
defmodule MyApp.Workers.SendConfirmation do
  use Oban.Worker, queue: :emails, max_attempts: 5

  @impl Oban.Worker
  def perform(%Oban.Job{args: %{"order_id" => order_id}}) do
    order = MyApp.Orders.get_order!(order_id)
    MyApp.Mailer.send_confirmation(order)
    :ok
  end
end

# Enqueue from context
def complete_order(order) do
  with {:ok, order} <- mark_completed(order) do
    %{order_id: order.id}
    |> MyApp.Workers.SendConfirmation.new()
    |> Oban.insert()
    {:ok, order}
  end
end

# Application supervisor
children = [
  MyApp.Repo,
  {Oban, Application.fetch_env!(:my_app, Oban)},
  # ...
]

# config/config.exs
config :my_app, Oban,
  repo: MyApp.Repo,
  queues: [default: 10, emails: 5, payments: 2],
  plugins: [
    {Oban.Plugins.Pruner, max_age: 60 * 60 * 24},
    {Oban.Plugins.Cron, crontab: [{"0 2 * * *", MyApp.Workers.DailyCleanup}]}
  ]
```

### 6.2 When to use

- Jobs must not be lost (email, webhooks, billing, notifications)
- Need retries with backoff
- Need scheduling (run at specific time, cron)
- Need uniqueness (deduplicate identical jobs)
- Need cross-node coordination (shared DB)

### 6.3 When NOT to use

- **One-off in-memory tasks** → `Task.Supervisor.start_child/2`
- **High-volume ephemeral events** → GenStage / Broadway (Oban DB overhead is too much)
- **Synchronous operations that block until result** → direct call

### 6.4 Idempotency is required

Oban jobs can retry. Jobs MUST be idempotent:

```elixir
# BAD — not idempotent; double-charges on retry
def perform(%{args: %{"order_id" => id}}) do
  order = MyApp.Orders.get_order!(id)
  PaymentGateway.charge(order.total, order.token)    # Charges every retry!
end

# GOOD — check state first
def perform(%{args: %{"order_id" => id}}) do
  order = MyApp.Orders.get_order!(id)
  case order.payment_status do
    :charged -> :ok
    :pending ->
      with {:ok, result} <- PaymentGateway.charge(order.total, order.token) do
        MyApp.Orders.mark_charged(order, result.transaction_id)
      end
  end
end

# Alternative: idempotency via Oban unique constraints
%{order_id: order.id}
|> ChargeWorker.new(unique: [period: 300, keys: [:order_id]])
|> Oban.insert()
```

### 6.5 Queue design

Separate queues by concern. Jobs in one queue don't block another.

```elixir
queues: [
  default: 10,         # Background maintenance, low priority
  emails: 5,           # Transactional email — moderate throughput
  payments: 2,         # Payment operations — low concurrency, careful
  webhooks: 20,        # High-volume inbound webhook processing
  analytics: 3,        # Batch analytics — low priority
  search_index: 5      # Search index updates
]
```

**Concurrency per queue** limits parallelism. Tune based on:
- Downstream rate limits (e.g., email provider limits)
- DB load (heavy jobs shouldn't overwhelm the DB)
- External API limits

### 6.6 Oban Pro features

Oban Pro adds:
- **Workflow** (DAG of jobs with dependencies)
- **Batch** (group jobs; react when all complete)
- **Reliable scheduling**
- **Rate limiting per queue**
- **Global uniqueness across clusters**

Consider Pro for: complex multi-step workflows, batch notification, rate-limited external APIs.

---

## 7. Pattern 6: Event Sourcing (Commanded)

**Events are the source of truth.** Current state is derived by replaying events.

### 7.1 When it fits

- Perfect audit trail is a business / regulatory requirement
- Complex long-lived processes (insurance claims, loan origination, order fulfillment with many steps)
- Undo / replay capabilities needed
- Multiple very different read projections of the same data
- Compliance / compliance audit requirements

### 7.2 When it doesn't

- Standard CRUD apps
- Small data sets where audit is a "nice to have"
- Teams without event-sourcing experience (significant learning curve)
- Contexts where event versioning would be painful (rapidly evolving domain)

### 7.3 Cost

Event sourcing has real operational cost:

- **Complexity** — commands, aggregates, events, projections, process managers — all new abstractions
- **Event schema evolution** — old events must still replay correctly; either upcast old events or version them
- **Storage growth** — event log is append-only; grows indefinitely without snapshots
- **Eventual consistency** — projections lag behind events
- **Debugging** — event replay to reproduce a bug is more involved than querying a row

### 7.4 Per-context adoption

**Don't event-source everything.** Most apps should event-source only the contexts that need it:

- **Orders** — audit, replay, process managers → event source
- **Billing** — audit, regulatory → event source
- **Accounts** — standard CRUD → standard Ecto
- **Catalog** — standard CRUD → standard Ecto
- **Settings** — standard CRUD → standard Ecto

**The boundary module (context) hides the choice.** Callers don't know or care.

### 7.5 Implementation

Full depth: `event-sourcing` skill (Commanded library).

Brief overview:

```elixir
# Command
%PlaceOrder{customer_id: 42, items: [...]}

# Aggregate (pure function)
def execute(%Order{status: :new}, %PlaceOrder{...} = cmd) do
  %OrderPlaced{order_id: generate_id(), customer_id: cmd.customer_id, items: cmd.items, placed_at: DateTime.utc_now()}
end

# State is derived by applying events
def apply(%Order{} = order, %OrderPlaced{} = event) do
  %{order | id: event.order_id, items: event.items, status: :placed}
end

# Projection builds read model from event stream
project(%OrderPlaced{} = event, fn multi ->
  Ecto.Multi.insert(multi, :listing, %OrderListingEntry{...})
end)

# Process manager coordinates multi-aggregate workflows
def interested?(%OrderPlaced{} = event), do: {:start, event.order_id}
def handle(%OrderFulfillment{} = pm, %OrderPlaced{} = event), do: [%ReserveStock{...}]
```

---

## 8. Sagas and process managers

For multi-step workflows that must complete or compensate.

### 8.1 Explicit saga (Elixir pattern)

A function that calls context operations in sequence with explicit rollback on failure.

```elixir
defmodule MyApp.OrderSaga do
  def place_order(user_id, items) do
    with {:ok, reservation} <- Catalog.reserve_stock(items),
         {:ok, payment} <- Billing.charge(user_id, total(items)),
         {:ok, order} <- Orders.create(user_id, items, payment.id) do
      {:ok, order}
    else
      {:error, :payment_failed} ->
        Catalog.release_stock(reservation)   # Compensating action
        {:error, :payment_failed}

      {:error, :out_of_stock} ->
        {:error, :out_of_stock}

      {:error, :order_failed} ->
        Catalog.release_stock(reservation)
        Billing.refund(payment.id)
        {:error, :order_failed}
    end
  end
end
```

**Use when:** workflow is bounded (few steps, fast completion). Whole flow visible in one function.

### 8.2 Process manager (Commanded)

Long-lived process that listens for events and emits commands in response.

```elixir
defmodule MyApp.OrderFulfillmentProcess do
  use Commanded.ProcessManagers.ProcessManager

  def interested?(%OrderPlaced{order_id: id}), do: {:start, id}
  def interested?(%PaymentCaptured{order_id: id}), do: {:continue, id}
  def interested?(%StockReserved{order_id: id}), do: {:continue, id}
  def interested?(%FulfillmentCompleted{order_id: id}), do: {:stop, id}

  def handle(%{}, %OrderPlaced{} = event) do
    [%CapturePayment{order_id: event.order_id, amount: event.total}]
  end

  def handle(%{payment_captured: true}, %StockReserved{} = event) do
    [%CompleteFulfillment{order_id: event.order_id}]
  end
end
```

**Use when:** workflow is long-lived (minutes/days); driven by events; needs to wait for external completion; timeouts and retries are declarative.

### 8.3 Saga vs process manager

| Need | Saga | Process manager |
|---|---|---|
| Short, in-memory workflow | ✅ | Overkill |
| Synchronous completion | ✅ | Not the model |
| Long-lived (minutes/days) | Awkward | ✅ |
| Event-driven | Awkward | ✅ |
| Requires event sourcing | No | Yes (Commanded) |
| Compensating actions | Manual | Declarative |
| Visibility | One function | Distributed across events |

---

## 9. External message broker integration

When consuming events from Kafka, RabbitMQ, SQS, etc., use Broadway.

### 9.1 Broadway with Kafka

```elixir
defmodule MyApp.EventPipeline do
  use Broadway

  def start_link(_opts) do
    Broadway.start_link(__MODULE__,
      name: __MODULE__,
      producer: [
        module: {BroadwayKafka.Producer, [
          hosts: [localhost: 9092],
          group_id: "my-app",
          topics: ["user_events"]
        ]},
        concurrency: 1
      ],
      processors: [default: [concurrency: 20]],
      batchers: [
        default: [batch_size: 100, batch_timeout: 1000, concurrency: 5]
      ]
    )
  end

  @impl true
  def handle_message(_processor, %Broadway.Message{data: data} = message, _context) do
    event = Jason.decode!(data)
    Message.update_data(message, fn _ -> event end)
  end

  @impl true
  def handle_batch(_batcher, messages, _batch_info, _context) do
    events = Enum.map(messages, & &1.data)
    MyApp.EventStore.insert_all(events)
    messages
  end
end
```

### 9.2 Broadway offerings

- **BroadwayKafka** — Kafka consumer
- **BroadwaySQS** — AWS SQS
- **BroadwayRabbitMQ** — RabbitMQ
- **BroadwayCloudPubSub** — Google Cloud Pub/Sub
- **BroadwayRedisStream** — Redis Streams

### 9.3 Broker decision

| Need | Broker |
|---|---|
| Ordered per partition, long retention, log semantics | Kafka |
| Simple work queue, AWS ecosystem | SQS |
| Complex routing, priority, simple setup | RabbitMQ |
| GCP ecosystem | Google Pub/Sub |
| Lightweight, already using Redis | Redis Streams |
| Elixir-only, simple | Oban |
| Just in-process | GenStage |

---

## 10. Cross-service synchronous: HTTP / gRPC

When services must communicate synchronously.

### 10.1 HTTP client choice

- **Req** — modern default; handles retries, JSON, streaming, caching
- **Finch** — low-level connection pool; high-performance
- **Mint** — lower-level HTTP/2 client

For most uses: **Req**. It's built on Finch.

```elixir
defmodule MyApp.Inventory.Client do
  @behaviour MyApp.Inventory

  @impl true
  def check_stock(sku) do
    req = Req.new(base_url: "https://inventory.internal:8080", retry: :transient)
    case Req.get(req, url: "/stock/#{sku}") do
      {:ok, %{status: 200, body: %{"available" => n}}} -> {:ok, n}
      {:ok, %{status: 404}} -> {:error, :not_found}
      {:error, _reason} = err -> err
    end
  end
end
```

### 10.2 Hexagonal — behaviour + adapter

Wrap HTTP calls in a behaviour so:
- Domain doesn't know about HTTP
- Tests can mock via Mox
- Implementation can change (HTTP, gRPC, in-process) without domain changes

```elixir
defmodule MyApp.Inventory do
  @callback check_stock(sku :: String.t()) :: {:ok, non_neg_integer()} | {:error, term()}
end
```

See [architecture-patterns.md](architecture-patterns.md) §4 for the full hexagonal pattern.

### 10.3 Resilience for cross-service calls

Every cross-service call needs:

- **Timeout** — never unbounded wait
- **Retries** — for transient failures (HTTP 5xx, connection reset)
- **Circuit breaker** — stop calling when the service is down
- **Fallback** — graceful degradation when possible

See [SKILL.md §11 Resilience Planning](SKILL.md#11-resilience-planning) for how these fit together.

### 10.4 gRPC

Elixir gRPC support: `grpc` library. Works well for service-to-service communication in polyglot environments.

**When to prefer gRPC over HTTP/JSON:**
- Cross-language service mesh (other services are Go/Java/Python)
- Strongly-typed contracts important
- Streaming RPCs needed
- Performance-critical inter-service calls

**Otherwise HTTP+JSON is simpler and often adequate.**

---

## 11. Cross-Elixir nodes: `:erpc` and `:pg`

For Elixir-to-Elixir within a trusted network.

### 11.1 `:erpc`

Synchronous call to remote node (OTP 23+). Preferred over `:rpc` (better error handling).

```elixir
case :erpc.call(:"worker@host", MyApp.Heavy, :compute, [data], 30_000) do
  result -> {:ok, result}
rescue
  e -> {:error, e}
end
```

### 11.2 `:pg` — distributed process groups

OTP-built-in distributed PubSub-like mechanism:

```elixir
# Join a group on any node
:pg.join(:my_scope, :workers, self())

# Send to all members (including remote nodes)
for pid <- :pg.get_members(:my_scope, :workers) do
  send(pid, {:work, data})
end
```

Phoenix.PubSub uses `:pg` under the hood for cross-node broadcast.

### 11.3 When to use

- Elixir cluster with trusted network
- Already using distribution for other purposes (clustered deploy)
- Elixir-to-Elixir only (for polyglot, use HTTP/gRPC)

See `erpc` skill for deeper distributed patterns.

---

## 12. Communication decision tree

```
Need to decouple contexts?

├── No (sync call needed, need return value)
│   └── Direct function call. STOP.
│
├── Yes, and:
│   ├── Fire-and-forget, loss OK
│   │   └── Phoenix.PubSub or :pg (Event Notification or Event-Carried State Transfer)
│   │
│   ├── Per-entity subscriptions
│   │   └── Registry :duplicate
│   │
│   ├── Producer faster than consumer, data loss unacceptable
│   │   ├── In-process: GenStage
│   │   └── External broker: Broadway
│   │
│   ├── Events must survive restart, guaranteed delivery
│   │   └── Oban
│   │
│   ├── Multi-step workflow with compensation
│   │   ├── Short & synchronous: explicit saga
│   │   └── Long-lived & event-driven: process manager (requires event sourcing)
│   │
│   ├── Events ARE the source of truth (audit, replay)
│   │   └── Event sourcing (Commanded)
│   │
│   └── Cross-service (different languages / compliance)
│       ├── Trusted network, Elixir-only: :erpc / :pg
│       ├── Polyglot / public: HTTP (Req) + behaviour
│       └── Polyglot + strongly typed: gRPC
```

---

## 13. Escalation path — when to move up

Start simple. Escalate only when the current mechanism fails.

```
Direct function call
  ↓ (need async or decoupling)
PubSub
  ↓ (mailbox growing? fast producer / slow consumer?)
GenStage / Broadway
  ↓ (events lost on deploy / crash?)
Oban
  ↓ ("what happened and when?" / replay / compliance?)
Event sourcing (Commanded)
```

**Signals to escalate:**

| Symptom | Upgrade |
|---|---|
| Subscriber mailbox growing | → GenStage (backpressure) |
| Events lost during restart | → Oban (persistence) |
| Need to batch writes | → Broadway (batching) |
| "What happened and when?" | → Event sourcing |

**Do NOT skip steps.** Each escalation adds complexity. Only take the next step if the current mechanism demonstrably fails.

---

## 14. Capacity planning

### 14.1 PubSub

- **Throughput**: limited by subscriber processing speed × mailbox capacity
- **Typical**: 10K-100K events/sec in-process; ~5-10K/sec cross-node due to serialization
- **Failure mode**: slow subscriber → unbounded mailbox → OOM

**Plan for:**
- Upper bound on publish rate
- Subscriber handling time
- Mailbox capacity (kill threshold)

### 14.2 GenStage / Broadway

- **Throughput**: bounded by slowest stage × concurrency
- **Typical**: 10K-1M events/sec depending on stage complexity and batching
- **Failure mode**: upstream buffer fills; producer blocks

**Plan for:**
- Batch size (tradeoff: latency vs throughput)
- Concurrency per stage
- Max in-flight events
- Backpressure to source

### 14.3 Oban

- **Throughput**: bounded by DB write rate × concurrency
- **Typical**: 100-10K jobs/sec per queue
- **Failure mode**: DB can't keep up → queue backlog

**Plan for:**
- Queue-by-queue concurrency
- DB load under max concurrency
- Pruning strategy (old jobs accumulate)
- Monitoring: queue depth, execution time, retry rate

### 14.4 Event sourcing

- **Throughput**: bounded by event store write rate; projection update rate
- **Typical**: 1K-50K events/sec write; projections lag by seconds to minutes
- **Failure mode**: slow projection → stale reads; storage growth

**Plan for:**
- Event store scaling (partition if needed)
- Snapshot frequency (to avoid full replay on aggregate load)
- Projection rebuild time (after schema changes)
- Storage growth (events are append-only)

---

## 15. Common integration mistakes

### 15.1 PubSub for things that must not be lost

```elixir
# BAD — Phoenix.PubSub for guaranteed delivery
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:send_receipt, order})
# If Mailer subscriber is down, receipt is never sent.

# GOOD — Oban for guaranteed delivery
%{order_id: order.id}
|> MyApp.Workers.SendReceipt.new()
|> Oban.insert()
```

### 15.2 PubSub with unbounded mailbox

```elixir
# BAD — slow handler → mailbox grows forever
def handle_info({:event, data}, state) do
  slow_operation(data)  # Takes 500ms
  {:noreply, state}
end
# Under load (100 events/sec), mailbox grows by ~50 events/sec → OOM in minutes

# GOOD — offload, keep handler fast
def handle_info({:event, data}, state) do
  Task.Supervisor.start_child(MyApp.TaskSupervisor, fn -> slow_operation(data) end)
  {:noreply, state}
end

# BETTER — if producer rate is real, use GenStage
```

### 15.3 GenStage for UI broadcast

```elixir
# BAD — GenStage for LiveView updates
# You don't need backpressure; consumers are fast.
# Just use Phoenix.PubSub.
```

### 15.4 Oban for synchronous-required work

```elixir
# BAD — Oban for "I need the result now"
def create_order(user_id, items) do
  job = %{user_id: user_id, items: items} |> CreateOrderWorker.new() |> Oban.insert()
  wait_for_job(job)   # Polling for async job = wrong pattern
end

# GOOD — direct call for synchronous work
def create_order(user_id, items), do: MyApp.Orders.create(user_id, items)
```

### 15.5 Non-idempotent Oban workers

```elixir
# BAD — sends email every retry
def perform(%{args: %{"order_id" => id}}) do
  order = MyApp.Orders.get_order!(id)
  MyApp.Mailer.send_confirmation(order)
end

# GOOD — check state; skip if already sent
def perform(%{args: %{"order_id" => id}}) do
  order = MyApp.Orders.get_order!(id)
  if order.confirmation_sent_at do
    :ok
  else
    with :ok <- MyApp.Mailer.send_confirmation(order) do
      MyApp.Orders.mark_confirmation_sent(order)
    end
  end
end
```

### 15.6 Cross-context Repo access pretending to be integration

```elixir
# BAD — one context reaching into another's data
defmodule MyApp.Billing do
  alias MyApp.Orders.Order     # Internal module of Orders context!
  def get_order(id), do: Repo.get(Order, id)
end

# GOOD — through Orders' public API
defmodule MyApp.Billing do
  def get_order(id), do: MyApp.Orders.get_order(id)
end
```

### 15.7 Saga without idempotency

Sagas with compensating actions must also be idempotent — you may get interrupted mid-compensation and need to retry.

```elixir
# BAD — if compensation interrupts, stock may be over-released
with {:ok, reservation} <- Catalog.reserve_stock(items) do
  case Billing.charge(user_id, total(items)) do
    {:ok, _} -> # ...
    {:error, _} ->
      Catalog.release_stock(reservation)  # What if this is retried?
  end
end

# GOOD — compensation is idempotent
def release_stock(reservation_id) do
  case get_reservation(reservation_id) do
    %{status: :released} -> :ok         # Already released
    %{status: :held} -> do_release(...)
    nil -> {:error, :not_found}
  end
end
```

---

## 16. Cross-references

### Within this skill

- `SKILL.md §9` — integration mechanisms summary and decision guide
- `SKILL.md §11` — resilience for integration boundaries
- [architecture-patterns.md](architecture-patterns.md) §6 (event-driven), §7 (CQRS) — how integration supports styles
- [process-topology.md](process-topology.md) — where integration processes live in supervision
- [otp-design.md](otp-design.md) — the underlying OTP primitives

### In other skills

- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9 — implementation code for Oban, GenStage, PubSub
- [../elixir-reviewing/SKILL.md](../elixir-reviewing/SKILL.md) §7.6, §8.3 — review and debug integration patterns
- `event-sourcing` skill — Commanded deep dive
- `state-machine` skill — process managers implementation
- `erpc` skill — distributed Elixir communication
- `../elixir/otp-advanced.md` — GenStage / Flow / Broadway reference

---

**End of integration-patterns.md.** For architectural style selection, see [architecture-patterns.md](architecture-patterns.md). For supervision of integration processes, see [process-topology.md](process-topology.md).
