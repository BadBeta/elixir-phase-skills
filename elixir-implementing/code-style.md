# Code Style — Implementation Reference

Phase-focused on **writing** style-compliant idiomatic Elixir. Covers the formatter (`.formatter.exs`), Credo check catalog, module organization, function ordering, multi-clause formatting, sigil selection, defdelegate use, and readable-code patterns.

**For architectural decisions about how code is structured at the module/context level**, see `../elixir-planning/architecture-patterns.md`.

---

## Rules for Writing Style-Compliant Elixir

1. **ALWAYS run `mix format` before committing.** No exceptions. CI should `mix format --check-formatted`.
2. **ALWAYS run `mix credo --strict`** and address warnings. Don't suppress; fix or make a considered exception.
3. **ALWAYS configure `.formatter.exs` with `import_deps`** for Phoenix/Ecto/Plug so their DSLs render correctly.
4. **NEVER fight the formatter.** If the formatter produces output you dislike, restructure your code — don't add manual alignment that the formatter will destroy.
5. **ALWAYS alphabetize aliases.** Credo's `AliasOrder` enforces this. Group aliases by first module segment, then alphabetize.
6. **NEVER pipe a single step.** `name |> String.upcase()` → `String.upcase(name)`.
7. **NEVER pipe into an anonymous function directly.** Use `then/1` or name the function.
8. **ALWAYS use underscores in large numbers** (5+ digits). `40_000`, not `40000`. Credo's `LargeNumbers` enforces.
9. **NEVER use `length(list) > 0`** for non-empty check — it's O(n). Use `list != []` or pattern match.
10. **ALWAYS give a `@moduledoc`** (even `@moduledoc false`). Credo's `ModuleDoc` enforces.
11. **PREFER `do`/`end` blocks for complex bodies**, `do:` keyword for one-liners.
12. **NEVER hand-craft configurations that duplicate what `import_deps` would provide.**

---

## `.formatter.exs` — Template

```elixir
# .formatter.exs
[
  inputs: ["{mix,.formatter}.exs", "{config,lib,test}/**/*.{ex,exs}"],

  # line_length 98 is the default; 110-120 is acceptable for wider monitors
  line_length: 98,

  # Pull in DSL configs from deps — use this instead of duplicating locals_without_parens
  import_deps: [:phoenix, :ecto, :ecto_sql, :plug],

  # DSL calls that skip parentheses in YOUR project
  locals_without_parens: [
    my_macro: 1,
    my_macro: 2,
    my_dsl: :*    # :* = all arities
  ],

  # Formatter plugins (since 1.13)
  plugins: [Phoenix.LiveView.HTMLFormatter],

  # For umbrella apps
  subdirectories: ["apps/*"]
]
```

### Library authors — export formatting config

Libraries should `export:` their `locals_without_parens` so consumers can `import_deps:` them:

```elixir
# In your library's .formatter.exs
[
  inputs: [...],
  locals_without_parens: [my_dsl: :*],
  export: [
    locals_without_parens: [my_dsl: :*]
  ]
]
```

### Migration options (Elixir 1.18+)

```sh
mix format --migrate
```

| Migration | Effect |
|---|---|
| `migrate_bitstring_modifiers` | `<<x::binary()>>` → `<<x::binary>>` |
| `migrate_charlists_as_sigils` | `'foo'` → `~c"foo"` |
| `migrate_unless` | `unless x, do: y` → `if !x, do: y` |
| `migrate_call_parens_on_pipe` (1.19+) | `foo \|> bar` → `foo \|> bar()` |

Enable all: `--migrate` flag or `migrate: true` in `.formatter.exs`.

### Formatter commands

```sh
mix format                     # Format all files
mix format --check-formatted   # CI check — exit 1 if unformatted
mix format --dry-run           # Check without writing
mix format lib/my_file.ex      # Format specific file
```

### What the formatter enforces

- 2-space indent, spaces around binary ops, single trailing newline.
- Parens added to all function calls except `locals_without_parens`; removed from `if`/`unless`/`case`/`cond` conditions.
- Large integers get underscores; hex digits uppercased.
- Breaks at `line_length` boundary; multi-line collections get one element per line.

