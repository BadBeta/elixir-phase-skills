# Testing Patterns — Implementation Templates

Phase-focused on **writing** tests. Covers ExUnit syntax, Mox API, Ecto sandbox setup, factory code, assertion patterns, LiveView/Channel/Task/GenServer helpers.

**For architectural test concerns** (test pyramid, what to test at which level, mock-boundary principles, CI strategy, property-testing decisions), see `../elixir-planning/test-strategy.md`.

**TDD workflow** (red/green/refactor, writing the test first) lives in the main `SKILL.md` §3.

---

## Rules for Writing Tests

1. **ALWAYS use `async: true`** on test modules. Exception: only when the test touches a shared global (true singletons: `:persistent_term`, unnamed-named processes you can't isolate, `Application.put_env`).
2. **ALWAYS use `describe` blocks** to group tests by the function under test: `describe "register_user/1" do ... end`.
3. **ALWAYS name tests** with the behaviour being asserted, not the call being made: `"rejects duplicate email"`, not `"tests register_user"`.
4. **NEVER set `timeout_ms: :infinity`** on a test — a hung test hangs CI. Use narrower timeouts and `Process.flag(:trap_exit, true)` to debug hang sources.
5. **ALWAYS use `assert_receive` / `refute_receive`** with explicit timeouts when asserting async messages.
6. **NEVER sleep in tests.** `Process.sleep` hides flake; use `assert_receive` or `eventually/1` helper patterns.
7. **ALWAYS use factories for schema fixtures.** Hand-crafted changesets duplicate business logic; one test failure cascades.
8. **NEVER mock what you own.** Mox replaces external behaviour boundaries (HTTP clients, payment gateways), not your own modules. See `../elixir-planning/test-strategy.md` for mock-boundary rules.
9. **ALWAYS set `Mox.verify_on_exit!()`** in `setup` to ensure mocks got called as expected.
10. **ALWAYS use `start_supervised!/1`** inside tests for OTP processes — ExUnit shuts them down at test end automatically. Don't call `GenServer.start_link` directly in tests.
11. **ALWAYS use `Ecto.Adapters.SQL.Sandbox`** for DB tests. Each test runs in a transaction that is rolled back. See `setup_sandbox/1` template below.
12. **NEVER assert on private internals.** Test public behaviour — the observable result of calling the function. If you need to observe internal state to verify correctness, your test may be over-coupled to implementation.

---

## Test Module Template

```elixir
defmodule MyApp.AccountsTest do
  use MyApp.DataCase, async: true

  alias MyApp.Accounts
  alias MyApp.AccountsFixtures

  describe "register_user/1" do
    test "creates user with valid attributes" do
      attrs = AccountsFixtures.valid_user_attributes()

      assert {:ok, user} = Accounts.register_user(attrs)
      assert user.email == attrs.email
      assert user.hashed_password != attrs.password
    end

    test "returns error for duplicate email" do
      %{email: email} = AccountsFixtures.user_fixture()
      attrs = AccountsFixtures.valid_user_attributes(email: email)

      assert {:error, %Ecto.Changeset{} = cs} = Accounts.register_user(attrs)
      assert %{email: ["has already been taken"]} = errors_on(cs)
    end

    test "returns error for invalid email format" do
      attrs = AccountsFixtures.valid_user_attributes(email: "not-an-email")

      assert {:error, cs} = Accounts.register_user(attrs)
      assert %{email: ["has invalid format"]} = errors_on(cs)
    end
  end
end
```

**Conventions:**
- `use MyApp.DataCase` — Ecto sandbox + helpers.
- `async: true` — always, unless globals are touched.
- `describe` — one per function (with arity).
- `AccountsFixtures` — colocated factory module.
- `errors_on/1` — helper that converts changeset errors to a traversable map (standard Phoenix-gen helper).

---

## Ecto Sandbox Setup — `DataCase` Template

```elixir
defmodule MyApp.DataCase do
  use ExUnit.CaseTemplate

  using do
    quote do
      alias MyApp.Repo
      import Ecto
      import Ecto.Changeset
      import Ecto.Query
      import MyApp.DataCase
    end
  end

  setup tags do
    MyApp.DataCase.setup_sandbox(tags)
    :ok
  end

  def setup_sandbox(tags) do
    pid = Ecto.Adapters.SQL.Sandbox.start_owner!(MyApp.Repo, shared: not tags[:async])
    on_exit(fn -> Ecto.Adapters.SQL.Sandbox.stop_owner(pid) end)
  end

  def errors_on(changeset) do
    Ecto.Changeset.traverse_errors(changeset, fn {message, opts} ->
      Regex.replace(~r"%{(\w+)}", message, fn _, key ->
        opts |> Keyword.get(String.to_existing_atom(key), key) |> to_string()
      end)
    end)
  end
end
```

**How it works:**
- Each test checks out a DB connection; all changes within the test are rolled back.
- `async: true` → per-test connection (tests run in parallel safely).
- `async: false` → shared connection (needed when test spawns processes that need access to the same test data).

### Sharing sandbox connection with a spawned process

```elixir
test "worker reads from sandbox" do
  pid = start_supervised!({MyApp.Worker, opts})
  Ecto.Adapters.SQL.Sandbox.allow(MyApp.Repo, self(), pid)
  # ... Worker can now hit the same DB state ...
end
```

### `async: false` for tests that use named globals

```elixir
defmodule MyApp.ConfigTest do
  use ExUnit.Case, async: false  # Modifies Application env — shared global
  # ...
end
```

---

## Factory Template (ExMachina-style, hand-rolled)

Factories colocated with the context:

```elixir
defmodule MyApp.AccountsFixtures do
  alias MyApp.Accounts

  @default_password "super-secret-password-123"

  def unique_email, do: "user-#{System.unique_integer([:positive])}@example.com"

  def valid_user_attributes(overrides \\ %{}) do
    Enum.into(overrides, %{
      email: unique_email(),
      name: "Test User",
      password: @default_password
    })
  end

  def user_fixture(overrides \\ %{}) do
    {:ok, user} = overrides |> valid_user_attributes() |> Accounts.register_user()
    user
  end

  def admin_fixture(overrides \\ %{}) do
    overrides |> Map.put(:role, :admin) |> user_fixture()
  end
end
```

**Rules:**
- **ALWAYS unique-ify fields** with unique-constraint indexes (`System.unique_integer`).
- **ALWAYS go through the context function** (`Accounts.register_user`), never direct `Repo.insert` — tests stay honest to the real API.
- **Factories take overrides**, never positional args — flexible, explicit test setup.

### If using ExMachina

```elixir
defmodule MyApp.Factory do
  use ExMachina.Ecto, repo: MyApp.Repo

  def user_factory do
    %MyApp.Accounts.User{
      email: sequence(:email, &"user#{&1}@example.com"),
      name: "Test User",
      hashed_password: Bcrypt.hash_pwd_salt("password")
    }
  end

  def admin_factory, do: build(:user, role: :admin)
end

# Usage:
insert(:user)
insert(:user, %{email: "known@example.com"})
```

ExMachina bypasses changesets — use only if your data doesn't need validation to be realistic. Otherwise roll your own (above).

---

## Mox — External Boundary Mocking

### Step 1 — define a behaviour at the boundary

```elixir
defmodule MyApp.EmailSender do
  @callback send(to :: String.t(), subject :: String.t(), body :: String.t()) ::
              {:ok, any()} | {:error, term()}
end

defmodule MyApp.EmailSender.Swoosh do
  @behaviour MyApp.EmailSender
  @impl true
  def send(to, subject, body), do: # ... real Swoosh impl ...
end
```

### Step 2 — wire config to select implementation

```elixir
# config/config.exs
config :my_app, :email_sender, MyApp.EmailSender.Swoosh

# config/test.exs
config :my_app, :email_sender, MyApp.EmailSender.Mock
```

### Step 3 — define mock in test_helper.exs

```elixir
# test/test_helper.exs
Mox.defmock(MyApp.EmailSender.Mock, for: MyApp.EmailSender)

ExUnit.start()
```

### Step 4 — use in tests

```elixir
defmodule MyApp.AccountsTest do
  use MyApp.DataCase, async: true
  import Mox

  setup :verify_on_exit!

  test "sends welcome email on registration" do
    user_attrs = AccountsFixtures.valid_user_attributes()

    MyApp.EmailSender.Mock
    |> expect(:send, fn to, subject, _body ->
      assert to == user_attrs.email
      assert subject =~ "Welcome"
      {:ok, :sent}
    end)

    assert {:ok, _user} = Accounts.register_user(user_attrs)
  end
end
```

### Mox API at a glance

| Call | Purpose |
|---|---|
| `expect(mock, :fun, n \\ 1, impl)` | Assert `:fun` is called exactly N times, running `impl` |
| `stub(mock, :fun, impl)` | Allow `:fun` to be called any number of times (including zero) |
| `stub_with(mock, real_module)` | Delegate every call to `real_module` (for partial mocking) |
| `verify_on_exit!()` | Fail test if expected calls didn't happen |
| `allow(mock, parent_pid, child_pid)` | Let another process use the mock (Mox private mode) |

### Mox modes

```elixir
# Private mode (default, per-test, async-safe)
:ok = Mox.set_mox_private()

# Global mode (shared across processes; use sparingly, requires async: false)
:ok = Mox.set_mox_global()
```

**Default is private mode.** Use global mode only when you can't thread PIDs (e.g., background process you don't own). Global mode forces `async: false`.

