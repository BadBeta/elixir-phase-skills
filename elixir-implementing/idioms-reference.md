# Idioms Reference — Implementation Patterns

Phase-focused on **writing** idiomatic Elixir. Covers pattern matching, guards, `with`, `case`, `cond`, pipelines, comprehensions, `Enum`/`Stream`, captures — the language-construct syntax patterns.

**For architectural choices** (which pattern fits the domain model?), see `../elixir-planning/SKILL.md` §patterns.

---

## Rules for Writing Idiomatic Constructs

1. **ALWAYS prefer pattern matching in function heads** over `case` in the body.
2. **ALWAYS use `with` for 2+ chained ok/error ops**. For 1 op, use `case`. For no data flow between, use sequential statements.
3. **NEVER end a single-step pipeline with `|> case do`.** Assign an intermediate variable or call directly.
4. **ALWAYS use `for` comprehensions** for map-filter combinations over a single source.
5. **ALWAYS use function captures** (`&Mod.fun/1`) over anonymous wrappers (`fn x -> Mod.fun(x) end`) when arity matches.
6. **NEVER use `Enum.each/2` to accumulate.** Use `map`, `reduce`, `filter`, or a `for` comprehension.
7. **ALWAYS use guards in function heads** over `if` in the body when branching on argument types/ranges.
8. **NEVER use `try/rescue` for expected failures.** Return `{:ok, _}` / `{:error, _}` tuples.

---

## Pattern Matching in Function Heads

### Struct-type dispatch

```elixir
def handle(%Click{} = event), do: handle_click(event)
def handle(%Submit{} = event), do: handle_submit(event)
def handle(%Hover{} = event), do: handle_hover(event)
```

### Map-key presence dispatch

```elixir
def process(%{type: :email} = data), do: send_email(data)
def process(%{type: :sms} = data), do: send_sms(data)
def process(%{type: :push} = data), do: send_push(data)
```

### Tagged-tuple dispatch

```elixir
def render({:ok, value}), do: {:safe, Phoenix.HTML.Tag.content_tag(:pre, inspect(value))}
def render({:error, :not_found}), do: {:safe, "<em>Not found</em>"}
def render({:error, reason}), do: {:safe, "Error: #{inspect(reason)}"}
```

### List head/tail dispatch (tail recursion)

```elixir
def sum([head | tail], acc), do: sum(tail, acc + head)
def sum([], acc), do: acc

# Invocation with default accumulator
def sum(list), do: sum(list, 0)
```

### Pin operator (match against existing binding)

```elixir
target_id = 42

case user do
  %{id: ^target_id} = user -> {:ok, user}
  _ -> {:error, :mismatch}
end
```

### Pin operator — advanced uses

**Pin as map key** (essential for dynamic key lookup):

```elixir
# Without the pin, `key` would be bound to whatever key matches first
key = :email
%{^key => value} = %{email: "a@b.c", name: "Alice"}
# value = "a@b.c"
```

**Double pin** (assert both key AND value):

```elixir
expected_id = 42
expected_role = :admin

case user do
  %{id: ^expected_id, role: ^expected_role} -> :match
  _ -> :mismatch
end
```

**Pin in `receive` — correlate async responses** (the definitive use case):

```elixir
# Send a request with a unique ref; only accept the matching reply
ref = make_ref()
send(worker, {:request, self(), ref, payload})

receive do
  {:reply, ^ref, result} -> {:ok, result}
after
  5_000 -> {:error, :timeout}
end
# Other messages with different refs stay in the mailbox
```

**Pin in comprehension generators** (filter by known value):

```elixir
target_user_id = 42

# Only select events for the target user
for {:event, %{user_id: ^target_user_id} = e} <- events, do: e
```

**Pin with pattern match on function args:**

```elixir
def toggle(%User{role: role} = user, role) do
  # role argument pinned against the struct field — matches only when they agree
  {:ok, user}
end

def toggle(_user, _), do: {:error, :role_mismatch}
```

### String prefix matching with `<>`

`<>` in a pattern matches a **prefix** (not suffix, not middle):

```elixir
# Extract token after "Bearer " prefix
case header do
  "Bearer " <> token -> {:ok, token}
  _ -> {:error, :invalid_auth}
end

# Parse command-like strings
def handle_command("/quit" <> _rest), do: :quit
def handle_command("/join " <> channel), do: {:join, channel}
def handle_command("/msg " <> rest) do
  [user, message] = String.split(rest, " ", parts: 2)
  {:msg, user, message}
end
def handle_command(text), do: {:say, text}

# Multi-level dispatch on prefixes
def route("api/v1/" <> path), do: v1_route(path)
def route("api/v2/" <> path), do: v2_route(path)
```

**Constraint:** the LHS of `<>` must be a **literal** string. `prefix <> rest` where `prefix` is a variable does not work for pattern matching.

```elixir
# BAD — doesn't compile; prefix must be literal
def strip(prefix <> rest, prefix), do: rest

# GOOD
def strip(str, prefix) do
  if String.starts_with?(str, prefix) do
    String.replace_prefix(str, prefix, "")
  else
    str
  end
end
```

**Suffix matching:** `<>` cannot match suffixes. Use `String.ends_with?/2`:

```elixir
if String.ends_with?(filename, ".ex"), do: compile(filename)
```

### Default arguments with multi-clause — header clause

When combining default arguments (`\\`) with multiple function clauses, define a **header** that lists the defaults:

```elixir
# Header — defines defaults ONCE; no body
def fetch(url, opts \\ [])

# Clauses follow, without repeating defaults
def fetch(url, []), do: fetch_default(url)
def fetch(url, opts) when is_list(opts), do: fetch_with_opts(url, opts)
```

**Why a header is required:** Elixir forbids repeating defaults in multiple clauses — it would be ambiguous which clause's defaults apply when the caller omits args.

```elixir
# BAD — won't compile: defaults in multiple clauses
def fetch(url, opts \\ []), do: ...
def fetch(url, opts \\ [], headers), do: ...   # error

# GOOD
def fetch(url, opts \\ [], headers \\ [])
def fetch(url, opts, []), do: fetch_basic(url, opts)
def fetch(url, opts, headers), do: fetch_with_headers(url, opts, headers)
```

**Guidance:** use the header when you have 2+ clauses; use inline defaults (`def f(x, opts \\ [])`) for single-clause functions.

### Assertive pattern matching — let it crash

When you expect a value to have a specific shape, **pattern match to assert it**. Don't extract defensively — let a `MatchError` surface the real problem.

```elixir
# BAD — defensive; hides malformed input, returns wrong value
def process(response) do
  body = Map.get(response, :body, nil)
  status = Map.get(response, :status, 0)
  # If status is 0, is that a real response or a missing key?
  handle(status, body)
end
```

```elixir
# GOOD — assertive: response MUST have status and body; crash on violation
def process(%{status: status, body: body}) do
  handle(status, body)
end
```

**When to assert vs extract:**

| Situation | Strategy |
|---|---|
| Internal data you built (structs, validated inputs) | Assertive — pattern match; crash on violation |
| External input (user params, HTTP bodies, DB rows with unknown shape) | Validate at boundary with changeset/case; extract safely |
| Optional fields | Explicit: `Map.get(m, :k, default)` or match `%{}` |
| Required fields | Assertive: `%{k: v} = m` |

**Real-world pattern:** Phoenix controllers receive `%Plug.Conn{} = conn`, not `Map.get(conn, :assigns)`. Ecto changesets destructure as `%Changeset{valid?: true, changes: changes} = cs`. Assertive destructuring surfaces bugs early.

### Membership and computed-value dispatch → multi-clause with guards

When the branching decision is "is the argument in this set?" or "does this computed property hold?", multi-clause functions with guards read cleaner than `if ... in ... else` or `case computed() do`.

**Membership:**

```elixir
@boxes [Blackboxes.Arithmetic, Blackboxes.Logic, Blackboxes.Comparison, Blackboxes.StringOps]

# BAD — if/else on membership
def execute(module, i, a, b) do
  if module in @boxes do
    module.execute(i, a, b)
  else
    {:error, {:unknown_blackbox, module}}
  end
end

# GOOD — multi-clause with guard + catch-all
def execute(module, i, a, b) when module in @boxes, do: module.execute(i, a, b)
def execute(module, _i, _a, _b), do: {:error, {:unknown_blackbox, module}}
```

The guard version reads as a definition ("when the module is known"), exposes the branching logic in the function head (where pattern matching belongs), and avoids the nesting of `if/else`.

**Computed value:**

```elixir
# BAD — case on a computed value
defp validate(v) when is_binary(v) do
  case byte_size(v) do
    n when n <= @max -> {:ok, v}
    n -> {:error, {:too_long, n}}
  end
end

# GOOD — push the computation into a guard
defp validate(v) when is_binary(v) and byte_size(v) <= @max, do: {:ok, v}
defp validate(v) when is_binary(v), do: {:error, {:too_long, byte_size(v)}}
```

The guard form keeps the "happy path" first-line and eliminates the inner case scaffold.

**When NOT to use multi-clause:** if the guard would be long or repeated across many branches, a `case` body with guards is clearer. But for 2-3 clauses with simple membership/computed-value tests, multi-clause wins.

---

## Guards

### Common guard functions

```elixir
# Type guards: is_integer, is_float, is_binary, is_list, is_map, is_tuple,
#              is_atom, is_nil, is_boolean, is_function, is_pid, is_port, is_reference,
#              is_struct(term, module)

def process(x) when is_integer(x) and x >= 0, do: process_nat(x)
def process(x) when is_binary(x), do: String.to_integer(x) |> process()
def process(list) when is_list(list), do: Enum.reduce(list, 0, &+/2)
```

### Range guards

```elixir
def month_name(m) when m in 1..12, do: # ...
def weekday(d) when d in [:mon, :tue, :wed, :thu, :fri], do: true
def weekday(d) when d in [:sat, :sun], do: false
```

### Multiple `when` clauses — OR semantics

```elixir
defp escape_char(char)
     when char in 0x2061..0x2064
     when char in [0x061C, 0x200E, 0x200F]
     when char in 0x202A..0x202E do
  # matches if ANY of the when clauses is true
end
```

### Custom guards (`defguard`)

