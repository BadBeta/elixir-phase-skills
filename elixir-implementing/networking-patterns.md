# Networking Patterns — Implementation Templates

Phase-focused on **writing** socket and protocol code. Covers `:gen_tcp` / `:gen_udp` call patterns, binary matching for framing, acceptor-loop templates, per-connection process lifecycle.

**For architectural networking concerns** (active vs passive mode decision, Ranch vs Thousand Island vs raw, connection supervision shape, TLS placement, backpressure design), see `../elixir-planning/networking-design.md`.

---

## Rules for Writing Networking Code

1. **ALWAYS spawn a process per connection.** Never let your listener process handle a client directly — the next `accept/1` will be starved.
2. **ALWAYS use `:binary` mode** — never `:list`. Lists of bytes are slow and idiosyncratic.
3. **ALWAYS set `packet: N` or `packet: :line`** when the protocol allows. The BEAM's built-in framing is faster than any user-space framing code.
4. **ALWAYS match on `reuseaddr: true`** for listen sockets to allow fast restart.
5. **NEVER use `active: true` in production** for long-lived connections — unbounded incoming data fills the mailbox. Use `active: :once` or `active: N` for backpressure.
6. **ALWAYS close sockets on error paths.** Use `try/after` or `Process.flag(:trap_exit, true)` + `terminate/2`.
7. **ALWAYS use length-prefix framing** over delimiter framing for binary protocols. Length is O(1) to parse; scanning for delimiters is O(n).
8. **NEVER assume a single `recv` call returns your whole message.** TCP is a byte stream, not a message stream — accumulate into a buffer and parse.
9. **ALWAYS size buffers and timeouts explicitly.** Default `:gen_tcp` timeout is infinity — set a real ms value sized to your SLO.
10. **ALWAYS use `controlling_process/2`** when spawning a handler to transfer ownership — otherwise the handler can't receive data from the socket.

---

## TCP Server Template — Acceptor Loop

```elixir
defmodule MyApp.TCPServer do
  require Logger

  def start_link(port), do: {:ok, spawn_link(fn -> listen(port) end)}

  defp listen(port) do
    opts = [:binary,
            packet: 4,              # 4-byte length prefix; BEAM does framing for you
            active: :once,
            reuseaddr: true,
            backlog: 1024
          ]
    {:ok, listen_sock} = :gen_tcp.listen(port, opts)
    Logger.info("Listening on port #{port}")
    accept_loop(listen_sock)
  end

  defp accept_loop(listen_sock) do
    case :gen_tcp.accept(listen_sock) do
      {:ok, client_sock} ->
        {:ok, pid} = Task.Supervisor.start_child(
          MyApp.ConnectionSup,
          fn -> handle_connection(client_sock) end
        )
        :ok = :gen_tcp.controlling_process(client_sock, pid)
        accept_loop(listen_sock)

      {:error, reason} ->
        Logger.error("accept failed: #{inspect(reason)}")
        accept_loop(listen_sock)
    end
  end

  defp handle_connection(sock) do
    # Enable one frame to arrive
    :inet.setopts(sock, active: :once)
    receive do
      {:tcp, ^sock, data} ->
        handle_frame(sock, data)
        :inet.setopts(sock, active: :once)  # Ask for the next frame
        handle_connection(sock)

      {:tcp_closed, ^sock} ->
        Logger.debug("client closed")

      {:tcp_error, ^sock, reason} ->
        Logger.warning("TCP error: #{inspect(reason)}")
    after
      60_000 -> :gen_tcp.close(sock)  # idle timeout
    end
  end

  defp handle_frame(sock, data) do
    response = process(data)
    :gen_tcp.send(sock, response)
  end

  defp process(data), do: # business logic
end
```

**Key points:**
- `packet: 4` — BEAM reads a 4-byte big-endian length, buffers until that many bytes arrive, then delivers a single `{:tcp, sock, data}` message with the framed payload. No user-space framing needed.
- `active: :once` — BEAM delivers one message, then sets the socket passive until you re-enable. Natural backpressure.
- `controlling_process/2` — handler becomes the process that receives `{:tcp, ...}` messages.

---

## Active Mode Decision

| Mode | Behaviour | When to use |
|---|---|---|
| `active: false` | Must call `:gen_tcp.recv/2` explicitly | Synchronous protocols (request/reply); simpler flow |
| `active: :once` | One message delivered, then passive | **Default for production** — one message at a time with backpressure |
| `active: N` (integer) | N messages delivered, then passive | Batch processing; avoids overhead of many `setopts` |
| `active: true` | All data delivered as messages | **NEVER in production** — mailbox overflow risk |