### `allow/3` — propagating mock permission to spawned processes

```elixir
test "background worker uses mock" do
  parent = self()

  MyApp.EmailSender.Mock
  |> expect(:send, fn _, _, _ -> {:ok, :sent} end)

  {:ok, worker} = start_supervised(MyApp.Worker)
  Mox.allow(MyApp.EmailSender.Mock, parent, worker)

  MyApp.Worker.trigger(worker)
  verify!(MyApp.EmailSender.Mock)
end
```

---

## Async Message Assertions

```elixir
# Wait for a specific message (default timeout 100ms — raise to match intent)
assert_receive {:done, result}, 1_000

# Use guards and binds
assert_receive {:event, %{type: type, payload: payload}}, 500
assert type == :completed

# Refute — no such message arrives within the timeout
refute_receive {:error, _}, 200

# Flush all pending messages for debugging (REPL only; don't use in tests)
```

### Pattern: sending self() a message from a mock

```elixir
test "controller dispatches email async" do
  parent = self()

  MyApp.EmailSender.Mock
  |> expect(:send, fn to, _, _ ->
    send(parent, {:email_sent, to})
    {:ok, :sent}
  end)

  Accounts.register_user(attrs)

  assert_receive {:email_sent, ^expected_to}, 1_000
end
```

---

