# Alpine.js Integration Subskill

## Overview

Alpine.js is a lightweight (~10KB) JavaScript framework for adding client-side interactivity to server-rendered HTML. It consists of 18 directives, 9 magic properties, and 3 global methods.

**Use with LiveView when:** UI feedback must be < 100ms, or state doesn't need server involvement.

---

## Setup

### Installation

```bash
cd assets && npm install alpinejs
```

### Critical LiveView Configuration

```javascript
// assets/js/app.js
import Alpine from 'alpinejs'

window.Alpine = Alpine
Alpine.start()

let liveSocket = new LiveSocket("/live", Socket, {
  params: { _csrf_token: csrfToken },
  dom: {
    onBeforeElUpdated(from, to) {
      // CRITICAL: Preserve Alpine state during LiveView DOM patches
      if (from._x_dataStack) {
        window.Alpine.clone(from, to)
      }
    }
  }
})
```

### Prevent Content Flash

```css
/* In app.css */
[x-cloak] { display: none !important; }
```

```heex
<div x-data="{ open: false }" x-cloak>
  <%!-- Hidden until Alpine initializes --%>
</div>
```

---

## Directives Reference

### State & Initialization

| Directive | Purpose | Example |
|-----------|---------|---------|
| `x-data` | Declare reactive state | `x-data="{ open: false }"` |
| `x-init` | Run code on init | `x-init="fetchData()"` |
| `x-model` | Two-way binding | `<input x-model="name">` |

### Rendering

| Directive | Purpose | When to Use |
|-----------|---------|-------------|
| `x-show` | Toggle CSS display | Frequent toggles (cheaper) |
| `x-if` | Add/remove from DOM | Heavy content, rare display |
| `x-for` | Loop iteration | `<template x-for="item in items">` |
| `x-text` | Set text content | `<span x-text="message">` |
| `x-html` | Set inner HTML | **Avoid with user input (XSS)** |

### Events & Binding

| Directive | Purpose | Example |
|-----------|---------|---------|
| `x-on` / `@` | Event listener | `@click="toggle()"` |
| `x-bind` | Dynamic attributes | `x-bind:class="{ active: isActive }"` |

### Advanced

| Directive | Purpose |
|-----------|---------|
| `x-transition` | CSS transitions |
| `x-ref` | Element references |
| `x-cloak` | Hide until Alpine loads |
| `x-teleport` | Move element in DOM |
| `x-effect` | Reactive side effects |
| `x-ignore` | Skip Alpine processing |

---

## Magic Properties

| Property | Purpose | Example |
|----------|---------|---------|
| `$el` | Current element | `$el.focus()` |
| `$refs` | Referenced elements | `$refs.input.focus()` |
| `$store` | Global stores | `$store.auth.user` |
| `$dispatch` | Custom events | `$dispatch('notify', data)` |
| `$nextTick` | After DOM update | `$nextTick(() => $refs.input.focus())` |
| `$watch` | Watch changes | `$watch('count', v => log(v))` |

---

## Event Modifiers

```heex
<%!-- Click outside to close --%>
@click.outside="open = false"

<%!-- Keyboard events --%>
@keydown.escape.window="close()"
@keydown.enter="submit()"

<%!-- Rate limiting --%>
@input.debounce.300ms="search()"
@click.throttle.500ms="save()"

<%!-- Event control --%>
@click.stop="handle()"      <%!-- Stop propagation --%>
@click.prevent="handle()"   <%!-- Prevent default --%>
@click.self="handle()"      <%!-- Only if target is element --%>
@click.once="init()"        <%!-- Fire once only --%>

<%!-- Window/document level --%>
@resize.window="onResize()"
@scroll.window.passive="onScroll()"
```

---

## Transitions

### Simple

```heex
<div x-show="open" x-transition>Content</div>

<%!-- Customized --%>
<div x-show="open"
     x-transition.duration.300ms
     x-transition.opacity
     x-transition.scale.95>
```

### CSS Class Transitions

