# Performance Pitfall Catalog

Comprehensive catalog of Elixir/BEAM performance pitfalls with concrete fixes. Used during code review and performance investigations.

**Layout:** each entry follows `Symptom → Root cause → Fix → Evidence`.

---

## Data Structure Pitfalls

### 1. `length(list)` for emptiness check

**Symptom:** CPU hotspot on large-list checks.
**Root cause:** `length/1` is O(n) — traverses the whole list.
**Fix:** pattern match `[]` / `[_|_]`, or compare to empty literal.

```elixir
# BAD
if length(items) > 0, do: process(items)

# GOOD
case items do
  [] -> :empty
  _ -> process(items)
end
```

**Evidence:** Benchee shows 1000× difference for 1M-item lists.

---

### 2. `list ++ list` appending in a loop

**Symptom:** O(n²) time in accumulator code.
**Root cause:** `++` is O(length of left operand) — re-copies the left list each iteration.
**Fix:** prepend to head, reverse at end; or use `Enum.map`/`for`.

```elixir
# BAD — O(n²)
Enum.reduce(items, [], fn x, acc -> acc ++ [transform(x)] end)

# GOOD — O(n)
Enum.reduce(items, [], fn x, acc -> [transform(x) | acc] end) |> Enum.reverse()

# BETTER — simpler
Enum.map(items, &transform/1)
```

---

### 3. String concatenation with `<>` in a loop

**Symptom:** Slow string-building, high memory pressure.
**Root cause:** `a <> b` creates a new binary (copy of both).
**Fix:** build with IO lists, flatten once.

```elixir
# BAD
Enum.reduce(items, "", fn x, acc -> acc <> format(x) <> "\n" end)

# GOOD
items
|> Enum.map(&format/1)
|> Enum.intersperse("\n")
|> IO.iodata_to_binary()

# BETTER (when going to I/O)
items |> Enum.map(&[format(&1), "\n"]) |> IO.write()
```

---

### 4. `Map.to_list |> Enum.filter`

**Symptom:** Unnecessary intermediate list.
**Root cause:** Converting the whole map to a list then filtering doubles allocation.
**Fix:** `for` comprehension with pattern match.

```elixir
# BAD
map |> Map.to_list() |> Enum.filter(fn {_, v} -> v > 0 end)

# GOOD
for {k, v} <- map, v > 0, do: {k, v}
```

---

### 5. `Map.values |> Enum.count`

**Symptom:** Unnecessary materialization.
**Root cause:** `Map.values` allocates a new list to count it.
**Fix:** `map_size/1` for total; `Enum.count/2` with filter avoids materialization.

```elixir
# BAD
map |> Map.values() |> Enum.count(& &1.active?)

# GOOD
Enum.count(map, fn {_, v} -> v.active? end)
```

---

### 6. `List.duplicate` for large N

**Symptom:** Long startup or allocation spike.
**Root cause:** Large N materializes a huge list.
**Fix:** for simple tests, use `Stream.cycle/1` + `take`; for config, use a smaller base.

```elixir
# BAD — if only iterating
items = List.duplicate(:x, 1_000_000)
Enum.each(items, &process/1)

# GOOD
Stream.cycle([:x]) |> Stream.take(1_000_000) |> Stream.each(&process/1) |> Stream.run()
```

---

## Enum vs Stream Pitfalls

### 7. Chaining multiple `Enum.map/filter` passes

**Symptom:** Many intermediate lists, slower than one-pass.
**Root cause:** Each `Enum.*` traverses and materializes a new list.
**Fix:** one `for` comprehension, or use `Stream` and materialize once with `Enum.to_list` at the end.

```elixir
# BAD — 4 passes, 3 intermediate lists
items
|> Enum.map(&parse/1)
|> Enum.filter(&valid?/1)
|> Enum.map(&transform/1)
|> Enum.reject(&excluded?/1)

# GOOD — 1 pass
for item <- items, parsed = parse(item), valid?(parsed), !excluded?(parsed),
  do: transform(parsed)

# ALSO GOOD — still 4 passes but no intermediate materialization
items
|> Stream.map(&parse/1)
|> Stream.filter(&valid?/1)
|> Stream.map(&transform/1)
|> Stream.reject(&excluded?/1)
|> Enum.to_list()
```

**Evidence:** for 1M items with predicate rejecting 90%, Stream is ~2× faster than chained Enum.

---

### 8. `Stream` where `Enum` would be faster

**Symptom:** Premature lazy evaluation, actually slower.
**Root cause:** `Stream.map` has wrapper overhead; for small lists or when all items are consumed, `Enum.map` wins.
**Fix:** use Stream only for large inputs, early termination, or I/O.

