# Process Topology — deep reference

Phase-focused deep reference for supervision tree design and process architecture. Expands on `SKILL.md §8` with the full design vocabulary: error kernel, supervisor strategies by intent, process-per-service vs per-entity, stateful vs stateless design, the callback module pattern, and the instructions pattern.

**When to load:** when designing the supervision tree for a new system, when reorganizing an existing tree, when deciding where state should live, when a single GenServer is doing too much, or when you need to understand which supervisor strategy to use.

**Related:**
- `SKILL.md §8` — the overview and decision tables
- [architecture-patterns.md](architecture-patterns.md) — how architectural styles map to process topologies
- [integration-patterns.md](integration-patterns.md) — inter-context communication patterns that live between processes
- [otp-design.md](otp-design.md) — when to pick GenServer vs Task vs Agent vs :gen_statem
- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9 — OTP callback code templates

---

## 0. The Actor Model in BEAM — quick conceptual orientation

If you're coming from a thread/shared-memory world, the mental model matters. The BEAM's **actor model** has five properties that drive every process-topology decision:

| Property | What it means | Consequence for design |
|---|---|---|
| **Isolated state** | Each process has its own heap, own GC | No locks, no mutexes, no shared-data race conditions |
| **Message passing** | Processes communicate only by messages (async `send` or sync `GenServer.call`) | Inter-process data is **copied** (immutable by design) |
| **Shared nothing** | No shared memory between processes | Scales linearly across cores; GC is per-process, never stop-the-world |
| **Location transparent** | `send(pid, msg)` works identically for local and remote PIDs | Distribution is a configuration choice, not a code change |
| **Fail independently** | One process crash doesn't affect others | Supervision handles recovery; unrelated workers keep running |

**Message-passing semantics you must design around:**

| Guarantee | What it means | Implication |
|---|---|---|
| **At-most-once delivery** | A message is delivered zero or one times (default) | Messages can be lost if the receiver crashes before processing → idempotency matters |
| **Per-sender order** | Messages from A to B arrive in send order | But A→B and C→B may interleave |
| **No exactly-once** | BEAM provides no built-in exactly-once | Application handles via idempotency keys |
| **`call` vs `cast`** | `call` blocks until reply or exit; `cast` is fire-and-forget | Use `call` when you need the outcome; `cast` only when loss is acceptable |

**The single most important rule this drives:** across node boundaries, ALWAYS use `call` (with a sensible timeout and `catch :exit`). Network partitions make `cast` silently unreliable — the message disappears without a trace.

**Design implication — "processes for isolation, modules for thought":** processes are a runtime tool (fault isolation, parallelism, lifecycle management). They are not the unit of code organization. A domain "User" is a module (plus maybe an Ecto schema), not a process-per-user — unless *users have in-memory runtime state that must survive concurrent access*.

See `../elixir-implementing/otp-callbacks.md` for the implementation side. The rest of this document takes the actor model as given and focuses on how to shape a supervision tree.

---

## 1. Rules for designing process topology (LLM)

1. **ALWAYS draw the supervision tree before writing code.** The tree IS the architecture. If you can't draw it, you can't build it.
2. **ALWAYS order children by dependency.** Children started first are started first. Later children may depend on earlier ones. Top to bottom = dependency chain.
3. **ALWAYS put critical state at the top of the tree** (error kernel). Volatile, crash-prone workers go below.
4. **NEVER create processes to model domain concepts.** Processes model *runtime concerns* (fault isolation, parallelism, lifecycle). Modules model *thought concerns*.
5. **PREFER stateless design** — most contexts don't need a process, just functions over a data store.
6. **ALWAYS design a recovery strategy for stateful processes.** What happens on crash? Reconstruct from DB? Accept empty state? Fetch from peer? If you can't answer, the process shouldn't hold state.
7. **NEVER let a worker's crash affect unrelated workers.** That's the bulkhead principle. Use supervision boundaries to isolate failure domains.
8. **ALWAYS use `:one_for_all`** for tightly coupled process pairs (Registry + DynamicSupervisor).
9. **ALWAYS use `:rest_for_one`** when later children depend on earlier ones.
10. **PREFER `:one_for_one`** at the top level for independent subsystems.
11. **ALWAYS start the endpoint (HTTP, WebSocket acceptor) LAST.** Don't accept traffic until the system is ready.
12. **NEVER `spawn`/`spawn_link` for long-running work.** Supervise everything that outlives its caller. Use `Task.Supervisor` for fire-and-forget, `DynamicSupervisor` for managed workers.
13. **ALWAYS keep business logic in pure modules.** GenServer callbacks delegate to pure functions. This is the pure-core-impure-shell rule.
14. **PREFER the instructions pattern** when domain logic needs to trigger side effects — return instruction lists, let the caller interpret.
15. **PREFER the callback module pattern** when a process needs to dispatch to pluggable transports (HTTP, WebSocket, channel, test).

