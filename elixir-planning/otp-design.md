# OTP Design — deep reference

Phase-focused deep reference for choosing **which OTP primitive** to use for a given need. Planning-mode: when GenServer, when Task, when Agent, when `:gen_statem`, when ETS, when `:persistent_term`, when GenStage/Broadway, when hot upgrades.

**When to load:** when you're designing a process and need to pick the right construct, or when refactoring an existing process because the current choice isn't fitting (e.g., GenServer bottleneck, Agent as an object).

**Related:**
- `SKILL.md §8, §9` — decision tables summary
- [process-topology.md](process-topology.md) — supervision tree design
- [integration-patterns.md](integration-patterns.md) — GenStage/Broadway/Oban for async pipelines
- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9 — OTP callback code templates
- `../elixir/otp-reference.md` — callback signatures reference
- `../elixir/otp-examples.md` — worked examples (cache, rate limiter, circuit breaker)
- `../elixir/otp-advanced.md` — GenStage, Flow, Broadway, hot code upgrades

---

## 1. Rules for OTP construct selection (LLM)

1. **ALWAYS ask "do I need a process at all?"** first. Most code is pure functions over a data store. Only introduce a process when state is shared, access is serialized, or lifecycle is independent.
2. **PREFER the narrowest construct.** Preference order: pure function → struct module → ETS → `Agent` → GenServer → `:gen_statem`. Each step up adds complexity.
3. **NEVER use `Agent` or GenServer for reads only.** Readers serialize through the process. Use ETS instead (parallel reads, no bottleneck).
4. **ALWAYS use `:gen_statem`** for processes with ≥3 states and meaningful transitions. GenServer with big `case` on state is a code smell.
5. **ALWAYS use `Task.Supervisor.async_nolink/3`** inside a GenServer if you need async work. Never `Task.async` — it links and kills the GenServer on task crash.
6. **NEVER use `:persistent_term` for frequently-updated data.** Writes are O(n) where n is the number of processes on the node (it invalidates caches). Use it for write-once / rarely-write config.
7. **ALWAYS use `:counters` / `:atomics`** for high-frequency numeric counters (requests/sec, bytes-in). They're lock-free and ~100× faster than GenServer updates.
8. **ALWAYS use Registry + DynamicSupervisor** for per-entity processes. Never use named GenServers with dynamic atoms (atom table exhaustion).
9. **PREFER GenStage / Broadway** over plain messaging when producer throughput can exceed consumer throughput. Bounded mailboxes; backpressure prevents OOM.
10. **NEVER reach for hot code upgrades** unless you have a hard "zero restart" requirement AND you've got operational discipline to keep module versions compatible. Almost all apps do fine with rolling deploys.
11. **ALWAYS design for Mox testability.** Behaviours at the infrastructure boundary → mockable without changing domain code.

---

## 2. Master decision — do you need a process?

The first and most important OTP decision. Walk through this tree:

```
Do you need a process?

1. Is this a pure transformation of data? (input → output, no external effect)
   ├── YES → Pure function. NO PROCESS.
   └── NO → continue

2. Does the call have side effects but no persistent state between calls?
   ├── YES → Pure function + module constant (or config). NO PROCESS unless serialization needed.
   └── NO → continue

3. Is state shared across multiple callers but rarely written?
   ├── YES, and reads are frequent → ETS table (possibly owned by a GenServer that writes). NOT a pure GenServer.
   ├── YES, writes only on config changes → :persistent_term
   ├── YES, numeric only → :counters / :atomics
   └── NO → continue

4. Does the state need a single writer for consistency?
   ├── YES → GenServer (or Agent if state updates are trivial).
   └── NO → Reconsider above — you probably don't need a process.

5. Does the process have distinct states with state-specific transitions?
   ├── YES → :gen_statem
   └── NO → GenServer

6. Is this work independent, one-off, with no state?
   ├── YES → Task (preferably Task.Supervisor.start_child/2)
   └── NO → Back to top.

7. Is this one process per entity (user, game, device)?
   ├── YES → DynamicSupervisor + Registry + GenServer (or :gen_statem)
   └── NO → named GenServer (one per capability)
```

### 2.1 Things that LOOK like processes but aren't