```elixir
# BAD — Stream for 10 items consumed fully; wrapper overhead dominates
items |> Stream.map(&double/1) |> Enum.to_list()

# GOOD — just Enum for small/fully-consumed
Enum.map(items, &double/1)
```

**Rule:** use Stream when you take/discard early, or when source is I/O-bound.

---

## Process & OTP Pitfalls

### 9. `GenServer.call` with default timeout in a hot path

**Symptom:** Request-tail latency spikes to 5s.
**Root cause:** Default timeout is 5000ms; if the callee is slow, whole request blocks for 5s.
**Fix:** explicit narrower timeout + fallback.

```elixir
# BAD
def get_config, do: GenServer.call(MyConfig, :get)

# GOOD
def get_config do
  try do
    GenServer.call(MyConfig, :get, 100)
  catch
    :exit, {:timeout, _} -> @default_config
  end
end
```

---

### 10. Unbounded `Task.async_stream` concurrency

**Symptom:** memory balloons; system chokes under load.
**Root cause:** default `max_concurrency` is `System.schedulers_online()`; for I/O-bound work with many small tasks, this underutilizes; for CPU-bound, it's fine.
**Fix:** match concurrency to the bottleneck.

```elixir
# BAD — unbounded allocation waiting on 10K HTTP calls
urls
|> Task.async_stream(&fetch/1)
|> Enum.to_list()

# GOOD — bounded
urls
|> Task.async_stream(&fetch/1,
    max_concurrency: 50,
    timeout: 10_000,
    on_timeout: :kill_task,
    ordered: false)
|> Enum.reduce([], fn
  {:ok, r}, acc -> [r | acc]
  _, acc -> acc
end)
```

---

### 11. `Process.sleep` in a GenServer callback

**Symptom:** whole process stalls; all pending messages blocked.
**Root cause:** a GenServer handles one message at a time. Sleeping blocks everything.
**Fix:** use `Process.send_after/3` to schedule the next action.

```elixir
# BAD — blocks all messages for 10s
def handle_info(:tick, state) do
  Process.sleep(10_000)
  work()
  send(self(), :tick)
  {:noreply, state}
end

# GOOD
def handle_info(:tick, state) do
  work()
  Process.send_after(self(), :tick, 10_000)
  {:noreply, state}
end
```

---

### 12. Blocking `init/1`

**Symptom:** supervisor boot takes N seconds per child.
**Root cause:** `init/1` is synchronous — caller blocks until it returns.
**Fix:** return quickly, defer heavy work to `handle_continue`.

```elixir
# BAD
def init(opts) do
  data = expensive_load()
  {:ok, %{data: data, opts: opts}}
end

# GOOD
def init(opts), do: {:ok, %{data: nil, opts: opts}, {:continue, :load}}

def handle_continue(:load, state) do
  {:noreply, %{state | data: expensive_load()}}
end
```

---

### 13. `GenServer` as a registry

**Symptom:** Single process bottlenecks all lookups.
**Root cause:** Every call goes through one mailbox — serialized.
**Fix:** use ETS (or `Registry`) for read-heavy state.

```elixir
# BAD
defmodule Cache do
  use GenServer
  def get(k), do: GenServer.call(__MODULE__, {:get, k})
  def handle_call({:get, k}, _, state), do: {:reply, Map.get(state, k), state}
end

# GOOD — reads don't go through a process
:ets.new(:my_cache, [:set, :named_table, :public, read_concurrency: true])
def get(k), do: :ets.lookup(:my_cache, k) |> case do
  [{^k, v}] -> {:ok, v}
  [] -> :error
end
```

---

### 14. `active: true` on a TCP socket

**Symptom:** mailbox fills; memory balloons.
**Root cause:** BEAM delivers every received packet as a message — no backpressure.
**Fix:** `active: :once` or `active: N`.

```elixir
# BAD
:gen_tcp.listen(port, [:binary, active: true])

# GOOD
:gen_tcp.listen(port, [:binary, active: :once, packet: 4])
```

---

### 15. Unsupervised `spawn`

**Symptom:** silent crashes; work disappears.
**Root cause:** `spawn/1` is not monitored; errors go to the void.
**Fix:** `Task.Supervisor.start_child/2` or supervised worker.

```elixir
# BAD
spawn(fn -> send_email(user) end)

# GOOD
Task.Supervisor.start_child(MyApp.TaskSup, fn -> send_email(user) end)
```

---

## Ecto Pitfalls

### 16. N+1 queries via preload in a loop