```elixir
defmodule MyApp.Guards do
  defguard is_positive(n) when is_number(n) and n > 0
  defguard is_non_empty_string(s) when is_binary(s) and byte_size(s) > 0
  defguard is_valid_id(id) when is_integer(id) and id > 0
end

# Usage
defmodule MyApp.Users do
  import MyApp.Guards

  def get(id) when is_valid_id(id), do: Repo.get(User, id)
end
```

### Guards on struct fields (direct dot-access)

```elixir
# Works because structs are maps
def feature_enabled?(config) when config.feature_x?, do: true
def feature_enabled?(_), do: false
```

### Allowed in guards

`==`, `!=`, `===`, `!==`, `<`, `>`, `<=`, `>=`, `and`, `or`, `not`, `in`, `+`, `-`, `*`, `/`, `abs`, `div`, `rem`, `round`, `trunc`, `is_atom`, `is_binary`, `is_integer`, `is_float`, `is_list`, `is_map`, `is_tuple`, `is_nil`, `is_boolean`, `is_number`, `is_pid`, `is_struct`, `is_function`, `byte_size`, `elem`, `hd`, `tl`, `length`, `map_size`, `tuple_size`, `is_map_key`, `Bitwise.*` (after `import Bitwise`).

**NOT allowed:** `String.length`, `Enum.*`, or any user-defined function that isn't a `defguard`.

---

## `case` / `cond` / `if` — Syntax Patterns

### `case` — branch on a value's shape

```elixir
case fetch_user(id) do
  {:ok, %User{active?: true} = user} -> {:ok, user}
  {:ok, %User{active?: false}} -> {:error, :inactive}
  {:error, :not_found} -> {:error, :not_found}
end
```

### `cond` — multi-condition branching

```elixir
cond do
  score >= 90 -> :a
  score >= 80 -> :b
  score >= 70 -> :c
  score >= 60 -> :d
  true -> :f
end
```

**Always include `true -> ...`** as the last clause; `cond` raises if no clause matches.

### `if` — simple boolean gate

```elixir
if stream?, do: stream_result(items), else: batch_result(items)

# One-liner:
if count > 0, do: "#{count} items"

# Returning nil is idiomatic when the else is absent:
if error, do: log_error(error)  # returns nil if no error
```

---

## `with` Chains — Ok/Error Flow

### Basic

```elixir
with {:ok, user} <- Accounts.get_user(id),
     {:ok, post} <- Content.create_post(user, attrs),
     {:ok, _sub} <- Notifications.subscribe(user.id, post.id) do
  {:ok, post}
else
  {:error, reason} -> {:error, reason}
end
```

### Multiple error paths

```elixir
with {:ok, user} <- Accounts.get_user(id),
     {:ok, profile} <- Accounts.get_profile(user) do
  {:ok, %{user: user, profile: profile}}
else
  {:error, :user_not_found} -> {:error, "User does not exist"}
  {:error, :no_profile} -> {:error, "Profile incomplete"}
  {:error, reason} -> {:error, inspect(reason)}
end
```

### Naked `with` (no else — errors bubble up transparently)

```elixir
# If any step returns non-{:ok, _}, that value is returned unchanged
with {:ok, user} <- Accounts.get_user(id),
     {:ok, token} <- Tokens.generate(user) do
  {:ok, token}
end
```

### Mixing non-tagged expressions

```elixir
with {:ok, user} <- Accounts.get_user(id),
     true <- User.admin?(user) do
  :allow
else
  false -> {:error, :not_admin}
  {:error, _} = err -> err
end
```

**Convention:** Prefer each `<-` step to return a `{:ok, _}` / `{:error, _}` tuple. Mixing non-tagged steps (like `true`/`false`) is permissible but makes `else` harder.

### `with` pitfall — conflating missing clauses

```elixir
# BAD — both error-producers could return {:error, :bad_input}, can't distinguish
with {:ok, user} <- parse_user(input),
     {:ok, email} <- parse_email(input) do
  # ...
else
  {:error, :bad_input} -> # which one?
end

# GOOD — tag errors with context
with {:ok, user} <- parse_user(input) |> tag_error(:user),
     {:ok, email} <- parse_email(input) |> tag_error(:email) do
  # ...
else
  {:error, {:user, reason}} -> ...
  {:error, {:email, reason}} -> ...
end

defp tag_error({:ok, _} = ok, _tag), do: ok
defp tag_error({:error, reason}, tag), do: {:error, {tag, reason}}
```

---

## Pipelines

### Rule: 2+ steps, first arg is data

```elixir
# GOOD
users
|> Enum.filter(&active?/1)
|> Enum.map(&User.full_name/1)
|> Enum.sort()
```

### Anti-pattern: single-step pipeline

```elixir
# BAD
name |> String.upcase()

# GOOD
String.upcase(name)
```

### Anti-pattern: single-step → case

```elixir
# BAD
params |> validate() |> case do
  :ok -> ...
  :error -> ...
end

# GOOD
result = validate(params)
case result do
  :ok -> ...
  :error -> ...
end
```

### End-of-pipeline `case` (when pipeline is genuine)

```elixir
# OK — pipeline has real steps; case at the end
raw
|> String.trim()
|> String.split("\n")
|> Enum.reject(&(&1 == ""))
|> Enum.map(&parse_line/1)
|> case do
  [first | _] -> {:ok, first}
  [] -> {:error, :empty}
end
```

### `tap/2` — side-effect without breaking the chain

```elixir
data
|> validate()
|> tap(&Logger.debug("validated: #{inspect(&1)}"))
|> transform()
|> persist()
```

### `then/2` — apply a function mid-pipeline when data isn't first-arg

```elixir
users
|> Enum.map(&format_user/1)
|> then(&Enum.join(&1, ", "))
|> IO.puts()
```

---

## `Enum` — Common Patterns

### `map/2` with capture vs anon fn

```elixir
# GOOD
Enum.map(users, &User.name/1)
Enum.map(items, &(&1 * 2))

# BAD — anonymous fn wrapping a single call
Enum.map(users, fn u -> User.name(u) end)
```

### `filter` + `map` → `for` comprehension

```elixir
# 2-step
result =
  items
  |> Enum.filter(&active?/1)
  |> Enum.map(&format/1)

# 1-step (often more readable)
result = for item <- items, active?(item), do: format(item)
```

### `reduce` — accumulator patterns

```elixir
# Single accumulator
Enum.reduce(items, 0, &(&1.price + &2))

# Tuple accumulator (multi-state)
{sum, count} =
  Enum.reduce(items, {0, 0}, fn item, {s, c} ->
    {s + item.price, c + 1}
  end)

# Map accumulator (aggregating groups)
Enum.reduce(items, %{}, fn item, acc ->
  Map.update(acc, item.category, [item], &[item | &1])
end)
```

### `reduce_while` — early exit

```elixir
Enum.reduce_while(stream, 0, fn item, acc ->
  if acc > threshold do
    {:halt, acc}
  else
    {:cont, acc + item.size}
  end
end)
```

### `group_by/2` / `group_by/3`

```elixir
items |> Enum.group_by(& &1.category)
# %{electronics: [...], books: [...]}

items |> Enum.group_by(& &1.category, & &1.name)
# %{electronics: ["laptop", "phone"], books: ["novel"]}
```

### `frequencies/1` / `frequencies_by/2`

```elixir
Enum.frequencies(["a", "b", "a", "c", "b", "a"])
# %{"a" => 3, "b" => 2, "c" => 1}

Enum.frequencies_by(words, &String.length/1)
# %{3 => 2, 5 => 4, 8 => 1}
```

### `chunk_every` / `chunk_by`

```elixir
Enum.chunk_every(list, 100)                           # page into 100s
Enum.chunk_every(list, 3, 3, :discard)                # drop incomplete last
Enum.chunk_by(list, & &1.day)                         # group runs by key
```

### `into` — collect into a specific type

```elixir
[{:a, 1}, {:b, 2}] |> Enum.into(%{})       # → %{a: 1, b: 2}
words |> Enum.into(MapSet.new())           # → deduped set
values |> Enum.into(%{}, fn {k, v} -> {k, v * 2} end)  # → transform + into
```

### `zip` / `zip_with` / `unzip`

```elixir
Enum.zip([1, 2, 3], [:a, :b, :c])             # → [{1, :a}, {2, :b}, {3, :c}]
Enum.zip_with([1, 2], [3, 4], &(&1 + &2))     # → [4, 6]
Enum.unzip([{1, :a}, {2, :b}])                # → {[1, 2], [:a, :b]}
```

### Sorting

```elixir
Enum.sort(list)                              # default: ascending
Enum.sort(list, :desc)                       # descending
Enum.sort_by(users, & &1.inserted_at)        # by field, ascending
Enum.sort_by(users, & &1.score, :desc)       # by field, descending
Enum.sort_by(users, &{&1.role, &1.name})     # multi-key sort
```

### Looking into without breaking chain

```elixir
items
|> Enum.filter(& &1.active?)
|> Enum.count()
|> dbg()    # Debug mid-pipeline; equivalent to IO.inspect(label: "...")
|> handle_count()
```

### `with_index` — pair each element with its position

```elixir
Enum.with_index(["a", "b", "c"])          # [{"a", 0}, {"b", 1}, {"c", 2}]
Enum.with_index(["a", "b"], 1)            # [{"a", 1}, {"b", 2}]  (offset)

# Common pattern — render list with row numbers
for {item, idx} <- Enum.with_index(items), do: "#{idx + 1}. #{item.name}"

# Transforming form
Enum.with_index(list, fn x, i -> {i, transform(x)} end)
```

### Deduplication — `uniq`, `uniq_by`, `dedup`, `dedup_by`

**Uniq** removes duplicates from the whole collection (O(n) via a MapSet under the hood).
**Dedup** only collapses **consecutive** duplicates — cheap O(n), no hashing.

```elixir
Enum.uniq([1, 2, 1, 3, 2])                # [1, 2, 3]         — global
Enum.uniq_by(users, & &1.email)           # one per email     — global by key

Enum.dedup([1, 1, 2, 2, 2, 1, 3])         # [1, 2, 1, 3]      — consecutive only
Enum.dedup_by(events, & &1.type)           # collapse runs of same type
```

**When:** use `uniq` when order of first occurrence matters and the collection is small. Use `dedup` for sorted data or streaming where only run-length matters.

### Min / Max / Sum — with keys and comparators

