# Ecto Patterns — Implementation Templates

Phase-focused on **writing** Ecto code. Covers schemas, changesets, queries, migrations, `Multi`, custom types — the daily-coding syntax and idioms.

**For architectural Ecto concerns** (data ownership, which context owns which table, schema-per-tenant vs row-per-tenant), see `../elixir-planning/data-ownership-deep.md`.

---

## Rules for Writing Ecto Code

1. **ALWAYS put `Repo` calls behind a context function.** Controllers, LiveViews, CLI commands, workers — none call `Repo` directly. Call `Accounts.register_user/1`, not `Repo.insert`.
2. **ALWAYS separate `cast/3` from `validate_*`.** Cast ONCE at the top of the pipeline; then validate. The list of `cast` keys is the whitelist of writable fields.
3. **NEVER use `cast/3` with atoms the user controls.** `cast(struct, params, @allowed)` — `@allowed` is a compile-time list.
4. **ALWAYS use `validate_*` for immediate in-process checks** (shape, format, ranges) and `*_constraint` for DB-enforced checks (uniqueness, foreign keys). These are different phases — don't conflate them.
5. **ALWAYS pair `unique_constraint` with a unique index** in a migration. Without the index, the constraint can silently allow duplicates under race conditions.
6. **NEVER use `Ecto.Query.dynamic/2` without binding bookkeeping.** Pass `[b: binding]` or use a consistent alias with `as: :binding`.
7. **ALWAYS compose queries with pipelines** — accept a base `queryable` and return a new one: `def active(q \\ __MODULE__), do: from(x in q, where: x.active == true)`.
8. **NEVER preload inside a `for` loop** (N+1). Preload at the query level or via `Repo.preload/2` after loading the parent list.
9. **ALWAYS use `Ecto.Multi` when multiple writes must succeed or fail together.** Never call `Repo.insert` + `Repo.update` back-to-back and hope.
10. **NEVER write migrations that do destructive + non-destructive work in the same migration** — split into: (1) additive change + backfill, (2) cut-over code, (3) remove old column/table. See migration patterns below.
11. **ALWAYS use `Repo.transaction/1` with isolation level explicit** when reading-then-writing (`Repo.transaction(fn -> ... end, isolation: :serializable)` or equivalent multi).
12. **NEVER return `Ecto.Query` from a context function.** The context returns data (structs, lists, tuples) — queries are internal. If a caller needs composition, export the narrow composition function.

---

## Schema Template

```elixir
defmodule MyApp.Accounts.User do
  use Ecto.Schema
  import Ecto.Changeset

  @derive {Jason.Encoder, only: [:id, :email, :name]}
  schema "users" do
    field :email, :string
    field :name, :string
    field :hashed_password, :string, redact: true
    field :password, :string, virtual: true, redact: true
    field :role, Ecto.Enum, values: [:user, :admin], default: :user
    field :active?, :boolean, source: :is_active, default: true

    belongs_to :organization, MyApp.Accounts.Organization
    has_many :posts, MyApp.Content.Post
    many_to_many :groups, MyApp.Accounts.Group, join_through: "user_groups"

    timestamps(type: :utc_datetime_usec)
  end

  @castable ~w(email name password role organization_id)a
  @required ~w(email name)a

  def changeset(user, attrs) do
    user
    |> cast(attrs, @castable)
    |> validate_required(@required)
    |> validate_format(:email, ~r/^[^\s]+@[^\s]+\.[^\s]+$/)
    |> validate_length(:name, min: 2, max: 100)
    |> unique_constraint(:email)
    |> assoc_constraint(:organization)
    |> put_hashed_password()
  end

  defp put_hashed_password(%{valid?: true, changes: %{password: pw}} = cs),
    do: put_change(cs, :hashed_password, Bcrypt.hash_pwd_salt(pw))
  defp put_hashed_password(cs), do: cs
end
```

**Key points:**
- `@castable` / `@required` as module attributes — make the whitelist explicit and auditable.
- `redact: true` — keeps sensitive fields out of `inspect/Logger` output.
- `Ecto.Enum` — type-safe string-backed enum.
- `source:` — map an Elixir field name to a different DB column name.
- `timestamps(type: :utc_datetime_usec)` — microsecond precision for sortability; UTC to avoid timezone bugs.
- `@derive {Jason.Encoder, only: [...]}` — explicit whitelist for serialization.
- Changeset helpers (`put_hashed_password/1`) are private and guard on `valid?: true` to skip work on invalid input.

---

## Changeset Patterns

