# Growing Architecture — deep reference

Phase-focused deep reference for **how an Elixir application grows from small to large**, and **when to apply each refactoring**. Expands `SKILL.md §13` with concrete evolution patterns, triggering symptoms, and a refactoring decision tree.

**When to load:** when starting a new project (to know what NOT to build yet), when something is growing and you're deciding whether/how to split, when refactoring, when the team is adding people, when the architecture feels off but you can't name why.

**Related:**
- `SKILL.md §13` — the three stages + what doesn't change
- [architecture-patterns.md](architecture-patterns.md) §3 — modular monolith as the default; when/how to split
- [process-topology.md](process-topology.md) §2 — how the supervision tree evolves
- [data-ownership-deep.md](data-ownership-deep.md) §8 — data ownership migrations
- [integration-patterns.md](integration-patterns.md) §13 — escalation path for inter-context mechanisms

---

## 1. Rules for evolving architecture (LLM)

1. **ALWAYS start simpler than you think.** MVP is Stage 1 — one Mix app, one context or a handful, flat supervision, no PubSub, no Oban, no GenStage, no event sourcing. Adopt complexity *only* when the specific problem it solves appears.
2. **ALWAYS let the trigger precede the change.** Don't add GenStage "in case throughput grows." Add it when throughput IS exceeding PubSub's limits.
3. **NEVER restructure the fundamentals.** Context boundaries, hexagonal behaviours, supervision as architecture, ok/error tuples — these hold at every stage. The progression is ADDITIVE, not RESTRUCTURING.
4. **ALWAYS name the triggering problem** before a refactor. "I think we should split this" without a stated problem is a red flag.
5. **PREFER many small migrations over one big rewrite.** Extract one context. Move one table's ownership. Escalate one integration mechanism. Each migration stands alone.
6. **ALWAYS plan the migration path.** Where is the code going? What's the intermediate state? How do you roll back if it's wrong?
7. **NEVER split into separate services to "fix" architectural debt.** Fix the contexts and boundaries first. Services add network hops, not clarity.
8. **ALWAYS consider "stage up" vs "stage down."** Sometimes the right move is to REMOVE complexity (collapse two contexts back into one) rather than add.
9. **ALWAYS document the architectural decisions** as you grow. "Why did we split Orders from Billing?" becomes essential context for future refactors.

---

## 2. The three stages — recap

### 2.1 Stage 1 — Small App

- 1–3 domains
- 1 developer (or very small team)
- Single deployable, no separate workers
- Flat supervision

**Build:**
- One Mix app
- One or a few context modules
- Flat `:one_for_one` supervision (Repo + maybe Phoenix endpoint)
- Direct function calls between contexts
- External deps behind minimal behaviours (at least Repo)

**Don't build:**
- PubSub (unless Phoenix LiveView needs it, which is Stage 2)
- Oban
- GenStage / Broadway
- Event sourcing
- Umbrella / multiple apps

### 2.2 Stage 2 — Medium App

- 3–8 domains
- Small team (2-5 developers)
- Web app + maybe workers
- Need cross-context decoupling

**Add:**
- Multiple context modules
- PubSub for UI broadcasts / decoupling
- First GenServers for genuinely shared state (cache, counters)
- Behaviours at all external boundaries (mailer, payment, HTTP)
- Oban when jobs must survive restart

**Keep:**
- Single Mix app (contexts give enough separation)
- Flat or slightly nested supervision
- Direct function calls as the default integration

### 2.3 Stage 3 — Large App

- 8+ domains
- Multiple teams
- Independent scaling needs
- Production observability / compliance

**Add:**
- Nested supervision hierarchy with error kernel design
- Oban queues per concern
- GenStage / Broadway for high-throughput pipelines
- Full telemetry instrumentation
- Possibly: event sourcing for contexts that need it
- Possibly: umbrella for team / deployment boundaries

**Retain:**
- Domain logic in pure functions (still!)
- External deps behind behaviours (still!)
- Boundary modules as public API (still!)
- ok/error tuples (still!)

### 2.4 Between stages — the "not yet" zone

