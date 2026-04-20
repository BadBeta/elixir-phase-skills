# Types & Docs — Implementation Reference

Phase-focused on **writing** `@spec`, `@type`, `@doc`, `@moduledoc`, doctests, and Dialyzer annotations. Covers the syntax for documenting and typing Elixir code.

**For architectural type-system strategy** (when to introduce Dialyzer, set-theoretic types adoption), see `../elixir-planning/SKILL.md`.

---

## Rules for Writing Types & Docs

1. **ALWAYS use `@spec` on every public function.** Every `def` without a `@spec` is a hidden interface.
2. **ALWAYS use `@moduledoc`** on every module — even `@moduledoc false` is better than nothing.
3. **ALWAYS use `@doc`** on every public function. Use `@doc false` for intentionally undocumented internals.
4. **ALWAYS pair `@spec` with the function it describes** — immediately above, no blank line between.
5. **ALWAYS document options** in `@doc` for functions taking keyword lists. Use `@type opts/0`.
6. **PREFER `@type t()` for the "primary" type** a module represents. This makes `ModuleName.t()` a legible type reference.
7. **PREFER named types over inlined structural types** when a shape is reused. `@type user_id :: pos_integer()` beats writing `pos_integer()` everywhere.
8. **NEVER use `@spec` with `any()` without justification.** `any()` opts out of type checking.
9. **NEVER use `t()` without `@type t`** defined — it silently maps to `any()`.
10. **ALWAYS write doctests** for pure functions with no I/O. They serve as executable examples in `@doc`.
11. **NEVER put sensitive data in `@doc`/`@moduledoc` examples.** These end up in HexDocs.
12. **ALWAYS run `mix dialyzer`** in CI for projects with established specs. A warning means the spec doesn't match the code.

---

## `@moduledoc` — Templates

### Basic

```elixir
defmodule MyApp.Accounts do
  @moduledoc """
  User account management — registration, authentication, and session lifecycle.

  ## Overview

  The Accounts context owns user identity and session state. All user-related
  reads and writes go through this module. Password hashing uses Bcrypt.

  ## Related

  - `MyApp.Accounts.User` — the schema
  - `MyApp.Accounts.Session` — session tokens
  - `MyApp.Accounts.Mailer` — registration/reset emails
  """
end
```

### Hide internal module

```elixir
defmodule MyApp.Accounts.Internal do
  @moduledoc false
  # This module is not part of the public API
end
```

### Module with examples

```elixir
defmodule MyApp.Money do
  @moduledoc """
  Money arithmetic with cent-level precision.

  ## Examples

      iex> MyApp.Money.new(100)
      %MyApp.Money{cents: 10000, currency: :usd}

      iex> MyApp.Money.add(MyApp.Money.new(10), MyApp.Money.new(5))
      %MyApp.Money{cents: 1500, currency: :usd}
  """
end
```

---

## `@doc` — Templates

### Basic

```elixir
@doc """
Registers a new user with the given attributes.

## Parameters

  * `attrs` — a map of user attributes (`:email`, `:name`, `:password`)

## Returns

  * `{:ok, %User{}}` on success
  * `{:error, %Ecto.Changeset{}}` on validation failure
"""
def register_user(attrs), do: ...
```

### With examples and since

```elixir
@doc """
Capitalizes the first letter of each word.

## Examples

    iex> MyApp.StringUtils.title_case("hello world")
    "Hello World"

    iex> MyApp.StringUtils.title_case("elixir is great")
    "Elixir Is Great"
"""
@doc since: "1.2.0"
def title_case(string), do: ...
```

### Deprecation

```elixir
@doc """
Authenticates a user by email/password.
"""
@doc deprecated: "Use authenticate_user_with_token/1 instead"
def authenticate_user(email, password), do: ...
```

Or the more explicit `@deprecated`:

```elixir
@deprecated "Use authenticate_user_with_token/1 instead"
def authenticate_user(email, password), do: ...
```

### Hide a public function from docs

```elixir
@doc false
def internal_helper(...), do: ...
```

### Private function — no `@doc` needed

```elixir
# defp functions don't need @doc (they're private anyway)
defp normalize_email(email), do: ...
```

### `@typedoc` for types