### What the formatter does NOT enforce

- Variable/function naming.
- Module organization order.
- Pipe usage patterns.
- Documentation presence.
- Code complexity.

**→ Credo covers those.**

---

## Credo — Check Catalog

`mix credo` enforces semantic style the formatter can't. Most important checks organized by priority:

### Naming (high priority)

| Check | Rule |
|---|---|
| `FunctionNames` | `snake_case` |
| `VariableNames` | `snake_case` |
| `ModuleNames` | `PascalCase` |
| `ModuleAttributeNames` | `snake_case` |
| `PredicateFunctionNames` | Public: end with `?`. Guards: start with `is_`, no `?` |
| `PreferUnquotedAtoms` | `:foo`, not `:"foo"` (unless needed) |
| `ParenthesesInCondition` | No parens in `if`/`unless` |
| `Semicolons` | Never `;` — use newlines |

### Readability (recommended)

| Check | Rule |
|---|---|
| `SinglePipe` | No single-step pipelines |
| `ModuleDoc` | Every module has `@moduledoc` or `@moduledoc false` |
| `AliasOrder` | Alphabetize aliases in groups |
| `SeparateAliasRequire` | Group all `alias` together, all `require` together |
| `LargeNumbers` | `1_000_000`, not `1000000` |
| `RedundantBlankLines` | Max 1 consecutive blank line |
| `PipeIntoAnonymousFunctions` | Use `then/1`, not `\|> (fn x -> ... end).()` |
| `StringSigils` | Use `~s` when string has 3+ escaped quotes |
| `OnePipePerLine` | Each `\|>` on its own line |
| `OneArityFunctionInPipe` | `\|> String.downcase()`, not `\|> String.downcase` |
| `WithSingleClause` | Single-clause `with` + `else` → use `case` |
| `ImplTrue` | Prefer `@impl MyBehaviour` over `@impl true` when multiple behaviours |

### Consistency (team choice — pick one per project)

| Check | Options |
|---|---|
| `MultiAliasImportRequireUse` | `alias Mod.{A, B}` vs separate `alias` per module |
| `ParameterPatternMatching` | `pattern = param` vs `param = pattern` |
| `UnusedVariableNames` | `_user` (meaningful) vs `_` (anonymous) |

### Running Credo

```sh
mix credo --strict              # all checks, including consistency
mix credo suggest --strict      # just suggestions
mix credo list                  # list all available checks
mix credo explain Credo.Check.Readability.SinglePipe  # details on a specific check
```

---

## Module Organization — Standard Order

The formatter doesn't enforce this, but the community strongly converges on:

```elixir
defmodule MyApp.Accounts.User do
  @moduledoc """
  User accounts and authentication.
  """

  # 1. use — changes module fundamentals
  use Ecto.Schema

  # 2. @behaviour — declared contracts
  @behaviour MyApp.Authenticatable

  # 3. import — brings functions into scope
  import Ecto.Changeset

  # 4. alias — shortens references (STRICTLY alphabetized)
  alias MyApp.Accounts.{Organization, Team}
  alias MyApp.Repo

  # 5. require — compile-time macros
  require Logger

  # 6. Module attributes — constants, config
  @max_login_attempts 5
  @token_ttl :timer.hours(24)

  # 7. @type / @typep — type definitions
  @type t :: %__MODULE__{}
  @typep state :: :active | :suspended

  # 8. @callback — if this module defines a behaviour
  # (usually lives in a separate behaviour module)

  # 9. Schema / struct definition
  schema "users" do
    field :email, :string
    # ...
  end

  # 10. Public functions — the module's API
  def create(attrs), do: ...
  def get!(id), do: ...

  # 11. Callback implementations (@impl true)
  @impl true
  def authenticate(creds), do: ...

  # 12. Private functions
  defp validate_email(cs), do: ...
  defp hash_password(cs), do: ...
end
```

### Alias ordering (Credo `AliasOrder`)