```heex
<div x-show="open"
     x-transition:enter="transition ease-out duration-300"
     x-transition:enter-start="opacity-0 scale-90"
     x-transition:enter-end="opacity-100 scale-100"
     x-transition:leave="transition ease-in duration-200"
     x-transition:leave-start="opacity-100 scale-100"
     x-transition:leave-end="opacity-0 scale-90">
```

---

## LiveView Integration Patterns

### Pattern 1: Isolate Alpine-Controlled DOM

```heex
<%!-- LiveView won't patch this element --%>
<div x-data="{ open: false }" phx-update="ignore" id="dropdown-1">
  <button @click="open = !open">Toggle</button>
  <div x-show="open" x-transition>
    Dropdown content
  </div>
</div>
```

**Warning:** Assigns inside `phx-update="ignore"` only render once at mount.

### Pattern 2: Initialize Server Data Correctly

```heex
<%!-- BAD: Timing issues, stale data --%>
<div x-data="{ items: #{Jason.encode!(@items)} }">

<%!-- GOOD: Declare then initialize --%>
<div x-data="{ items: [] }"
     x-init={"items = #{JSON.encode!(@items)}"}>
```

### Pattern 3: Safe Data Passing

```heex
<%!-- BAD: Breaks on quotes, newlines, special chars --%>
<div x-init={"message = '#{@message}'"}>

<%!-- GOOD: JSON encoding handles escaping --%>
<div x-data="{ message: '', config: {} }"
     x-init={"message = #{JSON.encode!(@message)}; config = #{JSON.encode!(@config)}"}>
```

### Pattern 4: Compare by ID, Not Reference

```heex
<%!-- BAD: Object references change after LiveView update --%>
<span x-show="selected == item">

<%!-- GOOD: Compare primitive values --%>
<span x-show="selected?.id === item.id">
```

### Pattern 5: Attribute Syntax Warning

```heex
<%!-- BAD: Conflicts with LiveView's :if/:for/:let --%>
<div :class="open ? 'visible' : 'hidden'">

<%!-- GOOD: Use full x-bind: prefix --%>
<div x-bind:class="open ? 'visible' : 'hidden'">
```

### Pattern 6: Emit Events to LiveView

```heex
<div x-data="{ value: '' }"
     id="alpine-input"
     phx-hook="AlpineEvents">
  <input x-model="value" @change="$dispatch('value-changed', { value })">
</div>
```

```javascript
// In app.js
Hooks.AlpineEvents = {
  mounted() {
    this.el.addEventListener('value-changed', e => {
      this.pushEvent('value-changed', e.detail)
    })
  }
}
```

### Pattern 7: Reinitialize After Dynamic Content

```javascript
Hooks.AlpineReinit = {
  mounted() {
    Alpine.initTree(this.el)
  },
  updated() {
    Alpine.initTree(this.el)
  }
}
```

---

## Common UI Components

### Dropdown

```heex
<div x-data="{ open: false }" class="relative">
  <button @click="open = !open"
          @keydown.escape.window="open = false">
    Options
  </button>

  <div x-show="open"
       x-transition
       x-cloak
       @click.outside="open = false"
       class="absolute mt-2 bg-white shadow rounded">
    <a href="#" class="block px-4 py-2">Edit</a>
    <a href="#" class="block px-4 py-2">Delete</a>
  </div>
</div>
```

### Modal

```heex
<div x-data="{ open: false }">
  <button @click="open = true">Open Modal</button>

  <template x-teleport="body">
    <div x-show="open"
         x-transition.opacity
         x-cloak
         @keydown.escape.window="open = false"
         class="fixed inset-0 bg-black/50 flex items-center justify-center">

      <div @click.outside="open = false"
           x-transition:enter="transition ease-out duration-200"
           x-transition:enter-start="opacity-0 scale-95"
           x-transition:enter-end="opacity-100 scale-100"
           class="bg-white rounded-lg p-6 max-w-md">
        <h2 class="text-lg font-bold">Modal Title</h2>
        <p>Modal content here</p>
        <button @click="open = false" class="mt-4">Close</button>
      </div>
    </div>
  </template>
</div>
```

### Tabs

