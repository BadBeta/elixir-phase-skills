# Production Patterns — Implementation Reference

Phase-focused on **writing** the code that makes an Elixir app ship-ready for production — and on writing libraries for Hex. Covers concrete patterns from high-traffic Phoenix apps, `NimbleOptions` validation, Mix custom tasks & quality aliases, telemetry wiring, and library-authoring conventions.

**Architectural concerns** (which boundaries to draw, data ownership, distribution) live in `../elixir-planning/`. This file is about the reusable templates that don't belong in any one other subskill.

---

## Rules

1. **ALWAYS use `NimbleOptions.validate!/2`** to validate options in library `start_link/1` and other public APIs that accept keyword lists.
2. **ALWAYS provide a `mix quality` alias** that runs formatter check + Credo + Dialyzer + tests. Wire it into CI.
3. **ALWAYS emit telemetry at public-API boundaries** of a library — `[:library_name, :op, :start | :stop | :exception]` naming.
4. **ALWAYS `@moduledoc false` on internal modules.** Published packages should have a clear public surface.
5. **NEVER call `System.get_env` at compile time** for config the user will set — use `config/runtime.exs`.
6. **ALWAYS check schema/module conventions** before inventing your own — there are community-standard patterns (schema base module, kit modules, policy module) for most concerns.

---

## Production Phoenix Patterns

Patterns extracted from large-scale Phoenix apps (changelog.com, Oban itself, Hex.pm, others). Each one is a **reusable template**, not a general rule — adopt when the pattern fits your need.

| Pattern | Purpose |
|---|---|
| Schema Base Module | Inject common query helpers (`newest_first`, `limit`, `older_than`) into all schemas via `use MyApp.Schema` |
| Kit Modules | Small, focused utility modules (`StringKit`, `ListKit`) instead of one catch-all helper |
| Response Cache Plug | Cache entire HTTP responses for unauthenticated users by request path |
| Policy Module | Authorization with `defoverridable` defaults; role helpers injected into every policy |
| Controller Context Injection | Override `action/2` to inject assigns into every action of a controller |
| HTTP Client with SSL Fallback | Req client with custom retry step for servers that fail default TLS |
| Oban Telemetry Reporter | Capture job failures via `:telemetry` and forward to error tracking |
| Cache with Cascade Deletion | Delete related cache entries when a primary entity changes |
| Soft Delete via Timestamp | Track lifecycle with `unsubscribed_at` instead of hard delete |

### Schema Base Module

Inject query helpers into every schema so contexts can compose queries uniformly.

```elixir
defmodule MyApp.Schema do
  defmacro __using__(opts) do
    sort_field = Keyword.get(opts, :default_sort, :inserted_at)

    quote do
      use Ecto.Schema
      import Ecto.Changeset
      import Ecto.Query

      @sort_field unquote(sort_field)

      def newest_first(query, field \\ @sort_field),
        do: from(q in query, order_by: [desc: field(q, ^field)])

      def older_than(query, %{__struct__: _} = ref, field \\ @sort_field),
        do: from(q in query, where: field(q, ^field) < ^Map.get(ref, field))

      def limit(query, n), do: from(q in query, limit: ^n)
      def with_ids(query, ids), do: from(q in query, where: q.id in ^ids)
      def any?(query), do: MyApp.Repo.exists?(query)

      defoverridable [
        newest_first: 1, newest_first: 2,
        older_than: 2, older_than: 3,
        limit: 2, any?: 1
      ]
    end
  end
end

# Usage — each schema inherits all helpers
defmodule MyApp.Episode do
  use MyApp.Schema, default_sort: :published_at

  schema "episodes" do
    field :title, :string
    field :published_at, :utc_datetime
    timestamps()
  end
end

# Composable queries across schemas
MyApp.Episode
|> MyApp.Episode.newest_first()
|> MyApp.Episode.limit(10)
|> MyApp.Repo.all()
```

