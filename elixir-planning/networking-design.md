# Networking Design — deep reference

Phase-focused deep reference for designing TCP/UDP servers and clients in Elixir. Planning-level decisions: active vs passive mode, protocol framing strategy, connection supervision, process-per-connection vs pool, backpressure, TLS termination placement, clustering considerations.

The actual `:gen_tcp`/`:gen_udp` call patterns and binary-protocol code lives in [../elixir-implementing/networking-patterns.md](../elixir-implementing/networking-patterns.md) (when written) and `../elixir/networking.md`.

**When to load:** when designing a TCP/UDP server or client, when planning protocol framing for a custom wire format, when choosing between Ranch/Thousand Island/raw `:gen_tcp`, when thinking about TLS topology, or when the current networking architecture is hitting limits (connection count, throughput, latency).

**Related:**
- [architecture-patterns.md](architecture-patterns.md) §4 — hexagonal architecture (put network dependencies behind behaviours)
- [process-topology.md](process-topology.md) §4.2 — process-per-entity (one process per connection)
- [integration-patterns.md](integration-patterns.md) §9 — HTTP client design (this subskill covers RAW TCP/UDP, not HTTP)
- [otp-design.md](otp-design.md) — GenServer / gen_statem for connection state machines
- `../elixir/networking.md` — deep `:gen_tcp`/`:gen_udp` API reference

---

## 1. Rules for networking design (LLM)

1. **ALWAYS decide on active mode first.** `{:active, false}` (manual), `{:active, :once}` (per-message), `{:active, N}` (batched), `{:active, true}` (firehose) — each has a specific fit. Most servers use `:once`.
2. **NEVER use `{:active, true}` on an untrusted connection.** No backpressure; malicious peer can OOM your node.
3. **ALWAYS define the framing protocol explicitly.** Length-prefix, delimiter, fixed-size, or TLV — pick one. Partial reads must be handled.
4. **ALWAYS use Ranch or Thousand Island for TCP servers.** They handle the acceptor pool, connection supervision, and graceful shutdown. Don't reinvent.
5. **ALWAYS supervise connections.** Each connection is a process; that process is supervised. Crash = isolation, not propagation.
6. **NEVER do `:gen_tcp.accept/1` inside a GenServer callback.** It blocks the GenServer. Acceptor lives in its own process (Ranch/Thousand Island handle this).
7. **ALWAYS design for graceful shutdown.** Active connections need a chance to finish in-flight work before the listener closes.
8. **ALWAYS set timeouts at every I/O call.** `:gen_tcp.recv/3` without a timeout blocks forever.
9. **PREFER `:gen_statem` over `GenServer`** for complex connection state (handshake → authenticated → data → closing). GenServer with a big state-case is a smell.
10. **NEVER parse in the network process if parsing is CPU-heavy.** Offload to a worker. The connection process should pull bytes and dispatch.
11. **ALWAYS decide TLS placement before coding.** Terminate at load balancer, in the BEAM, or at a sidecar — each has different implications.
12. **ALWAYS plan for connection accumulation.** What happens at 1K connections? 100K? 1M? Memory/process-count profile differs dramatically.

---

## 2. TCP server architecture

### 2.1 Canonical shape

```
┌──────────────────────────────────────────────────────┐
│ Listener (port bound)                                 │
│   └── Acceptor pool (Ranch/Thousand Island)          │
│       └── When new connection arrives:               │
│           │                                           │
│           ↓                                           │
│           DynamicSupervisor of Connection processes   │
│           ├── Conn 1 (GenServer / :gen_statem)        │
│           ├── Conn 2                                  │
│           ├── Conn 3                                  │
│           └── ...                                     │
└──────────────────────────────────────────────────────┘
```

- **One acceptor pool** (typically N acceptors, where N is about CPU count × 2)
- **One connection process per connection** (isolated state, isolated failure)
- **DynamicSupervisor** for connection processes (automatic cleanup on crash)

### 2.2 Use Ranch or Thousand Island — don't build the acceptor yourself

**Ranch** is a battle-tested Erlang library that handles:
- Acceptor pool
- Connection supervision
- Graceful shutdown
- Protocol upgrades (WebSocket, HTTP/2)

**Thousand Island** is a more modern Elixir alternative with similar design.

