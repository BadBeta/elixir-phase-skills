# Phoenix LiveView Wire Protocol

Technical reference for the LiveView wire protocol — Socket V2 envelope, rendered tree internals, diff format, event taxonomy, JS-command encoding, uploads, streams, and navigation. For implementers building alternative clients, debugging at the wire level, or understanding LiveView's internal architecture.

**Source files** (phoenixframework/phoenix_live_view):
- Server: `channel.ex`, `diff.ex`, `engine.ex`, `js.ex`, `live_stream.ex`, `static.ex`, `upload_config.ex`
- Client: `view.js`, `rendered.js`, `js.js`, `constants.js`, `serializer.js`

---

## 1. Socket V2 Envelope

Messages are **5-element JSON arrays** (V2) instead of named-field objects (V1):

```
[join_ref, ref, topic, event, payload]
```

| Field | Type | Purpose |
|---|---|---|
| `join_ref` | string/null | Channel join session ID. Null for server-initiated |
| `ref` | string/null | Monotonic message ref for request/reply correlation |
| `topic` | string | Channel topic, e.g. `"lv:phx-FgK..."` |
| `event` | string | Event name |
| `payload` | object | Event-specific data |

### Message kinds

**Client → Server (push):**
```json
["1", "4", "lv:phx-FgK...", "event", {"event": "increment", "type": "click", "value": {}, "cid": null}]
```

**Server → Client (reply):**
```json
["1", "4", "lv:phx-FgK...", "phx_reply", {"status": "ok", "response": {"diff": {...}}}]
```

**Server → Client (broadcast, no ref):**
```json
[null, null, "lv:phx-FgK...", "diff", {diff_payload}]
```

### Binary wire format (optional)

1-byte length prefixes, kind byte first: `0` = push, `1` = reply, `2` = broadcast.

```
Push:      [0][join_ref_len][topic_len][event_len][join_ref][topic][event][payload_bytes]
Reply:     [1][join_ref_len][ref_len][topic_len][status_len][join_ref][ref][topic][status][payload_bytes]
Broadcast: [2][topic_len][event_len][topic][event][payload_bytes]
```

Field lengths capped at 255 bytes.

---

## 2. Rendered Tree

### The `%Rendered{}` struct

```elixir
%Phoenix.LiveView.Rendered{
  static: [String.t()],                # Literal HTML strings (compile-time)
  dynamic: (boolean() -> [dyn()]),      # Function returning dynamic parts (runtime)
  fingerprint: integer(),               # MD5-based template identity hash
  root: boolean() | nil,
  caller: :not_available | {module, ...}
}
```

Where `dyn()` = `nil | iodata | %Rendered{} | %Comprehension{} | component_ref`

### Statics/dynamics split

At compile time, HEEx splits templates into alternating static/dynamic segments:

```elixir
# Template: <div class="<%= @class %>"><%= @content %></div>
%Rendered{
  static: ["<div class=\"", "\">", "</div>"],    # N+1 strings
  dynamic: fn _track? -> [@class, @content] end, # N values
  fingerprint: 823749283
}
```

Reconstruction: `static[0] <> dynamic[0] <> static[1] <> dynamic[1] <> static[2]`

Statics are **always one element longer** than dynamics.

### Fingerprints

Computed at compile time: `:erlang.md5(term_to_binary({block_ast, statics}))` → integer. Uniquely identifies a template shape. When a conditional renders a different template, the fingerprint changes, signaling the diff engine to send full statics (not just dynamics).

### The `%Comprehension{}` struct (for loops)

```elixir
%Phoenix.LiveView.Comprehension{
  static: [String.t()] | non_neg_integer(),  # Shared statics or template ref
  entries: [{key, map, keyed_render_fun}],
  fingerprint: term(),
  has_key?: boolean(),
  stream: [ref, inserts, deletes, reset?] | nil
}
```

Static template sent **once** regardless of list size — only per-item dynamics transmitted.

---

## 3. Diff Format

### Key map

| Key | JSON | Type | Purpose |
|---|---|---|---|
| `:s` | `"s"` | int / [string] | Static template ref (int) or literal statics list |
| `:c` | `"c"` | map | Component diffs keyed by CID |
| `:k` | `"k"` | map | Keyed collection items (comprehensions) |
| `:kc` | `"kc"` | int | Total keyed item count |
| `:e` | `"e"` | list | Pushed events (server → client) |
| `:r` | `"r"` | term | Reply value |
| `:t` | `"t"` | string | Page title update |
| `:p` | `"p"` | map | Template storage (shared static fragments) |
| `:stream` | `"stream"` | list | Stream metadata `[ref, inserts, deletes, reset?]` |
| `0`, `1`, ... | `"0"`, `"1"` | any | Dynamic content at position N |

### Initial full render