### Kit Modules — focused utility modules

Instead of one bloated `MyApp.Helpers`, ship many small **Kit** modules, each under 50 lines and scoped to one data type.

```elixir
defmodule MyApp.StringKit do
  def blank?(nil), do: true
  def blank?(str) when is_binary(str), do: String.trim(str) == ""
  def present?(str), do: not blank?(str)

  def truncate(str, max) when byte_size(str) <= max, do: str
  def truncate(str, max), do: String.slice(str, 0, max - 3) <> "..."

  def dasherize(str) do
    str |> String.downcase() |> String.replace(~r/[^\w]+/, "-")
  end
end

defmodule MyApp.ListKit do
  def compact(list), do: Enum.reject(list, &(&1 in [nil, ""]))
  def compact_join(list, sep \\ " "), do: list |> compact() |> Enum.join(sep)

  def exclude(list, nil), do: list
  def exclude(list, items) when is_list(items), do: Enum.reject(list, &(&1 in items))
  def exclude(list, %{id: id}), do: Enum.reject(list, &(Map.get(&1, :id) == id))
  def exclude(list, item), do: Enum.reject(list, &(&1 == item))

  def overlap?(a, b), do: Enum.any?(a, &(&1 in b))
end

defmodule MyApp.MapKit do
  def sans_blanks(map) do
    map
    |> Enum.reject(fn {_k, v} -> MyApp.StringKit.blank?(v) end)
    |> Map.new()
  end
end
```

**Benefits:** small modules are easier to test, reuse, and `@doc`. Imports are obvious at call site (`MyApp.StringKit.truncate(...)`). Much easier to onboard someone than a 1000-line `Utils` module.

### Response Cache Plug

Cache full HTTP responses for anonymous users. Guards skip caching for authenticated traffic.

```elixir
defmodule MyAppWeb.Plug.ResponseCache do
  import Plug.Conn

  def cached_response(%{assigns: %{current_user: user}} = conn, _) when not is_nil(user),
    do: conn
  def cached_response(conn, _) do
    case MyApp.Cache.get(cache_key(conn)) do
      nil -> conn
      cached -> send_cached(conn, cached) |> halt()
    end
  end

  def cache_public(%{assigns: %{current_user: user}} = conn, _) when not is_nil(user),
    do: conn
  def cache_public(conn, ttl \\ :infinity) do
    register_before_send(conn, fn conn ->
      MyApp.Cache.put(cache_key(conn), %{
        body: conn.resp_body,
        content_type: get_resp_header(conn, "content-type"),
        status: conn.status
      }, ttl)
      conn
    end)
  end

  defp cache_key(conn) do
    qs = if conn.query_string == "", do: "", else: "?#{conn.query_string}"
    "response:#{conn.request_path}#{qs}"
  end

  defp send_cached(conn, %{body: b, content_type: [ct], status: s}),
    do: conn |> put_resp_content_type(ct) |> send_resp(s, b)
end
```

### Policy Module — deny-by-default authorization

```elixir
defmodule MyApp.Policy do
  defmacro __using__(_) do
    quote do
      # Defaults — deny everything
      def new(actor), do: create(actor)
      def create(_actor), do: false
      def index(_actor), do: false
      def show(_actor, _res), do: false
      def edit(actor, res), do: update(actor, res)
      def update(_actor, _res), do: false
      def delete(_actor, _res), do: false

      # Role helpers — available in every policy
      defp is_admin(nil), do: false
      defp is_admin(actor), do: Map.get(actor, :admin, false)
      defp is_editor(nil), do: false
      defp is_editor(actor), do: Map.get(actor, :editor, false)
      defp is_admin_or_editor(a), do: is_admin(a) or is_editor(a)

      defoverridable new: 1, create: 1, index: 1, show: 2, edit: 2, update: 2, delete: 2
    end
  end
end

# Concrete policy — override only what differs from deny-by-default
defmodule MyApp.Policy.Post do
  use MyApp.Policy

  def index(_actor), do: true
  def show(_actor, _post), do: true
  def create(actor), do: is_admin_or_editor(actor)
  def update(actor, post), do: is_admin(actor) or is_owner(actor, post)
  def delete(actor, _post), do: is_admin(actor)

  defp is_owner(nil, _), do: false
  defp is_owner(%{id: id}, %{author_id: aid}), do: id == aid
end
```