- **Accumulator pattern**: `Enum.reduce` threads state — no process needed
- **Functional state module** (`%MyState{}` + pure functions that return new state) — no process needed even for "stateful-looking" domain logic
- **Configuration** — module attributes, `Application.get_env`, `:persistent_term` — no process
- **Counter** — `:counters`, not a GenServer with `{:inc, n}` messages

---

## 3. GenServer — when it fits

### 3.1 When to use

- Single-writer serialized state (writes need ordering guarantees)
- State changes that trigger side effects (notifications, DB writes coordinated with state)
- Long-running worker with a mailbox (receives messages from multiple sources)
- Scheduling (periodic work via `handle_info(:tick, ...)`)
- Wrapping a fragile resource (one process serializes access to a single connection, file handle, hardware)

### 3.2 When NOT to use

| Anti-use | Better choice |
|---|---|
| Read-only cache | ETS `:public`, `read_concurrency: true` |
| High-frequency counter | `:counters` / `:atomics` |
| Global config | `:persistent_term` |
| Process per domain concept (cart, inventory) | Pure modules + functions |
| Complex state machine with ≥3 states | `:gen_statem` |
| Fire-and-forget side effect | `Task.Supervisor.start_child/2` |
| Write-heavy pub/sub | GenStage / Broadway |

### 3.3 GenServer design rules

1. **Client API wraps callback messages.** Callers use `MyServer.add(x)`, not `GenServer.call(MyServer, {:add, x})`.
2. **Callbacks delegate to pure functions.** `handle_call` should be 2-3 lines: match the message, call a pure function, return `{:reply, result, new_state}`.
3. **No blocking I/O in callbacks.** HTTP, DB, `Process.sleep` — offload to `Task.Supervisor.async_nolink/3` or `handle_continue/2`.
4. **Always set `timeout` on `call`.** Default is 5000ms, usually wrong.
5. **Implement `format_status/1`** if state contains secrets. Default status includes full state in crash logs.
6. **Handle unexpected messages.** `handle_info` catch-all that logs, doesn't crash.
7. **`handle_continue/2` for expensive init work.** Keeps supervisor startup fast.

### 3.4 GenServer sizing

A single GenServer processes one message at a time. Throughput budget:

- Simple state updates: ~500K-1M msgs/sec
- State + DB write: ~5K-50K msgs/sec (DB bound)
- State + external API: ~10-1000 msgs/sec (API bound)
- With `handle_continue` + `handle_info` pipeline: still one message at a time

**If you need higher throughput**, you're not at GenServer scale. Options:

- **Read side: ETS** (parallel reads)
- **Partitioned: PartitionSupervisor** (N GenServers keyed by hash)
- **Pipeline: GenStage / Broadway** (multi-stage parallel pipeline)

---

## 4. Agent — when it fits

`Agent` is a thin wrapper around GenServer. Use when:

- State is single-value (not a stateful protocol)
- Updates are trivial (no branching, no side effects)
- You don't need custom message handling (only get/update/get_and_update)

```elixir
defmodule MyApp.Counter do
  def start_link(_), do: Agent.start_link(fn -> 0 end, name: __MODULE__)
  def increment, do: Agent.update(__MODULE__, &(&1 + 1))
  def get, do: Agent.get(__MODULE__, & &1)
end
```

**Agent anti-pattern:** using Agent for complex state that needs branching, validation, or multi-step updates. If you're reaching for `Agent.update(agent, fn state -> case ... end)`, you want a GenServer.

**For high-frequency counters**: prefer `:counters` / `:atomics` over Agent. Agent serializes all updates; `:counters` is lock-free.

---

## 5. `:gen_statem` — when it fits

A proper state machine. Use when:

- Process has ≥3 named states
- State transitions are meaningful (different states respond to different messages)
- You want the `{state, data}` shape where the state is a named atom or struct

### 5.1 State machine shape

```elixir
defmodule MyApp.ConnectionFSM do
  @behaviour :gen_statem

  # States: :disconnected, :connecting, :connected, :reconnecting

  def callback_mode, do: :state_functions

  def disconnected(:enter, _old, data), do: ...
  def disconnected({:call, from}, :connect, data), do: ...

  def connecting({:call, _from}, :connect, _data), do: ...
  def connecting(:info, {:connected, ref}, data), do: ...

  def connected({:call, from}, :send, data), do: ...
  def connected(:info, :disconnected, data), do: ...

  def reconnecting(:info, :reconnect, data), do: ...
end
```

