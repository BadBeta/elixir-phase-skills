---
name: elixir-planning
description: >
  Elixir architectural planning — the decisions made BEFORE writing implementation code.
  Covers project layout (single app / umbrella / poncho / library), domain boundaries
  (contexts, aggregates, entity vs use case), data ownership and multi-tenancy,
  process architecture (supervision as architecture, error kernel, stateful vs stateless),
  inter-context communication (direct call / PubSub / Registry / GenStage / Broadway / Oban /
  event sourcing — with decision guide), configuration strategy, resilience patterns
  (bulkheads, circuit breakers, retries, graceful degradation, timeouts), architectural
  styles (MVC / hexagonal / modular monolith / event-driven / CQRS / microservices),
  growing architecture from small to large, distributed systems, and the architectural
  anti-patterns to avoid.
  ALWAYS use when planning or designing an Elixir application, service, or feature.
  ALWAYS use when the user asks to "design", "architect", "structure", "plan", "lay out",
  or "organize" Elixir code.
  ALWAYS use when choosing between umbrella/single-app, contexts, process placement,
  supervision strategy, or inter-context communication mechanism.
  ALWAYS use when starting a new Elixir project or major refactor.
  ALWAYS use when the user asks "should I split X into Y" or "where should Z live".
  For writing the code itself (patterns, constructs, idiom), also load elixir-implementing.
---

# Elixir — Planning Skill

Architectural decisions made **before** writing implementation code. This skill sits upstream of `elixir-implementing`: planning answers *what to build and how to structure it*; implementing answers *how to type it idiomatically*.

## About this skill family

- **elixir-planning** (this) — upfront architecture: project layout, contexts, data ownership, process shape, supervision, integration mechanism, resilience, architectural style.
- **[elixir-implementing](../elixir-implementing/SKILL.md)** — the moment of writing: decision tables for constructs, idiomatic templates, anti-patterns Claude produces, TDD, testing essentials, OTP callback patterns.
- **[elixir-reviewing](../elixir-reviewing/SKILL.md)** — code inspection: review PRs, debug bugs, profile performance.

The three skills follow the skill-authoring three-modes framework. This skill leans heavily on **decision tables** (the "at the moment of designing" mode) and **process-style rules** (constraints that fire during review). Code templates appear mainly as supervision-tree shapes and context API patterns — the bulk of code templates lives in `elixir-implementing`.

## Subskills — deep references within elixir-planning

This SKILL.md covers the decision tables and quick-reference material. For depth on any topic, load the relevant subskill:

| Subskill | Scope | Load when |
|---|---|---|
| [architecture-patterns.md](architecture-patterns.md) | Hexagonal, layered, modular monolith, event-driven, CQRS, microservices — deep walkthroughs | Deciding architectural style for a project or context |
| [process-topology.md](process-topology.md) | Supervision tree design, error kernel, process-per-service vs per-entity, instructions pattern, callback module pattern | Designing the supervision tree; placing processes |
| [otp-design.md](otp-design.md) | OTP construct choice — GenServer vs Task vs Agent vs `:gen_statem` vs ETS vs `:persistent_term` vs GenStage/Broadway vs Oban | Picking the OTP primitive for a use case |
| [integration-patterns.md](integration-patterns.md) | Six inter-context mechanisms in depth, capacity planning, escalation path, sagas, process managers | Designing how contexts / services communicate |
| [data-ownership-deep.md](data-ownership-deep.md) | Aggregates, multi-tenancy strategies, cross-context transactions, sagas, idempotency | Designing the data model, tenant isolation, retry-safe operations |
| [test-strategy.md](test-strategy.md) | Test pyramid, mock boundaries, factory architecture, async isolation design, CI strategy, contract tests | Planning test infrastructure at project start; fixing slow/flaky suites |
| [networking-design.md](networking-design.md) | TCP/UDP server architecture, active vs passive mode, protocol framing, connection supervision, TLS placement | Designing a network server or protocol |
| [growing-evolution.md](growing-evolution.md) | Stage 1→2→3 evolution, refactoring decision tree, when to split / merge / escalate mechanisms | Growing an existing app; deciding whether a refactor is needed |

**Cross-references:** subskills link to each other and to the other main skills' subskills (when they exist) via relative paths.

## How to use this skill

1. **Starting a new project?** — Read §1 (Rules), §2 (Planning Workflow), §5 (Project Layout). Walk through the decisions in sequence.
2. **Adding a new feature to an existing project?** — §2 (Planning Workflow), §3 (Master Decision Table). Check §6 (do I need a new context?) and §8 (do I need a new process?).
3. **Refactoring?** — §13 (Growing Architecture) to identify where you are, §14 (Anti-patterns) to find what to fix, §6 and §9 for context/integration rework.
4. **Choosing how two parts of the system should talk?** — §9 (Inter-Context Communication) — the 6 mechanisms and the decision guide.
5. **Designing for failure?** — §11 (Resilience) — where circuit breakers, retries, and degradation live.
6. **About to write code?** — Load `elixir-implementing` alongside this skill.

---

## 1. Rules for Architecting Elixir Applications (LLM)

1. **ALWAYS start with the simplest architecture**: single Mix application + contexts + one-level supervision. Add complexity (umbrella, PubSub, GenStage, Oban, event sourcing) only when the specific problem it solves is present.
2. **ALWAYS think in three modes of content** — this skill itself follows them: rules (constrain design at review), decision tables (guide at moment of designing), BAD/GOOD (verify). For each planning decision, check the relevant decision table in §3 or §9 first.
3. **ALWAYS sketch the supervision tree before writing code.** The supervision tree IS the architecture. Start order = dependency order. Strategy encodes coupling. If you cannot draw it, you cannot build it.
4. **ALWAYS put external dependencies behind a `@callback` behaviour.** Database, HTTP, email, payment gateway, hardware — every boundary that crosses out of your app. Config picks the implementation. This gives you hexagonal architecture for free.
5. **NEVER split a modular monolith into microservices for "loose coupling" or "fault isolation"** — OTP already provides both. Only split for different languages, compliance isolation, wildly different scaling needs, or genuinely separate teams/release cycles.
6. **ALWAYS use single Mix application over umbrella** until you need hard compile-time boundaries across teams or separate deployment targets. "Feels like it's getting big" is not a reason to split.
7. **ALWAYS name modules after the domain**, not the framework (`Accounts`, `Catalog`, `Billing` — not `Controllers`, `Models`, `Services`). Scream the domain.
8. **NEVER organize code into `models/`, `services/`, `helpers/` directories.** These are anti-patterns from other ecosystems. Elixir uses contexts (boundary modules) with internal modules marked `@moduledoc false`.
9. **NEVER call `Repo` across context boundaries.** Each table is owned by exactly one context. Other contexts read through the owning context's public API.
10. **NEVER put business logic in interface modules** (controllers, LiveViews, CLI handlers, GenServer callbacks). Interfaces translate input, delegate to a context, format output. Business logic lives in pure functions inside contexts.
11. **PREFER pure functions over processes.** Use a GenServer only when you need shared mutable state, serialized access to a resource, or scheduled work. If two concepts always change together in the same flow, they belong in the same process (or no process at all).
12. **ALWAYS design for replaceability.** Can you swap this component's implementation without changing business logic? If not, introduce a behaviour at the boundary.
13. **ALWAYS define the aggregate consistency boundary** for domain operations. One aggregate per transaction. Cross-aggregate operations are sagas or eventual consistency, never multi-aggregate `Repo.transaction`.
14. **ALWAYS identify which operations can be retried** (Oban workers, webhook handlers, event handlers, distributed calls) and design them to be idempotent from the start.
15. **ALWAYS choose a multi-tenancy strategy before starting** if the app is tenant-aware. Retrofitting multi-tenancy is painful. Row-level (tenant_id) is the default; escalate to schema-per-tenant or DB-per-tenant only when isolation requirements demand it.
16. **NEVER place circuit breakers or retry logic in domain modules.** They belong in infrastructure adapters, wrapping external calls.
17. **ALWAYS cascade timeouts correctly**: outer > middle > inner (endpoint > GenServer.call > HTTP client). Otherwise outer timeouts fire before inner ones with meaningless errors.
18. **ALWAYS start with direct function calls** between contexts. Escalate to PubSub when you need decoupling, GenStage when you need backpressure, Oban when events must survive restarts, event sourcing when you need audit/replay. Don't pre-select the complex solution.
19. **NEVER introduce distribution (multi-node clustering) until single-node is maxed out.** `Task.async_stream`, process pools, Broadway, read replicas — exhaust these first. Distribution brings network partitions, split-brain, and eventual consistency.
20. **ALWAYS hand off to `elixir-implementing` for the actual code.** This skill decides *what to build*; the implementing skill covers *how to type it idiomatically*.

---

## 2. The Planning Workflow

Walk through this sequence before starting any Elixir project or significant feature. Answer each question; defer to the named section for detail.

### 2.1 Opening questions for a new project

| Question | Defer to |
|---|---|
| What IS the domain? Name the business concepts (the contexts). | §6 Domain Boundaries |
| What are the inputs (interfaces) and outputs (side effects / external systems)? | §4 Principles (Hexagonal), §10 Config |
| Is this a library or an application? Who owns the supervision tree? | §5.3 Library vs App |
| Single Mix app, umbrella, or poncho? | §5 Project Layout |
| Does the app have tenants? Which isolation strategy? | §7.4 Multi-Tenancy |
| What state needs to survive a crash? What's volatile? | §8 Error Kernel |
| What state lives in processes vs. in the database? | §8.5 Stateful vs Stateless |
| How will contexts communicate? Any cross-context consistency needs? | §9 Inter-Context Communication |
| What external services are involved? What happens when they fail? | §11 Resilience |
| What failure modes must the system tolerate gracefully? | §11 Graceful Degradation |

### 2.2 Opening questions for a new feature in an existing project

| Question | Defer to |
|---|---|
| Does this feature belong in an existing context, or does it warrant a new one? | §6.2 When to create a new context |
| Which context owns the data this feature operates on? | §7.1 Data Ownership |
| Does the feature cross context boundaries? If yes, how? | §9 Inter-Context Communication |
| Does it need a new process, or pure functions in an existing context? | §8.1 Do you need a process? |
| Is there a retry / failure path? Is the operation idempotent? | §7.3 Idempotency |
| Does the feature need to degrade gracefully when a dependency is down? | §11.4 Graceful Degradation |

### 2.3 Opening questions when refactoring

| Question | Defer to |
|---|---|
| Which growth stage is this app at? | §13 Growing Architecture |
| Are there contexts doing more than one job (mixed responsibilities)? | §6.2 When to split |
| Are there cross-context Repo calls, or contexts reaching into each other's internals? | §7.1 Data Ownership |
| Are there GenServers doing CRUD-y stuff that could be pure functions? | §8.1 Do you need a process? §14 Anti-Patterns |
| Is the supervision tree expressing the architecture, or is it flat? | §8.3 Supervision as Architecture |
| Are there processes simulating objects (agent-per-entity)? | §14 "Simulating Objects with Processes" |

### 2.4 The "what's needed now vs later" test

Elixir architecture is **additive**. The progression is:

```
Phase 0 (MVP):     Contexts + supervision + one behaviour (Repo)
Phase 1:           + PubSub for UI updates / decoupling
Phase 2:           + Oban for guaranteed async work
Phase 3:           + GenStage / Broadway for backpressured pipelines
Phase 4:           + Event sourcing for audit / replay (only if needed)
Phase 5:           + Distributed architecture (only if single-node maxed)
```

**Never adopt a phase before its triggering problem appears.** Each phase adds complexity; unjustified complexity compounds.

---

## 3. Master "Planning Decision" Table

This is the spine of the skill. Every major architectural question maps to a row. Find your question in the left column; the right columns show the decision and the defer-to section.

### 3.1 Project layout

| Question | Answer | Details |
|---|---|---|
| New project, one team, one deployable | Single Mix application + contexts | §5.1 |
| New project, multiple teams with hard boundaries | Umbrella | §5.2 |
| New project, apps need different dep versions | Poncho | §5.3 |
| Building a reusable library (will be a Hex dep) | Single Mix application, NO supervision tree, behaviour-based extension points | §5.3 (Library vs App) |
| "Should I split this monolith?" | **Almost certainly no.** Add contexts first. | §13 (Growing Architecture) |
| Need code in multiple languages (Rust NIFs, Python ML) | Stay single-deploy, use NIFs / external processes | Defer to `rust-nif` |
| Feels like it's getting big | Add contexts, do NOT split | §13 |

### 3.2 Domain boundaries (contexts)

