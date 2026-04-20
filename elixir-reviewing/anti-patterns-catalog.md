# Anti-Patterns Catalog

Consolidated catalog of Elixir anti-patterns for use during review. Organized by category — scan the section that matches the code under review.

**Layout:** each entry has a **pattern name**, **why it's bad**, and **the fix**. Severity (block/request-change/suggest) applies contextually — see `./SKILL.md` §6.

**Related:** `./performance-catalog.md` covers performance-specific pitfalls in depth (symptom → root cause → fix → evidence). This catalog covers structural, idiom, process, design, testing, and security anti-patterns.

---

## A. Code-Level Anti-Patterns

### A1. `if` for structural dispatch

**Why it's bad:** `if` with `is_struct`/`is_map_key`/`is_*` guards hides what's really type dispatch. Multi-clause function heads express intent directly and let the compiler optimize.

```elixir
# BAD
def handle(event) do
  if is_struct(event, Click), do: handle_click(event), else: handle_other(event)
end

# GOOD
def handle(%Click{} = e), do: handle_click(e)
def handle(e), do: handle_other(e)
```

### A2. `try/rescue` for expected failures

**Why it's bad:** `rescue` is for truly exceptional cases. Expected failures (missing keys, parse errors, validation) should return `{:ok, _}` / `{:error, _}` tuples.

```elixir
# BAD
try do
  Integer.parse!(user_input)
rescue
  ArgumentError -> {:error, :invalid}
end

# GOOD
case Integer.parse(user_input) do
  {n, ""} -> {:ok, n}
  _ -> {:error, :invalid}
end
```

### A3. Single-step pipeline

**Why it's bad:** Pipelines are for sequences. A single step adds noise.

```elixir
# BAD
name |> String.upcase()

# GOOD
String.upcase(name)
```

### A4. Single-step pipeline into `case`

**Why it's bad:** Same as A3 plus pipe-to-case overhead.

```elixir
# BAD
result |> case do
  :ok -> ...
  _ -> ...
end

# GOOD
case result do
  :ok -> ...
  _ -> ...
end
```

### A5. Nested `case` where `with` fits

**Why it's bad:** Nested cases have O(n²) visual complexity. `with` linearizes the ok/error flow.

```elixir
# BAD — 3 levels deep
case A.get(id) do
  {:ok, a} ->
    case B.get(a.id) do
      {:ok, b} ->
        case C.do_thing(b) do
          {:ok, result} -> {:ok, result}
          err -> err
        end
      err -> err
    end
  err -> err
end

# GOOD
with {:ok, a} <- A.get(id),
     {:ok, b} <- B.get(a.id),
     {:ok, result} <- C.do_thing(b) do
  {:ok, result}
end
```

### A6. Anonymous function wrapping single call

**Why it's bad:** Verbose. Function captures are idiomatic.

```elixir
# BAD
Enum.map(users, fn u -> User.name(u) end)

# GOOD
Enum.map(users, &User.name/1)
```

### A7. `Enum.each/2` used to accumulate

**Why it's bad:** Rebinding inside `each` doesn't escape the closure.

```elixir
# BAD
total = 0
Enum.each(items, fn i -> total = total + i.price end)
IO.puts(total)   # Still 0!

# GOOD
total = Enum.reduce(items, 0, &(&1.price + &2))
```

### A8. `length(list) > 0` for emptiness

**Why it's bad:** O(n) — traverses the whole list.

```elixir
# BAD
if length(items) > 0, do: process(items)

# GOOD
if items != [], do: process(items)

# OR pattern match
case items do
  [] -> :empty
  _ -> process(items)
end
```

### A9. `map[:key] != nil` — can't distinguish missing key from nil value

**Why it's bad:** Ambiguous — `nil` may mean "key absent" OR "value is nil".

```elixir
# BAD
if config[:timeout] != nil, do: use_timeout(config[:timeout])

# GOOD
case Map.fetch(config, :timeout) do
  {:ok, timeout} -> use_timeout(timeout)
  :error -> use_default()
end
```