```elixir
# GOOD — strictly alphabetical by first segment, then by full path
alias MyApp.Accounts.{Organization, Team}   # "MyApp.Accounts" group
alias MyApp.Repo                             # "MyApp.Repo"
alias Phoenix.LiveView                       # "Phoenix"

# Within braces, alphabetize: {Organization, Team}, not {Team, Organization}
```

**Don't order by "dependency" or "importance"** — Credo's `AliasOrder` is strict alphabetical.

---

## Function Ordering

Two conventions are acceptable — pick one per project:

### A. Public followed by its private helpers

```elixir
def create_order(params) do
  params |> build_order() |> apply_pricing() |> Repo.insert()
end

defp build_order(params), do: ...
defp apply_pricing(order), do: ...

def cancel_order(order) do
  order |> validate_cancellable() |> do_cancel()
end

defp validate_cancellable(order), do: ...
defp do_cancel(order), do: ...
```

### B. All public first, then private grouped logically

```elixir
def create_order(...), do: ...
def cancel_order(...), do: ...
def list_orders(...), do: ...

# --- private ---

defp build_order(...), do: ...
defp apply_pricing(...), do: ...
defp validate_cancellable(...), do: ...
```

Both are defensible. Convention A reads top-to-bottom; B is easier for navigating many public functions.

---

## Multi-Clause Function Formatting

```elixir
# GOOD — short clauses: one line each, no blank line between
def to_status(:pending), do: "Pending"
def to_status(:active), do: "Active"
def to_status(:archived), do: "Archived"

# GOOD — complex clauses: blank line between each
def handle_event("save", params, socket) do
  # ... multi-line logic
end

def handle_event("delete", %{"id" => id}, socket) do
  # ... multi-line logic
end
```

**When a function has 5+ clauses, consider extracting:**

```elixir
# BAD — 8 handle_event clauses in one module
def handle_event("save", ...), do: ...
def handle_event("delete", ...), do: ...
# ... 6 more

# GOOD — lookup table
@status_labels %{pending: "Pending", active: "Active", archived: "Archived"}
def to_status(status), do: Map.fetch!(@status_labels, status)

# OR: extract to a specialized module
```

---

## String Sigil Selection

| Sigil | Interpolation | Use When |
|---|---|---|
| `""` | Yes | Default — most strings |
| `~s()` | Yes | String contains `"` quotes |
| `~S()` | No | Raw strings, doctests with `#{}` |
| `~r()` | Yes | Regex |
| `~w()` | No | Word lists — `~w(a b c)a` for atoms |
| `~c()` | Yes | Charlists (Erlang interop) — replaces `'string'` |
| `"""` | Yes | Heredocs, multi-line, long SQL |

```elixir
# GOOD — ~s when string has quotes
~s(She said "hello")

# GOOD — ~S in doctests so #{} isn't interpolated
~S"""
iex> parse("#{var}")
{:error, :unresolved}
"""

# GOOD — ~w for atom lists
~w(admin editor viewer)a

# GOOD — heredoc for multi-line SQL
query = """
SELECT u.name, count(p.id)
FROM users u
JOIN posts p ON p.user_id = u.id
GROUP BY u.name
"""

# BAD — escaped quotes when ~s is cleaner
"She said \"hello\""
```

---

## `defdelegate` — When to Use

```elixir
# GOOD — pure pass-through
defmodule MyApp.Accounts do
  defdelegate get_user(id), to: MyApp.Accounts.UserQueries
  defdelegate list_users(opts \\ []), to: MyApp.Accounts.UserQueries
end

# GOOD — rename on delegation
defdelegate active_users, to: MyApp.Accounts.UserQueries, as: :list_active
```

### Decision table

| Scenario | defdelegate? | Why |
|---|:---:|---|
| Pure pass-through to internal module | YES | Zero overhead, clean facade |
| Facade context (Phoenix contexts) | YES | Keeps context as routing layer |
| Delegating to Erlang module | YES | `Map` delegates 6 functions to `:maps` |
| Rename for better API | YES | Use `as:` option |
| Need logging / telemetry | NO | Wrapper — defdelegate can't add logic |
| Transform args / return | NO | Wrapper — args pass-through |
| Need authorization before call | NO | Wrapper — you'll need it later |
| Different `@doc` than target | NO | defdelegate copies target's `@doc` |
| Internal private helper | NO | Just call directly |

