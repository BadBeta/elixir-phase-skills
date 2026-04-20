# Data Structures — Implementation Reference

Phase-focused on **writing** code that manipulates Elixir data structures. Covers maps, structs, keywords, tuples, lists, MapSet, binaries, IO lists — with call signatures, performance characteristics, and common operations.

**For architectural choices** (which structure fits the domain model?), see `../elixir-planning/SKILL.md`.

---

## Performance Cheat Sheet — Operation Complexity

| Op | List | Map | Tuple | Keyword | MapSet |
|---|---|---|---|---|---|
| Prepend (head) | O(1) | — | — | O(1) | — |
| Append | O(n) | — | — | O(n) | — |
| Random access | O(n) | O(log n) | O(1) | O(n) | — |
| Update by key | — | O(log n) | O(1)† | O(n) | — |
| Membership check | O(n) | O(log n) | O(n) | O(n) | O(log n) |
| Size | O(n) (`length`) | O(1) (`map_size`) | O(1) (`tuple_size`) | O(n) | O(log n) |
| Iteration | linear | linear | linear | linear | linear |

† `put_elem/3` rebuilds the tuple — still O(n) in memory, but O(1) in direct-access time.

**Rule of thumb:**
- **List** when you prepend a lot or iterate sequentially.
- **Map** when keys are dynamic (user input, arbitrary strings) and you need lookup.
- **Tuple** when the structure is fixed and small (≤ ~5 elements), and position matters.
- **Keyword** when keys are compile-time atoms and you might have duplicates (opts, filters).
- **MapSet** when you need membership checks and set operations.

---

## Maps

### Literals & access

```elixir
# Literal forms
%{"a" => 1, "b" => 2}                    # string keys
%{a: 1, b: 2}                            # atom-key shorthand (keys must be atoms)
%{:a => 1, 2 => :b, "c" => [1, 2]}       # mixed keys

# Access — atom-key shorthand works only for atom keys
m.a                    # atom-key only (raises if :a missing)
m[:a]                  # returns nil if :a missing
m["a"]                 # string key

# Map.get — with default
Map.get(m, :key, :default_value)

# Map.fetch — returns :ok tuple
{:ok, v} = Map.fetch(m, :key)
:error = Map.fetch(m, :missing)

# Map.fetch! — raises on missing
v = Map.fetch!(m, :key)
```

### Put / update / delete

```elixir
# Put (creates or overwrites)
Map.put(m, :k, v)                        # %{m | :k => v} only if :k exists
%{m | :k => v}                           # strict — raises if :k doesn't exist

# Update with fallback
Map.put_new(m, :k, v)                    # Insert only if absent
Map.update(m, :k, default, fn v -> v + 1 end)
Map.update!(m, :k, fn v -> v + 1 end)    # Raises if :k absent

# Pop & delete
{value, rest} = Map.pop(m, :k)
{value, rest} = Map.pop!(m, :k)          # Raises if absent
m_without_k = Map.delete(m, :k)
m = Map.drop(m, [:a, :b])                # Remove multiple
m = Map.take(m, [:a, :b])                # Keep only these
```

### Transform

```elixir
Map.new(enum)                            # [{k,v}, ...] → map
Map.new(enum, fn {k, v} -> {k, v * 2} end)  # transform + collect

Map.keys(m)
Map.values(m)
Map.to_list(m)

Map.merge(m1, m2)                        # m2 wins on conflict
Map.merge(m1, m2, fn _k, v1, v2 -> v1 + v2 end)  # custom merge

Map.split(m, [:a, :b])                   # {taken_map, rest_map}

Map.filter(m, fn {_k, v} -> v > 0 end)
Map.reject(m, fn {_k, v} -> v > 0 end)
```

### Nested update