| Question | Answer | Details |
|---|---|---|
| Does this feature need a new context? | Check §6.2 rules: different business domain? different team? different data lifecycle? | §6.2 |
| Where does this function live? | In the context that OWNS the primary data being manipulated | §7.1 |
| How big is too big for one context? | Multiple unrelated aggregates = too big | §6.3 |
| Two contexts need the same table? | One owns it; the other reads through the owner's public API | §7.1 |
| Multiple entities that must stay consistent | Same aggregate, same context, one `Repo.transaction` | §6.3 (Aggregates) |
| Entities that MAY be consistent | Different aggregates → saga or eventual consistency | §7.2 (Cross-Context Transactions) |
| Cross-context transaction? | Sign of missing boundary OR need for saga pattern | §7.2 |
| Integrating with an external system / legacy | Anti-corruption layer at the adapter | §6.5 |

### 3.3 Data ownership and consistency

| Question | Answer | Details |
|---|---|---|
| Who owns this table? | Exactly one context — the one that writes | §7.1 |
| Can two contexts write to the same table? | **No.** Always one writer context | §7.1 |
| How do other contexts read the data? | Through the owning context's public API | §7.1 |
| Cross-context update in one transaction? | Merge contexts, or saga, or eventual consistency | §7.2 |
| Is idempotency needed? | Yes for: Oban workers, webhook handlers, event handlers, distributed calls, anything retryable | §7.3 |
| Multi-tenant isolation? | Row-level (default), schema-per-tenant, or DB-per-tenant | §7.4 |

### 3.4 Process architecture

| Question | Answer | Details |
|---|---|---|
| Do I need a process for this? | **Probably not.** Most code is pure functions | §8.1 |
| Need shared mutable state across callers | GenServer (one writer) | §8.4 |
| Need fast concurrent reads | ETS (one writer, many readers) | §8.4 |
| Need to serialize access to a resource | GenServer | §8.4 |
| Need state per entity (user, game, device) | DynamicSupervisor + Registry | §8.6 (Process-per-Entity) |
| State must survive crash | Database + stateless process, OR stateful + recovery strategy | §8.5 |
| Long-running background work | Supervised Task, or Oban for persistence | §8.4 |
| Scheduled / periodic work | `Process.send_after` in a GenServer, or Oban cron | §8.4 |
| Multi-step process with states and transitions | `gen_statem` | Defer to `state-machine` skill |

### 3.5 Supervision strategy

| Question | Answer | Details |
|---|---|---|
| What restarts when child X crashes? | `:one_for_one` (just X), `:rest_for_one` (X + later), `:one_for_all` (all) | §8.3 |
| Children are independent | `:one_for_one` | §8.3 |
| Child B depends on A's state | `:rest_for_one` (A before B) | §8.3 |
| Registry + DynamicSupervisor pairing | `:one_for_all` (tightly coupled) | §8.6 |
| Startup order | Infrastructure (Repo, PubSub) → Domain → Endpoint last | §8.3 |

### 3.6 Inter-context communication

| Question | Answer | Details |
|---|---|---|
| Simplest case, synchronous, need result | Direct function call via public API | §9.1 |
| Fire-and-forget notification, loss OK | `Phoenix.PubSub` / `:pg` | §9.2 |
| Per-entity subscriptions (one order, one user) | `Registry` with `:duplicate` keys | §9.3 |
| Producer can exceed consumer throughput | GenStage / Broadway (backpressure) | §9.4 |
| Event must survive restart | Oban (persistent queue) | §9.5 |
| Full audit trail / replay / complex workflow | Event sourcing (Commanded) | §9.6 |
| Consuming from Kafka / SQS / RabbitMQ | Broadway | §9.4 |
| Multi-step orchestration with compensation | Saga (explicit) or process manager (Commanded) | §9.7 |

### 3.7 Integration boundaries (external systems)

| Question | Answer | Details |
|---|---|---|
| Calling an HTTP API | Behaviour + adapter + config switch | §4 (Principle 2), §10 |
| Sending email | `@callback` Mailer behaviour, Swoosh adapter | §10 |
| Payment gateway | `@callback` PaymentGateway behaviour, Stripe/etc. adapter | §10, §6.5 (ACL) |
| Hardware (I2C, SPI, GPIO) | `@callback` adapter behaviour | Defer to `nerves`, `i2c`, `spi` |
| Database | Ecto (already behaviour-based via `Ecto.Adapter`) | §4 |
| Another service over HTTP / gRPC | Behaviour + adapter | §10 |
| Need to swap implementation in tests | Behaviour + Mox | `elixir-implementing` §4.4 |

### 3.8 Resilience

| Question | Answer | Details |
|---|---|---|
| External service may be slow/flaky | Circuit breaker in the adapter | §11.2 |
| Operation may fail transiently | Retry at the right layer (HTTP client, Oban, supervisor) | §11.3 |
| External service is down | Graceful degradation — return partial / cached / default | §11.4 |
| Timeouts across layers | Outer > middle > inner | §11.5 |
| Prevent one subsystem from failing another | BEAM processes as bulkheads (separate supervisors) | §11.1 |
| Prevent retries from duplicating | Idempotency | §7.3 |

### 3.9 Architectural style

| Question | Answer | Details |
|---|---|---|
| Default Elixir app | Contexts + supervision + behaviours (modular monolith, hexagonal, MVC all at once) | §12.1, §4 |
| Separate read path from write path | Light CQRS (same context, both kinds of functions) | §12.3 |
| Reads need very different optimization | Separated read path (query module, optional read replica) | §12.3 |
| Full audit trail + replay + multiple read projections | Event sourcing + full CQRS | §12.4 |
| Decouple contexts with async notifications | PubSub (event notification or event-carried state transfer) | §12.5 |
| Split into microservices | Last resort — only for different languages, compliance, or org boundaries | §12.2 |

### 3.10 Configuration

| Question | Answer | Details |
|---|---|---|
| Value fixed at build, app-owned | `config/config.exs` + `Application.compile_env` | §10.1 |
| Env var, per-deployment | `config/runtime.exs` + `System.fetch_env!` | §10.1 |
| Library consumer configures | Accept runtime config via options; NEVER `compile_env` in a library | §10.2 |
| Test-specific overrides (Mox wiring, small pool sizes) | `config/test.exs` | §10.1 |
| Feature flag, toggleable at runtime | External (FunWithFlags, Flagsmith, database row) | §10.3 |

### 3.11 Distribution (usually NO)

| Question | Answer | Details |
|---|---|---|
| Need more throughput | `Task.async_stream`, Broadway, more cores — NOT distribution | §15.3 |
| Need high availability | Supervisor restarts + health checks + rolling deploys | §15.3 |
| Need 1M+ WebSocket connections | Single node handles it — verify before clustering | §15.3 |
| Geographic data locality | Distribution — genuinely needs it | §15.2 |
| Legitimate need to distribute | Design state ownership first, then pick communication | §15.1 |

---

## 4. Architectural Principles

Eleven principles that govern every structural decision. When in doubt, return here.

> **Depth:** [architecture-patterns.md](architecture-patterns.md) — full walkthrough of each architectural style (hexagonal, layered, modular monolith, event-driven, CQRS) with worked examples, common mistakes, and migration paths.

### 4.1 The eleven principles

1. **Dependencies point inward.** Interface depends on Domain. Domain depends on nothing external. Infrastructure implements contracts defined by Domain. Never let inner layers reference outer layers. A domain module must NEVER alias, import, or reference web modules, controller helpers, or framework-specific types.

2. **Behaviours are ports. Implementations are adapters.** Every external dependency (database, API, email, file system, hardware) is behind a `@callback` behaviour defined by the domain. Config selects which implementation runs. This IS hexagonal architecture — Elixir has it built in. Ecto itself follows this pattern: `Ecto.Adapter` is a behaviour, Postgres/MySQL/SQLite are adapters.

3. **Side effects belong in infrastructure, never in domain** — the ideal. In practice, Phoenix contexts intentionally mix Repo calls into domain-adjacent modules (`mix phx.gen.context` generates this). Full separation (pure domain, Repo behind behaviours) is practiced in event-sourced systems but is not the norm for standard Phoenix CRUD apps. For non-Repo side effects (HTTP, email, file I/O), the behaviour boundary is consistently applied.

4. **The supervision tree IS the architecture.** Start order = dependency order. Strategy encodes coupling. The tree is not just fault tolerance — it expresses which components depend on which, what restarts together, and what can fail independently.

5. **Error kernel design.** Stable processes hold critical state near the top of the tree. Volatile, crash-prone workers live below. If a worker crashes, critical state survives. Design for recovery, not prevention.

6. **Pure core, impure shell.** GenServers delegate business logic to pure functions. The GenServer handles process mechanics (state, messages, lifecycle). Pure functions handle domain logic (calculations, validations, transformations). This makes domain logic testable without processes. For complex cases, use the **instructions pattern** — domain functions return instruction tuples, GenServer interprets them (§8.7).

7. **Each boundary module has one reason to change: its domain changes.** If a module changes because both business rules changed AND the database schema changed, it has too many responsibilities. Boundary modules are public API facades. Internal modules use `@moduledoc false`.

8. **Design for replaceability.** Can you swap this component's implementation without changing business logic? If not, introduce a behaviour at the boundary.

9. **Keep behaviours small and focused.** No client should be forced to depend on callbacks it doesn't use. Prefer multiple small behaviours over one large one. Split `Chargeable`, `Refundable`, `Subscribable` rather than one giant `PaymentGateway` with 20 callbacks.

10. **The testability test.** If you cannot test a business rule without starting a database, web server, or external service, your architecture has a boundary problem. Pure domain logic should be testable with plain ExUnit — no Repo, no HTTP, no processes required.

11. **Scream the domain.** Top-level module names reflect business concepts (`Accounts`, `Catalog`, `Billing`, `Sensors`) — not technical concerns (`Controllers`, `Models`, `Services`, `Helpers`). A developer reading the module tree should understand what the system does, not what framework it uses.

### 4.2 The Actor Model — what BEAM gives you for free

| BEAM property | What it means | What it gives you |
|---|---|---|
| **Isolated state** | Each process has its own heap and GC | No locks, mutexes, or race conditions on shared data |
| **Message passing** | Processes communicate only by sending messages | All inter-process data is immutable by design (copied) |
| **Shared nothing** | No shared memory between processes | Scales linearly across cores; GC is per-process |
| **Location transparent** | `send(pid, msg)` identical for local and remote pids | Distribution is a config choice, not a code change |
| **Fail independently** | One process crash doesn't affect others | Supervision handles recovery; system continues |

### 4.3 Message passing semantics

| Guarantee | Meaning | Implication |
|---|---|---|
| **At-most-once** | Messages can be lost if receiver crashes before processing | Application handles reliability (idempotency, retries) |
| **Ordering within pair** | Messages from A→B arrive in send order | A→B and C→B may interleave arbitrarily |
| **No exactly-once** | BEAM provides no built-in exactly-once delivery | Design for at-least-once: make operations idempotent |
| **`call` semantics** | Caller gets `{:reply, _}` OR an exit | Caller always knows the outcome |

**Rule:** Use `GenServer.call` when you need to know the outcome. Use `cast` or `send` only when fire-and-forget is acceptable. Across node boundaries, ALWAYS use `call` — network partitions make `cast` unreliable.

### 4.4 Hexagonal architecture in Elixir

| Hexagonal concept | Elixir implementation |
|---|---|
| Port (interface) | `@callback` behaviour |
| Adapter (implementation) | Module implementing the behaviour |
| Domain core | Context modules with pure functions |
| Driving adapter (input) | Phoenix controllers, LiveView, CLI, API |
| Driven adapter (output) | Repo, HTTP clients, email, file I/O, hardware |
| Configuration | `Application.compile_env` (app) or `Application.get_env` (library) picks adapter |

Elixir gets hexagonal architecture **for free** via behaviours. You do not need a framework.

### 4.5 Layered architecture

The standard three layers:

```
┌─────────────────────────────────────┐
│ Interface (driving adapters)        │ ← Phoenix, CLI, LiveView, GraphQL
├─────────────────────────────────────┤
│ Domain (contexts, pure logic)       │ ← Accounts, Catalog, Orders, ...
├─────────────────────────────────────┤
│ Infrastructure (driven adapters)    │ ← Repo, HTTP clients, Mailer, Cache
└─────────────────────────────────────┘

Dependencies point downward (Interface → Domain → Infrastructure).
Never upward. Never sideways (Interface → Infrastructure).
```

- **Interface layer** translates input, delegates to domain, formats output. No business logic.
- **Domain layer** contains contexts with entities (pure data + invariants) and use cases (orchestration). No framework references.
- **Infrastructure layer** implements behaviours defined by domain. Each external dependency has an adapter.

---

## 5. Project Layout

First decision in any new Elixir project: how to lay it out.

> **Depth:** [architecture-patterns.md](architecture-patterns.md) §3 — modular monolith deep dive, §5 — layered architecture.

### 5.1 Single Mix application — the default

One `lib/` tree, organized by domain boundaries. This works for Phoenix web apps, Nerves firmware, CLI tools, and pure OTP services alike.