### A10. `Map.put` on a struct

**Why it's bad:** Silently accepts typo'd keys. `%{s | k: v}` raises on unknown keys.

```elixir
# BAD
Map.put(user, :emali, "x@y.com")   # typo silently added as new map key

# GOOD
%{user | email: "x@y.com"}         # raises KeyError on typo
```

### A11. `String.to_atom/1` on untrusted input

**Why it's bad:** Atom table is bounded (~1M default) and never GC'd. DoS vector.

```elixir
# BAD
key = String.to_atom(params["key"])

# GOOD
key = String.to_existing_atom(params["key"])

# BEST — whitelist
@allowed ~w(active inactive pending)a
if params["key"] in Enum.map(@allowed, &to_string/1),
  do: String.to_existing_atom(params["key"]),
  else: :invalid
```

### A12. String concatenation in a loop

**Why it's bad:** `<>` in `reduce` is O(n²). Each call allocates a new binary.

```elixir
# BAD
Enum.reduce(parts, "", fn p, acc -> acc <> p end)

# GOOD
IO.iodata_to_binary(parts)

# OR — pass IO list directly to I/O
IO.write(parts)
```

### A13. `Map.values |> Enum.filter` — two passes

**Why it's bad:** Materializes intermediate list.

```elixir
# BAD
map |> Map.values() |> Enum.filter(& &1.active?)

# GOOD
for {_, %{active?: true} = v} <- map, do: v
```

### A14. Identity `case` statement

**Why it's bad:** Does nothing — every clause returns its own input.

```elixir
# BAD
mode = case config.mode do
  :async -> :async
  :sync -> :sync
end

# GOOD
mode = config.mode
```

### A15. Pipe to anonymous function

**Why it's bad:** Awkward syntax. `then/1` is idiomatic.

```elixir
# BAD
data |> (fn x -> x * 2 end).()

# GOOD
data |> then(&(&1 * 2))
```

### A16. Hand-aligned multi-line calls

**Why it's bad:** Formatter will destroy the alignment.

```elixir
# BAD
result = some_function(arg1,
                       arg2,
                       arg3)

# GOOD — let formatter own the layout
result =
  some_function(
    arg1,
    arg2,
    arg3
  )
```

### A17. Defensive extraction where assertive match is better

**Why it's bad:** Defensive extraction of internal data hides bugs. Assertive match crashes on violation — the bug surfaces immediately.

```elixir
# BAD — internal data, defensive
def process(response) do
  body = Map.get(response, :body, nil)
  status = Map.get(response, :status, 0)
  handle(status, body)
end

# GOOD — internal data, assertive
def process(%{status: status, body: body}), do: handle(status, body)
```

(For external/user input, defensive is correct — see A11.)

---

## B. Process & OTP Anti-Patterns

### B1. Blocking `init/1`

**Why it's bad:** Supervisor blocks during `init`. If one child takes 30s, the whole tree waits.

```elixir
# BAD
def init(opts) do
  data = expensive_load()
  {:ok, %{data: data}}
end

# GOOD
def init(opts), do: {:ok, %{data: nil, opts: opts}, {:continue, :load}}

def handle_continue(:load, state) do
  {:noreply, %{state | data: expensive_load()}}
end
```

### B2. Unsupervised `spawn`

**Why it's bad:** Crashes are silent; work disappears.

```elixir
# BAD
spawn(fn -> send_email(user) end)

# GOOD
Task.Supervisor.start_child(MyApp.TaskSup, fn -> send_email(user) end)
```

### B3. `try/rescue` instead of `catch :exit` for GenServer.call

**Why it's bad:** GenServer.call raises **exits** not exceptions. `rescue` won't catch them.

```elixir
# BAD — won't catch the exit
try do
  GenServer.call(pid, :status)
rescue
  _ -> {:error, :down}
end

# GOOD
try do
  GenServer.call(pid, :status)
catch
  :exit, _ -> {:error, :down}
end
```