## OTP Process Testing

### Always use `start_supervised!`

```elixir
test "counter increments" do
  pid = start_supervised!({MyApp.Counter, limit: 10})
  assert :ok = MyApp.Counter.increment(pid)
  assert MyApp.Counter.value(pid) == 1
end
```

**Why `start_supervised!`:**
- ExUnit manages shutdown — no zombie processes between tests.
- Uses a dedicated supervisor per-test — can run `async: true`.
- `!` variant raises if start fails, surfacing misconfigurations early.

### Testing a GenServer's state

```elixir
test "caches result after first call" do
  pid = start_supervised!({MyApp.Cache, []})

  MyApp.HTTPMock
  |> expect(:get, 1, fn _url -> {:ok, "result"} end)  # called ONCE only

  assert {:ok, "result"} = MyApp.Cache.fetch(pid, "key")
  assert {:ok, "result"} = MyApp.Cache.fetch(pid, "key")  # second call: cached
end
```

### Testing state directly via `:sys.get_state`

```elixir
test "worker holds registered names" do
  pid = start_supervised!({MyApp.Worker, []})
  MyApp.Worker.register(pid, "alice")

  state = :sys.get_state(pid)
  assert "alice" in state.names
end
```

**Use sparingly.** Prefer asserting via public API; use `:sys.get_state` for debugging or when the observable behaviour is itself "later reads should see this state."