```
my_app/
├── lib/
│   ├── my_app/                   # Domain layer
│   │   ├── application.ex        # Supervision tree
│   │   ├── repo.ex               # Ecto Repo
│   │   ├── accounts.ex           # Context — public API
│   │   ├── accounts/
│   │   │   ├── user.ex           # Schema (internal — @moduledoc false)
│   │   │   └── token.ex
│   │   ├── catalog.ex
│   │   ├── catalog/
│   │   │   ├── product.ex
│   │   │   └── category.ex
│   │   ├── mailer.ex             # Behaviour
│   │   └── mailer/
│   │       └── swoosh.ex         # Adapter
│   └── my_app_web/               # Interface layer (Phoenix)
│       ├── endpoint.ex
│       ├── router.ex
│       ├── controllers/
│       ├── live/
│       └── components/
├── config/
│   ├── config.exs
│   ├── dev.exs
│   ├── test.exs
│   └── runtime.exs
├── test/
└── mix.exs
```

**When it's sufficient:** Most applications. Contexts provide domain boundaries without the overhead of multiple apps. Scale by adding contexts, not apps.

**How to grow it:** Add new context files (`lib/my_app/orders.ex`) and their internal modules (`lib/my_app/orders/*.ex`). No restructuring needed until you hit a team-boundary or deployment-boundary problem.

### 5.2 Umbrella project — multiple apps, shared config

Multiple OTP applications in one repository sharing build artifacts, deps, and config:

```
my_platform/                        # Root — no code here
├── apps/
│   ├── core/                       # Domain logic
│   │   ├── lib/core/
│   │   │   ├── accounts.ex
│   │   │   └── billing.ex
│   │   └── mix.exs
│   ├── core_web/                   # Phoenix web layer
│   │   ├── lib/core_web/
│   │   │   ├── endpoint.ex
│   │   │   └── router.ex
│   │   └── mix.exs                 # deps: [{:core, in_umbrella: true}]
│   └── worker/                     # Background processing
│       └── mix.exs                 # deps: [{:core, in_umbrella: true}]
├── config/config.exs               # Shared config for ALL apps
├── mix.exs                         # apps_path: "apps"
└── mix.lock                        # Single lockfile
```

**Root `mix.exs`:**

```elixir
defmodule MyPlatform.MixProject do
  use Mix.Project
  def project, do: [apps_path: "apps", version: "0.1.0", deps: deps()]
  defp deps, do: []   # Shared deps go here; app-specific deps in child mix.exs
end
```

**Child `mix.exs`:**

```elixir
defmodule Core.MixProject do
  use Mix.Project
  def project do
    [
      app: :core,
      build_path: "../../_build",
      config_path: "../../config/config.exs",
      deps_path: "../../deps",
      lockfile: "../../mix.lock",
      deps: [{:ecto, "~> 3.12"}]     # App-specific deps
    ]
  end
end
```

**Key properties:**

- Single `mix test` runs all apps; `mix test --app core` runs one
- Single `config/config.exs` for all apps — shared configuration
- Sibling deps via `in_umbrella: true`
- All apps share the same dependency versions (no version conflicts)
- `mix new my_platform --umbrella` scaffolds the structure

**When umbrella wins:** Multiple teams working on distinct subsystems. Separate deployment targets (web vs worker vs API). Hard compile-time module boundaries.

**When umbrella loses:** Single team, single deploy. The split creates maintenance overhead with little benefit. Stay with single Mix app + contexts.

### 5.3 Poncho project — full independence

Independent Mix projects in one repository linked by path dependencies:

```
my_platform/
├── core/                           # Independent project
│   ├── lib/core/
│   ├── config/config.exs           # Own config
│   ├── mix.exs
│   └── mix.lock
├── web/
│   └── mix.exs                     # deps: [{:core, path: "../core"}]
└── worker/
    └── mix.exs                     # deps: [{:core, path: "../core"}]
```

**Differences from umbrella:**

- Each app has its own config, deps, and lockfile
- Different apps can use different dep versions
- No shared build directory — fully independent compilation
- No `mix test` from root — test each app separately

**When poncho wins:** Apps need different dependency versions. Apps have different release cycles. Migrating toward fully independent Hex packages. Teams need complete autonomy.

### 5.4 Library vs application architecture

**A library is code you publish for others to consume** (Hex package, path dep in another project). **An application is code you deploy as a running system** (Mix release).

| Dimension | Application | Library |
|---|---|---|
| Owns supervision tree | Yes | No — added as child to someone else's tree |
| Configuration | `Application.get_env` in `runtime.exs`, `Application.compile_env` in `config.exs` | Accepts config via function arguments; optionally `Application.get_env` at runtime only |
| Framework dependencies | Can depend on Phoenix/Ecto/etc. | Framework-agnostic, or optional integration |
| Behaviour for swap | Config-driven | Consumer passes implementation module |
| Global state | Named GenServers, `Application.ensure_started` | Accepts registry/PubSub refs as options |

**Library rules:**

1. **Never use `Application.compile_env` in a library** — consumers can't reconfigure after compilation. Use `Application.get_env` at runtime or accept config as arguments.
2. **Never hardcode global names** — `name: __MODULE__` means only one instance can run. Accept a name option.
3. **Minimize dependencies** — each dep is a liability for your consumers.
4. **Define extension via behaviours** — let consumers customize, don't hardcode implementations.
5. **Ship a default implementation** — a useful library works out of the box AND can be customized.

```elixir
# BAD — library assumes it owns the world
defmodule MyLib.Worker do
  use GenServer
  def start_link(_) do
    GenServer.start_link(__MODULE__, Application.get_env(:my_lib, :config), name: __MODULE__)
    #                                                                      ^^^^^^^^^^^^^^ hardcoded
  end
end

# GOOD — library is a guest in someone else's application
defmodule MyLib.Worker do
  use GenServer
  def start_link(opts) do
    {config, server_opts} = Keyword.split(opts, [:buffer_size, :flush_interval])
    GenServer.start_link(__MODULE__, config, server_opts)
  end

  def child_spec(opts) do
    %{id: opts[:id] || __MODULE__, start: {__MODULE__, :start_link, [opts]}}
  end
end
```

### 5.5 Layout decision guide

| Signal | Layout |
|---|---|
| Single team, one deployable | Single Mix app + contexts |
| Multiple teams, hard compile-time boundaries | Umbrella |
| Apps need different dep versions | Poncho |
| Extracting a library for Hex | Poncho → eventual Hex package |
| "Should I split?" uncertainty | **Don't split.** Use contexts inside a single app. |
| Feels like it's getting big | **Don't split.** Add contexts. |
| Code genuinely can't compile together | Umbrella or poncho (rare — usually indicates broken contexts) |

**Rule:** prefer single app + contexts until a concrete, non-ergonomic reason forces a split. Splitting is the hardest architectural decision to reverse.

---

## 6. Domain Boundaries (Contexts)

A context is a module that groups related functionality behind a public API. Phoenix calls them "contexts"; the pattern is framework-agnostic and works in any Elixir application. **The boundary module is the only public entry point. Internal modules are hidden behind `@moduledoc false`.**

> **Depth:** [data-ownership-deep.md](data-ownership-deep.md) — aggregate design, context boundaries, multi-tenancy. [architecture-patterns.md](architecture-patterns.md) §3.4 — context design within a modular monolith.

### 6.1 Entities vs use cases

Domain code has two kinds of logic. Distinguish them when designing.

**Entities** — core business rules that exist regardless of the application. Pure data structures with functions that enforce invariants:

```elixir
defmodule MyApp.Orders.Order do
  @moduledoc false
  defstruct [:id, :items, :status, :total]

  def calculate_total(%__MODULE__{items: items}) do
    Enum.reduce(items, Decimal.new(0), &Decimal.add(&2, &1.subtotal))
  end

  def can_cancel?(%__MODULE__{status: status}), do: status in [:pending, :confirmed]
end
```

**Use cases** — application-specific orchestration. Each public function in a context module is a use case. It coordinates entities, calls infrastructure through behaviours, returns `{:ok, _} | {:error, _}`:

```elixir
defmodule MyApp.Orders do
  @moduledoc "Order lifecycle — placement, cancellation, fulfillment."
  alias MyApp.Orders.Order

  def cancel_order(order_id) do
    with {:ok, order} <- fetch_order(order_id),
         true <- Order.can_cancel?(order),
         {:ok, order} <- mark_cancelled(order),
         :ok <- notify_cancellation(order) do
      {:ok, order}
    else
      false -> {:error, :not_cancellable}
      error -> error
    end
  end
end
```

**For most Elixir applications**, keep entities as internal modules (`@moduledoc false`) and use cases as public context functions. Separate them explicitly only when entity rules are complex enough to warrant independent testing and reuse across multiple use cases.

### 6.2 When to create a new context

**Create a new context when:**

- Different business domain (Catalog vs. ShoppingCart vs. Accounts)
- Different teams will own the code
- Data has a distinct lifecycle (orders vs. products)
- Entities have different consistency requirements
- When in doubt — prefer separate contexts. Merging is easier than splitting later.

**DON'T split when:**

- Entities share the same aggregate root (Order and OrderItem — same context)
- Operations always change together in a transaction
- Splitting would require constant cross-context calls
- The contexts would be thin wrappers around a shared set of operations

**Smell tests that say "split this":**

- The context file is over ~800 lines of public functions
- Two clusters of functions never reference each other's data
- Different teams keep stepping on each other's changes
- One set of functions changes for reason A, another for reason B (single-responsibility violation)

### 6.3 Aggregates — the consistency boundary

An **aggregate** is a cluster of entities that must be consistent as a unit. The **aggregate root** is the entity you load, validate, and save as a whole. In Ecto this maps to `cast_assoc` / `cast_embed`:

```elixir
defmodule MyApp.Orders.Order do
  use Ecto.Schema

  schema "orders" do
    field :status, Ecto.Enum, values: [:pending, :confirmed, :shipped]
    has_many :items, MyApp.Orders.OrderItem, on_replace: :delete
    timestamps()
  end

  def changeset(order, attrs) do
    order
    |> cast(attrs, [:status])
    |> cast_assoc(:items)                    # Items validated + saved WITH the order
    |> validate_at_least_one_item()
  end
end

# Context operates on the aggregate root, never individual items
defmodule MyApp.Orders do
  def add_item(order, item_attrs) do
    items = order.items ++ [item_attrs]
    update_order(order, %{items: items})     # Whole aggregate saved together
  end
end
```

**Aggregate rules:**

- Never load or save parts of an aggregate independently — always go through the root
- Each aggregate is a transaction boundary — one `Repo.insert`/`update` per aggregate
- Different aggregates communicate through the context's public API, not direct associations
- If two entities must be consistent, they belong in the same aggregate → same context

### 6.4 Boundary structure template

```elixir
# With Ecto (Phoenix, database-backed apps)
defmodule MyApp.Catalog do
  @moduledoc "Product catalog management."

  import Ecto.Query, warn: false
  alias MyApp.Repo
  alias MyApp.Catalog.{Product, Category}

  # Queries
  def list_products, do: Repo.all(Product)
  def get_product!(id), do: Repo.get!(Product, id)

  # Commands
  def create_product(attrs \\ %{}) do
    %Product{}
    |> Product.changeset(attrs)
    |> Repo.insert()
  end
end

# Without Ecto (Nerves, CLI, pure OTP services)
defmodule MyFirmware.Sensors do
  @moduledoc "Sensor reading and calibration."
  alias MyFirmware.Sensors.{Reader, Calibration}

  defdelegate read(sensor_id), to: Reader
  defdelegate calibrate(sensor_id, reference), to: Calibration

  def read_calibrated(sensor_id) do
    with {:ok, raw} <- Reader.read(sensor_id),
         {:ok, cal} <- Calibration.get(sensor_id) do
      {:ok, Calibration.apply(raw, cal)}
    end
  end
end
```

**Internal modules are private to the boundary:**

```elixir
defmodule MyApp.Catalog.Product do
  @moduledoc false                          # Internal — not part of public API
  use Ecto.Schema
  # ...
end
```

**Context organization inside a context:**

```
lib/my_app/catalog/
├── product.ex              # Schema (internal)
├── category.ex             # Schema (internal)
├── product_queries.ex      # Complex query builders (internal)
├── import_worker.ex        # Background processing (internal)
└── price_calculator.ex     # Pure business logic (internal)
```

All internal modules are private. Only `MyApp.Catalog` is the public API.

### 6.5 Context relationships (context mapping)

Contexts don't exist in isolation — they relate to each other in specific ways.

| Relationship | Meaning | Elixir implementation |
|---|---|---|
| **Shared kernel** | Two contexts share a data structure | Shared module in a common namespace (e.g., `MyApp.Shared.Money`) |
| **Customer-supplier** | One context serves another | Supplier exposes public API, customer calls it |
| **Conformist** | You adapt to an external model | Anti-corruption layer translates their types to yours |
| **Separate ways** | Contexts are independent | No direct communication, possibly PubSub |

### 6.6 Anti-corruption layer (ACL)

When integrating with external or legacy systems, translate their data model to yours at the boundary. **Never let foreign data structures leak into your domain.**