```elixir
# Ranch-based TCP server
:ranch.start_listener(
  :my_tcp_listener,
  :ranch_tcp,                # or :ranch_ssl for TLS
  %{
    socket_opts: [port: 4040],
    num_acceptors: 20
  },
  MyApp.ProtocolHandler,     # Your connection-handler module
  []
)
```

**Raw `:gen_tcp.listen/accept/recv`** is fine for learning and tiny apps. For production: use Ranch or Thousand Island.

### 2.3 Connection handler — the protocol module

The connection handler implements the protocol:

```elixir
defmodule MyApp.ProtocolHandler do
  # Ranch calls start_link per connection
  def start_link(ref, transport, opts) do
    pid = :proc_lib.spawn_link(__MODULE__, :init, [ref, transport, opts])
    {:ok, pid}
  end

  def init(ref, transport, _opts) do
    {:ok, socket} = :ranch.handshake(ref)
    :ok = transport.setopts(socket, [{:active, :once}])
    loop(socket, transport, %{buffer: <<>>})
  end

  defp loop(socket, transport, state) do
    receive do
      {:tcp, ^socket, data} ->
        state = handle_data(data, state)
        :ok = transport.setopts(socket, [{:active, :once}])
        loop(socket, transport, state)

      {:tcp_closed, ^socket} ->
        :ok = transport.close(socket)

      {:tcp_error, ^socket, reason} ->
        Logger.warning("TCP error: #{inspect(reason)}")
        :ok = transport.close(socket)
    after
      60_000 ->
        :ok = transport.close(socket)
    end
  end

  # ... handle_data implements framing
end
```

### 2.4 `GenServer` or `:gen_statem` for connection?

**GenServer:**
- Simple protocols (request/response, stateless)
- No clear state transitions
- Easy to implement

**`:gen_statem`:**
- Multi-state protocols (unauthenticated → authenticated → data → closing)
- State-specific message handling
- Cleaner than GenServer with big case-on-state

See [otp-design.md](otp-design.md) §5 for the state machine choice.

---

## 3. Active mode — the critical choice

### 3.1 The four modes

| Mode | Delivery | Backpressure | Use |
|---|---|---|---|
| `{:active, false}` | Manual `:gen_tcp.recv/2,3` — you pull | Full control | Clients, sequential protocols, bidirectional blocking |
| `{:active, :once}` | One `{:tcp, socket, data}` message, then pauses | Per-message (re-arm after each) | **Most production servers.** Safe backpressure |
| `{:active, N}` (N integer) | N messages, then `{:tcp_passive, socket}` | Batched | High throughput (OTP 17+) |
| `{:active, true}` | Unlimited messages, no stopping | **NONE** | Trusted LAN, benchmarks, NEVER untrusted |

### 3.2 Decision — which mode

```
Are you building a client or server?
├── Client, synchronous request/response
│   └── {:active, false} — recv explicitly
├── Client, streaming
│   └── {:active, :once} with loop
├── Server, untrusted peers (internet)
│   └── {:active, :once} — safe backpressure
├── Server, trusted peers (LAN, internal services)
│   └── {:active, N} for batched throughput (start with N=10)
└── Benchmarking / trusted dev
    └── {:active, true}
```

### 3.3 `:once` — re-arm pattern

`{:active, :once}` is the safe default for servers. Must re-arm after each message:

```elixir
def handle_info({:tcp, socket, data}, state) do
  state = process_data(data, state)
  # Re-arm for next message
  :ok = :inet.setopts(socket, [{:active, :once}])
  {:noreply, state}
end

def handle_info({:tcp_closed, _socket}, state), do: {:stop, :normal, state}
def handle_info({:tcp_error, _socket, reason}, state), do: {:stop, reason, state}
```

**If you forget to re-arm, data just stops arriving.** Classic bug.

### 3.4 `{:active, N}` — batched mode

```elixir
# Start with 10 messages in flight
:inet.setopts(socket, [{:active, 10}])

# After 10 messages, you get:
# {:tcp_passive, socket} — re-arm with setopts again
def handle_info({:tcp_passive, socket}, state) do
  :inet.setopts(socket, [{:active, 10}])
  {:noreply, state}
end
```

### 3.5 Active mode + backpressure

Active mode controls socket-level backpressure. If your process can't keep up:

- `{:active, false}` — you don't read; OS buffers fill; TCP window closes; peer slows
- `{:active, :once}` — you re-arm when ready; same effect
- `{:active, N}` — TCP window stays open for N messages; then closes if you don't re-arm
- `{:active, true}` — NO backpressure; mailbox grows unbounded; peer can OOM you

**Rule:** untrusted networks ALWAYS use `:once` or `N`. Never `true`.

---

## 4. Framing — parsing the byte stream

TCP is a byte stream, not a message stream. Your protocol must define how to tell where one message ends and the next begins.

### 4.1 Four framing strategies

| Strategy | Format | Pros | Cons |
|---|---|---|---|
| **Length-prefix** | `<<length::32, data::binary-size(length)>>` | Fast, self-delimiting, no escaping | Length field limits max size |
| **Delimiter** | `data\n` or `data\0` | Human-readable (for text) | Requires escaping delimiter in data |
| **Fixed-size** | Always N bytes | Trivial parsing | Only works for fixed-length messages |
| **TLV (type-length-value)** | `<<type::8, len::16, value::binary-size(len)>>` | Extensible, self-describing | Slightly more code |

### 4.2 Length-prefix (most common for custom protocols)

```elixir
def parse_frames(buffer) do
  case buffer do
    <<length::32-big, rest::binary>> when byte_size(rest) >= length ->
      <<frame::binary-size(length), rest_rest::binary>> = rest
      {[frame], rest_rest}

    <<length::32-big, rest::binary>> ->
      # Partial frame — wait for more bytes
      {[], <<length::32-big, rest::binary>>}

    incomplete ->
      # Not even 4 bytes yet
      {[], incomplete}
  end
end
```

**Must handle partial reads.** TCP can split a single logical message across many `{:tcp, socket, data}` deliveries.

### 4.3 Delimiter-based (for text protocols)

```elixir
def parse_lines(buffer) do
  case String.split(buffer, "\n", parts: 2) do
    [line, rest] -> {[line], rest}
    [incomplete] -> {[], incomplete}
  end
end
```

Repeat to extract multiple frames:

```elixir
def parse_all_lines(buffer, acc \\ []) do
  case parse_lines(buffer) do
    {[line], rest} -> parse_all_lines(rest, [line | acc])
    {[], rest} -> {Enum.reverse(acc), rest}
  end
end
```

### 4.4 Fixed-size

```elixir
@frame_size 128

def parse_frames(buffer) when byte_size(buffer) >= @frame_size do
  <<frame::binary-size(@frame_size), rest::binary>> = buffer
  [frame | parse_frames(rest)]
end
def parse_frames(buffer), do: {[], buffer}  # Or however you want to structure
```

### 4.5 TLV (type-length-value)

Common in binary protocols (RADIUS, SNMP, many IoT protocols):

```elixir
def parse_tlv(<<type::8, length::16, value::binary-size(length), rest::binary>>) do
  {{type, value}, rest}
end
def parse_tlv(incomplete), do: {:incomplete, incomplete}
```

### 4.6 Built-in `:packet` option

For length-prefix framing, `:gen_tcp` can do it for you:

```elixir
:inet.setopts(socket, [packet: 4])
# Now each {:tcp, socket, data} is a complete frame — length prefix stripped
```

Options: `:packet, 1` (1-byte length), `:packet, 2`, `:packet, 4`, `:packet, :line` (line-delimited).

**Use this when possible** — it's faster than Elixir-side parsing and handles partial reads internally.

### 4.7 Buffer management

Always store leftover bytes in state. When new data arrives, concatenate + re-parse.

```elixir
def handle_info({:tcp, socket, data}, %{buffer: buf} = state) do
  {frames, leftover} = parse_frames(buf <> data)
  state = Enum.reduce(frames, state, &process_frame/2)
  :inet.setopts(socket, [{:active, :once}])
  {:noreply, %{state | buffer: leftover}}
end
```

---

## 5. Connection supervision

### 5.1 Each connection is a process

One TCP connection = one Elixir process. Benefits:
- **Isolated failure:** crash kills only that connection
- **Independent state:** no shared mutable state between connections
- **Natural concurrency:** thousands of connections = thousands of lightweight processes

### 5.2 Supervision shape

With Ranch:

