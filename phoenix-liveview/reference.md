# Phoenix LiveView Quick Reference

## Lifecycle Callback Signatures

```elixir
# Mount - params/session have STRING keys
@spec mount(params :: map(), session :: map(), socket :: Socket.t()) ::
  {:ok, Socket.t()} | {:ok, Socket.t(), keyword()}

# Handle URL params - called after mount and on navigation
@spec handle_params(params :: map(), uri :: String.t(), socket :: Socket.t()) ::
  {:noreply, Socket.t()}

# Render - must return ~H sigil or template
@spec render(assigns :: map()) :: Phoenix.LiveView.Rendered.t()

# Handle client events - event name and params are strings
@spec handle_event(event :: String.t(), params :: map(), socket :: Socket.t()) ::
  {:noreply, Socket.t()} | {:reply, map(), Socket.t()}

# Handle process messages - any Erlang term
@spec handle_info(msg :: term(), socket :: Socket.t()) ::
  {:noreply, Socket.t()}

# Handle async results
@spec handle_async(name :: atom(), result :: {:ok, term()} | {:exit, term()}, socket :: Socket.t()) ::
  {:noreply, Socket.t()}
```

## Socket Assign Functions

```elixir
# Basic assign
assign(socket, key, value)
assign(socket, key: value, other: value2)
assign(socket, %{key: value})

# Conditional assign
assign_new(socket, :key, fn -> compute_value() end)
assign_new(socket, :key, fn assigns -> compute_from(assigns) end)

# Update existing
update(socket, :count, fn count -> count + 1 end)
update(socket, :count, &(&1 + 1))

# Async assigns
assign_async(socket, :data, fn -> {:ok, %{data: fetch_data()}} end)
assign_async(socket, [:users, :posts], fn -> {:ok, %{users: [], posts: []}} end)

# Start async task
start_async(socket, :task_name, fn -> do_work() end)

# Streams
stream(socket, :items, items)
stream(socket, :items, items, reset: true)
stream_insert(socket, :items, item)
stream_insert(socket, :items, item, at: 0)
stream_insert(socket, :items, item, at: -1)
stream_delete(socket, :items, item)
stream_delete_by_dom_id(socket, :items, "items-123")

# Temporary assigns (cleared after render)
{:ok, socket, temporary_assigns: [messages: []]}

# Check connection
connected?(socket)
```

## LiveView.JS Commands

```elixir
# Show/Hide
JS.show(to: "#el")
JS.show(to: "#el", transition: {"ease-out duration-300", "opacity-0", "opacity-100"})
JS.show(to: "#el", time: 200)
JS.hide(to: "#el")
JS.hide(to: "#el", transition: {"ease-in duration-200", "opacity-100", "opacity-0"})
JS.toggle(to: "#el")

# Classes
JS.add_class("active", to: "#el")
JS.remove_class("active", to: "#el")
JS.toggle_class("active", to: "#el")
JS.add_class("active", to: "#el", transition: "fade-in")

# Attributes
JS.set_attribute({"aria-expanded", "true"}, to: "#el")
JS.remove_attribute("disabled", to: "#el")
JS.toggle_attribute({"aria-expanded", "true", "false"}, to: "#el")

# Events
JS.push("event_name")
JS.push("event_name", value: %{id: 123})
JS.push("event_name", target: "#component")
JS.dispatch("click", to: "#el")
JS.dispatch("my-event", to: "#el", detail: %{key: "value"})

# Navigation
JS.navigate(~p"/path")
JS.navigate(~p"/path", replace: true)
JS.patch(~p"/path")
JS.patch(~p"/path", replace: true)

# Focus
JS.focus(to: "#input")
JS.focus_first(to: "#container")
JS.pop_focus()

# Execute other commands
JS.exec("phx-remove", to: "#el")
JS.exec("data-confirm", to: "#el")

# Chaining
JS.hide(to: "#modal")
|> JS.show(to: "#success")
|> JS.push("confirmed")
```

## Form Binding Attributes

