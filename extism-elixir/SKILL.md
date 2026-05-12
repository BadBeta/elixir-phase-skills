---
name: extism-elixir
description: >
  Extism host SDK for Elixir — running WebAssembly plugins from Elixir
  applications. Covers manifest shapes, Plugin.new/call/free lifecycle,
  WASI mode, GenServer/DynamicSupervisor wrapping, error mapping,
  Phoenix integration, testing seams, and the v1.0 API. ALWAYS use when
  writing or reviewing Elixir code that loads `.wasm` plugins via the
  `extism` hex package. ALWAYS use when designing supervision for
  long-lived plugin processes. ALWAYS use when wiring Extism into
  Phoenix LiveView or background workers. For plugin authoring in Rust,
  see the `rust-wasm` skill's `rust_wasm_extism.md` subskill.
---

# Extism — Elixir Host SDK

WebAssembly plugin host integration for Elixir. The `extism` hex
package (currently v1.0.0) wraps the Extism runtime so an Elixir
application can load `.wasm` modules, call exported functions, and
exchange data — typically JSON-encoded — across the WASM boundary.

> **Verified against:** `extism` v1.0.0 (hex), `extism/elixir-sdk` main.
> If `Extism.Plugin.new/2` signatures look different in a later release,
> trust the docs and flag the drift.