### Controller Context Injection

When every action in a controller needs the same parent context (a podcast, a tenant, a project), override `action/2` to inject it once.

```elixir
defmodule MyAppWeb.PodcastEpisodeController do
  use MyAppWeb, :controller

  # Override action/2 — inject podcast (set by earlier plug) as 3rd arg
  def action(conn, _opts) do
    apply(__MODULE__, action_name(conn), [conn, conn.params, conn.assigns.podcast])
  end

  # Every action has signature (conn, params, podcast)
  def index(conn, params, podcast) do
    episodes = Episodes.list_for_podcast(podcast, params)
    render(conn, :index, episodes: episodes)
  end

  def show(conn, %{"slug" => slug}, podcast) do
    episode = Episodes.get_by_podcast_and_slug!(podcast, slug)
    render(conn, :show, episode: episode)
  end
end
```

### HTTP Client with SSL Fallback

Some servers reject TLS with default middlebox compatibility. Retry once with `middlebox_comp_mode: false`.

```elixir
defmodule MyApp.HTTP do
  @doc "Reusable Req client with SSL fallback as a retry step."
  def client(opts \\ []) do
    Req.new(opts)
    |> Req.Request.append_request_steps(ssl_fallback: &ssl_fallback_step/1)
  end

  defp ssl_fallback_step(request) do
    {request, fn {request, response_or_error} ->
      case response_or_error do
        %Req.TransportError{} ->
          opts = [connect_options: [transport_opts: [middlebox_comp_mode: false]]]
          {Req.Request.merge_options(request, opts), response_or_error}
        _ ->
          {request, response_or_error}
      end
    end}
  end
end

# Usage
MyApp.HTTP.client() |> Req.get!(url: "https://finicky.example.com")
```

### Oban Telemetry Error Reporter

```elixir
defmodule MyApp.ObanReporter do
  def attach do
    :telemetry.attach("oban-errors", [:oban, :job, :exception], &handle_event/4, [])
  end

  def handle_event([:oban, :job, _], measure, meta, _) do
    extra =
      meta.job
      |> Map.take([:id, :args, :meta, :queue, :worker, :attempt, :max_attempts])
      |> Map.merge(measure)

    Sentry.capture_exception(meta.reason, stacktrace: meta.stacktrace, extra: extra)
  end

  def handle_event(_event, _measure, _meta, _opts), do: :ok
end

# In application.ex start/2
MyApp.ObanReporter.attach()
```

### Cache with Cascade Deletion

Pattern-match per struct type — deletion of one entity cascades to dependent cache keys.

```elixir
defmodule MyApp.Cache do
  def delete(nil), do: :ok

  def delete(%Episode{} = ep) do
    ep = Repo.preload(ep, :podcast)
    delete_prefix("/#{ep.podcast.slug}/#{ep.slug}")
    delete_prefix("/#{ep.podcast.slug}")     # podcast listing
  end

  def delete(%NewsItem{} = item) do
    item = Repo.preload(item, :object)
    delete_key("response:/news/#{item.slug}")
    delete(item.object)                       # cascade
  end

  def delete(%Post{} = post), do: delete_key("response:/posts/#{post.slug}")

  defp delete_key(k), do: ConCache.delete(:app_cache, k)
  defp delete_prefix(prefix) do
    ConCache.ets(:app_cache)
    |> :ets.tab2list()
    |> Enum.each(fn {key, _} ->
      if String.starts_with?(to_string(key), prefix), do: delete_key(key)
    end)
  end
end
```