```elixir
Enum.min(list)                            # smallest element
Enum.max(list)                            # largest
Enum.sum(list)                            # shortcut for Enum.reduce(list, 0, &+/2)
Enum.product(list)                        # multiplicative

Enum.min_by(users, & &1.age)              # user with min :age
Enum.max_by(events, & &1.priority, fn a, b -> a >= b end)  # custom comparator
Enum.min_max(list)                        # {min, max} in one pass
Enum.min_max_by(list, & &1.score)         # {min_user, max_user}
```

### `take_while` / `drop_while` / `take_every` — partial prefixes

Process only the leading run that satisfies a predicate:

```elixir
# Take events until the first shutdown
Enum.take_while(events, fn e -> e.type != :shutdown end)

# Skip header lines, process the rest
lines |> Enum.drop_while(&String.starts_with?(&1, "#")) |> parse_body()

# Every third element (sampling)
Enum.take_every(1..100, 10)               # [1, 11, 21, 31, 41, ...]
```

### `chunk_by` / `chunk_while` — run-based grouping

```elixir
# Group consecutive elements by a key
Enum.chunk_by([1, 1, 2, 3, 3, 3], & &1)
# [[1, 1], [2], [3, 3, 3]]

Enum.chunk_by(events, & &1.session_id)
# Each list is a contiguous run of events from the same session
```

`chunk_while/4` is the general-purpose stateful chunker — use when `chunk_by` isn't expressive enough:

```elixir
# Group numbers into chunks that sum to <= 10
Enum.chunk_while([1, 2, 3, 5, 4, 6, 2], 0,
  fn n, acc when acc + n <= 10 -> {:cont, [n | chunk_state(acc, n)], acc + n}
     n, acc -> {:cont, Enum.reverse(acc_to_list(acc)), n}
  end,
  fn acc -> {:cont, Enum.reverse(acc_to_list(acc)), 0} end)
```

Less commonly needed than `chunk_every`/`chunk_by` — reach for `chunk_while` only for custom grouping logic.

### `find_index`, `find_value`, `reject`

```elixir
Enum.find_index(list, &(&1 > 100))       # position of first match, or nil
Enum.find_value(list, fn u -> u.email && String.downcase(u.email) end)
# Returns the first truthy transformed value — handy for "search + transform"

Enum.reject(list, & &1.archived?)        # inverse of filter
```

### `map_intersperse` / `map_join` — build strings in one pass

```elixir
# Transform + join in one pass (avoids intermediate list)
users |> Enum.map_join(", ", & &1.name)
# "Alice, Bob, Charlie"

# Transform + intersperse (produces a list — useful for IO lists)
users |> Enum.map_intersperse("; ", & &1.name)
# ["Alice", "; ", "Bob", "; ", "Charlie"]   (returns iolist-compatible form)
```

### `zip_reduce` — fold across multiple enumerables

```elixir
# Sum two columns pair-wise
Enum.zip_reduce([1, 2, 3], [10, 20, 30], 0, fn a, b, acc -> acc + a * b end)
# 140  (= 1*10 + 2*20 + 3*30)

# Variable arity via list-of-enumerables
Enum.zip_reduce([[1, 2], [3, 4], [5, 6]], [], fn row, acc -> [Enum.sum(row) | acc] end)
# [11, 7, 3]
```

### `slice` / `at`

```elixir
Enum.at(list, 5)                          # element at index, or nil
Enum.at(list, 5, :none)                   # with default
Enum.slice(list, 2, 3)                    # 3 elements from index 2
Enum.slice(list, 2..4)                    # range slice
```

**Caveat:** `Enum.at/2` and `Enum.slice/2,3` on a list are O(n). For random access, use a tuple (`elem/2`) or map keyed by index.

### Reference — remaining common Enum functions

| Function | Purpose |
|---|---|
| `Enum.concat/1,2` | Flatten list-of-lists, or append two enumerables |
| `Enum.count/1,2` | Total count or count matching predicate |
| `Enum.empty?/1` | O(1) — preferred over `length(x) == 0` |
| `Enum.random/1`, `Enum.take_random/2` | Random picks |
| `Enum.shuffle/1` | Shuffle |
| `Enum.drop/2`, `Enum.take/2` | Drop/take N |
| `Enum.reverse/1,2` | Reverse (with tail) |
| `Enum.member?/2` | Membership check (O(n) for lists; O(log n) for MapSet) |

---

## `Stream` — Lazy Sequences

### When to reach for Stream

- Source is infinite (`Stream.iterate`, `Stream.cycle`).
- Source is large and you want to pipeline without materializing all intermediates.
- You're reading from I/O (files, DB) and want to work incrementally.

```elixir
# Lazy — nothing runs until Enum call
1..1_000_000
|> Stream.map(&expensive/1)
|> Stream.filter(& &1 > 100)
|> Enum.take(10)                # Executes just enough work to produce 10
```

### Common generators

```elixir
Stream.iterate(0, &(&1 + 1))                 # 0, 1, 2, ...
Stream.repeatedly(fn -> :rand.uniform(10) end) # infinite RNG
Stream.cycle([:a, :b, :c])                   # :a, :b, :c, :a, :b, :c, ...
Stream.unfold(0, fn n -> if n < 100, do: {n, n + 1}, else: nil end)
```

### Consuming with side effects

```elixir
File.stream!("big.csv")
|> Stream.map(&parse_line/1)
|> Stream.chunk_every(500)
|> Stream.each(&Repo.insert_all(MyTable, &1))
|> Stream.run()
```

**Use `Stream.run/1`** when only side effects matter (no result value).

### `Stream.transform/3,4,5` — stateful transformations

The Stream equivalent of `Enum.flat_map_reduce/3` + cleanup. Use when you need to emit 0..N outputs per input while threading state (parsers, chunkers, session builders).

```elixir
# Group lines into records separated by blank lines
File.stream!("events.log")
|> Stream.transform([], fn
  "", buffer -> {[Enum.reverse(buffer)], []}    # blank line flushes buffer
  line, buffer -> {[], [line | buffer]}         # accumulate non-blank
end)
|> Enum.to_list()

# With init + after (5-arity form, Elixir 1.16+) — opens and closes a resource
Stream.transform(
  0..9,
  fn -> File.open!("/tmp/log", [:write]) end,   # start
  fn i, fh -> IO.puts(fh, "tick #{i}"); {[i], fh} end,  # transform
  fn _fh -> :ok end,                             # last (before close)
  fn fh -> File.close(fh) end                    # after — cleanup
)
```

### `Stream.resource/3` — open / read / close pattern

For wrapping a resource (file handle, socket, DB cursor) as a stream with guaranteed cleanup:

```elixir
def stream_lines(path) do
  Stream.resource(
    fn -> File.open!(path, [:read]) end,          # start — returns accumulator
    fn fh ->
      case IO.read(fh, :line) do
        :eof -> {:halt, fh}                        # signal end → `after` runs
        line -> {[line], fh}                       # emit one line
      end
    end,
    fn fh -> File.close(fh) end                    # after — always runs
  )
end

stream_lines("huge.log") |> Stream.take(100) |> Enum.to_list()
# Only reads first 100 lines; close is still called
```

**Key guarantee:** the `after` callback runs even if the consumer calls `take/take_while` (terminating early), making `Stream.resource/3` safe for file descriptors, DB cursors, and sockets.

### `Stream.flat_map` / `Stream.concat` / `Stream.zip`

```elixir
# Lazy flat_map — preserves laziness through expansion
files |> Stream.flat_map(&File.stream!/1) |> Stream.take(1000)

# Concatenate lazy streams
Stream.concat([a_stream, b_stream, c_stream])

# Zip with a lazy source of timestamps
events |> Stream.zip(Stream.iterate(System.monotonic_time(), &(&1 + 1_000)))
```

### `Stream.take_while` / `Stream.drop_while` / `Stream.dedup`

```elixir
# Consume until a condition becomes false
logs |> Stream.take_while(&(&1.level != :fatal)) |> Enum.to_list()

# Skip heading noise, then stream the body
Stream.drop_while(lines, &String.starts_with?(&1, "#"))

# Lazy dedup of adjacent duplicates (think: running log of state changes)
state_events |> Stream.dedup_by(& &1.kind) |> Enum.take(10)
```

### Building your own stream — full walkthrough

When a data source isn't already a stream (external API paging, DB cursor, custom file format), wrap it in `Stream.resource/3`.

**Pattern: paginated HTTP API as a stream**

```elixir
defmodule MyApp.Pager do
  @doc """
  Returns a Stream of all items across all pages.
  Consumer controls how much to pull.
  """
  def stream(base_url) do
    Stream.resource(
      # start — no fetch yet, just the initial cursor
      fn -> {base_url, nil} end,

      # each call pulls one page, emits its items, advances the cursor
      fn
        {_, :halt} ->
          {:halt, :done}

        {url, cursor} ->
          params = if cursor, do: [cursor: cursor], else: []
          {:ok, %{"items" => items, "next" => next}} = MyApp.HTTP.get(url, params: params)

          case next do
            nil -> {items, {url, :halt}}       # last page; flag halt next call
            next_cursor -> {items, {url, next_cursor}}
          end
      end,

      # after — cleanup. No resource held here, so :ok
      fn _ -> :ok end
    )
  end
end

# Usage
MyApp.Pager.stream("https://api.example.com/events")
|> Stream.filter(& &1["type"] == "purchase")
|> Stream.take(100)
|> Enum.to_list()
# Only fetches enough pages to produce 100 purchases; then HTTP stops.
```

**The three-argument contract:**

- **`start_fun`** (0-arity) — acquire the resource, return the initial accumulator.
- **`next_fun`** (1-arity) — given the accumulator, return `{elements, new_acc}` (emit) or `{:halt, acc}` (stop).
- **`after_fun`** (1-arity) — cleanup. Always runs, even when the consumer terminates early.

**Pattern: streaming a custom binary file format**

```elixir
def stream_records(path) do
  Stream.resource(
    fn -> File.open!(path, [:read, :binary]) end,
    fn fh ->
      case :file.read(fh, 4) do
        :eof -> {:halt, fh}
        {:ok, <<len::32>>} ->
          {:ok, payload} = :file.read(fh, len)
          {[payload], fh}
      end
    end,
    fn fh -> File.close(fh) end
  )
end
```