### Testing crash/restart behavior

```elixir
test "supervisor restarts worker on crash" do
  {:ok, sup} = start_supervised(MyApp.Supervisor)
  [{_, worker_pid, _, _}] = Supervisor.which_children(sup)

  Process.exit(worker_pid, :kill)

  # Wait for restart
  Process.sleep(50)  # Unavoidable here — use a briefer sleep or poll
  [{_, new_pid, _, _}] = Supervisor.which_children(sup)
  assert new_pid != worker_pid
end
```

### Trap exits to observe process deaths

```elixir
test "worker exits cleanly on stop" do
  Process.flag(:trap_exit, true)
  pid = start_supervised!({MyApp.Worker, []})
  MyApp.Worker.stop(pid)
  assert_receive {:EXIT, ^pid, :normal}, 1_000
end
```

---

## Phoenix Controller Tests

```elixir
defmodule MyAppWeb.UserControllerTest do
  use MyAppWeb.ConnCase, async: true

  alias MyApp.AccountsFixtures

  describe "GET /users/:id" do
    test "shows user", %{conn: conn} do
      user = AccountsFixtures.user_fixture()

      conn = get(conn, ~p"/users/#{user.id}")

      assert html_response(conn, 200) =~ user.name
    end

    test "404 for missing user", %{conn: conn} do
      assert_error_sent :not_found, fn ->
        get(conn, ~p"/users/0")
      end
    end
  end

  describe "POST /users" do
    test "creates user with valid params", %{conn: conn} do
      attrs = AccountsFixtures.valid_user_attributes()

      conn = post(conn, ~p"/users", user: attrs)

      assert redirected_to(conn) =~ ~r"/users/\d+"
    end

    test "renders errors for invalid params", %{conn: conn} do
      conn = post(conn, ~p"/users", user: %{email: ""})

      assert html_response(conn, 200) =~ "can&#39;t be blank"
    end
  end
end
```

### ConnCase extras

```elixir
# Authenticated conn
conn = log_in_user(conn, user)

# JSON
conn = post(conn, ~p"/api/users", user: attrs)
assert json_response(conn, 201) == %{"id" => _, "email" => _}

# Headers
conn = put_req_header(conn, "authorization", "Bearer #{token}")
```

---

## LiveView Tests

```elixir
defmodule MyAppWeb.DashboardLiveTest do
  use MyAppWeb.ConnCase, async: true
  import Phoenix.LiveViewTest

  test "mount shows user", %{conn: conn} do
    user = user_fixture()
    conn = log_in_user(conn, user)

    {:ok, view, html} = live(conn, ~p"/dashboard")

    assert html =~ user.name
    assert has_element?(view, "#user-panel")
  end

  test "clicking button updates state", %{conn: conn} do
    user = user_fixture()
    conn = log_in_user(conn, user)
    {:ok, view, _} = live(conn, ~p"/dashboard")

    view |> element("#increment") |> render_click()

    assert render(view) =~ "Count: 1"
  end

  test "submitting form validates", %{conn: conn} do
    conn = log_in_user(conn, user_fixture())
    {:ok, view, _} = live(conn, ~p"/dashboard")

    view
    |> form("#new-post", post: %{title: ""})
    |> render_submit()

    assert render(view) =~ "can&#39;t be blank"
  end
end
```

### LiveView assertion helpers

