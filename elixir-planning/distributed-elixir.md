# Distributed Elixir — Planning Deep Reference

Phase-focused deep reference for **designing multi-node Elixir systems**. Covers the architectural decisions that come with distribution: node connection patterns, cross-node communication, distributed registries, consistency choices, partition handling, and the anti-patterns that sink most first distribution attempts.

**When to load this:** when you're considering multi-node, clustering, or cross-region deployment. Before you flip `Node.connect/1`.

**For implementation templates** (how to write the `:erpc` call, configure `libcluster`, use `Horde.Registry`), see `../elixir-implementing/otp-callbacks.md` and the implementing networking subskill.

---

## 1. Default to single node

**Most Elixir apps don't need distribution.** The BEAM scales well on a single machine — one node handles ~1M WebSocket connections, ~100K concurrent requests, and gigabytes of in-memory state before the hardware is the bottleneck.

**Before going multi-node, exhaust single-node options:**

| Problem | Single-node solution | Distribute only when… |
|---|---|---|
| More throughput | `Task.async_stream`, `Flow`, more cores | Single machine maxed out |
| High availability | Supervisor restarts, blue/green deploys, health checks | Need zero-downtime deploys across regions |
| Background job capacity | Oban (shares PostgreSQL) | CPU-heavy work exceeds one node |
| WebSocket scale | Single node handles ~1M connections | More concurrent connections than one machine |
| Cache | ETS + TTL | Data must be near users geographically |
| Write throughput | Single node + async writes + Oban | DB write throughput requires sharding |

**Cost of distribution** (budget this before opting in):

- Network partitions → split-brain → eventual consistency.
- Every cross-node message is a potential timeout.
- Debugging is harder (logs split across nodes, clock skew).
- Deployment complexity (service discovery, rolling deploys, version skew).
- CAP theorem applies — you'll pick two of consistency / availability / partition tolerance.

**Rule:** if single-node works, ship single-node. Revisit when traffic or topology forces the issue.

---

## 2. What changes when you go multi-node

The actor model's **location transparency** means `send(pid, msg)` and `GenServer.call(pid, ...)` work across nodes — but the semantics gain failure modes.

| Single-node assumption | Distributed reality |
|---|---|
| Function/process calls always reach the target | Network can partition, delay, reorder |
| Process state is on the same machine | May be on another node that just became unreachable |
| PubSub is instant and reliable | Messages may be delayed, duplicated (with retry), or lost (on partition) |
| ETS is shared across the app | ETS is **local to each node** |
| Registry finds processes instantly | Need a distributed registry (`:global`, Horde, Syn, `:pg`) |
| One supervision tree | One tree per node; cross-node coordination is app-level |
| Clock / monotonic time is consistent | Nodes may clock-skew by seconds |
| `GenServer.call` timeout is a local concern | Timeout may mean "call succeeded but reply lost" |

**Failure-mode mental model:** every cross-node operation can (1) succeed, (2) fail cleanly, or (3) **fail ambiguously** — you don't know if the other side acted. Design for ambiguous failure by making operations idempotent.

---

## 3. Node connection topology

### Full mesh (default)

BEAM's default — every node connects to every other. When node A connects to B, A inherits all of B's connections.

```elixir
Node.connect(:"worker2@host2")
# After this call, both nodes see each other AND inherit each other's existing connections.
```

**Pros:** any node can call any other directly.
**Cons:** O(n²) connections. Becomes painful past ~40 nodes.

### Hidden nodes

A "hidden" node doesn't auto-connect to other nodes in a mesh. Useful for:
- Admin / observer nodes that shouldn't be load-balanced onto.
- Remote shells (`iex --remsh`) that shouldn't join the cluster.

```sh
iex --name admin@host --hidden --cookie ... --remsh app@host
```

### Partitioned mesh (via tags)

`libcluster`'s `Cluster.Strategy.Kubernetes` and similar can create topology groups — only nodes with matching labels auto-connect. Useful for geographic regions or tenant isolation.

### Decision

| Scale | Topology |
|---|---|
| 2-10 nodes | Full mesh — simplest |
| 10-40 nodes | Full mesh still OK |
| 40-100 nodes | Partitioned mesh OR one node does aggregation |
| 100+ nodes | Don't use BEAM distribution for this; use a message bus (NATS, Kafka) or HTTP APIs between clusters |

**BEAM distribution is a LAN-era design.** It assumes reliable low-latency networks. For cross-region or internet-scale, route through HTTP/gRPC/message queues instead.