### Active-N pattern

```elixir
:inet.setopts(sock, active: 100)

def handle_connection(sock, remaining) when remaining <= 0 do
  :inet.setopts(sock, active: 100)  # Re-arm
  handle_connection(sock, 100)
end

def handle_connection(sock, remaining) do
  receive do
    {:tcp, ^sock, data} ->
      handle_frame(sock, data)
      handle_connection(sock, remaining - 1)

    {:tcp_passive, ^sock} ->       # Arrives when counter hits 0
      handle_connection(sock, 0)

    {:tcp_closed, ^sock} -> :ok
  end
end
```

---

## Passive Mode — Request/Reply Server

```elixir
defp handle_connection(sock) do
  case :gen_tcp.recv(sock, 0, 30_000) do
    {:ok, data} ->
      reply = process(data)
      :gen_tcp.send(sock, reply)
      handle_connection(sock)

    {:error, :closed} -> :ok
    {:error, reason} -> Logger.warning("recv error: #{inspect(reason)}")
  end
end
```

`:gen_tcp.recv(sock, 0, timeout)` — `0` means "whatever packet framing yields". Use explicit byte count only for raw byte streams without framing.

---

## Protocol Framing — Length Prefix

```elixir
# BEAM handles it (preferred):
opts = [:binary, packet: 4, active: :once]

# Manual (when you need custom length size, e.g., 2 or 8 bytes):
opts = [:binary, packet: :raw, active: :once]

defp parse_frame(buffer) do
  case buffer do
    <<len::32, payload::binary-size(len), rest::binary>> ->
      {:ok, payload, rest}
    _ ->
      :incomplete
  end
end

# In the connection loop:
def handle_loop(sock, buffer) do
  receive do
    {:tcp, ^sock, data} ->
      new_buffer = buffer <> data

      case parse_frame(new_buffer) do
        {:ok, frame, rest} ->
          handle_frame(sock, frame)
          :inet.setopts(sock, active: :once)
          handle_loop(sock, rest)
        :incomplete ->
          :inet.setopts(sock, active: :once)
          handle_loop(sock, new_buffer)
      end

    {:tcp_closed, ^sock} -> :ok
  end
end
```

---

## Protocol Framing — Line Delimiter

```elixir
# BEAM handles it (preferred):
opts = [:binary, packet: :line, active: :once]
# BEAM delivers one {:tcp, sock, line} per \n-terminated line

# Manual (for custom delimiters):
defp split_lines(buffer) do
  case :binary.split(buffer, "\r\n") do
    [line, rest] -> {:ok, line, rest}
    [buffer] -> :incomplete
  end
end
```

---

## Protocol Framing — TLV (Type-Length-Value)

```elixir
defp parse_tlv(buffer) do
  case buffer do
    <<type::8, len::16, value::binary-size(len), rest::binary>> ->
      {:ok, {type, value}, rest}
    _ ->
      :incomplete
  end
end

# Encoding
def encode_tlv(type, value) do
  len = byte_size(value)
  <<type::8, len::16, value::binary>>
end
```

---

## TCP Client Template

```elixir
defmodule MyApp.TCPClient do
  def connect(host, port, opts \\ []) do
    default_opts = [:binary, packet: 4, active: false]
    merged = Keyword.merge(default_opts, opts)

    case :gen_tcp.connect(to_charlist(host), port, merged, 5_000) do
      {:ok, sock} -> {:ok, sock}
      {:error, reason} -> {:error, reason}
    end
  end

  def send(sock, data), do: :gen_tcp.send(sock, data)

  def recv(sock, timeout \\ 5_000) do
    case :gen_tcp.recv(sock, 0, timeout) do
      {:ok, data} -> {:ok, data}
      {:error, :timeout} -> {:error, :timeout}
      {:error, :closed} -> {:error, :closed}
      {:error, reason} -> {:error, reason}
    end
  end

  def close(sock), do: :gen_tcp.close(sock)

  def request(host, port, payload) do
    with {:ok, sock} <- connect(host, port),
         :ok <- send(sock, payload),
         {:ok, reply} <- recv(sock) do
      _ = close(sock)
      {:ok, reply}
    end
  end
end
```