### B4. Missing `handle_info/2` catch-all

**Why it's bad:** Stray `:DOWN`, `:EXIT`, or telemetry messages crash the process.

```elixir
# BAD
def handle_info({:my_event, data}, state), do: ...
# (no catch-all)

# GOOD
def handle_info({:my_event, data}, state), do: ...
def handle_info(_msg, state), do: {:noreply, state}
```

### B5. `GenServer.call` with default timeout in hot path

**Why it's bad:** 5s tail latency spikes when the callee is busy.

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

### B6. GenServer as a read-heavy registry

**Why it's bad:** Single process serializes all reads — bottleneck.

```elixir
# BAD
defmodule Cache do
  use GenServer
  def get(k), do: GenServer.call(__MODULE__, {:get, k})
  def handle_call({:get, k}, _, state), do: {:reply, Map.get(state, k), state}
end

# GOOD — ETS bypasses the mailbox
:ets.new(:my_cache, [:set, :named_table, :public, read_concurrency: true])

def get(k) do
  case :ets.lookup(:my_cache, k) do
    [{^k, v}] -> {:ok, v}
    [] -> :error
  end
end
```

### B7. `Process.sleep` in a GenServer callback

**Why it's bad:** Blocks all pending messages for the sleep duration.

```elixir
# BAD
def handle_info(:tick, state) do
  Process.sleep(10_000)
  work()
  Process.send(self(), :tick, ...)
  {:noreply, state}
end

# GOOD
def handle_info(:tick, state) do
  work()
  Process.send_after(self(), :tick, 10_000)
  {:noreply, state}
end
```

### B8. `Agent` holding complex business logic

**Why it's bad:** Business rules buried in Agent closures are untestable and invisible.

```elixir
# BAD
Agent.update(Cart, fn cart ->
  if Enum.count(cart.items) >= 50, do: cart, else: %{cart | items: [item | cart.items]}
end)

# GOOD — GenServer with State module holding pure logic
defmodule Cart do
  use GenServer
  defmodule State do
    def add_item(%{items: items} = s, _item) when length(items) >= 50, do: s
    def add_item(%{items: items} = s, item), do: %{s | items: [item | items]}
  end
  # ... delegate in callbacks
end
```

### B9. Named `start_link` that can't be instanced

**Why it's bad:** `name: __MODULE__` hardcoded blocks tests and multi-instance.

```elixir
# BAD
def start_link(_), do: GenServer.start_link(__MODULE__, [], name: __MODULE__)

# GOOD
def start_link(opts) do
  name = Keyword.get(opts, :name, __MODULE__)
  GenServer.start_link(__MODULE__, opts, name: name)
end
```

### B10. `active: true` on a TCP listener

**Why it's bad:** BEAM delivers every packet as a message — mailbox overflow.

```elixir
# BAD
:gen_tcp.listen(port, [:binary, active: true])

# GOOD
:gen_tcp.listen(port, [:binary, active: :once, packet: 4])
```

### B11. Handling client in the acceptor process

**Why it's bad:** Next `accept/1` is starved while you serve the current client.

```elixir
# BAD
def accept_loop(sock) do
  {:ok, client} = :gen_tcp.accept(sock)
  handle_client(client)
  accept_loop(sock)
end

# GOOD — spawn per connection
def accept_loop(sock) do
  {:ok, client} = :gen_tcp.accept(sock)
  {:ok, pid} = Task.Supervisor.start_child(Sup, fn -> handle_client(client) end)
  :gen_tcp.controlling_process(client, pid)
  accept_loop(sock)
end
```

### B12. `terminate/2` assumed to run on crash

**Why it's bad:** `terminate/2` is only called on `{:stop, _, _}` and normal shutdown, **not** on link-propagated exits. Use `trap_exit` if you need cleanup.

```elixir
# BAD — cleanup won't run on sibling crash
def terminate(_, %{file: file}), do: File.close(file)

# GOOD
def init(_) do
  Process.flag(:trap_exit, true)
  # ... now terminate/2 is called on supervisor shutdown
end
```

