---
name: phoenix-liveview
description: Phoenix LiveView guidance including lifecycle, components, forms, streams, uploads, hooks, and real-time patterns. ALWAYS use for LiveView development and debugging. ALWAYS use when writing LiveView modules, components, or HEEx templates.
---

# Phoenix LiveView Skill

## Rules for Writing LiveView Code (LLM)

1. ALWAYS use `connected?(socket)` guard before subscribing to PubSub or starting expensive work in `mount/3` — mount runs twice (HTTP + WebSocket)
2. ALWAYS use streams for lists of database records — never store large collections in assigns
3. ALWAYS use `assign_async/3` or `start_async/3` for operations that block (HTTP calls, heavy queries) — never block the socket process
4. ALWAYS use `@impl true` on all LiveView callbacks
5. ALWAYS use `phx-disable-with` on submit buttons to prevent double-submission and show loading state
6. ALWAYS use `push_navigate/2` and `push_patch/2` — never use deprecated `live_redirect/2` or `live_patch/2`
7. ALWAYS preload associations in the parent LiveView — never query the database inside `render/1` or component render functions
8. ALWAYS use `<.input field={@form[:field]} />` for form fields — never access `@changeset` directly in templates
9. NEVER use `Process.sleep` in tests — use `assert_receive`, `render_async/1`, or `eventually` patterns
10. ALWAYS use `phx-update="stream"` with a unique `id` on the container and `id={dom_id}` on each item when using streams
11. ALWAYS pass data to LiveComponents via assigns, communicate back via `send/2` or callback assigns — never reach into parent state
12. NEVER copy large data structures (full conn, socket) into spawned processes or async assigns — extract only needed fields first

## Decision Tables

### Which Component Type?

| When you need to... | Use this | NOT this |
|---|---|---|
| Reusable stateless UI | Function component | LiveComponent |
| Encapsulated state + events | LiveComponent with `id` | Function component with assigns hack |
| Independent process surviving navigation | `live_render` with `sticky: true` | LiveComponent |
| Just organize code into modules | Function component (extract module) | LiveComponent |
| Batch-load data for list items | LiveComponent with `update_many/1` | N+1 queries in function components |

### Which Async Pattern?