| Call | Purpose |
|---|---|
| `live(conn, path)` | Mount LiveView, return `{:ok, view, html}` |
| `element(view, selector)` | Bind to an element for click/submit/etc. |
| `render(view)` | Current HTML |
| `has_element?(view, selector, text?)` | Element exists (optionally containing text) |
| `form(view, selector, params)` | Bind to a form for validation/submit |
| `render_click(element)` | Fire `phx-click` |
| `render_submit(form)` | Fire `phx-submit` |
| `render_change(form, changes)` | Fire `phx-change` |
| `render_hook(view, event, payload)` | Fire custom JS hook |
| `follow_trigger_action(form)` | Follow a form's action after phx-trigger-action |
| `send(view.pid, msg)` | Send message to LiveView process |

---

## Channel Tests

```elixir
defmodule MyAppWeb.RoomChannelTest do
  use MyAppWeb.ChannelCase, async: true

  setup do
    {:ok, _, socket} =
      MyAppWeb.UserSocket
      |> socket("user_id", %{user_id: 42})
      |> subscribe_and_join(MyAppWeb.RoomChannel, "room:lobby")

    %{socket: socket}
  end

  test "broadcasts a message", %{socket: socket} do
    push(socket, "new:msg", %{body: "hello"})

    assert_broadcast "new:msg", %{body: "hello"}
  end

  test "replies with ack on ping", %{socket: socket} do
    ref = push(socket, "ping", %{})
    assert_reply ref, :ok, %{pong: true}
  end
end
```

### Channel assertion helpers

| Call | Purpose |
|---|---|
| `push(socket, event, payload)` | Simulate client `:push`, returns ref |
| `assert_push event, payload` | Server pushed to THIS socket |
| `assert_broadcast event, payload` | Broadcast to channel |
| `assert_reply ref, status, payload` | Reply to a pushed message |
| `close(socket)` | Simulate socket close |

---

## Oban Job Tests

```elixir
defmodule MyApp.SendWelcomeEmailJobTest do
  use MyApp.DataCase, async: true
  use Oban.Testing, repo: MyApp.Repo

  alias MyApp.Workers.SendWelcomeEmail

  describe "perform/1" do
    test "sends welcome to user" do
      user = user_fixture()

      MyApp.EmailSender.Mock
      |> expect(:send, fn to, _, _ -> {:ok, to} end)

      assert :ok = perform_job(SendWelcomeEmail, %{user_id: user.id})
    end

    test "handles missing user" do
      assert {:error, :not_found} = perform_job(SendWelcomeEmail, %{user_id: 0})
    end
  end

  test "enqueues on user creation" do
    user = user_fixture()
    assert_enqueued worker: SendWelcomeEmail, args: %{user_id: user.id}
  end

  test "inline mode runs synchronously" do
    with_testing_mode(:inline, fn ->
      user = user_fixture()
      # After user_fixture runs its job scheduling, worker has already run
      assert_has_side_effect(user)
    end)
  end
end
```

**Oban testing modes:**
- `:manual` (default) — jobs enqueued but not run; use `perform_job/2` + `assert_enqueued/1` to assert.
- `:inline` — jobs run synchronously as they're enqueued; useful for end-to-end tests.

---

## Assertions — Idiomatic Patterns

### Pattern match in assertions

```elixir
assert {:ok, user} = Accounts.register_user(attrs)
assert %User{email: ^expected_email, role: :user} = user
```

### Assertions with pin operator

```elixir
expected = "alice"
assert %{name: ^expected} = result
```

### Struct-specific

```elixir
assert %Ecto.Changeset{valid?: false} = cs
assert [%User{}, %User{}] = Accounts.list_users()
```

### `assert_raise`

```elixir
assert_raise ArgumentError, ~r/invalid email/, fn ->
  Accounts.register_user!(%{email: nil})
end

assert_raise Ecto.NoResultsError, fn ->
  Accounts.get_user!(0)
end
```

### Errors on changesets

```elixir
assert {:error, cs} = Accounts.register_user(attrs)
assert %{email: ["has already been taken"]} = errors_on(cs)
assert %{password: [msg]} = errors_on(cs)
assert msg =~ "at least 12 characters"
```