```elixir
@typedoc """
A user identifier — always a positive integer from the `users` table.
"""
@type user_id :: pos_integer()
```

---

## `@spec` — Templates

### Basic forms

```elixir
@spec register_user(map()) :: {:ok, User.t()} | {:error, Ecto.Changeset.t()}
def register_user(attrs), do: ...

@spec add(number(), number()) :: number()
def add(a, b), do: a + b

@spec list_users() :: [User.t()]
def list_users, do: ...

@spec find_user(pos_integer()) :: User.t() | nil
def find_user(id), do: ...
```

### With union types

```elixir
@spec parse_status(String.t()) :: {:ok, :active | :inactive | :pending} | {:error, :invalid}
def parse_status(str), do: ...
```

### With `when` (type variables)

```elixir
@spec first(list(t)) :: t | nil when t: term()
def first([]), do: nil
def first([h | _]), do: h

@spec map(Enumerable.t(a), (a -> b)) :: [b] when a: term(), b: term()
def map(enum, fun), do: ...
```

### Multi-clause function — one `@spec` per public clause (or combined)

```elixir
# Combined
@spec process(integer() | String.t()) :: String.t()
def process(n) when is_integer(n), do: "num: #{n}"
def process(s) when is_binary(s), do: "str: #{s}"
```

### Keyword options

```elixir
@type list_opts :: [
        active: boolean(),
        page: pos_integer(),
        per_page: pos_integer()
      ]

@spec list_users(list_opts()) :: [User.t()]
def list_users(opts \\ []), do: ...
```

### Callback signature (for behaviours)

```elixir
defmodule MyApp.Storage do
  @callback put(key :: String.t(), value :: term()) :: :ok | {:error, term()}
  @callback get(key :: String.t()) :: {:ok, term()} | :error
  @callback delete(key :: String.t()) :: :ok

  @optional_callbacks [delete: 1]
end
```

### GenServer callbacks

```elixir
@impl true
@spec init(opts :: keyword()) :: {:ok, state()} | {:stop, reason :: term()}
def init(opts), do: ...

@impl true
@spec handle_call(term(), GenServer.from(), state()) ::
        {:reply, term(), state()} | {:stop, term(), term(), state()}
def handle_call(:status, _from, state), do: ...
```

### Plug signature

```elixir
@impl true
@spec init(keyword()) :: keyword()
def init(opts), do: opts

@impl true
@spec call(Plug.Conn.t(), keyword()) :: Plug.Conn.t()
def call(conn, opts), do: ...
```

---

## `@type` — Templates

### Module's primary type

```elixir
defmodule MyApp.User do
  @type t :: %__MODULE__{
          id: pos_integer() | nil,
          email: String.t(),
          name: String.t(),
          role: :user | :admin,
          active?: boolean(),
          inserted_at: DateTime.t() | nil
        }

  defstruct [:id, :email, :name, role: :user, active?: true, inserted_at: nil]
end

# Used elsewhere
@spec greet(User.t()) :: String.t()
def greet(user), do: "Hello, #{user.name}"
```

### Opaque type (hide internal representation)

```elixir
defmodule MyApp.Money do
  @opaque t :: %__MODULE__{cents: integer(), currency: atom()}
  defstruct [:cents, :currency]

  @spec new(number(), atom()) :: t()
  def new(amount, currency \\ :usd), do: %__MODULE__{cents: round(amount * 100), currency: currency}

  @spec add(t(), t()) :: t()
  def add(%__MODULE__{cents: a, currency: c}, %__MODULE__{cents: b, currency: c}),
    do: %__MODULE__{cents: a + b, currency: c}
end
```

**`@opaque`:** callers can use `Money.t()` but Dialyzer prevents them from pattern-matching on internal fields.

### Private type (module-local)

```elixir
@typep cache_entry :: {term(), pos_integer()}

@spec maybe_cache(cache_entry()) :: :ok
defp maybe_cache(entry), do: ...
```

### Parameterized types

```elixir
@type pair(a, b) :: {a, b}
@type result(ok_type, err_type) :: {:ok, ok_type} | {:error, err_type}

@spec lookup(String.t()) :: result(User.t(), :not_found)
def lookup(email), do: ...
```

### Common built-in types