### Soft Delete via Timestamp

Track unsubscription as an `unsubscribed_at` timestamp. Re-subscribing clears it, keeping the same row — preserves history and referential integrity.

```elixir
defmodule MyApp.Subscription do
  use Ecto.Schema
  import Ecto.{Changeset, Query}

  schema "subscriptions" do
    belongs_to :user, MyApp.User
    belongs_to :podcast, MyApp.Podcast
    field :unsubscribed_at, :utc_datetime
    field :context, :string
    timestamps()
  end

  def subscribe(%Subscription{unsubscribed_at: nil} = sub, _), do: sub
  def subscribe(%Subscription{} = sub, context) do
    sub
    |> cast(%{unsubscribed_at: nil, context: context}, [:unsubscribed_at, :context])
    |> MyApp.Repo.update!()
  end

  def unsubscribe(%Subscription{} = sub) do
    sub
    |> cast(%{unsubscribed_at: DateTime.utc_now(:second)}, [:unsubscribed_at])
    |> MyApp.Repo.update!()
  end

  def active(query \\ __MODULE__), do: from(s in query, where: is_nil(s.unsubscribed_at))
end
```

---

## NimbleOptions — Options Validation

Standard in the ecosystem (Broadway, Finch, NimblePool, Oban) for validating keyword lists.

### Basic usage

```elixir
defmodule MyServer do
  @options_schema [
    host: [type: :string, required: true, doc: "Hostname to connect to."],
    port: [type: :pos_integer, default: 4000, doc: "Port number."],
    pool_size: [type: :pos_integer, default: 10, doc: "Connections in the pool."],
    transport: [type: {:in, [:tcp, :ssl]}, default: :tcp, doc: "Transport protocol."],
    ssl_opts: [
      type: :keyword_list,
      default: [],
      doc: "Options passed to `:ssl.connect/3`.",
      keys: [
        verify: [type: {:in, [:verify_peer, :verify_none]}, default: :verify_peer],
        cacertfile: [type: :string]
      ]
    ]
  ]

  def start_link(opts) do
    opts = NimbleOptions.validate!(opts, @options_schema)
    GenServer.start_link(__MODULE__, opts)
  end
end
```

### Auto-generated documentation

```elixir
defmodule MyServer do
  @options_schema [...]

  @moduledoc """
  My server.

  ## Options

  #{NimbleOptions.docs(@options_schema)}
  """
end
```

Produces formatted Markdown tables with types, defaults, and docs — zero duplication between code and docs.

### Common types

| Type | Validates |
|---|---|
| `:string` | binary |
| `:atom` | atom |
| `:pos_integer` / `:non_neg_integer` | integer > 0 / ≥ 0 |
| `:boolean` | true/false |
| `{:in, [list]}` | value in list |
| `:keyword_list` | keyword (with optional nested `keys:`) |
| `{:list, inner}` | list of inner type |
| `{:or, [t1, t2]}` | any of given types |
| `{:custom, mod, fun, args}` | custom validator |
| `:mfa` | `{module, fun, args}` tuple |
| `{:fun, arity}` | function of given arity |

### When to use

- Library `start_link/1` and public API entry points.
- Anywhere option typos (`:timout` instead of `:timeout`) have been a problem.
- Complex nested config trees where you want auto-docs.

**Don't use** for internal-only data structures — changeset or pattern-matching suffices.

---

## Mix Custom Tasks & Quality Aliases

### Custom task template

```elixir
defmodule Mix.Tasks.MyApp.Setup do
  use Mix.Task

  @shortdoc "Setup the application — deps, DB, seeds."

  @moduledoc """
  Bootstrap a fresh environment for this app.

  Runs:
  - `mix deps.get`
  - `mix ecto.setup`
  - `mix cmd --app my_app mix assets.setup`
  """

  @impl Mix.Task
  def run(args) do
    Mix.Task.run("deps.get", args)
    Mix.Task.run("ecto.setup", args)
    Mix.shell().info("Setup complete.")
  end
end
```

