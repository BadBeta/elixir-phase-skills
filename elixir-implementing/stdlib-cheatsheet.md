# Stdlib Cheat Sheet

Dense lookups for the stdlib functions you'll type most often. Load when you need the call signature fast but don't need the full reference.

**For deeper stdlib reference** (every function with parameters and examples), load the parent `elixir` skill's `quick-references.md`.

---

## Enum — top 30

```elixir
Enum.map(enum, fun)               Enum.filter(enum, fun)
Enum.reject(enum, fun)            Enum.reduce(enum, acc, fun)
Enum.reduce_while(enum, acc, fn)  Enum.flat_map(enum, fun)
Enum.find(enum, fun)              Enum.find_value(enum, fn)
Enum.find_index(enum, fun)        Enum.any?(enum, fun)
Enum.all?(enum, fun)              Enum.count(enum)
Enum.count(enum, fun)             Enum.empty?(enum)
Enum.member?(enum, x)             Enum.sum(enum)
Enum.min_by(enum, fun)            Enum.max_by(enum, fun)
Enum.sort_by(enum, fun, order)    Enum.group_by(enum, key_fn)
Enum.frequencies(enum)            Enum.frequencies_by(enum, fn)
Enum.uniq(enum)                   Enum.uniq_by(enum, fun)
Enum.chunk_every(enum, n)         Enum.chunk_by(enum, fun)
Enum.with_index(enum)             Enum.zip(a, b)
Enum.split_with(enum, fun)        Enum.take(enum, n)
Enum.drop(enum, n)                Enum.take_while(enum, fn)
Enum.drop_while(enum, fn)         Enum.into(enum, collectable)
Enum.map_join(enum, joiner, fn)   Enum.map_reduce(enum, acc, fn)
```

## Map

```elixir
Map.get(map, key)                 Map.get(map, key, default)
Map.fetch(map, key)               Map.fetch!(map, key)
Map.put(map, key, value)          Map.put_new(map, key, value)
Map.delete(map, key)              Map.drop(map, keys)
Map.take(map, keys)               Map.merge(a, b)
Map.merge(a, b, fn)               Map.update(map, k, default, fn)
Map.update!(map, k, fn)           Map.has_key?(map, k)
Map.keys(map)                     Map.values(map)
Map.new()                         Map.new(enum)
Map.new(enum, fn)                 Map.from_struct(struct)
map[:key]                          %{map | key: new}          # Update existing only
```

## Keyword

```elixir
Keyword.get(kw, k)                Keyword.get(kw, k, default)
Keyword.fetch(kw, k)              Keyword.fetch!(kw, k)
Keyword.put(kw, k, v)             Keyword.put_new(kw, k, v)
Keyword.delete(kw, k)             Keyword.merge(a, b)
Keyword.has_key?(kw, k)           Keyword.validate!(kw, [:a, b: 1])
Keyword.keyword?(term)            Keyword.new(enum)
```

## List

```elixir
[head | tail] = list              list ++ other        # O(length left)
hd(list)                          tl(list)
length(list)                      # O(n) — avoid on hot paths
List.first(list)                  List.last(list)
List.flatten(list)                List.duplicate(x, n)
List.keyfind(list, k, pos)        List.keydelete(list, k, pos)
List.keymember?(list, k, pos)     List.replace_at(list, i, x)
List.insert_at(list, i, x)        List.delete_at(list, i)
List.update_at(list, i, fn)       List.to_tuple(list)
Enum.reverse(list)                # O(n)
Enum.sort(list)                   Enum.sort_by(list, fn)
```

## String

```elixir
String.trim(s)                    String.trim_leading(s, p)
String.trim_trailing(s, p)        String.downcase(s)
String.upcase(s)                  String.capitalize(s)
String.replace(s, a, b)           String.replace(s, ~r/../, b)
String.split(s, d)                String.split(s, d, parts: n)
String.contains?(s, p)            String.starts_with?(s, p)
String.ends_with?(s, p)           String.length(s)     # grapheme count, O(n)
byte_size(s)                      # byte count, O(1)
String.to_integer(s)              String.to_existing_atom(s)
String.slice(s, start, len)       String.pad_leading(s, n, pad)
String.pad_trailing(s, n, pad)
Integer.parse(s)                  Float.parse(s)
"#{a} and #{b}"                   # interpolation — preferred over <>
```

## File / Path / System

```elixir
File.read(path)                   File.read!(path)
File.write(path, content)         File.write!(path, content)
File.exists?(path)                File.dir?(path)
File.mkdir_p(path)                File.mkdir_p!(path)
File.rm(path)                     File.rm_rf(path)
File.cp(src, dst)                 File.cp_r(src, dst)
File.ls(path)                     File.stream!(path)
File.stat(path)                   File.cwd!()

Path.join(a, b)                   Path.join([a, b, c])
Path.expand(relative, __DIR__)    Path.basename(path)
Path.dirname(path)                Path.extname(path)
Path.rootname(path)               Path.relative_to_cwd(path)

System.fetch_env!("DATABASE_URL") System.get_env("VAR", "default")
System.monotonic_time(:millisecond)  System.system_time(:second)
System.cmd("cmd", args)           System.cwd!()
```