**`Stream.unfold/2`** — simpler when there's no resource to acquire/release, just state to evolve:

```elixir
# Fibonacci
Stream.unfold({0, 1}, fn {a, b} -> {a, {b, a + b}} end) |> Enum.take(10)

# Exponential backoff sequence
Stream.unfold(100, fn delay -> {delay, min(delay * 2, 30_000)} end) |> Enum.take(5)
# [100, 200, 400, 800, 1600]
```

Use `Stream.unfold/2` when it's just state → state with no resource to close. Use `Stream.resource/3` when there's a handle that must be closed.

### Enum vs Stream — decision table

| Scenario | Use |
|---|---|
| Small to medium list, consume all of it | **Enum** (lower overhead, single pass per step) |
| Chain 3+ transformations on a large list, consume most | **Enum** → **Stream** depending on memory profile — benchmark |
| Source is infinite (generate until N satisfied) | **Stream** |
| Only need first K results from a pipeline | **Stream** → `Enum.take(k)` (work stops at K) |
| Source is I/O (file, socket, DB cursor) | **Stream** (`File.stream!`, `Stream.resource`) |
| Need the full result anyway (e.g., sort, group_by, sum) | **Enum** (Stream must materialize to sort anyway) |
| Pipeline of side effects, no return value | **Stream** + `Stream.run/1` |
| Memory-constrained environment (Nerves, low-RAM) | **Stream** where possible |

**Benchmark rule of thumb:** for a 10K-element list consumed fully with 3 chained operations, Stream is typically 2× **slower** than Enum due to wrapper overhead. Stream wins when:
- You stop early (`take/take_while`).
- The source is lazy/external (I/O).
- Intermediate lists would exceed memory.

---

## `for` Comprehensions

### Basic

```elixir
for x <- 1..5, do: x * x
# [1, 4, 9, 16, 25]
```

### With filter

```elixir
for x <- 1..10, rem(x, 2) == 0, do: x
# [2, 4, 6, 8, 10]
```

### Multiple generators (cartesian product)

```elixir
for x <- 1..3, y <- [:a, :b], do: {x, y}
# [{1, :a}, {1, :b}, {2, :a}, {2, :b}, {3, :a}, {3, :b}]
```

### Pattern matching in generator

```elixir
for %{active?: true, name: name} <- users, do: name
# Only matches active; non-matching are skipped
```

### `into:` — collect into a specific type

```elixir
for {k, v} <- %{a: 1, b: 2}, into: %{}, do: {k, v * 2}
# %{a: 2, b: 4}

for line <- File.stream!("file.txt"), into: IO.stream(:stdio, :line) do
  String.upcase(line)
end
```

### `reduce:` — reduce accumulator

```elixir
for item <- items, reduce: %{total: 0, count: 0} do
  %{total: t, count: c} -> %{total: t + item.price, count: c + 1}
end
```

### `uniq:` — deduplicate

```elixir
for item <- items, uniq: true, do: item.category
```

### Binary comprehension

```elixir
for <<r, g, b <- pixels>>, do: {r, g, b}
# Iterates over a binary, 3 bytes at a time
```

---

## Recursion

Recursion is **a first-class iteration tool in Elixir**, alongside `Enum`/`Stream` and `for` comprehensions. A tail-recursive function is the functional equivalent of an imperative `while` loop: same constant stack, often the same runtime cost, better expressed through pattern matching.

**Reach for recursion when:**

- **Long-running loops** — GenServer message loops, TCP accept loops, retry loops, supervision-adjacent idle loops. This is Elixir's `while (true)`.
- **Early termination** with complex halt conditions spanning multiple accumulators (simple cases fit `Enum.reduce_while/3`).
- **Tree / graph traversal** — parent→children structures, ASTs, nested documents.
- **Parsers and walkers** where each element shapes what you do with the next.
- **Mutually recursive** grammars or state transitions.
- **Custom enumeration** (implementing `Enumerable`, often paired with `Stream.resource/3`).
- **Infinite / lazy generation** — typically wrapped in `Stream.iterate`/`Stream.unfold`/`Stream.resource`.
- **State-machine loops** in a single process — `receive` + tail call = `:gen_statem` without the framework.

**Canonical long-running loop:**

```elixir
# The functional while-loop — tail-recursive, constant stack, first-class pattern
def loop(state) do
  receive do
    :stop -> :ok
    msg -> msg |> handle(state) |> loop()
  end
end
```

```elixir
# Retry loop with backoff — idiomatic; no framework required
def retry(attempt \\ 1) do
  case work() do
    {:ok, result} -> {:ok, result}
    {:error, _} when attempt >= @max_attempts -> {:error, :exhausted}
    {:error, _} ->
      Process.sleep(backoff(attempt))
      retry(attempt + 1)
  end
end
```

**Reach for `Enum`/`Stream` instead when:**

- A simple map/filter/reduce over a bounded collection — `Enum.map/2` is clearer than hand-rolled recursion and the compiler emits equivalent code.
- Two-pass transformations — a pipeline of `|> Enum.*` reads top-to-bottom; helper-function recursion forces a jump.
- You'd end up re-implementing `Enum.map/2` — use the real thing.

### Last Call Optimization (LCO) — the full story

The BEAM implements **Last Call Optimization** (often called TCO colloquially). LCO applies to **any** call in tail position — self-recursion, mutual recursion, and calls to other modules — converting the call into a jump so the current stack frame is reused. Constant stack, no frame allocation.

A call is in **tail position** when its result IS the function's return value — nothing wraps it, nothing follows it, the VM has no work left after the call.

**Tail-recursive — constant stack:**

```elixir
def sum([], acc), do: acc
def sum([h | t], acc), do: sum(t, acc + h)   # recursion is the last thing
```

The accumulator carries partial state. The VM reuses the frame on every call.

**Body-recursive — uses the process heap (not a traditional stack):**

```elixir
def sum([]), do: 0
def sum([h | t]), do: h + sum(t)   # + wraps the recursive call
```

Each call's intermediate `h` waits in the heap until the recursion unwinds. The BEAM process heap (and stack-like area) grows dynamically — there's **no fixed stack-frame limit**. For bounded input this is fine; for unbounded input, memory grows with depth.

**The Erlang/OTP guidance** — from the official *Seven Myths of Erlang Performance*: *"Use the version that makes your code cleaner (hint: it is usually the body-recursive version)."* Since R12B, body-recursive list building uses the **same memory** as tail-recursive + `Enum.reverse`. The stdlib's `:lists.map`, `:lists.filter`, `:lists.foldr`, and list comprehensions are all body-recursive by choice.

**Modern performance nuance** (OTP 24+ with JIT): on large inputs, tail-recursive versions of list operations can now be noticeably faster (the JIT inlines the frame-reuse aggressively), while body-recursive stays lower in peak memory. **Default to clarity;** benchmark only when a hot path proves it matters.

### Tail-position precision

Where LCO DOES apply:

| Construct | Final call is tail? |
|---|---|
| `def f(...), do: other_fun()` | ✅ |
| `case x do ... -> other_fun() end` (final branch) | ✅ |
| `cond do true -> other_fun() end` | ✅ |
| `if cond, do: other_fun(), else: another_fun()` | ✅ |
| `with {:ok, x} <- step1() do other_fun(x) end` (no `else`) | ✅ |
| Inside `rescue` / `catch` clauses | ✅ (stacktrace already captured) |
| Mutual recursion — `def a, do: b(); def b, do: a()` | ✅ (LCO applies across modules too) |

Where LCO does NOT apply (subtle traps):