```json
{
  "s": ["<div>", "<span>", "</span></div>"],
  "0": "Hello",
  "1": "World"
}
```

### Subsequent diff (only changed dynamics)

```json
{"0": "Goodbye"}
```

No `"s"` key = statics unchanged (fingerprint matched).

### Template deduplication

```json
{
  "p": {
    "0": ["<li>", "</li>"],
    "1": ["<div class=\"card\">", "</div>"]
  }
}
```

Then references: `{"s": 0, "0": "content"}` — `"s": 0` points to `"p"["0"]`.

### Component diffs

```json
{
  "c": {
    "1": {"s": ["<button>", "</button>"], "0": "Click me"},
    "2": {"0": "Updated text only"}
  }
}
```

**Negative `"s"` = static reuse** across components: `{"s": -2, "0": "First"}` reuses CID 2's statics.

### Diff merging rules (client-side)

1. `diff["s"]` exists → **replace** entire subtree (new template shape)
2. Otherwise → **deep merge** recursively (new values overwrite old)
3. Component diffs merge by CID into the components map

---

## 4. Component IDs (CIDs)

**CIDs** are monotonically increasing integers starting from 1. Each stateful `live_component` gets a unique CID.

Server maintains: `{cid_to_component, id_to_cid, next_uuid}`

### DOM identification

- Component: `data-phx-component="{cid}"`, magic ID `c{cid}-{viewId}`
- Root LiveView: `data-phx-main="true"`, `data-phx-session`, `data-phx-static`
- Nested LiveView: `data-phx-parent-id`, `data-phx-session`

### Component lifecycle on wire

```
Client → Server: "cids_will_destroy"  {cids: [1, 2, 3]}
Client → Server: "cids_destroyed"     {cids: [1, 2, 3]}
```

Two-phase deletion prevents accidental removal if a component reappears between messages.

---

## 5. Event Taxonomy

Every user event:
```json
["join_ref", "ref", "topic", "event", {
  "type": "<type>",
  "event": "<phx-event-name>",
  "value": { ... },
  "cid": <integer|null>
}]
```

| Attribute | Wire `type` | Value content |
|---|---|---|
| `phx-click` | `"click"` | `phx-value-*` attributes merged |
| `phx-submit` | `"form"` | Serialized form data string |
| `phx-change` | `"form"` | Serialized form data + `_target` in meta |
| `phx-blur` | `"blur"` | `phx-value-*` attributes |
| `phx-focus` | `"focus"` | `phx-value-*` attributes |
| `phx-keydown` | `"keydown"` | `{key: "Enter", ...}` + `phx-value-*` |
| `phx-keyup` | `"keyup"` | `{key: "Escape", ...}` + `phx-value-*` |
| `phx-hook` | `"hook"` | Custom payload from `this.pushEvent()` |
| `phx-window-*` | Same as non-window | Window-level listener variant |

### Form events

```json
{
  "type": "form",
  "event": "validate",
  "value": "name=John&email=j%40example.com",
  "meta": {"_target": "user[name]"},
  "uploads": { ... },
  "cid": 5
}
```

### Targeting

- `phx-target="#id"` → CSS selector
- `phx-target={@myself}` → sends component CID integer

### Reply format

```json
["join_ref", "ref", "topic", "phx_reply", {
  "status": "ok",
  "response": {
    "diff": { ... },
    "e": [["event_name", {"key": "value"}]],
    "r": "reply_value",
    "t": "New Page Title"
  }
}]
```

### Loading CSS classes

Applied during event round-trip: `phx-click-loading`, `phx-change-loading`, `phx-submit-loading`, `phx-keydown-loading`, `phx-keyup-loading`, `phx-blur-loading`, `phx-focus-loading`, `phx-hook-loading`.

---

## 6. JS Command Encoding

### The `%JS{}` struct

```elixir
%Phoenix.LiveView.JS{ops: [["command", %{args}], ...]}
```

Serialized to JSON in DOM attributes:
```html
<button phx-click='[["push",{"event":"inc"}],["toggle",{"to":"#modal"}]]'>
```

### Command catalog