---

## 4. Cross-node communication mechanisms

### `:erpc` — preferred synchronous call (OTP 23+)

The modern replacement for `:rpc`. Better error handling, proper propagation of exits.

```elixir
case :erpc.call(:"worker@host", MyApp.Heavy, :compute, [data], 30_000) do
  result -> {:ok, result}
catch
  :exit, reason -> {:error, reason}
end
```

**Use when:** you need the result; the call is idempotent; timeout is acceptable.

### `:rpc` — legacy, avoid for new code

Older Erlang API. Still works but `:erpc` is strictly better.

### `send(pid, msg)` — fire-and-forget across nodes

Works, but **silently drops the message** on partition. Use only for hints (metrics, logs) where loss is OK.

### `GenServer.call({Name, node}, ...)` — remote named call

```elixir
try do
  GenServer.call({MyWorker, :"remote@host"}, :work, 10_000)
catch
  :exit, {:noproc, _} -> {:error, :not_running}
  :exit, {{:nodedown, _}, _} -> {:error, :node_down}
  :exit, {:timeout, _} -> {:error, :timeout}
end
```

**Always wrap with `catch :exit`** — remote calls crash the caller by default on any cross-node failure.

### `Phoenix.PubSub` — auto-distributes via `:pg`

In a connected cluster, `Phoenix.PubSub.broadcast/3` fans out to subscribers on all nodes. Under partitions, each partition keeps working in isolation; messages don't cross the split.

```elixir
# All subscribers on all connected nodes receive this
Phoenix.PubSub.broadcast(MyApp.PubSub, "events", {:update, payload})
```

**Distribution semantics:** best-effort. Subscribers in a disconnected partition get nothing until the partition heals (and even then, history is not replayed).

### `:pg` — distributed process groups

OTP 23+ built-in. Eventually consistent across connected nodes. Used by Phoenix PubSub under the hood.

```elixir
:pg.join(:my_scope, :workers, self())
:pg.get_members(:my_scope, :workers)     # pids from ALL connected nodes
```

**Use when:** you need to broadcast to "all instances of role X" without a single coordinator.

### External message bus (Kafka, RabbitMQ, NATS)

When BEAM distribution is too fragile — across regions, or for cross-service messaging — use an external broker. Broadway has producers for all major brokers.

**Decision:**

| Need | Use |
|---|---|
| Sync call, need result, small cluster | `:erpc.call/5` |
| Fire-and-forget within cluster | `Phoenix.PubSub.broadcast/3` |
| Broadcast to role-based subscribers | `:pg` + `Phoenix.PubSub` |
| Persistent, cross-region, cross-service | External broker (Kafka, RabbitMQ) via Broadway |
| Request/reply across the internet | HTTP / gRPC — BEAM distribution is LAN-only |

---

## 5. Distributed registries — finding processes across nodes

Need: given a key (user_id, session_id, game_id), find the process that owns it, regardless of which node it's on.

| Option | Consistency | Throughput | Use when |
|---|---|---|---|
| `:global` | Strong (global lock) | Low (~100s/sec) | Rare one-off registrations (coordinator election) |
| `Registry` (local only) | N/A | High | Single node — don't use for distribution |
| `:pg` | Eventual | High | Fan-out pub-sub style; many processes per key |
| **Horde.Registry** | Eventual (CRDT) | High | Per-entity registrations; survives node failure |
| **Syn** | Eventual (gossip) | High | Similar to Horde; different trade-offs |

### `:global` — strong but slow

```elixir
:global.register_name({:coord, :billing}, self())
case :global.whereis_name({:coord, :billing}) do
  :undefined -> :not_running
  pid -> GenServer.call(pid, :status)
end
```

Uses a **global lock** during registration. Under high registration churn, becomes a bottleneck and can deadlock during netsplits. Suitable for a handful of singletons (leader election), not per-entity registration.

### Horde — CRDT-based, eventually consistent

```elixir
# Supervision tree
{Horde.Registry, name: MyApp.DistRegistry, keys: :unique}

# Register from any node
Horde.Registry.register(MyApp.DistRegistry, {:user, user_id}, :metadata)

# Lookup from any node
[{pid, _meta}] = Horde.Registry.lookup(MyApp.DistRegistry, {:user, user_id})
```

CRDTs guarantee convergence after partitions heal — different nodes may briefly see different state but all eventually agree.