Often you're between stages. That's fine. The question is: does the next addition solve an observed problem, or is it speculation?

| Current state | Next addition | Right time? |
|---|---|---|
| 2 contexts | Add third context | When the third domain appears |
| Flat supervision | Nest one layer | When a child crash should cascade to siblings |
| Direct calls | Add PubSub | When a context needs to react to events |
| PubSub | Add Oban | When events start getting lost on deploys |
| Oban | Add GenStage | When producer rate exceeds consumer |
| Standard Ecto | Event sourcing | When audit/replay is a business requirement |

---

## 3. Evolution patterns — triggered by symptoms

### 3.1 "The context file is getting too big"

**Symptom:** One context module is 500+ lines of public functions, or its internal directory has 15+ files.

**Diagnosis tree:**

```
Does the context do multiple unrelated things?
├── YES → Split into multiple contexts. See §5.1.
└── NO → Extract internal helpers into more internal modules.
         Not an architectural problem.

Multiple teams work on the same context?
├── YES → Split by team-domain alignment. See §5.1.
└── NO → Large is OK if cohesive.
```

**Red flag:** don't split just because it's "too many lines." Cohesive 1000-line contexts are fine. Incoherent 300-line contexts are not.

### 3.2 "Cross-context calls everywhere"

**Symptom:** Context A calls Context B calls Context C calls Context A.

**Diagnosis:**

```
Are the contexts really separate domains?
├── YES → The design is awkward but OK. Maybe introduce PubSub to break circularity.
├── NO → They should be one context. Merge. See §5.2.
└── IT'S ACTUALLY DATA FLOW → You need an orchestration layer (saga or process manager).
```

### 3.3 "GenServer bottleneck"

**Symptom:** One GenServer has a growing mailbox under load.

**Fix path:**

```
What's slow in the GenServer?
├── Reads are slow (serializing readers)
│   └── Move reads to ETS. See [otp-design.md §7].
├── One handler does heavy I/O
│   └── Offload to Task.Supervisor.async_nolink.
├── Producer > consumer rate
│   └── Introduce GenStage/Broadway. See [integration-patterns.md §5].
└── CPU-heavy work per message
   └── PartitionSupervisor for parallel execution.
```

### 3.4 "Messages lost during deploys"

**Symptom:** Events published via PubSub are lost when a deploy restarts subscribers.

**Fix:** Migrate from PubSub to Oban for guaranteed delivery. See [integration-patterns.md §6].

**Migration steps:**
1. Identify which PubSub topics need persistence
2. Create corresponding Oban workers
3. Dual-publish: emit BOTH the PubSub event and the Oban job
4. Migrate consumers one at a time to use Oban
5. Remove PubSub publishing once no consumer uses it

### 3.5 "Tests are slow / flaky"

**Symptom:** Test suite takes 10+ min; flaky tests on CI.

**Diagnosis:**

```
Is the suite mostly integration tests?
├── YES → Shift to unit tests. Test domain logic without DB/framework.
│         See [test-strategy.md §2–3].
└── NO → Check for flakiness source:
    ├── Process.sleep → replace with assert_receive
    ├── Global state (named GenServers, App env) → isolate per test
    ├── Ecto sandbox misuse → verify async+checkout pattern
    └── Wall-clock assertions → use assert_in_delta or injected clock
```

### 3.6 "Can't test X without starting Y"

**Symptom:** Unit-testing a context function requires spinning up Repo, Phoenix, external HTTP.

**Fix:** Introduce behaviours at the boundary. Now the context depends on `@callback` types, not specific modules. Tests mock the behaviour.

This is the **hexagonal retrofit** — see [architecture-patterns.md §4.6].

### 3.7 "Dev server won't start" after adding a dep

**Symptom:** Adding a new dep / starting a subsystem causes cascading startup failures.

**Diagnosis:**
- Supervision order wrong — child starts before its dependency
- Missing `handle_continue` — init does expensive work that times out
- Config mismatch — dev config doesn't include required keys

**Fix:** Review the supervision tree. Order children by dependency. Use `handle_continue` for init. See [process-topology.md §10].