## Regex

```elixir
~r/pattern/flags                  # i=case-insensitive, u=unicode, m=multiline
Regex.match?(~r/.../, s)          Regex.run(~r/(\w+)/, s)
Regex.scan(~r/\d+/, s)            Regex.named_captures(~r/(?<y>\d+)/, s)
Regex.replace(~r/.../, s, fn)     Regex.split(~r/\s/, s)
```

## Date / Time

```elixir
DateTime.utc_now()                DateTime.from_iso8601(s)
DateTime.to_iso8601(dt)           DateTime.diff(a, b, :second)
DateTime.compare(a, b)            DateTime.add(dt, n, :second)
DateTime.shift(dt, months: 1)     # Elixir 1.17+

Date.utc_today()                  Date.from_iso8601(s)
Date.diff(a, b)                   Date.compare(a, b)
Date.add(date, days)              Date.day_of_week(date)

NaiveDateTime.utc_now()
Time.utc_now()

Calendar.strftime(dt, "%Y-%m-%d %H:%M:%S")
```

## Process

```elixir
self()                            spawn(fn -> ... end)
spawn_link(fn -> ... end)         spawn_monitor(fn -> ... end)
Process.alive?(pid)               Process.exit(pid, reason)
Process.monitor(pid)              Process.demonitor(ref, [:flush])
Process.link(pid)                 Process.unlink(pid)
Process.send(pid, msg, opts)      Process.send_after(pid, msg, ms)
Process.cancel_timer(ref)         Process.flag(:trap_exit, true)
Process.whereis(name)             Process.register(pid, name)
Process.info(pid)                 Process.info(pid, :message_queue_len)
```

## Erlang stdlib — daily picks

```elixir
:timer.send_after(5_000, self(), :tick)
:timer.tc(fn -> work() end)                  # {microseconds, result}
:queue.new() |> :queue.in(:a) |> :queue.out()

:ets.new(:t, [:named_table, :public, read_concurrency: true])
:ets.insert(:t, {key, val})       :ets.lookup(:t, key)
:ets.delete(:t, key)              :ets.update_counter(:t, k, {2, 1}, {k, 0})

:persistent_term.put({MyApp, :cfg}, val)
:persistent_term.get({MyApp, :cfg})

:crypto.strong_rand_bytes(32)
:crypto.hash(:sha256, data)
:crypto.mac(:hmac, :sha256, key, msg)

:rand.uniform()                   :rand.uniform(n)
:math.log2(x)                     :math.sqrt(x)

:erlang.system_info(:process_count)
:erlang.system_info(:schedulers)
```

## JSON (Elixir 1.18+) / Jason

```elixir
# Built-in (Elixir 1.18+)
JSON.encode!(%{a: 1})             JSON.decode!(~s({"a":1}))

# Jason (older Elixir / feature parity)
Jason.encode!(%{a: 1})            Jason.decode!(~s({"a":1}))
Jason.decode!(~s({"a":1}), keys: :atoms)         # DANGEROUS with user input
Jason.decode!(~s({"a":1}), keys: :existing_atoms) # Safer
```

## URI / Base

```elixir
URI.parse("https://x.com/path?q=1")
URI.encode_query(%{q: "hello"})
URI.decode_query("q=hello")
URI.encode("hello world")          URI.decode(encoded)

Base.encode64(binary)              Base.decode64!(s)
Base.encode16(binary)              Base.decode16!(s)
Base.url_encode64(binary)          Base.url_decode64!(s)
```

## Access / Nested data

```elixir
get_in(map, [:a, :b, :c])                   # nil on any missing key
put_in(map, [:a, :b, :c], value)
update_in(map, [:a, :b, :c], fn v -> v + 1 end)
pop_in(map, [:a, :b, :c])                   # {value, rest_of_map}

# With Access helpers
get_in(list, [Access.all(), :name])         # All names in a list of maps
update_in(list, [Access.filter(& &1.active), :count], & &1 + 1)
```

## Logger — levels

```elixir
Logger.debug("...")               Logger.info("...", meta: value)
Logger.notice("...")              Logger.warning("...")
Logger.error("...")

# Structured metadata
Logger.info("order completed", order_id: id, total: amount)

# Lazy message — closure only runs if level enabled
Logger.debug(fn -> "state: #{inspect(compute_heavy())}" end)
```

## Supervision child specs

```elixir
# Module child spec (module defines child_spec/1)
MyApp.Worker
{MyApp.Worker, opt: val}

# Full child spec map
%{
  id: :unique_id,
  start: {MyApp.Worker, :start_link, [args]},
  restart: :permanent,          # :permanent | :transient | :temporary
  type: :worker,                # :worker | :supervisor
  shutdown: 5_000
}
```

---

## Cross-References

- **Daily call patterns** (not just signatures): `./data-reference.md`, `./idioms-reference.md`, `./otp-callbacks.md`
- **Full stdlib reference** with parameter details and examples: parent `elixir` skill's `quick-references.md`