---

## C. Ecto / Data Anti-Patterns

### C1. N+1 preloads

**Why it's bad:** One query per parent.

```elixir
# BAD
users = Repo.all(User)
Enum.map(users, fn u -> Repo.preload(u, :organization) end)

# GOOD
users = User |> Repo.all() |> Repo.preload(:organization)
# OR
users = from(u in User, preload: :organization) |> Repo.all()
```

### C2. `Repo.all |> length` for count

**Why it's bad:** Loads all rows into memory to count them.

```elixir
# BAD
count = Repo.all(from(u in User, where: u.active?)) |> length()

# GOOD
count = Repo.aggregate(from(u in User, where: u.active?), :count, :id)
```

### C3. Calling `Repo` directly from controller/LiveView

**Why it's bad:** Breaks context abstraction; couples HTTP layer to persistence.

```elixir
# BAD
def show(conn, %{"id" => id}) do
  user = Repo.get!(User, id)
  render(conn, :show, user: user)
end

# GOOD
def show(conn, %{"id" => id}) do
  user = Accounts.get_user!(id)
  render(conn, :show, user: user)
end
```

### C4. `cast/3` with user-controlled keys

**Why it's bad:** User can set arbitrary fields, including `role: :admin`.

```elixir
# BAD
def changeset(user, attrs), do: cast(user, attrs, Map.keys(attrs))

# GOOD
@castable ~w(email name password)a    # whitelist at compile time
def changeset(user, attrs), do: cast(user, attrs, @castable)
```

### C5. Validating uniqueness without DB constraint

**Why it's bad:** Race condition — two parallel inserts can both pass.

```elixir
# BAD — racy
def changeset(user, attrs) do
  user |> cast(attrs, @castable) |> validate_unique_in_code()
end

# GOOD
def changeset(user, attrs) do
  user
  |> cast(attrs, @castable)
  |> unique_constraint(:email)   # DB enforces + changeset translates DB error
end
# Must pair with: create unique_index(:users, [:email]) in a migration
```

### C6. Returning a query from a context

**Why it's bad:** Leaks Ecto.Query to callers; context abstraction broken.

```elixir
# BAD
def list_active_users, do: from(u in User, where: u.active?)

# GOOD
def list_active_users, do: from(u in User, where: u.active?) |> Repo.all()
```

### C7. Multiple `Repo` calls where `Multi` is needed

**Why it's bad:** Partial success on crash.

```elixir
# BAD
{:ok, user} = Repo.insert(user_cs)
{:ok, _} = Repo.insert(profile_cs(user))   # What if this fails?

# GOOD
Multi.new()
|> Multi.insert(:user, user_cs)
|> Multi.insert(:profile, fn %{user: u} -> profile_cs(u) end)
|> Repo.transaction()
```

### C8. Destructive migration in one step

**Why it's bad:** Between migration run and code deploy, code is broken.

```elixir
# BAD — drop + add in one migration
def change do
  alter table(:users) do
    remove :old_field
    add :new_field, :string
  end
end

# GOOD — three phases across deploys:
# 1. Add :new_field
# 2. Dual-write in code; read from :new_field
# 3. Backfill :new_field from :old_field
# 4. Separate migration: remove :old_field
```

### C9. Long work inside `Repo.transaction`

**Why it's bad:** Holds DB connection → pool exhaustion under load.

```elixir
# BAD
Repo.transaction(fn ->
  user = Repo.insert!(cs)
  send_welcome_email(user)   # Network I/O under lock
  log_to_s3(user)
end)

# GOOD
{:ok, user} = Repo.insert(cs)
Task.Supervisor.start_child(Sup, fn -> send_welcome_email(user) end)
Task.Supervisor.start_child(Sup, fn -> log_to_s3(user) end)
```

### C10. Query without tenant/user scope

**Why it's bad:** IDOR — any user can access any record by ID.