**Precedent:** Elixir's `Map` delegates `keys/1`, `values/1`, `merge/2`, `to_list/1` to `:maps`. `String` delegates `split/1`, `trim_leading/1` to `String.Break`. Phoenix contexts use `defdelegate` to route to submodules.

---

## Readable Pipelines

```elixir
# GOOD — multi-step transformation, reads top-to-bottom
order
|> calculate_subtotal()
|> apply_discount(coupon)
|> add_tax(state)
|> round_to_cents()

# BAD — single step
name |> String.upcase()

# GOOD — direct call
String.upcase(name)

# BAD — piping to anon fn
data |> (fn x -> x * 2 end).()

# GOOD — use then/1
data |> then(&(&1 * 2))
```

### Pipe-to-case

```elixir
# OK — end of a genuine multi-step pipeline
data
|> transform()
|> validate()
|> case do
  {:ok, value} -> value
  {:error, _} -> nil
end

# BAD — single-step pipe to case
data |> case do: ...
```

Rule: only use `|> case do` when the pipeline has 2+ real steps. Don't nest pipe-to-case.

---

## With-Chain Formatting

```elixir
# GOOD — each clause on its own line, aligned
with {:ok, user} <- Accounts.get_user(id),
     {:ok, token} <- Tokens.generate(user),
     :ok <- Mailer.send_reset(user, token) do
  {:ok, :email_sent}
else
  {:error, :not_found} -> {:error, :user_not_found}
  {:error, :rate_limited} -> {:error, :try_later}
  {:error, reason} -> {:error, reason}
end

# BAD — with for a single clause; use case instead
with {:ok, user} <- Accounts.get_user(id) do
  {:ok, user.name}
else
  _ -> {:error, :not_found}
end

# GOOD — case for a single pattern
case Accounts.get_user(id) do
  {:ok, user} -> {:ok, user.name}
  _ -> {:error, :not_found}
end
```

---

## Pattern Match Ordering

**Always order from most specific to most general.**

```elixir
# GOOD
def handle_response({:ok, %{status: 200, body: body}}), do: {:ok, decode(body)}
def handle_response({:ok, %{status: 404}}), do: {:error, :not_found}
def handle_response({:ok, %{status: status}}), do: {:error, {:http, status}}
def handle_response({:error, reason}), do: {:error, reason}

# GOOD — success path first
case Repo.insert(changeset) do
  {:ok, record} -> {:ok, record}
  {:error, changeset} -> {:error, format_errors(changeset)}
end
```

---

## Paragraph-Style Whitespace

Use blank lines within a function body to separate logical phases:

```elixir
# GOOD
def process_order(params) do
  # Phase 1: Build
  order = build_order(params)
  items = build_line_items(params.items)

  # Phase 2: Calculate
  subtotal = calculate_subtotal(items)
  tax = calculate_tax(subtotal, params.region)
  total = Decimal.add(subtotal, tax)

  # Phase 3: Persist
  order
  |> Order.changeset(%{items: items, total: total})
  |> Repo.insert()
end
```

---

## Common BAD / GOOD

### Fighting the formatter

```elixir
# BAD — manual alignment; formatter destroys it
result = some_function(arg1,
                       arg2,
                       arg3)

# GOOD — let formatter decide (2-space nesting)
result =
  some_function(
    arg1,
    arg2,
    arg3
  )
```

### Deeply nested data access

```elixir
# BAD — Map.get chain
city = Map.get(Map.get(Map.get(user, :address, %{}), :location, %{}), :city)

# GOOD — get_in with Access path
city = get_in(user, [:address, :location, :city])

# BEST (when shape known) — pattern match
%{address: %{location: %{city: city}}} = user
```

### Magic numbers