> **Pre-v1.0 examples are STALE.** Many tutorials and demos on the web —
> including Extism's own blog post on the Fly.io game system and the
> [`extism/game_box`](https://github.com/extism/game_box) reference repo
> (still on the pre-v1.0 API at the time of writing) — use
> `Extism.Context.new()` + `Extism.Context.new_plugin/3`. **v1.0 removed
> `Extism.Context`.** The current API is `Extism.Plugin.new(manifest, wasi)`
> directly — no context object to thread. When porting old examples,
> drop the context, replace `Context.new_plugin(ctx, m, wasi)` with
> `Plugin.new(m, wasi)`, and remove any `Context.free/1` calls (Plugin
> resources are managed individually now).

> **Different from `rust-nif`:** Rustler embeds native Rust code directly
> in the BEAM (one address space, scheduler-aware). Extism loads sandboxed
> WASM modules (separate memory, no scheduler integration, language-agnostic
> plugins). They solve different problems — see "Extism vs Rustler" below.

## Rules for Writing Extism Elixir Code (LLM)

1. **ALWAYS run `mix deps.get` with a working Rust toolchain installed** —
   the `extism` package compiles a native NIF on `mix compile`. Without
   `rustup` / `cargo` on PATH the dep fails. CI images that lack Rust
   need an explicit install step.
2. **ALWAYS pattern-match `Extism.Plugin.new/2`** — it returns
   `{:ok, plugin}` on success and `{:error, reason}` on a bad manifest,
   missing WASM, or runtime failure. The bang form is not in the SDK.
3. **NEVER create a plugin per request / per render / per LiveView mount.**
   Plugin instantiation parses + JIT-compiles the WASM module — it's
   slow (tens to hundreds of ms) and memory-heavy. Create once at
   application start (or in a `start_async` for slow modules), hold
   the reference in a process or named registry, reuse.
4. **ALWAYS call `Extism.Plugin.free/1` when a plugin is no longer
   needed** — particularly when reloading after the WASM file changes.
   Memory used by the plugin is freed only when `free/1` runs (or the
   owning process dies and GC sweeps the resource).
5. **NEVER call functions on a plugin after `free/1`** — the SDK raises
   on subsequent calls. If you reload, replace the held reference;
   otherwise the next caller crashes.
6. **ALWAYS use `Extism.Plugin.has_function/2`** when calling a
   plugin loaded at runtime (user-supplied `.wasm`). An unknown
   function name returns `{:error, _}` from `call/3`, but
   `has_function` lets you fail fast at registration time.
7. **NEVER pass non-string input to `Plugin.call/3`** — the SDK
   accepts a binary as input. For structured data, `Jason.encode!/1`
   on the Elixir side and `Json<T>` on the plugin side is the
   convention. Pass raw binary for bytes (e.g., a PDF upload).
8. **ALWAYS treat the output of `Plugin.call/3` as `{:ok, binary}`** —
   never `{:ok, %{...}}`. The binary is whatever the plugin wrote to
   its output (typically JSON-encoded). Decode in the caller.
9. **NEVER use host functions in the Elixir SDK as of v1.0** — they
   are not yet supported. Plugins that import host functions will fail
   to load. If you need host callbacks, use a polling pattern (plugin
   returns a "needs more data" tag; host re-invokes with new input)
   or wait for SDK support.
10. **ALWAYS pass `wasi: true` (second arg) when the plugin needs
    WASI** — file I/O, environment vars, time. The default `false`
    runs in `wasm32-unknown-unknown` mode and any WASI import call
    crashes the plugin. Match the plugin's build target.
11. **PREFER GenServer-per-plugin** for long-lived plugins where one
    Elixir process owns one plugin's lifecycle. The Erlang resource
    `Extism.Plugin` is not process-bound, but lifecycle management
    is clearest when one process owns one resource. See §"GenServer
    wrapping" below.
12. **ALWAYS supervise plugin processes.** A plugin holding non-trivial
    state (a parsed config, a database of in-memory rules) is
    expensive to rebuild — supervisor restart with the same manifest
    is the recovery path. `transient` restart strategy is the right
    default: a plugin crash gets one restart, then escalates.
13. **NEVER set the plugin manifest's `wasm.url` to a URL fetched at
    plugin-creation time in production** without a fallback. Network
    outages during `Plugin.new` will fail the start. Vendor plugins
    by copying the `.wasm` file into `priv/` and referencing it by
    `path`, or pre-fetch + cache to disk in a Mix release build step.
14. **ALWAYS propagate `Logger.metadata` across plugin calls in async
    contexts** (Task.async, Oban worker). The plugin call is
    synchronous within the calling process, but if you wrap it in a
    Task or it lives in a worker, the caller's request_id / trace_id
    must be set in the worker too. See elixir-implementing §5.13.

## Decision Tables

### When to use Extism

| Situation | Use Extism? | Alternative |
|---|---|---|
| User-supplied plugin logic (extensibility) | **Yes** — WASM sandbox is the point | Lua / Erlang plugins lose sandbox safety |
| Polyglot extensions (Rust + JS + Go in one app) | **Yes** — Extism PDKs exist for many languages | One language → use a NIF or pure Elixir |
| Performance-critical inner loop, trusted code | **No** — Rustler NIF beats Extism (no WASM overhead) | `rust-nif` skill |
| Long-running compute that may hang | **Maybe** — Extism has timeouts; NIFs need dirty schedulers | NIF with dirty scheduler is faster but riskier |
| Code generation / template rendering | **Yes** if templates are user-supplied | NimbleParsec / EEx for trusted templates |
| Single deploy, one team, no extension surface | **No** — Extism adds a layer for no isolation benefit | Plain Elixir module |

### Manifest source — which to use

| You have… | Use this | Why |
|---|---|---|
| `.wasm` vendored into `priv/` | `%{wasm: [%{path: "priv/plugins/x.wasm"}]}` | Survives offline deploys; included in Mix release |
| Plugin distributed via GitHub releases | Fetch at build time via a Mix task → drop in `priv/` | Don't fetch at boot — outages = startup failure |
| Plugin bytes already in memory (e.g., from a DB) | `%{wasm: [%{data: bytes}]}` | One round-trip, no FS write |
| Plugin URL that's stable + cacheable | `%{wasm: [%{url: url}]}` + retry/fallback | OK for dev, risky for prod without fallback |

### Process placement

| Workload | Process shape | Restart |
|---|---|---|
| One plugin shared by all callers | Named GenServer | `:transient` |
| One plugin per tenant / per session | DynamicSupervisor + Registry | `:transient` |
| Many short-lived calls, plugin is cheap to load | `Task.Supervisor` + create-and-discard | `:temporary` |
| Plugin reload on file change (dev) | GenServer with `{:reload, manifest}` handle_call | `:transient` |

## Installation

```elixir
# mix.exs
def deps do
  [{:extism, "~> 1.0"}]
end
```

Prerequisite: a working Rust toolchain on PATH (`rustup` / `cargo`). The
`extism` package compiles the host runtime as a NIF when the dep
compiles. Both your dev machine and any CI runner / Docker build
stage need Rust available.

```dockerfile
# Dockerfile excerpt for a release image that needs Extism
FROM hexpm/elixir:1.18.4-erlang-27.2-debian-bookworm-20250113-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
      sh -s -- -y --profile minimal && \
    rm -rf /var/lib/apt/lists/*
ENV PATH="/root/.cargo/bin:${PATH}"
```

The runtime image doesn't need Rust — the compiled NIF (`.so`) ships
inside the release. Only the build stage needs the toolchain.

## Public API Cheat Sheet

| Function | Signature | Returns |
|---|---|---|
| `Extism.Plugin.new/2` | `(manifest :: map, wasi :: boolean)` | `{:ok, plugin} \| {:error, term}` |
| `Extism.Plugin.call/3` | `(plugin, name :: String.t, input :: binary)` | `{:ok, output :: binary} \| {:error, term}` |
| `Extism.Plugin.free/1` | `(plugin)` | `:ok` (idempotent; subsequent calls raise) |
| `Extism.Plugin.has_function/2` | `(plugin, name :: String.t)` | `boolean` |
| `Extism.set_log_file/2` | `(filepath, level)` | `:ok` — host runtime logs |

**Not supported in v1.0:** host functions (Elixir-side callbacks the
plugin imports), `cancel/1` (in-flight call cancellation), `reset/1`
(reset plugin state without freeing). Track issues on
[extism/elixir-sdk](https://github.com/extism/elixir-sdk/issues).

## Patterns

### Single shared plugin — named GenServer

For one plugin reused across the application. The GenServer owns the
plugin resource; callers send requests through the named API.

```elixir
defmodule MyApp.VowelCounter do
  @moduledoc """
  Wraps the count_vowels.wasm plugin. Single instance per node.
  """
  use GenServer
  require Logger

  @manifest %{wasm: [%{path: "priv/plugins/count_vowels.wasm"}]}

  def start_link(opts) do
    GenServer.start_link(__MODULE__, :ok, name: opts[:name] || __MODULE__)
  end

  # Client API — callers never touch the plugin reference directly.
  @spec count(String.t()) :: {:ok, map()} | {:error, term()}
  def count(text), do: GenServer.call(__MODULE__, {:count, text})

  @impl true
  def init(:ok) do
    # Move plugin load to handle_continue/2 so init/1 returns fast and
    # doesn't block the supervisor's start sequence. WASM compile is slow.
    {:ok, %{plugin: nil}, {:continue, :load}}
  end

  @impl true
  def handle_continue(:load, state) do
    case Extism.Plugin.new(@manifest, false) do
      {:ok, plugin} -> {:noreply, %{state | plugin: plugin}}
      {:error, reason} -> {:stop, {:plugin_load_failed, reason}, state}
    end
  end

  @impl true
  def handle_call({:count, text}, _from, %{plugin: plugin} = state) when not is_nil(plugin) do
    reply =
      with {:ok, json} <- Extism.Plugin.call(plugin, "count_vowels", text),
           {:ok, decoded} <- Jason.decode(json) do
        {:ok, decoded}
      end

    {:reply, reply, state}
  end

  @impl true
  def terminate(_reason, %{plugin: plugin}) when not is_nil(plugin) do
    Extism.Plugin.free(plugin)
    :ok
  end
end
```

In your application supervisor:

```elixir
def start(_type, _args) do
  children = [
    # ... other children ...
    {MyApp.VowelCounter, []},
  ]
  Supervisor.start_link(children, strategy: :one_for_one, name: MyApp.Supervisor)
end
```

### Per-tenant plugin pool — DynamicSupervisor + Registry

When each tenant / session loads its own plugin (different `.wasm`
files, different configurations).

```elixir
defmodule MyApp.Plugins.Registry do
  def child_spec(_), do: Registry.child_spec(keys: :unique, name: __MODULE__)
  def via(tenant_id), do: {:via, Registry, {__MODULE__, tenant_id}}
end

defmodule MyApp.Plugins.Supervisor do
  use DynamicSupervisor
  def start_link(_), do: DynamicSupervisor.start_link(__MODULE__, :ok, name: __MODULE__)

  @impl true
  def init(:ok), do: DynamicSupervisor.init(strategy: :one_for_one)

  def start_plugin(tenant_id, manifest, opts \\ []) do
    spec = {MyApp.Plugins.Worker, [tenant_id: tenant_id, manifest: manifest] ++ opts}
    DynamicSupervisor.start_child(__MODULE__, spec)
  end

  def stop_plugin(tenant_id) do
    case Registry.lookup(MyApp.Plugins.Registry, tenant_id) do
      [{pid, _}] -> DynamicSupervisor.terminate_child(__MODULE__, pid)
      [] -> :ok
    end
  end
end

defmodule MyApp.Plugins.Worker do
  use GenServer, restart: :transient

  def start_link(opts) do
    tenant_id = Keyword.fetch!(opts, :tenant_id)
    GenServer.start_link(__MODULE__, opts, name: MyApp.Plugins.Registry.via(tenant_id))
  end

  def call(tenant_id, fun, input) do
    GenServer.call(MyApp.Plugins.Registry.via(tenant_id), {:call, fun, input})
  end

  @impl true
  def init(opts) do
    manifest = Keyword.fetch!(opts, :manifest)
    wasi = Keyword.get(opts, :wasi, false)
    {:ok, %{plugin: nil, manifest: manifest, wasi: wasi}, {:continue, :load}}
  end

  @impl true
  def handle_continue(:load, %{manifest: m, wasi: w} = state) do
    case Extism.Plugin.new(m, w) do
      {:ok, plugin} -> {:noreply, %{state | plugin: plugin}}
      {:error, r} -> {:stop, {:plugin_load_failed, r}, state}
    end
  end

  @impl true
  def handle_call({:call, fun, input}, _from, %{plugin: plugin} = state) do
    {:reply, Extism.Plugin.call(plugin, fun, input), state}
  end

  @impl true
  def terminate(_, %{plugin: plugin}) when not is_nil(plugin) do
    Extism.Plugin.free(plugin)
  end
  def terminate(_, _), do: :ok
end
```

Application supervisor wires the registry BEFORE the dynamic supervisor:

```elixir
children = [
  MyApp.Plugins.Registry,
  MyApp.Plugins.Supervisor,
  # ...
]
```

### Phoenix LiveView integration

A LiveView calling into the plugin GenServer. The plugin lives outside
the LiveView process — never load a plugin inside `mount/3`.

```elixir
defmodule MyAppWeb.PdfLive do
  use MyAppWeb, :live_view

  def mount(%{"id" => id}, _session, socket) do
    {:ok,
     socket
     |> assign(:document_id, id)
     |> assign(:result, nil)
     |> assign(:loading?, false)}
  end

  def handle_event("count", %{"text" => text}, socket) do
    {:noreply,
     socket
     |> assign(:loading?, true)
     |> start_async(:counted, fn -> MyApp.VowelCounter.count(text) end)}
  end

  def handle_async(:counted, {:ok, {:ok, result}}, socket) do
    {:noreply, assign(socket, result: result, loading?: false)}
  end

  def handle_async(:counted, {:ok, {:error, reason}}, socket) do
    {:noreply,
     socket
     |> put_flash(:error, "Plugin failed: #{inspect(reason)}")
     |> assign(loading?: false)}
  end

  def handle_async(:counted, {:exit, reason}, socket) do
    {:noreply,
     socket
     |> put_flash(:error, "Plugin crashed: #{inspect(reason)}")
     |> assign(loading?: false)}
  end
end
```

`start_async/3` keeps the LiveView responsive while the plugin runs.
The plugin call itself is synchronous in the calling task; the LiveView
just awaits the result. See `phoenix-liveview` §"Async as CPS".

### Hot reload — handle_call({:reload, manifest})

In dev, swap the plugin when the `.wasm` file changes:

```elixir
def handle_call({:reload, new_manifest}, _from, %{plugin: old} = state) do
  case Extism.Plugin.new(new_manifest, state.wasi) do
    {:ok, new_plugin} ->
      if old, do: Extism.Plugin.free(old)
      {:reply, :ok, %{state | plugin: new_plugin, manifest: new_manifest}}

    {:error, reason} = err ->
      # Keep the old plugin running — reload failure shouldn't kill service.
      {:reply, err, state}
  end
end
```

Pair with a file-watcher (`file_system` hex package) that triggers
`MyApp.VowelCounter.reload(new_manifest)` on `.wasm` changes.

### Testing — behaviour seam

The Extism Elixir SDK doesn't ship Mox-friendly behaviours. Wrap your
plugin module in your own behaviour so tests can substitute a stub.

```elixir
defmodule MyApp.VowelCounter.Behaviour do
  @callback count(String.t()) :: {:ok, map()} | {:error, term()}
end

defmodule MyApp.VowelCounter do
  @behaviour MyApp.VowelCounter.Behaviour
  # ... GenServer impl from §"Single shared plugin" above ...
end

defmodule MyApp.VowelCounter.Stub do
  @behaviour MyApp.VowelCounter.Behaviour
  @impl true
  def count(text) do
    {:ok, %{"count" => String.length(text), "total" => String.length(text), "vowels" => ""}}
  end
end

# config/test.exs
config :my_app, vowel_counter: MyApp.VowelCounter.Stub
```

Then call sites dispatch through `Application.get_env`:

```elixir
defp impl, do: Application.get_env(:my_app, :vowel_counter, MyApp.VowelCounter)
def count(text), do: impl().count(text)
```

For tests that DO exercise the real plugin (integration tier), tag them
`@tag :extism` and exclude from `mix test` defaults:

```elixir
# test_helper.exs
ExUnit.start(exclude: [:extism])
```

Run with `mix test --include extism` in CI.

## Anti-patterns (BAD/GOOD)

**Plugin-per-request (slow startup, leaks memory):**

```elixir
# BAD — recreates plugin on every call (parse + compile = expensive)
def count(text) do
  {:ok, plugin} = Extism.Plugin.new(@manifest, false)
  Extism.Plugin.call(plugin, "count_vowels", text)
  # NOTE: plugin never freed — leaks until process GC
end

# GOOD — load once, reuse via GenServer
def count(text), do: GenServer.call(MyApp.VowelCounter, {:count, text})
```

**Missing `free/1` after `Plugin.new` outside a GenServer:**

```elixir
# BAD — script style; plugin survives until OS process exit
{:ok, plugin} = Extism.Plugin.new(manifest, false)
{:ok, output} = Extism.Plugin.call(plugin, "fun", input)
process(output)

# GOOD — explicit free in any non-GenServer script
{:ok, plugin} = Extism.Plugin.new(manifest, false)
try do
  Extism.Plugin.call(plugin, "fun", input)
after
  Extism.Plugin.free(plugin)
end
```

**Treating output as a parsed map:**

```elixir
# BAD — Plugin.call returns binary, not decoded JSON
{:ok, %{"count" => n}} = Extism.Plugin.call(plugin, "count_vowels", text)
# ** (MatchError) — output is the JSON string, not a map

# GOOD — decode explicitly
{:ok, json} = Extism.Plugin.call(plugin, "count_vowels", text)
{:ok, %{"count" => n}} = Jason.decode(json)
```

**Loading plugin synchronously in `init/1`:**

```elixir
# BAD — blocks the supervisor's start sequence; slow WASM modules
# delay app startup by seconds.
def init(:ok) do
  {:ok, plugin} = Extism.Plugin.new(@manifest, false)
  {:ok, %{plugin: plugin}}
end

# GOOD — return fast, load via handle_continue
def init(:ok), do: {:ok, %{plugin: nil}, {:continue, :load}}

def handle_continue(:load, state) do
  case Extism.Plugin.new(@manifest, false) do
    {:ok, p} -> {:noreply, %{state | plugin: p}}
    {:error, r} -> {:stop, {:plugin_load_failed, r}, state}
  end
end
```

**Fetching plugin from URL at runtime without fallback:**

```elixir
# BAD — production startup depends on network reachability
@manifest %{wasm: [%{url: "https://example.com/plugin.wasm"}]}

# GOOD — vendor at build time, reference by path
# mix.exs aliases:
defp aliases do
  [
    "deps.get": ["deps.get", "extism.vendor"],
    "extism.vendor": &vendor_plugins/1
  ]
end

defp vendor_plugins(_) do
  File.mkdir_p!("priv/plugins")
  for {name, url} <- @plugins do
    body = Req.get!(url, retry: :transient).body
    File.write!("priv/plugins/#{name}.wasm", body)
  end
end

# Then in the GenServer:
@manifest %{wasm: [%{path: "priv/plugins/count_vowels.wasm"}]}
```

**Calling a freed plugin (use-after-free):**

```elixir
# BAD — plugin reference held after free
{:ok, plugin} = Extism.Plugin.new(manifest, false)
Extism.Plugin.free(plugin)
Extism.Plugin.call(plugin, "fun", input)  # raises

# GOOD — set the field to nil and pattern-match
def handle_call(:reload, _from, %{plugin: old} = state) do
  old && Extism.Plugin.free(old)
  case Extism.Plugin.new(@manifest, false) do
    {:ok, new} -> {:reply, :ok, %{state | plugin: new}}
    {:error, _} = err -> {:reply, err, %{state | plugin: nil}}
  end
end

def handle_call({:call, _, _}, _from, %{plugin: nil} = state),
  do: {:reply, {:error, :plugin_not_loaded}, state}
```

## Extism vs Rustler — when to pick which

Both expose native code to Elixir. They solve different problems.

| Property | Extism | Rustler NIF |
|---|---|---|
| Language of native code | Any (Rust, Go, JS, TS, C, Zig, AssemblyScript, …) | Rust only |
| Isolation | WASM sandbox (separate memory, no host syscalls without WASI) | None — runs in the BEAM process address space |
| Crash blast radius | Plugin crash returns error; BEAM keeps running | NIF segfault crashes the entire BEAM node |
| Scheduler integration | None — long calls block the calling process | Dirty schedulers available for long calls |
| Setup cost | Cargo build of `extism` NIF on first compile | Rustler build per project |
| Performance | ~5–50× slower than Rustler for tight loops; near-native for substantial work | Near-native always |
| User-supplied plugins | **Yes** — primary use case | **No** — code is part of your deploy |
| Host function imports | Not yet (v1.0 Elixir SDK) | Direct Elixir↔Rust calls |

**Pick Extism when:** plugins are an extension surface for users; multi-
language plugin authors; sandbox safety is required; the plugin call
is non-trivial work (parsing, transformation, compute) that amortizes
the WASM overhead.

**Pick Rustler when:** you own the code and trust it; performance
matters in tight loops; Elixir↔Rust integration needs callbacks both
ways; the work fits the BEAM scheduler (or use dirty schedulers if not).

For the Rust plugin-side (writing `.wasm` modules that Extism loads),
see [`rust-wasm`](../rust-wasm/SKILL.md) and its
[`rust_wasm_extism.md`](../rust-wasm/rust_wasm_extism.md) subskill.

## Common pitfalls

- **WASM module size matters.** A 30 MB plugin takes meaningful time
  and memory to load. Strip with `wasm-opt -Oz` on the plugin side, or
  split into smaller modules each loaded on demand.
- **No automatic `Logger.metadata` propagation.** The plugin call
  runs synchronously in the calling process; metadata applies. But
  any plugin output you log AFTER the call returns is in the caller's
  metadata scope. The plugin's own logs (via `info!`, `warn!` from
  the Rust PDK) go to Extism's log file — set via `Extism.set_log_file/2`.
- **Plugins can't call Elixir back (v1.0).** Design plugins as pure
  transformations: input in, output out. If the plugin needs data
  from your app, pass it in the input. If it needs to trigger a side
  effect, return a description and have the host execute it (the
  "instructions" pattern from elixir-planning §8.7).
- **The `extism` package compiles a Rust NIF.** That means slow first
  `mix compile`, and the `_build` dir size grows. CI caches that
  exclude `_build/dev/lib/extism` rebuild it every run.
- **WASM has no threads** (in the Extism runtime). Plugin compute is
  single-threaded within one `Plugin.call/3`. Parallelism comes from
  multiple plugin instances called from multiple Elixir processes.

## Related Skills

- **[rust-wasm](../rust-wasm/SKILL.md)** — Rust→WASM toolchain, build
  targets, and the `rust_wasm_extism.md` subskill for authoring plugins
  with `extism-pdk`. Key: `cargo build --target wasm32-unknown-unknown`
  for plugins without WASI; `wasm32-wasip1` when WASI is needed.
- **[rust-nif](../rust-nif/SKILL.md)** — Rustler NIFs for trusted native
  Rust. Key: choose Rustler over Extism when performance is paramount
  and you own the code.
- **[phoenix-liveview](../phoenix-liveview/SKILL.md)** — LiveView async
  patterns. Key: wrap Extism calls in `start_async/3` so the WebSocket
  stays responsive.
- **[elixir-planning](../elixir-planning/SKILL.md)** — Supervision tree
  design, error-kernel placement. Key: long-lived plugins go in the
  domain-services layer; transient per-request plugins under a
  `Task.Supervisor`.
- **[elixir-implementing](../elixir-implementing/SKILL.md)** — GenServer
  templates, `handle_continue` for slow init, Logger.metadata propagation.