```elixir
# put_in / update_in / get_in — for nested structures
put_in(user, [:address, :city], "Oslo")
update_in(user, [:stats, :count], &(&1 + 1))
get_in(user, [:address, :city])

# With dynamic access (Access.key!)
update_in(user, [Access.key!(:address), Access.key!(:city)], fn _ -> "Oslo" end)

# Macro form (when all keys are static)
%{user | address: %{user.address | city: "Oslo"}}
```

---

## Structs

### Definition

```elixir
defmodule MyApp.User do
  @enforce_keys [:email]
  defstruct [
    :id,
    :email,
    :name,
    role: :user,
    active?: true,
    tags: []
  ]
end
```

**`@enforce_keys`** raises at compile time if a required key is missing on `%User{}` construction.

### Construction

```elixir
%User{email: "a@b.com"}
%User{email: "a@b.com", name: "Alice", role: :admin}
struct(User, %{email: "a@b.com"})        # From arbitrary enumerable
struct!(User, %{email: "a@b.com"})       # Raises on unknown keys
```

### Update

```elixir
%{user | name: "Bob"}                    # GOOD — raises on unknown key
Map.put(user, :name, "Bob")              # BAD — silently accepts typos
```

### Nested struct update

```elixir
# With put_in / update_in
update_in(user.address.city, fn _ -> "Oslo" end)   # New Elixir 1.14+ macro

# Or with struct update syntax nested
%{user | address: %{user.address | city: "Oslo"}}
```

### Struct in pattern match

```elixir
def permit?(%User{role: :admin}), do: true
def permit?(%User{role: :user, active?: true}), do: true
def permit?(%User{}), do: false
```

### Derived protocols

```elixir
defmodule MyApp.User do
  @derive {Jason.Encoder, only: [:id, :email, :name]}
  @derive {Inspect, only: [:id, :email]}  # exclude password from inspect
  defstruct [...]
end
```

---

## Keyword Lists

Ordered list of 2-tuples with atom keys; duplicates allowed.

```elixir
[foo: 1, bar: 2, foo: 3]                 # Syntactic sugar
[{:foo, 1}, {:bar, 2}, {:foo, 3}]        # Explicit

# Access — first match wins
Keyword.get(opts, :foo)                  # 1 (not 3)
Keyword.get_values(opts, :foo)           # [1, 3]
Keyword.fetch(opts, :foo)                # {:ok, 1}

# Update
Keyword.put(opts, :new, :v)              # [{:new, :v} | opts]
Keyword.put_new(opts, :new, :v)
Keyword.delete(opts, :foo)               # Removes ALL :foo

# Merge (with right-bias)
Keyword.merge(defaults, overrides)

# Validate (Elixir 1.13+)
Keyword.validate!(opts, [:timeout, {:retries, 3}])
# Raises ArgumentError for any key not in the whitelist; fills defaults for tuple form
```

**When to use:** function options, filter clauses in Ecto queries, configuration.

**When NOT to use:** large dynamic data (use Map) or key-value with non-atom keys.

---

## Tuples

Fixed-size, positional.

```elixir
t = {:ok, value}
t = {1, :a, "b", [1, 2]}

# Size
tuple_size(t)                            # 4

# Access (0-indexed)
elem(t, 1)                               # :a
put_elem(t, 1, :z)                       # {1, :z, "b", [1, 2]} — new tuple

# Convert
Tuple.to_list({:a, :b, :c})              # [:a, :b, :c]
List.to_tuple([:a, :b, :c])              # {:a, :b, :c}
Tuple.insert_at({1, 3}, 1, 2)            # {1, 2, 3}
Tuple.delete_at({1, 2, 3}, 1)            # {1, 3}
Tuple.append({1, 2}, 3)                  # {1, 2, 3}
```

**When to use:**
- Tagged returns: `{:ok, value}`, `{:error, reason}`.
- Multiple named values: `{pid, ref}`.
- Fixed-arity records — Erlang pattern.

**When NOT to use:** variable-size collections (use list or map).

---

## Lists

Linked lists — head/tail access fast, random access slow.