### Multi-step changeset with helper functions

```elixir
def registration_changeset(user, attrs) do
  user
  |> cast(attrs, @castable)
  |> validate_required(@required)
  |> validate_email()
  |> validate_password()
  |> hash_password()
end

defp validate_email(cs) do
  cs
  |> validate_format(:email, ~r/@/)
  |> validate_length(:email, max: 160)
  |> unsafe_validate_unique(:email, MyApp.Repo)  # Hint-only; always keep unique_constraint too
  |> unique_constraint(:email)
end

defp validate_password(cs) do
  cs
  |> validate_length(:password, min: 12, max: 72)
  |> validate_format(:password, ~r/[a-z]/, message: "must contain lowercase")
  |> validate_format(:password, ~r/[A-Z]/, message: "must contain uppercase")
  |> validate_format(:password, ~r/\d/, message: "must contain a digit")
end

defp hash_password(%{valid?: true, changes: %{password: pw}} = cs) do
  cs
  |> put_change(:hashed_password, Bcrypt.hash_pwd_salt(pw))
  |> delete_change(:password)
end
defp hash_password(cs), do: cs
```

### validate_* vs *_constraint

| Check happens... | Use |
|---|---|
| Immediately (before DB call) | `validate_required`, `validate_format`, `validate_length`, `validate_inclusion`, `validate_number` |
| After DB call (needs DB knowledge) | `unique_constraint`, `foreign_key_constraint`, `assoc_constraint`, `check_constraint`, `exclusion_constraint` |
| Pre-check DB for uniqueness (hint, UX only) | `unsafe_validate_unique` (ALWAYS pair with `unique_constraint`) |

### Changeset with association

```elixir
def changeset_with_posts(user, attrs) do
  user
  |> cast(attrs, @castable)
  |> cast_assoc(:posts, with: &MyApp.Content.Post.changeset/2)
end
```

### Force a change even if unchanged

```elixir
changeset |> force_change(:updated_at, DateTime.utc_now())
```

### Changeset against a non-schema (schemaless)

```elixir
types = %{email: :string, password: :string}

{%{}, types}
|> cast(attrs, Map.keys(types))
|> validate_required([:email, :password])
|> validate_format(:email, ~r/@/)
```

---

## Query Templates

### Basic

```elixir
import Ecto.Query

# Simple
from(u in User, where: u.active? == true, order_by: u.inserted_at)

# Composed over a base queryable
query =
  User
  |> where([u], u.active? == true)
  |> order_by([u], desc: u.inserted_at)
  |> limit(10)

Repo.all(query)
```

### Composable query functions

```elixir
defmodule MyApp.Accounts.User do
  import Ecto.Query

  def base, do: from(u in __MODULE__, as: :user)

  def active(q \\ base()), do: where(q, [user: u], u.active? == true)
  def in_org(q \\ base(), org_id), do: where(q, [user: u], u.organization_id == ^org_id)
  def by_name_prefix(q \\ base(), prefix), do: where(q, [user: u], ilike(u.name, ^"#{prefix}%"))

  def recent(q \\ base(), limit),
    do: q |> order_by([user: u], desc: u.inserted_at) |> limit(^limit)
end

# Usage:
User.active() |> User.in_org(org_id) |> User.recent(20) |> Repo.all()
```

**Use `as: :user`** for named bindings — composable across arbitrary join orders.

### Joins & preloading

```elixir
# Preload in one query (JOIN)
from(u in User,
  join: o in assoc(u, :organization),
  preload: [organization: o],
  where: o.active? == true
)
|> Repo.all()

# Preload in N+1 follow-up queries (separate query)
User |> Repo.all() |> Repo.preload(:organization)

# Preload with custom query
preload_query = from(p in Post, order_by: [desc: p.inserted_at], limit: 3)
User |> Repo.all() |> Repo.preload(posts: preload_query)
```

### select — specify return shape

```elixir
# Tuple
from(u in User, select: {u.id, u.email})

# Map
from(u in User, select: %{id: u.id, email: u.email})

# Struct
from(u in User, select: struct(u, [:id, :email]))

# Map into existing struct (partial load)
from(u in User, select: %User{id: u.id, email: u.email})
```

### Aggregates

```elixir
Repo.aggregate(User, :count)
Repo.aggregate(from(u in User, where: u.active?), :count, :id)
Repo.aggregate(User, :avg, :score)
Repo.aggregate(User, :sum, :amount)

# Group-by
from(u in User, group_by: u.role, select: {u.role, count(u.id)})
|> Repo.all()
```