```
MyApp.Application (:one_for_one)
├── Repo, PubSub, ...
└── Ranch listener (supervised internally by Ranch)
    └── Acceptor pool (N acceptors)
        └── Connection processes (one per connection)
            ├── Conn 1
            ├── Conn 2
            └── ...
```

Ranch manages the acceptor pool and per-connection supervisor. You just implement the connection handler.

### 5.3 Connection crash behavior

When a connection process crashes:
- Only that connection is terminated
- Other connections unaffected
- New connections still accepted
- Supervisor logs the crash
- Client sees connection close (their next send/recv fails)

Client should reconnect with backoff.

### 5.4 Connection count limits

| Concern | Typical limit |
|---|---|
| OS file descriptors | `ulimit -n` (often 1024 default; raise to 100K+ for servers) |
| BEAM process count | ~1M default (`+P` flag); memory is the real limit |
| Memory per connection | ~10-50KB typical (2.6KB process + socket buffers + state) |
| Port count | OS limit (~65K ephemeral ports on the client side) |

**For 100K connections:** ~5GB of BEAM memory. Plan accordingly.

### 5.5 Graceful shutdown

When the app is shutting down:
1. Stop accepting new connections (close listener)
2. Signal existing connections to finish in-flight work
3. Wait up to a timeout for connections to close
4. Force-close remaining connections

Ranch handles this with proper config:

```elixir
:ranch.start_listener(..., shutdown: 30_000)  # 30s grace period
```

---

## 6. Process-per-connection vs pool

### 6.1 Process-per-connection (default)

One Elixir process per TCP connection. Each process:
- Owns its socket
- Holds its per-connection state
- Parses incoming frames
- Handles application protocol

**This is the Elixir idiom.** Works for 10 connections, works for 1M.

### 6.2 Pool-of-workers (rare)

Share sockets across a pool of worker processes. Used in some DB drivers where connection setup is expensive.

```
Pool (N workers) ←→ N DB connections
         ↓
Application code requests a worker; works; releases it
```

**Use for:**
- Outbound connections with expensive setup (DB connections via Poolboy / DBConnection)
- Very high connection turnover where per-connection processes would be too many

**Don't use for:**
- Inbound server connections (process-per-connection is simpler and scales fine)

### 6.3 Protocol-per-process design

Your connection process can be:

- **Stateless request-response**: simple GenServer; each request is independent
- **Stateful session**: `:gen_statem` with authenticated/data/closing states
- **Streaming**: GenServer with backpressure on consumer side
- **Pub/sub endpoint**: Connection subscribes to Phoenix.PubSub, pushes events downstream

---

## 7. Backpressure at every layer

### 7.1 Three backpressure layers

```
┌──────────────────────────────────────┐
│ Application consumer (your code)     │ ← Layer 3: consume rate
├──────────────────────────────────────┤
│ Connection process mailbox           │ ← Layer 2: mailbox management
├──────────────────────────────────────┤
│ OS TCP receive buffer                │ ← Layer 1: TCP window / socket opts
└──────────────────────────────────────┘
        ↑
        │  peer sending
```

### 7.2 Layer 1 — socket-level (active mode)

Active mode controls TCP read behavior. `{:active, false}` or `{:active, :once}` means the OS buffers fill; TCP window closes; peer stops sending.

### 7.3 Layer 2 — process mailbox

If your connection process pulls messages but doesn't process fast enough, mailbox grows. If you use `{:active, :once}`, you naturally re-arm only when ready → no mailbox growth. If you use `{:active, true}`, mailbox grows until OOM.

### 7.4 Layer 3 — downstream consumer

Connection process often pushes work to downstream (parse → dispatch → DB). If downstream is slower than connection:
- Use GenStage (demand-driven backpressure)
- Use bounded queues (drop overflow or block producer)
- Don't just forward blindly

### 7.5 Outbound send buffer

On the send side, `:gen_tcp.send/2` can block if the OS send buffer is full (peer is slow to receive). Options:
- **`:gen_tcp.send/2` blocks** by default — fine for some cases
- **`{send_timeout, N}` option** — abort after N ms
- **`{send_timeout_close, true}` option** — close socket if send times out
- **Check `:inet.getopts(socket, [:sndbuf])` size**; tune if needed

---

## 8. TLS placement

### 8.1 Three topologies

