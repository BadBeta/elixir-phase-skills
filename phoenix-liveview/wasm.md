# WebAssembly Integration with Phoenix LiveView

Run compute-intensive, privacy-sensitive, or offline-capable logic client-side using WebAssembly modules coordinated through LiveView hooks.

## Use Cases

| Use Case | Why WASM | Example |
|----------|----------|---------|
| Compute offload | Move CPU-intensive work to browser, keep server idle | Image processing, route calculation, encryption |
| Privacy by architecture | Data never leaves browser | Client-side PII processing, local analytics |
| Offline-first features | WASM runs without server connection | PWA calculations, offline form validation |
| Rich text editing | Sub-millisecond response times | Collaborative editors, syntax highlighting |
| Real-time visualization | High-frequency data processing | Audio visualization, signal processing |

## Approach 1: Exclosured (Rust → WASM → LiveView)

The most mature community solution. Compiles Rust to WASM with automatic LiveView integration.

### Setup

```elixir
# mix.exs
defp deps do
  [{:exclosured, "~> 0.1"}]
end
```

### Inline Rust with ~RUST Sigil

```elixir
defmodule MyAppWeb.ImageProcessorLive do
  use MyAppWeb, :live_view
  use Exclosured

  # Rust code compiled to WASM, runs in browser
  ~RUST"""
  use exclosured::prelude::*;

  #[wasm_bindgen]
  pub fn apply_filter(image_data: &[u8], filter_type: &str) -> Vec<u8> {
      match filter_type {
          "grayscale" => grayscale(image_data),
          "blur" => gaussian_blur(image_data, 3.0),
          _ => image_data.to_vec(),
      }
  }
  """

  def mount(_params, _session, socket) do
    {:ok, assign(socket, filter: "none", processing: false)}
  end

  def handle_event("apply-filter", %{"filter" => filter}, socket) do
    # WASM processes client-side, emits result back
    {:noreply, assign(socket, filter: filter)}
  end
end
```

### Key Features

- **Fallback behavior**: If WASM fails to load, same function runs as pure Elixir
- **Automatic sync**: LiveView assigns flow to WASM modules automatically
- **Event emission**: `emit()` sends events from WASM back to LiveView
- **Data stays local**: WASM linear memory — data never reaches server
- **Incremental chunks**: Generates chunks that LiveView accumulates

## Approach 2: Manual Hook + WASM Module

For custom WASM modules without Exclosured:

### JavaScript Hook

```javascript
Hooks.WasmProcessor = {
  async mounted() {
    // Load and instantiate WASM module
    const response = await fetch("/wasm/processor.wasm")
    const bytes = await response.arrayBuffer()
    const { instance } = await WebAssembly.instantiate(bytes, {
      env: {
        // Import functions WASM can call
        notify_progress: (percent) => {
          this.pushEvent("wasm-progress", { percent })
        }
      }
    })
    this.wasm = instance.exports

    // Listen for server events
    this.handleEvent("process", ({ data }) => {
      const result = this.wasm.process(data)
      this.pushEvent("wasm-result", { result })
    })
  },

  destroyed() {
    this.wasm = null
  }
}
```

### LiveView

```elixir
def mount(_params, _session, socket) do
  {:ok, assign(socket, result: nil, progress: 0)}
end

def handle_event("start-processing", %{"data" => data}, socket) do
  {:noreply, push_event(socket, "process", %{data: data})}
end

def handle_event("wasm-progress", %{"percent" => percent}, socket) do
  {:noreply, assign(socket, progress: percent)}
end

def handle_event("wasm-result", %{"result" => result}, socket) do
  {:noreply, assign(socket, result: result, progress: 100)}
end
```

### Template

```heex
<div id="wasm-processor" phx-hook="WasmProcessor">
  <button phx-click="start-processing" phx-value-data={@input_data}>
    Process Client-Side
  </button>

  <progress :if={@progress > 0} value={@progress} max="100">
    {@progress}%
  </progress>

  <div :if={@result}>Result: {@result}</div>
</div>
```

### Memory Management

WASM modules manage their own memory. For passing complex data:

```javascript
// Allocate memory in WASM, copy data in, process, free
const ptr = this.wasm.alloc(data.length)
const mem = new Uint8Array(this.wasm.memory.buffer, ptr, data.length)
mem.set(new Uint8Array(data))

const resultPtr = this.wasm.process(ptr, data.length)
// Read result from WASM memory
const result = new Uint8Array(this.wasm.memory.buffer, resultPtr, resultLength)

this.wasm.dealloc(ptr, data.length)
this.wasm.dealloc(resultPtr, resultLength)
```

## Approach 3: Orb (Elixir → WASM)

Write WebAssembly directly in Elixir — experimental/alpha but promising for pure-Elixir shops.

```elixir
defmodule Calculator do
  use Orb

  defw add(a: I32, b: I32), I32 do
    a + b
  end

  defw fibonacci(n: I32), I32 do
    if I32.le_u(n, 1) do
      n
    else
      call(:fibonacci, n - 1) + call(:fibonacci, n - 2)
    end
  end
end

# Compile to WAT/WASM
wat = Orb.to_wat(Calculator)
```

**Status**: Alpha. Compiles to WAT text format. Produces tiny kilobyte-sized executables. Composable modules publishable to Hex. Worth monitoring as it matures.

## When to Use WASM vs Server-Side

| Factor | Server-side (LiveView) | Client-side (WASM) |
|--------|----------------------|-------------------|
| Data sensitivity | Data already on server | PII, private data |
| Compute cost | Light processing | Heavy (image, crypto, ML) |
| Latency requirement | ~50ms roundtrip OK | Sub-millisecond needed |
| Offline requirement | Always online | Must work offline |
| Complexity | Simple | Worth the build toolchain overhead |

## Serving WASM Files

```elixir
# In endpoint.ex — serve .wasm files with correct MIME type
plug Plug.Static,
  at: "/wasm",
  from: {:my_app, "priv/static/wasm"},
  gzip: true,
  headers: %{"content-type" => "application/wasm"}
```

## Related

- **[rust-wasm](../../rust-wasm/SKILL.md)** — Rust WebAssembly development patterns, build toolchain, wasm-bindgen
- **[rust-nif](../../rust-nif/SKILL.md)** — Alternative: run Rust on server via NIFs instead of client via WASM