```elixir
# BAD — external API's data model leaks into domain
def process_payment(stripe_charge) do
  if stripe_charge["status"] == "succeeded" do
    update_order(stripe_charge["metadata"]["order_id"], stripe_charge["amount"])
  end
end

# GOOD — anti-corruption layer translates at the boundary
defmodule MyApp.PaymentGateway.Stripe do
  @behaviour MyApp.PaymentGateway

  @impl true
  def charge(amount, token) do
    case Stripe.Charge.create(%{amount: amount, source: token}) do
      {:ok, charge} -> {:ok, to_domain_result(charge)}
      {:error, err} -> {:error, to_domain_error(err)}
    end
  end

  # Translation layer — Stripe's model → our domain model
  defp to_domain_result(charge) do
    %{transaction_id: charge.id, amount: charge.amount, captured_at: DateTime.utc_now()}
  end

  defp to_domain_error(%{code: "card_declined"}), do: :card_declined
  defp to_domain_error(%{code: "expired_card"}), do: :card_expired
  defp to_domain_error(_), do: :payment_failed
end
```

**Rule:** The behaviour adapter IS the anti-corruption layer. All translation between external and domain models happens in the adapter module. Domain code never sees external data structures.

### 6.7 API design for contexts

When designing a context's public API:

| Design choice | Why |
|---|---|
| Each public function is a use case | Not just a CRUD wrapper — name it by business intent (`register_user`, not `insert_user`) |
| Return `{:ok, _} / {:error, _}` | Consistent, composable with `with` |
| Keyword options at the end | Easy to extend without breaking callers |
| Validate options with `Keyword.validate!/2` | Reject typos, document accepted options |
| `defdelegate` for pure pass-through to internals | Keeps context as a clean facade |
| Regular `def` when you add logging, telemetry, cross-cutting logic | The context is more than a namespace — it's the place for cross-cutting concerns |

```elixir
defmodule MyApp.Catalog do
  # Pure pass-through — defdelegate
  defdelegate get_product!(id), to: Product, as: :fetch!

  # Wrapper with cross-cutting concerns
  def calculate_price(product, qty) do
    product
    |> PriceCalculator.total(qty)
    |> tap(fn total -> :telemetry.execute([:catalog, :priced], %{total: total}) end)
  end

  # Keyword options pattern
  def list_products(opts \\ []) do
    opts = Keyword.validate!(opts, category: nil, in_stock: nil, limit: 50)
    # ...
  end
end
```

---

## 7. Data Ownership & Consistency

> **Depth:** [data-ownership-deep.md](data-ownership-deep.md) — aggregate design, multi-tenancy strategies (row-level/schema-per-tenant/DB-per-tenant), cross-context transactions, sagas, idempotency patterns, data ownership migration path.

### 7.1 Who owns the data?

**Every table (or storage location) is owned by exactly one context. That context is the only one allowed to write.** Other contexts read through the owning context's public API.

```elixir
# Accounts OWNS users — only Accounts writes
defmodule MyApp.Accounts do
  def create_user(attrs) do
    %User{} |> User.changeset(attrs) |> Repo.insert()
  end
  def get_user!(id), do: Repo.get!(User, id)
end

# Orders REFERENCES users — never writes to users table
defmodule MyApp.Orders do
  def create_order(user_id, items) do
    user = MyApp.Accounts.get_user!(user_id)   # Read via owning context
    # ... create order with user_id foreign key
  end
end
```

**When two contexts seem to need the same table:** either one owns it and the other reads through the API, or the data belongs in a shared kernel module. Never have two contexts writing to the same table.

**Cross-context foreign keys are fine**, but always fetch data through the owning context's public API. Never `Repo.preload` across context boundaries.

### 7.2 Cross-context transactions

What happens when an operation spans multiple contexts?

```elixir
# BAD — reaching into multiple contexts' internals in one transaction
Repo.transaction(fn ->
  Repo.insert!(%Order{...})             # Orders context data
  Repo.update!(%Product{stock: ...})    # Catalog context data
  Repo.insert!(%Payment{...})           # Billing context data
end)
```

**Three options:**

**Option 1 — Saga pattern** (sequence of compensating operations):

```elixir
defmodule MyApp.OrderSaga do
  def place_order(user_id, items) do
    with {:ok, reservation} <- Catalog.reserve_stock(items),
         {:ok, payment} <- Billing.charge(user_id, total(items)),
         {:ok, order} <- Orders.create(user_id, items, payment.id) do
      {:ok, order}
    else
      {:error, :payment_failed} ->
        Catalog.release_stock(reservation)    # Compensating action
        {:error, :payment_failed}
      {:error, :out_of_stock} ->
        {:error, :out_of_stock}
    end
  end
end
```

**Option 2 — Eventual consistency** (async side effects):

```elixir
def place_order(user_id, items) do
  with {:ok, order} <- Orders.create(user_id, items) do
    Oban.insert(StockReductionWorker.new(%{order_id: order.id}))
    Oban.insert(PaymentChargeWorker.new(%{order_id: order.id}))
    {:ok, order}
  end
end
```

**Option 3 — Merge contexts** if they always change together:

If Orders and Billing are always modified in the same transaction, they belong in the same context — the split was premature.

### 7.3 Cross-context transaction decision

| Operation characteristic | Strategy |
|---|---|
| Operations always happen together, synchronously | Merge into one context, use `Ecto.Multi` |
| Operations can fail independently | Saga with compensating actions |
| Eventual consistency is acceptable | Async via Oban |
| Full audit trail required | Event sourcing with process managers |

### 7.4 Idempotency — design for retries

**Any operation that may be retried must be idempotent** — executing it multiple times produces the same result as executing once.

```elixir
# BAD — not idempotent; double-charges on retry
def charge_order(order_id) do
  order = Orders.get_order!(order_id)
  PaymentGateway.charge(order.total, order.token)   # Charges every time!
end

# GOOD — idempotent; check if already done
def charge_order(order_id) do
  order = Orders.get_order!(order_id)
  case order.payment_status do
    :charged -> {:ok, order}                         # Already done
    :pending ->
      with {:ok, result} <- PaymentGateway.charge(order.total, order.token) do
        Orders.mark_charged(order, result.transaction_id)
      end
  end
end

# GOOD — idempotency via Oban unique constraints
%{order_id: order.id}
|> ChargeWorker.new(unique: [period: 300, keys: [:order_id]])
|> Oban.insert()

# GOOD — idempotency via DB constraints
def record_event(event_id, data) do
  %Event{id: event_id, data: data}
  |> Repo.insert(on_conflict: :nothing)              # Silently skip duplicates
end
```

**Operations that MUST be idempotent:**

- Oban workers (retried on failure)
- Webhook handlers (provider may retry)
- Event handlers / projectors (may replay)
- Anything called via `:erpc` or HTTP (network may retry)
- Saga compensating actions

### 7.5 Eventual consistency

When contexts communicate asynchronously, different parts may temporarily disagree.

**Rules:**

- Accept eventual consistency for non-critical reads (dashboards, analytics, search)
- Require strong consistency for financial operations (use `Ecto.Multi` or saga)
- Show clear state indicators in UI ("processing", "confirmed", "failed")
- Design event handlers to be idempotent — they may process the same event twice
- Use optimistic UI updates (show expected state immediately, correct via PubSub later)

### 7.6 Multi-tenancy

**Decide the tenancy strategy at project start.** Retrofitting is painful.

| Strategy | Isolation | Complexity | When to use |
|---|---|---|---|
| **Row-level** (tenant_id column) | Low — shared tables | Low | Most SaaS apps; single database; simplest |
| **Schema-per-tenant** (Postgres schemas) | Medium — separate tables, shared DB | Medium | Stronger isolation; moderate tenant count (<1000) |
| **Database-per-tenant** | High — full isolation | High | Regulatory requirement; very different data sizes; separate backups |

**Row-level (default — start here):**

Every table has a `tenant_id` column. Enforce at the data layer — never rely on callers remembering to filter:

```elixir
# Repo-level enforcement via prepare_query
defmodule MyApp.Repo do
  use Ecto.Repo, otp_app: :my_app

  @impl true
  def prepare_query(_operation, query, opts) do
    case opts[:tenant_id] || Process.get(:current_tenant_id) do
      nil -> {query, opts}
      tenant_id -> {where(query, tenant_id: ^tenant_id), opts}
    end
  end
end
```

**Architectural rules for multi-tenancy:**

1. Choose tenant strategy early — it affects every context, every query, every migration
2. Tenant scoping is infrastructure, not domain — enforce in the repo/data layer, not scattered across contexts
3. Pass `tenant_id` explicitly OR set it once at the interface boundary (Plug, GenServer init) — don't scatter tenant resolution
4. For schema- or DB-per-tenant, each tenant may need its own process subtree (connection pool, cache, workers)
5. **Test with multiple tenants.** The #1 multi-tenancy bug is data leaking between tenants.

---

## 8. Process Architecture

The supervision tree IS the architecture. Start order expresses dependencies, strategy expresses coupling, and the error kernel concept organizes what must survive.

> **Depth:** [process-topology.md](process-topology.md) — supervision tree design, error kernel, process patterns (service/entity/hybrid), stateful vs stateless, instructions pattern, callback module pattern. [otp-design.md](otp-design.md) — GenServer vs Task vs Agent vs `:gen_statem` vs ETS vs `:persistent_term` vs GenStage vs Oban — the OTP construct choice.

### 8.1 Do you need a process at all?

The first process-architecture question. Most code does NOT need a process.

| Situation | Need a process? |
|---|---|
| Pure data transformation | **No** — pure function |
| Stateless request / response (CRUD) | **No** — context + Repo |
| State that lives for one function call | **No** — pass as arg, return new state |
| State shared across MULTIPLE callers | **Yes** |
| Serializing access to a single resource (one writer) | **Yes** — GenServer |
| State that must survive a crash | **Yes** (supervised) + recovery strategy |
| Long-running scheduled work | **Yes** (GenServer or Oban) |
| Parallel independent work | **Task** (short-lived) or GenServer (long-lived) |
| Per-entity state (user, game, device) | **Yes** — DynamicSupervisor + Registry |

**Rule:** Default to pure functions and stateless context calls. Introduce a process only when a concrete requirement forces it.

### 8.2 Error kernel design

The **error kernel** is the minimal set of processes that must not fail for the system to function. Everything else is expendable and can crash freely.

```
Application Supervisor (:one_for_one)
├── Telemetry              # Must survive (observability)
├── Repo                   # Must survive (data access)
├── PubSub                 # Must survive (communication)
│
│   ─── ERROR KERNEL BOUNDARY ───
│   Above: stable infrastructure.
│   Below: volatile, can crash and recover.
│
├── DomainServices (:rest_for_one supervisor)
│   ├── Cache              # Volatile — rebuilt from DB on restart
│   ├── EventProcessor     # Volatile — replays from last checkpoint
│   └── NotificationQueue  # Volatile — Oban persists pending jobs
├── WorkerManager (:one_for_all supervisor)
│   ├── WorkerRegistry     # Tightly coupled pair
│   └── WorkerSupervisor   # DynamicSupervisor for workers
└── Endpoint               # Web — last (serve only when ready)
```

**Design principles:**

- Critical state (DB, PubSub, telemetry) starts FIRST and lives at the TOP
- Volatile processes (caches, processors, workers) live BELOW — they can crash and recover
- Workers under DynamicSupervisor are fully expendable — each crash is isolated
- Endpoint starts LAST — don't accept traffic until the system is ready

### 8.3 Supervision as architecture

The supervision tree encodes three things:

1. **Start order** — dependency order (top to bottom)
2. **Restart strategy** — coupling between children
3. **Placement in the tree** — blast radius of a crash

**Supervision strategy — decision table:**

| Strategy | Restarts | Use when |
|---|---|---|
| `:one_for_one` | Only the crashed child | Children are independent (default at top level) |
| `:rest_for_one` | Crashed child + all children started AFTER it | Later children depend on earlier ones |
| `:one_for_all` | All children | Children are tightly coupled; must restart together |

**Architectural rules expressed through supervision:**

- **Start order = dependency order** — children listed first start first
- **`:rest_for_one`** = later children depend on earlier ones (Cache → Processor → Notifier)
- **`:one_for_all`** = tightly coupled subsystem (Registry + DynamicSupervisor MUST be in sync)
- **`:one_for_one`** at top level = independent subsystems
- **Endpoint last** = don't accept requests until everything is ready

### 8.4 Which OTP construct for the process?

Given you've decided a process is needed, which construct?