**Naming:** `Mix.Tasks.Namespace.Task` → `mix namespace.task`. Always include `@shortdoc` (appears in `mix help`) and `@moduledoc` (appears in `mix help namespace.task`).

### Quality alias

A single `mix quality` task that runs the full verification stack. Invoke in CI.

```elixir
# mix.exs
def project do
  [
    # ...
    aliases: aliases(),
    preferred_cli_env: [quality: :test]
  ]
end

defp aliases do
  [
    # Setup after git clone
    setup: ["deps.get", "ecto.setup", "assets.setup", "assets.build"],

    # DB convenience
    "ecto.setup": ["ecto.create", "ecto.migrate", "run priv/repo/seeds.exs"],
    "ecto.reset": ["ecto.drop", "ecto.setup"],

    # The quality gate — what CI runs
    quality: [
      "compile --warnings-as-errors",
      "format --check-formatted",
      "credo --strict",
      "sobelow --skip",
      "deps.audit",
      "dialyzer",
      "test --warnings-as-errors"
    ],

    # Faster local variant (no dialyzer — Dialyzer is slow)
    "quality.fast": [
      "format --check-formatted",
      "credo --strict",
      "test"
    ]
  ]
end
```

**CI invocation:**

```yaml
# .github/workflows/ci.yml
- name: Quality gate
  run: mix quality
```

### Common aliases catalog

| Alias | Contents | When |
|---|---|---|
| `setup` | Bootstrap a fresh checkout | `git clone` + `mix setup` = running app |
| `quality` | All checks CI runs | PR validation |
| `quality.fast` | Quick checks for local pre-commit | `lefthook` / git pre-commit |
| `ecto.reset` | Drop + recreate + migrate + seed | Dev DB in a bad state |
| `start` | Start server (with custom env) | `mix start` vs `mix phx.server` |
| `test.watch` | Watch mode | Via `mix_test_watch` dep |

---

## Library Authoring Patterns

When the thing you're writing will be published to Hex (not just an internal app), these conventions differ.

### `mix.exs` package configuration

```elixir
defmodule MyLib.MixProject do
  use Mix.Project

  @version "0.3.0"
  @source_url "https://github.com/me/my_lib"

  def project do
    [
      app: :my_lib,
      version: @version,
      elixir: "~> 1.17",
      start_permanent: Mix.env() == :prod,
      deps: deps(),
      package: package(),
      docs: docs(),
      description: "One-line description for Hex search."
    ]
  end

  defp package do
    [
      maintainers: ["Your Name"],
      licenses: ["Apache-2.0"],
      links: %{"GitHub" => @source_url, "Changelog" => "#{@source_url}/blob/main/CHANGELOG.md"},
      files: ~w(lib mix.exs README.md LICENSE CHANGELOG.md .formatter.exs)
    ]
  end

  defp docs do
    [
      main: "readme",
      source_ref: "v#{@version}",
      source_url: @source_url,
      extras: ["README.md", "CHANGELOG.md"],
      groups_for_modules: [
        "Core": [MyLib, MyLib.Config],
        "Internal": [~r"MyLib\.Internal\..*"]
      ]
    ]
  end
end
```

**Key points:**
- `@version` + `@source_url` at the top — bump in one place.
- `package.files` — whitelist what ships. Don't ship test/dev files.
- `docs` — `main: "readme"` makes README the landing page on HexDocs.
- Changelog link in `package.links` for the Hex package page.

### Export formatter config

Let users inherit your library's DSL formatting:

```elixir
# .formatter.exs in your library
[
  inputs: ["{mix,.formatter}.exs", "{config,lib,test}/**/*.{ex,exs}"],
  locals_without_parens: [my_dsl: :*, my_setup: 1],
  export: [
    locals_without_parens: [my_dsl: :*, my_setup: 1]
  ]
]
```