```elixir
list = [1, 2, 3, 4]

# Prepend — O(1)
new_list = [0 | list]

# Head / tail
hd([1, 2, 3])                            # 1
tl([1, 2, 3])                            # [2, 3]

# Pattern match head
[first | rest] = [1, 2, 3]
[first, second | rest] = [1, 2, 3, 4]

# Length — O(n)!
length(list)

# Check emptiness — O(1)
case list do
  [] -> :empty
  [_ | _] -> :non_empty
end

# Append — O(m + n) — prefer prepending and reversing, or use IO list
[1, 2] ++ [3, 4]                         # [1, 2, 3, 4]

# Reverse
Enum.reverse([1, 2, 3])                  # [3, 2, 1]

# Flatten nested lists
List.flatten([[1, [2]], [3, 4]])         # [1, 2, 3, 4]

# Subtract
[1, 2, 3, 2, 1] -- [2, 4]                # [1, 3, 2, 1] (first :2 removed only)
```

### Keyfind / keymember — for list of tuples

```elixir
pairs = [{:a, 1}, {:b, 2}, {:c, 3}]

List.keyfind(pairs, :b, 0)               # {:b, 2}
List.keymember?(pairs, :c, 0)            # true
List.keyreplace(pairs, :b, 0, {:b, 20})
List.keydelete(pairs, :b, 0)
```

---

## MapSet

Unordered collection of unique values. O(log n) membership, union, intersection.

```elixir
s = MapSet.new()
s = MapSet.new([1, 2, 3])
s = MapSet.new([1, 2, 2, 3])             # dedupes

MapSet.put(s, 4)
MapSet.delete(s, 2)
MapSet.member?(s, 3)                     # true
MapSet.size(s)

# Set operations
MapSet.union(s1, s2)
MapSet.intersection(s1, s2)
MapSet.difference(s1, s2)                # s1 - s2
MapSet.disjoint?(s1, s2)
MapSet.subset?(s1, s2)

# Conversions
MapSet.to_list(s)
Enum.into(list, MapSet.new())
```

**When to use:** dedupe, membership checks where O(n) list scan is too slow, set algebra (union/intersection).

---

## Ranges

Lazy integer ranges — constant memory.

```elixir
1..10                                    # Inclusive range, step 1
1..10//2                                 # Step 2: 1, 3, 5, 7, 9
10..1//-1                                # Descending

Enum.to_list(1..5)                       # [1, 2, 3, 4, 5]
Enum.member?(1..100_000, 42)             # true — O(1) for ranges
Enum.count(1..1_000_000)                 # 1_000_000 — O(1)

# Iterate
for i <- 1..n, do: do_work(i)

# Pattern match a range
def in_range(n) when n in 1..10, do: :ok
```

---

## Binaries & Strings

Elixir strings are UTF-8 binaries. Raw bytes use binary syntax `<<...>>`.

### Literal forms

```elixir
"hello"                                  # UTF-8 binary
<<104, 105>>                             # "hi" as raw bytes
<<1, 2, 3>>                              # byte sequence
<<1::8, 2::16>>                          # with bit-width specifiers
<<"hello", 0, "world">>                  # mixed
```

### String operations

```elixir
# Byte vs char vs grapheme
byte_size("héllo")                       # 6 (é is 2 bytes in UTF-8)
String.length("héllo")                   # 5 (graphemes)
String.graphemes("héllo")                # ["h", "é", "l", "l", "o"]
String.codepoints("héllo")               # ["h", "é", "l", "l", "o"] (Unicode code points)

# Access
String.at("hello", 1)                    # "e"
String.slice("hello", 1, 3)              # "ell"
String.slice("hello", 1..3)              # "ell"

# Modify
String.upcase("abc")
String.downcase("ABC")
String.capitalize("hello world")         # "Hello world"
String.trim("  hi  ")
String.trim_leading(str, "x")
String.pad_leading("42", 5, "0")         # "00042"

# Split/join
String.split("a,b,c", ",")               # ["a", "b", "c"]
String.split("a b  c")                   # splits on whitespace
Enum.join(["a", "b"], ", ")              # "a, b"

# Search
String.contains?("hello", "ell")
String.starts_with?("hello", "he")
String.ends_with?("hello", "lo")
String.replace("a,b,c", ",", ";")

# Convert
String.to_integer("42")
String.to_float("3.14")
String.to_atom("foo")                    # DANGER — unbounded atom creation
String.to_existing_atom("foo")           # Safe — raises if atom doesn't exist
```

