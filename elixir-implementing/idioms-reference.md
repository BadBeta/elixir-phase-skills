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
