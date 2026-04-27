# Saving and Restoring LiveView State

Persist LiveView state in browser storage (survives page refresh, reconnect, server restart) using encrypted tokens.

## Browser Storage Hook

Reusable hook for sessionStorage/localStorage operations:

```javascript
// app.js
Hooks.BrowserStorage = {
  mounted() {
    this.handleEvent("store", (obj) => this.store(obj))
    this.handleEvent("clear", (obj) => this.clear(obj))
    this.handleEvent("restore", (obj) => this.restore(obj))
  },
  store(obj) {
    sessionStorage.setItem(obj.key, obj.data)
  },
  restore(obj) {
    let data = sessionStorage.getItem(obj.key)
    this.pushEvent(obj.event, data)
  },
  clear(obj) {
    sessionStorage.removeItem(obj.key)
  }
}
```

```heex
<div id="state-manager" phx-hook="BrowserStorage"></div>
```

## Encrypted State with Phoenix.Token

Securely store sensitive state client-side:

```elixir
defmodule MyAppWeb.WizardLive do
  use MyAppWeb, :live_view

  @state_salt "wizard_state_v1"
  @max_age 86_400  # 24 hours

  def mount(_params, _session, socket) do
    {:ok, assign(socket, step: 1, form_data: %{})}
  end

  def handle_params(_params, _uri, socket) do
    if connected?(socket), do: send(self(), :restore_state)
    {:noreply, socket}
  end

  def handle_info(:restore_state, socket) do
    {:noreply, push_event(socket, "restore", %{
      key: "wizard_state",
      event: "state_restored"
    })}
  end

  def handle_event("state_restored", nil, socket) do
    {:noreply, socket}
  end

  def handle_event("state_restored", token, socket) when is_binary(token) do
    case Phoenix.Token.decrypt(socket.endpoint, @state_salt, token, max_age: @max_age) do
      {:ok, %{version: 1} = data} ->
        {:noreply, assign(socket, step: data.step, form_data: data.form_data)}
      _ ->
        {:noreply, socket}
    end
  end

  def handle_event("save_progress", _params, socket) do
    state = %{
      version: 1,
      step: socket.assigns.step,
      form_data: socket.assigns.form_data
    }

    token = Phoenix.Token.encrypt(socket.endpoint, @state_salt, state)
    {:noreply, push_event(socket, "store", %{key: "wizard_state", data: token})}
  end

  def handle_event("complete", _params, socket) do
    {:noreply, push_event(socket, "clear", %{key: "wizard_state"})}
  end
end
```

## Optimized: Restore via Connect Params

Eliminate round-trips by sending stored state during the WebSocket handshake:

```javascript
// app.js - params as function, executed at connection time
let liveSocket = new LiveSocket("/live", Socket, {
  params: () => ({
    _csrf_token: csrfToken,
    restore: sessionStorage.getItem("wizard_state")
  })
})
```

```elixir
def mount(_params, _session, socket) do
  socket =
    case get_connect_params(socket) do
      %{"restore" => token} when is_binary(token) ->
        case Phoenix.Token.decrypt(socket.endpoint, @state_salt, token, max_age: @max_age) do
          {:ok, %{version: 1} = data} ->
            assign(socket, step: data.step, form_data: data.form_data)
          _ ->
            assign(socket, step: 1, form_data: %{})
        end
      _ ->
        assign(socket, step: 1, form_data: %{})
    end

  {:ok, socket}
end
```

### Selective Restoration with Data Attributes

Enable restoration only for specific LiveViews using DOM markers:

```heex
<div data-restore-state="true" data-storage-key="wizard_state">...</div>
```

```javascript
let liveSocket = new LiveSocket("/live", Socket, {
  params: (liveViewRoot) => {
    let restoreEl = liveViewRoot?.querySelector("[data-restore-state='true']")
    if (restoreEl) {
      let key = restoreEl.getAttribute("data-storage-key")
      return {_csrf_token: csrfToken, restore: sessionStorage.getItem(key)}
    }
    return {_csrf_token: csrfToken}
  }
})
```

## Comparison

| Approach | Pros | Cons |
|----------|------|------|
| Hook-based | Flexible, can restore anytime | Extra round-trip delay |
| Connect params | Immediate, no round-trip | Only at connection time |

Use connect params for initial state; hooks for mid-session save/restore.

## When to Restore State

| URL-Dependent State | Restore Location |
|---------------------|------------------|
| No (wizard progress, form data) | `mount/3` or `handle_info` |
| Yes (page number, filters) | `handle_params/3` |

## Storage Options

| Storage | Lifetime | Use For |
|---------|----------|---------|
| `sessionStorage` | Until tab closes | Wizard progress, temporary state |
| `localStorage` | Persistent | User preferences, draft data |

## Best Practices

1. **Version your tokens** — Include `version: 1` for future migrations
2. **Set max_age** — Prevent restoring stale state
3. **Encrypt sensitive data** — Phoenix.Token handles this
4. **Check `connected?/1`** — Only restore after WebSocket establishes
5. **Handle missing/invalid gracefully** — Token may be expired or corrupted
6. **Clear on completion** — Remove state when no longer needed
7. **Minimize stored data** — Only persist what can't be easily reconstructed

## What to Store

**Good candidates:** Multi-step form progress, shopping cart, document draft state, user-selected options.

**Avoid storing:** UI state (use URL or JS), frequently-changing data, large datasets, anything easily fetched from database.