**Symptom:** request does 100+ queries.
**Root cause:** `Repo.preload` inside `Enum.map`.
**Fix:** preload once on the parent list.

```elixir
# BAD
users = Repo.all(User)
Enum.map(users, fn u -> Repo.preload(u, :posts) end)

# GOOD
users = User |> Repo.all() |> Repo.preload(:posts)
# OR
users = from(u in User, preload: :posts) |> Repo.all()
```

---

### 17. Counting with `Repo.all |> length`

**Symptom:** full row load for a count.
**Root cause:** loads all rows into memory to count them.
**Fix:** `Repo.aggregate/3` with `:count`.

```elixir
# BAD
count = Repo.all(from(u in User, where: u.active?)) |> length()

# GOOD
count = Repo.aggregate(from(u in User, where: u.active?), :count, :id)
```

---

### 18. Large `IN` clause

**Symptom:** slow query; DB plan bails.
**Root cause:** `where: u.id in ^ids` with 10K IDs. Query planner optimizations may not apply.
**Fix:** batch, or use a join/subquery.

```elixir
# BAD
Repo.all(from(u in User, where: u.id in ^large_list))

# GOOD — batch
large_list
|> Enum.chunk_every(1000)
|> Enum.flat_map(fn chunk ->
  Repo.all(from(u in User, where: u.id in ^chunk))
end)
```

---

### 19. Missing index

**Symptom:** query time grows linearly with table size.
**Root cause:** Postgres does seq scan on unindexed column.
**Fix:** `EXPLAIN ANALYZE` to confirm, then add index.

```sh
# Identify
mix ecto.gen.migration add_idx_users_email
```

```elixir
def change do
  create index(:users, [:email])
  # Or for large tables (no write lock):
  # create index(:users, [:email], concurrently: true)
end
```

---

### 20. `Repo.transaction` holding DB connection too long

**Symptom:** connection pool exhaustion under load.
**Root cause:** long work inside `Repo.transaction/1` keeps the connection held.
**Fix:** don't do non-DB work (HTTP calls, file I/O, long computations) inside a transaction.

```elixir
# BAD
Repo.transaction(fn ->
  user = Repo.insert!(changeset)
  send_welcome_email(user)      # Blocks connection!
  log_to_s3(user)               # Blocks connection!
end)

# GOOD
{:ok, user} = Repo.insert(changeset)
Task.Supervisor.start_child(MyApp.TaskSup, fn -> send_welcome_email(user) end)
Task.Supervisor.start_child(MyApp.TaskSup, fn -> log_to_s3(user) end)
```

---

### 21. Wide `select *` when only a few columns are needed

**Symptom:** increased network transfer; GC pressure.
**Root cause:** Ecto defaults to loading all columns.
**Fix:** explicit `select`.

```elixir
# BAD
Repo.all(from(u in User))   # Loads every column including large TEXT fields

# GOOD — for list views
from(u in User, select: %{id: u.id, name: u.name, email: u.email}) |> Repo.all()
```

---

## Memory & Binary Pitfalls

### 22. Large binary held by a long-lived process

**Symptom:** binary memory grows; processes unwilling to GC.
**Root cause:** Refcounted binaries (>64 bytes) held by reference in process state.
**Fix:** extract only what's needed (sub-binary); periodically force GC; use `:fullsweep_after`.

```elixir
# BAD — holds entire original response
def handle_info({:response, body}, state) do
  token = extract_token(body)   # But state now holds body via ref
  {:noreply, %{state | last_response: body}}
end

# GOOD — copy the needed slice, let original GC
def handle_info({:response, body}, state) do
  token = :binary.copy(extract_token(body))
  {:noreply, %{state | last_token: token}}
end

# OR tune GC for the process
Process.flag(:fullsweep_after, 10)
```

---

### 23. ETS table without eviction

**Symptom:** ETS memory grows unboundedly.
**Root cause:** nothing ever deletes old entries.
**Fix:** periodic sweep, use `cachex`/`nebulex`, or limit size.

```elixir
# Sweep job
def handle_info(:sweep, state) do
  cutoff = System.system_time(:second) - 3600
  :ets.select_delete(:my_cache, [
    {{:_, :_, :"$1"}, [{:<, :"$1", cutoff}], [true]}
  ])
  Process.send_after(self(), :sweep, 60_000)
  {:noreply, state}
end
```

---

### 24. `String.to_atom/1` on untrusted input

**Symptom:** atom table grows; eventually node crashes.
**Root cause:** atoms are not garbage collected; limit is ~1M default.
**Fix:** `String.to_existing_atom/1` (raises on unknown), or whitelist.