| Construct | Why not |
|---|---|
| `[h \| f(t)]` — wrapped in cons | Construction happens after the call returns |
| `h + f(t)` — wrapped in arithmetic | Same reason |
| `IO.puts(f(t))` — argument to another call | The outer call is the tail call |
| `with ... do ... else ... end` | The `else` clause may match the result → VM keeps it ([elixir-lang #6251](https://github.com/elixir-lang/elixir/issues/6251)) |
| `try do f() end` — the protected `do` body | Stacktrace is kept until `try` exits |
| `try do ... after cleanup end` | `after` runs post-call → body is not tail |

```elixir
# Tail position inside case — ✅ LCO applies
def f([h | t]) do
  case check(h) do
    :ok -> f(t)            # tail call — constant stack
    :skip -> f(t)
  end
end

# NOT tail — with/else keeps the result
def f([h | t]) do
  with :ok <- check(h) do
    f(t)                    # looks tail, but...
  else
    :error -> []            # ...else forces the VM to hold the result
  end
end

# Tail again — no else clause
def f([h | t]) do
  with :ok <- check(h) do
    f(t)                    # LCO applies
  end
end
```

### The accumulator-reverse pattern

Tail recursion builds results head-first (prepend — O(1)), then reverses at the end.

```elixir
def map([], _fun, acc), do: Enum.reverse(acc)
def map([h | t], fun, acc), do: map(t, fun, [fun.(h) | acc])

def map(list, fun), do: map(list, fun, [])    # public entry point
```

This is strictly O(n) with constant stack — same cost as `Enum.map/2` under the hood.

**Why not append?** `acc ++ [x]` is O(length of acc) per step, giving O(n²) total. Always **prepend then reverse**.

### Early termination with recursion

```elixir
# Search — halt at first match without traversing the rest
def find([], _fun), do: nil
def find([h | t], fun) do
  if fun.(h), do: h, else: find(t, fun)
end

# Validate until first failure
def validate_all([]), do: :ok
def validate_all([h | t]) do
  case validate(h) do
    :ok -> validate_all(t)
    {:error, reason} -> {:error, reason}
  end
end
```

`Enum.reduce_while/3` handles most of these cases; reach for explicit recursion when state is complex enough that `reduce_while` tuples become awkward.

### Tree / graph traversal

```elixir
defmodule Tree do
  defstruct [:value, children: []]

  # Preorder depth-first — body-recursive (stack bounded by tree depth, usually fine)
  def preorder(%Tree{value: v, children: cs}) do
    [v | Enum.flat_map(cs, &preorder/1)]
  end

  # Depth-first with tail-recursion (explicit stack — for deep or adversarial trees)
  def preorder_tco(tree), do: do_preorder([tree], [])

  defp do_preorder([], acc), do: Enum.reverse(acc)
  defp do_preorder([%Tree{value: v, children: cs} | rest], acc) do
    do_preorder(cs ++ rest, [v | acc])
  end
end
```

For most trees, body recursion is fine — stack depth is bounded by tree depth (usually ≤ 50). Only rewrite to tail recursion when the tree can be pathologically deep.

### Binary pattern-match recursion — the decoder idiom

The dominant pattern for binary protocol decoders, parsers, and byte-oriented state machines. The BEAM specifically optimizes sub-binary reuse — pattern-matching `<<head, rest::binary>>` reuses the underlying buffer rather than copying.

```elixir
# Decode a length-prefixed frame stream
def decode_frames(<<>>), do: []
def decode_frames(<<len::32, payload::binary-size(len), rest::binary>>) do
  [payload | decode_frames(rest)]
end

# Parse null-terminated C strings out of a buffer
def parse_cstrings(binary), do: parse_cstrings(binary, "", [])
defp parse_cstrings(<<>>, _acc, out), do: Enum.reverse(out)
defp parse_cstrings(<<0, rest::binary>>, acc, out),
  do: parse_cstrings(rest, "", [acc | out])
defp parse_cstrings(<<byte, rest::binary>>, acc, out),
  do: parse_cstrings(rest, acc <> <<byte>>, out)

# Stateful decoder — case on a header byte, dispatch to the right parser
def decode(<<0x01, rest::binary>>, state), do: decode_login(rest, state)
def decode(<<0x02, rest::binary>>, state), do: decode_message(rest, state)
def decode(<<>>, state), do: {:done, state}
```

The `<<byte, rest::binary>>` pattern is a **tail-recursive match** on the buffer — the BEAM's sub-binary optimization means `rest` is a pointer into the original binary, not a copy. This makes binary-pattern recursion O(n) total for decoding any protocol.

### Mutual recursion

Two (or more) functions calling each other — LCO applies the same way. Both self- and mutual tail calls reuse the frame.

```elixir
# Parse alternating identifiers and values — mutually recursive
def parse([], acc), do: Enum.reverse(acc)
def parse([name | rest], acc) when is_atom(name), do: parse_value(rest, name, acc)

def parse_value([], _name, acc), do: Enum.reverse(acc)
def parse_value([value | rest], name, acc), do: parse(rest, [{name, value} | acc])
```

**Classic use:** state machines as mutually-recursive state functions (pre-`:gen_statem`). Each state is a function; transitions are tail calls between state functions.

```elixir
def state_idle(state) do
  receive do
    {:connect, host} -> state_connecting(%{state | host: host})
    :stop -> :ok
  end
end

def state_connecting(state) do
  receive do
    :connected -> state_active(state)
    :timeout -> state_idle(state)
  end
end

def state_active(state) do
  receive do
    {:data, d} -> state_active(%{state | buffer: [d | state.buffer]})
    :disconnect -> state_idle(state)
  end
end
```

LCO ensures none of these transitions grow the stack — it's a real state machine, not a leak.

### Recursion vs Enum.reduce_while — decision

| Scenario | Use |
|---|---|
| Simple early-exit fold | `Enum.reduce_while/3` |
| Non-list source (tree, graph, stream) | Explicit recursion |
| Need to restructure the collection (parse, rewrite AST) | Explicit recursion |
| Multi-pass (process list, then process the result) | Enum chain |
| Accumulator is 2+ fields AND halt logic is complex | Explicit recursion — `reduce_while` tuples become unreadable |
| You'd have to "lift" state into the accumulator awkwardly | Explicit recursion |

### Common recursion anti-patterns

**Appending in the accumulator:**

```elixir
# BAD — O(n²)
def map_bad([], _fun, acc), do: acc
def map_bad([h | t], fun, acc), do: map_bad(t, fun, acc ++ [fun.(h)])

# GOOD — prepend + reverse
def map_good([], _fun, acc), do: Enum.reverse(acc)
def map_good([h | t], fun, acc), do: map_good(t, fun, [fun.(h) | acc])
```

**Body recursion on genuinely unbounded input:**

This isn't always "BAD" — for bounded lists body recursion is fine and often clearer. The problem is when input size is user-controlled or stream-sourced and could be arbitrarily large. For those, prefer tail recursion (or just `Enum`).

```elixir
# RISKY for unbounded input — heap grows with recursion depth
def sum([]), do: 0
def sum([h | t]), do: h + sum(t)

# SAFE for any size — constant stack
def sum(list), do: sum(list, 0)
defp sum([], acc), do: acc
defp sum([h | t], acc), do: sum(t, h + acc)

# IDIOMATIC — just use Enum.sum
```

**Forgetting to reverse:**

```elixir
# BAD — results come out backward
def reverse_evens([], acc), do: acc           # ← forgot Enum.reverse
def reverse_evens([h | t], acc) when rem(h, 2) == 0,
  do: reverse_evens(t, [h | acc])
def reverse_evens([_ | t], acc), do: reverse_evens(t, acc)

# GOOD
def reverse_evens([], acc), do: Enum.reverse(acc)
```

**Rewriting Enum.map from scratch:**

```elixir
# BAD — reinventing the wheel
def each_squared([], _acc), do: _acc
def each_squared([h | t], acc), do: each_squared(t, [h * h | acc])

# GOOD
Enum.map(list, &(&1 * &1))
```

### When recursion meets Stream — custom lazy source

When your recursive walker is over a large/unbounded structure, wrap it in `Stream.resource/3` so consumers can `take/take_while` and stop early:

```elixir
# Lazy depth-first tree traversal
def lazy_preorder(tree) do
  Stream.resource(
    fn -> [tree] end,     # stack of nodes to visit
    fn
      [] -> {:halt, []}
      [%Tree{value: v, children: cs} | rest] -> {[v], cs ++ rest}
    end,
    fn _ -> :ok end
  )
end

# Consumer stops at first 5 matching nodes — walker never visits the rest
lazy_preorder(huge_tree)
|> Stream.filter(& &1 > 100)
|> Enum.take(5)
```

See `Stream.resource/3` earlier in this file for the three-argument contract.

---

## Captures & Function References

### Capture shorthand

```elixir
Enum.map(users, &User.name/1)
Enum.map(numbers, &(&1 * 2))
Enum.map(pairs, fn {a, b} -> a + b end)     # Destructuring — can't use shorthand
```

### Multi-arity capture

```elixir
Enum.reduce(items, 0, &+/2)                  # Binary operator capture
Enum.sort(list, &>=/2)                       # Comparator capture
```

### Capturing function with arguments baked-in

```elixir
find_user = &Repo.get(User, &1)
find_user.(123)

# Partial application via closure
max_limit = 100
Enum.filter(items, &(&1.count <= max_limit))
```

### Capture vs anon-fn — when to use which

| Use capture `&Mod.fun/1` when | Use `fn` when |
|---|---|
| Single call, arity matches | Pattern matching on args |
| `&1`/`&2` are the only variables | Multiple statements in body |
| Delegating to a named function | Returning multiple values |

---

## IO Lists & String Building

### Build with IO list, flush once

```elixir
# BAD — O(n²) if many iterations
parts
|> Enum.reduce("", fn p, acc -> acc <> p <> ", " end)

# GOOD — IO list; flatten once at the end
parts
|> Enum.intersperse(", ")
|> IO.iodata_to_binary()

# OR — pass IO list to I/O directly (no conversion needed)
IO.write([parts, "\n"])
File.write!(path, [header, "\n", parts])
```

### Interpolation (good for small cases)

```elixir
"Welcome, #{user.name}! You have #{count} messages."
```

### Sigils for specific forms

```elixir
~s(single-quoted string with "escapes")
~S(raw; no interpolation: #{not_substituted})
~w(a b c)a                      # [:a, :b, :c]
~w(a b c)                       # ["a", "b", "c"]
~r/^\d+$/                       # regex
~D[2024-12-31]                  # Date
~T[23:59:59]                    # Time
~U[2024-12-31T23:59:59Z]        # DateTime (UTC)
```

---

## Error Handling Patterns

### Tagged-tuple functions

```elixir
def parse(str) do
  case Integer.parse(str) do
    {n, ""} -> {:ok, n}
    {_n, _rest} -> {:error, :trailing_garbage}
    :error -> {:error, :not_a_number}
  end
end
```

### Let-it-crash at function entry (use `!` variant)

```elixir
# Expected to fail if not a number; caller handles
def parse(str), do: ...

# Will raise if not a number; caller expects it
def parse!(str) do
  case parse(str) do
    {:ok, n} -> n
    {:error, reason} -> raise ArgumentError, "invalid: #{inspect(reason)}"
  end
end
```

### `catch :exit` for external process calls

```elixir
try do
  GenServer.call(pid, :status)
catch
  :exit, _ -> {:error, :not_running}
end
```

### `rescue` only at untrusted boundaries

```elixir
def deserialize(binary) do
  term = :erlang.binary_to_term(binary, [:safe])
  {:ok, term}
rescue
  ArgumentError -> {:error, :malformed}
end
```

### Distinct failure modes get distinct tags

When a single slot can fail for multiple reasons, give each mode its own tag. Don't compress "wrong type" and "out of range" into a single compound reason — the caller needs to know which kind of failure happened to respond usefully.

```elixir
# BAD — one reason covering two unrelated failure modes
defp validate_a(a) when is_integer(a) and a in 0..100, do: {:ok, a}
defp validate_a(a), do: {:error, {:invalid_input, :a, {:out_of_range_or_wrong_type, a}}}

# GOOD — split the failure space
defp validate_a(a) when is_integer(a) and a in 0..100, do: {:ok, a}
defp validate_a(a) when is_integer(a),
  do: {:error, {:invalid_input, :a, {:out_of_range, a, 0..100}}}
defp validate_a(a),
  do: {:error, {:invalid_input, :a, {:wrong_type, a}}}
```

The GOOD version includes the expected range in the out-of-range error, and lets a caller render a type-error message differently from a range-error message.

**Rule of thumb:** every distinct branch in your validation function should emit a distinct reason atom. If two branches would emit the same atom, they're probably one branch.

### Consistent error style per module boundary

Pick one error-signalling style at each public boundary and stick to it. Mixing raise + tagged-tuple within the same module's public surface confuses callers.

```elixir
# BAD — facade mixes raise and tagged-tuple
defmodule Blackboxes do
  def describe(module) when module in @boxes, do: %{...}  # raises FunctionClauseError otherwise

  def execute(module, ...) do
    if module in @boxes, do: module.execute(...), else: {:error, {:unknown_blackbox, module}}
  end
end

# GOOD — uniform tagged-tuple on the "safe" names
defmodule Blackboxes do
  def describe(module) when is_atom(module) do
    if module in @boxes, do: {:ok, %{...}}, else: {:error, {:unknown_blackbox, module}}
  end

  def describe!(module) do
    case describe(module) do
      {:ok, desc} -> desc
      {:error, reason} -> raise ArgumentError, "unknown blackbox: #{inspect(module)}"
    end
  end

  def execute(module, ...) do
    if module in @boxes, do: module.execute(...), else: {:error, {:unknown_blackbox, module}}
  end
end
```

**Convention:** safe name returns `{:ok, _} | {:error, _}`; `!` variant raises on error. This matches the stdlib (`File.read`/`File.read!`, `Integer.parse`/`String.to_integer`, etc.).

### Emit telemetry + structured logs on rejection paths

Every security rejection (auth failure, IP allowlist denial, Host guard, rate limit, CSRF) should emit a `:telemetry` event AND a structured `Logger` call. Telemetry gives operators metrics + alerts; the log entry gives the forensic trail. Strings-with-interpolation in Logger don't let log pipelines filter — use metadata.

```elixir
# BAD — concatenated string; no queryable field
def call(%Plug.Conn{remote_ip: ip} = conn, _opts) do
  if loopback?(ip) do
    conn
  else
    Logger.warning("rejecting from #{:inet.ntoa(ip)}")
    conn |> send_resp(403, "Forbidden") |> halt()
  end
end

# GOOD — telemetry + structured log with queryable metadata
def call(%Plug.Conn{remote_ip: ip} = conn, _opts) do
  if loopback?(ip) do
    conn
  else
    :telemetry.execute(
      [:my_app, :request, :rejected],
      %{count: 1},
      %{reason: :non_loopback, peer: :inet.ntoa(ip), path: conn.request_path}
    )

    Logger.warning("request rejected",
      event: :non_loopback,
      peer: :inet.ntoa(ip),
      path: conn.request_path
    )

    conn |> send_resp(403, "Forbidden") |> halt()
  end
end
```

Event-naming convention: `[:app_name, :subsystem, :decision]` where decision is `:allowed` / `:rejected` / `:throttled`. Keep the measurement map small (counters, durations) and put context in metadata.

### Validation order in `with` chains — gate by dispatch key first

When an operation has both a **dispatch key** (instruction, action, command name) and **data inputs**, validate the dispatch key FIRST. Reason: some dispatch values legitimately don't use the data (reflection, meta-operations). If you validate data first, you force those branches to accept dummy values just to pass validation.

```elixir
# BAD — data validated before instruction; instruction :list_instructions
# rejects nil/invalid a/b even though it ignores them
def execute(instruction, a, b) do
  with {:ok, a} <- validate_a(a),
       {:ok, b} <- validate_b(b),
       {:ok, instruction} <- validate_instruction(instruction) do
    dispatch(instruction, a, b)
  end
end

# GOOD — dispatch key first; reflection paths are free of data validation
def execute(instruction, a, b) do
  with {:ok, instruction} <- validate_instruction(instruction),
       {:ok, a} <- validate_a(a),
       {:ok, b} <- validate_b(b) do
    dispatch(instruction, a, b)
  end
end
```

**Even better:** if a dispatch value truly doesn't need data, promote it to its own function so the call site expresses the intent directly:

```elixir
# Cleanest — reflection is its own function; execute/3 never sees :list_instructions
def instructions, do: @instructions
def execute(instruction, a, b) when instruction != :list_instructions, do: ...
```

See `../elixir-planning/architecture-patterns.md §4.9` for the behaviour-design counterpart (don't overload dispatch with reflection atoms).

---

## Advanced Reduce Patterns

Beyond `Enum.reduce/3` with a single accumulator, real codebases (Ecto, Phoenix LiveView, Plug) use richer reducer patterns:

### Multi-accumulator reduce (tuple state)

```elixir
# Partition a stream in a single pass (from Ecto.Changeset)
{changes, errors, valid?} =
  Enum.reduce(new_changes, {old_changes, [], true}, fn
    {key, value}, {changes, errors, valid?} ->
      case validate(key, value) do
        :ok -> {Map.put(changes, key, value), errors, valid?}
        {:error, msg} -> {changes, [{key, msg} | errors], false}
      end
  end)
```

When Enum has a dedicated function for the pattern, prefer it:
- Two-list partition → `Enum.split_with/2`
- Group by a key → `Enum.group_by/2,3`
- Count per key → `Enum.frequencies_by/2`

### `Enum.reduce_while/3` with complex halt state

Use when processing must stop mid-collection:

```elixir
# Validate config keys, halt on first unknown
Enum.reduce_while(config, :ok, fn {key, _value}, :ok ->
  if key in allowed_keys, do: {:cont, :ok}, else: {:halt, {:error, {:unknown, key}}}
end)

# Process within a budget
Enum.reduce_while(items, {[], budget}, fn item, {processed, remaining} ->
  cost = compute_cost(item)
  if cost <= remaining do
    {:cont, {[process(item) | processed], remaining - cost}}
  else
    {:halt, {Enum.reverse(processed), remaining}}
  end
end)
```

### `Enum.map_reduce/3` — transform + thread state

Map each element to a new value while threading an accumulator:

```elixir
# Transform + accumulate params (from Ecto.Query.Builder)
{escaped, params_acc} =
  Enum.map_reduce(exprs, params, fn expr, p ->
    {escaped_expr, new_params} = escape(expr, type, p, vars)
    {escaped_expr, new_params}
  end)

# Assign sequential IDs
{items_with_ids, _next} =
  Enum.map_reduce(items, 1, fn item, id ->
    {Map.put(item, :id, id), id + 1}
  end)
```

### `Enum.flat_map_reduce/3` — emit 0..N per element with state

Use when each input produces a variable number of outputs AND you need to thread state:

```elixir
# Delete components while tracking remaining state (from Phoenix LiveView)
{deleted_cids, new_state} =
  Enum.flat_map_reduce(cids, state, fn cid, acc ->
    {deleted, components} = delete_component(cid, acc.components)
    {deleted, %{acc | components: components}}
  end)

# Expand aliases: each input may become 0, 1, or many outputs
{all_envs, seen} =
  Enum.flat_map_reduce(inputs, MapSet.new(), fn name, seen ->
    cond do
      name in seen -> {[], seen}
      String.contains?(name, "@") -> {expand_group(name), MapSet.put(seen, name)}
      true -> {[name], MapSet.put(seen, name)}
    end
  end)
```

### `Enum.scan/2,3` — running totals (rare, but useful for cumulative state)

Like `reduce` but emits every intermediate accumulator:

```elixir
# Running totals
Enum.scan([10, 20, 30, 40], 0, &(&1 + &2))
# [10, 30, 60, 100]

# State evolution (e.g., replaying events)
states = Enum.scan(events, initial_state, &apply_event/2)
# [state_after_event_1, state_after_event_2, ...]
```

Use `Stream.scan/2,3` if the events list is large and you want lazy intermediates.

### Building maps/keyword lists from reducers

When collecting into a shape, prefer `Map.new/2` / `Enum.into/2` over manual reduce:

```elixir
# GOOD — prefer Map.new when collecting
Map.new(pairs, fn {k, v} -> {k, transform(v)} end)

# GOOD — conditional filter in reduce (when Map.new doesn't fit)
Enum.reduce([timeout: t, retries: r, verbose: v], [], fn
  {_key, nil}, acc -> acc            # skip nil values
  {key, value}, acc -> [{key, value} | acc]
end)
```

### Decision: which reducer?

| You need to… | Use |
|---|---|
| Reduce to a single value | `Enum.reduce/2,3` |
| Halt partway through | `Enum.reduce_while/3` |
| Transform while threading state | `Enum.map_reduce/3` |
| Emit 0..N per element + thread state | `Enum.flat_map_reduce/3` |
| Emit running/intermediate values | `Enum.scan/2,3` (or `Stream.scan/2,3`) |
| Partition into two | `Enum.split_with/2` (not reduce) |
| Group by key | `Enum.group_by/2,3` (not reduce) |
| Build a map | `Map.new/2` (not reduce into `%{}`) |
| Count per key | `Enum.frequencies_by/2` (not reduce) |

---

## Protocols

A **protocol** is data-dispatch polymorphism: one function, many implementations per data type. Elixir dispatches at runtime based on the first argument's type.

**Use a protocol when:** you want different data types (structs, built-in types) to share a method like `encode/1`, `render/1`, `to_param/1`. See `../elixir-planning/architecture-patterns.md` for the Behaviour-vs-Protocol decision.

### Defining a protocol

```elixir
# Most protocols: single function
defprotocol MyApp.Renderable do
  @spec render(t()) :: iodata()
  def render(term)
end

# With a fallback when Any is a reasonable default
defprotocol MyApp.Parameterizable do
  @fallback_to_any true
  @spec to_param(t()) :: String.t()
  def to_param(term)
end
```

**Rule of thumb:** prefer single-function protocols (matches stdlib). Multi-function only for performance callbacks (Enumerable's `count/1`, `member?/2`, `slice/1`).

### Implementing — structs

```elixir
# In the struct's own module (preferred — @derive-able, single source of truth)
defmodule MyApp.Widget do
  defstruct [:name, :html]

  defimpl MyApp.Renderable do
    def render(%{html: html}), do: html
  end
end

# Outside the struct's module (for foreign structs)
defimpl MyApp.Renderable, for: MyApp.Alert do
  def render(%{message: m, level: l}), do: ~s(<div class="#{l}">#{m}</div>)
end
```

### Implementing — built-in types

The 11 built-in types for `defimpl, for:` are `Atom`, `BitString`, `Float`, `Function`, `Integer`, `List`, `Map`, `PID`, `Port`, `Reference`, `Tuple` — plus `Any` for fallback.

```elixir
defimpl MyApp.Renderable, for: BitString do
  # Guard — BitString includes non-binary bitstrings
  def render(binary) when is_binary(binary), do: binary
  def render(bits), do: raise Protocol.UndefinedError, protocol: @protocol, value: bits
end

defimpl MyApp.Renderable, for: List do
  def render(iolist), do: iolist     # IO lists are already iodata
end

# Multiple types at once
defimpl MyApp.Renderable, for: [Integer, Float] do
  def render(n), do: to_string(n)
end
```

### `@derive` — compile-time protocol implementation

```elixir
defmodule MyApp.User do
  # @derive MUST come BEFORE defstruct/schema (compiler warns otherwise)
  @derive {Jason.Encoder, only: [:id, :name, :email]}
  @derive {Phoenix.Param, key: :username}
  @derive {Inspect, only: [:id, :name]}      # hides password_hash from logs
  defstruct [:id, :name, :email, :username, :password_hash]
end
```

For **structs you don't own** (third-party), use `Protocol.derive/3`:

```elixir
require Protocol
Protocol.derive(Jason.Encoder, SomeLibrary.Thing, only: [:id, :name])
```

### `@fallback_to_any` — when

| Protocol | Has fallback? | Why |
|---|---|---|
| `Inspect` | Yes | Default `%Module{...}` printing for all structs |
| `Phoenix.Param` | Yes | Convention: assumes `:id` field exists |
| `Plug.Exception` | Yes | Default 500 status, empty actions |
| `Jason.Encoder` | Yes, but raises | Encourages `@derive` |
| `Enumerable` | **No** | Must fail loudly on non-enumerable input |
| `String.Chars` | **No** | Silent garbage output would hide bugs |
| `Collectable` | **No** | No sensible default |

**Alternative to `@fallback_to_any`** (Elixir 1.18+) — customize the error message without providing a fallback:

```elixir
defprotocol MyApp.Encoder do
  @undefined_impl_description """
  protocol must be explicitly implemented.
  Add `@derive {MyApp.Encoder, only: [...]}` before defstruct.
  """
  def encode(term)
end
```

### Enumerable / Collectable / Inspect — common implementations

**`Inspect`** — customize `inspect/2` output (use `@derive {Inspect, only: [...]}` for most cases):

```elixir
defimpl Inspect, for: MyApp.Money do
  import Inspect.Algebra
  def inspect(%{cents: c, currency: cur}, opts) do
    concat(["#Money<", to_string(cur), " ", Integer.to_string(div(c, 100)), ".", Integer.to_string(rem(c, 100)), ">"])
  end
end
```

**`String.Chars`** — enables `to_string/1` and `"#{value}"`:

```elixir
defimpl String.Chars, for: MyApp.Money do
  def to_string(%{cents: c, currency: cur}) do
    "#{cur} #{Float.round(c / 100, 2)}"
  end
end
```

**`Enumerable`** — make a struct usable in `Enum.*`:

```elixir
defimpl Enumerable, for: MyApp.Tree do
  def count(%{size: n}), do: {:ok, n}             # or {:error, __MODULE__} for O(n)
  def member?(%{nodes: ns}, v), do: {:ok, v in ns}
  def slice(_), do: {:error, __MODULE__}           # fall back to reduce
  def reduce(tree, acc, fun), do: do_reduce(to_list(tree), acc, fun)

  defp do_reduce(_, {:halt, acc}, _), do: {:halted, acc}
  defp do_reduce(list, {:suspend, acc}, fun), do: {:suspended, acc, &do_reduce(list, &1, fun)}
  defp do_reduce([], {:cont, acc}, _), do: {:done, acc}
  defp do_reduce([h | t], {:cont, acc}, fun), do: do_reduce(t, fun.(h, acc), fun)
end
```

Return `{:error, __MODULE__}` from `count/1`, `member?/2`, `slice/1` when O(1) isn't possible — Elixir falls back to `reduce/3`.

**`Collectable`** — enables `Enum.into(enum, %MyStruct{})`:

```elixir
defimpl Collectable, for: MyApp.Bag do
  def into(bag) do
    collector = fn
      acc, {:cont, elem} -> MyApp.Bag.add(acc, elem)
      acc, :done -> acc
      _acc, :halt -> :ok
    end
    {bag, collector}
  end
end
```

### Protocol consolidation

In production (`MIX_ENV=prod`), Elixir **consolidates** protocols — pre-computes dispatch tables so calls are O(1). In dev/test, dispatch is O(n) in the number of implementations.

```elixir
# mix.exs — enabled by default in releases
def project do
  [consolidate_protocols: Mix.env() != :test]
end
```

Consolidation is why `@derive` must come before `defstruct` — the compiler collects implementations at compile time.

### Making a protocol derivable

If you want users to `@derive YourProtocol, opts` on their structs, implement `__deriving__/3`:

```elixir
defprotocol MyApp.Cacheable do
  @fallback_to_any true
  @spec cache_key(t()) :: String.t()
  def cache_key(term)
end

defimpl MyApp.Cacheable, for: Any do
  defmacro __deriving__(module, _struct, opts) do
    keys = Keyword.get(opts, :keys, [:id])
    quote do
      defimpl MyApp.Cacheable, for: unquote(module) do
        def cache_key(%{unquote_splicing(Enum.map(keys, &{&1, Macro.var(&1, nil)}))}) do
          unquote("#{module}:") <>
            Enum.map_join(unquote(Enum.map(keys, &Macro.var(&1, nil))), ":", &to_string/1)
        end
      end
    end
  end

  def cache_key(_), do: raise "Cacheable not derived — add @derive MyApp.Cacheable"
end
```

Users now: `@derive {MyApp.Cacheable, keys: [:org_id, :id]}`.

### Common anti-patterns

**`@derive` after `defstruct`:**

```elixir
# BAD — compiler warns, derivation may not apply
defmodule User do
  defstruct [:id, :name]
  @derive Jason.Encoder   # too late
end

# GOOD
defmodule User do
  @derive Jason.Encoder
  defstruct [:id, :name]
end
```

**`defimpl for: Map` expecting to match structs:**

```elixir
# BAD — this matches ONLY bare %{} maps, not structs
defimpl MyApp.Renderable, for: Map do
  def render(m), do: inspect(m)
end

# GOOD — structs dispatch separately; implement per struct
defimpl MyApp.Renderable, for: MyApp.Widget do
  def render(%{...}), do: ...
end
```

**Protocol where a behaviour fits:**

```elixir
# BAD — "strategy" where the strategy is a MODULE (no data to dispatch on)
defprotocol StorageBackend, do: def put(backend, key, value)

# GOOD — behaviour for strategy
defmodule StorageBackend do
  @callback put(String.t(), term()) :: :ok | {:error, term()}
end

# Config chooses the implementation
config :my_app, :storage, MyApp.RedisBackend
```

See `../elixir-planning/architecture-patterns.md` for the Behaviour vs Protocol decision table.

---

## Behaviours

A **behaviour** is module-dispatch polymorphism: a named contract (`@callback`s) and one or more modules that `@behaviour MyContract` and implement those callbacks. The caller picks which module to use — typically at config time, or by receiving a module atom.

**Use a behaviour when:**
- The implementation is chosen per-environment (test double vs real implementation).
- Pluggable strategies / adapters (hexagonal architecture ports).
- Multiple implementations at once (multiple storage backends, multiple email providers).
- The stdlib framework pattern (GenServer, Plug, Supervisor, `:gen_statem`).

See `../elixir-planning/architecture-patterns.md` for the architectural decision.

### Defining a behaviour

```elixir
defmodule MyApp.Storage do
  @moduledoc """
  Contract for key-value storage backends.
  """

  @type key :: String.t()
  @type value :: binary()

  @callback put(key(), value()) :: :ok | {:error, term()}
  @callback get(key()) :: {:ok, value()} | :error
  @callback delete(key()) :: :ok

  @callback keys(prefix :: String.t()) :: [key()]
  @optional_callbacks keys: 1
end
```

**Key directives:**
- `@callback fun(arg_type()) :: return_type()` — required contract.
- `@macrocallback` — same, but the implementation must be a macro (rare; framework internals like Ecto.Query).
- `@optional_callbacks [fun: arity, ...]` — may be left unimplemented. Callers must check via `function_exported?/3` before invoking.
- `@type`s in a behaviour module are part of its public contract.

### Implementing a behaviour

```elixir
defmodule MyApp.Storage.Redis do
  @behaviour MyApp.Storage

  @impl true
  def put(key, value), do: Redix.command(:my_redis, ["SET", key, value])

  @impl true
  def get(key) do
    case Redix.command(:my_redis, ["GET", key]) do
      {:ok, nil} -> :error
      {:ok, value} -> {:ok, value}
    end
  end

  @impl true
  def delete(key), do: Redix.command(:my_redis, ["DEL", key]) |> elem(0)

  @impl true
  def keys(prefix), do: Redix.command!(:my_redis, ["KEYS", prefix <> "*"])
end
```

**`@impl` is mandatory.** Options:
- `@impl true` — asserts "this implements a callback from one of the declared `@behaviour`s."
- `@impl ModuleName` — names which behaviour (required when implementing multiple behaviours with overlapping callback names).

The compiler errors on:
- A function marked `@impl` that doesn't match a callback (typo in function name).
- A callback without a corresponding `@impl` (missing implementation).

### Calling into a behaviour

**Config-time dispatch** (most common — choose per-environment):

```elixir
# config/config.exs
config :my_app, :storage, MyApp.Storage.Redis

# config/test.exs
config :my_app, :storage, MyApp.Storage.Mock
```

```elixir
defmodule MyApp.Cache do
  @storage Application.compile_env!(:my_app, :storage)

  def get(key), do: @storage.get(key)
  def put(key, value), do: @storage.put(key, value)
end
```

**Runtime dispatch** (when the backend is data — e.g., per-tenant):

```elixir
def get(backend, key), do: backend.get(key)

# Caller:
MyApp.Cache.get(MyApp.Storage.Redis, "user:42")
```

### `use` + `__using__/1` — behaviour with defaults

When a behaviour has obvious defaults for most callbacks, provide them via `use`:

```elixir
defmodule MyApp.JobWorker do
  @callback perform(map()) :: :ok | {:error, term()}
  @callback retry_delay(attempt :: non_neg_integer()) :: pos_integer()

  defmacro __using__(_opts) do
    quote do
      @behaviour MyApp.JobWorker

      # Default implementation — subclasses override if needed
      @impl true
      def retry_delay(attempt), do: trunc(:math.pow(2, attempt) * 1_000)

      defoverridable retry_delay: 1
    end
  end
end

# Usage — worker gets @behaviour + default retry_delay
defmodule MyApp.SendEmailJob do
  use MyApp.JobWorker

  @impl true
  def perform(%{"to" => to, "body" => body}), do: Mailer.send(to, body)
  # retry_delay/1 inherited — or override:
  # def retry_delay(_), do: 60_000
end
```

**`defoverridable`** marks functions injected by `use` as overridable so the using module can replace them. The overriding function can call the original via `super/1`.

### Testing with Mox

`Mox.defmock/2` creates a test-only module implementing your behaviour:

```elixir
# test/test_helper.exs
Mox.defmock(MyApp.Storage.Mock, for: MyApp.Storage)

# In a test
MyApp.Storage.Mock
|> expect(:get, fn "user:42" -> {:ok, "alice"} end)
|> expect(:put, fn "user:42", "bob" -> :ok end)

assert {:ok, "alice"} = MyApp.Cache.get("user:42")
```

See `testing-patterns.md` for full Mox setup.

### Decision: `@callback` vs `@optional_callbacks` vs default via `use`

| Situation | Use |
|---|---|
| All implementations MUST provide this | `@callback` (required) |
| Most skip this; a few implement for optimization | `@optional_callbacks` (caller checks `function_exported?/3`) |
| All implementations would write nearly the same code | `@callback` + default in `__using__/1` with `defoverridable` |
| Contract shared across projects (a library) | Behaviour in a standalone module — no `use` (users should write `@behaviour` explicitly) |

### Common anti-patterns

**Missing `@impl`:**

```elixir
# BAD — typo in `hanle_call` compiles silently; callback missing
defmodule MyServer do
  use GenServer
  def hanle_call(_, _, s), do: {:reply, :ok, s}
end

# GOOD — @impl catches typos at compile time
defmodule MyServer do
  use GenServer
  @impl true
  def handle_call(_, _, s), do: {:reply, :ok, s}
end
```

**`Application.get_env` at every call instead of `compile_env`:**

```elixir
# BAD — reads env dict on every invocation
def get(key), do: Application.get_env(:my_app, :storage).get(key)

# GOOD — bound at compile time
@storage Application.compile_env!(:my_app, :storage)
def get(key), do: @storage.get(key)
```

(Use `Application.get_env` only when the backend must be switchable at runtime.)

**Behaviour with a single implementation:**

```elixir
# BAD — behaviour + one concrete impl just to "use DI"
defmodule MyApp.EmailSender, do: @callback send(to, body) :: :ok
defmodule MyApp.EmailSender.Swoosh, do: @behaviour MyApp.EmailSender; ...

# Only one prod implementation, no tests using it → behaviour is noise
# GOOD — a plain module; introduce behaviour only when a second impl (or Mox) is needed
defmodule MyApp.EmailSender do
  def send(to, body), do: Swoosh.deliver(...)
end
```

**Rule:** add a behaviour when you have a real second implementation (test double, alternate backend). Don't add behaviours "just in case."

**Cross-behaviour ambiguity:**

```elixir
# BAD — two behaviours both define handle_call/3; which does @impl true mean?
defmodule Dual do
  @behaviour A
  @behaviour B
  @impl true
  def handle_call(req, from, state), do: ...
end

# GOOD — name the behaviour
@impl A
def handle_call(req, from, state), do: ...
```

---

## Imperative → Elixir Translation

For engineers coming from JavaScript / Python / Ruby / Go — the cheat sheet.

### Collection operations

| Imperative | Elixir |
|---|---|
| `for (x of list) result.push(f(x))` | `Enum.map(list, &f/1)` |
| `for (x of list) if (p(x)) result.push(x)` | `Enum.filter(list, &p/1)` |
| `let acc = init; for (...) acc = f(acc, x)` | `Enum.reduce(list, init, fn x, acc -> ... end)` |
| `list.find(x => p(x))` | `Enum.find(list, &p/1)` |
| `list.some(x => p(x))` | `Enum.any?(list, &p/1)` |
| `list.every(x => p(x))` | `Enum.all?(list, &p/1)` |
| `list.flatMap(x => f(x))` | `Enum.flat_map(list, &f/1)` |
| `[...new Set(list)]` | `Enum.uniq(list)` |
| `list.sort((a,b) => a.name - b.name)` | `Enum.sort_by(list, & &1.name)` |
| `Object.groupBy(list, x => x.type)` | `Enum.group_by(list, & &1.type)` |
| `_.countBy(list, f)` | `Enum.frequencies_by(list, &f/1)` |
| `_.chunk(list, 3)` | `Enum.chunk_every(list, 3)` |
| `_.partition(list, pred)` | `Enum.split_with(list, &pred/1)` |
| `list.join(", ")` | `Enum.join(list, ", ")` |
| `Math.max(...list)` | `Enum.max(list)` |
| `list.reduce((a, b) => a + b, 0)` | `Enum.sum(list)` |

### Control flow

| Imperative | Elixir |
|---|---|
| `if / else if / else` on types | Multi-clause function with pattern matching |
| `switch (x.type)` | `case x.type do ... end` (or multi-clause function) |
| `if (x != null && x.active)` | `def f(%{active: true} = x)` (pattern match) |
| `try { risky() } catch(e) {...}` | `case risky() do {:ok, v} -> v; {:error, _} -> fallback end` |
| `for (...) if (done) break` | `Enum.reduce_while(list, acc, fn x, acc -> {:cont/:halt, ...} end)` |
| `while (cond) {...}` | Recursive function with guard; or `Stream.iterate/2` |
| `return early` | Pattern match + multi-clause function |
| `goto` / labels | You don't. Recursion or `reduce_while` handles all early-exit cases. |

### Data mutation → transformation

| Imperative | Elixir |
|---|---|
| `obj.key = value` | `%{map \| key: value}` or `Map.put(map, key, value)` |
| `obj.a.b.c = value` | `put_in(obj, [:a, :b, :c], value)` |
| `obj.count++` | `update_in(obj, [:count], &(&1 + 1))` |
| `delete obj.key` | `Map.delete(map, key)` |
| `list.push(item)` | `[item \| list]` (prepend is O(1)) |
| `list.pop()` | `[head \| tail] = list` (pattern match) |
| `set.add(item)` | `MapSet.put(set, item)` |
| `str += chunk` in a loop | IO list: `[chunk \| acc]`, flatten with `IO.iodata_to_binary/1` |
| `"Hello " + name + "!"` | `"Hello #{name}!"` (interpolation) |
| `result = ""; for (x) result += f(x)` | `Enum.map_join(items, ", ", &f/1)` |
| `x ?? default` (null-coalesce) | `x \|\| default` (careful — `\|\|` also catches `false`) |
| `x?.y?.z` (optional chaining) | `get_in(x, [:y, :z])` |

### State and side effects

| Imperative | Elixir |
|---|---|
| Global mutable variable | Application env + `Application.get_env/3` OR `:persistent_term` OR a GenServer |
| Class instance with fields + methods | Module with struct + functions taking struct as first arg |
| Singleton | Named GenServer, or `:persistent_term` for read-heavy |
| Promise / async/await | `Task.async/1` + `Task.await/1` |
| Thread pool | `Task.Supervisor` + `Task.async_stream/3` |
| Event emitter / observer | `Phoenix.PubSub.broadcast/3` |
| Try/finally cleanup | `try do ... after ... end`, or supervised process with `terminate/2` |
| Long-lived network connection | Supervised GenServer with `:gen_tcp` |
| Exception propagation up the stack | Supervisor restart + tagged tuple returns |

**The single biggest mindset shift:** you don't mutate — you **transform**. Every function takes data in and returns new data out. The "state" of your program is a value flowing through a pipeline, not a location being overwritten.

---

## Common Anti-Patterns (BAD / GOOD)

### 1. `if` for structural dispatch

```elixir
# BAD
def render(event) do
  if is_struct(event, Click), do: render_click(event), else: render_other(event)
end
```

```elixir
# GOOD
def render(%Click{} = e), do: render_click(e)
def render(e), do: render_other(e)
```

### 2. `Enum.each` used to accumulate

```elixir
# BAD — rebinding outside the each doesn't escape
total = 0
Enum.each(items, fn i -> total = total + i.price end)
IO.puts(total)  # Still 0!
```

```elixir
# GOOD
total = Enum.reduce(items, 0, fn i, acc -> acc + i.price end)
```

### 3. `Map.values |> Enum.filter`

```elixir
# BAD — two passes
active = map |> Map.values() |> Enum.filter(& &1.active?)
```

```elixir
# GOOD — single pass
active = for {_, %{active?: true} = v} <- map, do: v
```

### 4. `length(list) > 0`

```elixir
# BAD — O(n)
if length(list) > 0, do: ...
```

```elixir
# GOOD — O(1)
case list do
  [_ | _] -> ...
  [] -> ...
end
```

### 5. `map[:key] != nil`

```elixir
# BAD — nil could mean "absent" or "value is nil"
if config[:timeout] != nil, do: use_timeout(config[:timeout])
```

```elixir
# GOOD
case Map.fetch(config, :timeout) do
  {:ok, timeout} -> use_timeout(timeout)
  :error -> use_default()
end
```

### 6. Nested `case` where `with` fits

```elixir
# BAD
case Accounts.get_user(id) do
  {:ok, user} ->
    case Content.get_post(post_id) do
      {:ok, post} ->
        case Authz.can?(user, post) do
          true -> {:ok, post}
          false -> {:error, :unauthorized}
        end
      err -> err
    end
  err -> err
end
```

```elixir
# GOOD
with {:ok, user} <- Accounts.get_user(id),
     {:ok, post} <- Content.get_post(post_id),
     true <- Authz.can?(user, post) do
  {:ok, post}
else
  false -> {:error, :unauthorized}
  err -> err
end
```

---

## Cross-References

- **Architectural patterns (event-driven / hexagonal / CQRS):** `../elixir-planning/architecture-patterns.md`
- **Language & stdlib lookup:** `../elixir/quick-references.md` + `../elixir/language-patterns.md`
- **Data-structure specific patterns:** `./data-reference.md`
- **Reviewing idiom use:** `../elixir-reviewing/SKILL.md`
