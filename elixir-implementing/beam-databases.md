# BEAM-native Databases — Mnesia & Khepri Implementation Templates

Phase-focused on **writing** code against the two BEAM-native persistent stores. Covers table/tree setup, transactional and dirty APIs, subscriptions, schema evolution, and boot-ordering against the supervision tree.

**For architectural choices** (Mnesia vs Khepri vs Postgres, partition behaviour, ownership implications), see `../elixir-planning/data-ownership-deep.md#12-beam-native-data-stores--mnesia-and-khepri` and `../elixir-planning/distributed-elixir.md` §7.

---

## Rules for Writing Mnesia / Khepri Code

1. **ALWAYS wrap store access in a context module.** Controllers, LiveViews, workers don't call `:mnesia` or `:khepri` directly — they call `MyApp.Sessions.get/1`. Same rule as Ecto.
2. **ALWAYS do writes inside a transaction** (`:mnesia.transaction/1`, `:khepri.transaction/1`) unless you have named the specific reason a dirty op is safe. "It's faster" is not a reason.
3. **NEVER use `:mnesia.dirty_*` in any code path where losing the write on a netsplit is not explicitly acceptable.** Dirty ops bypass both locks and the replication protocol.
4. **ALWAYS subscribe to `:mnesia.subscribe(:system)`** in a supervised process and alert on `:inconsistent_database`, `:mnesia_down`, and `:mnesia_overload`. Silent split-brain is the default otherwise.
5. **NEVER start Mnesia or Khepri from `Application.start/2` without a defined peer-discovery step.** Two nodes booting in parallel without seeing each other form two independent clusters that will not merge.
6. **ALWAYS version your schema in code.** There is no `priv/repo/migrations` for these stores — the owning context's boot logic is the migration system.
7. **NEVER mix Mnesia/Khepri and Ecto inside one logical transaction.** There is no cross-store transaction; you will get partial writes. Pick one store per aggregate.
8. **ALWAYS return plain Elixir terms from context functions** — never raw Mnesia tuples (`{Table, key, val, ...}`) or Khepri path tuples. Convert at the context boundary.
9. **NEVER call `:mnesia.transform_table/3` on a large table during normal operations.** It takes a table-wide write lock and rewrites every row. Run it during a planned window with the cluster at reduced load.
10. **ALWAYS size Khepri clusters with odd node counts ≥3.** A 2-node cluster blocks on any single failure. A 1-node Khepri is just ETS with extra ceremony.

---

## Mnesia — the minimum viable setup

### Table declaration

Mnesia has no schema DSL. A table is declared at runtime by a call with its attribute list, access mode, and replica placement.

```elixir
defmodule MyApp.Sessions.Mnesia do
  @table :sessions

  def ensure_table!(nodes \\ [node()]) do
    :mnesia.create_schema(nodes)   # idempotent — returns {:error, {_, {:already_exists, _}}} if already set up
    :mnesia.start()

    case :mnesia.create_table(@table,
           attributes: [:id, :user_id, :expires_at, :data],
           type: :set,
           disc_copies: nodes,
           index: [:user_id]
         ) do
      {:atomic, :ok} -> :ok
      {:aborted, {:already_exists, @table}} -> :ok
    end

    :ok = :mnesia.wait_for_tables([@table], 10_000)
  end
end
```

**Key options:**

- `attributes:` — the tuple shape. Row 1 is always the key. Order matters; reordering is a schema migration.
- `type:` — `:set` (unique key), `:ordered_set` (key-sorted, supports `:mnesia.first`/`:next`), `:bag` (duplicate keys allowed).
- `disc_copies:` / `ram_copies:` / `disc_only_copies:` — replica placement **per node**. Different nodes can hold the same table at different storage tiers.
- `index:` — secondary indexes on non-key fields. Each index adds write cost.
- `:mnesia.wait_for_tables/2` — blocks boot until the local replica has loaded. Without it, early reads return `{:aborted, {:no_exists, table}}`.

### Transactions

```elixir
def put(id, user_id, data, ttl_seconds) do
  expires_at = System.system_time(:second) + ttl_seconds
  record = {@table, id, user_id, expires_at, data}

  case :mnesia.transaction(fn -> :mnesia.write(record) end) do
    {:atomic, :ok} -> :ok
    {:aborted, reason} -> {:error, reason}
  end
end

def get(id) do
  case :mnesia.transaction(fn -> :mnesia.read({@table, id}) end) do
    {:atomic, []} -> :error
    {:atomic, [{@table, ^id, user_id, expires_at, data}]} ->
      {:ok, %{id: id, user_id: user_id, expires_at: expires_at, data: data}}
  end
end
```