```elixir
# Form events
phx-change="validate"      # On any input change
phx-submit="save"          # On form submit
phx-trigger-action         # Trigger traditional form POST

# Input events
phx-focus="focused"        # On focus
phx-blur="blurred"         # On blur
phx-debounce="300"         # Debounce in ms
phx-debounce="blur"        # Debounce until blur
phx-throttle="500"         # Throttle in ms

# Click events
phx-click="clicked"        # On click
phx-click-away="close"     # Click outside element

# Value passing
phx-value-id={@item.id}    # Pass as %{"id" => "..."}
phx-value-action="delete"  # Pass as %{"action" => "delete"}

# Disable during submit
phx-disable-with="Saving..." # Button text while processing

# Target (for LiveComponents)
phx-target={@myself}       # Send to component
phx-target="#component-id" # Send to specific target

# Window/Document events
phx-window-keydown="key"   # Window keydown
phx-window-keyup="key"     # Window keyup
phx-window-focus="focus"   # Window focus
phx-window-blur="blur"     # Window blur

# Key filtering
phx-key="Enter"            # Only fire on Enter key
phx-key="Escape"           # Only fire on Escape key
```

## Upload Options

```elixir
allow_upload(socket, :avatar,
  accept: ~w(.jpg .jpeg .png .gif),  # Allowed extensions
  accept: :any,                       # Any file type
  max_entries: 3,                     # Max files
  max_file_size: 10_000_000,          # 10MB
  chunk_size: 64_000,                 # Chunk size for upload
  chunk_timeout: 10_000,              # Timeout per chunk
  auto_upload: true,                  # Upload on selection
  progress: &handle_progress/3,       # Progress callback
  external: &presign_upload/2         # External upload (S3)
)

# Access uploads
@uploads.avatar              # Upload config
@uploads.avatar.entries      # List of entries
@uploads.avatar.errors       # Upload-level errors

# Entry fields
entry.client_name            # Original filename
entry.client_type            # MIME type
entry.client_size            # File size
entry.progress               # Upload progress (0-100)
entry.ref                    # Unique reference
entry.valid?                 # Passes validations?
entry.done?                  # Upload complete?
entry.cancelled?             # Was cancelled?

# Entry errors
upload_errors(@uploads.avatar)         # Upload-level errors
upload_errors(@uploads.avatar, entry)  # Entry-level errors

# Consume uploads
consume_uploaded_entries(socket, :avatar, fn %{path: path}, entry ->
  # path is temp file path
  {:ok, result}
end)

# Cancel upload
cancel_upload(socket, :avatar, entry.ref)
```

## Test Helper Functions

```elixir
import Phoenix.LiveViewTest

# Mount LiveView
{:ok, view, html} = live(conn, ~p"/path")
{:ok, view, html} = live(conn, ~p"/path", session: %{})

# Navigate
{:ok, view, html} = live(conn, ~p"/path")
{:ok, new_view, html} = live_redirect(view, to: ~p"/other")

# Render
html = render(view)
html = render_click(view, "event")
html = render_click(view, "event", %{value: 1})
html = render_click(element(view, "#button"))
html = render_change(view, "validate", %{form: %{field: "value"}})
html = render_submit(view, "save", %{form: %{field: "value"}})
html = render_keydown(view, "keydown", %{key: "Enter"})
html = render_keyup(view, "keyup", %{key: "Escape"})
html = render_blur(view, "blur")
html = render_focus(view, "focus")
html = render_hook(view, "hook-event", %{data: "value"})

# Async
html = render_async(view)
html = render_async(view, timeout: 5000)

# Elements
element(view, "#id")
element(view, "button", "Click me")
element(view, "form#user-form")

# Forms
form(view, "#form-id")
form(view, "#form-id", user: %{name: "John"})

# Assertions
assert has_element?(view, "#id")
assert has_element?(view, "#id", "text content")
refute has_element?(view, "#deleted")

# Follow redirect
{:ok, conn} = follow_redirect(result, conn)
{:ok, view, html} = follow_redirect(result, conn, ~p"/expected")

# LiveComponent
{:ok, view, html} = live(conn, ~p"/path")
component = find_live_component(view, "#component-id")
html = render_click(component, "event")

# File uploads
file = file_input(view, "#form", :avatar, [
  %{
    name: "photo.jpg",
    content: File.read!("test/fixtures/photo.jpg"),
    type: "image/jpeg"
  }
])
render_upload(file, "photo.jpg")

# PubSub in tests
Phoenix.PubSub.broadcast(MyApp.PubSub, "topic", {:event, data})
```