### 5.2 `:gen_statem` vs `GenServer` with state-matching

```elixir
# BAD — GenServer with big case on state
def handle_call(:connect, _from, %{status: :disconnected} = state), do: ...
def handle_call(:connect, _from, %{status: :connecting} = state), do: ...
def handle_call(:connect, _from, %{status: :connected} = state), do: ...
def handle_call(:send, _from, %{status: :connected} = state), do: ...
def handle_call(:send, _from, %{status: :disconnected} = state), do: ...
# Pattern explosion: N messages × M states = N*M clauses
```

With `:gen_statem`, each state has its own function. `:connect` in `:disconnected` is one function; `:connect` in `:connected` is a different function. Much cleaner.

### 5.3 When gen_statem shines

- Protocol implementations (TCP state machine, authentication flow, payment processor)
- Device controllers (connected → initializing → ready → error)
- Workflow engines (draft → review → approved → published)
- Game state (lobby → in_progress → ended)

**Specialized skill:** see `state-machine` skill for full `:gen_statem` implementation depth, GenStateMachine (sugar wrapper), and AshStateMachine (for Ash resources).

---

## 6. Task and Task.Supervisor — when it fits

### 6.1 Use cases

| Need | Construct |
|---|---|
| Fire-and-forget supervised side effect | `Task.Supervisor.start_child/2` |
| Await a single result (linked — task crash kills caller) | `Task.async/1` + `Task.await/2` |
| Await a result (NOT linked — handle `:DOWN` yourself) | `Task.Supervisor.async_nolink/3` |
| Parallel map with concurrency control | `Task.async_stream/3,5` |
| Stream-process many items lazily | `Task.async_stream` with `ordered: false` |

### 6.2 `async` vs `async_nolink` — the critical choice

```elixir
# BAD — Task.async inside a GenServer
def handle_call(:fetch, _from, state) do
  task = Task.async(fn -> HTTPClient.get("https://api.example.com") end)
  result = Task.await(task, 10_000)              # Blocks the GenServer for 10s!
  {:reply, result, state}
end
```

Two problems:
1. Task.await blocks the GenServer — no other calls can be served
2. If the HTTP call crashes, the linked Task propagates to the GenServer, killing it

```elixir
# GOOD — async_nolink + handle {ref, result} + handle :DOWN
def handle_call(:fetch, _from, state) do
  task = Task.Supervisor.async_nolink(MyApp.TaskSupervisor, fn ->
    HTTPClient.get("https://api.example.com")
  end)
  {:reply, :fetching, %{state | task_ref: task.ref}}
end

def handle_info({ref, result}, %{task_ref: ref} = state) do
  Process.demonitor(ref, [:flush])
  # handle result
  {:noreply, %{state | task_ref: nil, result: result}}
end

def handle_info({:DOWN, ref, :process, _pid, _reason}, %{task_ref: ref} = state) do
  {:noreply, %{state | task_ref: nil}}
end
```

### 6.3 `Task.async_stream` for parallel map

```elixir
# Fetch 100 URLs in parallel, limit to 10 concurrent
urls
|> Task.async_stream(&HTTPClient.get/1,
  max_concurrency: 10,
  timeout: 10_000,
  ordered: false    # Use false unless you specifically need input order
)
|> Enum.map(fn
  {:ok, result} -> result
  {:exit, reason} -> {:error, reason}
end)
```

**Rule:** use `Task.async_stream` for bounded parallelism. Never naked `Task.async` + `Task.await` in loops (unbounded parallelism).

---

## 7. ETS — when to escape GenServer

ETS (Erlang Term Storage) is a shared, concurrent, in-memory table. Use it when you need:

- **Read-heavy shared state** — parallel reads without serializing through a process
- **Atomic counters across processes** — `:ets.update_counter/3` is atomic
- **Large cache** — ETS scales to millions of entries
- **Fast lookups from many processes** — O(1) for `:set` / `:ordered_set` / `:bag`