### Numeric and string assertions

```elixir
assert value in 1..10
assert String.contains?(result, "expected-substring")
assert Regex.match?(~r/\d{4}-\d{2}-\d{2}/, date_str)
assert_in_delta actual, expected, 0.01
```

### Custom assertion helpers

```elixir
defmodule MyApp.TestHelpers do
  import ExUnit.Assertions

  def assert_eventually(fun, timeout \\ 1_000, interval \\ 10) do
    deadline = System.monotonic_time(:millisecond) + timeout
    do_assert_eventually(fun, deadline, interval)
  end

  defp do_assert_eventually(fun, deadline, interval) do
    case fun.() do
      true -> true
      _ ->
        if System.monotonic_time(:millisecond) > deadline do
          flunk("Condition never became true within timeout")
        else
          Process.sleep(interval)
          do_assert_eventually(fun, deadline, interval)
        end
    end
  end
end
```

---

## Property-Based Tests (StreamData)

```elixir
defmodule MyApp.StringUtilsTest do
  use ExUnit.Case, async: true
  use ExUnitProperties

  property "reverse/1 is its own inverse" do
    check all string <- string(:printable) do
      assert string == string |> String.reverse() |> String.reverse()
    end
  end

  property "split then join equals identity" do
    check all string <- string(:ascii), separator <- member_of([",", ";", "|"]),
              not String.contains?(string, separator) do
      assert string == string |> String.split(separator) |> Enum.join(separator)
    end
  end
end
```

**Generators:**
- `string(:printable | :ascii | :alphanumeric)`
- `integer(1..100)`
- `member_of([:a, :b, :c])`
- `list_of(integer())`
- `map_of(atom(:alphanumeric), integer())`
- `tuple({integer(), string(:ascii)})`
- `constant(value)`
- `one_of([gen_a, gen_b])`
- `filter(gen, fun)` / `bind(gen, fun)` for dependencies

**When to use properties:** for invariants (roundtrip, idempotence, commutativity), parsers, serializers, state machines.
**When NOT to use:** for business rules specific to example inputs — example-based tests communicate intent better there.

See `../elixir-planning/test-strategy.md` for the choice.

---

## Parametrized Tests (Elixir 1.18+)

Run the same test body with multiple parameter sets without copy-paste. `parameterize/1` is evaluated at compile time.

```elixir
defmodule MyApp.ParserTest do
  use ExUnit.Case, async: true

  describe "parse/1" do
    parameterize([
      %{input: "42", expected: {:ok, 42}},
      %{input: "0", expected: {:ok, 0}},
      %{input: "-1", expected: {:ok, -1}},
      %{input: "abc", expected: {:error, :invalid}},
      %{input: "", expected: {:error, :empty}}
    ])

    test "parses input", %{input: input, expected: expected} do
      assert MyApp.Parser.parse(input) == expected
    end
  end
end
```

ExUnit runs one test per parameter row, with a descriptive name derived from the parameters.

**Alternative (pre-1.18):**

```elixir
# Works in any Elixir version — uses for-comprehension to generate tests
for {input, expected} <- [
      {"42", {:ok, 42}},
      {"abc", {:error, :invalid}}
    ] do
  @tag input: input, expected: expected
  test "parses #{input}", %{input: input, expected: expected} do
    assert MyApp.Parser.parse(input) == expected
  end
end
```

Use parametrized tests for:
- Boundary/edge-case tables.
- Cross-provider tests (same behaviour, different backends).
- Cross-locale / cross-region tests.

---

## ExVCR — Recording & Replaying HTTP

Use when you MUST hit a real external API at least once (integration test) but want reproducible test runs after.