## Hook Lifecycle Methods

```javascript
let Hooks = {}

Hooks.MyHook = {
  // Called when element is added to DOM
  mounted() {
    // this.el - the hook element
    // this.pushEvent(event, payload) - send to server
    // this.pushEventTo(selector, event, payload) - send to target
    // this.handleEvent(event, callback) - receive from server
    // this.upload(name, files) - upload files
    // this.uploadTo(selector, name, files) - upload to target
  },

  // Called before element is updated
  beforeUpdate() {},

  // Called after element is updated
  updated() {},

  // Called before element is removed
  beforeDestroy() {},

  // Called when element is removed
  destroyed() {},

  // Called when LiveView disconnects
  disconnected() {},

  // Called when LiveView reconnects
  reconnected() {}
}
```

## Component Communication Patterns

```elixir
# Parent to child: via assigns
<.live_component module={Child} id="child" data={@data} />

# Parent to child: via send_update
send_update(Child, id: "child", data: new_data)

# Child to parent: via callback
# In parent
<.live_component module={Child} id="child" on_save={&handle_save/1} />

def handle_save(data) do
  send(self(), {:child_saved, data})
end

# In child
def handle_event("save", _, socket) do
  socket.assigns.on_save.(socket.assigns.data)
  {:noreply, socket}
end

# Child to parent: via send
# In child
def handle_event("save", _, socket) do
  send(self(), {:child_event, :saved, socket.assigns.data})
  {:noreply, socket}
end

# In parent handle_info
def handle_info({:child_event, :saved, data}, socket) do
  {:noreply, assign(socket, data: data)}
end
```

## Common Event Parameter Shapes

| Event | Parameter Shape |
|-------|----------------|
| `phx-click` | `%{}` or `%{"value" => "..."}` with `phx-value-*` |
| `phx-click` with values | `%{"id" => "123", "action" => "delete"}` |
| `phx-change` on form | `%{"form_name" => %{"field" => "value"}}` |
| `phx-submit` on form | `%{"form_name" => %{"field" => "value"}}` |
| `phx-keydown` | `%{"key" => "Enter", "value" => "..."}` |
| `phx-blur` | `%{"value" => "current_value"}` |
| JS hook `pushEvent` | Whatever JS sends (object becomes map) |

## Socket Return Values

```elixir
# mount/3
{:ok, socket}
{:ok, socket, temporary_assigns: [items: []]}
{:ok, socket, layout: {MyAppWeb.Layouts, :other}}

# handle_params/3
{:noreply, socket}

# handle_event/3
{:noreply, socket}
{:reply, %{result: "ok"}, socket}  # Reply to client

# handle_info/2
{:noreply, socket}

# handle_async/3
{:noreply, socket}
```

## Navigation Functions

```elixir
# Server-side navigation
push_navigate(socket, to: ~p"/path")
push_navigate(socket, to: ~p"/path", replace: true)

push_patch(socket, to: ~p"/path")
push_patch(socket, to: ~p"/path", replace: true)

redirect(socket, to: ~p"/path")
redirect(socket, external: "https://example.com")

# Template navigation
<.link navigate={~p"/path"}>Navigate</.link>  # Different LiveView
<.link patch={~p"/path"}>Patch</.link>        # Same LiveView
<.link href={~p"/path"}>Regular</.link>       # Full page load
```

## Flash Messages

```elixir
# Set flash
put_flash(socket, :info, "Success!")
put_flash(socket, :error, "Something went wrong")

# Clear flash
clear_flash(socket)
clear_flash(socket, :info)

# In template (via core_components)
<.flash_group flash={@flash} />
```