---

## UDP Server Template

```elixir
defmodule MyApp.UDPServer do
  require Logger

  def start_link(port) do
    {:ok, sock} = :gen_udp.open(port, [:binary, active: :once])
    {:ok, spawn_link(fn -> loop(sock) end)}
  end

  defp loop(sock) do
    receive do
      {:udp, ^sock, ip, port, data} ->
        handle_datagram(sock, ip, port, data)
        :inet.setopts(sock, active: :once)
        loop(sock)
    end
  end

  defp handle_datagram(sock, ip, port, data) do
    response = process(data)
    :gen_udp.send(sock, ip, port, response)
  end
end
```

### UDP broadcast / multicast

```elixir
# Broadcast
{:ok, sock} = :gen_udp.open(0, [:binary, broadcast: true])
:gen_udp.send(sock, {255, 255, 255, 255}, port, message)

# Multicast
{:ok, sock} = :gen_udp.open(port, [
  :binary,
  active: :once,
  reuseaddr: true,
  add_membership: {{239, 1, 2, 3}, {0, 0, 0, 0}},  # group IP, iface
  multicast_ttl: 4,
  multicast_loop: false
])
```

---

## Common `:gen_tcp` / `:gen_udp` Options

| Option | Purpose |
|---|---|
| `:binary` | Receive as binary (always use this) |
| `active: false/once/N/true` | Receive mode (see table above) |
| `packet: :raw/:line/1/2/4/8` | Built-in framing |
| `reuseaddr: true` | Allow quick restart (listen sockets) |
| `keepalive: true` | TCP keep-alive probes |
| `nodelay: true` | Disable Nagle (low-latency) |
| `backlog: 1024` | Max pending connects (listen) |
| `send_timeout: 5_000` | Block `send` if buffer full |
| `send_timeout_close: true` | Close socket on send_timeout |
| `recbuf: 65536` / `sndbuf: 65536` | OS socket buffer sizes |
| `delay_send: true` | Coalesce small sends |

---

## Ranch Protocol Template

```elixir
defmodule MyApp.EchoProtocol do
  @behaviour :ranch_protocol

  @impl true
  def start_link(ref, transport, opts) do
    pid = :proc_lib.spawn_link(__MODULE__, :init, [ref, transport, opts])
    {:ok, pid}
  end

  def init(ref, transport, _opts) do
    {:ok, sock} = :ranch.handshake(ref)
    :ok = transport.setopts(sock, active: :once)
    loop(sock, transport)
  end

  defp loop(sock, transport) do
    receive do
      {:tcp, ^sock, data} ->
        transport.send(sock, data)  # echo
        transport.setopts(sock, active: :once)
        loop(sock, transport)

      {:tcp_closed, ^sock} -> :ok
      {:tcp_error, ^sock, _reason} -> :ok
    after
      60_000 -> :ok
    end
  end
end

# Start Ranch
:ranch.start_listener(
  :my_echo,
  :ranch_tcp,                    # or :ranch_ssl for TLS
  %{socket_opts: [port: 4040], num_acceptors: 10},
  MyApp.EchoProtocol,
  []
)
```

---

## Thousand Island (Modern Alternative)

```elixir
defmodule MyApp.EchoHandler do
  use ThousandIsland.Handler

  @impl ThousandIsland.Handler
  def handle_data(data, socket, state) do
    ThousandIsland.Socket.send(socket, data)
    {:continue, state}
  end
end

# In supervision tree:
{ThousandIsland, port: 4040, handler_module: MyApp.EchoHandler}
```

Thousand Island uses pure-Elixir acceptor pool and has a behaviour-based API — often cleaner than Ranch for greenfield projects.

---

## TLS

### Server

```elixir
opts = [
  :binary,
  packet: 4,
  active: :once,
  reuseaddr: true,
  certfile: "/path/to/cert.pem",
  keyfile: "/path/to/key.pem",
  verify: :verify_none,               # or :verify_peer + cacertfile:
  versions: [:"tlsv1.2", :"tlsv1.3"],
  ciphers: :ssl.cipher_suites(:default, :"tlsv1.3")
]

{:ok, listen_sock} = :ssl.listen(port, opts)
```

### Client

```elixir
{:ok, sock} = :ssl.connect(~c"api.example.com", 443, [
  :binary,
  active: false,
  verify: :verify_peer,
  cacerts: :public_key.cacerts_get(),
  server_name_indication: ~c"api.example.com",
  customize_hostname_check: [match_fun: :public_key.pkix_verify_hostname_match_fun(:https)]
])
```