### 7.1 ETS patterns

```elixir
# Create in GenServer init — GenServer owns the table
def init(_) do
  :ets.new(:my_cache, [:named_table, :public, read_concurrency: true])
  {:ok, %{}}
end

# Any process reads directly — no serialization, no bottleneck
def get(key) do
  case :ets.lookup(:my_cache, key) do
    [{^key, value}] -> {:ok, value}
    [] -> :error
  end
end

# Atomic counter increment — no races
:ets.update_counter(:stats, :requests, {2, 1}, {:requests, 0})
# Updates element at pos 2 by 1; default tuple if key missing
```

### 7.2 ETS options matter

| Option | Meaning |
|---|---|
| `:named_table` | Reference by name atom (otherwise reference by ref) |
| `:public` | Any process can read/write |
| `:protected` | Only owner writes (default) |
| `:private` | Only owner accesses |
| `read_concurrency: true` | Optimize for many readers |
| `write_concurrency: true` | Optimize for many writers (OTP 26+: `:auto`) |

**Common combos:**

- Cache (many readers, one writer): `[:public, :named_table, :set, read_concurrency: true]`
- Counter table (many writers): `[:public, :named_table, :set, write_concurrency: true]`
- Sorted data (range queries): `[:public, :named_table, :ordered_set, read_concurrency: true]`

### 7.3 ETS ownership and recovery

**The process that creates the table owns it.** When that process dies, the table is destroyed.

**Recovery:**

- Own ETS tables from a GenServer (supervised). On crash, supervisor restarts GenServer → GenServer recreates the table → you must repopulate it.
- Populate in `init/1` (for small data) or `handle_continue(:populate, ...)` for larger datasets.
- For persistent data across restarts: use DETS (disk-backed) — but DETS is slow and rarely the right choice. Usually you rebuild from Repo.

### 7.4 ETS vs GenServer for reads — benchmark

| Operation | GenServer.call | ETS.lookup | Ratio |
|---|---|---|---|
| Single read | ~1-3 μs | ~0.1-0.5 μs | ~10× |
| 100 concurrent reads | Serialized, one at a time | Parallel | ~100× |
| 1000 concurrent reads | Serialized bottleneck | Parallel | ~1000× |

**Rule:** if readers can hit the resource in parallel, use ETS. If you need serialized writes with complex logic, use a GenServer that owns the ETS table (writes via GenServer; reads direct).

---

## 8. `:persistent_term` — when to use

`:persistent_term` is a global, process-shared, read-optimized key-value store. Reads are basically free (no copy). Writes are expensive.

### 8.1 Rules

- **Reads are O(1) and effectively free** — no copy, no lock
- **Writes invalidate all process caches** — O(N) where N is process count
- **Never write on a hot path.** Writing 100× per second will make your node unusable.

### 8.2 Use cases

- Static configuration loaded at boot (read thousands of times, written once)
- Compiled patterns (regexes, NIF handles, schema metadata)
- Feature flags that change rarely (once per deploy)

### 8.3 Don't use for

- Application state that changes during runtime
- Per-request data
- High-frequency writes
- Data you might need to tombstone / garbage collect

### 8.4 Typical pattern

```elixir
# Write ONCE on application start
:persistent_term.put({MyApp, :config}, %{
  api_key: System.fetch_env!("API_KEY"),
  max_retries: 3,
  timeout_ms: 5000
})

# Read many, many times (cheap)
defp config, do: :persistent_term.get({MyApp, :config})

def call_api(data) do
  config = config()
  HTTPoison.post(config.url, data, receive_timeout: config.timeout_ms)
end
```

**Prefer namespaced keys:** `{MyApp, :something}` instead of `:something` — avoid collisions.

---

## 9. `:counters` / `:atomics` — lock-free numeric state

For high-frequency counters (request counts, bytes in/out, active connections), use `:counters` or `:atomics`. Both are lock-free arrays of integers shared across processes.

### 9.1 `:counters` — single-counter semantics