**Combine with `Horde.DynamicSupervisor`** to get "one process per entity across the cluster" — when a node dies, other nodes take over its processes.

### Decision

| Scenario | Use |
|---|---|
| Leader election (1-of-N singleton) | `:global` |
| Per-entity process across cluster, fault-tolerant | `Horde.Registry` + `Horde.DynamicSupervisor` |
| Role-based broadcast | `:pg` |
| Service discovery in K8s | K8s service + `libcluster` strategy |

---

## 6. State distribution patterns

### Owner-based (single authoritative node)

One node owns each entity. Register it in a distributed registry. Other nodes route requests to the owner.

```
[Node A]                   [Node B]
 ┌──────────┐              ┌──────────┐
 │ User 42  │◄─────────────│ route    │
 │ (owner)  │              │ request  │
 └──────────┘              └──────────┘
```

**Pros:** single source of truth; no merge logic.
**Cons:** owner crash → brief unavailability until re-registered; one node handles all traffic for that entity.

**Use when:** state is mutable, serialization matters (game state, chat room).

### Replicated (state converges via CRDT)

Every node has a copy. Updates propagate asynchronously. Conflicts resolve via merge function.

Libraries: `Horde`, `DeltaCrdt`.

**Pros:** any node can read/write; survives partitions.
**Cons:** eventual consistency; merge semantics must match domain.

**Use when:** state is "last writer wins" OK, or semilattice / counter / set operations apply.

### Sharded (consistent hashing)

Partition the key space across nodes: `node = hash(key) mod N`. Each node owns a slice.

**Pros:** scales linearly; predictable data location.
**Cons:** rebalancing during node add/remove is non-trivial.

**Use when:** large working set that doesn't fit on one node; moderate write volume.

### External store (ownership out of BEAM)

Use PostgreSQL, Redis, or a distributed store as the truth. Nodes are stateless workers.

**Pros:** simplest to reason about; well-understood consistency (Postgres).
**Cons:** DB becomes the bottleneck; every read is a network hop.

**Use when:** the default — most apps fall here.

### Decision table

| Situation | Use |
|---|---|
| State lives in DB anyway | **External store** (Postgres / Redis) |
| In-memory per-entity with occasional crash | **Owner-based** with Horde |
| Counters, sets, "last write wins" OK | **Replicated CRDT** |
| Large cache that exceeds one node | **Sharded** consistent hashing |
| Session data, per-tenant cache | **Local ETS** per node, sticky routing |

---

## 7. Partition handling — split brain

**Netsplit scenario:** a connection drops; each side sees the other as "down". Both continue operating independently. When the connection heals, state may have diverged.

### Detection

```elixir
:net_kernel.monitor_nodes(true)
# You'll receive:
#   {:nodeup, node}
#   {:nodedown, node}
```

### Strategies

1. **Last-writer-wins (LWW)** — simplest; may lose writes. Use for caches, metrics, ephemeral state.
2. **Vector clocks** — attach `{node, counter}` tuples; detect concurrent writes. Use when you can handle conflict resolution at the app layer.
3. **CRDT** — structure the data so merges are commutative/associative/idempotent. Horde does this automatically for its registry.
4. **Primary / secondary** — one partition is "authoritative," the other rejects writes. Requires consensus (Raft, external coordination).
5. **Application-layer consensus** — use Postgres / etcd / Consul as the truth; BEAM nodes are stateless.

### Rule of thumb

**Partition-tolerance in BEAM distribution is LIMITED by design.** The BEAM is optimized for LAN reliability. If you need Raft-like consensus, use a library that explicitly provides it (`:ra` from RabbitMQ, or externalize via etcd).

---

## 8. Cluster formation with `libcluster`

`libcluster` handles the "how do nodes find each other" problem.

### Strategies (by environment)

| Environment | Strategy |
|---|---|
| Dev / local | `Cluster.Strategy.Epmd` (manual list of node names) |
| Kubernetes | `Cluster.Strategy.Kubernetes.DNS` or `Cluster.Strategy.Kubernetes` |
| AWS (ECS, EC2 w/ tags) | `Cluster.Strategy.Gossip` or community adapter |
| Fly.io | `Cluster.Strategy.DNSPoll` against `fly-app.internal` |
| Single-region K8s | `Kubernetes.DNS` |
| Multi-region | Do NOT use BEAM distribution — external broker |

### Typical K8s config