```
Topology A: TLS at the load balancer
  Client ─(TLS)→ LB ─(plain)→ App (BEAM)
  Pros: offload compute; centralized cert management
  Cons: plain traffic between LB and app

Topology B: TLS in the BEAM
  Client ─(TLS)→ App (BEAM, :ranch_ssl / :ssl)
  Pros: end-to-end TLS
  Cons: BEAM handles crypto (OpenSSL via NIF — still fast)

Topology C: TLS at a sidecar (Envoy, stunnel)
  Client ─(TLS)→ Sidecar ─(plain or TLS)→ App
  Pros: language-agnostic; mature TLS stack; independent deploy
  Cons: extra hop; operational complexity
```

### 8.2 Choose based on

| Factor | Recommendation |
|---|---|
| Have an ELB / nginx in front? | Terminate TLS there (Topology A) |
| Need end-to-end TLS for compliance | Topology B — `:ranch_ssl` |
| Polyglot infra with mTLS everywhere | Topology C — sidecar (Envoy) |
| Small app, no LB | Topology B — `:ranch_ssl` |

### 8.3 `:ranch_ssl` in Elixir

```elixir
:ranch.start_listener(
  :my_tls_listener,
  :ranch_ssl,
  %{
    socket_opts: [
      port: 8443,
      certfile: "/etc/ssl/cert.pem",
      keyfile: "/etc/ssl/key.pem",
      versions: [:"tlsv1.3", :"tlsv1.2"],
      verify: :verify_peer,             # for mTLS
      cacertfile: "/etc/ssl/ca.pem"
    ],
    num_acceptors: 20
  },
  MyApp.ProtocolHandler,
  []
)
```

### 8.4 Certificate rotation

- **LetsEncrypt / ACME**: use `site_encrypt` library or a sidecar; Ranch picks up cert reload via setopts
- **Internal CA**: rotate certs on disk; signal the app to reload (SIGHUP or similar)
- **Short-lived certs**: design for routine rotation (hours, not months)

---

## 9. UDP server architecture

### 9.1 UDP is different

- Connectionless — no accept; just listen for datagrams
- Each datagram is a complete "message" (no framing needed within one datagram)
- But no ordering, no delivery guarantee
- No backpressure at protocol level — OS drops packets when buffer fills

### 9.2 Canonical UDP server shape

```elixir
defmodule MyApp.UDPServer do
  use GenServer

  def start_link(opts), do: GenServer.start_link(__MODULE__, opts, name: __MODULE__)

  @impl true
  def init(opts) do
    port = Keyword.fetch!(opts, :port)
    {:ok, socket} = :gen_udp.open(port, [:binary, active: :once])
    {:ok, %{socket: socket}}
  end

  @impl true
  def handle_info({:udp, socket, ip, port, data}, state) do
    # Dispatch — often to a worker
    Task.Supervisor.start_child(MyApp.UDPWorkers, fn ->
      process_datagram(ip, port, data)
    end)
    :inet.setopts(socket, [{:active, :once}])
    {:noreply, state}
  end
end
```

### 9.3 Single GenServer vs multiple acceptors

Unlike TCP, UDP typically uses **one listening socket** with one receiving process. The process dispatches to workers for processing.

For very high UDP throughput:
- Multiple sockets on the same port (via `SO_REUSEPORT`) with separate listening processes
- OS kernel distributes packets across listeners
- Useful for very high packet rates (>100K/sec)

### 9.4 UDP protocol design

Since UDP has no framing / ordering / delivery:

- **Each packet must be self-contained** (no multi-packet "messages" unless you build reassembly)
- **Include sequence numbers** if ordering matters at your layer
- **Build retry / ACK** at the application layer if delivery matters
- **Keep packets < MTU** (typically ~1400 bytes for safety)

### 9.5 Broadcast / multicast

```elixir
# Broadcast (local network)
{:ok, socket} = :gen_udp.open(0, [:binary, {:broadcast, true}])
:gen_udp.send(socket, {255, 255, 255, 255}, port, data)

# Multicast
{:ok, socket} = :gen_udp.open(port, [:binary, {:add_membership, {{239, 1, 1, 1}, {0, 0, 0, 0}}}])
```

---

## 10. Client design

### 10.1 Client patterns