```elixir
# test/test_helper.exs
ExUnit.start()
HTTPoison.start()

# In a test
defmodule MyApp.GitHubTest do
  use ExUnit.Case, async: false   # ExVCR uses a global cassette file
  use ExVCR.Mock, adapter: ExVCR.Adapter.Hackney

  setup do
    ExVCR.Config.cassette_library_dir("test/fixtures/cassettes")
    :ok
  end

  test "fetches repo stars" do
    use_cassette "github_stars" do
      assert {:ok, %{stars: n}} = MyApp.GitHub.get_stars("elixir-lang/elixir")
      assert n > 0
    end
  end
end
```

**Workflow:**
1. First run — ExVCR records the HTTP exchange to `test/fixtures/cassettes/github_stars.json`.
2. Subsequent runs — ExVCR replays from the cassette; no network.
3. Commit cassettes to git so CI is reproducible.

**When to re-record:** when the API changes or you want fresh data. Delete the cassette file and re-run. Store as fixture data; review changes in PR.

**Redacting secrets in cassettes:**

```elixir
ExVCR.Config.filter_request_headers(["Authorization"])
ExVCR.Config.filter_sensitive_data("token=[A-Z0-9]+", "token=***")
```

**When NOT to use:** for your own code's HTTP boundary (use Mox on a behaviour — see §Mox above). ExVCR is for when you want to actually verify the integration works end-to-end.

---

## Wallaby — Browser / End-to-End Tests

Use when you need to verify JavaScript-dependent flows, full-stack interactions, or accessibility. Wallaby drives a real (headless) Chrome via Selenium.

### Setup

```elixir
# mix.exs
{:wallaby, "~> 0.30", runtime: false, only: :test}

# test/test_helper.exs
{:ok, _} = Application.ensure_all_started(:wallaby)

# config/test.exs
config :my_app, MyAppWeb.Endpoint,
  http: [port: 4002],
  server: true                    # must run the server during tests

config :wallaby,
  otp_app: :my_app,
  chromedriver: [headless: true]

# test/support/feature_case.ex
defmodule MyAppWeb.FeatureCase do
  use ExUnit.CaseTemplate

  using do
    quote do
      use Wallaby.Feature
      import Wallaby.Query
      alias MyApp.{AccountsFixtures}
    end
  end

  setup tags do
    pid = Ecto.Adapters.SQL.Sandbox.start_owner!(MyApp.Repo, shared: not tags[:async])
    on_exit(fn -> Ecto.Adapters.SQL.Sandbox.stop_owner(pid) end)
    :ok
  end
end
```

### A feature test

```elixir
defmodule MyAppWeb.LoginFeatureTest do
  use MyAppWeb.FeatureCase, async: true

  feature "user logs in and sees dashboard", %{session: session} do
    user = AccountsFixtures.user_fixture(%{email: "alice@example.com"})

    session
    |> visit("/login")
    |> fill_in(text_field("Email"), with: user.email)
    |> fill_in(text_field("Password"), with: "super-secret")
    |> click(button("Log in"))
    |> assert_has(css(".flash-info", text: "Welcome back"))
    |> assert_has(css("[data-test='dashboard']"))
  end
end
```

**Key query functions:**
- `css(selector)` — CSS selector, optionally with `text:` constraint
- `text_field("Email")` — locate input by label
- `button("Log in")` — locate button by label
- `link("Profile")` — locate link by text

**Actions:** `visit`, `click`, `fill_in`, `clear`, `execute_script`, `take_screenshot`.

**Assertions:** `assert_has`, `refute_has`, `assert_text`, `has?`.

### When to use Wallaby

| Scenario | Wallaby? |
|---|---|
| Happy-path user journey | Yes — one feature per key flow |
| Javascript interaction (Alpine, Stimulus, custom JS) | Yes |
| LiveView specific behaviour | Prefer `Phoenix.LiveViewTest` (faster, no browser) |
| Visual regression | No — separate tool (Percy, Chromatic) |
| Every form field validation | No — controller/LiveView tests (faster) |

**Keep feature tests to a small number** (5–20 for a typical app). Each one is expensive; they're for catching integration regressions, not exhaustive validation.

### Screenshots on failure