```elixir
# config/runtime.exs
if config_env() == :prod do
  config :libcluster,
    topologies: [
      my_app: [
        strategy: Cluster.Strategy.Kubernetes.DNS,
        config: [
          service: "my-app-headless",
          application_name: "my_app",
          polling_interval: 10_000
        ]
      ]
    ]
end
```

Runs as part of the supervision tree:

```elixir
children = [
  {Cluster.Supervisor, [topologies, [name: MyApp.ClusterSupervisor]]},
  # ... rest of app
]
```

---

## 9. Distribution anti-patterns

### 1. Storing cluster-wide mutable state in a single GenServer

```
Node A ──► [GenServer on Node B] ◄── Node C
            (single bottleneck)
```

All reads and writes traverse the network to Node B. Node B dies → cluster is down. Never scales past one node.

**Fix:** CRDT (`Horde.Registry`) or external store.

### 2. Assuming remote calls always succeed

```elixir
# BAD
result = GenServer.call({MyServer, :"remote@host"}, :work)
```

**Fix:** always `catch :exit` for cross-node calls; treat them as "may fail ambiguously".

### 3. Using `:global` for high-frequency registration

`:global` takes a cluster-wide lock. Under load (new registrations per request), the lock becomes the bottleneck and can deadlock during partitions.

**Fix:** use Horde / `:pg` for per-entity registration.

### 4. Silent `cast` across nodes

```elixir
# BAD — across a partition, this disappears with no trace
GenServer.cast({MyLogger, :"remote@host"}, {:log, msg})
```

**Fix:** use `call` with explicit timeout + failure handling. For fan-out logging, use Phoenix.PubSub which handles partition gracefully.

### 5. No netsplit plan

"We'll just connect and hope" is not a plan.

**Fix:** document each piece of state: what happens to it during a split? Does it diverge? Is that OK? Who resolves conflicts?

### 6. Distribution for problems that aren't distribution problems

"We'll cluster 3 nodes to get HA" — but your traffic fits on one node. Now you have 3× the ops complexity and zero additional throughput, and a distributed bug surface.

**Fix:** single node + blue/green deploy + good monitoring often beats a 3-node cluster for "HA".

### 7. BEAM distribution across the internet

Cookies travel in cleartext; latency kills `GenServer.call`; partition-rate is high.

**Fix:** BEAM distribution is for LAN (same data center / K8s cluster). For cross-region, use HTTP / gRPC / message queue.

---

## 10. Observability in a cluster

- **Per-node logs**: aggregate via a log shipper (Fluentd, Vector) to a central store. Correlate with `node()` tag.
- **Telemetry**: each node emits its own metrics. Scrape per-node and aggregate at query time.
- **Distributed tracing**: pass trace context across cross-node calls. OpenTelemetry + `OpentelemetryErlangOtp`.
- **Cluster topology dashboards**: show node up/down events, cluster size, partition events.

**Rule:** never assume "the problem is on node X" without data. In a distributed system, every request touches multiple nodes.

---

## 11. When NOT to use BEAM distribution

| Problem | Better tool |
|---|---|
| Cross-service messaging | HTTP / gRPC / message queue |
| Cross-region replication | Database replication + stateless app nodes |
| Background job processing | Oban (works across a stateless fleet via shared DB) |
| Event streaming | Kafka / NATS / Pub/Sub |
| Cross-language services | HTTP / gRPC — BEAM distribution is Erlang-only |
| Uncontrolled client counts | WebSockets are fine on a single beefy node |

**BEAM distribution shines at:** tightly-coupled worker clusters, in-memory coordination among trusted nodes, distributed state for a single product.

---

## 12. Decision framework — should you distribute?

Answer yes to at least two:

1. Single-node CPU / memory / IO is genuinely saturated.
2. You need zero-downtime rolling deploys that survive a single node loss.
3. You need geographic distribution (users in multiple regions, data locality matters).
4. Your state naturally partitions (sharded entities) and doesn't fit on one node.
5. You need HA for persistent in-memory state (game state, real-time presence).

**If fewer than two:** you probably don't need distribution yet. Revisit in 6 months.

---

## Cross-References

- **Implementation templates** (`:erpc` call, libcluster config, Horde usage): `../elixir-implementing/otp-callbacks.md`
- **Integration patterns inside a single node**: `./integration-patterns.md`
- **Growing architecture — when distribution becomes justified**: `./growing-evolution.md`
- **Actor model and message semantics**: `./process-topology.md` §0
- **Security in distributed systems** (cookie, TLS dist): `../elixir-reviewing/security-audit-deep.md`