```elixir
# BAD
def show(conn, %{"id" => id}) do
  post = Repo.get!(Post, id)   # ANY post, not just current user's
  render(conn, :show, post: post)
end

# GOOD — scope at context
def get_user_post!(user, id) do
  Post |> where(user_id: ^user.id) |> Repo.get!(id)
end
```

---

## D. Architecture & Design Anti-Patterns

### D1. Side effects mixed into domain logic

**Why it's bad:** Domain becomes untestable; hard to reason about.

```elixir
# BAD
defmodule Orders do
  def place(params) do
    order = calculate(params)
    Mailer.send_confirmation(order)     # Side effect in business logic
    SMSNotifier.send(order.user)        # Another side effect
    Analytics.track(order)               # Another
    {:ok, order}
  end
end

# GOOD — domain is pure; side effects are event-driven
defmodule Orders do
  def place(params) do
    order = calculate(params)
    Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:placed, order})
    {:ok, order}
  end
end

# Side effect handlers are separately supervised
defmodule Notifications.Worker do
  def handle_info({:placed, order}, state) do
    Mailer.send_confirmation(order)
    {:noreply, state}
  end
end
```

### D2. Modules that skip the context layer

**Why it's bad:** Coupling from controller/job/worker directly to schema/query bypasses the domain boundary.

```elixir
# BAD
defmodule MyAppWeb.UserController do
  def show(conn, %{"id" => id}) do
    user = Repo.get!(MyApp.Accounts.User, id)
    # ...
  end
end

# GOOD
defmodule MyAppWeb.UserController do
  def show(conn, %{"id" => id}) do
    user = MyApp.Accounts.get_user!(id)
    # ...
  end
end
```

### D3. Shared state between contexts via global

**Why it's bad:** Hidden coupling; can't split into services later.

```elixir
# BAD — two contexts reading/writing the same :persistent_term
defmodule Accounts, do: :persistent_term.put({:shared, :session}, data)
defmodule Billing, do: :persistent_term.get({:shared, :session})
# Now Billing can't move without knowing about Accounts internals
```

```elixir
# GOOD — explicit API between contexts
defmodule Accounts do
  def current_session(user_id), do: ...   # public
end

defmodule Billing do
  def charge(user_id) do
    {:ok, session} = Accounts.current_session(user_id)
    # ...
  end
end
```

### D4. Protocol + behaviour confusion

**Why it's bad:** Protocols dispatch on data type; behaviours dispatch on module. Using protocols for strategy pattern (where module is the strategy) creates confusing code.

```elixir
# BAD — protocol where behaviour is the natural fit
defprotocol StorageBackend do
  def put(backend, key, value)
  def get(backend, key)
end
# The "backend" is effectively a module — but Protocol dispatches on struct type

# GOOD — behaviour for strategy
defmodule StorageBackend do
  @callback put(key :: String.t(), value :: term()) :: :ok | {:error, term()}
  @callback get(key :: String.t()) :: {:ok, term()} | :error
end

defmodule RedisBackend do
  @behaviour StorageBackend
  # ...
end
```

### D5. Leaky abstraction (context exposes schema)

**Why it's bad:** Callers depend on schema fields; changes to DB schema ripple through UI.

```elixir
# BAD
def get_user(id), do: Repo.get(User, id)
# Caller does: user.hashed_password, user.internal_notes, ...

# GOOD — context returns public-safe view, or at least filters sensitive fields
def get_user(id) do
  case Repo.get(User, id) do
    nil -> {:error, :not_found}
    user -> {:ok, %{id: user.id, email: user.email, name: user.name}}
  end
end
```

### D6. Over-supervision of ephemeral work

**Why it's bad:** Creating a permanent supervisor for a one-shot parallel map is waste.