### 3.8 "Different teams stepping on each other"

**Symptom:** Two PRs touch the same files; merge conflicts; coordination burden.

**Diagnosis:**

```
Are they working on the same domain?
├── YES → Same context — coordination is inherent. Communicate.
└── NO → Context boundary is wrong. One team's domain shouldn't touch another's files.
```

**Fix:** Either:
- Reshape context boundaries to match team ownership
- Use CODEOWNERS to flag ownership without physical splits
- If boundaries are clear but file-level conflicts, use umbrella for compile-time boundaries

### 3.9 "Deployment is all-or-nothing"

**Symptom:** A change to one subsystem requires redeploying everything. Deploy windows are scarce.

**Fix path:**

```
Does the subsystem need independent deploy cadence?
├── NO, just bigger window → Optimize CI / test speed, not architecture.
├── YES → Umbrella with separate releases.
└── YES, different infra requirements → Separate service (last resort).
```

See [architecture-patterns.md §3.3] on when splitting is justified.

---

## 4. Refactoring decision tree — full

```
You observe: something feels wrong / broken / slow / hard.

1. Name the problem concretely.
   ├── Can't name it → Stop. Observe more. Measure.
   └── Named → continue

2. Is it a symptom or a cause?
   ├── "Tests are slow" → symptom. Cause might be "heavy integration tests."
   ├── "Deploy is scary" → symptom. Cause might be "no separate release targets."
   └── Dig one level until you find the cause.

3. Is the cause at the right level?
   ├── Code-level (use a different function) → just fix it
   ├── Module-level (wrong abstractions) → small refactor
   ├── Context-level (wrong boundary) → context redraw
   └── Architecture-level (wrong stage of growth) → growth-step

4. What's the minimum change?
   ├── Growth-step → §5
   ├── Context redraw → §6
   ├── Integration mechanism change → §7
   └── Supervision tree change → §8

5. How do you know it worked?
   ├── Define success before starting.
   ├── Measure it after.
   └── Roll back if it didn't help. Don't double down.
```

---

## 5. Growth steps — when to move up a stage

### 5.1 When to add a context

**Triggers:**
- A new business domain appears ("Now we have billing, not just orders")
- A distinct team takes ownership
- Data lifecycle differs from existing contexts
- Constraints / rules differ substantially

**Migration:**
1. Create the new context module (`lib/my_app/billing.ex`)
2. Add internal modules as needed (`lib/my_app/billing/...`)
3. Move relevant functions from other contexts — one at a time
4. Update callers
5. Remove the functions from the old context

**Anti-patterns:**
- Splitting a context just because it's long
- Splitting "for future scalability"
- Splitting by technical concern instead of domain

### 5.2 When to merge contexts