| Pattern | Shape | When |
|---|---|---|
| **One-off client** | `:gen_tcp.connect/3` + send/recv + close | Request-response; throw away after use |
| **Persistent client** | GenServer holding socket; reconnect on failure | Long-lived connection (DB driver, AMQP, Redis) |
| **Connection pool** | N persistent clients; checkout/checkin | High concurrency sharing setup cost |

### 10.2 Persistent client with reconnect

```elixir
defmodule MyApp.PersistentClient do
  use GenServer

  @reconnect_after 1_000

  def init(opts) do
    Process.flag(:trap_exit, true)
    send(self(), :connect)
    {:ok, %{socket: nil, opts: opts}}
  end

  def handle_info(:connect, state) do
    case :gen_tcp.connect(state.opts[:host], state.opts[:port], [:binary, active: :once]) do
      {:ok, socket} ->
        {:noreply, %{state | socket: socket}}
      {:error, _reason} ->
        Process.send_after(self(), :connect, @reconnect_after)
        {:noreply, state}
    end
  end

  def handle_info({:tcp_closed, _socket}, state) do
    Process.send_after(self(), :connect, @reconnect_after)
    {:noreply, %{state | socket: nil}}
  end

  # ...
end
```

### 10.3 Exponential backoff

Real clients use exponential backoff (not fixed retry):

```elixir
defp reconnect_delay(attempts) do
  base = 1_000
  max = 60_000
  delay = min(base * :math.pow(2, attempts), max) |> round()
  jitter = :rand.uniform(delay)
  delay + jitter
end
```

### 10.4 Client connection pool

Use a pool library:
- **NimblePool** — simple, worker-based
- **Poolboy** — classic
- **DBConnection** — for database drivers (Postgrex, MyXQL use this)

Design:
- Worker processes are persistent connections
- Pool checks out a worker for each request
- Worker handles one request at a time
- Returned to pool when done

---

## 11. Protocol design — planning level

### 11.1 Binary vs text

| Factor | Binary | Text (e.g., JSON, line-based) |
|---|---|---|
| Parsing speed | Fast (pattern matching) | Slow (string parsing) |
| Debuggability | Needs tools | Easy to read on the wire |
| Extensibility | TLV, version bits | Just add fields |
| Size | Small | Larger |
| Use cases | IoT, high-frequency, internal | Interoperability, public APIs |

### 11.2 Versioning

**Every wire protocol needs a versioning strategy.** Common approaches:

- **Version byte in header** — `<<version::8, type::8, ...>>`
- **Separate port per version** — run both old and new
- **Capabilities negotiation** — client/server exchange supported versions at handshake
- **Forward-compatible encoding** — protobuf, Cap'n Proto, Avro

### 11.3 Idempotency

If the protocol is request-response across unreliable network:
- Each request has a unique ID
- Server dedupes retries by ID
- Server can cache responses for re-delivery

See [data-ownership-deep.md](data-ownership-deep.md) §5 for idempotency patterns.

### 11.4 Heartbeats / keepalive

Long-lived connections need heartbeats to detect dead peers:

```elixir
# Server side
def init(opts) do
  Process.send_after(self(), :heartbeat, @heartbeat_interval)
  {:ok, %{last_ping: monotonic_now()}}
end

def handle_info(:heartbeat, state) do
  if monotonic_now() - state.last_ping > @timeout do
    {:stop, :peer_timeout, state}
  else
    # Send ping
    :gen_tcp.send(state.socket, ping_frame())
    Process.send_after(self(), :heartbeat, @heartbeat_interval)
    {:noreply, state}
  end
end
```

TCP keepalive at the socket level exists but is OS-dependent and slow. Application-layer heartbeats are more responsive.

### 11.5 Schema evolution

- **Additive changes safe** — new optional fields
- **Removing fields** — mark deprecated; remove after all peers upgraded
- **Renaming fields** — introduce new name; support both; remove old after migration
- **Changing semantics** — usually a new version

---

## 12. Ranch vs Thousand Island vs raw `:gen_tcp`