**Inside a transaction fun:**

- `:mnesia.read({Table, Key})` / `:mnesia.write(Record)` — locked reads/writes. Record is the full tuple.
- `:mnesia.match_object({Table, :_, user_id, :_, :_})` — match-spec-style query. `:_` is a wildcard.
- `:mnesia.select(Table, MatchSpec)` — more expressive; use `:ets.fun2ms/1` to build the match spec from a function.
- `:mnesia.index_read(Table, Value, IndexField)` — fast lookup via a declared index.
- Transactions retry on lock conflict; make the fun idempotent (don't send messages, don't log, don't do IO).

### Dirty operations (use sparingly)

```elixir
:mnesia.dirty_read({:sessions, id})        # no locks, no tx
:mnesia.dirty_write({:sessions, id, ...})  # no locks, no replication coordination
```

Skip the transaction layer entirely. Useful for read-only hot paths where a millisecond matters. **Writes via dirty ops are not safely replicated** — on partition heal they may be silently dropped. Never use for data you can't lose.

### Subscriptions — see the cluster state

```elixir
defmodule MyApp.Mnesia.Watcher do
  use GenServer

  def start_link(_), do: GenServer.start_link(__MODULE__, nil, name: __MODULE__)

  @impl true
  def init(_) do
    {:ok, _} = :mnesia.subscribe(:system)
    {:ok, %{}}
  end

  @impl true
  def handle_info({:mnesia_system_event, {:inconsistent_database, context, node}}, state) do
    Logger.error("Mnesia inconsistent_database: #{inspect(context)} on #{node}")
    MyApp.Alerts.page("mnesia_split_brain", %{peer: node, context: context})
    {:noreply, state}
  end

  def handle_info({:mnesia_system_event, event}, state) do
    Logger.warning("Mnesia event: #{inspect(event)}")
    {:noreply, state}
  end
end
```

The events you must not silently drop: `:inconsistent_database` (split-brain heal), `:mnesia_down` (peer lost), `:mnesia_overload` (dump queue backing up).

### Joining a cluster

```elixir
def join_cluster(peer) when is_atom(peer) do
  true = Node.connect(peer)
  :mnesia.start()
  case :mnesia.change_config(:extra_db_nodes, [peer]) do
    {:ok, [_]} -> copy_tables_to_self()
    {:ok, []} -> {:error, :peer_has_no_mnesia}
    err -> err
  end
end

defp copy_tables_to_self do
  Enum.each(:mnesia.system_info(:tables), fn table ->
    case :mnesia.add_table_copy(table, node(), :disc_copies) do
      {:atomic, :ok} -> :ok
      {:aborted, {:already_exists, _, _}} -> :ok
    end
  end)
end
```

**The boot dance:** node A creates the schema and tables. Node B starts Mnesia *without* a schema, connects to A, calls `change_config(:extra_db_nodes, [A])`, then asks for local copies of the tables. Get the order wrong and you create two disjoint clusters.

### Schema evolution

```elixir
# Add a field — :data → :data + :ip
def migrate_add_ip_field do
  :mnesia.transform_table(
    :sessions,
    fn {:sessions, id, user_id, expires_at, data} ->
      {:sessions, id, user_id, expires_at, data, nil}  # :ip initialised to nil
    end,
    [:id, :user_id, :expires_at, :data, :ip]
  )
end
```

**Cost:** `transform_table/3` takes a write lock on the table cluster-wide and rewrites every row. For a large table this is a cluster-wide stall. For anything bigger than "small" — create a new table, dual-write, backfill, switch reads, drop the old one.

---

## Khepri — the minimum viable setup

### Starting a store

```elixir
# mix.exs:  {:khepri, "~> 0.16"}

defmodule MyApp.Config.Store do
  @store :myapp_config

  def start_link(_) do
    :khepri.start(
      ~c"/var/lib/myapp/khepri/#{@store}",
      @store
    )
  end

  def child_spec(arg), do: %{id: @store, start: {__MODULE__, :start_link, [arg]}, type: :worker}
end
```

Khepri stores data as a tree of arbitrary Erlang terms. Paths are lists of atoms/binaries: `[:app, :config, :rate_limits]`.

### Put / get / delete

```elixir
def put(path, value) when is_list(path) do
  :khepri.put(@store, path, value)
end

def get(path) do
  case :khepri.get(@store, path) do
    {:ok, value} -> {:ok, value}
    {:error, :node_not_found} -> :error
  end
end

def delete(path), do: :khepri.delete(@store, path)
```

**Path forms:** literal atoms (`[:app, :limits]`), `:khepri_path.if_name_matches/2` predicates, and `?KHEPRI_WILDCARD_STAR` (`:*`) for "any node at this level."

### Transactions

```elixir
def increment_counter(counter_name) do
  :khepri.transaction(@store, fn ->
    path = [:counters, counter_name]
    current = case :khepri_tx.get(path) do
      {:ok, n} -> n
      {:error, :node_not_found} -> 0
    end
    :khepri_tx.put(path, current + 1)
    current + 1
  end)
end
```

**Inside a `:khepri.transaction/2` fun:**

- Use `:khepri_tx` (not `:khepri`) for all operations — the tx variants go through the Raft log.
- The fun is **replayed on every node** as part of the Raft log, so it must be **pure and deterministic**. No time, no `self()`, no message sends, no IO, no random numbers.
- Violating determinism is not a warning — it corrupts the cluster. Different nodes end up in different states.

### Reads with consistency options

```elixir
:khepri.get(@store, path, %{favor: :consistency})  # full linearizable — round trip to leader
:khepri.get(@store, path, %{favor: :low_latency}) # local replica, may be slightly stale
```

Default is consistency-favoring. Relax only for read paths where stale-by-milliseconds is fine (dashboards, cached config that also has its own TTL).

### Triggers — reacting to tree changes

```elixir
:khepri.register_trigger(
  @store,
  :on_limit_change,
  [:app, :limits, :*],
  {:khepri_evf, :tree, %{on_actions: [:create, :update, :delete]}},
  {MyApp.Config.Reactor, :handle_change, []}
)
```

The trigger MF/A runs on the leader after the write is committed. Use for "when X changes, push a notification" — keep the callback fast; it blocks the log applier.

### Projections — derived views for faster reads

```elixir
:khepri.register_projection(
  @store,
  [:app, :limits, :*],
  :khepri_projection.new(:active_limits, fn path, value -> {List.last(path), value} end)
)

# Later: read from an ETS-backed projection (microseconds, no Raft round trip)
:ets.lookup(:active_limits, :requests_per_second)
```

Projections materialise part of the tree into an ETS table on every node. Great for read-heavy config where you want the Raft durability on writes but local-ETS speed on reads.

---

## Boot ordering — where these live in the supervision tree

Both stores need to start **before** any supervised process that reads from them, but **after** `libcluster` has had a chance to discover peers. The usual shape:

```elixir
defmodule MyApp.Application do
  use Application

  def start(_type, _args) do
    children = [
      # 1. Cluster formation first — so peers are visible before we try to replicate
      {Cluster.Supervisor, [topologies(), [name: MyApp.ClusterSupervisor]]},

      # 2. Wait for at least one peer (only in prod with >1 replica)
      MyApp.ClusterReady,

      # 3. BEAM-native store starts with peers known
      MyApp.Mnesia.Bootstrap,       # or MyApp.Config.Store for Khepri
      MyApp.Mnesia.Watcher,         # subscribe to :system events

      # 4. Ecto repo (independent of BEAM cluster)
      MyApp.Repo,

      # 5. App processes that depend on any of the above
      MyApp.Sessions.Supervisor,
      MyApp.Config.Supervisor,
      MyAppWeb.Endpoint
    ]

    Supervisor.start_link(children, strategy: :one_for_one, name: MyApp.Supervisor)
  end
end
```

**`MyApp.ClusterReady`** is a small GenServer that blocks `init/1` until `Node.list/0` is non-empty or a timeout elapses. This avoids the "two nodes boot simultaneously, each forms a cluster of one" failure.

```elixir
defmodule MyApp.ClusterReady do
  use GenServer

  def start_link(_), do: GenServer.start_link(__MODULE__, nil, name: __MODULE__)

  @impl true
  def init(_) do
    if Application.get_env(:my_app, :cluster_required?, false) do
      wait_for_peer(30_000)
    end
    :ignore
  end

  defp wait_for_peer(budget_ms) when budget_ms <= 0, do: :timeout
  defp wait_for_peer(budget_ms) do
    case Node.list() do
      [] -> Process.sleep(500); wait_for_peer(budget_ms - 500)
      [_ | _] -> :ok
    end
  end
end
```

**Why this matters:** Mnesia's `extra_db_nodes` and Khepri's cluster membership both need the BEAM cluster to be formed first. If you let the store start in isolation, Mnesia creates a standalone schema that will not later merge with peers without manual intervention, and Khepri creates a one-member Raft cluster that needs explicit membership changes to grow.

---

## Anti-patterns — quick reference

### 1. Long work inside `:mnesia.transaction/1`

```elixir
# BAD — transaction holds locks during HTTP call
:mnesia.transaction(fn ->
  user = :mnesia.read({Users, id})
  notify_external_service(user)   # ← network IO under a lock
  :mnesia.write(...)
end)

# GOOD — read, commit, then do IO
{:atomic, user} = :mnesia.transaction(fn -> :mnesia.read({Users, id}) end)
notify_external_service(user)
```

Transactions retry on conflict. A long transaction multiplies its own retry cost and holds locks that block every other writer.

### 2. Non-deterministic Khepri transaction fun

```elixir
# BAD — different nodes see different system_time
:khepri.transaction(@store, fn ->
  :khepri_tx.put([:events, System.system_time()], event)
end)

# GOOD — pass the timestamp in from outside
now = System.system_time()
:khepri.transaction(@store, fn ->
  :khepri_tx.put([:events, now], event)
end)
```

The tx fun runs on every Raft member. `System.system_time/0` returns a different value on each one. The cluster corrupts silently.

### 3. Reading Mnesia from outside a transaction

```elixir
# BAD — race: value can change between these two reads
[{_, _, a}] = :mnesia.dirty_read({Accounts, id1})
[{_, _, b}] = :mnesia.dirty_read({Accounts, id2})
# `a + b` is not a consistent snapshot

# GOOD — one transaction, one snapshot
:mnesia.transaction(fn ->
  [{_, _, a}] = :mnesia.read({Accounts, id1})
  [{_, _, b}] = :mnesia.read({Accounts, id2})
  a + b
end)
```

### 4. Growing the cluster without `extra_db_nodes`

```elixir
# BAD — new node starts with no peer info, forms its own cluster
def start(_, _) do
  :mnesia.start()
  # ... children ...
end

# GOOD — explicit peer list before starting
def start(_, _) do
  peers = discover_peers()
  for p <- peers, do: Node.connect(p)
  :mnesia.start()
  :mnesia.change_config(:extra_db_nodes, peers)
  # ... children ...
end
```

### 5. Exposing raw tuples / paths from the context

```elixir
# BAD — callers now depend on Mnesia's tuple shape
def get_session(id), do: :mnesia.dirty_read({:sessions, id})

# GOOD — shape is an implementation detail
def get_session(id) do
  case :mnesia.transaction(fn -> :mnesia.read({:sessions, id}) end) do
    {:atomic, [{:sessions, ^id, user_id, expires_at, data}]} ->
      {:ok, %Session{id: id, user_id: user_id, expires_at: expires_at, data: data}}
    {:atomic, []} -> :error
  end
end
```

Same principle as "don't return `Ecto.Query` from a context." The store is an implementation detail.

### 6. Logging or dispatching inside a Raft callback

```elixir
# BAD — blocks the Khepri log applier
:khepri.register_trigger(@store, :t, path, evf, {__MODULE__, :on_change, []})

def on_change(_path, _value) do
  Logger.info(...)
  HTTPClient.post("https://webhook", ...)    # ← blocks every write to that path
end

# GOOD — enqueue; do the slow work elsewhere
def on_change(path, value) do
  send(MyApp.Webhook.Worker, {:config_changed, path, value})
  :ok
end
```

Triggers run inline on the leader. A slow trigger is a slow cluster.

### 7. 2-node Khepri cluster

```elixir
# BAD — any single failure blocks writes
# Khepri members: [a@host1, b@host2]
# host1 goes down → b@host2 is minority → writes blocked until host1 returns
```

Raft quorum requires a majority. With 2 members, you need both. Use 1 (trivial, no HA), 3 (tolerates 1 failure), or 5 (tolerates 2). Never 2 or 4.

---

## Cross-References

- **Store choice (Mnesia vs Khepri vs Postgres, ownership, backup story):** `../elixir-planning/data-ownership-deep.md` §12
- **Partition semantics and netsplit strategies:** `../elixir-planning/distributed-elixir.md` §7
- **Supervision tree placement / boot ordering:** `./otp-callbacks.md`, `../elixir-planning/process-topology.md`
- **Reviewing store-access code (split-brain watcher, transaction discipline):** `../elixir-reviewing/anti-patterns-catalog.md` §H
- **Ecto patterns (the default persistent-store path):** `./ecto-patterns.md`