```elixir
# At application start
counters = :counters.new(10, [:atomics])     # 10 counters, atomic operations
:persistent_term.put({MyApp, :counters}, counters)

# In any process — increment atomically
defp counters, do: :persistent_term.get({MyApp, :counters})

def record_request do
  :counters.add(counters(), 1, 1)   # counter index 1, increment by 1
end

def read_request_count do
  :counters.get(counters(), 1)
end
```

### 9.2 `:atomics` — arrays of arbitrary atomic integers

```elixir
# More flexible — arbitrary get/set/add semantics
atomics = :atomics.new(10, signed: true)

:atomics.add(atomics, 1, 5)
:atomics.get(atomics, 1)
:atomics.compare_exchange(atomics, 1, 0, 10)   # CAS operation
```

### 9.3 When to use

- Counters incremented thousands of times per second
- Gauges that need atomic read/update across processes
- Simple shared integers without the overhead of a process

### 9.4 When NOT to use

- If you need the counter to be one of many keys — use ETS with `:ets.update_counter/3`
- If you need observers to subscribe to changes — use a GenServer with a callback list

---

## 10. DynamicSupervisor + Registry — per-entity processes

When you need **one process per entity** (user, game, device, session), use DynamicSupervisor + Registry together.

### 10.1 The canonical shape

```elixir
# Registry — start BEFORE DynamicSupervisor
defmodule MyApp.GameRegistry do
  def child_spec(_), do: Registry.child_spec(keys: :unique, name: __MODULE__)
  def via(game_id), do: {:via, Registry, {__MODULE__, game_id}}
end

# DynamicSupervisor — starts workers on demand
defmodule MyApp.GameSupervisor do
  use DynamicSupervisor

  def start_link(_), do: DynamicSupervisor.start_link(__MODULE__, :ok, name: __MODULE__)

  @impl true
  def init(:ok), do: DynamicSupervisor.init(strategy: :one_for_one)

  def start_game(game_id, opts \\ []) do
    DynamicSupervisor.start_child(__MODULE__,
      {MyApp.GameServer, [game_id: game_id] ++ opts}
    )
  end
end

# Worker registers via the Registry helper
defmodule MyApp.GameServer do
  use GenServer

  def start_link(opts) do
    game_id = Keyword.fetch!(opts, :game_id)
    GenServer.start_link(__MODULE__, opts, name: MyApp.GameRegistry.via(game_id))
  end

  def call(game_id, msg) do
    GenServer.call(MyApp.GameRegistry.via(game_id), msg)
  end
end

# In application.ex — Registry BEFORE DynamicSupervisor (:one_for_all strategy)
children = [
  {Supervisor, name: MyApp.GamesSup, strategy: :one_for_all, children: [
    MyApp.GameRegistry,
    MyApp.GameSupervisor
  ]}
]
```

### 10.2 Why `:one_for_all` for Registry + DynamicSupervisor

If Registry crashes:
- All workers lose their registered name
- They can't be found by `via()`
- Effectively orphaned

So: when Registry dies, we must tear down all workers too. That's `:one_for_all`.

### 10.3 Discovery patterns

```elixir
# Lookup
case Registry.lookup(MyApp.GameRegistry, game_id) do
  [{pid, _}] -> {:ok, pid}
  [] -> :error
end

# Dispatch to all workers of a type
Registry.dispatch(MyApp.GameRegistry, "game:events", fn entries ->
  for {pid, _} <- entries, do: send(pid, {:broadcast, event})
end)

# Count
Registry.count(MyApp.GameRegistry)
```

### 10.4 When per-entity is right

- Distinct state per entity (each user has a separate cart, each game has its own board)
- Independent failure domains (one user's crash doesn't affect others)
- Async communication between entities
- Long-lived stateful sessions (WebSocket connections, game sessions, device handlers)

### 10.5 When per-entity is wrong

- Short-lived requests (use a pool instead of a process per request)
- Millions of entities (memory cost — each process is ~2.6KB + state)
- When the data could just live in a database row and be loaded on demand

### 10.6 Millions of entities — partitioning

For >100K entities, consider:

- **PartitionSupervisor** — N supervisors keyed by hash, each holding a subset of workers
- **Consistent hashing** — route entity_id mod N to a specific node (for clustered apps)
- **Process hibernation** — `:hibernate` returns save memory for idle processes