| Need | Construct | Why |
|---|---|---|
| One-off async side-effect work, supervised | `Task.Supervisor.start_child/2` | Supervised, no state |
| Parallel map with concurrency control | `Task.async_stream/3,5` | Built-in concurrency + backpressure |
| Long-running worker with state | GenServer | Standard behaviour, well-tooled |
| Explicit state machine with transitions | `:gen_statem` | Cleaner than huge `case` in GenServer |
| Single-value concurrent update | `Agent` | Lightweight wrapper around GenServer |
| Read-heavy shared data | ETS | Avoids GenServer bottleneck |
| Atomic counters / gauges | `:counters` / `:atomics` | Lock-free, very fast |
| Rarely-changing global config | `:persistent_term` | O(1) reads; expensive writes |
| Backpressured data pipeline | GenStage / Broadway | Designed for flow control |
| Persistent job queue with retries | Oban | Durable, observable |
| Many transient processes (per-entity) | DynamicSupervisor + Registry | Start/stop dynamically, find by key |
| Pub/sub within a node | `Registry :duplicate` or `Phoenix.PubSub` | Native dispatch |

**For implementation details of each**, load `elixir-implementing` §9.

### 8.5 Stateful vs stateless design

A key decision: should a process hold state in memory, or reconstruct it from a data store on each call?

| Approach | Trade-off | Use when |
|---|---|---|
| **Stateless** (reconstruct from DB on each call) | Slower reads, crash-resilient | CRUD operations, request handlers, most web contexts |
| **Stateful** (state in process memory) | Fast reads, state lost on crash | Real-time data, caches, active sessions, hardware connections |
| **Hybrid** (process state + periodic persistence) | Best of both, more complex | Game state, long-running workflows, IoT device state |

**The decision rule:** Hold state in a process only when you need it — for performance (avoid repeated DB hits), for real-time responsiveness (sub-ms access), or because the state has no durable store (hardware connections, WebSocket sessions, in-flight computations).

**Recovery strategy for stateful processes:**

Every stateful process must answer: **what happens on crash?**

- Reconstruct from DB on restart (event sourcing, periodic snapshots)
- Accept empty state (cache, ephemeral session)
- Fetch from peer (clustered cache replication)
- Crash means data loss (acceptable for purely ephemeral processes)

If you can't answer this, the process shouldn't be stateful.

### 8.6 Process architecture patterns

**Process-per-service (most common):**

One long-lived process per service capability, not per entity:

```elixir
children = [
  MyApp.Repo,              # One DB connection pool
  MyApp.Cache,             # One cache service
  MyApp.Mailer,            # One email sender
  MyApp.RateLimiter        # One rate limiting service
]
```

**Use when:** Service has shared state (connection pool, cache, counters). This is the default for most applications.

**Process-per-entity (when needed):**

One process per domain entity, each managing its own state:

```elixir
# Game server — one process per active game
DynamicSupervisor.start_child(GameSupervisor, {GameServer, game_id: id})

# IoT device — one process per connected device
DynamicSupervisor.start_child(DeviceSupervisor, {DeviceHandler, device_id: id})
```

**Use when:** Entities have independent state, need isolated failure domains, or communicate asynchronously. **Watch for:** memory scales linearly with entity count.

**Hybrid — Service + Entity Pool:**

Service process manages lifecycle, DynamicSupervisor manages instances:

```elixir
defmodule MyApp.GameManager do
  def start_game(params) do
    game_id = generate_id()
    {:ok, _pid} = DynamicSupervisor.start_child(
      MyApp.GameSupervisor,
      {MyApp.GameServer, {game_id, params}}
    )
    {:ok, game_id}
  end
  def find_game(game_id), do: MyApp.GameRegistry.lookup(game_id)
end
```

### 8.7 The Instructions Pattern (for complex domain + side-effects)

When domain logic needs to trigger side effects (notifications, messages, I/O), don't perform them inline. Instead, pure domain functions return a list of **instructions** — data describing what should happen — and the caller (GenServer, controller, test) interprets them.

```elixir
# Pure domain module — no side effects, no process mechanics
defmodule MyApp.Workflow do
  defstruct [:state, :participants, instructions: []]

  @spec advance(t(), participant_id(), action()) :: {[instruction()], t()}
  def advance(workflow, participant_id, action) do
    workflow
    |> validate_participant(participant_id)
    |> apply_action(action)
    |> maybe_transition()
    |> emit_instructions()
  end

  # Returns instructions like:
  # [
  #   {:notify, participant_id, {:status_changed, :approved}},
  #   {:notify, reviewer_id, {:task_assigned, task}},
  #   {:schedule, {:deadline, task_id}, :timer.hours(24)}
  # ]
end

# GenServer interprets the instructions
defmodule MyApp.WorkflowServer do
  use GenServer

  @impl true
  def handle_call({:advance, pid, action}, _from, state) do
    {instructions, workflow} = MyApp.Workflow.advance(state.workflow, pid, action)
    execute_instructions(instructions, state)
    {:reply, :ok, %{state | workflow: workflow}}
  end
end
```

**Benefits:**

- Domain logic is pure and trivially testable — assert on returned instructions, no mocking needed
- Multiple drivers — same domain module can be driven by GenServer, LiveView, test, or IEx
- Temporal concerns (retries, timeouts, delivery) stay out of domain

**Use when:** The domain has complex state transitions and multiple kinds of side effects. For simple GenServers, normal delegation to pure helpers (Principle 6) is enough.

### 8.8 Anti-patterns in process design

**Simulating objects with processes (very common mistake):**

```elixir
# BAD — one Agent per domain concept
cart_agent = Agent.start_link(fn -> Cart.new() end)
inventory_agent = Agent.start_link(fn -> Inventory.new(products) end)
# Every operation now requires cross-process messaging to coordinate
Agent.update(cart_agent, fn cart ->
  item = Agent.get(inventory_agent, fn inv -> Inventory.take(inv, sku) end)
  Cart.add(cart, item)
end)

# GOOD — pure functional abstractions — modules and functions, no processes
cart = Cart.new()
{:ok, item, inventory} = Inventory.take(inventory, sku)
cart = Cart.add(cart, item)
# Simple, testable, no overhead.
```

**Rule:** Use functions and modules to separate *thought concerns* (domain concepts in your mental model). Use processes to separate *runtime concerns* (fault isolation, parallelism, independent lifecycles). If multiple concepts always change together in one flow, they belong in the same process (or no process at all).

**Decision test:** Ask "do these things need to fail independently? Run in parallel? Have different lifecycles?" If not, they belong together.

**Other process anti-patterns:**

```elixir
# BAD — GenServer.call for reads on a hot path (bottleneck)
def get(key), do: GenServer.call(__MODULE__, {:get, key})
# Every reader serializes through the GenServer.

# GOOD — direct ETS read (no serialization)
def get(key) do
  case :ets.lookup(:my_table, key) do
    [{^key, v}] -> {:ok, v}
    [] -> :error
  end
end
```

```elixir
# BAD — Registry + DynamicSupervisor under :one_for_one
# If Registry crashes, DynamicSupervisor's children can't re-register
children = [
  {Registry, keys: :unique, name: MyApp.Registry},
  {DynamicSupervisor, name: MyApp.DynSup}
]
Supervisor.init(children, strategy: :one_for_one)   # WRONG

# GOOD — :rest_for_one (or dedicated :one_for_all sub-supervisor)
Supervisor.init(children, strategy: :rest_for_one)
```

---

## 9. Inter-Context Communication

How contexts talk to each other is a critical architectural decision. The six mechanisms, in order of escalating complexity — **start with the simplest**, escalate only when the current one fails.

> **Depth:** [integration-patterns.md](integration-patterns.md) — six mechanisms in full depth, capacity planning, escalation triggers, sagas, process managers, external brokers (Kafka/SQS/RabbitMQ), cross-Elixir with `:erpc`/`:pg`.

### 9.1 Pattern 1: Direct function calls (default)

The simplest approach. Context A calls Context B's public API directly.

```elixir
defmodule MyApp.ShoppingCart do
  alias MyApp.Catalog

  def add_item_to_cart(cart, product_id) do
    product = Catalog.get_product!(product_id)   # Through Catalog public API
    # ... NOT Repo.get!(Product, id) — never reach into another context's data
  end
end
```

**Use when:** Synchronous, request-scoped, simple dependency. The caller needs the result immediately. **This is the right default for most cross-context calls.**

**Properties:** Zero persistence, zero backpressure, zero cross-node. You get a direct return value synchronously. If the callee is slow, your caller is slow.

### 9.2 Pattern 2: PubSub (fire-and-forget events)

Decoupled asynchronous communication — the publisher doesn't know or care who listens.

**Two options:**

- **`Phoenix.PubSub`** (if Phoenix is a dep) — topic-based, pluggable adapters
- **`:pg`** (Erlang built-in, OTP 23+) — process groups, no dependencies, cross-node

```elixir
# Phoenix.PubSub
Phoenix.PubSub.subscribe(MyApp.PubSub, "orders")
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:order_completed, order})

# Erlang :pg
:pg.join(:my_app_pubsub, "orders", self())
:pg.get_members(:my_app_pubsub, "orders") |> Enum.each(&send(&1, {:order_completed, order}))
```

**Limitations (both):**

- **No persistence** — subscriber down when event fires = event lost forever
- **No backpressure** — fast publisher overwhelms slow subscriber; mailbox grows unbounded
- **No ordering guarantees** — across nodes, messages may arrive out of order
- **No delivery confirmation** — publisher doesn't know if anyone received

**Use when:** UI updates (LiveView), notifications where occasional loss is OK, decoupling contexts where subscribers can tolerate missed events, in-process event fan-out.

### 9.3 Pattern 3: Registry for fine-grained PubSub

When PubSub topics are too coarse, use Registry with `:duplicate` keys for per-entity subscriptions.

```elixir
# Subscribe to specific entity events
Registry.register(MyApp.EventRegistry, {:order, order_id}, [])

# Broadcast to specific entity subscribers only
Registry.dispatch(MyApp.EventRegistry, {:order, order_id}, fn entries ->
  for {pid, _} <- entries, do: send(pid, {:order_updated, order})
end)
```

**Use when:** Per-entity subscriptions (e.g., LiveView watching one order). More efficient than broad PubSub topics with many entities.

**Limitations:** Single-node only (for cross-node per-entity dispatch, use `:pg` or Phoenix.PubSub with sharded topic).

### 9.4 Pattern 4: GenStage / Broadway (backpressure pipelines)

**GenStage** solves a fundamental problem: what happens when producers are faster than consumers? PubSub has no answer — mailboxes grow unbounded until crash. GenStage inverts control — consumers request data when ready (demand-driven).

```elixir
# Producer: buffers events, dispatches on demand
defmodule MyApp.OrderProducer do
  use GenStage
  def start_link(_), do: GenStage.start_link(__MODULE__, :ok, name: __MODULE__)
  def init(:ok), do: {:producer, %{queue: :queue.new()}}

  def notify(event), do: GenStage.cast(__MODULE__, {:notify, event})

  # ... dispatch events to consumers based on demand
end

# Consumer: processes at its own pace
defmodule MyApp.OrderProcessor do
  use GenStage
  def init(:ok), do: {:consumer, :ok, subscribe_to: [{MyApp.OrderProducer, max_demand: 10}]}

  def handle_events(events, _from, state) do
    Enum.each(events, &process_order/1)
    {:noreply, [], state}
  end
end
```

**Broadway** wraps GenStage with a declarative API, batching, fault tolerance, and built-in adapters for message brokers.

**Choose GenStage over PubSub / plain messaging when:**

- Producer rate is variable / bursty and can exceed consumer throughput
- Data loss is unacceptable
- You need multi-stage transformation pipelines (producer → filter → transform → persist)
- Processing involves I/O that creates natural bottlenecks
- You need concurrency control

**Choose Broadway over raw GenStage when:**

- Consuming from an external broker (Kafka, SQS, RabbitMQ, Redis Streams)
- You need batching (accumulate N items, flush together)
- You want declarative concurrency config
- You need built-in fault tolerance, graceful shutdown, telemetry

**Don't use GenStage when:**

- Fan-out to UI (LiveView updates) — use PubSub, consumers are fast
- Occasional loss is acceptable (notifications, analytics)
- No transformation pipeline — just broadcast and forget

### 9.5 Pattern 5: Oban (persistent job queue)

When events must survive restarts, need scheduling, retries, and guaranteed execution.

```elixir
defmodule MyApp.Workers.SendConfirmation do
  use Oban.Worker, queue: :emails, max_attempts: 5

  @impl true
  def perform(%Oban.Job{args: %{"order_id" => order_id}}) do
    order = MyApp.Orders.get_order!(order_id)
    MyApp.Mailer.send_confirmation(order)
    :ok
  end
end

# In your context
def complete_order(order) do
  with {:ok, order} <- mark_completed(order) do
    %{order_id: order.id}
    |> MyApp.Workers.SendConfirmation.new()
    |> Oban.insert()
    {:ok, order}
  end
end
```

**Use when:**

- Jobs must not be lost (email, webhooks, billing)
- Need retries with backoff
- Need scheduling (run at specific times, cron)
- Need uniqueness constraints (deduplicate)

**Properties:** Persistent (PostgreSQL), backpressure via queue limits, cross-node (shared DB).