| Feature | Raw `:gen_tcp` | Ranch | Thousand Island |
|---|---|---|---|
| Acceptor pool | DIY | Built-in | Built-in |
| Connection supervision | DIY | Built-in | Built-in |
| Graceful shutdown | DIY | Built-in | Built-in |
| TLS support | `:ssl` module | `:ranch_ssl` | Built-in |
| Connection limits | DIY | `max_connections` option | `num_connections` option |
| Mature | Trivial | Very (used in Cowboy) | Newer (modern Elixir) |
| API style | Erlang-ish | Erlang-ish | Elixir-idiomatic |
| Best fit | Learning, tiny | Production, any | Production, new Elixir projects |

**Default: Ranch.** It underlies Phoenix's Cowboy, has been battle-tested for years.

**Thousand Island** if you prefer a more idiomatic Elixir API and are starting fresh.

**Raw `:gen_tcp`** only for learning or trivial cases.

---

## 13. Clustering considerations

### 13.1 Distribution adds complexity

If your TCP server runs on multiple nodes:

- **Connection affinity**: each connection lives on one node; can't migrate
- **Load balancing**: front-load at LB level (round robin, least-connections)
- **Cross-node state**: if two connections on different nodes need to coordinate, use `:pg` or Phoenix.PubSub

### 13.2 Session stickiness

If connections are stateful (game server, chat), the LB needs to route the same client to the same node:
- **Source IP hash** — basic stickiness
- **Cookie-based** — HTTP layer
- **Protocol-based** — first packet contains a session ID; LB routes by that

### 13.3 Cross-node communication

For messages between connections on different nodes:

```elixir
# Register connection in a distributed scope
:pg.join(:connections, "user:#{user_id}", self())

# Send to all nodes that have this user's connection
for pid <- :pg.get_members(:connections, "user:#{user_id}") do
  send(pid, {:push, msg})
end
```

See `erpc` skill for distributed Elixir patterns.

---

## 14. Capacity planning

### 14.1 Scaling dimensions

Know which dimension you're hitting:

| Bottleneck | Symptom | Fix |
|---|---|---|
| File descriptors | `:eaddrinuse` or `:enfile` | Raise `ulimit -n` |
| Memory | OOM; BEAM memory growth | Fewer connections per node; smaller per-connection state |
| CPU | High load avg; slow responses | More acceptors; offload CPU-heavy parsing |
| Network bandwidth | LB reports congestion | Multiple network interfaces; faster NIC |
| TCP port exhaustion (client side) | `:eaddrinuse` when connecting out | Connection pooling; increase ephemeral port range |

### 14.2 Benchmarking TCP servers

- **Tools**: `wrk`, `vegeta`, `bombardier`, `tcpkali`
- **Metrics**: p50/p95/p99 latency; throughput (req/sec); connection rate; open-connection count
- **Ramp test**: start at 10 conn/sec, ramp to target; find the knee

### 14.3 Expected performance

Rough numbers (Elixir/BEAM on modern hardware):

| Workload | Rate |
|---|---|
| Accept rate | 50K-200K new conn/sec per node |
| Open connections | ~1M per node (memory-bound) |
| Simple request/response | 100K-500K req/sec per node |
| TLS handshake | ~5K-20K new TLS conn/sec per core |
| UDP packet rate | 100K-500K pkt/sec per node |

Your mileage varies by protocol complexity. These are order-of-magnitude estimates.

---

## 15. Common networking design mistakes

### 15.1 `{:active, true}` on untrusted peer

```elixir
# BAD — malicious peer can OOM you by sending a firehose
:inet.setopts(socket, [{:active, true}])
```

Always `:once` or `N` for public-facing servers.

### 15.2 Forgetting to re-arm after `:once`

```elixir
# BAD — process data but forget re-arm
def handle_info({:tcp, _socket, data}, state) do
  process_data(data)
  {:noreply, state}   # No setopts(active: :once)! Messages stop.
end

# GOOD — re-arm every time
def handle_info({:tcp, socket, data}, state) do
  process_data(data)
  :inet.setopts(socket, [{:active, :once}])
  {:noreply, state}
end
```

### 15.3 Not handling partial frames

```elixir
# BAD — assume each {:tcp, socket, data} is a complete frame
def handle_info({:tcp, socket, data}, state) do
  frame = data                             # WRONG — might be half a frame
  process(frame)
  # ...
end

# GOOD — buffer and parse
def handle_info({:tcp, socket, data}, state) do
  {frames, leftover} = parse_frames(state.buffer <> data)
  state = Enum.reduce(frames, state, &process_frame/2)
  # ... update state with leftover buffer
end
```