```elixir
# test/test_helper.exs
Wallaby.screenshot_on_failure()
```

Screenshots land in `screenshots/` — useful for CI artifact upload.

---

## Common Anti-Patterns (BAD / GOOD)

### 1. `Process.sleep` waiting for async work

```elixir
# BAD — flaky on slow CI, slow on fast CI
test "worker processed" do
  MyApp.Worker.trigger(pid)
  Process.sleep(500)
  assert MyApp.State.get() == :done
end
```

```elixir
# GOOD — message-driven, deterministic
test "worker processed" do
  :telemetry.attach("test", [:worker, :done], fn _, _, _, _ -> send(self(), :done) end, nil)
  MyApp.Worker.trigger(pid)
  assert_receive :done, 1_000
end
```

### 2. Hand-crafted schema structs in tests

```elixir
# BAD — duplicates changeset logic, rots fast
setup do
  {:ok, user} = Repo.insert(%User{email: "x@y.com", hashed_password: "fake"})
  %{user: user}
end
```

```elixir
# GOOD — factory going through the real context
setup do
  %{user: AccountsFixtures.user_fixture()}
end
```

### 3. Testing the implementation, not the behaviour

```elixir
# BAD — coupled to internal state, breaks on refactor
test "add_item calls Logger.info" do
  assert_called Logger.info(:_) do
    Cart.add_item(cart, item)
  end
end
```

```elixir
# GOOD — tests observable outcome
test "add_item returns updated cart with the item" do
  new_cart = Cart.add_item(cart, item)
  assert item in new_cart.items
end
```

### 4. Mocking what you own

```elixir
# BAD — mocks the MyApp.UserRepo (your own module); now nothing tests its actual behaviour
expect(MyApp.UserRepoMock, :get, fn _ -> %User{} end)
Accounts.register_user(attrs)
```

```elixir
# GOOD — use the real Repo through the sandbox; mock the external boundary only
user = AccountsFixtures.user_fixture()
MyApp.EmailSender.Mock |> expect(:send, fn _, _, _ -> {:ok, :sent} end)
Accounts.register_user(valid_user_attributes(email: user.email))
```

### 5. `async: false` without a stated global

```elixir
# BAD — slower CI with no reason
defmodule MyTest do
  use ExUnit.Case, async: false
  test "pure function" do
    assert MyMath.add(1, 2) == 3
  end
end
```

```elixir
# GOOD
defmodule MyTest do
  use ExUnit.Case, async: true
  test "pure function" do
    assert MyMath.add(1, 2) == 3
  end
end
```

### 6. Global mock mode when private would work

```elixir
# BAD — forces async: false needlessly
setup :set_mox_global

test "uses mock" do
  expect(MyMock, :call, fn -> :ok end)
  MyApp.do_thing()
end
```

```elixir
# GOOD — private mode (default), still async
setup :verify_on_exit!

test "uses mock" do
  expect(MyMock, :call, fn -> :ok end)
  MyApp.do_thing()
end
```

### 7. Not cleaning up test processes

```elixir
# BAD — orphaned process; next test may see stale state
test "worker starts" do
  {:ok, pid} = MyApp.Worker.start_link([])
  # pid lives beyond this test if not explicitly stopped
end
```

```elixir
# GOOD
test "worker starts" do
  pid = start_supervised!(MyApp.Worker)
  # ExUnit auto-shuts down after test
end
```

---

## Cross-References

- **Test strategy / pyramid / what-to-test:** `../elixir-planning/test-strategy.md`
- **Mock-boundary decisions (what to mock):** `../elixir-planning/test-strategy.md#mocking-boundaries`
- **Stdlib testing reference:** `../elixir/testing-reference.md` + `../elixir/testing-examples.md`
- **Ecto-specific patterns (sandbox, factories):** `./ecto-patterns.md`
- **LiveView/Channel patterns (writing the code under test):** `./otp-callbacks.md`
- **Reviewing test code for quality:** `../elixir-reviewing/SKILL.md`
