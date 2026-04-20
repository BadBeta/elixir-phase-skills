# OTP Callbacks — Implementation Templates

Phase-focused on **writing** OTP callback code. Covers the HOW: callback signatures, return tuples, mailbox patterns, process-naming syntax, supervision child-specs, common templates.

**For the WHICH (which construct do I choose?) and the WHY (how does this fit the architecture?),** see `../elixir-planning/otp-design.md` and `../elixir-planning/process-topology.md`.

---

## Rules for Writing OTP Callbacks

1. **ALWAYS use `@impl true`** on every callback. Catches typos and missing callbacks at compile time.
2. **ALWAYS keep callbacks thin** — delegate to pure functions in a separate `State` module for computation; callbacks only handle process mechanics.
3. **NEVER block in `init/1`** — use `{:ok, state, {:continue, :load}}` to defer heavy work until after the caller unblocks.
4. **NEVER call `self()` from another process to target this one** — use `name` or `via: {Registry, ...}` registration.
5. **ALWAYS return `{:stop, reason, state}` for fatal errors** in callbacks — let the supervisor restart. Don't swallow errors.
6. **NEVER use `GenServer.call` with default timeout in hot paths** — pass an explicit timeout sized to the SLO, or design with `handle_continue`/`cast` to avoid blocking.
7. **ALWAYS handle `handle_info/2` catch-all** `def handle_info(_msg, state), do: {:noreply, state}` to swallow stray messages; without it, unexpected messages crash the process.
8. **ALWAYS use `handle_continue/2` for post-init work**, not `Process.send_after(self(), :init, 0)`.
9. **NEVER rely on `terminate/2`** being called — it runs only on `{:stop, reason, state}` and normal shutdown, not on link-propagated exits. Use `Process.flag(:trap_exit, true)` if you need cleanup, or handle state externally (ETS/disk).
10. **ALWAYS register long-lived named processes under a `@name` module attribute** and a `start_link(opts)` that accepts `name: @name` — enables multi-instance via `PartitionSupervisor` without code changes.

---

## Return-Tuple Decision Guide

### `init/1` returns

| When you need to... | Return |
|---|---|
| Start synchronously, ready immediately | `{:ok, state}` |
| Defer heavy init (load from disk, DB, network) | `{:ok, state, {:continue, :load}}` |
| Send self-`:timeout` info after N ms | `{:ok, state, timeout_ms}` |
| Start idle to minimize memory | `{:ok, state, :hibernate}` |
| Start conditionally fails (config missing) | `{:stop, reason}` |
| Start but don't register (e.g., already running) | `:ignore` |

### `handle_call/3` returns

| When you need to... | Return |
|---|---|
| Reply now and continue | `{:reply, reply, state}` |
| Reply now, then do more work | `{:reply, reply, state, {:continue, term}}` |
| Defer reply (e.g., async work) — call `GenServer.reply(from, reply)` later | `{:noreply, state}` |
| Reply then stop | `{:stop, reason, reply, state}` |
| Stop without reply (caller will get `:exit`) | `{:stop, reason, state}` |

### `handle_cast/2` and `handle_info/2` returns