```heex
<div x-data="{ activeTab: 'tab1' }">
  <div class="flex border-b" role="tablist">
    <button @click="activeTab = 'tab1'"
            x-bind:class="activeTab === 'tab1' ? 'border-b-2 border-blue-500' : ''"
            class="px-4 py-2">
      Tab 1
    </button>
    <button @click="activeTab = 'tab2'"
            x-bind:class="activeTab === 'tab2' ? 'border-b-2 border-blue-500' : ''"
            class="px-4 py-2">
      Tab 2
    </button>
  </div>

  <div x-show="activeTab === 'tab1'" class="p-4">Tab 1 content</div>
  <div x-show="activeTab === 'tab2'" class="p-4">Tab 2 content</div>
</div>
```

### Accordion

```heex
<div x-data="{ active: null }">
  <%= for {item, index} <- Enum.with_index(@items) do %>
    <div class="border-b">
      <button @click={"active = active === #{index} ? null : #{index}"}
              class="w-full text-left p-4 flex justify-between">
        <span><%= item.title %></span>
        <span x-text={"active === #{index} ? '−' : '+'"}>+</span>
      </button>
      <div x-show={"active === #{index}"}
           x-transition:enter="transition ease-out duration-200"
           x-transition:enter-start="opacity-0 max-h-0"
           x-transition:enter-end="opacity-100 max-h-96"
           class="p-4 bg-gray-50">
        <%= item.content %>
      </div>
    </div>
  <% end %>
</div>
```

### Toggle with LiveView Sync

```heex
<div x-data={"{ enabled: #{@enabled} }"}
     id="feature-toggle"
     phx-hook="ToggleSync">
  <button @click="enabled = !enabled; $dispatch('toggle-changed', { enabled })"
          x-bind:class="enabled ? 'bg-blue-600' : 'bg-gray-200'"
          class="relative inline-flex h-6 w-11 rounded-full transition-colors">
    <span x-bind:class="enabled ? 'translate-x-6' : 'translate-x-1'"
          class="inline-block h-4 w-4 mt-1 rounded-full bg-white transition-transform">
    </span>
  </button>
</div>
```

```javascript
Hooks.ToggleSync = {
  mounted() {
    this.el.addEventListener('toggle-changed', e => {
      this.pushEvent('toggle-changed', e.detail)
    })
  }
}
```

---

## Global Stores

```javascript
// In app.js, before Alpine.start()
Alpine.store('notifications', {
  items: [],

  add(message, type = 'info') {
    const id = Date.now()
    this.items.push({ id, message, type })
    setTimeout(() => this.remove(id), 5000)
  },

  remove(id) {
    this.items = this.items.filter(n => n.id !== id)
  }
})
```

```heex
<%!-- Notification display component --%>
<div x-data class="fixed top-4 right-4 space-y-2">
  <template x-for="notification in $store.notifications.items" :key="notification.id">
    <div x-transition
         x-bind:class="{
           'bg-green-100': notification.type === 'success',
           'bg-red-100': notification.type === 'error',
           'bg-blue-100': notification.type === 'info'
         }"
         class="p-4 rounded shadow">
      <span x-text="notification.message"></span>
      <button @click="$store.notifications.remove(notification.id)">&times;</button>
    </div>
  </template>
</div>

<%!-- Trigger from anywhere --%>
<button @click="$store.notifications.add('Saved!', 'success')">Save</button>
```

---

## Reusable Components with Alpine.data()

```javascript
// In app.js
Alpine.data('dropdown', () => ({
  open: false,

  toggle() {
    this.open = !this.open
  },

  close() {
    this.open = false
  }
}))

Alpine.data('modal', () => ({
  open: false,

  show() {
    this.open = true
    this.$nextTick(() => this.$refs.closeButton?.focus())
  },

  hide() {
    this.open = false
  }
}))
```

```heex
<%!-- Usage --%>
<div x-data="dropdown">
  <button @click="toggle()">Menu</button>
  <div x-show="open" @click.outside="close()">Content</div>
</div>
```

---

## Anti-Patterns