**Triggers:**
- Constant cross-context calls between two contexts
- Shared aggregate root (if you have to coordinate A and B atomically, they're one thing)
- The split was premature / speculative

**Merging two contexts is easier than splitting.** Don't hesitate if the diagnosis says merge.

**Migration:**
1. Move all functions into one context
2. Mark the old context's module as `@deprecated`
3. Remove after all callers updated

### 5.3 When to add PubSub

**Triggers:**
- A context needs to react to events from another context async
- UI / LiveView needs real-time updates across sessions
- Cross-node communication needed (clustered app)

**Migration:**
1. Add `{Phoenix.PubSub, name: MyApp.PubSub}` to supervision tree
2. Start publishing events from producing context: `Phoenix.PubSub.broadcast(...)`
3. Add subscriber processes (GenServers) that subscribe in `init/1`
4. Add LiveView subscriptions as needed

### 5.4 When to add Oban

**Triggers:**
- Events getting lost on deploys (PubSub subscribers down)
- Need scheduled / cron jobs
- Retries with backoff needed
- Unique constraint on jobs (dedupe)

**Migration:**
1. Add Oban to deps
2. Add Oban migration
3. Add `{Oban, Application.fetch_env!(:my_app, Oban)}` to supervisor
4. Define worker modules
5. Convert async handlers from PubSub subscribers to Oban workers

### 5.5 When to add GenStage / Broadway

**Triggers:**
- PubSub subscriber mailboxes growing under load
- Producer rate exceeds consumer throughput
- Consuming from external message broker (Kafka, SQS, RabbitMQ)
- Need batching for efficient DB writes

**Migration:**
1. Identify the production / consumption pattern
2. For external brokers: add Broadway with the right adapter
3. For in-process: add a GenStage pipeline
4. Move handlers from PubSub subscribers to GenStage consumers

### 5.6 When to add event sourcing

**Triggers:**
- Perfect audit trail is a requirement (compliance, regulations)
- Complex long-lived workflows that benefit from replay
- Multiple read views of the same data
- Already using Commanded elsewhere and adding another event-sourced context

**This is a big step.** Event sourcing for ONE context adds substantial complexity (commands, events, aggregates, projections, process managers). Don't take it lightly.

**Migration:**
1. Add Commanded deps, configure event store (Postgres typically)
2. Design commands + events for the target context
3. Write aggregate module (pure functions: command → events)
4. Write projections (event → Ecto updates, or custom read store)
5. Migrate existing data into the event log (replay from CRUD data)
6. Swap the context's public API to use commands

### 5.7 When to extract to an umbrella

**Triggers:**
- Multiple teams need hard compile-time boundaries
- Separate deployable targets (web vs worker vs API)
- Different dependencies per target

**Migration:**
1. `mix new my_platform --umbrella`
2. Create apps: `apps/core`, `apps/core_web`, `apps/worker`
3. Move relevant contexts into each app
4. Wire up `deps: [{:core, in_umbrella: true}]` in each sibling
5. Update releases config to produce separate release artifacts

**This is usually irreversible.** Consider alternatives (CODEOWNERS, separate releases from a single app) first.

### 5.8 When to consider separate services

Almost never. See [architecture-patterns.md §8]. Signs that actually justify splitting:

- **Different language needed** (Python ML, Rust GPU compute — but first try NIF)
- **Compliance isolation** (PCI data must be separate from the rest)
- **Wildly different scaling profile** (video transcoding at 100× the request rate of auth)
- **Team autonomy is a hard requirement** — separate release cycle is a business requirement, not preference

---

## 6. Context redraw — changing boundaries

### 6.1 Symptoms of wrong boundaries

| Symptom | Likely fix |
|---|---|
| Constant cross-context calls | Merge contexts |
| Two contexts writing to the same table | One owner; the other is a consumer |
| Repo calls from one context into another's schemas | Introduce a proper API |
| Business rule lives in "wrong" context | Move to the owning context |
| Team boundaries don't match context boundaries | Align boundaries with team ownership |
| Aggregate's invariants are split across contexts | Same context or clearer aggregate boundary |

### 6.2 The context extraction

Extract a new context from an existing one:

1. **Pick a seam.** Which functions + tables form a coherent unit?
2. **Create the new context module.** Move public functions; update function names.
3. **Move schemas.** `lib/my_app/existing/thing.ex` → `lib/my_app/new_context/thing.ex`. Namespace changes.
4. **Migrate data ownership.** The new context owns the table now. Update references.
5. **Update callers.** Other modules call the new context's public API.
6. **Remove shim from old context.** Once all callers are on the new API.

### 6.3 The context merge

Merge two contexts into one:

1. **Pick the target name.** Usually the more central/general one.
2. **Move functions from B into A.** Rename if there are collisions.
3. **Mark B as deprecated.** Delegate B's functions to A.
4. **Update all callers** to use A.
5. **Remove B** when no callers remain.

### 6.4 Pragmatic notes

- **Context reshaping is low-risk if tests are good.** The compiler + tests catch most mistakes.
- **Use `mix xref`** to find caller sites: `mix xref callers MyApp.OldContext.old_function/1`
- **Big-bang redraws are risky.** Break into multiple smaller PRs.
- **Keep delegating shims during transition** — they let you migrate callers gradually.

---

## 7. Integration migration — up the escalation ladder

[integration-patterns.md §13] has the escalation path:

```
Direct function call
  ↓ (need async / decoupling)
PubSub
  ↓ (mailbox growing? fast producer / slow consumer?)
GenStage / Broadway
  ↓ (events lost on deploy / crash?)
Oban
  ↓ ("what happened and when?" / replay / compliance?)
Event sourcing (Commanded)
```

Migrating up one rung:

### 7.1 Direct → PubSub

```elixir
# BEFORE — direct call
def complete_order(order) do
  with {:ok, order} <- mark_completed(order) do
    MyApp.Mailer.send_confirmation(order)              # Direct call
    MyApp.Analytics.track_order_completed(order)       # Direct call
    {:ok, order}
  end
end

# AFTER — PubSub decoupling
def complete_order(order) do
  with {:ok, order} <- mark_completed(order) do
    Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:order_completed, order})
    {:ok, order}
  end
end

# Mailer subscribes
defmodule MyApp.Mailer.OrderListener do
  use GenServer
  def init(:ok) do
    Phoenix.PubSub.subscribe(MyApp.PubSub, "orders")
    {:ok, %{}}
  end
  def handle_info({:order_completed, order}, state) do
    MyApp.Mailer.send_confirmation(order)
    {:noreply, state}
  end
end
```

**Gains:** decoupling. Order context doesn't know about Mailer / Analytics.

**Loses:** synchronous confirmation. If Mailer is down, email silently not sent.

### 7.2 PubSub → Oban (for guaranteed delivery)

```elixir
# BEFORE — PubSub (may drop on restart)
Phoenix.PubSub.broadcast(MyApp.PubSub, "orders", {:send_email, order})

# AFTER — Oban (persistent)
%{order_id: order.id}
|> MyApp.Workers.SendEmail.new()
|> Oban.insert()
```

**Gains:** persistence, retry, scheduling.

**Loses:** real-time. Jobs take at least one Oban tick to process.

### 7.3 PubSub → GenStage (for backpressure)

When a PubSub subscriber can't keep up:

```elixir
# BEFORE — PubSub; subscriber mailbox grows unbounded
defmodule MyApp.Event.SlowHandler do
  def init(:ok) do
    Phoenix.PubSub.subscribe(MyApp.PubSub, "events")
    {:ok, %{}}
  end
  def handle_info({:event, data}, state) do
    slow_operation(data)   # If producer is faster than this, mailbox grows
    {:noreply, state}
  end
end

# AFTER — GenStage with max_demand controls backpressure
defmodule MyApp.Event.Producer do
  use GenStage
  # Buffers events; emits on demand
end

defmodule MyApp.Event.Consumer do
  use GenStage
  def init(:ok), do: {:consumer, :ok, subscribe_to: [{Producer, max_demand: 10}]}
  def handle_events(events, _from, state) do
    Enum.each(events, &slow_operation/1)
    {:noreply, [], state}
  end
end
```

**Gains:** bounded memory. Producer slows when consumer is slow.

**Loses:** simpler setup. GenStage adds a supervision tree subtree.

### 7.4 Standard Ecto → event sourcing (per context)

This is a big migration. Only for contexts that genuinely need event sourcing.

1. Decide: which context?
2. Design commands + events
3. Add Commanded; configure event store
4. Write aggregate + projections
5. Dual-write: write to both standard Ecto AND events during transition
6. Replay events to rebuild projections
7. Switch reads to use projections
8. Remove standard Ecto from this context

---

## 8. Supervision tree evolution

See [process-topology.md §10] for the worked example of building from scratch.

### 8.1 Stage 1 tree

```
MyApp.Application (:one_for_one)
├── MyApp.Repo
└── MyAppWeb.Endpoint
```

Flat. Simple. Works for most apps for a long time.

### 8.2 Stage 2 tree

```
MyApp.Application (:one_for_one)
├── MyAppWeb.Telemetry
├── MyApp.Repo
├── {Phoenix.PubSub, name: MyApp.PubSub}
├── MyApp.Cache                    # First GenServer appears
├── {Oban, Application.fetch_env!(:my_app, Oban)}
└── MyAppWeb.Endpoint
```

One level deep. More children but still flat.

### 8.3 Stage 3 tree

```
MyApp.Application (:one_for_one)
├── MyAppWeb.Telemetry
├── MyApp.Repo                                ┐
├── {Phoenix.PubSub, name: MyApp.PubSub}      │ Error kernel
├── ────────────────                          ┘
├── MyApp.DomainSupervisor (:rest_for_one)    # Volatile services
│   ├── MyApp.Cache
│   ├── MyApp.EventProcessor
│   └── MyApp.NotificationService
├── MyApp.WorkerSupervisor (:one_for_all)     # Tightly coupled pair
│   ├── {Registry, keys: :unique, name: MyApp.WorkerRegistry}
│   └── {DynamicSupervisor, name: MyApp.WorkerDynSup}
├── {Oban, ...}
└── MyAppWeb.Endpoint                         # Last
```

Nested. Error kernel distinct. Tightly coupled pairs grouped with `:one_for_all`.

### 8.4 When to nest

Add a sub-supervisor when:
- You need a different restart strategy for a group of children
- You want to encapsulate a subsystem (e.g., "the worker pool" with its own restart semantics)
- A specific subsystem needs different restart intensity (`max_restarts`)

---

## 9. Team evolution and architecture

### 9.1 Conway's Law in Elixir

"Organizations produce designs that mirror their communication structures."

- **1 dev:** contexts are a style choice; no team boundary to enforce
- **2-5 devs:** contexts become light coordination boundaries
- **5-15 devs:** contexts become ownership boundaries; CODEOWNERS starts mattering
- **15+ devs:** umbrella or separate releases start to be justified

### 9.2 Onboarding evolution

As the team grows, the architecture should help onboarding:

- **Stage 1:** README + good code
- **Stage 2:** Context docs; `@moduledoc` matters more
- **Stage 3:** Architecture Decision Records (ADRs); diagrams; training materials

**An app is onboardable if a new dev can add a new feature to the least-complex context within their first week.** If they can't, the architecture needs clarification.

### 9.3 Code ownership

- **Stage 1:** everyone owns everything
- **Stage 2:** informal ownership (who usually reviews X?)
- **Stage 3:** CODEOWNERS file; "don't touch X without owner's review"

CODEOWNERS is a lighter-weight split than umbrella. Often it's enough.

---

## 10. When to remove complexity (stage down)

Sometimes the right move is to REMOVE a layer you added prematurely.

### 10.1 Signs you over-architected

| Sign | Fix |
|---|---|
| GenStage pipeline with no backpressure issue | Revert to PubSub |
| Oban for tasks that don't need persistence | Revert to `Task.Supervisor` |
| Event sourcing for CRUD-like data | Revert to standard Ecto |
| Umbrella with apps that depend on each other in every direction | Merge into one app |
| Multiple contexts that always change together | Merge contexts |
| Behaviours with one implementation ever | Remove the behaviour; use direct calls |

### 10.2 Removal is harder than adding

Removing a behaviour means updating all implementers. Merging contexts means updating all callers. The inertia is usually: "we'll clean it up later." It rarely happens.

**Planning tip:** don't add the layer in the first place without a concrete justification.

### 10.3 A retrospective question

Every quarter, look at the last quarter's architectural changes:
- Did adding X solve the problem we said it would?
- Is it still earning its complexity?
- Is there anything we could remove?

---

## 11. Documentation as architecture evolves

### 11.1 What to document at each stage

**Stage 1:** README + inline `@moduledoc`.

**Stage 2:** Add:
- Context-level `@moduledoc` explaining the context's purpose and public API
- Architecture overview (one page): "these are our contexts, here's who owns what"

**Stage 3:** Add:
- ADRs (Architecture Decision Records) — why each major decision was made
- Supervision tree diagram
- Integration diagram (which contexts talk to which, via what mechanism)
- Onboarding guide (where do I start if I want to add X)

### 11.2 ADR format

Simple ADR template:

```markdown
# ADR-0042: Introduce Oban for async jobs

## Status
Accepted — 2025-06-15

## Context
PubSub events for outbound emails were getting lost during deploys.
Users weren't receiving welcome emails ~2% of the time.

## Decision
Migrate outbound email from PubSub subscribers to Oban workers.

## Consequences
+ Emails persist; never lost on restart
+ Retry / backoff for flaky SMTP providers
- Oban adds a DB dependency (already have one; fine)
- Slightly more infrastructure to monitor
```

### 11.3 Architecture diagrams

Keep diagrams in the repo (`docs/architecture.md` or similar). Use Mermaid. Diagrams drift — review quarterly.

---

## 12. Common evolution mistakes

### 12.1 Building Stage 3 at Stage 1

```elixir
# Day 1 of new project
children = [
  MyApp.Telemetry,
  MyApp.Repo,
  {Phoenix.PubSub, name: MyApp.PubSub},
  {Oban, queues: [default: 10, emails: 5, payments: 2]},
  MyApp.EventStore,
  MyApp.CQRS.CommandBus,
  MyApp.CQRS.QueryBus,
  # ... 20 more children for problems we don't have yet
  MyAppWeb.Endpoint
]
```

At Stage 1, this is a tax. Features are slower to build. Debugging is harder. The app doesn't *need* any of this yet.

**Rule:** start minimal. Add complexity as problems arrive.

### 12.2 Splitting to "prepare for scale"

```
Umbrella with 5 apps from day 1.
Only 1 of them has any code.
```

You pay the umbrella tax forever. For the first year, you have 1 real app and 4 shells.

**Rule:** split when you have the problem, not in anticipation.

### 12.3 Adding every advanced pattern

Event sourcing + CQRS + GenStage + every context + Hexagonal for every dep + microservices...

These are tools. Use them when needed. Don't use them all at once.

### 12.4 Never refactoring

The opposite problem: the app is at Stage 3 scale but still has Stage 1 structure. One context with 5000 lines. Flat supervision. Everyone stepping on each other.

**Rule:** refactoring is part of the job. Schedule time for it.

### 12.5 Big-bang refactors

Rewriting the whole app "the right way" in one branch. Six months later, still not shipped; original features didn't get worked on.

**Rule:** small migrations. Extract one context. Move one table. Escalate one integration mechanism. Ship each.

### 12.6 Not documenting why

Two years later: "Why does Orders call Analytics through Oban instead of PubSub?" No one remembers.

**Rule:** write an ADR when you make a non-obvious architectural change.

### 12.7 Splitting a monolith to "fix" architecture problems

```
Monolith is messy.
"Let's split into microservices. That'll fix it."
Now you have two messes and network hops between them.
```

**Rule:** fix the context boundaries within the monolith FIRST. Then decide if splitting is still needed. Usually the answer is no.

---

## 13. The "non-evolution" — what stays constant

These never change, at any stage:

- **Domain logic is pure functions.** From day 1 to 10 years later.
- **External dependencies behind behaviours.** Same forever.
- **Boundary modules are the only public API.** Same.
- **ok/error tuples.** Same.
- **Supervision tree expresses architecture.** The tree grows; the principle holds.
- **Context module is the public entry point for its domain.** Doesn't change.

**The progression is additive.** You add GenServers, PubSub, supervision layers. You never restructure the fundamentals.

---

## 14. Cross-references

### Within this skill

- `SKILL.md §13` — three stages overview
- [architecture-patterns.md](architecture-patterns.md) §3 — modular monolith as default
- [process-topology.md](process-topology.md) §10 — supervision tree worked example
- [data-ownership-deep.md](data-ownership-deep.md) §8 — data ownership migrations
- [integration-patterns.md](integration-patterns.md) §13 — escalation path

### In other skills

- [../elixir-implementing/SKILL.md](../elixir-implementing/SKILL.md) §10 — implementing contexts at each stage
- [../elixir-reviewing/SKILL.md](../elixir-reviewing/SKILL.md) §7 — review checklist to catch regressions
- `../elixir/architecture-reference.md` — original architectural reference

---

**End of growing-evolution.md.** The app gets more complex over time. The fundamentals don't change. Add layers when the problem arrives — not before.