### 9.6 Pattern 6: Event sourcing / Commanded (full audit + replay)

Full history, replay, and complex multi-aggregate workflows.

**Use when:**

- Perfect audit trail is a business requirement (compliance)
- Complex long-lived processes (insurance claims, loan origination)
- Undo / replay capabilities needed
- Multiple very different read projections of the same data

**Defer to `event-sourcing` skill for implementation.**

### 9.7 Sagas and process managers

For multi-step workflows that must complete or compensate:

- **Explicit saga** — a function that calls context operations in sequence with explicit rollback on failure (§7.2 Option 1)
- **Process manager** (Commanded) — long-lived process that listens for events and emits commands in response; handles timeouts and retries declaratively

**Choose explicit saga when:** Workflow is bounded (few steps, fast completion). You can see the whole flow in one function.

**Choose process manager when:** Workflow is long-lived (minutes/days), driven by events, needs to wait for external completion.

### 9.8 Communication decision guide

| Need | Mechanism | Persistence | Backpressure | Cross-Node |
|---|---|---|---|---|
| Simple sync call | Direct function | N/A | N/A | No |
| UI updates, notifications | Phoenix.PubSub / :pg | No | No | Yes |
| Per-entity subscriptions | Registry (`:duplicate`) | No | No | No |
| High-throughput pipeline | GenStage / Broadway | No (in-flight) | **Yes** | No |
| Reliable async jobs | Oban | **Yes** (PostgreSQL) | Yes (queue limits) | **Yes** |
| Full audit + replay | Commanded | **Yes** (event store) | Via subscriptions | **Yes** |
| Cross-service messaging | External broker + Broadway | **Yes** | **Yes** | **Yes** |

### 9.9 Escalation path — when to move up the ladder

**Start with direct function calls. Escalate only when the current mechanism fails:**

```
Direct function call
  ↓ (need async / decoupling)
PubSub
  ↓ (PubSub subscriber mailbox growing? fast publisher, slow consumer?)
GenStage / Broadway
  ↓ (events lost on deploy/crash?)
Oban
  ↓ ("what happened and when?" / replay / compliance?)
Event sourcing (Commanded)
```

**Signals you've outgrown your current mechanism:**

- PubSub subscriber mailbox growing → need GenStage (backpressure)
- Events lost during deploys / crashes → need Oban (persistence)
- Need to batch writes for performance → need Broadway (batching)
- "What happened and when?" questions → need event sourcing (audit trail)

**Do not skip steps.** Each escalation adds complexity; unjustified complexity compounds.

---

## 10. Configuration Strategy

### 10.1 Config file roles

| File | Loaded when | Use for |
|---|---|---|
| `config/config.exs` | Compile time | Defaults, application-owned compile-time values |
| `config/dev.exs` | Compile time (dev only) | Dev overrides (verbose logs, dev tooling) |
| `config/test.exs` | Compile time (test only) | Mox wiring, small pool sizes, test adapters |
| `config/runtime.exs` | Boot time (after release assembly) | Per-deployment env vars, secrets |

### 10.2 Compile-time vs runtime — decision

| Value character | API | File |
|---|---|---|
| Known at build, app-owned, immutable per release | `Application.compile_env!(:my_app, :key)` | `config/config.exs` |
| Per-deployment env var | `System.fetch_env!("VAR")` + `Application.get_env` | `config/runtime.exs` |
| Library consumer configures | `Application.get_env(:my_lib, :key, default)` at runtime; options to `start_link` | Caller's config files |
| Feature flag (toggleable without deploy) | External (FunWithFlags, Flagsmith, DB row, ETS) | Outside `config/*.exs` |
| Test-specific override | `config :my_app, ...` | `config/test.exs` |

### 10.3 Library vs application config

**Applications** can use `Application.compile_env` safely — they control their own build:

```elixir
defmodule MyApp.Cache do
  @ttl Application.compile_env!(:my_app, [:cache, :ttl])
  def ttl, do: @ttl
end
```

**Libraries MUST NOT** use `Application.compile_env` — consumers can't reconfigure after compilation:

```elixir
# BAD (in a library)
defmodule MyLib.Client do
  @api_key Application.compile_env!(:my_lib, :api_key)
  def call, do: request(@api_key)
end

# GOOD (in a library)
defmodule MyLib.Client do
  def call, do: request(api_key())
  defp api_key, do: Application.get_env(:my_lib, :api_key) ||
                      raise "configure :my_lib, :api_key"
end

# BEST (in a library) — accept as argument
defmodule MyLib.Client do
  def call(opts), do: request(Keyword.fetch!(opts, :api_key))
end
```

### 10.4 Configuration handoff to `elixir-implementing`

The implementation patterns for reading config (at-runtime vs at-boot, `fetch_env!` vs `get_env`) are in `elixir-implementing` §8.6. This section is about **where values live** and **why** — the planning decision.

---

## 11. Resilience Planning

> **Related subskill:** [integration-patterns.md](integration-patterns.md) §10 — resilience at integration boundaries (circuit breakers around adapters, retries by layer, graceful degradation, timeout cascades).

OTP provides resilience primitives that other ecosystems need external libraries for. These patterns are **architectural** — they determine where failure handling lives and how subsystems degrade.

### 11.1 BEAM processes as bulkheads

Every BEAM process is an isolated failure domain — its own heap, its own GC, its own crash boundary. **This IS the bulkhead pattern.** When one process crashes, others are unaffected.

```elixir
children = [
  # If email sending fails, order processing continues
  {MyApp.Mailer.Pool, pool_size: 5},
  # If payment gateway is slow, catalog browsing is unaffected
  {MyApp.PaymentWorker, []},
  # If search indexing crashes, CRUD operations work fine
  {MyApp.SearchIndexer, []}
]
```

**Architectural rule:** Different concerns run in different processes. This gives you bulkhead isolation for free. **Never run unrelated work in the same GenServer** — split it.

### 11.2 Circuit breaker — where it belongs

Prevent cascading failures by stopping calls to a failing subsystem. In Elixir, implement with a GenServer or use the `:fuse` library.

**Architectural placement: around infrastructure adapters** (HTTP clients, external APIs, database calls to remote services). **NEVER in domain logic.**

```elixir
defmodule MyApp.PaymentGateway.Protected do
  @behaviour MyApp.PaymentGateway

  @impl true
  def charge(amount, token) do
    case :fuse.ask(:payment_fuse, :sync) do
      :ok ->
        case MyApp.PaymentGateway.Stripe.charge(amount, token) do
          {:ok, _} = success -> success
          {:error, :timeout} -> :fuse.melt(:payment_fuse); {:error, :service_unavailable}
          {:error, _} = error -> error
        end
      :blown -> {:error, :service_unavailable}
    end
  end
end

# Supervision — fuse must start before the service that uses it
children = [
  {Fuse, name: :payment_fuse, strategy: {:standard, 5, 60_000}},   # 5 failures in 60s
  MyApp.PaymentWorker
]
```

**Rule:** The domain receives `{:error, :service_unavailable}` and decides what to do (queue for retry, show cached data, return partial result). Domain never knows a circuit breaker exists.

### 11.3 Retry and backoff — where each lives

Retries belong in infrastructure, **never** in domain logic. Different layers handle retries at different scales.

| Layer | Retry mechanism | Example |
|---|---|---|
| HTTP client | Built-in retry | `Req.new(retry: :transient, max_retries: 3)` |
| Background jobs | Job-level retry | `use Oban.Worker, max_attempts: 5` |
| Event handlers | Handler-level retry | Commanded error callback with backoff |
| GenServer | Process restart (supervisor) | `max_restarts` / `max_seconds` on supervisor |
| Infrastructure adapter | Wrapper with custom backoff | Custom retry around external call |

**Idempotency is a prerequisite for safe retries.** If an operation isn't idempotent, retrying it may cause duplicate effects. See §7.3.

### 11.4 Graceful degradation

When a subsystem is down, serve degraded functionality instead of failing entirely.

```elixir
defmodule MyApp.Catalog do
  def get_product_with_recommendations(product_id) do
    product = get_product!(product_id)

    # Recommendations are nice-to-have — degrade if service is down
    recommendations =
      case MyApp.Recommendations.for_product(product_id) do
        {:ok, recs} -> recs
        {:error, _} -> []   # Show product without recommendations
      end

    {product, recommendations}
  end
end
```

**Architectural rule:** For each feature, identify whether it's **critical** (must work) or **nice-to-have** (can degrade). Critical paths use synchronous calls with clear error handling. Nice-to-have features use `try`-style fallbacks or cached data.

### 11.5 Timeout architecture

Timeouts must be set at **every boundary**, and **outer > middle > inner**. Otherwise outer timeouts fire before inner ones with meaningless errors.

```
Phoenix endpoint   : timeout 15_000ms     (outermost)
  GenServer.call   : timeout 10_000ms     (middle)
    HTTP client    : timeout 5_000ms      (innermost)

15_000 > 10_000 > 5_000  ✓
```

**Where to set timeouts:**

- HTTP clients: `receive_timeout` in Req/Finch
- GenServer calls: second argument to `GenServer.call/3` (default 5000ms — usually too short)
- `Task.await`: second argument (default 5000ms)
- DB queries: `:timeout` option in Repo operations
- Phoenix endpoint: `:timeout` in endpoint config

### 11.6 Resilience decision guide

| Concern | Solution | Where it lives |
|---|---|---|
| External service may be slow / flaky | Circuit breaker (:fuse) | Infrastructure adapter |
| Operation may fail transiently | Retry with backoff | Client library, Oban, supervisor |
| External service is down | Graceful degradation (partial / cached / default) | Context function (orchestration) |
| Timeouts across layers | Outer > middle > inner cascade | Every layer |
| Prevent one subsystem failing another | Separate processes / supervisors | Supervision tree |
| Prevent retries from duplicating | Idempotency | Operation design |

---

## 12. Architectural Styles in Elixir

How common architectural styles map to Elixir idioms. **Many patterns that require frameworks in other languages are built into OTP.** Understand what Elixir gives you for free before reaching for external solutions.

### 12.1 What each style solves

Match a problem to an architectural approach. **Start with the simplest style.** Adopt a style because you have the specific problem it solves — not because it sounds sophisticated.

| Problem You Have | Style | Elixir Solution |
|---|---|---|
| Separate UI from logic | MVC | Thin dispatchers → contexts → structs (Elixir default) |
| Swappable external dependencies | Hexagonal / Ports & Adapters | Behaviours (ports) + implementations (adapters) + config |
| Fault isolation without separate deployments | Modular Monolith | Contexts + supervision trees (OTP default) |
| Decouple producers from consumers | Event Notification | PubSub / `:pg` — fire and forget |
| Subscribers need full data without calling back | Event-Carried State Transfer | PubSub with rich event payloads |
| Complete audit trail / state replay / compliance | Event Sourcing | Commanded — events are source of truth |
| Read and write patterns diverge | CQRS | Query modules, read replicas, or projections |
| Backpressure between fast producer and slow consumer | Demand-Driven | GenStage / Broadway |
| Side effects must survive crashes | Persistent Queue | Oban |
| Multi-step workflows must complete or compensate | Saga / Process Manager | Commanded process managers or Oban workflows |
| Different language / compliance / extreme scaling | Microservices | Separate deployments — last resort in Elixir |
| Protection against slow/failing external services | Resilience | Circuit breaker, bulkheads, timeouts |

**The default Elixir architecture** — contexts + supervision + behaviours — already gives you MVC, hexagonal, and modular monolith patterns simultaneously. **Most apps never need anything beyond this plus PubSub** for decoupling.

### 12.2 MVC — how it maps to Elixir

| Classical MVC | Elixir Reality |
|---|---|
| Model (ActiveRecord, ORM) | Contexts + schemas/structs (separated) |
| View (template / UI) | Function components, CLI formatters, display renderers |
| Controller (handles input) | Thin dispatcher — translates input, delegates to context |

| Interface | "Controller" | "View" | "Model" |
|---|---|---|---|
| Phoenix web | Controller / LiveView | HEEx templates, components | Contexts + Ecto schemas |
| CLI tool | `main/1` / escript entry | IO / formatting module | Contexts + structs |
| Nerves device | GenServer handling hardware | Display / output module | Contexts + structs |
| Library | Public API module | N/A | Internal modules |

**The LLM rule:** NEVER organize Elixir code into `models/`, `services/`, or `helpers/` directories. These are anti-patterns imported from Rails/Django. Elixir uses:

- **Contexts / boundary modules** where MVC would say "model" or "service"
- **Output / formatting modules** where MVC would say "view"
- **Thin dispatchers** where MVC would say "controller" — no business logic

```elixir
# BAD — imported "MVC" thinking
lib/my_app/
├── models/
│   └── user.ex
├── services/
│   └── user_service.ex
└── helpers/
    └── format_helper.ex

# GOOD — Elixir domain-driven structure
lib/my_app/
├── accounts.ex              # Context (boundary)
├── accounts/
│   ├── user.ex              # Schema / struct (internal)
│   └── authentication.ex    # Pure logic (internal)
└── catalog.ex               # Another context
```

