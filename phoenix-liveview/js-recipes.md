# LiveView JavaScript Recipes — Common Third-Party Widgets

Worked hook patterns for the libraries that recur in real LiveView
projects. Each recipe is opinionated about the shape that survives
contact with `mounted/updated/destroyed`, `phx-update="ignore"`, and
hot reloads in dev.

> Companion to the **JavaScript Interop** section in `SKILL.md`.
> Read that first for the hook lifecycle, methods, and the basic
> `phx-update="ignore"` decision.

## Routing — which recipe do I need?

| You want to render… | Recipe |
|---|---|
| Embedded PDF, page-by-page in canvas | [pdf.js](#pdfjs) |
| Line/bar/pie/scatter chart with live updates | [Chart.js](#chartjs) |
| Full IDE-style code editor (autocomplete, themes, ~3 MB bundle) | [Monaco Editor](#monaco-editor) |
| Lightweight code editor (~100 KB bundle, modular extensions) | [CodeMirror 6](#codemirror-6) |
| Interactive map with markers + tile layers | [Leaflet](#leaflet) |

## Conventions used in every recipe

- `assets/package.json` for npm deps + `assets/vendor/` for hand-vendored libs.
- `esbuild` (the Phoenix default since 1.6) or `Vite` — recipes work with
  both; the import lines are the only difference.
- HEEx wires data via JSON-encoded `data-*` attributes on the hook
  element. Server-to-client commands go via `push_event/3`.
- The hook decides whether `updated()` should respond to attribute
  changes (typical for "data updates") or whether the element is
  `phx-update="ignore"` and the hook owns the DOM completely (typical
  for editors and maps).

---

## pdf.js

[mozilla/pdf.js](https://mozilla.github.io/pdf.js/) renders PDF files
to canvas. The dominant pitfall: pdf.js needs a **worker script URL**
set globally before any document loads, or every call throws.

```bash
cd assets && npm install pdfjs-dist
```

```javascript
// assets/js/hooks/pdf_viewer.js
import * as pdfjsLib from "pdfjs-dist"
// Worker bundle — esbuild copies this; with Vite use `?url` suffix.
import workerSrc from "pdfjs-dist/build/pdf.worker.mjs?url"

// One-time global setup. Without this, pdfjsLib.getDocument throws
// "Setting up fake worker failed" on every call.
pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc

export const PdfViewer = {
  async mounted() {
    this.canvas = this.el.querySelector("canvas")
    this.url = this.el.dataset.url
    this.page = parseInt(this.el.dataset.page || "1", 10)
    this.renderTask = null
    this.pdf = await pdfjsLib.getDocument(this.url).promise
    await this.renderPage(this.page)

    // Server-initiated page change (e.g., user clicks Next button).
    this.handleEvent("pdf:goto", ({ page }) => this.renderPage(page))
  },

  async renderPage(num) {
    // Cancel any in-flight render — switching pages fast otherwise
    // races two renders against the same canvas and produces tears.
    if (this.renderTask) this.renderTask.cancel()

    const page = await this.pdf.getPage(num)
    const viewport = page.getViewport({ scale: 1.5 })
    this.canvas.width = viewport.width
    this.canvas.height = viewport.height

    this.renderTask = page.render({
      canvasContext: this.canvas.getContext("2d"),
      viewport
    })
    try { await this.renderTask.promise } catch (e) {
      if (e?.name !== "RenderingCancelledException") throw e
    }
    this.renderTask = null
    this.pushEvent("pdf:rendered", { page: num })
  },

  // When data-url changes (different PDF), reload. When data-page changes,
  // re-render. data-* attribute changes always trigger updated().
  async updated() {
    const newUrl = this.el.dataset.url
    const newPage = parseInt(this.el.dataset.page, 10)
    if (newUrl !== this.url) {
      this.url = newUrl
      this.pdf?.destroy()
      this.pdf = await pdfjsLib.getDocument(newUrl).promise
    }
    if (newPage !== this.page || newUrl !== this.url) {
      this.page = newPage
      await this.renderPage(newPage)
    }
  },

  destroyed() {
    this.renderTask?.cancel()
    this.pdf?.destroy()
  }
}
```

```heex
<div id={"pdf-#{@document.id}"} phx-hook="PdfViewer"
     data-url={@document.url}
     data-page={@current_page}>
  <canvas></canvas>
</div>

<button phx-click="next_page">Next</button>
```

```elixir
def handle_event("next_page", _, socket) do
  next = socket.assigns.current_page + 1
  {:noreply, assign(socket, current_page: next)}
end
```

**Pitfalls:**

- **NEVER skip `GlobalWorkerOptions.workerSrc`** — without it, pdf.js falls
  back to a fake worker that's gated behind a runtime check and throws.
  Set it once at module load, NOT inside `mounted()` (cheap but redundant
  if multiple hooks instantiate).
- **NEVER call `page.render` without cancelling the prior `renderTask`** —
  fast page navigation otherwise interleaves canvas draws and the output
  is corrupted. The `RenderingCancelledException` swallow above is
  intentional and documented in pdf.js's own examples.

---

## Chart.js

[chartjs/Chart.js](https://www.chartjs.org/) is the easiest "make a chart
fast" library. The dominant pitfall: changing **chart type** at runtime
requires `destroy()` + new constructor — you can't mutate `chart.config.type`.

```bash
cd assets && npm install chart.js
```

```javascript
// assets/js/hooks/chart.js
import { Chart, registerables } from "chart.js"
Chart.register(...registerables)

export const ChartHook = {
  mounted() {
    this.type = this.el.dataset.type || "line"
    this.chart = new Chart(this.el, {
      type: this.type,
      data: JSON.parse(this.el.dataset.data),
      options: JSON.parse(this.el.dataset.options || "{}")
    })

    // Surgical append for real-time series — much cheaper than full reload.
    this.handleEvent("chart:append", ({ label, values }) => {
      this.chart.data.labels.push(label)
      this.chart.data.datasets.forEach((ds, i) => ds.data.push(values[i]))
      this.chart.update("none") // skip animation on streaming data
    })
  },

  updated() {
    const newType = this.el.dataset.type || "line"
    const newData = JSON.parse(this.el.dataset.data)

    // Chart type change requires destroy + recreate — Chart.js doesn't
    // support live type swap. Animation off because the data is the
    // same conceptually, just a different visualization.
    if (newType !== this.type) {
      this.chart.destroy()
      this.type = newType
      this.chart = new Chart(this.el, {
        type: newType,
        data: newData,
        options: JSON.parse(this.el.dataset.options || "{}")
      })
      return
    }

    // Otherwise just update data in place.
    this.chart.data = newData
    this.chart.update("none")
  },

  destroyed() {
    this.chart?.destroy()
  }
}
```

```heex
<canvas id={"chart-#{@id}"} phx-hook="ChartHook"
        data-type={@chart_type}
        data-data={Jason.encode!(@chart_data)}
        data-options={Jason.encode!(@chart_options)}></canvas>
```

```elixir
# Real-time tick from PubSub or a Telemetry handler
def handle_info({:metric, label, values}, socket) do
  {:noreply, push_event(socket, "chart:append", %{label: label, values: values})}
end
```

**Pitfalls:**

- **NEVER call `chart.update()` without `"none"` for streaming data** —
  the default animation re-runs on every tick and turns a smooth chart
  into a strobing one. The `"none"` mode flag is documented in Chart.js
  and saves both CPU and visual quality.
- **NEVER use `phx-update="ignore"` here** — we WANT `updated()` to
  fire when `data-data` changes from the server. The hook owns the
  canvas's contents, but LiveView owns the `data-*` attributes.

---

## Monaco Editor

[microsoft/monaco-editor](https://microsoft.github.io/monaco-editor/) is
VS Code's editor extracted as a library. Powerful but heavy (~3 MB
bundle); lazy-load via the AMD loader to keep initial page weight down.

```bash
cd assets && npm install monaco-editor
```

```javascript
// assets/js/hooks/monaco.js
// Lazy-loaded — first MonacoEditor mount triggers AMD load.
let loaderPromise = null

function loadMonaco() {
  if (loaderPromise) return loaderPromise
  loaderPromise = new Promise((resolve) => {
    const script = document.createElement("script")
    script.src = "/vendor/monaco/vs/loader.js"
    script.onload = () => {
      window.require.config({ paths: { vs: "/vendor/monaco/vs" } })
      window.require(["vs/editor/editor.main"], () => resolve(window.monaco))
    }
    document.head.appendChild(script)
  })
  return loaderPromise
}

export const MonacoEditor = {
  async mounted() {
    const monaco = await loadMonaco()
    this.suppressNextChange = false

    this.editor = monaco.editor.create(this.el, {
      value: this.el.dataset.value || "",
      language: this.el.dataset.language || "elixir",
      theme: this.el.dataset.theme || "vs-dark",
      automaticLayout: true,
      minimap: { enabled: false }
    })

    // Debounce client→server updates — every keystroke would flood the WS.
    let timer = null
    this.editor.onDidChangeModelContent(() => {
      if (this.suppressNextChange) {
        this.suppressNextChange = false
        return
      }
      clearTimeout(timer)
      timer = setTimeout(() => {
        this.pushEvent("editor:changed", { value: this.editor.getValue() })
      }, 300)
    })

    this.handleEvent("editor:set_value", ({ value }) => {
      // Suppress the change event we're about to cause — otherwise
      // the server's set_value bounces back via onDidChangeModelContent
      // and we get an echo loop.
      this.suppressNextChange = true
      this.editor.setValue(value)
    })
  },

  updated() {
    // Theme/language changes via data-* attrs without touching content.
    const monaco = window.monaco
    if (!monaco || !this.editor) return
    const newTheme = this.el.dataset.theme
    const newLang = this.el.dataset.language
    if (newTheme && newTheme !== this._lastTheme) {
      monaco.editor.setTheme(newTheme)
      this._lastTheme = newTheme
    }
    const model = this.editor.getModel()
    if (newLang && model && model.getLanguageId() !== newLang) {
      monaco.editor.setModelLanguage(model, newLang)
    }
  },

  destroyed() {
    this.editor?.dispose()
  }
}
```

```heex
<div id="editor" phx-hook="MonacoEditor" phx-update="ignore"
     class="h-96 border"
     data-value={@code}
     data-language={@language}
     data-theme={@theme}></div>
```

```elixir
def handle_event("editor:changed", %{"value" => v}, socket) do
  # Persist or validate — don't push back what we just received.
  {:noreply, assign(socket, code: v)}
end

def handle_event("toggle_theme", _, socket) do
  new_theme = if socket.assigns.theme == "vs-dark", do: "vs", else: "vs-dark"
  {:noreply, assign(socket, theme: new_theme)}
end
```

**Pitfalls:**

- **ALWAYS `phx-update="ignore"`** for the editor element — the editor
  manages its own children. Without `ignore`, LiveView will obliterate
  the editor DOM on any parent re-render.
- **NEVER push server→client `set_value` without the suppression flag** —
  it triggers `onDidChangeModelContent`, which fires `editor:changed`,
  which sends back the same value — an infinite loop. The
  `suppressNextChange` flag breaks the cycle.
- **ALWAYS host the Monaco bundle yourself** (under `/priv/static/vendor/monaco/`)
  rather than loading from a CDN. Monaco's workers must come from the
  same origin or COEP/COOP headers break them.

---

## CodeMirror 6

[codemirror/dev](https://codemirror.net/) is the modern, modular code
editor. ~100 KB bundle, plugin-architected via "extensions." When you
need read-only / language / theme to change at runtime, use a
`Compartment` so you can `reconfigure` without rebuilding the state.

```bash
cd assets && npm install @codemirror/state @codemirror/view \
  @codemirror/language @codemirror/lang-javascript @codemirror/commands
```

```javascript
// assets/js/hooks/codemirror.js
import { EditorState, Compartment } from "@codemirror/state"
import { EditorView, keymap } from "@codemirror/view"
import { defaultKeymap } from "@codemirror/commands"
import { javascript } from "@codemirror/lang-javascript"

export const CodeMirrorHook = {
  mounted() {
    this.language = new Compartment()
    this.readonly = new Compartment()
    this.suppressNextChange = false

    const updateListener = EditorView.updateListener.of((u) => {
      if (!u.docChanged) return
      if (this.suppressNextChange) { this.suppressNextChange = false; return }
      // Debounce — same reasoning as Monaco.
      clearTimeout(this._t)
      this._t = setTimeout(() => {
        this.pushEvent("editor:changed", {
          value: u.state.doc.toString()
        })
      }, 300)
    })

    this.view = new EditorView({
      state: EditorState.create({
        doc: this.el.dataset.value || "",
        extensions: [
          keymap.of(defaultKeymap),
          this.language.of(javascript()),
          this.readonly.of(EditorState.readOnly.of(this.el.dataset.readonly === "true")),
          updateListener
        ]
      }),
      parent: this.el
    })

    this.handleEvent("editor:set_value", ({ value }) => {
      this.suppressNextChange = true
      this.view.dispatch({
        changes: { from: 0, to: this.view.state.doc.length, insert: value }
      })
    })
  },

  updated() {
    const ro = this.el.dataset.readonly === "true"
    this.view.dispatch({
      effects: this.readonly.reconfigure(EditorState.readOnly.of(ro))
    })
    // If you support language switching, do the same dance with
    // this.language.reconfigure(...) using the right language pack.
  },

  destroyed() {
    this.view?.destroy()
  }
}
```

```heex
<div id="cm-editor" phx-hook="CodeMirrorHook" phx-update="ignore"
     data-value={@code}
     data-readonly={to_string(@readonly)}></div>
```

**Pitfalls:**

- **NEVER reconfigure an extension by replacing the whole `EditorState`** —
  the user's cursor and selection are lost. Use `Compartment.reconfigure`
  via `view.dispatch({ effects: ... })` instead.
- **NEVER include `EditorView.lineWrapping` or other heavy extensions
  conditionally inside `updated()`** without a Compartment — every
  reconfiguration without a Compartment requires `setState`, which
  defeats the editor's diffing.

---

## Leaflet

[leaflet/Leaflet](https://leafletjs.com/) is the canonical interactive
map. The dominant pitfall: the default marker icons 404 in production
builds because they're loaded as relative URLs from `dist/images/`. The
fix is a one-time mergeOptions block at module load.

```bash
cd assets && npm install leaflet
```

```javascript
// assets/js/hooks/leaflet_map.js
import L from "leaflet"
import "leaflet/dist/leaflet.css"
// Webpack/esbuild/Vite all resolve these to URLs:
import iconRetina from "leaflet/dist/images/marker-icon-2x.png"
import icon from "leaflet/dist/images/marker-icon.png"
import shadow from "leaflet/dist/images/marker-shadow.png"

// One-time fix — without this, every marker shows as a broken-image
// icon in production. Leaflet's defaults assume bundler resolves
// `dist/images/*` relative to the script, which is rarely true.
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: iconRetina,
  iconUrl: icon,
  shadowUrl: shadow
})

export const LeafletMap = {
  mounted() {
    const center = JSON.parse(this.el.dataset.center || "[0,0]")
    const zoom = parseInt(this.el.dataset.zoom || "13", 10)

    this.map = L.map(this.el).setView(center, zoom)

    // OSM tiles — required attribution per their TOS.
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19
    }).addTo(this.map)

    this.markerLayer = L.featureGroup().addTo(this.map)
    this.renderMarkers()

    this.handleEvent("map:fly_to", ({ lat, lng, zoom }) => {
      this.map.flyTo([lat, lng], zoom || this.map.getZoom())
    })
  },

  renderMarkers() {
    this.markerLayer.clearLayers()
    const markers = JSON.parse(this.el.dataset.markers || "[]")
    markers.forEach((m) => {
      const marker = L.marker([m.lat, m.lng]).addTo(this.markerLayer)
      if (m.popup) marker.bindPopup(m.popup)
      marker.on("click", () => this.pushEvent("marker:clicked", { id: m.id }))
    })

    // Fit bounds if there are markers and the user hasn't manually zoomed.
    if (markers.length > 0) {
      this.map.fitBounds(this.markerLayer.getBounds(), { padding: [40, 40] })
    }
  },

  updated() {
    this.renderMarkers()
  },

  destroyed() {
    this.map?.remove()
  }
}
```

```heex
<div id="map" phx-hook="LeafletMap" phx-update="ignore"
     class="h-96 w-full"
     data-center={Jason.encode!([@center.lat, @center.lng])}
     data-zoom={@zoom}
     data-markers={Jason.encode!(@markers)}></div>
```

```elixir
def handle_event("marker:clicked", %{"id" => id}, socket) do
  {:noreply, assign(socket, selected: id)}
end
```

**Pitfalls:**

- **ALWAYS do the `L.Icon.Default.mergeOptions` fix at module load** —
  the marker-icon 404 is the #1 Leaflet+bundler issue and silently
  ships in `mix phx.gen.release` builds without anyone noticing
  until production opens the map.
- **ALWAYS keep the OSM attribution** (or your tile provider's) — it's
  required by the tile provider's TOS and Leaflet adds an attribution
  control by default; removing it violates the agreement.
- **NEVER call `L.map(this.el)` twice** without `map.remove()` first —
  Leaflet stores the map instance on the DOM node and the second
  initialization throws "Map container is already initialized."
  `destroyed()` handles this; if you reuse the element in `updated()`,
  remove first.

---

## When none of these fit

The recipes share a shape that generalises:

1. **`mounted()`**: read `data-*` attrs, construct the widget, register
   server→client event handlers.
2. **`updated()`**: when the widget supports surgical updates, marshal
   `data-*` changes into widget API calls. When it doesn't, either
   `destroy + recreate` or use `phx-update="ignore"` and drive the
   widget entirely via `push_event/3`.
3. **`destroyed()`**: dispose the widget's resources (canvas contexts,
   WebGL contexts, web workers, RAF loops, observers).

For widgets that own their DOM completely (editors, maps), use
`phx-update="ignore"` and drive via events. For widgets where the
server-rendered HTML is the source of truth (charts where data lives in
`data-*`), let `updated()` fire and the hook reacts.

For very large bundles (>1 MB), lazy-load via dynamic `import()` inside
`mounted()` so the cost is only paid on the first page that uses the
widget — not on every LiveView page load.