### Subquery

```elixir
top_posts =
  from(p in Post, where: p.upvotes > 100, select: p.user_id)

from(u in User, where: u.id in subquery(top_posts)) |> Repo.all()
```

### Dynamic filters

```elixir
defp build_filter(filters) do
  Enum.reduce(filters, dynamic(true), fn
    {:active, true}, dyn -> dynamic([u], ^dyn and u.active? == true)
    {:org, org_id}, dyn -> dynamic([u], ^dyn and u.organization_id == ^org_id)
    {:search, q}, dyn -> dynamic([u], ^dyn and ilike(u.name, ^"%#{q}%"))
    _, dyn -> dyn
  end)
end

def list_users(filters) do
  from(u in User, where: ^build_filter(filters)) |> Repo.all()
end
```

### Upsert with `on_conflict`

```elixir
Repo.insert(%User{email: "x@y.com", name: "X"},
  on_conflict: {:replace, [:name, :updated_at]},
  conflict_target: :email,
  returning: true
)

# Or with a query
Repo.insert(%Counter{key: "views", count: 1},
  on_conflict: [inc: [count: 1]],
  conflict_target: :key
)
```

### Bulk insert

```elixir
Repo.insert_all(User, [
  %{email: "a@b.c", name: "A", inserted_at: now, updated_at: now},
  %{email: "b@b.c", name: "B", inserted_at: now, updated_at: now}
], returning: true)
```