Users then add `import_deps: [:my_lib]` to their `.formatter.exs` and your DSL formats correctly.

### `@moduledoc false` on internal modules

Be explicit about public surface:

```elixir
# Public — users call this
defmodule MyLib do
  @moduledoc """
  The primary API. ...
  """
  def do_thing(opts), do: MyLib.Internal.Impl.do_thing(opts)
end

# Internal — hidden from HexDocs, not part of the API
defmodule MyLib.Internal.Impl do
  @moduledoc false
  # Implementation details. May change without notice.
end
```

Rule: if a module's name contains `Internal`, `Impl`, or `Private`, give it `@moduledoc false`.

### Supervisor for libraries — make it opt-in

Libraries should not start processes unless the user explicitly wires them in. Don't be a `mix.exs` `application: [mod: {...}]` that auto-starts.

```elixir
# GOOD — user opts in
defmodule MyLib.Supervisor do
  use Supervisor

  def start_link(opts), do: Supervisor.start_link(__MODULE__, opts, name: __MODULE__)

  @impl true
  def init(opts) do
    children = [{MyLib.ConnectionPool, opts}]
    Supervisor.init(children, strategy: :rest_for_one)
  end
end

# User adds to their app:
children = [{MyLib.Supervisor, pool_size: 10}]
```

### Telemetry convention

Emit events with your library name as the first element; users attach handlers globally.

```elixir
# Wrap operations in telemetry spans
:telemetry.span(
  [:my_lib, :request],
  %{peer_id: peer_id},
  fn ->
    result = do_request(data)
    {result, %{result_class: classify(result)}}
  end
)
```

Document events in your README / HexDocs:

```
## Telemetry events

* `[:my_lib, :request, :start]` — measurements: `%{monotonic_time: int}`
                                   metadata: `%{peer_id: String.t()}`
* `[:my_lib, :request, :stop]`  — measurements: `%{duration: int}`
                                   metadata: `%{peer_id: String.t(), result_class: atom()}`
* `[:my_lib, :request, :exception]` — measurements: `%{duration: int}`
                                      metadata: `%{kind, reason, stacktrace, peer_id}`
```

### Deprecation

```elixir
@deprecated "Use MyLib.do_thing/2 with opts keyword list instead."
def do_thing(a, b, c) do
  do_thing(a, [b: b, c: c])
end
```

The compiler warns callers. Combined with `@moduledoc false` on the replaced module, users get a clear migration path.

### Versioning

Follow semver:
- Major: break a public function signature or remove a function.
- Minor: add a function; add an optional behaviour callback.
- Patch: bug fix; doc change.

**Add `@since "x.y.z"`** to new public functions so HexDocs shows when each was introduced:

```elixir
@doc since: "0.3.0"
def new_function(x), do: ...
```

### CHANGELOG discipline

Keep a `CHANGELOG.md` in Keep-a-Changelog format. Every release has:
- `### Added` — new features.
- `### Changed` — behaviour changes.
- `### Deprecated` — soon-to-be-removed.
- `### Removed` — actually removed.
- `### Fixed` — bug fixes.

Link from `package.links` so Hex shows it.

### NIFs — precompiled via `rustler_precompiled`

If shipping Rust NIFs, use `rustler_precompiled` so users don't need a Rust toolchain:

```elixir
defp deps do
  [
    {:rustler, ">= 0.0.0", optional: true},
    {:rustler_precompiled, "~> 0.8"}
  ]
end

defmodule MyLib.Native do
  use RustlerPrecompiled,
    otp_app: :my_lib,
    crate: "my_lib_native",
    base_url: "https://github.com/me/my_lib/releases/download/v#{Mix.Project.config()[:version]}",
    version: Mix.Project.config()[:version],
    force_build: System.get_env("MY_LIB_BUILD") in ["1", "true"]
end
```