### 15.4 Blocking recv inside GenServer callback

```elixir
# BAD — blocks the GenServer
def handle_call(:read, _from, state) do
  {:ok, data} = :gen_tcp.recv(state.socket, 0)   # Blocks until data or timeout!
  {:reply, data, state}
end

# GOOD — use active mode; receive via handle_info
```

### 15.5 No graceful shutdown

```elixir
# BAD — killing the app drops in-flight work
# All connections drop mid-transaction

# GOOD — configure Ranch shutdown, let connections finish
:ranch.start_listener(..., shutdown: 30_000)
```

### 15.6 Reinventing Ranch

Don't build the acceptor pool yourself. Ranch is battle-tested; your code won't be.

### 15.7 Mixing protocol parsing with I/O

The connection process should pull bytes and dispatch. If parsing is heavy (JSON with 1MB payloads), offload to a worker. Keep the connection process lean.

### 15.8 No heartbeats on long-lived connections

```elixir
# BAD — idle connection silently stales; firewall drops it; client doesn't know
```

Application-level heartbeats detect dead peers faster than TCP keepalive.

---

## 16. Worked example — design a chat protocol

### 16.1 Requirements

- 10K-100K concurrent connections
- Text-based framing (for debugging)
- TLS required
- Messages within a "channel" broadcast to all members of that channel
- Cross-node clustered

### 16.2 Design decisions

**Listener:** Ranch + `:ranch_ssl`, port 6697 (TLS), 20 acceptors.

**Per-connection:** `:gen_statem` with states:
- `:connecting` — TLS handshake, just arrived
- `:unauthenticated` — awaiting AUTH
- `:authenticated` — normal message flow
- `:closing` — graceful shutdown

**Framing:** line-delimited (CRLF), max line 1024 bytes. Use `{packet: :line}` socket option.

**Active mode:** `{:active, :once}` — safe backpressure.

**Channel membership:** `:pg` (distributed process groups). When a connection joins channel "#general", it joins `:pg.join(:chat, "#general", self())`.

**Broadcasting:** `:pg.get_members(:chat, "#general")` and `send/2` to each.

**Heartbeat:** PING/PONG every 60s, close if no PONG in 180s.

**TLS:** at the BEAM level (Topology B — end-to-end TLS is a chat requirement).

**Supervision:**

```
MyApp.Application (:one_for_one)
├── Repo, PubSub, Telemetry
├── MyApp.Chat.Presence                 # Tracks users; uses :pg
└── Ranch listener (:my_chat_listener)  # Ranch handles the rest
```

**Backpressure:** per-connection mailbox is the only layer needed. If a user sends too fast, their own connection queues up; other users unaffected.

### 16.3 Why each choice

- **`:gen_statem`** — multi-state protocol (connect → auth → data); `:gen_statem` reads much cleaner than GenServer with state case
- **Line-based framing** — chat is fundamentally text; debuggable on the wire
- **`{:active, :once}`** — safe default; prevents abuse
- **`:pg` for channels** — built-in cross-node dispatch; no need for a central pub/sub server
- **TLS in BEAM** — end-to-end TLS required for a chat product; BEAM's `:ssl` is fine at scale

---

## 17. Cross-references

### Within this skill

- [architecture-patterns.md](architecture-patterns.md) §4 — hexagonal architecture (put network code behind behaviours)
- [process-topology.md](process-topology.md) §4.2 — process-per-entity (one per connection)
- [integration-patterns.md](integration-patterns.md) §9 — HTTP client design (for clients, not raw TCP)
- [otp-design.md](otp-design.md) §5 — `:gen_statem` for connection state machines

### In other skills

- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9 — OTP callback templates for GenServer / :gen_statem
- [../elixir-reviewing/SKILL.md](../elixir-reviewing/SKILL.md) — review and debug network code
- `../elixir/networking.md` — deep `:gen_tcp`/`:gen_udp` API reference, all the socket options, binary matching patterns
- `nerves` skill — embedded networking (VintageNet)
- `modbus` skill, `can` skill, `i2c` skill, `spi` skill — specialized protocols

---

**End of networking-design.md.** For raw socket call patterns, see `../elixir/networking.md`. For the at-keyboard implementation code, see [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §9.