### 12.3 Microservices — why Elixir rarely needs them

OTP already provides fault isolation (supervision), independent scaling (process pools), loose coupling (contexts + PubSub), and service discovery (Registry, `:pg`). **The Elixir default is the modular monolith** — one deployment, zero network hops.

**ONLY split into separate services when:**

| Signal | Why Separate Service |
|---|---|
| Different language needed | GPU service in Python/CUDA, web in Elixir |
| Regulatory / compliance isolation | Payment processing must be PCI-isolated |
| Wildly different scaling needs | Video transcoding vs. web API |
| Separate teams, separate release cycles | Organization-driven, not tech-driven |
| Legacy system integration | Wrap legacy behind an API boundary |

**NEVER split into services for:**

- "It's getting big" → add contexts
- "We want loose coupling" → use behaviours and PubSub
- "We want fault isolation" → use supervision trees
- "We want independent scaling" → process pools, Task.async_stream, Broadway

**If you must split:** Communicate via well-defined APIs (HTTP/gRPC), not shared databases. Each service owns its data. Use Broadway + message broker (Kafka, RabbitMQ) for async integration. Consider `:erpc` for Elixir-to-Elixir calls within a trusted network.

### 12.4 Event-driven architecture — three patterns

These three are often conflated. Distinguish them when designing.

**Pattern 1: Event Notification** — event carries minimal data (just an identifier).

```elixir
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:order_completed, order_id})

def handle_info({:order_completed, order_id}, state) do
  order = Orders.get_order!(order_id)    # Subscriber calls back for data
  send_confirmation(order)
  {:noreply, state}
end
```

**Trade-offs:** Simple. Publisher is decoupled. But subscriber must call back to source → creates coupling and potential N+1.

**Pattern 2: Event-Carried State Transfer** — event carries all data subscriber needs.

```elixir
event = %{
  order_id: order.id,
  customer_email: order.customer.email,
  items: Enum.map(order.items, &%{name: &1.name, qty: &1.quantity}),
  total: order.total,
  completed_at: DateTime.utc_now()
}
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:order_completed, event})

def handle_info({:order_completed, event}, state) do
  send_confirmation(event.customer_email, event)   # No callback needed
  {:noreply, state}
end
```

**Trade-offs:** Subscribers fully decoupled. Larger events. Publisher must anticipate subscriber needs.

**Pattern 3: Event Sourcing** — events ARE the source of truth. Current state is derived by replaying events. Defer to `event-sourcing` skill.

### 12.5 Event-driven decision guide

```
Do you need to decouple contexts?
├── No coupling needed               → Direct function call (not event-driven)
├── Fire-and-forget notification     → Event Notification (PubSub, :pg)
├── Subscriber needs data, no callback → Event-Carried State Transfer
├── Need backpressure                → GenStage / Broadway
├── Events must survive crashes      → Oban
└── Events ARE the source of truth   → Event Sourcing (Commanded)
```

### 12.6 CQRS — three levels

**Level 1: Light CQRS** (default — most apps already do this).

```elixir
defmodule MyApp.Catalog do
  # Queries (reads)
  def list_products, do: Repo.all(Product)
  def get_product!(id), do: Repo.get!(Product, id)

  # Commands (writes)
  def create_product(attrs), do: %Product{} |> Product.changeset(attrs) |> Repo.insert()
  def delete_product(product), do: Repo.delete(product)
end
```

**This is CQRS.** Queries return data. Commands return ok/error. Same DB serves both. For most apps, this is enough.

**Level 2: Separated Read Path** (when reads need optimization).

```elixir
# Writes: standard context
defmodule MyApp.Catalog do
  def create_product(attrs), do: ...
  def update_product(product, attrs), do: ...
end

# Reads: specialized query module
defmodule MyApp.Catalog.Queries do
  @moduledoc false
  import Ecto.Query

  def top_sellers(limit \\ 10) do
    from(p in Product,
      join: oi in OrderItem, on: oi.product_id == p.id,
      group_by: p.id,
      order_by: [desc: count(oi.id)],
      limit: ^limit
    ) |> Repo.all()
  end
end
```

**Use when:** Dashboard/reporting queries are slow and contend with writes. Search needs a different store (Elasticsearch). Read traffic is 10x+ write.

**Level 3: Full CQRS + Projections** (with event sourcing).

Writes go to an event store. Reads come from purpose-built projections (materialized views), each optimized for a specific query pattern.

**Use when:** Event sourcing already in use. Multiple very different read views. Read and write scaling needs dramatically different. Eventual consistency between read models is acceptable.

### 12.7 CQRS decision guide

| Signal | Level |
|---|---|
| Standard web app, moderate traffic | Light (1) |
| Complex reporting alongside CRUD | Separated (2) |
| Dashboard queries contend with writes | Separated (2) — read replica |
| Full audit trail + different read stores | Full (3) — event sourcing |
| "Should I use CQRS?" uncertainty | Light (1) — you're probably already doing it |

### 12.8 Styles combine — per context

Different contexts within the same application can use different styles:

```
Typical large Elixir app (modular monolith):

┌──────────────────────────────────────────────────┐
│  Accounts context          Orders context          │
│  ├─ Light CQRS             ├─ Event sourcing       │
│  ├─ Direct Ecto            │  (Commanded)          │
│  └─ Request-response       ├─ Full CQRS            │
│                            │  (projections)         │
│  Catalog context           ├─ Event-driven         │
│  ├─ Separated read path    │  (process managers)   │
│  │  (search index)         └─ Sagas for workflows  │
│  └─ Event-carried state                            │
│                                                     │
│  Notifications context                             │
│  ├─ Event notification                             │
│  │  (subscribes to PubSub)                          │
│  └─ Oban for delivery                              │
│                                                     │
│  ─── All in one Mix release, one supervision ───   │
│  ─── tree, one deployment                    ───   │
└──────────────────────────────────────────────────┘
```

**Key insight:** The boundary module (context) is what enables this — callers don't know or care what style is used internally. Start simple; evolve individual contexts into richer patterns as their domains demand.

---

## 13. Growing Architecture — Small to Large

Elixir architecture is **additive**. Do not over-engineer Stage 1. Do not under-engineer Stage 3. Know which stage you're at.

> **Depth:** [growing-evolution.md](growing-evolution.md) — full stage-by-stage evolution, symptoms → refactors, context redraws, integration mechanism escalation, when to add/remove each complexity layer.

### 13.1 Stage 1 — Small App (1–3 domains, one developer)

The simplest structure that enforces boundaries.

```elixir
defmodule MyApp.Application do
  use Application
  def start(_type, _args) do
    children = [MyApp.Repo]     # Or nothing if no database
    Supervisor.start_link(children, strategy: :one_for_one)
  end
end

defmodule MyApp.Core do
  # Single boundary module — all public API here
  # Internal modules in MyApp.Core.* with @moduledoc false
end
```

**What matters at this stage:**

- Domain logic in pure functions (testable, no process overhead)
- External dependencies behind behaviours (at least: Repo)
- One supervision tree with flat `:one_for_one`
- **No PubSub, no GenStage, no event sourcing** — add only when needed

### 13.2 Stage 2 — Medium App (3–8 domains, small team)

Split into multiple boundary modules. Add processes only where needed.

```elixir
defmodule MyApp.Application do
  use Application
  def start(_type, _args) do
    children = [
      MyApp.Repo,
      {Phoenix.PubSub, name: MyApp.PubSub},
      MyApp.Cache,                          # First GenServer — shared state
      MyAppWeb.Endpoint
    ]
    Supervisor.start_link(children, strategy: :one_for_one)
  end
end

defmodule MyApp.Accounts do ... end
defmodule MyApp.Catalog do ... end
defmodule MyApp.Billing do ... end
```

**What changes:**

- Multiple boundary modules with clear ownership
- PubSub for cross-boundary events (UI updates, notifications)
- First GenServers appear for genuinely shared mutable state
- Behaviours at external service boundaries (payment, email)
- Still one Mix application — contexts provide sufficient boundaries

### 13.3 Stage 3 — Large App (8+ domains, multiple teams)

Introduce supervision hierarchy. Consider umbrella for team boundaries.

```elixir
defmodule MyApp.Application do
  use Application
  def start(_type, _args) do
    children = [
      # Infrastructure (error kernel)
      MyApp.Telemetry,
      MyApp.Repo,
      {Phoenix.PubSub, name: MyApp.PubSub},

      # Domain services (can crash and recover)
      {Supervisor, name: MyApp.DomainSupervisor, strategy: :rest_for_one,
        children: [
          MyApp.Cache,
          MyApp.EventProcessor,
          MyApp.NotificationService
        ]},

      # Dynamic workers
      {Supervisor, name: MyApp.WorkerSupervisor, strategy: :one_for_all,
        children: [
          {Registry, keys: :unique, name: MyApp.WorkerRegistry},
          {DynamicSupervisor, name: MyApp.Workers, max_children: 10_000}
        ]},

      MyAppWeb.Endpoint                    # Last
    ]
    Supervisor.start_link(children, strategy: :one_for_one)
  end
end
```

**What changes:**

- Nested supervision tree with error kernel design
- Oban for persistent background jobs
- GenStage / Broadway for high-throughput pipelines
- Telemetry instrumentation throughout
- Consider umbrella if teams need hard compile-time boundaries
- Event sourcing for domains that need audit trails

### 13.4 What DOES NOT change between stages

These hold at every scale — never restructure them:

- Domain logic is pure functions
- External dependencies are behind behaviours
- Boundary modules are the only public API
- `{:ok, _}` / `{:error, _}` tuples for results
- Supervision tree expresses architecture

**The progression is additive.** Add GenServers, PubSub, supervision layers as needed. Never restructure the fundamentals.

### 13.5 Refactoring decision tree

```
You notice something is wrong. Where to intervene?

Symptom: Module is doing too much.
├── Same context, multiple unrelated concerns → split into multiple contexts
├── Mixing business logic with infrastructure → extract behaviour, move impl to adapter
├── Pure logic buried inside GenServer → extract to pure module, GenServer delegates
└── Domain module referencing web/framework → inversion — domain defines behaviours, framework implements

Symptom: Testing is hard.
├── Needs Repo for pure logic tests → extract pure functions, test without Repo
├── Needs HTTP for business-rule tests → put HTTP behind behaviour, mock with Mox
├── Test uses complex setup of many modules → missing boundary, extract behaviour
└── Tests are flaky async → shared state; isolate or use async: false

Symptom: Performance.
├── GenServer bottleneck on reads → move to ETS
├── Slow queries contending with writes → separated read path or read replica
├── Large data in process state → move to ETS / :persistent_term
├── Producer faster than consumer → GenStage / Broadway
└── Retry storms → exponential backoff + circuit breaker

Symptom: Reliability.
├── Lost events → upgrade PubSub → Oban
├── Crashes propagate → split supervisors, review strategies
├── Cascading failures → circuit breakers around adapters
└── Timeouts at wrong layer → cascade outer > middle > inner
```

---

## 14. Architectural Anti-Patterns

### 14.1 Wrong module layout

```elixir
# BAD — "MVC" imported from other ecosystems
lib/my_app/
├── models/
│   └── user.ex
├── services/
│   └── user_service.ex
└── helpers/
    └── format_helper.ex

# GOOD — Elixir domain-driven
lib/my_app/
├── accounts.ex
├── accounts/
│   ├── user.ex
│   └── authentication.ex
└── catalog.ex
```

### 14.2 Domain depending on framework

```elixir
# BAD — domain module references web layer
defmodule MyApp.Orders do
  alias MyAppWeb.Router.Helpers, as: Routes    # NEVER — domain depends on web!
  import Phoenix.Controller                     # NEVER — framework in domain!

  def complete_order(order) do
    url = Routes.order_url(MyAppWeb.Endpoint, :show, order)
    # ...
  end
end

# GOOD — domain is framework-agnostic
defmodule MyApp.Orders do
  def complete_order(order) do
    # Pure domain logic. URL generation belongs in controller/LiveView.
    with {:ok, order} <- mark_completed(order), do: {:ok, order}
  end
end
```

### 14.3 Interface layer calling Repo directly

```elixir
# BAD — controller queries Repo
def index(conn, _) do
  products = Repo.all(Product)
  render(conn, :index, products: products)
end

# GOOD — controller calls context
def index(conn, _) do
  products = Catalog.list_products()
  render(conn, :index, products: products)
end
```

### 14.4 God context

```elixir
# BAD — god context with unrelated concerns
defmodule MyApp.Admin do
  def list_users, do: ...
  def create_product, do: ...
  def process_payment, do: ...
  def send_notification, do: ...
end

# GOOD — separate contexts per domain
defmodule MyApp.Accounts do ... end
defmodule MyApp.Catalog do ... end
defmodule MyApp.Billing do ... end
defmodule MyApp.Notifications do ... end
```