| When you need to... | Return |
|---|---|
| Continue | `{:noreply, state}` |
| Continue with follow-up | `{:noreply, state, {:continue, term}}` |
| Hibernate | `{:noreply, state, :hibernate}` |
| Stop normally (supervisor :transient won't restart on `:normal`) | `{:stop, :normal, state}` |
| Stop with error (supervisor will restart per strategy) | `{:stop, reason, state}` |

---

## GenServer — Minimal Template

```elixir
defmodule MyApp.Worker do
  use GenServer

  # ── Client API ────────────────────────────────────────────────

  def start_link(opts) do
    name = Keyword.get(opts, :name, __MODULE__)
    GenServer.start_link(__MODULE__, opts, name: name)
  end

  def get(server \\ __MODULE__, key), do: GenServer.call(server, {:get, key})
  def put(server \\ __MODULE__, key, value), do: GenServer.cast(server, {:put, key, value})

  # ── Server callbacks ──────────────────────────────────────────

  @impl true
  def init(opts) do
    state = %{table: :ets.new(__MODULE__, [:set, :protected]), opts: opts}
    {:ok, state, {:continue, :warm_cache}}
  end

  @impl true
  def handle_continue(:warm_cache, state) do
    # Heavy work here — runs after init returns, caller is unblocked
    {:noreply, state}
  end

  @impl true
  def handle_call({:get, key}, _from, state) do
    reply =
      case :ets.lookup(state.table, key) do
        [{^key, value}] -> {:ok, value}
        [] -> {:error, :not_found}
      end
    {:reply, reply, state}
  end

  @impl true
  def handle_cast({:put, key, value}, state) do
    :ets.insert(state.table, {key, value})
    {:noreply, state}
  end

  @impl true
  def handle_info(_msg, state), do: {:noreply, state}
end
```

**Notes:**
- `start_link/1` accepts `:name` — defaults to `__MODULE__`, enables test isolation via `name: :"#{__MODULE__}_#{:erlang.unique_integer()}"`.
- `:protected` ETS is owned by this process. Reads from others are OK; only the owner writes.
- `handle_continue/2` avoids blocking the supervisor during boot.
- Catch-all `handle_info/2` prevents crashes from stray messages (e.g., DOWN messages from an old monitor).

---

## GenServer — Pure Function Split

**Rule:** callbacks handle process mechanics; a `State` module does the work.

```elixir
defmodule MyApp.Counter do
  use GenServer

  # ── State module — pure functions, fully testable ─────────────
  defmodule State do
    defstruct [:count, :limit]

    def new(limit), do: %__MODULE__{count: 0, limit: limit}

    def increment(%__MODULE__{count: n, limit: l} = s) when n < l,
      do: {:ok, %{s | count: n + 1}}
    def increment(%__MODULE__{count: n, limit: l}) when n >= l,
      do: {:error, :limit_reached}

    def value(%__MODULE__{count: n}), do: n
  end

  # ── Client API ─────────────────────────────────────────────────
  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)
  def increment, do: GenServer.call(__MODULE__, :increment)
  def value, do: GenServer.call(__MODULE__, :value)

  # ── Callbacks — thin, delegate to State ───────────────────────
  @impl true
  def init(opts), do: {:ok, State.new(Keyword.fetch!(opts, :limit))}

  @impl true
  def handle_call(:increment, _from, state) do
    case State.increment(state) do
      {:ok, new_state} -> {:reply, :ok, new_state}
      {:error, reason} -> {:reply, {:error, reason}, state}
    end
  end

  def handle_call(:value, _from, state), do: {:reply, State.value(state), state}
end
```

**Why split?** `MyApp.Counter.State` is testable without starting a process. You can `assert State.increment(State.new(5))` directly.

---

## Supervisor Child Specs

### Form 1 — module name (uses `child_spec/1`)

```elixir
children = [
  MyApp.Repo,
  {MyApp.Worker, [limit: 100]},
  {Registry, keys: :unique, name: MyApp.Registry},
  {DynamicSupervisor, strategy: :one_for_one, name: MyApp.DynSup}
]

Supervisor.start_link(children, strategy: :one_for_one, name: MyApp.Supervisor)
```

### Form 2 — explicit `child_spec`

```elixir
children = [
  %{
    id: MyApp.Worker,
    start: {MyApp.Worker, :start_link, [[limit: 100]]},
    restart: :permanent,    # :permanent | :transient | :temporary
    type: :worker,          # :worker | :supervisor
    shutdown: 5_000,        # ms or :brutal_kill | :infinity
    modules: [MyApp.Worker] # hot-upgrade hint
  }
]
```

### `child_spec/1` override in your module

```elixir
defmodule MyApp.Worker do
  use GenServer, restart: :transient, shutdown: 10_000
  # Or override fully:
  def child_spec(opts) do
    %{
      id: Keyword.get(opts, :id, __MODULE__),
      start: {__MODULE__, :start_link, [opts]},
      restart: :transient
    }
  end
end
```

### Restart-strategy decision

| Strategy | When to use |
|---|---|
| `:permanent` | Long-running service that should always be up (default) |
| `:transient` | Worker that may finish naturally; restart only on abnormal exit |
| `:temporary` | One-shot work; never restart (e.g., a Task spawned per job) |

### Supervision-strategy decision

| Strategy | When to use |
|---|---|
| `:one_for_one` | Children are independent (default) |
| `:rest_for_one` | Later children depend on earlier ones; restart them too |
| `:one_for_all` | All children share state; restart them all on any failure |

---

## Task — Templates

### Fire-and-forget supervised task

```elixir
# In supervision tree:
{Task.Supervisor, name: MyApp.TaskSup}

# Anywhere:
Task.Supervisor.start_child(MyApp.TaskSup, fn -> send_email(user) end)
# Or with :restart option:
Task.Supervisor.start_child(MyApp.TaskSup, fn -> ... end, restart: :transient)
```

### Await a single task

```elixir
task = Task.Supervisor.async(MyApp.TaskSup, fn -> expensive() end)
# ... do other work ...
result = Task.await(task, 10_000)
```

**Use `async_nolink` when the caller must survive a task crash:**

```elixir
task = Task.Supervisor.async_nolink(MyApp.TaskSup, fn -> may_crash() end)

case Task.yield(task, 5_000) || Task.shutdown(task, :brutal_kill) do
  {:ok, result} -> result
  {:exit, reason} -> {:error, reason}
  nil -> {:error, :timeout}
end
```

### Parallel work with `async_stream`

```elixir
urls
|> Task.async_stream(&fetch/1,
    max_concurrency: System.schedulers_online() * 2,
    timeout: 30_000,
    on_timeout: :kill_task,
    ordered: false          # Faster if order doesn't matter
  )
|> Enum.reduce([], fn
    {:ok, {:ok, body}}, acc -> [body | acc]
    {:ok, {:error, _}}, acc -> acc
    {:exit, _reason}, acc -> acc
  end)
```

**Side-effects only:** `|> Stream.run()` instead of `|> Enum.reduce/3`.

---

## Agent — Templates

Narrow state holder; avoid for anything beyond pure-value storage.

```elixir
# Start
{:ok, pid} = Agent.start_link(fn -> %{} end, name: MyApp.Config)

# Read — runs in Agent's process
value = Agent.get(MyApp.Config, fn state -> Map.get(state, :key) end)

# Write
Agent.update(MyApp.Config, fn state -> Map.put(state, :key, :value) end)

# Read + write atomically
Agent.get_and_update(MyApp.Config, fn state ->
  {Map.get(state, :counter, 0), Map.update(state, :counter, 1, &(&1 + 1))}
end)
```

**Anti-pattern:** Agent holding complex state with business rules. If your update functions do more than trivial assignment, use GenServer with `State` module.

---

## Registry — via-Tuple Syntax

```elixir
# In supervision tree:
{Registry, keys: :unique, name: MyApp.WorkerRegistry}

# Register at start_link:
def start_link(%{id: id} = opts) do
  GenServer.start_link(__MODULE__, opts, name: via(id))
end

defp via(id), do: {:via, Registry, {MyApp.WorkerRegistry, id}}

# Call by id:
def get_value(id), do: GenServer.call(via(id), :value)

# Dynamic start:
DynamicSupervisor.start_child(MyApp.DynSup, {MyApp.Worker, %{id: "user_42"}})
```

**`:unique` vs `:duplicate`:**
- `:unique` — one process per key (typical for per-entity processes).
- `:duplicate` — many processes per key (pubsub-like fan-out).

### Registry dispatch (pub-sub pattern)

```elixir
# Subscribers register under a topic key (:duplicate registry):
Registry.register(MyApp.PubSub, "user:42", :no_value)

# Publisher:
Registry.dispatch(MyApp.PubSub, "user:42", fn entries ->
  for {pid, _} <- entries, do: send(pid, {:event, payload})
end)
```

For app-wide pub/sub, prefer `Phoenix.PubSub` — this pattern is for local, in-process fan-out.

---

## DynamicSupervisor — Child Start Template

```elixir
# In supervision tree:
{DynamicSupervisor, strategy: :one_for_one, name: MyApp.DynSup}

# Start a child dynamically:
DynamicSupervisor.start_child(MyApp.DynSup, {MyApp.Worker, id: "job_123"})

# Stop a child:
DynamicSupervisor.terminate_child(MyApp.DynSup, pid)

# Count active:
%{active: n} = DynamicSupervisor.count_children(MyApp.DynSup)
```

**Common combo — Registry + DynamicSupervisor:** Start per-entity processes on demand, look them up by entity ID, restart them on crash.

```elixir
defmodule MyApp.Workers do
  def for_user(user_id) do
    case Registry.lookup(MyApp.WorkerRegistry, user_id) do
      [{pid, _}] -> {:ok, pid}
      [] -> DynamicSupervisor.start_child(MyApp.DynSup, {MyApp.Worker, %{id: user_id}})
    end
  end
end
```

---

## `:gen_statem` — Template (when state machine is formal)

Use `:gen_statem` when you have explicit named states with different legal operations per state (TCP connection: `connecting`/`connected`/`closed`; order: `pending`/`paid`/`shipped`).

```elixir
defmodule MyApp.OrderMachine do
  @behaviour :gen_statem

  # ── Client ─────────────────────────────────────────────────────
  def start_link(order_id), do: :gen_statem.start_link(__MODULE__, order_id, [])
  def pay(pid, payment), do: :gen_statem.call(pid, {:pay, payment})
  def ship(pid, tracking), do: :gen_statem.call(pid, {:ship, tracking})

  # ── Init ───────────────────────────────────────────────────────
  @impl true
  def callback_mode, do: :state_functions

  @impl true
  def init(order_id), do: {:ok, :pending, %{id: order_id, payment: nil, tracking: nil}}

  # ── State: :pending ────────────────────────────────────────────
  def pending({:call, from}, {:pay, payment}, data) do
    new_data = %{data | payment: payment}
    {:next_state, :paid, new_data, [{:reply, from, :ok}]}
  end
  def pending({:call, from}, _other, _data) do
    {:keep_state_and_data, [{:reply, from, {:error, :not_yet_paid}}]}
  end

  # ── State: :paid ───────────────────────────────────────────────
  def paid({:call, from}, {:ship, tracking}, data) do
    new_data = %{data | tracking: tracking}
    {:next_state, :shipped, new_data, [{:reply, from, :ok}]}
  end

  def shipped({:call, from}, _event, _data) do
    {:keep_state_and_data, [{:reply, from, {:error, :already_shipped}}]}
  end
end
```

**Callback modes:**
- `:state_functions` — one function per state (template above). Best for few states.
- `:handle_event_function` — single `handle_event/4`. Best for many states or dynamic state names.

See `../elixir-planning/otp-design.md` §on-state-machines for when to pick `:gen_statem` vs `GenServer` with a `:state` field.

---

## ETS — Call Patterns

```elixir
# Create (public, set)
table = :ets.new(:my_table, [:set, :public, read_concurrency: true])

# Named table (refer by atom across processes)
:ets.new(:my_cache, [:named_table, :set, :public, read_concurrency: true])

# Write
:ets.insert(:my_cache, {key, value})
:ets.insert_new(:my_cache, {key, value})  # Atomic check-and-set

# Read
case :ets.lookup(:my_cache, key) do
  [{^key, value}] -> {:ok, value}
  [] -> :error
end

# Atomic counter
:ets.update_counter(:my_counters, :requests, {2, 1}, {:requests, 0})

# Delete
:ets.delete(:my_cache, key)

# Select (match spec)
:ets.select(:my_cache, [{{:"$1", :"$2"}, [{:>, :"$2", 100}], [:"$1"]}])
# → returns all keys where value > 100

# Fold
:ets.foldl(fn {k, v}, acc -> [{k, v} | acc] end, [], :my_cache)
```

### ETS access modes

| Mode | Read | Write |
|---|---|---|
| `:public` | Any process | Any process |
| `:protected` | Any process | Owner only (default) |
| `:private` | Owner only | Owner only |

**Concurrent read:** `read_concurrency: true`.
**Concurrent write:** `write_concurrency: true` — also consider `decentralized_counters: true` for Erlang/OTP 25+.

---

## `:persistent_term` — Configuration Pattern

For read-very-often, write-rarely data (config, compiled regexes, dispatch tables):

```elixir
# Set once at app boot
:persistent_term.put({MyApp, :config}, expensive_load())

# Read cheaply (no message passing, no ETS lookup)
config = :persistent_term.get({MyApp, :config})
```

**Warning:** every `put/2` triggers a global GC scan. NEVER put in a hot write path.

---

## Process Flags & Trapping Exits

```elixir
@impl true
def init(opts) do
  Process.flag(:trap_exit, true)  # Now linked-process exits arrive as :EXIT messages
  {:ok, state}
end

@impl true
def handle_info({:EXIT, _pid, :normal}, state), do: {:noreply, state}
def handle_info({:EXIT, pid, reason}, state) do
  # Handle linked process death
  {:noreply, state}
end
```

When `trap_exit: true`, `terminate/2` is guaranteed to run on supervisor shutdown — use for cleanup (close files, flush buffers).

---

## Monitoring (vs Linking)

Use `Process.monitor/1` when you need to know a process died but don't want its death to kill you:

```elixir
ref = Process.monitor(pid)

# Later:
def handle_info({:DOWN, ^ref, :process, ^pid, reason}, state) do
  {:noreply, %{state | monitored_pid: nil}}
end
```

Demonitor (flush any pending DOWN):

```elixir
Process.demonitor(ref, [:flush])
```

---

## GenStage — Producer / Consumer / Producer-Consumer Templates

GenStage is for back-pressured streaming pipelines. Use when: (a) bounded memory under load, (b) coordinate producer rate with consumer capacity, (c) multiple stages process events in series.

**For when-to-use decision** (GenStage vs Flow vs Broadway vs Task.async_stream vs Oban), see `../elixir-planning/integration-patterns.md`.

### Producer

```elixir
defmodule MyApp.EventProducer do
  use GenStage

  def start_link(opts), do: GenStage.start_link(__MODULE__, opts, name: __MODULE__)

  @impl true
  def init(_opts) do
    # :queue holds buffered events; demand tracks consumer asks
    {:producer, %{queue: :queue.new(), demand: 0}}
  end

  # Consumers ask for N events
  @impl true
  def handle_demand(incoming_demand, %{demand: d} = state) do
    dispatch(%{state | demand: d + incoming_demand})
  end

  # External submission
  def enqueue(event), do: GenStage.cast(__MODULE__, {:enqueue, event})

  @impl true
  def handle_cast({:enqueue, event}, state) do
    dispatch(%{state | queue: :queue.in(event, state.queue)})
  end

  defp dispatch(%{demand: 0} = state), do: {:noreply, [], state}
  defp dispatch(%{queue: q, demand: d} = state) do
    {events, new_q, new_d} = take_events(q, d, [])
    {:noreply, Enum.reverse(events), %{state | queue: new_q, demand: new_d}}
  end

  defp take_events(q, 0, acc), do: {acc, q, 0}
  defp take_events(q, n, acc) do
    case :queue.out(q) do
      {{:value, e}, rest} -> take_events(rest, n - 1, [e | acc])
      {:empty, _} -> {acc, q, n}
    end
  end
end
```

### Consumer

```elixir
defmodule MyApp.EventConsumer do
  use GenStage

  def start_link(opts), do: GenStage.start_link(__MODULE__, opts)

  @impl true
  def init(_opts) do
    {:consumer, %{}, subscribe_to: [{MyApp.EventProducer, max_demand: 100, min_demand: 50}]}
  end

  @impl true
  def handle_events(events, _from, state) do
    Enum.each(events, &process/1)
    {:noreply, [], state}   # consumers emit no events
  end

  defp process(event), do: # ... actual work
end
```

**Key subscription options:**
- `max_demand` — max events per batch (sizes memory per consumer)
- `min_demand` — ask for more only after processing down to this level

### Producer-Consumer (transform stage)

```elixir
defmodule MyApp.EnrichStage do
  use GenStage

  def start_link(opts), do: GenStage.start_link(__MODULE__, opts, name: __MODULE__)

  @impl true
  def init(_opts) do
    {:producer_consumer, %{},
     subscribe_to: [{MyApp.EventProducer, max_demand: 100}]}
  end

  @impl true
  def handle_events(events, _from, state) do
    enriched = Enum.map(events, &enrich/1)
    {:noreply, enriched, state}
  end

  defp enrich(event), do: Map.put(event, :processed_at, DateTime.utc_now())
end
```

### Supervision wiring

```elixir
children = [
  MyApp.EventProducer,
  MyApp.EnrichStage,
  %{
    id: :consumer_pool,
    start: {Supervisor, :start_link, [
      Enum.map(1..5, fn i ->
        Supervisor.child_spec({MyApp.EventConsumer, []}, id: {:consumer, i})
      end),
      [strategy: :one_for_one]
    ]}
  }
]
```

---

## Broadway — Data Ingestion Pipeline Template

Broadway is built on GenStage, specialized for **data ingestion** from message brokers (SQS, RabbitMQ, Kafka, Pub/Sub). Handles batching, retries, partitioning, rate limiting out of the box.

```elixir
defmodule MyApp.OrderPipeline do
  use Broadway

  alias Broadway.Message

  def start_link(_opts) do
    Broadway.start_link(__MODULE__,
      name: __MODULE__,
      producer: [
        module: {BroadwaySQS.Producer, queue_url: "https://sqs.../orders"},
        concurrency: 1
      ],
      processors: [
        default: [concurrency: 10, max_demand: 20]
      ],
      batchers: [
        inserts: [concurrency: 2, batch_size: 100, batch_timeout: 1_000],
        errors: [concurrency: 1, batch_size: 10]
      ]
    )
  end

  # Per-message — fast, parallel
  @impl true
  def handle_message(_, %Message{data: data} = msg, _ctx) do
    case Jason.decode(data) do
      {:ok, order} ->
        msg
        |> Message.update_data(fn _ -> order end)
        |> Message.put_batcher(:inserts)
      {:error, _} ->
        msg |> Message.failed(:invalid_json) |> Message.put_batcher(:errors)
    end
  end

  # Per-batch — bulk inserts, commits
  @impl true
  def handle_batch(:inserts, messages, _batch_info, _ctx) do
    orders = Enum.map(messages, & &1.data)
    {count, _} = MyApp.Repo.insert_all(MyApp.Order, orders, on_conflict: :nothing)
    Logger.info("Inserted #{count}/#{length(orders)} orders")
    messages   # Broadway auto-acks
  end

  def handle_batch(:errors, messages, _batch_info, _ctx) do
    Enum.each(messages, &Logger.warning("Failed: #{inspect(&1.data)}"))
    messages
  end

  # Optional — called on exceptions; decide retry vs final-fail
  @impl true
  def handle_failed(messages, _ctx) do
    Enum.map(messages, fn msg ->
      if msg.metadata.attempt < 3 do
        msg   # Retry
      else
        Message.configure_ack(msg, on_failure: :ack)   # Give up
      end
    end)
  end
end
```

### Broadway options cheat sheet

| Option | Purpose |
|---|---|
| `producer.module` | Source: `BroadwaySQS.Producer`, `BroadwayRabbitMQ.Producer`, `BroadwayKafka.Producer`, `OffBroadway.SQS.Producer` |
| `producer.concurrency` | Parallel producer processes |
| `processors.*.concurrency` | Parallel message handlers |
| `processors.*.max_demand` | Batch pulled per processor |
| `batchers.*.batch_size` | Max messages per batch |
| `batchers.*.batch_timeout` | Emit batch after N ms even if not full |
| `batchers.*.concurrency` | Parallel batch handlers |
| `partition_by` | Shard messages to preserve per-key order |

### Partitioning for ordering

```elixir
# Messages with same user_id always go to same processor
Broadway.start_link(__MODULE__,
  # ...
  processors: [default: [concurrency: 10]],
  partition_by: fn msg ->
    %{user_id: uid} = Jason.decode!(msg.data)
    :erlang.phash2(uid)
  end
)
```

---

## Flow — Parallel Data Transformation Template

`Flow` builds on GenStage for **one-shot parallel processing** of an enumerable — MapReduce for in-process collections.

```elixir
# Count word frequencies in parallel from a large file
File.stream!("big.txt")
|> Flow.from_enumerable(stages: 4, max_demand: 100)
|> Flow.flat_map(&String.split(&1, ~r/\W+/))
|> Flow.partition()                        # shard by hash; same word → same stage
|> Flow.reduce(fn -> %{} end, fn word, acc -> Map.update(acc, word, 1, &(&1 + 1)) end)
|> Flow.on_trigger(& &1)
|> Enum.to_list()
```

### Task.async_stream vs Flow vs Broadway vs GenStage vs Oban

| Need | Use |
|---|---|
| One-shot parallel map over fixed collection | `Task.async_stream` |
| Parallel map-reduce with grouping/partitioning | `Flow` |
| Long-lived pipeline from message broker | `Broadway` |
| Custom streaming pipeline (non-standard source) | `GenStage` directly |
| Scheduled / retryable background jobs | `Oban` |

---

## Rate Limiter — Token Bucket with ETS + :atomics

A production-grade rate limiter uses ETS for per-key state and `:atomics` for lock-free counters. Faster than a GenServer for the hot path (writes don't serialize through a mailbox); a small GenServer handles refill.

```elixir
defmodule MyApp.RateLimit do
  @moduledoc """
  Token bucket rate limiter. Each `key` has a bucket of `burst` tokens
  that refills at `refill_per_sec` per second.
  """
  use GenServer

  @table :my_app_rate_limit

  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)

  @doc """
  Attempts to consume one token for `key`. Returns :ok or {:error, :rate_limited}.
  No message-passing on the hot path — direct ETS ops only.
  """
  def check(key, burst, refill_per_sec) do
    now = System.monotonic_time(:millisecond)

    case :ets.lookup(@table, key) do
      [] ->
        # First use — insert bucket with burst - 1 tokens
        :ets.insert_new(@table, {key, burst - 1, now, burst, refill_per_sec})
        :ok

      [{^key, tokens, last_refill, burst_cfg, rate}] ->
        elapsed_ms = now - last_refill
        refilled = tokens + div(elapsed_ms * rate, 1_000)
        tokens_now = min(burst_cfg, refilled)

        if tokens_now >= 1 do
          # Decrement atomically; race-safe via update_counter
          new_count = :ets.update_counter(@table, key,
            [{2, -1, 0, 0}],       # clamp at 0
            {key, tokens_now, now, burst_cfg, rate}
          )
          if new_count >= 0, do: :ok, else: {:error, :rate_limited}
        else
          {:error, :rate_limited}
        end
    end
  end

  # ── Server ─────────────────────────────────────────────────────

  @impl true
  def init(_opts) do
    :ets.new(@table, [
      :set, :named_table, :public,
      read_concurrency: true, write_concurrency: true,
      decentralized_counters: true
    ])
    {:ok, %{}}
  end

  @impl true
  def handle_info(_msg, state), do: {:noreply, state}
end
```

**Usage:**

```elixir
# Allow 10 requests per second, burst of 30
case MyApp.RateLimit.check("user:42", 30, 10) do
  :ok -> process_request()
  {:error, :rate_limited} -> {:error, :too_many_requests}
end
```

### Variants

| Need | Approach |
|---|---|
| Cluster-wide rate limit | [Hammer](https://hex.pm/packages/hammer) with Mnesia / Redis backend |
| Per-endpoint HTTP rate limit | Plug wrapper around this GenServer + Plug.Conn response |
| Sliding window (not token bucket) | Fixed-size ring buffer in ETS with `:ets.select_count` |
| Simpler single-token ops | `:counters` + periodic reset — drop the refill logic |

Start with this template for single-node; move to Hammer when distribution is needed.

---

## Common Anti-Patterns (BAD / GOOD)

### 1. Blocking `init/1`

```elixir
# BAD — supervisor blocks on boot; cascade-failures
def init(opts) do
  data = load_from_disk()  # Takes 30s
  {:ok, %{data: data}}
end
```

```elixir
# GOOD — return fast, load in handle_continue
def init(opts), do: {:ok, %{data: nil, opts: opts}, {:continue, :load}}

def handle_continue(:load, state), do: {:noreply, %{state | data: load_from_disk()}}
```

### 2. `spawn` instead of supervised task

```elixir
# BAD — unsupervised; crash is silent
spawn(fn -> send_email(user) end)
```

```elixir
# GOOD — supervised; crash is logged, retried per restart policy
Task.Supervisor.start_child(MyApp.TaskSup, fn -> send_email(user) end)
```

### 3. Using `try/rescue` instead of `catch :exit` for GenServer.call

```elixir
# BAD — rescue doesn't catch exits
try do
  GenServer.call(pid, :status)
rescue
  _ -> {:error, :down}
end
```

```elixir
# GOOD
try do
  GenServer.call(pid, :status)
catch
  :exit, _ -> {:error, :down}
end
```

### 4. Missing `handle_info/2` catch-all

```elixir
# BAD — stray :DOWN or :EXIT crashes the process
def handle_info({:my_event, data}, state), do: {:noreply, handle_event(state, data)}
# (no catch-all)
```

```elixir
# GOOD
def handle_info({:my_event, data}, state), do: {:noreply, handle_event(state, data)}
def handle_info(_msg, state), do: {:noreply, state}
```

### 5. `Agent` holding business logic

```elixir
# BAD — business rules buried in Agent closures
Agent.update(Cart, fn cart ->
  if cart.items |> Enum.count() >= 50, do: cart, else: %{cart | items: [item | cart.items]}
end)
```

```elixir
# GOOD — use GenServer with State module
defmodule Cart do
  use GenServer
  # ... with explicit add_item logic in Cart.State
end
```

### 6. `GenServer.call` with default timeout in a web request

```elixir
# BAD — request may hang 5s longer than your SLO
def controller_action(conn, params) do
  result = GenServer.call(MyWorker, {:process, params})  # default 5_000ms
  render(conn, :ok, result: result)
end
```

```elixir
# GOOD — explicit, documented, survivable timeout
@worker_timeout 1_500

def controller_action(conn, params) do
  case GenServer.call(MyWorker, {:process, params}, @worker_timeout) do
    {:ok, result} -> render(conn, :ok, result: result)
    {:error, _} -> render(conn, :service_unavailable)
  end
catch
  :exit, {:timeout, _} -> render(conn, :gateway_timeout)
end
```

### 7. Naming conflicts across instances

```elixir
# BAD — only one instance can exist at a time
def start_link(_), do: GenServer.start_link(__MODULE__, [], name: __MODULE__)
```

```elixir
# GOOD — accept name; enables tests and multi-instance
def start_link(opts) do
  name = Keyword.get(opts, :name, __MODULE__)
  GenServer.start_link(__MODULE__, opts, name: name)
end
```

---

## Cross-References

- **Architectural WHICH (GenServer vs Agent vs Task vs Oban?):** `../elixir-planning/otp-design.md`
- **Supervision tree shape:** `../elixir-planning/process-topology.md`
- **Integration patterns (PubSub, GenStage, Broadway):** `../elixir-planning/integration-patterns.md`
- **OTP stdlib reference lookup:** `../elixir/otp-reference.md` + `../elixir/otp-examples.md`
- **Advanced patterns (hot upgrades, production debug):** `../elixir/otp-advanced.md`
- **Reviewing existing OTP code for issues:** `../elixir-reviewing/SKILL.md` (process-level anti-pattern catalog)