```elixir
# Partition workers across N supervisors
{:ok, _} = PartitionSupervisor.start_link(
  child_spec: {DynamicSupervisor, strategy: :one_for_one},
  name: MyApp.GamePartitions,
  partitions: System.schedulers_online()
)

# Route by game_id hash
partition = :erlang.phash2(game_id, System.schedulers_online())
{:via, PartitionSupervisor, {MyApp.GamePartitions, partition}}
```

---

## 11. GenStage / Broadway — when pipelines need backpressure

Use when a producer can exceed a consumer's throughput. PubSub and plain messaging don't solve this — mailboxes grow unbounded until OOM.

### 11.1 GenStage in one paragraph

GenStage inverts control: **consumers request N items when ready**; producers emit only that many. Producer buffers events; only dispatches on demand. If consumer is slow, producer's buffer fills; once it's full, upstream backpressures.

### 11.2 When to use GenStage

- Producer rate is variable or bursty and can exceed consumer
- Data loss is unacceptable (PubSub drops events)
- Multi-stage transformation (producer → filter → transform → persist)
- I/O-bound processing with natural bottlenecks
- Need concurrency control (limit N items in flight)

### 11.3 Broadway vs raw GenStage

**Broadway wraps GenStage** with declarative config, built-in batching, fault tolerance, graceful shutdown, and message-broker adapters.

**Use Broadway when:**

- Consuming from Kafka, SQS, RabbitMQ, Redis Streams, Google Pub/Sub
- You need batching (accumulate N items, flush together — e.g., bulk DB inserts)
- You want declarative concurrency config
- You need built-in telemetry

**Use raw GenStage when:**

- In-process pipelines (no external broker)
- You need unusual topologies (fan-out, fan-in)
- Broadway's model doesn't fit

### 11.4 When NOT to use GenStage

- Fan-out to UI (LiveView updates) — use PubSub, fast consumers, low volume
- Occasional event loss acceptable — use PubSub
- No transformation — just broadcast and forget

For depth: `../elixir/otp-advanced.md` and [integration-patterns.md](integration-patterns.md).

---

## 12. Oban — when you need persistent async work

Oban is a PostgreSQL-backed job queue. Jobs survive crashes and restarts.

### 12.1 Use when

- Jobs must not be lost (email delivery, webhooks, billing)
- Need retries with backoff
- Need scheduling (run at specific times, cron)
- Need uniqueness (deduplicate identical jobs)
- Need cross-node coordination (shared DB)

### 12.2 When NOT to use

- One-off in-memory tasks (use `Task.Supervisor`)
- High-volume ephemeral events (use GenStage/Broadway)
- Tasks that must complete synchronously (await result) — Oban is async by design

### 12.3 Oban anatomy

```elixir
# Application supervisor includes Oban
children = [
  MyApp.Repo,
  {Oban, Application.fetch_env!(:my_app, Oban)}
]

# config/config.exs
config :my_app, Oban,
  repo: MyApp.Repo,
  queues: [default: 10, emails: 5, payments: 2],
  plugins: [
    {Oban.Plugins.Pruner, max_age: 60 * 60 * 24},
    {Oban.Plugins.Cron, crontab: [{"0 2 * * *", MyApp.Workers.DailyCleanup}]}
  ]

# Worker module
defmodule MyApp.Workers.SendEmail do
  use Oban.Worker, queue: :emails, max_attempts: 5

  @impl Oban.Worker
  def perform(%Oban.Job{args: %{"user_id" => user_id}}) do
    user = MyApp.Accounts.get_user!(user_id)
    MyApp.Mailer.send_welcome(user)
  end
end

# Enqueue from a context
def register(attrs) do
  with {:ok, user} <- Repo.insert(User.changeset(%User{}, attrs)) do
    %{user_id: user.id}
    |> MyApp.Workers.SendEmail.new()
    |> Oban.insert()
    {:ok, user}
  end
end
```

### 12.4 Design considerations

- **Idempotency is required** — jobs may retry. Code must handle duplicate execution safely.
- **Use `unique:`** — deduplicate jobs with the same args.
- **Set `max_attempts`** — failed jobs retry this many times with exponential backoff.
- **Keep jobs small** — large payloads inflate the DB. Pass IDs, not objects.
- **Queues separate concerns** — emails queue can't block payments queue.