### 14.5 Tight coupling to external services

```elixir
# BAD — domain tightly coupled to Stripe
defmodule MyApp.Billing do
  def charge(order) do
    Stripe.Charge.create(%{amount: order.total, source: order.token})
  end
end

# GOOD — behaviour-based abstraction
defmodule MyApp.Billing do
  @gateway Application.compile_env(:my_app, :payment_gateway)
  def charge(order), do: @gateway.charge(order.total, order.token)
end
```

### 14.6 Business logic in GenServer callbacks

```elixir
# BAD — business logic in the callback
def handle_call({:apply_discount, code}, _from, state) do
  discount = case code do
    "SAVE10" -> Decimal.new("0.10")
    "SAVE20" -> Decimal.new("0.20")
    _ -> Decimal.new("0")
  end
  new_total = Decimal.mult(state.total, Decimal.sub(1, discount))
  {:reply, {:ok, new_total}, %{state | total: new_total}}
end

# GOOD — pure function for logic, GenServer just for state
defmodule MyApp.Pricing do
  def apply_discount(total, code), do: Decimal.mult(total, Decimal.sub(1, rate(code)))
  defp rate("SAVE10"), do: Decimal.new("0.10")
  defp rate("SAVE20"), do: Decimal.new("0.20")
  defp rate(_), do: Decimal.new("0")
end

def handle_call({:apply_discount, code}, _from, state) do
  new_total = MyApp.Pricing.apply_discount(state.total, code)
  {:reply, {:ok, new_total}, %{state | total: new_total}}
end
```

### 14.7 Premature umbrella split

```
# BAD — premature umbrella
apps/
├── auth/               # Used by every other app
├── core/               # Used by every other app
├── web/                # Depends on auth, core, billing, catalog
├── billing/            # Depends on auth, core
├── catalog/            # Depends on auth, core
└── notifications/      # Depends on auth, core, billing, catalog

# GOOD — single app with clean contexts
lib/my_app/
├── accounts.ex
├── billing.ex
├── catalog.ex
└── notifications.ex
```

### 14.8 Wrong supervision strategy

```elixir
# BAD — Registry + DynamicSupervisor under :one_for_one
children = [
  {Registry, keys: :unique, name: MyApp.Registry},
  {DynamicSupervisor, name: MyApp.DynSup}
]
Supervisor.init(children, strategy: :one_for_one)   # WRONG — Registry crash leaves workers orphaned

# GOOD — tightly coupled processes under :one_for_all (or a sub-supervisor with :rest_for_one)
Supervisor.init(children, strategy: :one_for_all)
```

### 14.9 Simulating objects with processes

```elixir
# BAD — one Agent per domain concept
cart_agent = Agent.start_link(fn -> Cart.new() end)
inventory_agent = Agent.start_link(fn -> Inventory.new(products) end)
# Every operation needs cross-process messaging to coordinate!

# GOOD — pure functional abstractions
cart = Cart.new()
{:ok, item, inventory} = Inventory.take(inventory, sku)
cart = Cart.add(cart, item)
```

**Rule:** Use functions and modules to separate *thought* concerns. Use processes to separate *runtime* concerns (fault isolation, parallelism, independent lifecycles). If things always change together, keep them together.

### 14.10 Mock lies about real behavior

```elixir
# BAD — mock always returns :ok; hides error paths
Mox.expect(PaymentMock, :charge, fn _, _ -> {:ok, %{id: "tx_123"}} end)
# Tests pass; production crashes on {:error, _} because no code handles it.

# GOOD — test both success AND error paths
test "handles payment failure" do
  Mox.expect(PaymentMock, :charge, fn _, _ -> {:error, :card_declined} end)
  assert {:error, :payment_failed} = Orders.complete_order(order)
end
```

### 14.11 Shared database between contexts

```elixir
# BAD — two contexts writing to the same table
defmodule MyApp.Accounts do
  def update_last_login(user_id), do: Repo.update(...)
end
defmodule MyApp.Analytics do
  def track_login(user_id), do: Repo.update_all(...)  # Also writes users table!
end

# GOOD — one context owns the write; other context is a consumer
defmodule MyApp.Accounts do
  def update_last_login(user_id), do: ...
  # Publishes an event; Analytics subscribes
end
defmodule MyApp.Analytics do
  def handle_info({:user_logged_in, user_id}, state), do: ...
  # Stores analytics in its own tables
end
```

### 14.12 Cross-context `Repo.preload`

```elixir
# BAD — reaching into another context's data with preload
users = MyApp.Accounts.list_users()
|> Repo.preload(orders: :items)    # Orders + items belong to Orders context!

# GOOD — context provides the data shape
users_with_orders = MyApp.Orders.list_users_with_orders(user_ids)
# Orders context assembles the data, exposes it as a well-defined shape
```

### 14.13 Microservices split for "loose coupling"

- "We want loose coupling" → use behaviours and PubSub
- "We want fault isolation" → use supervision trees
- "We want independent scaling" → use process pools, Task.async_stream, Broadway
- "It's getting big" → add contexts

**Microservices are justified for: different languages, compliance isolation, org-level autonomy, or genuinely wildly different scaling needs.** Never for "it feels like it should be."

---

## 15. Distributed Architecture — Mostly Don't

### 15.1 What changes in distribution

| Single-node assumption | Distributed reality |
|---|---|
| Function calls always succeed | Network calls can fail, timeout, partition |
| Process state always available | Process may be on another node |
| PubSub is instant and reliable | Messages can be delayed, duplicated, lost |
| ETS shared across the app | ETS is local to each node |
| Registry finds processes instantly | Need distributed registry (`:global`, Horde, Syn) |
| One supervision tree | One tree per node, coordination across trees |

### 15.2 Before distributing — exhaust single-node options

| Problem | Single-node solution | Distribute only when |
|---|---|---|
| More throughput | `Task.async_stream`, Broadway, more cores | Single machine maxed out |
| High availability | Supervisor restarts, health checks | Need zero-downtime deploys |
| Data locality | ETS caching, read replicas | Data must be near users geographically |
| Background jobs | Oban (shares PostgreSQL) | Need to spread CPU-heavy work |
| WebSocket scale | Single node handles ~1M connections | More connections than one machine can serve |

**Default to single node.** Distribution adds network partitions, split-brain scenarios, and eventual consistency. Avoid until genuinely needed.

### 15.3 Distributed communication patterns

```elixir
# :erpc — synchronous call to remote node (OTP 23+)
case :erpc.call(:"worker@host", MyApp.Heavy, :compute, [data], 30_000) do
  result -> {:ok, result}
rescue
  e -> {:error, e}
end

# :pg — distributed process groups (OTP 23+), auto propagates across connected nodes
:pg.join(:my_scope, :workers, self())
:pg.get_members(:my_scope, :workers)    # Pids from ALL nodes

# Phoenix.PubSub — distributed by default in a cluster (uses :pg)
Phoenix.PubSub.broadcast(MyApp.PubSub, "events", {:update, data})

# Distributed Registry options:
# - Horde        — CRDT-based, eventually consistent
# - Syn          — global registry with metadata
# - :global      — built-in, uses global lock (NOT for high frequency)
```

### 15.4 Architectural decisions for distribution

**State ownership — who holds the truth?**

```
Where does authoritative state live?
├── Database (PostgreSQL, EventStore)  → Safest; use for persistent state
├── Single designated node             → :global or Horde to register owner
├── Replicated across nodes            → CRDTs (Horde, DeltaCrdt) for convergence
├── Local to each node                 → ETS cache, eventually consistent is OK
└── No shared state                    → Stateless workers, load balance freely
```

**When you must partition:**

- **Consistent hashing** — route entities to specific nodes by key (e.g., `game_id mod N`)
- **Leader election** — one node coordinates (use `:global` registration)
- **CRDTs** — each node modifies independently, state converges (Horde, DeltaCrdt)

### 15.5 Distribution anti-patterns

```elixir
# BAD — assuming remote calls always succeed
result = GenServer.call({MyServer, :"remote@host"}, :work)

# GOOD — handle node-down and timeout
try do
  GenServer.call({MyServer, :"remote@host"}, :work, 10_000)
catch
  :exit, {:noproc, _} -> {:error, :not_running}
  :exit, {{:nodedown, _}, _} -> {:error, :node_down}
  :exit, {:timeout, _} -> {:error, :timeout}
end
```

```elixir
# BAD — cluster-wide state in a single GenServer (bottleneck + SPOF)
# One node owns it; everyone else does cross-node calls.

# GOOD — local ETS cache per node, refreshed via PubSub or periodic sync
# Each node reads locally; writes propagate asynchronously.
```

```elixir
# BAD — :global for frequently accessed registrations (global lock = contention)

# GOOD — Horde or :pg for high-frequency distributed lookup
```

### 15.6 Cross-Elixir communication — `erpc` skill

For deep distributed patterns (AtomVM, custom protocols, Phoenix telemetry bridges), load the **`erpc`** skill.

---

## 16. Handoff to `elixir-implementing`

Once the plan is clear, load `elixir-implementing` and write the code. The two skills divide labor as follows:

| Planning decision | Implementation detail |
|---|---|
| Which context owns this? (§6–§7) | Context module structure (`elixir-implementing` §10.1) |
| Do I need a process? (§8.1) | Which GenServer callback, how to structure state (`elixir-implementing` §9) |
| Supervision strategy (§8.3) | Application module + child specs (`elixir-implementing` §9.7) |
| Inter-context mechanism (§9) | GenStage/Broadway/Oban code templates (`elixir-implementing` §9) |
| Behaviour at boundary (§4.4) | `@callback` definition + Mox wiring (`elixir-implementing` §4.4) |
| Config strategy (§10) | `compile_env!` vs `get_env` at call sites (`elixir-implementing` §8.6) |
| Multi-tenancy (§7.6) | `prepare_query` implementation, tenant_id in queries |
| Idempotency (§7.3) | `Oban.insert(unique: ...)` or `on_conflict: :nothing` |
| Circuit breaker placement (§11.2) | `:fuse.ask/2` call patterns |
| Graceful degradation (§11.4) | `case` on result + fallback value |

**Workflow:** Plan here → load `elixir-implementing` → write code → test → review. When a planning decision needs revisiting (e.g., "this context is getting too big"), return to this skill.

---

## 17. Related Skills

### Elixir family

- **[elixir-implementing](../elixir-implementing/SKILL.md)** — the companion skill for daily coding. Decision tables for constructs, idiomatic templates, TDD, testing essentials, OTP callback patterns, anti-patterns Claude produces. Load alongside this skill when planning transitions to implementation.
- **elixir-reviewing** *(planned)* — review checklist, anti-pattern catalog, "is this idiomatic?" trees. Load when reviewing existing code.
- **`elixir`** — the original comprehensive Elixir skill with many reference subfiles (architecture-reference, language-patterns, ecto-reference, otp-reference, networking, etc.). This `elixir-planning` skill restructures and improves the architecture-reference content for planning-mode use; load the original for deep reference material beyond what's here.

### Framework / domain

- **`phoenix`** — Phoenix contexts, controllers, plugs, router, channels, PubSub, security, forms, Tailwind.
- **`phoenix-liveview`** — LiveView lifecycle, streams, hooks, uploads, components.
- **`ash`** — Ash Framework declarative resources, policies, actions, extensions.
- **`state-machine`** — `gen_statem`, `GenStateMachine`, AshStateMachine.
- **`event-sourcing`** — Commanded library, aggregates, projections, process managers.
- **`otp`** — GenStage, Broadway, hot upgrades, deeper distribution patterns.
- **`nerves`** — Embedded Elixir firmware (Nerves systems, VintageNet, OTA).
- **`rust-nif`** — Rustler NIFs. Use when the architectural plan includes Rust NIFs.
- **`elixir-testing`** — Deep testing reference. `elixir-implementing` covers the daily 80%; this covers the 20%.
- **`elixir-deployment`** — Mix releases, Docker, Kubernetes, observability. Relevant when planning deploy topology.
- **`erpc`** — Distributed Elixir between nodes and microcontrollers.

### Cross-reference summary — for trivial queries without loading

- **Phoenix:** contexts are the public API boundary; routes → controllers → contexts → schemas. Plugs are composable middleware.
- **LiveView:** `mount → handle_params → render`; use streams for large collections; assign everything in `mount/3`.
- **Ash:** resources declare data + behavior; policies authorize; actions mutate.
- **OTP deep:** `gen_statem` for complex FSMs; PartitionSupervisor to shard one-GenServer bottlenecks; `:persistent_term` for hot-path config.
- **Ecto deep:** `Repo.transact/2` (not `transaction/2`); validations run before DB, constraints after; `Multi` for atomic multi-step; composable query functions with pipes.

---

**End of SKILL.md.** This skill answers *what to build and how to structure it*, before the first line of code is written. For the code itself — decision tables, idiomatic templates, TDD workflow, testing essentials, OTP callback patterns, anti-patterns — load `elixir-implementing` alongside this skill.