---

## 2. The error kernel — foundational concept

### 2.1 What is the error kernel?

The **error kernel** is the minimal set of processes that must not fail for the system to function. Everything else is expendable.

```
Application Supervisor (:one_for_one)
├── Telemetry              ┐
├── Repo                   │ ERROR KERNEL
├── PubSub                 │ Must not crash — if any of these fail,
│                          ┘ the system can't serve traffic
│   ─── BOUNDARY ───
│
├── DomainServices (:rest_for_one)     ┐
│   ├── Cache                          │ VOLATILE
│   ├── EventProcessor                 │ Can crash — recovery strategy
│   └── NotificationQueue              ┘ exists for each
├── WorkerManager (:one_for_all)       ┐
│   ├── WorkerRegistry                 │ Transient workers
│   └── WorkerSupervisor               ┘
└── Endpoint               ← Last. Only accept traffic when ready.
```

**Design principles:**

- Critical state (DB, PubSub, telemetry) starts FIRST and lives at the TOP
- Volatile processes (caches, processors, workers) live BELOW — they can crash and recover
- Workers under DynamicSupervisor are fully expendable — each crash is isolated
- Endpoint starts LAST — don't accept traffic until dependencies are ready

### 2.2 What makes something "error-kernel-worthy"?

A process belongs in the error kernel if **the system cannot function without it**. Typical error-kernel members:

- **Repo** — no DB = no reads/writes
- **PubSub** — no pubsub = no cross-context events
- **Telemetry** — no telemetry = blind to problems
- **Config store** (e.g., a process wrapping `:persistent_term`) — if used

Typical NOT error-kernel:
- Caches — can rebuild from DB on restart
- Background job workers — jobs persist in Oban; restarting workers is safe
- Connection handlers — crash kills one connection, others unaffected
- Per-entity processes — crash affects one user/game/device

### 2.3 Designing the error kernel

Walk through the failure scenarios:

1. **What fails first if the DB goes down?** The Repo process — and since it's in the kernel, the app supervisor's `max_restarts` will eventually trip and the app will exit (good! the orchestrator then restarts the app fresh).
2. **What fails if the cache crashes?** Just the cache. Everything else continues. The cache rebuilds on restart.
3. **What fails if one worker crashes?** Just that worker. Other workers unaffected. The DynamicSupervisor restarts it.

**Test:** trace every external dependency (DB, external API, cache). Which processes die if each goes away? Those are your failure domains.

---

## 3. Supervisor strategies by intent

Three strategies, each encoding a different coupling relationship.

### 3.1 `:one_for_one` — default, independent children

```elixir
Supervisor.init([A, B, C], strategy: :one_for_one)
# A crashes → only A restarts. B and C unaffected.
```

**Use for:**
- Top-level supervisor of independent subsystems
- Pool of identical but independent workers
- Anything where children don't share state

**Default choice.** Use unless you have a specific reason to use another.

### 3.2 `:rest_for_one` — children depend on earlier siblings

```elixir
Supervisor.init([A, B, C], strategy: :rest_for_one)
# A crashes → A, B, C restart (B and C may depend on A's state).
# B crashes → B, C restart.
# C crashes → just C.
```

**Use for:**
- Registry before DynamicSupervisor before workers (workers depend on both)
- Cache → Processor → Notifier (processor depends on cache; notifier depends on processor)
- Any chain where later children were started with refs to earlier ones

**Example:**

```elixir
children = [
  {Phoenix.PubSub, name: MyApp.PubSub},     # A
  MyApp.EventProcessor,                      # B — subscribes to PubSub on init
  MyApp.NotificationDispatcher               # C — depends on EventProcessor
]
# If PubSub crashes, B's subscription is gone → B must be restarted too
# If B crashes, C might have cached refs → restart C too
Supervisor.init(children, strategy: :rest_for_one)
```