```elixir
# BAD — what does 86400 mean?
Process.send_after(self(), :cleanup, 86400 * 1000)

# GOOD — module attribute
@cleanup_interval :timer.hours(24)
Process.send_after(self(), :cleanup, @cleanup_interval)
```

### Identity case statement

```elixir
# BAD — case does nothing
mode = case config.mode do
  :async -> :async
  :sync -> :sync
end

# GOOD — assign directly
mode = config.mode

# If validation is needed, use a private function
defp validate_mode!(:async), do: :async
defp validate_mode!(:sync), do: :sync
defp validate_mode!(other), do: raise ArgumentError, "unknown mode: #{inspect(other)}"
```

### Case that only passes errors through (use `with`)

```elixir
# BAD
case Native.call(args) do
  {:ok, r} -> {:ok, transform(r)}
  {:error, _} = err -> err
end

# GOOD — `with` lets errors fall through
with {:ok, r} <- Native.call(args), do: {:ok, transform(r)}
```

### Magic defaults duplicated in struct + constructor

```elixir
# BAD — default lives in two places
defstruct [timeout: 5_000, max_retries: 3]

def new(opts \\ []) do
  %__MODULE__{
    timeout: Keyword.get(opts, :timeout, 5_000),
    max_retries: Keyword.get(opts, :max_retries, 3)
  }
end

# GOOD — single source of truth
@default_timeout 5_000
@default_max_retries 3

defstruct [timeout: @default_timeout, max_retries: @default_max_retries]

def new(opts \\ []) do
  %__MODULE__{
    timeout: Keyword.get(opts, :timeout, @default_timeout),
    max_retries: Keyword.get(opts, :max_retries, @default_max_retries)
  }
end
```

### Over-aliasing / under-aliasing

```elixir
# BAD — alias for one-time use
alias MyApp.Accounts.Users.ProfilePicture
ProfilePicture.upload(user, file)

# GOOD — full path for one-off
MyApp.Accounts.Users.ProfilePicture.upload(user, file)

# BAD — no alias when used 3+ times
MyApp.Billing.Invoices.InvoiceCalculator.subtotal(items)
MyApp.Billing.Invoices.InvoiceCalculator.tax(items)
MyApp.Billing.Invoices.InvoiceCalculator.total(items)

# GOOD — alias when repeated
alias MyApp.Billing.Invoices.InvoiceCalculator
InvoiceCalculator.subtotal(items)
InvoiceCalculator.tax(items)
InvoiceCalculator.total(items)
```

### `@doc false` on internal-public functions

```elixir
# BAD — function appears in docs as undocumented
def __handle_internal__(data), do: ...

# GOOD — explicit
@doc false
def __handle_internal__(data), do: ...

# Also applies to:
@doc false
def child_spec(opts), do: ...   # OTP-required but not user-facing
```

### Inconsistent private function naming

```elixir
# BAD — mixed conventions
defp _process(data)       # leading underscore is "unused" convention
defp processHelper(data)  # camelCase

# GOOD — snake_case with meaningful prefixes
defp do_process(data)         # do_ for recursive/core logic
defp build_response(data)     # verb_ for actions
defp validate_input(data)
```

### Inline keyword block that should be `do/end`

```elixir
# BAD — long expression crammed into keyword
if user.admin?, do: render(conn, :admin_dashboard, users: list_users(), stats: get_stats()), else: redirect(conn, to: ~p"/")

# GOOD
if user.admin? do
  render(conn, :admin_dashboard, users: list_users(), stats: get_stats())
else
  redirect(conn, to: ~p"/")
end

# GOOD — keyword syntax for simple expressions
if user.admin?, do: :admin, else: :user
```

---

## Cross-References

- **Documentation patterns (`@moduledoc`, `@doc`, `@spec`):** `./type-and-docs.md`
- **Idioms (control flow, pipelines, captures):** `./idioms-reference.md`
- **Anti-patterns catalog (organized by category):** `../elixir-reviewing/anti-patterns-catalog.md`
- **Review checklist (what to flag in a diff):** `../elixir-reviewing/SKILL.md` §7