```elixir
# BAD — DynamicSupervisor just to run 100 tasks once
{:ok, _} = DynamicSupervisor.start_link(strategy: :one_for_one, name: Sup)
Enum.each(urls, fn url ->
  DynamicSupervisor.start_child(Sup, {Task, fn -> fetch(url) end})
end)

# GOOD — Task.async_stream
urls
|> Task.async_stream(&fetch/1, max_concurrency: 10, timeout: 30_000)
|> Enum.to_list()
```

### D7. Under-supervision of long-running work

**Why it's bad:** `spawn_link` for work that outlives the caller; no restart strategy.

```elixir
# BAD
spawn_link(fn -> cron_loop() end)

# GOOD
children = [MyApp.CronWorker]
Supervisor.start_link(children, strategy: :one_for_one)
```

### D8. `Application.get_env` in hot paths

**Why it's bad:** Each call goes through the application controller — unnecessary overhead.

```elixir
# BAD
def handle_request(conn) do
  timeout = Application.get_env(:my_app, :timeout)   # on every request
  # ...
end

# GOOD — cache as module attribute (compile-time) or :persistent_term (runtime-changeable)
@timeout Application.compile_env(:my_app, :timeout, 5_000)

# OR for runtime:
:persistent_term.put({MyApp, :timeout}, Application.get_env(:my_app, :timeout))
def handle_request(_), do: :persistent_term.get({MyApp, :timeout})
```

---

## E. Testing Anti-Patterns

### E1. `Process.sleep` waiting for async work

**Why it's bad:** Flaky on slow CI; slow on fast CI.

```elixir
# BAD
MyApp.Worker.trigger(pid)
Process.sleep(500)
assert MyApp.State.get() == :done

# GOOD — message-driven
:telemetry.attach("t", [:worker, :done], fn _, _, _, _ -> send(self(), :done) end, nil)
MyApp.Worker.trigger(pid)
assert_receive :done, 1_000
```

### E2. Hand-crafted schema structs

**Why it's bad:** Duplicates changeset logic. When validation changes, tests don't.

```elixir
# BAD
{:ok, user} = Repo.insert(%User{email: "x", hashed_password: "fake"})

# GOOD
user = AccountsFixtures.user_fixture()
# Uses Accounts.register_user/1 → real changeset path
```

### E3. Mocking what you own

**Why it's bad:** Mock replaces the code under test; you're testing the mock, not reality.

```elixir
# BAD — mocks your own repo module
expect(MyApp.UserRepoMock, :get, fn _ -> %User{} end)
Accounts.register_user(attrs)

# GOOD — use real Repo via sandbox; mock only external boundaries
MyApp.EmailSender.Mock |> expect(:send, fn _, _, _ -> {:ok, :sent} end)
Accounts.register_user(attrs)
```

### E4. `async: false` without stated global

**Why it's bad:** Slows the suite. `async: false` should cite its reason.

```elixir
# BAD
defmodule MyTest do
  use ExUnit.Case, async: false   # why?
  test "pure function", do: assert MyMath.add(1, 2) == 3
end

# GOOD
defmodule MyTest do
  use ExUnit.Case, async: true
  test "pure function", do: assert MyMath.add(1, 2) == 3
end
```

### E5. Testing implementation, not behaviour

**Why it's bad:** Coupled to internals; breaks on refactor even when behaviour is intact.

```elixir
# BAD
test "add_item calls Logger.info" do
  assert_called Logger.info(:_) do
    Cart.add_item(cart, item)
  end
end

# GOOD
test "add_item returns updated cart with the item" do
  new_cart = Cart.add_item(cart, item)
  assert item in new_cart.items
end
```

### E6. Orphaned processes between tests

**Why it's bad:** Next test sees stale state.

```elixir
# BAD
test "worker starts" do
  {:ok, _pid} = MyApp.Worker.start_link([])
  # pid leaks beyond the test
end

# GOOD
test "worker starts" do
  _pid = start_supervised!(MyApp.Worker)
  # ExUnit auto-shuts down after test
end
```

---

## F. Security Anti-Patterns

### F1. SQL injection via `fragment`

**Why it's bad:** Direct string interpolation into SQL.