### 3.3 `:one_for_all` — tightly coupled children

```elixir
Supervisor.init([A, B], strategy: :one_for_all)
# Any crash → ALL children restart.
```

**Use for:**
- Registry + DynamicSupervisor pair (if Registry dies, workers can't re-register — tear down and rebuild)
- Multiple producer/consumer pairs in a tight flow
- Any case where a partial restart leaves inconsistent state

**Canonical example — Registry + DynamicSupervisor:**

```elixir
defmodule MyApp.WorkerSupervisor do
  use Supervisor

  def start_link(init), do: Supervisor.start_link(__MODULE__, init, name: __MODULE__)

  @impl true
  def init(_) do
    children = [
      {Registry, keys: :unique, name: MyApp.WorkerRegistry},
      {DynamicSupervisor, name: MyApp.WorkerDynSup, strategy: :one_for_one}
    ]
    # If Registry dies, DynSup's workers can't re-register — must rebuild both
    Supervisor.init(children, strategy: :one_for_all)
  end
end
```

### 3.4 Strategy decision table

| Are children independent? | Later children depend on earlier? | Tightly coupled (must restart together)? | Strategy |
|---|---|---|---|
| ✅ | ❌ | ❌ | `:one_for_one` |
| ❌ | ✅ | ❌ | `:rest_for_one` |
| ❌ | ❌ | ✅ | `:one_for_all` |

### 3.5 Restart intensity — when `max_restarts` trips

By default, a supervisor allows **3 restarts in 5 seconds**. If that's exceeded, the supervisor itself exits.

```elixir
Supervisor.init(children, strategy: :one_for_one, max_restarts: 3, max_seconds: 5)
```

**Why this matters:**
- An error-kernel supervisor exiting → the application exits → the OS restarts your release (Kubernetes, systemd, etc.)
- A sub-supervisor exiting → its parent supervisor handles it per the parent's strategy

**Tuning:**
- Raise `max_restarts` for workers that routinely fail and retry (e.g., flaky external connections)
- Lower it when crashes should bubble up fast (e.g., config error on startup)

**Never** set `max_restarts: :infinity` casually — it hides actual bugs.

---

## 4. Process architecture patterns

### 4.1 Process-per-service (most common)

**One long-lived process per service capability.** Processes represent capabilities, not entities.

```elixir
children = [
  MyApp.Repo,              # One DB connection pool
  MyApp.Cache,             # One cache service
  MyApp.Mailer,            # One email sender
  MyApp.RateLimiter        # One rate limiting service
]
```

**Use for:** services that have shared state (connection pool, cache, counters). **This is the default for most applications.**

**Shape:**
- One process per service
- Named at the module level (`GenServer.start_link(..., name: __MODULE__)`)
- Clients call `MyApp.Cache.get(key)` which wraps `GenServer.call(__MODULE__, {:get, key})`

### 4.2 Process-per-entity (when independent state is real)

**One process per domain entity** — each instance manages its own state.

```elixir
# Game server — one process per active game
{:ok, _pid} = DynamicSupervisor.start_child(
  MyApp.GameSupervisor,
  {MyApp.GameServer, game_id: id, players: players}
)

# IoT device — one process per connected device
{:ok, _pid} = DynamicSupervisor.start_child(
  MyApp.DeviceSupervisor,
  {MyApp.DeviceHandler, device_id: id}
)
```

**Use for:**
- Entities with independent state (each game has its own board, each session has its own state)
- Entities that need isolated failure domains (one device's crash doesn't affect others)
- Entities that communicate asynchronously with each other

**Watch for:** memory scales linearly with entity count. 100K games = 100K processes × per-process memory.

**Cost profile:**
- Each process: ~2.6KB base + state
- 100K processes: ~260MB + state × 100K
- Each process has its own mailbox, GC, reduction counter

### 4.3 Hybrid — Service + Entity Pool

Service process manages lifecycle; DynamicSupervisor manages instances.

```elixir
defmodule MyApp.GameManager do
  def start_game(params) do
    game_id = generate_id()

    {:ok, _pid} = DynamicSupervisor.start_child(
      MyApp.GameSupervisor,
      {MyApp.GameServer, {game_id, params}}
    )

    {:ok, game_id}
  end

  def find_game(game_id), do: MyApp.GameRegistry.lookup(game_id)

  def end_game(game_id) do
    case find_game(game_id) do
      {:ok, pid} -> DynamicSupervisor.terminate_child(MyApp.GameSupervisor, pid)
      :error -> {:error, :not_found}
    end
  end
end
```

**Structure:**

```
GameManager (process-per-service — the API)
GameRegistry (Registry — for lookup)
GameSupervisor (DynamicSupervisor — for per-entity processes)
└── GameServer :game_1 (per-entity)
    GameServer :game_2
    GameServer :game_3
    ...
```

### 4.4 Choosing process-per-service vs per-entity

| Question | Process-per-service | Process-per-entity |
|---|---|---|
| How many entities? | 1 | Many (10s to 100Ks) |
| Memory cost | Bounded by service state | Scales with entity count |
| Fault isolation | All entities share one failure domain | Each entity is its own failure domain |
| Concurrency | One process serializes all requests | Each entity is independent |
| Discovery | Named registration | Registry / :via |
| Simplicity | Simple | More moving parts (registry, dyn sup) |

**Default to process-per-service.** Move to process-per-entity when you have a specific need: isolation, concurrency, or independent state.

### 4.5 Anti-pattern: simulating objects with processes

**Do NOT create one process per domain concept** (Agent for the shopping cart, Agent for the inventory, Agent for each order). This is the single most common OTP mistake.

```elixir
# BAD — simulating objects with processes
cart_agent = Agent.start_link(fn -> Cart.new() end)
inventory_agent = Agent.start_link(fn -> Inventory.new(products) end)
# Every operation requires cross-process messaging to coordinate
Agent.update(cart_agent, fn cart ->
  item = Agent.get(inventory_agent, fn inv -> Inventory.take(inv, sku) end)
  Cart.add(cart, item)
end)

# GOOD — pure functional abstractions
cart = Cart.new()
{:ok, item, inventory} = Inventory.take(inventory, sku)
cart = Cart.add(cart, item)
# Simple, testable, no process overhead.
```

**The rule:** Functions separate *thought concerns* (concepts in your model). Processes separate *runtime concerns* (fault isolation, parallelism, lifecycle). If concepts always change together in the same flow, they belong together.

**Decision test:** Ask "do these things need to fail independently? Run in parallel? Have different lifecycles?" If not, they belong together.

---

## 5. Stateful vs stateless design

A key architectural decision: should a process hold state in memory, or reconstruct it from a data store on each call?

### 5.1 The three approaches

| Approach | Trade-off | Use when |
|---|---|---|
| **Stateless** (reconstruct from DB) | Slower reads, crash-resilient | CRUD, request handlers, most web contexts |
| **Stateful** (state in process memory) | Fast reads, state lost on crash | Real-time counters, active sessions, device connections |
| **Hybrid** (process state + periodic persistence) | Best of both, more complex | Game state, long workflows, IoT device state |

### 5.2 Stateless example

```elixir
defmodule MyApp.Accounts do
  def get_user(id), do: Repo.get(User, id)

  def update_user(user, attrs) do
    user
    |> User.changeset(attrs)
    |> Repo.update()
  end
end
```

No process needed. Each call hits the DB. Works even if the previous call crashed.

### 5.3 Stateful example

```elixir
defmodule MyApp.DeviceConnection do
  use GenServer

  def get_status(device_id), do: GenServer.call(via(device_id), :status)

  @impl true
  def handle_call(:status, _from, state), do: {:reply, state.status, state}

  @impl true
  def handle_info({:sensor_data, data}, state) do
    new_state = %{state | last_reading: data, status: :active}
    {:noreply, new_state}
  end
end
```

State lives in the process. Reads are O(1). **If the process crashes, state is lost** — recovery strategy is needed.

### 5.4 Hybrid example

```elixir
defmodule MyApp.GameServer do
  use GenServer

  @persist_interval :timer.seconds(30)

  @impl true
  def init(game_id) do
    state = Games.load_state(game_id)          # Reconstruct from DB
    Process.send_after(self(), :persist, @persist_interval)
    {:ok, state}
  end

  @impl true
  def handle_info(:persist, state) do
    Games.save_state(state)                    # Periodic persistence
    Process.send_after(self(), :persist, @persist_interval)
    {:noreply, state}
  end

  @impl true
  def terminate(_reason, state) do
    Games.save_state(state)                    # Save on shutdown
  end
end
```

Process state for speed + periodic persistence for durability. Recovery from DB on restart.

### 5.5 Decision rules

1. **Default to stateless** — most contexts don't need a process.
2. **Don't create a GenServer for single-caller request/response** — that's just adding a bottleneck (serialized mailbox) for no benefit.
3. **Stateful processes need a recovery strategy** — document it explicitly.
4. **State ≠ cache.** If you're holding DB data in a GenServer just to avoid queries, use ETS or `:persistent_term` instead (non-serialized reads).

### 5.6 Recovery strategy catalog

Every stateful process must answer: **what happens on crash?**

| Strategy | Pattern | Use when |
|---|---|---|
| **Reconstruct from DB** | `init/1` loads from persistent store; events replay if event-sourced | State is derivable from durable storage |
| **Accept empty state** | `init/1` returns fresh state; caller must re-populate | Cache; state is purely ephemeral |
| **Fetch from peer** | `init/1` queries another node's state (clustered apps) | Replicated / clustered stateful services |
| **Periodic snapshot** | `handle_info(:persist, ...)` on an interval + `terminate/2` final save | Long-running workflows, game state |
| **Accept data loss** | `init/1` starts empty; any loss is acceptable | Purely ephemeral processes (TTL sessions) |
| **Don't be stateful** | Redesign to stateless — easier recovery is no recovery | When a recovery strategy is hard to pick |

---

## 6. OTP process construct choice

Choosing **which OTP primitive** to use for the process itself. Full decision table in `SKILL.md §9.2`; deep guide in [otp-design.md](otp-design.md).

Brief summary here:

| Need | Construct |
|---|---|
| One-off supervised side-effect work | `Task.Supervisor.start_child/2` |
| Parallel map with concurrency control | `Task.async_stream/3,5` |
| Long-running stateful worker | GenServer |
| Explicit state machine | `:gen_statem` |
| Single-value shared state | `Agent` (or GenServer — Agent is thin wrapper) |
| Read-heavy shared data | ETS (not a process construct — a shared table) |
| Atomic counters/gauges | `:counters` / `:atomics` |
| Rarely-changing global config | `:persistent_term` |
| Backpressured pipeline | GenStage / Broadway |
| Persistent job queue | Oban |
| Dynamic per-entity processes | DynamicSupervisor + Registry |

**For depth:** see [otp-design.md](otp-design.md).

---

## 7. The callback module pattern

When a GenServer needs to interact with different types of clients (HTTP, WebSocket, TCP, test harness), define a behaviour for the client-facing callbacks. The server invokes callback functions without knowing the transport.

### 7.1 The shape

```elixir
defmodule MyApp.SessionServer do
  @callback on_event(callback_arg :: any(), participant_id(), event()) :: any()
  @callback on_complete(callback_arg :: any(), participant_id(), result()) :: any()

  use GenServer

  def start_link(session_id, participants) do
    # Each participant: %{id: id, callback_mod: module, callback_arg: any}
    GenServer.start_link(__MODULE__, {session_id, participants}, name: via(session_id))
  end

  @impl true
  def handle_call({:action, participant_id, action}, _from, state) do
    {instructions, domain} = MyDomain.process(state.domain, participant_id, action)
    dispatch(instructions, state.participants)
    {:reply, :ok, %{state | domain: domain}}
  end

  defp dispatch(instructions, participants) do
    Enum.each(instructions, fn {:notify, participant_id, event} ->
      %{callback_mod: mod, callback_arg: arg} = Map.fetch!(participants, participant_id)
      mod.on_event(arg, participant_id, event)
    end)
  end
end
```

### 7.2 Different transports implement the same behaviour

```elixir
# Phoenix Channel transport
defmodule MyApp.ChannelNotifier do
  @behaviour MyApp.SessionServer
  @impl true
  def on_event(socket_pid, participant_id, event) do
    send(socket_pid, {:push_event, participant_id, event})
  end
  @impl true
  def on_complete(socket_pid, _participant_id, result) do
    send(socket_pid, {:session_complete, result})
  end
end

# Test transport — sends messages to test process
defmodule MyApp.TestNotifier do
  @behaviour MyApp.SessionServer
  @impl true
  def on_event(test_pid, participant_id, event) do
    send(test_pid, {:event, participant_id, event})
  end
  @impl true
  def on_complete(test_pid, _participant_id, result) do
    send(test_pid, {:complete, result})
  end
end
```

### 7.3 When to use

Any GenServer that needs to push information to external clients over potentially different transports:
- Multiplayer game server (WebSocket, IoT, test)
- Workflow engine (notify participants via email, Slack, webhook, test)
- Session server (web channel, mobile push, test)

**Benefits:**
- Server is transport-agnostic
- Testable without a real network (test transport sends to test process)
- New transports added without modifying the server

**When NOT to use:** if only one transport will ever exist, don't bother. YAGNI.

---

## 8. The instructions pattern

When domain logic needs to trigger side effects (notifications, messages, I/O), **don't perform them inline**. Pure domain functions return a list of **instructions** — data describing what should happen — and the caller (GenServer, controller, test) interprets them.

### 8.1 The shape

```elixir
defmodule MyApp.Workflow do
  @opaque t :: %__MODULE__{}
  defstruct [:state, :participants, instructions: []]

  @spec advance(t(), participant_id(), action()) :: {[instruction()], t()}
  def advance(workflow, participant_id, action) do
    workflow
    |> validate_participant(participant_id)
    |> apply_action(action)
    |> maybe_transition()
    |> emit_instructions()
  end

  # Returns instructions like:
  # [
  #   {:notify, participant_id, {:status_changed, :approved}},
  #   {:notify, reviewer_id, {:task_assigned, task}},
  #   {:schedule, {:deadline, task_id}, :timer.hours(24)}
  # ]

  defp emit_instructions(%{instructions: instructions} = workflow) do
    {Enum.reverse(instructions), %{workflow | instructions: []}}
  end

  # Internal helpers push instructions without performing them
  defp notify(workflow, participant, event) do
    %{workflow | instructions: [{:notify, participant, event} | workflow.instructions]}
  end

  defp schedule(workflow, event, delay) do
    %{workflow | instructions: [{:schedule, event, delay} | workflow.instructions]}
  end
end
```

### 8.2 GenServer interprets the instructions

```elixir
defmodule MyApp.WorkflowServer do
  use GenServer

  @impl true
  def handle_call({:advance, participant_id, action}, _from, state) do
    {instructions, workflow} = MyApp.Workflow.advance(state.workflow, participant_id, action)
    new_state = %{state | workflow: workflow}
    execute_instructions(instructions, state)
    {:reply, :ok, new_state}
  end

  defp execute_instructions(instructions, state) do
    Enum.each(instructions, fn
      {:notify, participant_id, event} ->
        MyApp.Notifier.send(state.notifiers[participant_id], event)

      {:schedule, event, delay} ->
        Process.send_after(self(), {:scheduled, event}, delay)
    end)
  end
end
```

### 8.3 Why this pattern

- **Domain logic is pure and trivially testable** — assert on returned instructions; no mocking
- **Multiple drivers** — same domain module can be driven by GenServer, LiveView, test, IEx
- **Temporal concerns stay out of domain** — retries, timeouts, delivery guarantees are the server's problem
- **Domain can evolve independently** — adding new business rules doesn't touch notification/persistence code

```elixir
# Testing is dead simple
test "advancing workflow notifies next participant" do
  workflow = Workflow.new([:alice, :bob])
  {instructions, _workflow} = Workflow.advance(workflow, :alice, :approve)

  assert {:notify, :bob, {:task_assigned, _}} = List.last(instructions)
end
```

### 8.4 When to use

The instructions pattern shines when:
- Domain has complex state transitions AND multiple side-effect types
- Logic should be testable without processes
- Multiple drivers will exist (GenServer, LiveView, CLI)

**When NOT to use:** for simple GenServers with one or two side effects, normal delegation to pure helpers (pure-core-impure-shell) is enough.

---

## 9. OTP application boundaries in umbrella projects

In umbrella/poncho projects, each OTP application has its own supervision tree, configuration, and lifecycle. This maps directly to architectural boundaries.

```elixir
defmodule Core.Application do
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      Core.Repo,
      {Phoenix.PubSub, name: Core.PubSub},
      Core.Accounts.SessionCleanup,
      Core.Catalog.SearchIndex
    ]
    Supervisor.start_link(children, strategy: :one_for_one, name: Core.Supervisor)
  end
end
```

**Each application controls:**
- Which processes start and in what order
- Restart strategy for its subsystems
- Configuration namespace (`Application.get_env(:core, ...)`)
- What it exposes to other applications (public modules)

**Umbrella vs single app:**
- Single app with contexts = simpler, one supervision tree, one config
- Umbrella = hard compile-time boundaries, per-app deployable targets, separate config namespaces

See `SKILL.md §5` for the layout decision.

---

## 10. Designing the supervision tree — worked example

Let's design a supervision tree for an e-commerce app from scratch.

### 10.1 Requirements

- Phoenix web interface
- PostgreSQL via Ecto
- PubSub for LiveView broadcasts
- Background jobs via Oban (emails, payment processing)
- Per-user cart state in memory (survives page reloads, not server restarts)
- External payment gateway (Stripe)
- Full-text product search (via a separate ETS cache)

### 10.2 Layered thinking

**Error kernel (must not fail):**
- Repo (DB)
- PubSub
- Telemetry

**Volatile services:**
- Search index (ETS-based, rebuilt from DB on restart)
- Cart processes (per-user, lost on restart — that's acceptable)

**Async workers:**
- Oban for email and payment

**Interface:**
- Phoenix endpoint (starts last)

### 10.3 Drawing the tree

```elixir
defmodule MyApp.Application do
  use Application

  @impl true
  def start(_type, _args) do
    children = [
      # === Error kernel ===
      MyAppWeb.Telemetry,
      MyApp.Repo,
      {Phoenix.PubSub, name: MyApp.PubSub},

      # === Volatile services ===
      {Supervisor,
        name: MyApp.DomainSupervisor,
        strategy: :rest_for_one,
        children: [
          MyApp.Catalog.SearchIndex,              # Rebuilt from DB on restart
          MyApp.Catalog.IndexUpdater              # Listens to PubSub for product changes
        ]},

      # === Per-user cart processes (transient) ===
      {Supervisor,
        name: MyApp.CartSupervisor,
        strategy: :one_for_all,
        children: [
          {Registry, keys: :unique, name: MyApp.CartRegistry},
          {DynamicSupervisor, name: MyApp.CartDynSup, strategy: :one_for_one}
        ]},

      # === Background jobs ===
      {Oban, Application.fetch_env!(:my_app, Oban)},

      # === Interface (LAST — don't accept traffic until above is ready) ===
      MyAppWeb.Endpoint
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: MyApp.Supervisor)
  end
end
```

### 10.4 Why each choice

- **`:one_for_one` at top**: error kernel, domain supervisor, cart supervisor, Oban, endpoint are mostly independent. If the endpoint crashes, we don't want the DB to restart.
- **`DomainSupervisor` is `:rest_for_one`**: `IndexUpdater` depends on `SearchIndex` (it subscribes to updates and writes to the ETS table owned by SearchIndex). If SearchIndex crashes, IndexUpdater must restart too.
- **`CartSupervisor` is `:one_for_all`**: Registry and DynamicSupervisor are tightly coupled — if Registry dies, carts can't re-register, so rebuild both.
- **Oban starts after PubSub**: Oban uses PubSub for cross-node coordination, so PubSub must exist first.
- **Endpoint LAST**: don't accept HTTP traffic until everything else is ready. Otherwise you'll serve errors during startup.

### 10.5 Failure scenarios — verify the design

Walk through "what if X crashes":

- **Repo crashes** → `max_restarts` eventually trips → app exits → orchestrator restarts. Correct behavior for total DB failure.
- **PubSub crashes** → only PubSub restarts (it's `:one_for_one` at top). But subscribers may have lost subscriptions. Acceptable for transient failures; consider `:rest_for_one` if subscription consistency is critical.
- **SearchIndex crashes** → SearchIndex restarts, and IndexUpdater restarts with it (`:rest_for_one`). Fresh index gets rebuilt from DB on startup.
- **One cart crashes** → only that cart is terminated (DynamicSupervisor + `:one_for_one`). Other users unaffected. User's cart state is lost — they need to re-add items. Acceptable.
- **CartRegistry crashes** → all carts + registry restart together (`:one_for_all`). Existing carts are gone. Acceptable.
- **Endpoint crashes** → only endpoint restarts. Traffic briefly rejected; DB and workers continue.
- **Oban crashes** → Oban restarts; jobs were persisted to DB so no loss.

**Every failure scenario is handled.** The design is ready.

---

## 11. Common mistakes

### 11.1 Wrong strategy for Registry + DynamicSupervisor

```elixir
# BAD — Registry + DynamicSupervisor under :one_for_one
# If Registry crashes, DynSup's children can't re-register → orphaned
children = [
  {Registry, keys: :unique, name: MyApp.Registry},
  {DynamicSupervisor, name: MyApp.DynSup}
]
Supervisor.init(children, strategy: :one_for_one)   # WRONG

# GOOD — :one_for_all (or encapsulated in a sub-supervisor)
Supervisor.init(children, strategy: :one_for_all)
```

### 11.2 Unsupervised long-running processes

```elixir
# BAD — spawn leaks; crash is silent
spawn(fn -> expensive_background_work() end)

# GOOD — supervised Task
Task.Supervisor.start_child(MyApp.TaskSupervisor, fn ->
  expensive_background_work()
end)
```

### 11.3 Endpoint before dependencies

```elixir
# BAD — endpoint starts first; early HTTP requests hit a broken system
children = [
  MyAppWeb.Endpoint,                    # Serving traffic immediately
  MyApp.Repo,                            # But DB isn't ready yet
  # ...
]

# GOOD — endpoint last
children = [
  MyApp.Repo,
  # ... all dependencies ...
  MyAppWeb.Endpoint
]
```

### 11.4 Business logic in GenServer callbacks

```elixir
# BAD — pricing logic inside handle_call
def handle_call({:apply_discount, code}, _from, state) do
  rate = case code do
    "SAVE10" -> Decimal.new("0.10")
    # ... more business rules ...
  end
  new_total = Decimal.mult(state.total, Decimal.sub(1, rate))
  {:reply, {:ok, new_total}, %{state | total: new_total}}
end

# GOOD — pure module owns the rule; GenServer delegates
def handle_call({:apply_discount, code}, _from, state) do
  new_total = MyApp.Pricing.apply_discount(state.total, code)
  {:reply, {:ok, new_total}, %{state | total: new_total}}
end
```

### 11.5 Stateful process without recovery strategy

```elixir
# BAD — state lives only in process memory; crash = total loss
defmodule MyApp.UserSession do
  use GenServer
  def init(_), do: {:ok, %{items: [], cart: %{}, history: []}}
  # No terminate, no periodic persistence, no snapshot
end

# GOOD — at least document the strategy
defmodule MyApp.UserSession do
  use GenServer
  @moduledoc """
  Per-user session state. Ephemeral — lost on crash.
  Recovery: user must re-add items. Documented as acceptable in product spec.
  """
  def init(_), do: {:ok, %{items: [], cart: %{}}}
end
```

### 11.6 Per-entity processes for ephemeral lookups

```elixir
# BAD — one process per product (10K products = 10K processes for no reason)
for product <- products do
  DynamicSupervisor.start_child(ProductSupervisor, {ProductServer, product})
end

# GOOD — products are data, not processes. Read from DB / cache.
def get_product(id), do: Repo.get(Product, id)
```

### 11.7 Over-supervising

```elixir
# BAD — supervisor for a single GenServer with no specific strategy need
children = [
  {Supervisor, name: MyApp.WrapperSup, strategy: :one_for_one,
    children: [MyApp.SingleWorker]}
]

# GOOD — MyApp.SingleWorker directly under the parent supervisor
children = [MyApp.SingleWorker]
```

Don't wrap a single child in a supervisor unless you need specific restart semantics.

---

## 12. Cross-references

### Within this skill

- `SKILL.md §8` — supervision strategy summary and decision tables
- `SKILL.md §9` — process construct decision (GenServer vs Task vs Agent)
- [architecture-patterns.md](architecture-patterns.md) — how architectural styles map to process topologies
- [otp-design.md](otp-design.md) — deep OTP construct decisions
- [integration-patterns.md](integration-patterns.md) — GenStage, Broadway, Oban supervision
- [growing-evolution.md](growing-evolution.md) — how the supervision tree evolves at each stage

### In other skills

- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9 — OTP callback templates, `handle_call`/`cast`/`info` patterns
- `../elixir/otp-reference.md` — deep OTP reference (callback signatures, ETS operations, :sys tracing)
- `../elixir/otp-examples.md` — worked examples (rate limiter, cache, circuit breaker, worker pool)
- `../elixir/otp-advanced.md` — GenStage, Flow, Broadway, hot code upgrades

---

**End of process-topology.md.** This subskill is for planning-mode supervision design. For callback code templates, see [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9. For the broader OTP primitive decision, see [otp-design.md](otp-design.md).