| Command | Wire encoding |
|---|---|
| `JS.push("event")` | `["push", %{event, target, loading, page_loading, value}]` |
| `JS.show(to: "#el")` | `["show", %{to, display, transition: [cls, start, end], time, blocking}]` |
| `JS.hide(to: "#el")` | `["hide", %{to, transition, time, blocking}]` |
| `JS.toggle(to: "#el")` | `["toggle", %{to, display, ins: [...], outs: [...], time, blocking}]` |
| `JS.add_class("x")` | `["add_class", %{to, names: ["x"], transition, time, blocking}]` |
| `JS.remove_class("x")` | `["remove_class", %{to, names: ["x"], transition, time}]` |
| `JS.toggle_class("x")` | `["toggle_class", %{to, names: ["x"], transition, time}]` |
| `JS.transition("fade")` | `["transition", %{to, transition: [["fade"], [], []], time, blocking}]` |
| `JS.dispatch("click")` | `["dispatch", %{event, to, detail, bubbles, blocking}]` |
| `JS.navigate("/path")` | `["navigate", %{href, replace}]` |
| `JS.patch("/path")` | `["patch", %{href, replace}]` |
| `JS.focus(to: "#el")` | `["focus", %{to}]` |
| `JS.focus_first(to: "#el")` | `["focus_first", %{to}]` |
| `JS.push_focus()` | `["push_focus", %{to}]` |
| `JS.pop_focus()` | `["pop_focus", %{}]` |
| `JS.set_attribute({"k","v"})` | `["set_attr", %{to, attr: ["k", "v"]}]` |
| `JS.remove_attribute("k")` | `["remove_attr", %{to, attr: "k"}]` |
| `JS.toggle_attribute({"k","t","f"})` | `["toggle_attr", %{to, attr: ["k", "t", "f"]}]` |
| `JS.exec("phx-remove")` | `["exec", %{attr, to}]` |

### Selector scoping

```elixir
JS.show(to: {:inner, ".child"})     # Within interacted element
JS.show(to: {:closest, ".parent"})  # Closest ancestor
JS.show(to: "#specific")            # Standard CSS selector
```

### Transition format

Normalizes to `[[transition_classes], [start_classes], [end_classes]]`:
```elixir
JS.show(transition: {"fade-in", "opacity-0", "opacity-100"})
# → [["fade-in"], ["opacity-0"], ["opacity-100"]]
```

### Chaining

Pipe appends to `ops` list — client executes sequentially without server round-trips (except `push`):
```elixir
JS.push("open") |> JS.show(to: "#modal") |> JS.add_class("active", to: "#bg")
```

---

## 7. Upload Protocol

### Preflight

```json
["1", "5", "topic", "allow_upload", {
  "ref": "phx-upload-ref-0",
  "entries": [{"ref": "0", "name": "photo.jpg", "type": "image/jpeg", "size": 524288}],
  "cid": 5
}]
```

Reply includes config: `max_file_size`, `chunk_timeout`, `writer` module.

### Progress

```json
["1", "6", "topic", "progress", {
  "event": "progress_event",
  "ref": "phx-upload-ref-0",
  "entry_ref": "0",
  "progress": 50,
  "cid": 5
}]
```

### Defaults

| Setting | Default |
|---|---|
| `max_file_size` | 8 MB |
| `chunk_size` | 64 KB |
| `chunk_timeout` | 10 s |
| `max_entries` | 1 |

---

## 8. Stream Protocol

Streams are encoded within comprehension diffs:

```json
{
  "stream": ["stream_ref", [[dom_id, position, limit, update_only], ...], [deleted_dom_id, ...], reset?],
  "k": {
    "0": {"0": "item content"},
    "1": {"0": "another item"}
  },
  "kc": 2
}
```

| Field | Purpose |
|---|---|
| `dom_id` | Generated DOM identifier (e.g., `"posts-42"`) |
| `position` | -1 = append, 0 = prepend, N = specific index |
| `limit` | Maximum items (for pruning) |
| `update_only` | Boolean — update existing without insert |
| `reset?` | Clear all existing items first |

---

## 9. Navigation Messages

### live_patch (same LiveView, URL change)

```json
Client: ["1", "7", "topic", "live_patch", {"url": "/posts?page=2"}]
Server: {"status": "ok", "response": {"diff": {...}}}
```

### Server-initiated navigation (in reply)

```json
{"live_redirect": {"to": "/new-path", "kind": "push"}}
{"redirect": {"to": "/login", "flash": {"error": "Not authorized"}}}
```

Kind: `"push"` = `history.pushState`, `"replace"` = `history.replaceState`.

---

## 10. Join Protocol

### Connect parameters

```json
{
  "session": "SFMyNTY...",
  "static": "SFMyNTY...",
  "url": "http://example.com/path",
  "params": {"_csrf_token": "..."},
  "_mounts": 0,
  "_live_referer": "http://example.com/previous"
}
```

### Join response

```json
{
  "rendered": { full_diff_tree },
  "container": ["div", {}],
  "liveview_version": "1.0.0"
}
```

### Dead render → live render

1. HTTP: `mount/3` → `render/1` → full HTML with signed tokens in `data-phx-session`/`data-phx-static`
2. WebSocket: client finds `[data-phx-main]`, sends join with tokens
3. Server validates tokens, re-runs `mount/3` + `handle_params/3`
4. Computes diff between dead render fingerprints and live render
5. Sends only the **differences** — join response is minimal when renders match

Session tokens signed with `Phoenix.Token`, max age 2 weeks.