```elixir
# BAD — DoS vector
key = params["key"] |> String.to_atom()

# GOOD
key = String.to_existing_atom(params["key"])

# OR whitelist
allowed = ~w(active inactive pending)a
if params["key"] in Enum.map(allowed, &to_string/1),
  do: String.to_existing_atom(params["key"]),
  else: :invalid
```

---

## Serialization Pitfalls

### 25. JSON-decoding into atom keys from untrusted input

**Symptom:** atom-table growth from JSON fields.
**Root cause:** `Jason.decode!(body, keys: :atoms)` creates atoms from JSON keys.
**Fix:** decode to strings; convert to existing atoms in a whitelist layer.

```elixir
# BAD
Jason.decode!(body, keys: :atoms)   # Every distinct JSON key → atom

# GOOD
Jason.decode!(body)                  # String keys

# OR with existing atoms only
Jason.decode!(body, keys: :atoms!)   # Raises on unknown atoms
```

---

### 26. Encoding large structures in a hot path

**Symptom:** high CPU on serialization.
**Root cause:** re-encoding a largely-unchanged structure repeatedly.
**Fix:** memoize the encoded binary, or encode fragments.

```elixir
# BAD — encodes full struct each call
def render(conn, data), do: json(conn, data)

# GOOD — cache the encoded form when data is known
:persistent_term.put({MyApp, :cached}, Jason.encode_to_iodata!(data))
body = :persistent_term.get({MyApp, :cached})
conn |> put_resp_content_type("application/json") |> send_resp(200, body)
```

---

## Phoenix / Web Pitfalls

### 27. Rendering a template per list item in a loop

**Symptom:** slow view rendering.
**Root cause:** `Enum.map(items, &render_item/1)` invokes HEEx per item; overhead compounds.
**Fix:** single template renders the list.

```heex
<!-- BAD — reinvokes render per item -->
<%= for item <- @items do %>
  <%= render "item.html", item: item %>
<% end %>

<!-- GOOD — inline the item markup -->
<%= for item <- @items do %>
  <li><%= item.name %></li>
<% end %>
```

---

### 28. Missing `stream` for LiveView lists

**Symptom:** LiveView sends full re-render of all list items on any change.
**Root cause:** lists in assigns always diff fully.
**Fix:** `Phoenix.LiveView.stream/4` for collections.

```elixir
# BAD
socket |> assign(messages: [new_msg | socket.assigns.messages])

# GOOD
socket |> stream_insert(:messages, new_msg, at: 0)
```

---

### 29. Synchronous third-party API in a controller

**Symptom:** tail latency = external API latency.
**Root cause:** controller blocks on sync HTTP call.
**Fix:** enqueue to Oban, return 202, poll or push-notify.

```elixir
# BAD
def create(conn, params) do
  result = ExternalAPI.slow_call(params)
  json(conn, result)
end

# GOOD
def create(conn, params) do
  {:ok, job} = Oban.insert(MyJob.new(params))
  conn |> put_status(202) |> json(%{job_id: job.id})
end
```

---

## Process Design Pitfalls

### 30. GenServer with giant state

**Symptom:** GC pauses slow callbacks; memory copied on each state update.
**Root cause:** BEAM copies state on each handler return (for the VM's fault tolerance).
**Fix:** split state across processes; move "big" data to ETS.

```elixir
# BAD — 100MB state, copied on every callback
def handle_call(:get, _, state), do: {:reply, state.items[id], state}

# GOOD — items in ETS
def handle_call({:get, id}, _, state) do
  [{^id, item}] = :ets.lookup(state.table, id)
  {:reply, item, state}
end
```

---

### 31. Monitoring many processes from one process

**Symptom:** single process mailbox floods with `:DOWN` messages.
**Root cause:** `:DOWN` arrives as a normal message; batch starts overwhelm the monitor.
**Fix:** shard the monitor across multiple processes, or use a Registry-based listener.

---

### 32. Registry `:duplicate` fan-out to thousands of subscribers

**Symptom:** slow dispatch; CPU spike on publish.
**Root cause:** `Registry.dispatch/3` is O(n) in subscribers.
**Fix:** shard topics, use Phoenix.PubSub, or partition Registry.

---

## Cross-References

- **Debugging specific symptoms:** `./debugging-playbook-deep.md`
- **Profiling tool selection:** `./profiling-playbook-deep.md`
- **Main reviewing skill §10 (Common pitfalls):** `./SKILL.md`
- **Idiomatic patterns (how to avoid producing these):** `../elixir-implementing/idioms-reference.md`
- **Data structure reference (complexity tables):** `../elixir-implementing/data-reference.md`