```elixir
# BAD
from(u in User, where: fragment("name = '#{q}'"))

# GOOD
from(u in User, where: fragment("name = ?", ^q))
# OR stay in Ecto DSL
from(u in User, where: u.name == ^q)
```

### F2. `binary_to_term` without `:safe`

**Why it's bad:** Untrusted binary can allocate unbounded atoms and refs.

```elixir
# BAD
:erlang.binary_to_term(network_input)

# GOOD
:erlang.binary_to_term(network_input, [:safe])
```

### F3. `==` for token comparison (timing attack)

**Why it's bad:** String equality is not constant-time.

```elixir
# BAD
if stored_token == provided_token, do: :ok

# GOOD
if Plug.Crypto.secure_compare(stored_token, provided_token), do: :ok
```

### F4. Logging unredacted secrets

**Why it's bad:** Secrets leak to logs/monitoring.

```elixir
# BAD
Logger.info("User: #{inspect(user)}")   # includes hashed_password, tokens

# GOOD — schema field with redact: true + filter_parameters config
schema "users" do
  field :hashed_password, :string, redact: true
  field :api_key, :string, redact: true
end
```

### F5. Open redirect from user param

**Why it's bad:** Phishing vector — attacker sends login link that redirects to their site.

```elixir
# BAD
def after_login(conn, %{"return_to" => url}) do
  redirect(conn, external: url)
end

# GOOD — validate internal only
def after_login(conn, %{"return_to" => url}) do
  if internal?(url), do: redirect(conn, to: url), else: redirect(conn, to: ~p"/home")
end

defp internal?(url), do: String.starts_with?(url, "/") and not String.starts_with?(url, "//")
```

### F6. Missing TLS peer verification

**Why it's bad:** MITM vulnerability.

```elixir
# BAD
:ssl.connect(host, 443, [verify: :verify_none])

# GOOD
:ssl.connect(host, 443, [
  verify: :verify_peer,
  cacerts: :public_key.cacerts_get(),
  server_name_indication: to_charlist(host),
  customize_hostname_check: [match_fun: :public_key.pkix_verify_hostname_match_fun(:https)]
])
```

(Full security catalog: `./security-audit-deep.md`.)

---

## G. Configuration Anti-Patterns

### G1. `System.get_env` in `config/config.exs`

**Why it's bad:** Compile-time env read; doesn't change at runtime.

```elixir
# BAD — config/config.exs
config :my_app, api_key: System.get_env("API_KEY")

# GOOD — config/runtime.exs
if config_env() == :prod do
  config :my_app,
    api_key: System.fetch_env!("API_KEY")
end
```

### G2. `Application.compile_env` in a library

**Why it's bad:** Compiled-in value means users can't override without recompiling.

```elixir
# BAD — library code
@timeout Application.compile_env(:my_lib, :timeout, 5_000)

# GOOD — accept config through options
def start_link(opts) do
  timeout = Keyword.get(opts, :timeout, 5_000)
  # ...
end
```

### G3. Test config imported into runtime code

**Why it's bad:** Production uses test-only values.

```elixir
# BAD — config/test.exs imported somewhere production reads
import_config "test.exs"   # in runtime.exs

# GOOD — test config is isolated to test.exs only
```

### G4. Hardcoded secrets in source

**Why it's bad:** Secret in VCS = secret on every dev laptop and in history forever.

```elixir
# BAD
@api_key "sk_live_abc123..."

# GOOD
def api_key, do: System.fetch_env!("API_KEY")
```

---

## Cross-References

- **Performance-specific anti-patterns** (with symptom → root cause → fix → evidence): `./performance-catalog.md`
- **Security-specific anti-patterns** (deep checklist): `./security-audit-deep.md`
- **Debugging playbook** (symptom → diagnosis): `./debugging-playbook-deep.md`
- **Review checklists by area** (architecture, control flow, OTP, etc.): `./SKILL.md` §7
- **Why the idiomatic form is better — implementation templates:** `../elixir-implementing/`