**Atom safety:** NEVER call `String.to_atom/1` on user input. Use `String.to_existing_atom/1` or reject upfront.

### Binary pattern matching

```elixir
<<header::binary-size(4), rest::binary>> = data
<<len::32, payload::binary-size(len), rest::binary>> = packet

# Common specifiers
<<value::integer>>              # default: 8-bit integer
<<value::8>>                    # 1 byte (8 bits)
<<value::16>>                   # 2 bytes
<<value::32>>                   # 4 bytes
<<value::64>>                   # 8 bytes
<<value::16-little>>            # little-endian
<<value::16-big>>               # big-endian (default for network)
<<value::float>>                # 64-bit IEEE
<<value::float-32>>             # 32-bit float
<<value::binary>>               # remainder as binary
<<value::binary-size(n)>>       # exactly n bytes
<<bit::1>>                      # single bit
<<flag::1, rest::7>>            # 1 bit + 7 bits
<<value::utf8>>                 # single UTF-8 codepoint
```

### Binary construction

```elixir
<<1, 2, 3>>                     # 3-byte binary
<<0x42, 0xFF>>                  # hex
<<len::32, data::binary>>       # frame with length prefix
<<"header", value::16, "footer">>

# Dynamic
frame = <<byte_size(payload)::32, payload::binary>>
```

### Binary comprehension

```elixir
# Iterate over binary
for <<r, g, b <- pixels>>, do: brightness(r, g, b)

# Parse structured binary
for <<id::32, kind::8, rest::binary-8 <- records>>, do: {id, kind, rest}
```

---

## IO Lists

A list where each element is a byte, binary, or IO list. Built cheaply, flushed to I/O in one pass.

```elixir
# Small IO list
iodata = ["Hello, ", name, "!\n"]

# Flatten to binary
IO.iodata_to_binary(iodata)               # "Hello, Alice!\n"

# Size (bytes)
IO.iodata_length(iodata)

# Pass to I/O directly — no flattening needed
IO.write(iodata)
IO.puts(iodata)
File.write!(path, iodata)
:gen_tcp.send(socket, iodata)
```

### When to build with IO lists

```elixir
# BAD — O(n²) string concatenation
Enum.reduce(parts, "", fn p, acc -> acc <> p end)

# GOOD — IO list, O(n)
parts                                     # Already iodata
|> IO.iodata_to_binary()

# OR — write directly to I/O
File.write!(path, parts)
```

---

## Ecto.Embedded & Embedded Schemas

For nested data that doesn't need its own table:

```elixir
defmodule MyApp.Address do
  use Ecto.Schema
  import Ecto.Changeset

  embedded_schema do
    field :street, :string
    field :city, :string
    field :zip, :string
  end

  def changeset(address, attrs), do:
    cast(address, attrs, [:street, :city, :zip])
end

# In parent schema:
schema "users" do
  embeds_one :address, MyApp.Address
  embeds_many :phone_numbers, MyApp.PhoneNumber
end
```

---

## Erlang Queue / Ordsets / Digraph

Useful Erlang stdlib structures:

### `:queue` — FIFO queue (O(1) in/out)

```elixir
q = :queue.new()
q = :queue.in(:a, q)                     # Add to rear
q = :queue.in(:b, q)
{:value, :a} = :queue.peek(q)
{{:value, :a}, q} = :queue.out(q)        # Pop front
:queue.len(q)
:queue.is_empty(q)
:queue.to_list(q)
```