| Type | Meaning |
|---|---|
| `atom()` | any atom |
| `boolean()` | `true` \| `false` |
| `integer()` | any integer |
| `pos_integer()` | > 0 |
| `non_neg_integer()` | >= 0 |
| `neg_integer()` | < 0 |
| `float()` | floating point |
| `number()` | integer or float |
| `binary()` | any binary (UTF-8 or raw) |
| `String.t()` | UTF-8 binary (= `binary()` but documents intent) |
| `iolist()` | nested list of bytes/binaries |
| `iodata()` | iolist or binary |
| `charlist()` | `[char()]` |
| `list()` | any list |
| `[type]` | list of `type` |
| `nonempty_list(t)` | `[t, ...]` |
| `map()` | any map |
| `%{key => value}` | map with specific keys |
| `%User{}` | struct (fields set to their field types) |
| `%User{field: type}` | struct with type-constrained fields |
| `tuple()` | any tuple |
| `{t1, t2}` | 2-tuple |
| `keyword()` | `[{atom(), any()}]` |
| `keyword(t)` | `[{atom(), t}]` |
| `nil` | the atom `nil` |
| `no_return()` | function never returns normally (raises/exits) |
| `none()` | no value (e.g., empty list type) |
| `term()` / `any()` | any value (avoid when possible) |

---

## Doctests

Executable examples embedded in `@doc`.

### Basic

```elixir
defmodule MyApp.Math do
  @doc """
  Squares a number.

  ## Examples

      iex> MyApp.Math.square(4)
      16

      iex> MyApp.Math.square(-3)
      9
  """
  def square(n), do: n * n
end
```

### Registration in the test module

```elixir
defmodule MyApp.MathTest do
  use ExUnit.Case, async: true
  doctest MyApp.Math
end
```

### Multi-line input

```elixir
@doc """
## Examples

    iex> 1 +
    ...>   2 +
    ...>   3
    6
"""
```

### With assertion on exception

```elixir
@doc """
## Examples

    iex> MyApp.Math.divide(10, 0)
    ** (ArgumentError) cannot divide by zero
"""
def divide(_, 0), do: raise(ArgumentError, "cannot divide by zero")
def divide(a, b), do: a / b
```

### With `...>` for continuation

```elixir
@doc """
## Examples

    iex> MyApp.List.sum([1, 2, 3])
    6

    iex> list = [4, 5, 6]
    ...> MyApp.List.sum(list)
    15
"""
```

### Ellipsis for variable output

```elixir
@doc """
## Examples

    iex> DateTime.utc_now()
    ~U[... ...]
"""
```

Not a real feature — use `@doc` narrative + actual test in the test file when output varies.

---

## Dialyzer Setup

### mix.exs

```elixir
defp deps do
  [
    {:dialyxir, "~> 1.4", only: [:dev], runtime: false}
  ]
end

def project do
  [
    # ...
    dialyzer: [
      plt_add_apps: [:ex_unit, :mix],
      plt_file: {:no_warn, "priv/plts/dialyzer.plt"},
      flags: [
        :error_handling,
        :extra_return,
        :missing_return,
        :no_improper_lists,
        :underspecs,
        :unknown,
        :unmatched_returns
      ]
    ]
  ]
end
```

### Running

```sh
mix dialyzer              # Builds PLT on first run; slow
mix dialyzer --format short
```

### Ignoring known warnings

Create `.dialyzer_ignore.exs`:

```elixir
[
  # Suppress false positives from third-party code
  ~r/deps\/some_lib\/.*/,
  # Specific warning suppression
  {"lib/my_app/foo.ex", :no_return, 42}
]
```

---

## Compiler Warnings → Spec Fixes

Common warnings and their fixes:

### "Function called at argument N has type X but expected Y"

```elixir
# Spec says
@spec process(integer()) :: String.t()
def process(n), do: Integer.to_string(n)

# But called
process("42")    # ← Dialyzer flags: got binary, expected integer

# Fix: widen spec or fix call-site
@spec process(integer() | String.t()) :: String.t()
def process(n) when is_integer(n), do: Integer.to_string(n)
def process(s) when is_binary(s), do: s
```

### "The pattern can never match the type"