---

## 13. Hot code upgrades — when (rarely) to consider

Hot code upgrades replace code in a running VM without restarting. Almost never worth the complexity.

### 13.1 Use only when

- Hard "zero downtime" requirement beyond rolling deploys (telecom, financial systems)
- State migrations across versions are well-controlled
- You have operational discipline to keep module versions compatible (`code_change/3` callbacks on GenServer, etc.)

### 13.2 Don't use when

- Rolling deploy works (you deploy new nodes, drain old ones) — this is the default for web apps
- State migrations are ad-hoc
- Team doesn't have experience managing release handoffs

### 13.3 Rolling deploys as the alternative

For most Elixir apps:
- Deploy new version alongside old
- Drain traffic from old nodes (LB stops sending to them)
- Old connections complete; old nodes shut down
- Zero downtime without hot code upgrade complexity

**Rolling deploys work for 99% of cases.** Hot upgrades are in the other 1%.

For depth on hot upgrades: `../elixir/otp-advanced.md`.

---

## 14. OTP design decision reference

### 14.1 Master decision table

| Need | Construct | Why not other options |
|---|---|---|
| Shared read-heavy state | ETS | GenServer serializes; Agent same |
| Shared write-heavy numeric | `:counters` | GenServer is slow; ETS counter is fine too |
| Rarely-changing global config | `:persistent_term` | ETS works but needs manual lookup; `:persistent_term` is designed for this |
| Single-writer serialized state | GenServer | Nothing else has the callback model for complex ops |
| State machine (≥3 states) | `:gen_statem` | GenServer with big case is worse |
| One-off async side effect | `Task.Supervisor.start_child/2` | spawn is unsupervised; Task.async requires await |
| Bounded parallel work | `Task.async_stream` | Manual `async + await` loops are unbounded |
| Per-entity processes | DynamicSupervisor + Registry | Named GenServers don't work for dynamic atoms |
| Backpressured pipeline | GenStage / Broadway | PubSub drops events under load |
| Persistent async jobs | Oban | In-memory tasks are lost on crash |
| Stateful protocol | `:gen_statem` | Complex state transitions in GenServer are unreadable |

### 14.2 Red flags in existing OTP code

| Observation | Likely issue | Fix |
|---|---|---|
| GenServer.call bottleneck on reads | Wrong construct | Move reads to ETS |
| Agent used for complex state | Need more than Agent | Upgrade to GenServer |
| `String.to_atom(user_input)` for Registry lookup | Atom exhaustion | Use binary keys or pre-registered atoms |
| Big `case` on `state.status` in GenServer | Need gen_statem | Refactor to `:gen_statem` |
| Counter GenServer | Bottleneck | Move to `:counters` |
| Giant process state (>100KB) | Wrong place for data | Move to ETS, chunk, or persist |
| Unsupervised `spawn` | Lost on crash, not cleanup | Supervised Task |
| Task.async without Task.Supervisor | Link leak; crash propagation | `Task.Supervisor.async_nolink/3` |
| Ad-hoc retries in domain code | Should be infrastructure | Oban or wrapper with backoff |

---

## 15. Cross-references

### Within this skill

- `SKILL.md §8, §9` — decision tables summary
- [process-topology.md](process-topology.md) — supervision tree design and error kernel
- [integration-patterns.md](integration-patterns.md) — GenStage/Broadway/Oban depth
- [test-strategy.md](test-strategy.md) — how OTP construct choice affects testability

### In other skills

- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9 — OTP callback code templates
- [../elixir-reviewing/SKILL.md](../elixir-reviewing/SKILL.md) §7.6, §8.1-8.3 — OTP review and debugging
- `state-machine` skill — deep `:gen_statem` / GenStateMachine / AshStateMachine
- `../elixir/otp-reference.md` — callback signatures reference
- `../elixir/otp-examples.md` — worked examples
- `../elixir/otp-advanced.md` — GenStage, Broadway, hot upgrades

---

**End of otp-design.md.** This subskill answers "which OTP construct?" For supervision tree shape, see [process-topology.md](process-topology.md). For callback code, see [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9.