**Note:** `insert_all` bypasses changesets — validate/prepare data manually. Include `inserted_at`/`updated_at` explicitly (timestamps aren't auto-filled).

### Streaming large result sets

```elixir
Repo.transaction(fn ->
  from(u in User, where: u.inserted_at < ^cutoff)
  |> Repo.stream()
  |> Stream.chunk_every(500)
  |> Stream.each(&archive/1)
  |> Stream.run()
end, timeout: :infinity)
```

---

## `Ecto.Multi` — Transactional Templates

### Two-step write

```elixir
def transfer(from_id, to_id, amount) do
  Ecto.Multi.new()
  |> Ecto.Multi.update(:from, Account.debit_changeset(from_id, amount))
  |> Ecto.Multi.update(:to, Account.credit_changeset(to_id, amount))
  |> Ecto.Multi.insert(:ledger, fn %{from: from, to: to} ->
    Ledger.changeset(%{from_id: from.id, to_id: to.id, amount: amount})
  end)
  |> Repo.transaction()
  |> case do
    {:ok, %{from: from, to: to}} -> {:ok, %{from: from, to: to}}
    {:error, step, reason, _changes} -> {:error, step, reason}
  end
end
```

### Conditional step

```elixir
Multi.new()
|> Multi.insert(:user, changeset)
|> Multi.run(:welcome_email, fn _repo, %{user: user} ->
  if user.email_verified?, do: {:ok, :skipped}, else: send_welcome(user)
end)
|> Repo.transaction()
```

### Upsert inside Multi

```elixir
Multi.new()
|> Multi.insert(:account, %Account{...},
    on_conflict: {:replace, [:name]},
    conflict_target: :external_id)
|> Multi.insert_all(:logs, Log, log_rows)
|> Repo.transaction()
```

### Multi with error step (return early)

```elixir
Multi.new()
|> Multi.run(:check, fn _repo, _changes ->
  if valid?(params), do: {:ok, :proceed}, else: {:error, :invalid}
end)
|> Multi.insert(:user, changeset)
|> Repo.transaction()
```

---

## Repo API — Common Calls

| Operation | Call |
|---|---|
| Get by primary key | `Repo.get(User, id)` / `Repo.get!(User, id)` |
| Get by other field | `Repo.get_by(User, email: email)` |
| All | `Repo.all(query)` |
| One (expect 0 or 1) | `Repo.one(query)` / `Repo.one!(query)` |
| Exists? | `Repo.exists?(query)` |
| Insert | `Repo.insert(changeset)` |
| Update | `Repo.update(changeset)` |
| Delete | `Repo.delete(struct)` / `Repo.delete(changeset)` |
| Bulk insert | `Repo.insert_all(User, entries)` |
| Bulk update | `Repo.update_all(query, set: [...])` |
| Bulk delete | `Repo.delete_all(query)` |
| Preload after load | `Repo.preload(records, :assoc)` |
| Transaction | `Repo.transaction(fn -> ... end)` / `Repo.transaction(multi)` |
| Stream | `Repo.stream(query)` (inside transaction) |

### When to use `!` variants

- **Use `!`** when the record MUST exist (route params with `/users/:id` where missing = 404 at router level).
- **Don't use `!`** in domain logic where absence is a valid case — return `{:error, :not_found}`.

---

## Migration Templates

### Basic create table

```elixir
defmodule MyApp.Repo.Migrations.CreateUsers do
  use Ecto.Migration

  def change do
    create table(:users) do
      add :email, :string, null: false
      add :name, :string, null: false
      add :hashed_password, :string, null: false
      add :role, :string, null: false, default: "user"
      add :is_active, :boolean, null: false, default: true
      add :organization_id, references(:organizations, on_delete: :restrict), null: false

      timestamps(type: :utc_datetime_usec)
    end

    create unique_index(:users, [:email])
    create index(:users, [:organization_id])
    create index(:users, [:organization_id, :role])  # Composite for common query
  end
end
```

### `on_delete` options

| Option | Behavior |
|---|---|
| `:nothing` (default) | DB raises on parent delete if children exist |
| `:delete_all` | Delete children when parent deleted (cascade) |
| `:nilify_all` | Set FK to NULL on parent delete (requires nullable FK) |
| `:restrict` | Explicit equivalent of `:nothing` (recommended for clarity) |

### Additive migration — safe schema change

```elixir
# Phase 1: Add column nullable
def change do
  alter table(:users) do
    add :timezone, :string
  end
end

# Phase 2 (separate migration, after deployment + backfill):
def change do
  execute "UPDATE users SET timezone = 'UTC' WHERE timezone IS NULL"
  alter table(:users) do
    modify :timezone, :string, null: false
  end
end
```

### Renaming a column (zero-downtime)

```elixir
# Phase 1 — add new, backfill, dual-write
def change do
  alter table(:users), do: add :email_address, :string
  execute "UPDATE users SET email_address = email"
  create unique_index(:users, [:email_address])
end

# App code: write both columns, prefer new on read. Deploy.

# Phase 2 — drop old column after verifying dual-write
def change do
  alter table(:users), do: remove :email
end
```

### Adding an index — concurrently (Postgres)

```elixir
defmodule MyApp.Repo.Migrations.IndexUserEmail do
  use Ecto.Migration
  @disable_ddl_transaction true
  @disable_migration_lock true

  def change do
    create index(:users, [:email], concurrently: true)
  end
end
```

**Why:** regular `create index` locks the table. For large production tables, `concurrently: true` builds without locking writes. `@disable_ddl_transaction true` is required (CONCURRENTLY cannot run in a transaction).

### Data backfill pattern

```elixir
defmodule MyApp.Repo.Migrations.BackfillUserTimezone do
  use Ecto.Migration
  import Ecto.Query

  def up do
    from(u in "users", where: is_nil(u.timezone))
    |> MyApp.Repo.update_all(set: [timezone: "UTC"])
  end

  def down, do: :ok
end
```

**Keep schema references inside migrations minimal** — use `"users"` (string) not `MyApp.Accounts.User` (module). Migrations must work against historical schemas; module references rot.

### Enum migration

```elixir
# Create enum type (Postgres)
def up do
  execute "CREATE TYPE user_role AS ENUM ('user', 'admin', 'superuser')"
  alter table(:users), do: add :role, :user_role, null: false, default: "user"
end

def down do
  alter table(:users), do: remove :role
  execute "DROP TYPE user_role"
end
```

### Check constraint

```elixir
create constraint("users", :positive_age, check: "age > 0")
```

---

## Custom Ecto Types

For a field that needs custom encoding (e.g., a money value, a versioned enum):

```elixir
defmodule MyApp.Types.Money do
  use Ecto.Type

  def type, do: :integer  # DB type

  # Elixir runtime value from params (user input)
  def cast(%Decimal{} = d), do: {:ok, Money.from_decimal(d)}
  def cast(n) when is_integer(n), do: {:ok, Money.new(n)}
  def cast(%Money{} = m), do: {:ok, m}
  def cast(_), do: :error

  # Elixir value to DB
  def dump(%Money{cents: c}), do: {:ok, c}
  def dump(_), do: :error

  # DB value to Elixir
  def load(c) when is_integer(c), do: {:ok, Money.new(c)}
end
```

Then use in schema: `field :amount, MyApp.Types.Money`.

---

## Schemaless Changesets (Forms without schemas)

```elixir
def registration_form(params) do
  types = %{email: :string, password: :string, accept_tos: :boolean}

  {%{}, types}
  |> cast(params, Map.keys(types))
  |> validate_required([:email, :password, :accept_tos])
  |> validate_format(:email, ~r/@/)
  |> validate_acceptance(:accept_tos)
end
```

Useful for multi-step forms, search filters, or any domain shape that doesn't map 1:1 to a table.

---

## Repo Logging, Slow Query Detection

```elixir
# config/dev.exs — see all SQL
config :my_app, MyApp.Repo, log: :debug

# Production — only log slow queries via telemetry
:telemetry.attach("slow-queries", [:my_app, :repo, :query], fn _event, %{query_time: t}, meta, _cfg ->
  if t > 100_000_000, do: Logger.warning("Slow query: #{meta.query} (#{div(t, 1_000_000)}ms)")
end, nil)
```

---

## Common Anti-Patterns (BAD / GOOD)

### 1. Calling `Repo` from a controller

```elixir
# BAD — controller coupled to persistence
def show(conn, %{"id" => id}) do
  user = MyApp.Repo.get!(MyApp.Accounts.User, id)
  render(conn, :show, user: user)
end
```

```elixir
# GOOD — through context
def show(conn, %{"id" => id}) do
  user = MyApp.Accounts.get_user!(id)
  render(conn, :show, user: user)
end
```

### 2. `cast/3` with user-controlled keys

```elixir
# BAD — user can set arbitrary fields, including admin/role
def changeset(user, attrs), do: cast(user, attrs, Map.keys(attrs))
```

```elixir
# GOOD — whitelist at module attribute
@castable ~w(email name)a  # role not included; not user-settable
def changeset(user, attrs), do: cast(user, attrs, @castable)
```

### 3. Validating uniqueness without the DB constraint

```elixir
# BAD — race-prone; two parallel inserts may both pass validation
def changeset(user, attrs) do
  user
  |> cast(attrs, @castable)
  |> validate_required([:email])
  |> Repo.exists?(...) |> validate_unique_in_code()  # Custom check — racy
end
```

```elixir
# GOOD — DB enforces uniqueness; changeset translates DB error to user-friendly message
def changeset(user, attrs) do
  user
  |> cast(attrs, @castable)
  |> validate_required([:email])
  |> unique_constraint(:email)  # Requires unique index
end
```

### 4. N+1 query

```elixir
# BAD
users = Repo.all(User)
Enum.map(users, fn u -> Repo.preload(u, :organization) end)  # N queries
```

```elixir
# GOOD
users = User |> Repo.all() |> Repo.preload(:organization)    # 2 queries total
# OR
users = from(u in User, preload: :organization) |> Repo.all()  # 1 query with JOIN
```

### 5. Multiple `Repo` calls where `Multi` is needed

```elixir
# BAD — partial success on crash
{:ok, user} = Repo.insert(user_changeset)
{:ok, _profile} = Repo.insert(profile_changeset(user))  # What if this fails?
```

```elixir
# GOOD — atomic
Multi.new()
|> Multi.insert(:user, user_changeset)
|> Multi.insert(:profile, fn %{user: user} -> profile_changeset(user) end)
|> Repo.transaction()
```

### 6. Destructive migration in one step

```elixir
# BAD — drop + add in one migration, deploy breaks between migration run and code deploy
def change do
  alter table(:users) do
    remove :old_field
    add :new_field, :string
  end
end
```

```elixir
# GOOD — three phases across deploys:
# 1. Add :new_field (still writing :old_field in code)
# 2. Deploy code that dual-writes, reads :new_field
# 3. Backfill :new_field from :old_field
# 4. Separate migration: remove :old_field
```

### 7. Returning a query from a context

```elixir
# BAD — leaks Ecto.Query to callers
def list_active_users, do: from(u in User, where: u.active?)
# Caller must then call `Repo.all` — context abstraction broken
```

```elixir
# GOOD
def list_active_users, do: from(u in User, where: u.active?) |> Repo.all()
```

---

## Cross-References

- **Data ownership / context boundaries / migration strategies:** `../elixir-planning/data-ownership-deep.md`
- **Multi-tenancy architecture (row/schema/DB):** `../elixir-planning/data-ownership-deep.md#multi-tenancy`
- **Ecto stdlib reference lookup:** `../elixir/ecto-reference.md` + `../elixir/ecto-examples.md`
- **Testing Ecto code (sandbox, factories):** `./testing-patterns.md` + `../elixir-planning/test-strategy.md`
- **Reviewing DB access code:** `../elixir-reviewing/SKILL.md` (N+1 detection, migration audits)