```elixir
# Spec says
@spec fetch(String.t()) :: {:ok, term()}

# Code tries
case MyMod.fetch(key) do
  {:ok, v} -> ...
  :error -> ...    # ← Dialyzer: pattern :error never matches
end

# Fix: spec is wrong — widen to real return
@spec fetch(String.t()) :: {:ok, term()} | :error
```

### "No return" / "Missing return"

Function spec says `:: something()` but the code has a path that never returns (raises or exits). Add `no_return()`:

```elixir
@spec validate!(map()) :: :ok | no_return()
def validate!(map) do
  if map[:ok?], do: :ok, else: raise(ArgumentError)
end
```

---

## Set-theoretic Types (Elixir 1.17+)

New syntax for types with `or`/`not`:

```elixir
# Union (1.17+)
@spec f(integer() or String.t()) :: String.t()

# Classic union still works
@spec f(integer() | String.t()) :: String.t()

# Dynamic type (opt out of inference)
@spec f(dynamic()) :: term()
```

The classic pipe syntax (`|`) remains idiomatic for most code.

---

## When to Write Specs

### Always

- Every public function of a library or context.
- Every behaviour callback.
- Every `@impl` implementation (spec attached to the callback definition is inherited, but explicit specs are clearer).

### Usually

- Non-trivial private functions — makes reasoning easier even without Dialyzer checking.
- Functions with options — `@type opts/0` documents the legal keys.

### Rarely

- Trivial one-liners (`defp a_plus_b(a, b), do: a + b` — spec is boilerplate).
- Test helpers (tests don't run Dialyzer usually).

---

## Common Anti-Patterns (BAD / GOOD)

### 1. Missing `@spec` on public function

```elixir
# BAD — public function with no spec
def register_user(attrs) do
  # ...
end
```

```elixir
# GOOD
@spec register_user(map()) :: {:ok, User.t()} | {:error, Ecto.Changeset.t()}
def register_user(attrs), do: ...
```

### 2. `@spec` using `any()` without reason

```elixir
# BAD — opts out of Dialyzer
@spec get(any()) :: any()
def get(id), do: Repo.get(User, id)
```

```elixir
# GOOD
@spec get(pos_integer()) :: User.t() | nil
def get(id), do: Repo.get(User, id)
```

### 3. Referring to `t()` without defining it

```elixir
# BAD — User.t() silently becomes any()
defmodule User do
  defstruct [:id, :email]
  # No @type t :: ...
end

@spec get(pos_integer()) :: User.t() | nil  # → any() | nil
```

```elixir
# GOOD
defmodule User do
  @type t :: %__MODULE__{id: pos_integer() | nil, email: String.t()}
  defstruct [:id, :email]
end
```

### 4. Doctest with varying output (time/random)

```elixir
# BAD — will fail tomorrow
@doc """
    iex> MyMod.now()
    ~U[2024-12-31T12:00:00Z]
"""
def now, do: DateTime.utc_now()
```

```elixir
# GOOD — either skip doctest, or inject time
@doc """
    iex> MyMod.is_datetime?(DateTime.utc_now())
    true
"""
def is_datetime?(dt), do: is_struct(dt, DateTime)
```

### 5. Documenting every private function

```elixir
# BAD — @doc on defp is silently ignored; clutter
@doc "Normalizes the email"
defp normalize_email(email), do: String.downcase(email)
```

```elixir
# GOOD — just use a clear name
defp normalize_email(email), do: String.downcase(email)
```

### 6. Spec ignoring error path

```elixir
# BAD — omits the error case
@spec fetch_user(pos_integer()) :: User.t()
def fetch_user(id), do: Repo.get(User, id)  # can return nil!
```

```elixir
# GOOD
@spec fetch_user(pos_integer()) :: User.t() | nil
def fetch_user(id), do: Repo.get(User, id)
```

---

## Cross-References

- **Deep type-system reference (set-theoretic types, Dialyzer config, compiler warnings):** `../elixir/type-system.md`
- **Documentation patterns (ExDoc, cross-references):** `../elixir/documentation.md`
- **Idiomatic construct reference:** `./idioms-reference.md`
- **Type strategy for big projects:** `../elixir-planning/SKILL.md`
- **Reviewing types for correctness:** `../elixir-reviewing/SKILL.md`