Use `:ssl` the same way as `:gen_tcp` — same message shape (`{:ssl, sock, data}` instead of `{:tcp, ...}`).

---

## HTTP Client Patterns

### Req (recommended default)

```elixir
Req.get!("https://api.example.com/users", params: [active: true])
Req.post!("https://api.example.com/users", json: %{name: "Alice"})

# With authentication
Req.get!(url, auth: {:bearer, token})

# With timeouts
Req.get!(url, receive_timeout: 5_000, connect_options: [timeout: 3_000])

# With retries
Req.get!(url, retry: :safe_transient, max_retries: 3)
```

### Finch (higher-control, pooled)

```elixir
# In supervision tree:
{Finch, name: MyFinch, pools: %{default: [size: 100]}}

# Call
Finch.build(:get, "https://api.example.com/users")
|> Finch.request(MyFinch)
```

### Mint (lowest-level, explicit state machine)

Use when Req/Finch can't do what you need (custom connection pooling, streaming uploads with backpressure, etc.).

---

## Common Anti-Patterns (BAD / GOOD)

### 1. `active: true` in production

```elixir
# BAD — mailbox overflow risk
:gen_tcp.listen(port, [:binary, active: true])
```

```elixir
# GOOD
:gen_tcp.listen(port, [:binary, active: :once])
# Or for batch: active: 100
```

### 2. Handling client in the acceptor process

```elixir
# BAD — blocks accept loop
def accept_loop(sock) do
  {:ok, client} = :gen_tcp.accept(sock)
  handle_client(client)         # handles this one, next accept is starved
  accept_loop(sock)
end
```

```elixir
# GOOD — spawn per connection
def accept_loop(sock) do
  {:ok, client} = :gen_tcp.accept(sock)
  {:ok, pid} = Task.Supervisor.start_child(MyApp.ConnSup, fn -> handle_client(client) end)
  :gen_tcp.controlling_process(client, pid)
  accept_loop(sock)
end
```

### 3. Assuming one recv = one message

```elixir
# BAD — TCP is a byte stream
def read_message(sock) do
  {:ok, data} = :gen_tcp.recv(sock, 0)
  parse_message(data)           # breaks if data is partial
end
```

```elixir
# GOOD — buffer and parse incrementally
def read_message(sock, buffer \\ "") do
  case parse_message(buffer) do
    {:ok, msg, rest} -> {:ok, msg, rest}
    :incomplete ->
      {:ok, more} = :gen_tcp.recv(sock, 0)
      read_message(sock, buffer <> more)
  end
end

# OR: use packet: N to let BEAM handle framing
```

### 4. Forgetting to transfer socket ownership

```elixir
# BAD — handler can't receive {:tcp, ...} messages
{:ok, pid} = Task.start_link(fn -> handle(client_sock) end)
accept_loop(listen_sock)        # client_sock still owned by this process
```

```elixir
# GOOD
{:ok, pid} = Task.Supervisor.start_child(sup, fn -> handle(client_sock) end)
:gen_tcp.controlling_process(client_sock, pid)
```

### 5. Scanning for delimiters in a byte-oriented protocol

```elixir
# BAD — O(n) scan every packet
defp find_end(data), do: :binary.match(data, "\r\n\r\n")
```

```elixir
# GOOD — length prefix
opts = [:binary, packet: 4]     # BEAM reads 4-byte length, delivers complete frames
```

### 6. Default timeouts

```elixir
# BAD — default is :infinity
:gen_tcp.recv(sock, 0)          # blocks forever if peer doesn't send
:gen_tcp.connect(host, port, opts)
```

```elixir
# GOOD — explicit timeouts sized to SLO
:gen_tcp.recv(sock, 0, 30_000)
:gen_tcp.connect(host, port, opts, 5_000)
```

---

## Cross-References

- **Architectural design** (mode choice rationale, TLS placement, Ranch vs Thousand Island, supervision shape, chat-protocol worked example): `../elixir-planning/networking-design.md`
- **Stdlib networking reference:** `../elixir/networking.md`
- **Binary patterns (framing, construction):** `./data-reference.md`
- **Process supervision for connection handlers:** `./otp-callbacks.md`
- **Reviewing network code:** `../elixir-reviewing/SKILL.md`