### Don't: Build Full SPAs

```javascript
// Alpine lacks routing and complex state management
// Use for progressive enhancement, not full applications
```

### Don't: Complex Logic in HTML

```heex
<%!-- BAD --%>
<div @click="items = items.filter(i => i.active).map(i => ({...i, count: i.count + 1}))">

<%!-- GOOD: Move to Alpine.data() or x-data methods --%>
<div x-data="itemManager()" @click="processItems()">
```

### Don't: Nest x-data with Same Variable Names

```heex
<%!-- BAD: Scope confusion --%>
<div x-data="{ open: false }">
  <div x-data="{ open: true }">  <%!-- Shadows parent --%>
  </div>
</div>

<%!-- GOOD: Unique names --%>
<div x-data="{ menuOpen: false }">
  <div x-data="{ dropdownOpen: true }">
  </div>
</div>
```

### Don't: Use x-html with User Input

```heex
<%!-- DANGEROUS: XSS vulnerability --%>
<div x-html="userInput"></div>

<%!-- SAFE: Use x-text or sanitize --%>
<div x-text="userInput"></div>
```

### Don't: Forget x-cloak

```heex
<%!-- BAD: Hidden content flashes on page load --%>
<div x-data="{ show: false }">
  <div x-show="show">Visible briefly!</div>
</div>

<%!-- GOOD --%>
<div x-data="{ show: false }" x-cloak>
  <div x-show="show">Properly hidden</div>
</div>
```

### Don't: Use Large Lists Without Keys

```heex
<%!-- BAD: Inefficient re-renders --%>
<template x-for="item in items">

<%!-- GOOD: Key for efficient diffing --%>
<template x-for="item in items" :key="item.id">
```

---

## Decision Matrix: LiveView.JS vs Alpine

| Use Case | LiveView.JS | Alpine |
|----------|:-----------:|:------:|
| Simple show/hide | ✅ | ❌ |
| Class toggle | ✅ | ❌ |
| Focus management | ✅ | ❌ |
| Push server event | ✅ | ❌ |
| Complex state machine | ❌ | ✅ |
| Multi-step client interactions | ❌ | ✅ |
| Smooth animations with timing | ❌ | ✅ |
| Third-party JS library wrappers | ❌ | ✅ |
| Drag and drop | ❌ | ✅ |
| Client-only form preview | ❌ | ✅ |

---

## Debugging

### Enable Debug Mode

```javascript
Alpine.debug = true  // Before Alpine.start()
```

### Inspect State in Console

```javascript
// Get Alpine data from element
document.querySelector('[x-data]')._x_dataStack

// Or with $el in Alpine context
$el._x_dataStack
```

### Trace Reactive Updates

```heex
<div x-data="{ count: 0 }"
     x-effect="console.log('count:', count)">
```

### Alpine DevTools

Install browser extension (Chrome/Firefox) to inspect:
- Component hierarchy
- Reactive data
- Event listeners
- Stores

---

## Common Failures & Solutions

| Failure | Cause | Solution |
|---------|-------|----------|
| State lost after LiveView patch | Missing `onBeforeElUpdated` | Add `Alpine.clone(from, to)` hook |
| Content flashes on load | Missing x-cloak | Add CSS and x-cloak attribute |
| Events fire twice | Both Alpine and LiveView handling | Use `.stop` modifier or separate |
| Stale data after server push | Data in x-data not updated | Use x-init with server data |
| Memory leaks | Components not destroyed | Use x-if for heavy content |
| Broken reactivity | Nested object mutation | Reassign objects with spread |

---

## Performance Tips

1. **Use `x-show` for frequent toggles** (cheaper than DOM manipulation)
2. **Use `x-if` for heavy/rare content** (removes from DOM)
3. **Add `:key` to x-for loops** for efficient diffing
4. **Debounce/throttle inputs** (`@input.debounce.300ms`)
5. **Keep state objects shallow** for reactivity
6. **Avoid large lists** (1000+ items) without pagination
7. **Use x-cloak** to prevent layout shift
8. **Prefer CSS transitions** over JS animations