| When you need to... | Use this | NOT this |
|---|---|---|
| Load data on mount with loading/error states | `assign_async/3` | Blocking call in mount |
| User-triggered async operation | `start_async/3` + `handle_async/3` | `Task.async` in handle_event |
| Async load into a stream | `start_async/3` + `stream(..., reset: true)` | `assign_async` (doesn't support streams) |
| Multiple independent async loads | Multiple `assign_async` calls | Single blocking function |

### Which Navigation?

| When you need to... | Use this | NOT this |
|---|---|---|
| Go to a different LiveView | `push_navigate/2` / `<.link navigate={}>` | `push_patch` (only same LV) |
| Stay in same LiveView, change params | `push_patch/2` / `<.link patch={}>` | `push_navigate` (remounts) |
| Full page load (non-LiveView) | `<.link href={}>` | `navigate` or `patch` |
| Redirect after form submit to controller | `redirect(socket, to: path)` | `push_navigate` |

## What LiveView Is

LiveView enables rich, real-time UX with server-rendered HTML over WebSockets. No JavaScript required for most interactions. Each LiveView runs as a process on the server.

**Good fit**: Real-time dashboards, forms with live validation, interactive UIs without complex client state, multi-user collaborative features.

**Consider alternatives**: Offline-first apps, complex client-side state (games, editors), heavy animations/graphics.

## Lifecycle Callbacks

### Connection Flow

```
HTTP GET → mount(params, session, socket) → render/1 → HTML response
                    ↓
WebSocket → mount(params, session, socket) → handle_params → render/1
                                                   ↓
                        User Event → handle_event/3 → render/1
                                                   ↓
                       Process Msg → handle_info/2 → render/1
```

### mount/3

First callback, called twice (HTTP then WebSocket):

```elixir
def mount(params, session, socket) do
  # params: %{"id" => "123"} - STRING keys from URL
  # session: %{"user_id" => 1} - STRING keys from session

  if connected?(socket), do: subscribe_to_updates()

  {:ok, assign(socket, user: nil, loading: true)}
end
```

### on_mount Hooks

Shared setup across multiple LiveViews — use for authentication, assigns, telemetry:

```elixir
defmodule MyAppWeb.UserAuth do
  import Phoenix.LiveView
  import Phoenix.Component

  # Optional auth — loads scope if present
  def on_mount(:mount_current_scope, _params, session, socket) do
    {:cont, mount_current_scope(socket, session)}
  end

  # Required auth — redirects if not authenticated
  def on_mount(:require_authenticated, _params, session, socket) do
    socket = mount_current_scope(socket, session)

    if socket.assigns.current_scope && socket.assigns.current_scope.user do
      {:cont, socket}
    else
      {:halt, socket |> put_flash(:error, "You must log in") |> redirect(to: ~p"/users/log-in")}
    end
  end

  # assign_new avoids re-fetching on push_patch within same live_session
  defp mount_current_scope(socket, session) do
    assign_new(socket, :current_scope, fn ->
      if token = session["user_token"] do
        {user, _} = Accounts.get_user_by_session_token(token)
        Scope.for_user(user)
      end || Scope.for_user(nil)
    end)
  end
end

# In router — :require_authenticated for protected routes
live_session :authenticated, on_mount: [{MyAppWeb.UserAuth, :require_authenticated}] do
  live "/dashboard", DashboardLive
  live "/settings", SettingsLive
end

# :mount_current_scope for public routes with optional user
live_session :public, on_mount: [{MyAppWeb.UserAuth, :mount_current_scope}] do
  live "/", HomeLive
end
```

**Key points:**
- Returns `{:cont, socket}` to continue or `{:halt, socket}` to stop
- Runs before `mount/3` — ideal for auth guards
- `current_scope` wraps user in a `Scope` struct — access user via `@current_scope.user`
- Session stores `:user_token` (not user ID) — enables per-session revocation
- `assign_new` avoids re-fetching on every `push_patch` within the session
- `live_session` groups routes sharing the same on_mount hooks

### Two-Tier live_session (User + Tenant)

For multi-tenant apps, use separate live_sessions for user-level and tenant-level auth. Crossing sessions forces a full page reload, clearing stale socket assigns:

```elixir
# User-level: authenticated but no team selected
live_session :authenticated, on_mount: [{UserAuth, :ensure_authenticated}] do
  live "/teams", TeamsLive
  live "/teams/new", NewTeamLive
end

# Tenant-level: authenticated AND team member
live_session :tenant, on_mount: [{UserAuth, :ensure_authenticated}, {TeamAuth, :ensure_member}] do
  live "/workspace", WorkspaceLive
  live "/workspace/notes/:id", NoteLive
end
```

### Controller-to-LiveView Handoff

Some actions need session mutation (setting tenant, logging in) which LiveView can't do. Use a controller POST that sets session, then redirects to a LiveView:

```elixir
# Controller — mutates session
def select_team(conn, %{"team_id" => team_id}) do
  conn
  |> put_session(:team_id, team_id)
  |> redirect(to: ~p"/workspace")
end

# LiveView — reads from session via on_mount
def on_mount(:load_team, _params, %{"team_id" => team_id}, socket) do
  {:cont, assign(socket, :team, Teams.get_team!(team_id))}
end
```
- Multiple hooks run in order: `on_mount: [Hook1, {Hook2, :arg}]`

### handle_params/3

Called after mount and on every navigation (push_patch, push_navigate):

```elixir
def handle_params(params, uri, socket) do
  # params: %{"page" => "2", "sort" => "name"} - STRING keys
  {:noreply,
   socket
   |> assign(:page, String.to_integer(params["page"] || "1"))
   |> load_data()}
end
```

### render/1

Returns HEEx template:

```elixir
def render(assigns) do
  ~H"""
  <div>
    <h1>{@title}</h1>
    <.user_list users={@users} />
  </div>
  """
end
```

### handle_event/3

Handles client events (phx-click, phx-submit, etc.):

```elixir
def handle_event(event, params, socket) do
  # event: "save" - STRING event name
  # params: %{"user" => %{"name" => "John"}} - STRING keys
  {:noreply, socket}  # or {:reply, map, socket}
end
```

### handle_info/2

Handles process messages (PubSub, Task results):

```elixir
def handle_info({:post_updated, post}, socket) do
  {:noreply, stream_insert(socket, :posts, post)}
end
```

### handle_async/3

Handles async task results (from start_async/3):

```elixir
def handle_async(:fetch_data, {:ok, result}, socket) do
  {:noreply, assign(socket, data: result)}
end

def handle_async(:fetch_data, {:exit, reason}, socket) do
  {:noreply, assign(socket, error: "Failed to load")}
end
```

## Function Components

Stateless, reusable UI pieces:

```elixir
attr :name, :string, required: true
attr :class, :string, default: nil
attr :rest, :global

slot :inner_block

def badge(assigns) do
  ~H"""
  <span class={["badge", @class]} {@rest}>
    {@name}
    {render_slot(@inner_block)}
  </span>
  """
end
```

### Named Slots

```elixir
slot :header
slot :footer
slot :inner_block, required: true

def card(assigns) do
  ~H"""
  <div class="rounded-lg border shadow">
    <div :if={@header != []} class="border-b px-4 py-2 bg-gray-50">
      {render_slot(@header)}
    </div>
    <div class="px-4 py-3">{render_slot(@inner_block)}</div>
    <div :if={@footer != []} class="border-t px-4 py-2 bg-gray-50">
      {render_slot(@footer)}
    </div>
  </div>
  """
end
```

### Slot Attributes

Pass data through slots for table columns, list items:

```elixir
slot :col, required: true do
  attr :label, :string, required: true
end

attr :rows, :list, required: true

def table(assigns) do
  ~H"""
  <table>
    <thead>
      <tr><th :for={col <- @col}>{col.label}</th></tr>
    </thead>
    <tbody>
      <tr :for={row <- @rows}>
        <td :for={col <- @col}>{render_slot(col, row)}</td>
      </tr>
    </tbody>
  </table>
  """
end
```

Usage: `<.table rows={@users}><:col :let={user} label="Name">{user.name}</:col></.table>`

**Key points:**
- Named slots are lists (check `@header != []` for optional)
- `render_slot(slot, argument)` passes data to `:let={var}`
- Slot attributes defined in `do` block

## LiveComponents (Stateful)

Use **only** when you need both encapsulated state AND encapsulated event handling:

```elixir
defmodule MyAppWeb.CounterComponent do
  use Phoenix.LiveComponent

  def mount(socket), do: {:ok, assign(socket, :count, 0)}

  def update(assigns, socket), do: {:ok, assign(socket, assigns)}

  def render(assigns) do
    ~H"""
    <div>
      <span>{@count}</span>
      <button phx-click="increment" phx-target={@myself}>+</button>
    </div>
    """
  end

  def handle_event("increment", _, socket) do
    {:noreply, update(socket, :count, &(&1 + 1))}
  end
end
```

```elixir
# In parent - id is REQUIRED
<.live_component module={CounterComponent} id="counter-1" initial={5} />

# Parent to component
send_update(CounterComponent, id: "counter-1", count: 10)

# Component to parent via callback
<.live_component module={Modal} id="modal" on_close={fn -> send(self(), :modal_closed) end} />
```

### update_many/1 for Batch Operations

Prevent N+1 queries when rendering multiple LiveComponents:

```elixir
def update_many(assigns_list) do
  ids = Enum.map(assigns_list, & &1.id)
  products = Products.get_many(ids) |> Map.new(&{&1.id, &1})
  Enum.map(assigns_list, fn assigns -> Map.put(assigns, :product, products[assigns.id]) end)
end
```

### LiveComponent Rules

- **Always** provide unique `id` attribute
- Events need `phx-target={@myself}` to stay in component
- Without `phx-target`, events go to parent LiveView
- **Never** use for code organization alone — use function components

## Nested LiveViews

Embed independent LiveViews using `live_render/3`:

```elixir
<%= live_render(@socket, MyAppWeb.AudioPlayerLive,
      id: "audio-player",
      session: %{"user_id" => @current_user.id},
      sticky: true
    ) %>
```

`sticky: true` keeps the child alive across parent navigation — use for audio players, chat widgets, persistent notifications.

## Forms

### Form Data Flow

```
Schema → Changeset → to_form() → @form assign → Template: @form[:field]
                                                        ↓
                              User Input (phx-change) → handle_event receives STRING key params
```

### Complete Form Example

```elixir
def mount(_params, _session, socket) do
  changeset = Accounts.change_user(%User{})
  {:ok, assign(socket, form: to_form(changeset))}
end

def handle_event("validate", %{"user" => user_params}, socket) do
  changeset =
    %User{}
    |> User.changeset(user_params)
    |> Map.put(:action, :validate)

  {:noreply, assign(socket, form: to_form(changeset))}
end

def handle_event("save", %{"user" => user_params}, socket) do
  case Accounts.create_user(user_params) do
    {:ok, user} ->
      {:noreply,
       socket
       |> put_flash(:info, "User created!")
       |> push_navigate(to: ~p"/users/#{user}")}

    {:error, %Ecto.Changeset{} = changeset} ->
      {:noreply, assign(socket, form: to_form(changeset))}
  end
end
```

### Form Template

```heex
<.form for={@form} phx-change="validate" phx-submit="save">
  <.input field={@form[:name]} type="text" label="Name" />
  <.input field={@form[:email]} type="email" label="Email" />
  <.button phx-disable-with="Saving...">Save</.button>
</.form>
```

### Form Rules

- **Always** use `to_form()` to convert changeset
- **Always** access fields as `@form[:field]`
- **Never** access changeset directly in template
- **Never** use `<.form let={f}>` — it's deprecated
- Form params **always** have STRING keys
- Use `phx-debounce` to rate-limit validation

### Form Auto-Recovery

LiveView automatically recovers form state after server restart or reconnection:

1. User fills form → values exist only in browser DOM state
2. Server restarts or WebSocket reconnects
3. LiveView fires `phx-change` automatically for forms with matching IDs
4. Handler updates server assigns with current form values

**Requirements:** Stable, unique `id` on the form. `phx-change` handler that updates assigns. Without `phx-change`, server sends stale state on reconnect → user input lost.

### Nested Forms

Use `inputs_for` to render nested associations (has_many, embeds_many):

```heex
<.form for={@form} phx-change="validate" phx-submit="save">
  <.input field={@form[:title]} label="Recipe Title" />

  <.inputs_for :let={ingredient_form} field={@form[:ingredients]}>
    <div class="flex gap-2 items-center">
      <.input field={ingredient_form[:name]} placeholder="Ingredient" />
      <.input field={ingredient_form[:amount]} placeholder="Amount" />
      <input type="hidden" name="recipe[ingredients_sort][]" value={ingredient_form.index} />
      <button type="button" name="recipe[ingredients_drop][]" value={ingredient_form.index}
              phx-click={JS.dispatch("change")}>
        <.icon name="hero-trash" />
      </button>
    </div>
  </.inputs_for>

  <input type="hidden" name="recipe[ingredients_drop][]" />
  <button type="button" name="recipe[ingredients_sort][]" value="new" phx-click={JS.dispatch("change")}>
    Add Ingredient
  </button>
</.form>
```

**Schema:** Use `cast_assoc(:ingredients, sort_param: :ingredients_sort, drop_param: :ingredients_drop)` with `on_replace: :delete`.

**Key points:**
- `sort_param` with value `"new"` adds a new item
- `drop_param` button value specifies which index to remove
- Empty hidden input for `drop_param` ensures param exists when nothing deleted

For advanced nested form patterns (custom `_target` handlers, Sortable.js integration), see [examples.md](examples.md).

## Streams

Use streams for large collections to minimize memory:

```elixir
def mount(_params, _session, socket) do
  {:ok, stream(socket, :messages, Chat.list_messages())}
end

def handle_info({:new_message, message}, socket) do
  {:noreply, stream_insert(socket, :messages, message)}
end
```

### Stream Template

```heex
<div id="messages" phx-update="stream">
  <div :for={{dom_id, message} <- @streams.messages} id={dom_id}>
    {message.body}
  </div>
</div>
```

### Stream Operations

```elixir
stream(socket, :items, items)                          # Initialize
stream_insert(socket, :items, item)                    # Append (default)
stream_insert(socket, :items, item, at: 0)             # Prepend
stream_delete(socket, :items, item)                    # Delete
stream_delete_by_dom_id(socket, :items, "items-123")   # Delete by DOM ID
stream(socket, :items, new_items, reset: true)         # Reset entire stream
```

### Stream Rules

- **Always** use streams for collections (not plain assigns)
- Streams are **not enumerable** — can't use Enum.filter
- To filter: refetch data and `stream(socket, :items, filtered, reset: true)`
- Parent element needs `phx-update="stream"` and an `id`
- Each item needs unique `id` from the dom_id
- **Never** use deprecated `phx-update="append"` or `"prepend"`

### Combining Streams with Async

Load large collections asynchronously into streams:

```elixir
def mount(_params, _session, socket) do
  {:ok,
   socket
   |> assign(:loading, true)
   |> stream(:notes, [])
   |> start_async(:load_notes, fn -> Notes.list_all() end)}
end

def handle_async(:load_notes, {:ok, notes}, socket) do
  {:noreply,
   socket
   |> assign(:loading, false)
   |> stream(:notes, notes, reset: true)}
end
```

**Note:** `assign_async` doesn't directly support streams. Use `start_async` with `stream(..., reset: true)` in the callback.

### Dynamic Forms with Streams

Use streams to manage collections of independent, editable forms (todo lists, kanban cards, inline editable settings):

```elixir
defp build_item_form(item_or_changeset, params \\ %{}, action \\ nil) do
  changeset =
    item_or_changeset
    |> Items.change_item(params)
    |> Map.put(:action, action)

  to_form(changeset, id: "item-form-#{changeset.data.id || "new"}")
end

def mount(%{"list_id" => list_id}, _session, socket) do
  item_forms = list_id |> Items.list_items() |> Enum.map(&build_item_form/1)
  {:ok, socket |> assign(:list_id, list_id) |> stream(:items, item_forms)}
end

def handle_event("validate", %{"item" => item_params, "id" => id}, socket) do
  item = Items.get_item(id) || %Item{id: id, list_id: socket.assigns.list_id}
  {:noreply, stream_insert(socket, :items, build_item_form(item, item_params, :validate))}
end

def handle_event("save", %{"item" => item_params, "id" => id}, socket) do
  item = Items.get_item(id) || %Item{id: id, list_id: socket.assigns.list_id}

  case Items.save_item(item, item_params) do
    {:ok, saved} -> {:noreply, stream_insert(socket, :items, build_item_form(saved))}
    {:error, cs} -> {:noreply, stream_insert(socket, :items, to_form(cs, id: "item-form-#{id}"))}
  end
end
```

**Key points:**
- Custom form IDs are critical — `to_form(changeset, id: "unique-id")` enables stream tracking
- Stream contains forms, not data — each item is a Phoenix.HTML.Form struct
- Pass ID via `phx-value-id` to identify which form triggered the event

| Aspect | Nested Forms (`inputs_for`) | Stream Forms |
|--------|----------------------------|--------------|
| Data structure | Parent with children | Independent items |
| Validation | All at once on parent submit | Each item independently |
| Save | Single transaction | Per-item saves |
| Use case | Recipe → ingredients | Todo list, kanban |

## Async Operations

### assign_async/3

For data that loads asynchronously on mount:

```elixir
def mount(_params, _session, socket) do
  {:ok,
   socket
   |> assign(:page_title, "Dashboard")
   |> assign_async(:stats, fn -> {:ok, %{stats: calculate_stats()}} end)}
end
```

```heex
<.async_result :let={stats} assign={@stats}>
  <:loading>Loading stats...</:loading>
  <:failed :let={reason}>Error: {inspect(reason)}</:failed>
  <div>Total: {stats.total}</div>
</.async_result>
```

### start_async/3

For operations triggered by user action:

```elixir
def handle_event("export", _, socket) do
  {:noreply, start_async(socket, :export, fn -> generate_export() end)}
end

def handle_async(:export, {:ok, file_path}, socket) do
  {:noreply, socket |> put_flash(:info, "Export ready!") |> push_event("download", %{path: file_path})}
end

def handle_async(:export, {:exit, _reason}, socket) do
  {:noreply, put_flash(socket, :error, "Export failed")}
end
```

## JavaScript Interop

### Hooks

```javascript
// app.js
let Hooks = {}

Hooks.InfiniteScroll = {
  mounted() {
    this.observer = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting) {
        this.pushEvent("load_more", {})
      }
    })
    this.observer.observe(this.el)
  },
  destroyed() { this.observer.disconnect() }
}

let liveSocket = new LiveSocket("/live", Socket, {
  hooks: Hooks,
  params: {_csrf_token: csrfToken}
})
```

```heex
<div id="scroll-trigger" phx-hook="InfiniteScroll" phx-update="ignore"></div>
```

### Hook Lifecycle

- `mounted()`: Element added to DOM
- `updated()`: Element updated by LiveView
- `destroyed()`: Element removed from DOM
- `disconnected()`: WebSocket disconnected
- `reconnected()`: WebSocket reconnected

### Hook Methods

```javascript
this.el                                    // The hook element
this.pushEvent(event, payload)             // Send event to LiveView
this.pushEventTo(selector, event, payload) // To specific target
this.handleEvent(event, callback)          // Receive from server
this.upload(name, files)                   // Programmatically trigger upload
```

### Hook with phx-update="ignore"

When a hook manages its own DOM, prevent LiveView from overwriting it:

```heex
<div id="chart" phx-hook="Chart" phx-update="ignore" data-values={Jason.encode!(@values)}></div>
```

### Server to Client Events

```elixir
# In LiveView
{:noreply, push_event(socket, "highlight", %{id: item.id})}
```

```javascript
// In hook
this.handleEvent("highlight", ({id}) => {
  document.getElementById(id).classList.add("highlight")
})
```

## SVG Interactions

SVG elements work with LiveView bindings. Click coordinates are available via `offsetX`/`offsetY`:

```elixir
defmodule MyAppWeb.DrawingLive do
  use Phoenix.LiveView

  def mount(_params, _session, socket) do
    {:ok, assign(socket, :points, [])}
  end

  def render(assigns) do
    ~H"""
    <svg phx-click="clicked" width="500" height="500" class="border border-blue-500">
      <circle :for={{x, y} <- @points} cx={x} cy={y} r="5" fill="purple" />
    </svg>
    """
  end

  def handle_event("clicked", %{"offsetX" => x, "offsetY" => y}, socket) do
    {:noreply, update(socket, :points, fn points -> [{x, y} | points] end)}
  end
end
```

**SVG with clickable zones:**

```heex
<svg viewBox="0 0 100 100" class="w-64 h-64">
  <rect
    :for={zone <- @zones}
    x={zone.x} y={zone.y}
    width={zone.width} height={zone.height}
    phx-click="zone-clicked"
    phx-value-id={zone.id}
    class="cursor-pointer hover:opacity-80"
    fill={zone.color}
  />
  <circle cx={@cursor.x} cy={@cursor.y} r="3" fill="red" />
</svg>
```

**Key points:**
- All standard SVG elements support `phx-click`, `phx-value-*`, `:for`, `:if`
- Use `viewBox` for scalable coordinates independent of display size
- SVG diffs efficiently — LiveView only patches changed attributes
- For interactive dashboards (gauges, meters, tanks), see the [live-industrial-web-ui](../live-industrial-web-ui/SKILL.md) skill

## Range Sliders

**CRITICAL:** `phx-change` only fires on release. For real-time updates while dragging, use a JavaScript hook.

### Real-Time Slider (Updates While Dragging)

```javascript
Hooks.Slider = {
  mounted() {
    this.el.addEventListener("input", (e) => {
      this.pushEvent("slider-change", {
        name: this.el.name,
        value: e.target.value
      })
    })
  }
}
```

```heex
<input type="range" id="exposure-slider" name="exposure"
       min="100" max="100000" value={@exposure} phx-hook="Slider" />
<span>{@exposure} μs</span>
```

```elixir
def handle_event("slider-change", %{"name" => "exposure", "value" => value}, socket) do
  {:noreply, assign(socket, :exposure, String.to_integer(value))}
end
```

### Hybrid: Visual Feedback + Debounced Server Updates

For expensive operations (hardware control, database writes):

```javascript
Hooks.DebouncedSlider = {
  mounted() {
    this.timeout = null
    this.el.addEventListener("input", (e) => {
      const value = e.target.value
      const name = this.el.name
      // Immediate visual feedback via CSS variable
      document.documentElement.style.setProperty(`--${name}`, value)
      // Debounce server update
      clearTimeout(this.timeout)
      this.timeout = setTimeout(() => {
        this.pushEvent("slider-commit", {name: name, value: value})
      }, 300)
    })
  },
  destroyed() { clearTimeout(this.timeout) }
}
```

### Throttling Considerations

| Approach | Use Case | Behavior |
|----------|----------|----------|
| `phx-debounce="300"` | Form validation | Waits for pause in input |
| `phx-throttle="100"` | Real-time display | Max 10 events/second |
| Hook with debounce | Hardware control | Immediate UI, delayed commit |
| Hook without debounce | Visual feedback only | Every change sent |

**Warning:** `phx-throttle` on sliders can cause value "snap back" if released during throttle window. Prefer debounce or hybrid hook.

## SVG Charts and Gauges

Server-rendered SVG charts update efficiently through LiveView's DOM diffing — only changed attributes are patched over the wire.

### Simple Bar Chart Component

```elixir
attr :data, :list, required: true  # [{label, value}, ...]
attr :max, :integer, default: nil
attr :width, :integer, default: 400
attr :height, :integer, default: 200

def bar_chart(assigns) do
  max_val = assigns.max || Enum.max_by(assigns.data, &elem(&1, 1)) |> elem(1)
  bar_width = assigns.width / length(assigns.data) * 0.8
  gap = assigns.width / length(assigns.data) * 0.2

  assigns = assign(assigns, max_val: max_val, bar_width: bar_width, gap: gap)

  ~H"""
  <svg viewBox={"0 0 #{@width} #{@height}"} class="w-full">
    <g :for={{label, value, idx} <- Enum.with_index(@data, fn {l, v}, i -> {l, v, i} end)}>
      <rect
        x={idx * (@bar_width + @gap) + @gap / 2}
        y={@height - value / @max_val * @height * 0.85}
        width={@bar_width}
        height={value / @max_val * @height * 0.85}
        fill="currentColor"
        class="text-blue-500 hover:text-blue-600 transition-colors"
      />
      <text
        x={idx * (@bar_width + @gap) + @gap / 2 + @bar_width / 2}
        y={@height - 2}
        text-anchor="middle"
        class="text-xs fill-gray-600"
      >
        {label}
      </text>
    </g>
  </svg>
  """
end
```

### Real-Time Gauge Component

```elixir
attr :value, :float, required: true  # 0.0 to 1.0
attr :label, :string, default: ""
attr :color, :string, default: "text-blue-500"

def gauge(assigns) do
  # Arc from -135° to 135° (270° sweep)
  angle = -135 + assigns.value * 270
  # SVG arc endpoint calculation
  rad = angle * :math.pi() / 180
  end_x = 50 + 35 * :math.cos(rad)
  end_y = 50 + 35 * :math.sin(rad)
  large_arc = if assigns.value > 0.5, do: 1, else: 0

  assigns = assign(assigns, end_x: end_x, end_y: end_y, large_arc: large_arc)

  ~H"""
  <svg viewBox="0 0 100 100" class="w-32 h-32">
    <%!-- Background arc --%>
    <circle cx="50" cy="50" r="35" fill="none" stroke="#e5e7eb" stroke-width="8"
            stroke-dasharray="235 100" transform="rotate(135 50 50)" />
    <%!-- Value arc --%>
    <path
      d={"M #{50 + 35 * :math.cos(-135 * :math.pi() / 180)} #{50 + 35 * :math.sin(-135 * :math.pi() / 180)} A 35 35 0 #{@large_arc} 1 #{@end_x} #{@end_y}"}
      fill="none"
      stroke="currentColor"
      stroke-width="8"
      stroke-linecap="round"
      class={@color}
    />
    <%!-- Center text --%>
    <text x="50" y="55" text-anchor="middle" class="text-lg font-bold fill-gray-800">
      {round(@value * 100)}%
    </text>
    <text x="50" y="70" text-anchor="middle" class="text-xs fill-gray-500">{@label}</text>
  </svg>
  """
end
```

### Live-Updating Dashboard Pattern

```elixir
def mount(_params, _session, socket) do
  if connected?(socket) do
    :timer.send_interval(1000, :tick)
  end

  {:ok, assign(socket, cpu: 0.0, memory: 0.0, requests: [])}
end

def handle_info(:tick, socket) do
  {:noreply,
   socket
   |> assign(:cpu, System.schedulers_online() |> get_cpu_usage())
   |> assign(:memory, :erlang.memory(:total) / 1_000_000_000)
   |> update(:requests, &Enum.take([get_rps() | &1], 60))}
end
```

```heex
<div class="grid grid-cols-3 gap-4">
  <.gauge value={@cpu} label="CPU" color="text-green-500" />
  <.gauge value={@memory} label="RAM" color="text-blue-500" />

  <svg viewBox="0 0 200 60" class="w-full">
    <polyline
      points={@requests |> Enum.with_index() |> Enum.map(fn {v, i} -> "#{i * 3.3},#{60 - v * 0.6}" end) |> Enum.join(" ")}
      fill="none"
      stroke="currentColor"
      stroke-width="1.5"
      class="text-purple-500"
    />
  </svg>
</div>
```

**Key points:**
- SVG diffs efficiently — only changed attributes (values, positions) are sent
- Use `viewBox` for responsive sizing, CSS classes for colors via `currentColor`
- Real-time updates via `:timer.send_interval` + `handle_info`
- For industrial-grade components (tanks, valves, meters), see [live-industrial-web-ui](../live-industrial-web-ui/SKILL.md) skill

### Chart via Hook (External Libraries)

When SVG components aren't enough, use Chart.js/D3 via hooks:

```javascript
Hooks.Chart = {
  mounted() {
    this.chart = new Chart(this.el, {
      type: "line",
      data: JSON.parse(this.el.dataset.chartData),
      options: { responsive: true, animation: false }
    })
  },
  updated() {
    const newData = JSON.parse(this.el.dataset.chartData)
    this.chart.data = newData
    this.chart.update("none")  // No animation on update
  },
  destroyed() { this.chart.destroy() }
}
```

```heex
<canvas id="metrics-chart" phx-hook="Chart"
        data-chart-data={Jason.encode!(@chart_data)}></canvas>
```

**Note:** Use `phx-update="ignore"` if the hook manages all DOM updates. Omit it (as above) when you want LiveView to update `data-*` attributes that trigger `updated()`.

## Drag-and-Drop with SortableJS

Complete pattern for reorderable lists:

```javascript
import Sortable from "sortablejs"

Hooks.Sortable = {
  mounted() {
    let group = this.el.dataset.group || undefined
    this.sortable = new Sortable(this.el, {
      animation: 150,
      delay: 100,
      group: group,
      dragClass: "drag-item",
      ghostClass: "drag-ghost",
      forceFallback: true,
      onEnd: e => {
        let params = { old: e.oldIndex, new: e.newIndex, ...e.item.dataset }
        this.pushEventTo(this.el, "reposition", params)
      }
    })
  },
  destroyed() { this.sortable.destroy() }
}
```

```heex
<div id="task-list" phx-hook="Sortable" data-group="tasks">
  <div :for={task <- @tasks} id={"task-#{task.id}"} data-id={task.id}
       class="drag-ghost:bg-zinc-300 drag-ghost:border-dashed">
    {task.title}
  </div>
</div>
```

```elixir
def handle_event("reposition", %{"id" => id, "old" => old, "new" => new}, socket) do
  task = Tasks.get_task!(id)
  Tasks.update_position(task, new)
  {:noreply, stream(socket, :tasks, Tasks.list_ordered())}
end
```

**Multi-list drag (kanban-style):** Items with the same `data-group` can be dragged between lists. Add `data-column={column.id}` to track source/destination.

**Tailwind variants** for drag styling:
```javascript
// tailwind.config.js
plugins: [
  plugin(({addVariant}) => {
    addVariant("drag-item", [".drag-item&", ".drag-item &"])
    addVariant("drag-ghost", [".drag-ghost&", ".drag-ghost &"])
  })
]
```

## LiveView.JS Commands

Client-side operations without server roundtrip:

```elixir
<button phx-click={JS.toggle(to: "#menu")}>Toggle Menu</button>

<button phx-click={JS.hide(to: "#modal") |> JS.push("close_modal")}>Close</button>
```

### Available Commands

```elixir
JS.show(to: selector, transition: {"ease-out", "opacity-0", "opacity-100"})
JS.hide(to: selector, transition: {"ease-in", "opacity-100", "opacity-0"})
JS.toggle(to: selector)
JS.add_class("active", to: selector)
JS.remove_class("active", to: selector)
JS.toggle_class("active", to: selector)
JS.set_attribute({"aria-expanded", "true"}, to: selector)
JS.remove_attribute("disabled", to: selector)
JS.toggle_attribute({"aria-expanded", "true", "false"}, to: selector)
JS.dispatch("click", to: selector)
JS.push("event_name", value: %{key: "value"})
JS.navigate(~p"/path")
JS.patch(~p"/path")
JS.focus(to: selector)
JS.focus_first(to: selector)
JS.push_focus()   # Save current focus to stack
JS.pop_focus()    # Restore focus from stack
JS.exec("phx-remove", to: selector)
```

### Essential JS Patterns

**Accordion:**
```heex
<div :for={item <- @items}>
  <button phx-click={
    JS.toggle_class("hidden", to: "#content-#{item.id}")
    |> JS.toggle_class("rotate-180", to: "#chevron-#{item.id}")
  }>
    <span>{item.title}</span>
    <.icon name="hero-chevron-down" id={"chevron-#{item.id}"} class="transition-transform duration-300" />
  </button>
  <div id={"content-#{item.id}"} class="hidden">{item.content}</div>
</div>
```

**Dropdown Menu:**
```heex
<div>
  <button phx-click={
    JS.toggle_class("hidden", to: "#dropdown-menu")
    |> JS.toggle_attribute({"aria-expanded", "true", "false"})
  } aria-expanded="false">Menu</button>
  <div id="dropdown-menu" class="hidden absolute mt-2 bg-white shadow-lg rounded">
    <a href="#" class="block px-4 py-2">Option 1</a>
  </div>
</div>
```

**Instant Feedback + Server Sync:**
```heex
<button phx-click={JS.push("toggle_search") |> JS.toggle(to: "#search-form")}>
  <.icon name="hero-magnifying-glass" />
</button>
```

**Extract Complex JS to Helper:**
```elixir
defp toggle_accordion(id) do
  JS.toggle_class("hidden", to: "#content-#{id}")
  |> JS.toggle_class("rotate-180", to: "#chevron-#{id}")
  |> JS.toggle_attribute({"aria-expanded", "true", "false"}, to: "#btn-#{id}")
end
```

**Focus Management Summary:**

| Command | Purpose |
|---------|---------|
| `JS.focus(to:)` | Focus specific element |
| `JS.focus_first(to:)` | Focus first focusable child |
| `JS.push_focus()` | Save current focus before modal/dropdown |
| `JS.pop_focus()` | Restore focus after closing |
| `<.focus_wrap>` | Trap Tab key within container |

For advanced patterns (accessible modals with focus stacks, server-triggered JS via `execJS`, copy to clipboard), see [examples.md](examples.md).

## Alpine.js Integration

Alpine.js adds client-side interactivity when LiveView.JS commands aren't sufficient.

**See [alpine.md](alpine.md) for comprehensive reference.**

### Critical Setup

```javascript
// app.js
import Alpine from "alpinejs";
window.Alpine = Alpine;
Alpine.start();

const liveSocket = new LiveSocket("/live", Socket, {
  hooks: Hooks,
  params: {_csrf_token: csrfToken},
  dom: {
    onBeforeElUpdated(from, to) {
      if (from._x_dataStack) Alpine.clone(from, to);  // Preserve Alpine state
    }
  }
});
```

### When to Use Alpine vs LiveView.JS

| Use Case | LiveView.JS | Alpine |
|----------|:-----------:|:------:|
| Simple show/hide, class toggle | x | |
| Focus management | x | |
| Complex client-side state machine | | x |
| Smooth animations with timing | | x |
| Third-party JS wrappers | | x |

### Integration Rules

- **Always** use `onBeforeElUpdated` with `Alpine.clone()`
- **Always** use `JSON.encode!` for server-to-client data
- **Always** add `x-cloak` and `[x-cloak] { display: none !important; }` CSS
- **Always** use `x-bind:` not `:` shorthand (conflicts with `:if`/`:for`)

## File Uploads

### Local Uploads

```elixir
def mount(_params, _session, socket) do
  {:ok,
   socket
   |> allow_upload(:avatar,
       accept: ~w(.jpg .jpeg .png),
       max_entries: 1,
       max_file_size: 5_000_000)}
end

def handle_event("save", _params, socket) do
  uploaded_files =
    consume_uploaded_entries(socket, :avatar, fn %{path: path}, entry ->
      dest = Path.join(["priv/static/uploads", entry.client_name])
      File.cp!(path, dest)
      {:ok, "/uploads/#{entry.client_name}"}
    end)

  {:noreply, update(socket, :uploaded_files, &(&1 ++ uploaded_files))}
end
```

```heex
<form phx-submit="save" phx-change="validate">
  <.live_file_input upload={@uploads.avatar} />

  <%= for entry <- @uploads.avatar.entries do %>
    <div>
      <.live_img_preview entry={entry} />
      <progress value={entry.progress} max="100">{entry.progress}%</progress>
      <button phx-click="cancel" phx-value-ref={entry.ref}>&times;</button>
    </div>

    <%= for err <- upload_errors(@uploads.avatar, entry) do %>
      <p class="error">{error_to_string(err)}</p>
    <% end %>
  <% end %>
</form>
```

For external uploads (S3), streaming uploads (UploadWriter), and programmatic uploads from hooks, see [examples.md](examples.md).

### File Downloads from LiveView

LiveView can't send binary responses directly. Use `push_event` to trigger browser downloads:

```elixir
def handle_event("download_csv", _, socket) do
  csv_data = Reports.generate_csv(socket.assigns.filters)

  # Option 1: Generate file, serve via controller
  path = Path.join(System.tmp_dir!(), "report-#{System.unique_integer()}.csv")
  File.write!(path, csv_data)
  {:noreply, redirect(socket, to: ~p"/downloads/#{Path.basename(path)}")}
end

# Option 2: Small files — push data URL to client
def handle_event("download_csv", _, socket) do
  csv_data = Reports.generate_csv(socket.assigns.filters)
  encoded = Base.encode64(csv_data)

  {:noreply, push_event(socket, "download", %{
    data: "data:text/csv;base64,#{encoded}",
    filename: "report.csv"
  })}
end
```

```javascript
// In hook or global listener
this.handleEvent("download", ({data, filename}) => {
  const link = document.createElement("a")
  link.href = data
  link.download = filename
  link.click()
})
```

**For large files**, always use Option 1 (controller route) — base64 encoding doubles the size and blocks the LiveView process.

## Navigation

### push_navigate vs push_patch

```elixir
push_navigate(socket, to: ~p"/users/#{user}")  # Different LiveView - full remount
push_patch(socket, to: ~p"/users?page=2")      # Same LiveView - triggers handle_params
```

### In Templates

```heex
<.link navigate={~p"/users/#{@user}"}>View User</.link>  <%!-- Different LiveView --%>
<.link patch={~p"/users?page=#{@page + 1}"}>Next Page</.link>  <%!-- Same LiveView --%>
<.link href={~p"/logout"} method="delete">Logout</.link>  <%!-- Full page load --%>
```

### URL-Synced Forms (Persistent Filters)

Sync filter/search forms with URL for shareable links and refresh persistence:

```elixir
def mount(_params, _session, socket) do
  # Don't load data here - handle_params will do it
  {:ok, socket}
end

def handle_params(params, _uri, socket) do
  filters = Map.take(params, ["title", "status", "author"])

  {:noreply,
   socket
   |> assign(:filters, filters)
   |> assign(:form, to_form(filters, as: "filters"))
   |> assign(:posts, Posts.search(filters))}
end

def handle_event("filter", %{"filters" => filters}, socket) do
  params = Map.reject(filters, fn {_k, v} -> v == "" end)
  {:noreply, push_patch(socket, to: ~p"/posts?#{params}")}
end
```

**Key points:**
- Form handler calls `push_patch`, not `assign`
- `handle_params` is the single source of truth
- Filter empty strings to keep URLs clean
- Use `phx-debounce` on text inputs
- Back button works — browser history navigates through filter states

### Pagination

```elixir
@per_page 20

def handle_params(params, _uri, socket) do
  page = String.to_integer(params["page"] || "1")
  filters = Map.take(params, ["status", "author"])
  %{entries: posts, total: total} = Posts.list(filters, page: page, per_page: @per_page)

  {:noreply,
   socket
   |> assign(:posts, posts)
   |> assign(:page, page)
   |> assign(:total_pages, ceil(total / @per_page))
   |> assign(:filters, filters)}
end
```

```heex
<nav :if={@total_pages > 1} class="flex gap-2 justify-center mt-4">
  <.link :if={@page > 1} patch={~p"/posts?#{Map.put(@filters, "page", @page - 1)}"}>Prev</.link>
  <.link :for={p <- 1..@total_pages} patch={~p"/posts?#{Map.put(@filters, "page", p)}"}
         class={if p == @page, do: "font-bold"}>{p}</.link>
  <.link :if={@page < @total_pages} patch={~p"/posts?#{Map.put(@filters, "page", @page + 1)}"}>Next</.link>
</nav>
```

### Context Function Pattern for Pagination

```elixir
# In context module — return structured result
def list(filters, opts \\ []) do
  page = Keyword.get(opts, :page, 1)
  per_page = Keyword.get(opts, :per_page, 20)

  query = from(p in Post) |> apply_filters(filters)
  total = Repo.aggregate(query, :count)
  entries = query |> limit(^per_page) |> offset(^((page - 1) * per_page)) |> Repo.all()

  %{entries: entries, total: total}
end
```

**Cursor-based pagination** (for streams or large datasets):

```elixir
def list_after(cursor_id, limit \\ 20) do
  from(p in Post, where: p.id > ^cursor_id, order_by: [asc: :id], limit: ^limit)
  |> Repo.all()
end

# In LiveView — load more on scroll or button click
def handle_event("load-more", _, socket) do
  last_id = List.last(socket.assigns.posts).id
  more = Posts.list_after(last_id)
  {:noreply, assign(socket, posts: socket.assigns.posts ++ more)}
end
```

## PubSub Integration

```elixir
def mount(_params, _session, socket) do
  if connected?(socket), do: Phoenix.PubSub.subscribe(MyApp.PubSub, "posts")
  {:ok, assign(socket, posts: [])}
end

def handle_info({:post_created, post}, socket) do
  {:noreply, stream_insert(socket, :posts, post, at: 0)}
end

def handle_info({:post_updated, post}, socket) do
  {:noreply, stream_insert(socket, :posts, post)}
end

def handle_info({:post_deleted, post}, socket) do
  {:noreply, stream_delete(socket, :posts, post)}
end
```

### Presence in Production

The basic `Presence.track/list` pattern is insufficient for production. Real apps need custom `handle_metas` for reactive UI, and `fetch/2` for bulk user loading:

```elixir
defmodule MyAppWeb.Presence do
  use Phoenix.Presence,
    otp_app: :my_app,
    pubsub_server: MyApp.PubSub

  @pubsub MyApp.PubSub

  # Bulk-load user data for presence entries (prevents N+1)
  def fetch(_topic, presences) do
    user_ids = Map.keys(presences) |> Enum.map(&String.to_integer/1)
    users = Accounts.get_users(user_ids) |> Map.new(&{to_string(&1.id), &1})

    for {id, presence} <- presences, into: %{} do
      {id, Map.put(presence, :user, users[id])}
    end
  end

  # React to presence changes — broadcast typed events
  def handle_metas(topic, %{joins: joins, leaves: leaves}, _presences, state) do
    for {user_id, _} <- joins do
      Phoenix.PubSub.local_broadcast(@pubsub, "proxy:#{topic}", {:user_joined, user_id})
    end

    for {user_id, _} <- leaves do
      Phoenix.PubSub.local_broadcast(@pubsub, "proxy:#{topic}", {:user_left, user_id})
    end

    {:ok, state}
  end
end
```

```elixir
# In LiveView — subscribe to proxy topic for reactive updates
def mount(_params, _session, socket) do
  if connected?(socket) do
    MyAppWeb.Presence.track(self(), "room:lobby", socket.assigns.current_user.id, %{
      joined_at: DateTime.utc_now()
    })
    Phoenix.PubSub.subscribe(MyApp.PubSub, "proxy:room:lobby")
  end

  {:ok, assign(socket, active_users: MyAppWeb.Presence.list("room:lobby"))}
end

def handle_info({:user_joined, user_id}, socket) do
  {:noreply, update(socket, :active_users, &Map.put(&1, user_id, %{}))}
end
```

### attach_hook for Cross-Cutting Concerns

Use `attach_hook/4` in `on_mount` to add behavior that runs on every `handle_params`, `handle_event`, or `handle_info` across multiple LiveViews:

```elixir
defmodule MyAppWeb.Nav do
  import Phoenix.LiveView
  import Phoenix.Component

  def on_mount(:default, _params, _session, socket) do
    {:cont,
     socket
     |> attach_hook(:active_tab, :handle_params, fn _params, uri, socket ->
       {:cont, assign(socket, :active_tab, active_tab_from_uri(uri))}
     end)
     |> attach_hook(:ping, :handle_event, fn
       "ping", %{"rtt" => rtt}, socket ->
         {:halt, push_event(socket, "pong", %{rtt: rtt})}
       _event, _params, socket ->
         {:cont, socket}
     end)}
  end

  defp active_tab_from_uri(uri) do
    uri |> URI.parse() |> Map.get(:path) |> String.split("/") |> Enum.at(1)
  end
end

# In router — applies to all LiveViews in this session
live_session :default, on_mount: [{MyAppWeb.Nav, :default}] do
  live "/dashboard", DashboardLive
  live "/settings", SettingsLive
end
```

**Key points:**
- `attach_hook` returns `{:cont, socket}` to continue or `{:halt, socket}` to stop processing
- `:handle_params` hooks fire on every navigation — ideal for breadcrumbs, active tab tracking
- `:handle_event` hooks can intercept events before the LiveView — useful for telemetry, ping/pong
- Detach with `detach_hook(socket, :hook_name, :handle_params)`

## Testing LiveView

```elixir
defmodule MyAppWeb.UserLiveTest do
  use MyAppWeb.ConnCase, async: true
  import Phoenix.LiveViewTest

  describe "Index" do
    test "lists users", %{conn: conn} do
      user = insert(:user)
      {:ok, view, html} = live(conn, ~p"/users")
      assert html =~ user.name
      assert has_element?(view, "#user-#{user.id}")
    end

    test "creates user", %{conn: conn} do
      {:ok, view, _html} = live(conn, ~p"/users/new")

      assert view
             |> form("#user-form", user: %{name: ""})
             |> render_change() =~ "can&#39;t be blank"

      {:ok, _, html} =
        view
        |> form("#user-form", user: %{name: "John", email: "john@example.com"})
        |> render_submit()
        |> follow_redirect(conn)

      assert html =~ "User created"
    end
  end
end
```

### Testing Async

```elixir
test "loads data asynchronously", %{conn: conn} do
  {:ok, view, _html} = live(conn, ~p"/dashboard")
  assert render_async(view) =~ "Data loaded"
end
```

### Testing Controller-Delegated Forms

| Helper | Use When |
|--------|----------|
| `render_submit/1` | Form handled entirely by LiveView |
| `submit_form/2` | Form has `:action`, submits to controller |
| `follow_trigger_action/2` | Form uses `phx-trigger-action` conditionally |

For complete testing patterns including `submit_form/2`, `follow_trigger_action/2`, and flash assertions, see [examples.md](examples.md).

## Anti-Patterns (BAD/GOOD)

### Memory Issues

```elixir
# BAD: Large list in assigns — grows with data!
{:ok, assign(socket, items: Repo.all(Item))}

# GOOD: Use streams
{:ok, stream(socket, :items, Repo.all(Item))}
```

### Blocking Operations

```elixir
# BAD: Blocking the socket process
def handle_event("fetch", _, socket) do
  data = HTTPClient.get!(url)  # Blocks all events!
  {:noreply, assign(socket, data: data)}
end

# GOOD: Use async
def handle_event("fetch", _, socket) do
  {:noreply, start_async(socket, :fetch, fn -> HTTPClient.get!(url) end)}
end
```

### PubSub Without connected? Guard

```elixir
# BAD: Subscribes during HTTP render too (mount runs twice)
def mount(_, _, socket) do
  Phoenix.PubSub.subscribe(MyApp.PubSub, "topic")
  {:ok, socket}
end

# GOOD: Only subscribe when WebSocket connected
def mount(_, _, socket) do
  if connected?(socket), do: Phoenix.PubSub.subscribe(MyApp.PubSub, "topic")
  {:ok, socket}
end
```

### Missing Feedback

```heex
<%!-- BAD: No loading state --%>
<button phx-click="save">Save</button>

<%!-- GOOD: Show loading --%>
<button phx-click="save" phx-disable-with="Saving...">Save</button>
```

### N+1 in Components

```elixir
# BAD: Query in component
def render(assigns) do
  user = Repo.get!(User, assigns.user_id)  # N+1!
  ...
end

# GOOD: Preload in parent
users = User |> preload(:department) |> Repo.all()
```

### Navigation Misuse

```elixir
# BAD: Using deprecated functions
live_redirect(socket, to: path)
live_patch(socket, to: path)

# GOOD: Use push_ functions
push_navigate(socket, to: path)
push_patch(socket, to: path)
```

### Form Anti-Patterns

```elixir
# BAD: Accessing changeset in template
<%= @changeset.errors %>

# GOOD: Use form
<%= for error <- @form[:email].errors do %>

# BAD: Using let binding (deprecated)
<.form for={@form} let={f}>

# GOOD: Direct field access
<.input field={@form[:email]} />
```

### Stream Without Proper IDs

```heex
<%!-- BAD: Missing id on container or items --%>
<div phx-update="stream">
  <div :for={{_id, item} <- @streams.items}>{item.name}</div>
</div>

<%!-- GOOD: Container and items both have ids --%>
<div id="items" phx-update="stream">
  <div :for={{dom_id, item} <- @streams.items} id={dom_id}>{item.name}</div>
</div>
```

### Trusting Client-Submitted IDs

```elixir
# BAD: user_id from hidden form field — client can change it
def handle_event("leave", %{"user_id" => user_id}, socket) do
  Teams.remove_member(user_id)  # Attacker submits any user_id!
end

# GOOD: Use server-side assigns — never trust client for identity
def handle_event("leave", _params, socket) do
  Teams.remove_member(socket.assigns.current_user.id)
end
```

### Full Re-Query on Every PubSub Message

```elixir
# BAD: Re-fetches entire workspace (7 joins) on every change
def handle_info(:update_workspace, socket) do
  workspace = Teams.get_full_workspace!(socket.assigns.team_id)  # Expensive!
  {:noreply, assign(socket, workspace: workspace)}
end

# GOOD: Granular updates — only change what's affected
def handle_info({:note_created, note}, socket) do
  {:noreply, stream_insert(socket, :notes, note)}
end

def handle_info({:member_joined, member}, socket) do
  {:noreply, update(socket, :members, &[member | &1])}
end
```

### Copying Large Data Into Async

```elixir
# BAD: Captures entire socket in closure
def handle_event("fetch", _, socket) do
  {:noreply, start_async(socket, :fetch, fn ->
    process(socket.assigns)  # Copies ALL assigns into spawned process
  end)}
end

# GOOD: Extract only what's needed
def handle_event("fetch", _, socket) do
  user_id = socket.assigns.current_user.id
  {:noreply, start_async(socket, :fetch, fn -> process(user_id) end)}
end
```

## Live Video & Streaming Patterns

### Video Player Hook

For HLS/live video playback, use a hook wrapping a player library (Vidstack, Video.js, or hls.js):

```javascript
Hooks.VideoPlayer = {
  mounted() {
    const videoEl = this.el.querySelector("video")
    const src = this.el.dataset.src

    // Initialize HLS.js for adaptive streaming
    if (Hls.isSupported()) {
      this.hls = new Hls({
        liveSyncDurationCount: 3,     // LL-HLS: stay close to live edge
        liveMaxLatencyDurationCount: 6,
        enableWorker: true
      })
      this.hls.loadSource(src)
      this.hls.attachMedia(videoEl)
    } else if (videoEl.canPlayType("application/vnd.apple.mpegurl")) {
      videoEl.src = src  // Safari native HLS
    }

    // Receive play commands from server
    this.handleEvent("play_video", ({url, title}) => {
      this.hls?.loadSource(url)
      // MediaSession API for OS-level controls
      if ("mediaSession" in navigator) {
        navigator.mediaSession.metadata = new MediaMetadata({title})
      }
    })
  },

  destroyed() {
    this.hls?.destroy()
  }
}
```

```heex
<div id="player" phx-hook="VideoPlayer" data-src={@video.hls_url}>
  <video controls playsinline class="w-full aspect-video bg-black"></video>
</div>
```

### HLS Content Delivery

Serve HLS segments via a plain Phoenix controller (not LiveView — binary content):

```elixir
defmodule MyAppWeb.HLSController do
  use MyAppWeb, :controller

  def show(conn, %{"video_id" => video_id, "filename" => filename}) do
    path = Path.join([storage_dir(), video_id, filename])

    content_type = case Path.extname(filename) do
      ".m3u8" -> "application/vnd.apple.mpegurl"
      ".ts" -> "video/mp2t"
      ".mp4" -> "video/mp4"
      _ -> "application/octet-stream"
    end

    conn
    |> put_resp_content_type(content_type)
    |> put_resp_header("cache-control", "no-cache")  # Live content — don't cache manifests
    |> send_file(200, path)
  end
end
```

### Dual Endpoint for Embeddable Content

For SaaS with embeddable widgets (video players, chat, forms), run a separate endpoint on a different port with relaxed CSP:

```elixir
# lib/my_app_web/embed/endpoint.ex
defmodule MyAppWeb.Embed.Endpoint do
  use Phoenix.Endpoint, otp_app: :my_app

  socket "/live", Phoenix.LiveView.Socket
  plug MyAppWeb.Embed.Router
end

# lib/my_app_web/embed/router.ex — minimal pipeline
pipeline :embed do
  plug :accepts, ["html"]
  plug :put_resp_header, "x-frame-options", "ALLOWALL"
  plug :put_resp_header, "content-security-policy", "frame-ancestors *"
end

# config/config.exs
config :my_app, MyAppWeb.Embed.Endpoint, http: [port: 4001]

# application.ex — add to supervision tree
children = [MyAppWeb.Endpoint, MyAppWeb.Embed.Endpoint]
```

### Stream Lifecycle with PubSub

For live streaming apps, broadcast stream state changes:

```elixir
# In context
def start_livestream(%User{} = user) do
  video = create_video!(%{user_id: user.id, type: :livestream, is_live: true})
  Phoenix.PubSub.broadcast!(MyApp.PubSub, "streams", %StreamStarted{video: video, user: user})
  {:ok, video}
end

def end_livestream(%Video{} = video) do
  {:ok, updated} = update_video(video, %{is_live: false, ended_at: DateTime.utc_now()})
  Phoenix.PubSub.broadcast!(MyApp.PubSub, "streams", %StreamEnded{video: updated})
  {:ok, updated}
end

# In LiveView
def mount(_params, _session, socket) do
  if connected?(socket) do
    Phoenix.PubSub.subscribe(MyApp.PubSub, "streams")
    Phoenix.PubSub.subscribe(MyApp.PubSub, "chat:#{socket.assigns.video.id}")
  end

  {:ok,
   socket
   |> stream(:messages, [])
   |> assign(:viewer_count, 0)}
end

def handle_info(%StreamStarted{video: video}, socket) do
  {:noreply, assign(socket, is_live: true, video: video)}
end

def handle_info(%Chat.MessageSent{message: msg}, socket) do
  {:noreply, stream_insert(socket, :messages, msg)}
end
```

### Chat with Auto-Scroll Hook

```javascript
Hooks.Chat = {
  mounted() {
    this.scrollToBottom()
  },
  updated() {
    // Only auto-scroll if user is near the bottom
    const threshold = 200
    const {scrollTop, scrollHeight, clientHeight} = this.el
    if (scrollHeight - scrollTop - clientHeight < threshold) {
      this.scrollToBottom()
    }
  },
  scrollToBottom() {
    this.el.scrollTop = this.el.scrollHeight
  }
}
```

```heex
<div id="chat-messages" phx-hook="Chat" phx-update="stream" class="overflow-y-auto h-96">
  <div :for={{dom_id, msg} <- @streams.messages} id={dom_id}>
    <span class="font-bold">{msg.sender_name}:</span> {msg.body}
  </div>
</div>
```

For the Membrane multimedia framework (RTMP ingestion, HLS packaging, ABR transcoding), see the [membrane](../membrane/SKILL.md) skill.

## Supporting Files

- **[reference.md](reference.md)** — Callback signatures, JS commands, form bindings, upload options, test helpers, socket return values
- **[examples.md](examples.md)** — Complete worked examples: full LiveView with all callbacks, modal component, search with debounce, custom input components (checkgroups), advanced nested forms, SortableJS drag-and-drop, accessible focus management, server-triggered JS (execJS), UploadWriter streaming uploads, component libraries, controller-delegated form testing
- **[alpine.md](alpine.md)** — Alpine.js directives, magic properties, stores, UI components, debugging
- **[state-persistence.md](state-persistence.md)** — Saving/restoring state with browser storage hooks, Phoenix.Token encryption, connect params optimization
- **[wasm.md](wasm.md)** — WebAssembly integration with LiveView hooks: Exclosured (Rust→WASM), Orb (Elixir→WASM), use cases

## Related Skills

- **[phoenix](../phoenix/SKILL.md)** — Contexts, Plug, channels, PubSub, router, security. Key: LiveView sits on top of Phoenix — contexts provide the data layer, PubSub enables real-time broadcasts.
- **[elixir](../elixir/SKILL.md)** — Pattern matching, pipelines, ok/error tuples. Key: LiveView callbacks are Elixir functions — use multi-clause dispatch, not if/else.
- **[elixir-testing](../elixir-testing/SKILL.md)** — ExUnit, Mox, async test patterns. Key: LiveView tests use ConnCase + Phoenix.LiveViewTest.
- **[tailwind](../tailwind/SKILL.md)** — Utility classes, dark mode, component styling. Key: Phoenix generators use Tailwind by default.
- **[svg](../svg/SKILL.md)** — SVG fundamentals, animation, accessibility. Key: SVG elements work natively with LiveView bindings.
- **[live-industrial-web-ui](../live-industrial-web-ui/SKILL.md)** — Industrial SVG components (gauges, meters, tanks) for LiveView dashboards.