### `:ordsets` — sorted list as set

```elixir
s = :ordsets.new()
s = :ordsets.add_element(3, s)
s = :ordsets.add_element(1, s)           # Kept sorted
:ordsets.is_element(2, s)
:ordsets.union(s1, s2)
```

### `:digraph` — mutable directed graph (unlike most Elixir data, this IS mutable; uses ETS under the hood)

```elixir
g = :digraph.new()
v1 = :digraph.add_vertex(g, :alice)
v2 = :digraph.add_vertex(g, :bob)
:digraph.add_edge(g, v1, v2)

:digraph.vertices(g)
:digraph.edges(g)
:digraph.get_path(g, v1, v2)
:digraph.delete(g)                       # MUST clean up — ETS-backed
```

---

## Access Behaviour — Custom `[]` Access

For a struct to support bracket access (`my_struct[:key]`), implement the `Access` behaviour:

```elixir
defmodule MyApp.Config do
  @behaviour Access

  defstruct [:timeout, :retries]

  @impl true
  def fetch(%__MODULE__{} = struct, key), do: Map.fetch(struct, key)

  @impl true
  def get_and_update(struct, key, fun) do
    {old_value, new_map} = Map.get_and_update(struct, key, fun)
    {old_value, struct(__MODULE__, new_map)}
  end

  @impl true
  def pop(struct, key) do
    {value, map} = Map.pop(Map.from_struct(struct), key)
    {value, struct(__MODULE__, map)}
  end
end
```

Alternatively, use `@derive Access` to generate defaults.

---

## Common Anti-Patterns (BAD / GOOD)

### 1. `Map.put` for struct update

```elixir
# BAD — silently accepts typos
Map.put(user, :emali, "x@y")             # typo: emali

# GOOD — raises on unknown field
%{user | email: "x@y"}
```

### 2. `String.to_atom/1` on user input

```elixir
# BAD — unbounded atom creation; DoS vector
String.to_atom(user_input)
```

```elixir
# GOOD
String.to_existing_atom(user_input)
# or validate against whitelist first
if input in ["active", "inactive"], do: String.to_existing_atom(input)
```

### 3. String concatenation in a loop

```elixir
# BAD — O(n²)
parts |> Enum.reduce("", fn p, acc -> acc <> p <> ", " end)
```

```elixir
# GOOD — IO list
parts |> Enum.intersperse(", ") |> IO.iodata_to_binary()
```

### 4. `length/1` for emptiness

```elixir
# BAD — traverses full list
if length(list) == 0, do: :empty
```

```elixir
# GOOD
if list == [], do: :empty
# OR
case list do
  [] -> :empty
  _ -> :non_empty
end
```

### 5. Atom keys vs string keys inconsistency

```elixir
# BAD — mixing silently
data = %{"a" => 1, :b => 2}
data[:a]                                 # nil — looked up :a, not "a"
```

```elixir
# GOOD — pick one
# For internal data: atom keys
# For external (JSON/user): string keys, convert at boundary
```

### 6. Appending to lists in a hot path

```elixir
# BAD — O(n) per append
Enum.reduce(items, [], fn i, acc -> acc ++ [transform(i)] end)
```

```elixir
# GOOD — prepend, then reverse; or use Enum.map
Enum.reduce(items, [], fn i, acc -> [transform(i) | acc] end) |> Enum.reverse()
# OR simpler:
Enum.map(items, &transform/1)
```

---

## Cross-References

- **Idiomatic use of Enum/Stream/for over these structures:** `./idioms-reference.md`
- **Types & specs (`@type` for data structures):** `./type-and-docs.md`
- **Stdlib data-structure reference (deep):** `../elixir/data-structures.md`
- **Binary protocol framing (over sockets):** `./networking-patterns.md`
- **Data ownership (which context owns which schema):** `../elixir-planning/data-ownership-deep.md`