CI builds binaries for Linux/macOS/Windows on each release; `rustler_precompiled` downloads the matching one at `mix deps.compile`.

---

## `Plug.Router` — dispatching to a plug module from a route

`plug(MyPlug)` in a pipeline runs `MyPlug.init([])` at compile time and caches the result, so `call/2` at request time receives already-normalized opts. A `get "/"` route block does **not** do this for you — if you call another plug's `call/2` from a route, you must pass pre-initialized opts yourself.

```elixir
# BAD — bypasses init/1 entirely; today it works only because init/1 is a no-op
get "/" do
  Handlers.Home.call(conn, [])
end
```

```elixir
# GOOD — pre-initialize at compile time, mirroring what `plug()` would do
@home_opts Handlers.Home.init([])
@status_opts Handlers.Status.init([])

get("/", do: Handlers.Home.call(conn, @home_opts))
get("/status", do: Handlers.Status.call(conn, @status_opts))
```

Alternative: if the plug applies to all requests matching a prefix, use `forward/2`:

```elixir
forward("/admin", to: MyApp.AdminRouter)
```

The anti-pattern is latent — nothing breaks until someone changes `init/1` to do option validation or shape normalization, at which point the route silently violates the module's assumptions. Write the `@plug_opts` up front; the cost is two lines and the payoff is that your route dispatches through the same contract the pipeline does.

---

## `config/runtime.exs` — parse env vars explicitly

Raw converters (`String.to_integer/1`, `String.to_atom/1`, `Date.from_iso8601!/1`) raise unattributed `ArgumentError` on malformed input. At boot time, ops sees a stacktrace with no hint about which env var was wrong. Wrap each untrusted input with explicit validation and a legible error message.

```elixir
# BAD — a typo in LOCAL_WEBVIEW_PORT gives a raw stacktrace at boot
port = System.get_env("LOCAL_WEBVIEW_PORT", "4040") |> String.to_integer()
config :local_webview, port: port
```

```elixir
# GOOD — named validation, legible boot-time message
raw = System.get_env("LOCAL_WEBVIEW_PORT", "4040")

port =
  case Integer.parse(raw) do
    {port, ""} when port in 0..65_535 ->
      port

    _ ->
      raise """
      LOCAL_WEBVIEW_PORT must be an integer in 0..65535, got: #{inspect(raw)}.
      Set the environment variable to a valid port number before starting the release.
      """
  end

config :local_webview, port: port
```

The same discipline applies to every conversion at the config boundary: atoms, booleans (`"true"`/`"1"`), URIs, file paths. The error message is what ops reads at 3am — make it actionable.

---

## Plug `halt/1` — the subtle semantics

Deferred to the `phoenix` skill's Plug section — `halted?` is a conn-level flag, not early return. Key thing to remember for implementation: **`halt(conn)` marks the conn as halted but does NOT return from your function.** You must also explicitly return the halted conn.

```elixir
# BAD — halt but continue executing code after
def call(conn, _opts) do
  if no_auth?(conn) do
    send_resp(conn, 401, "") |> halt()
  end
  assign(conn, :authenticated?, true)   # ← still runs even if halted!
end

# GOOD — explicit return
def call(conn, _opts) do
  if no_auth?(conn) do
    conn |> send_resp(401, "") |> halt()
  else
    assign(conn, :authenticated?, true)
  end
end
```

---

## Cross-References

- **Architectural planning** (contexts, data ownership, supervision shape): `../elixir-planning/`
- **Distributed Elixir** (multi-node, `:erpc`, Horde): `../elixir-planning/distributed-elixir.md`
- **Code style** (formatter, Credo, module organization): `./code-style.md`
- **Ecto patterns**: `./ecto-patterns.md`
- **OTP templates** (including Oban workers): `./otp-callbacks.md`
- **Phoenix framework specifics**: the `phoenix` sister skill.
- **Release / deployment**: the `elixir-deployment` sister skill.
