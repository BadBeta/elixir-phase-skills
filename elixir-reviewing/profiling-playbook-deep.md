# Profiling Playbook — Deep Reference

How to pick and use each Elixir/BEAM profiling tool. Phase-focused on **investigating performance issues** in existing code. Covers measurement, tool selection, interpreting output, and the specific cases each tool serves best.

---

## Profiling Principles

1. **Measure, don't guess.** Without evidence, "optimization" usually changes the code without improving it — or makes it worse.
2. **Establish a baseline before changing anything.** Record numbers; you can't claim improvement without a before/after.
3. **Profile closest to the symptom.** If production is slow, profile production-similar workloads. A dev benchmark at 100 items won't surface a production bug at 100K items.
4. **Use monotonic time.** `System.monotonic_time/1` or `:erlang.monotonic_time/0` — never `System.system_time` for durations (NTP can jump).
5. **Pick the right granularity.** One-shot timing → `:timer.tc`. Comparative → Benchee. Deep dive → `fprof`/`eprof`/`tprof`. System-wide → `:observer` + `:recon`.

---

## Tool Selection Decision Table

| Need | Tool | Overhead | Production-safe |
|---|---|---|---|
| Time a single function call once | `:timer.tc/1` | None | Yes |
| Compare two or more implementations | `Benchee` | Low | Dev only |
| Find where time is spent inside a function | `:fprof` | **HIGH** (10-50×) | No |
| Aggregate time per function (call profile) | `:eprof` | Medium | No |
| Aggregate call counts per function | `:cprof` | Medium | No |
| Sampling profiler (prod-grade) | `:tprof` (OTP 27+) | Low | Yes, with caution |
| Top processes by memory/reductions/mailbox | `:recon.proc_count` | Very low | Yes |
| Trace specific function calls (bounded) | `:recon_trace.calls` | Low (limited) | Yes |
| System-wide introspection (GUI) | `:observer.start()` | Low (but opens remote shell) | Staging only |
| Memory breakdown by allocator | `:erlang.memory/0` | None | Yes |
| Binary leak detection | `:recon.bin_leak` | Medium (triggers GC) | Careful — pauses procs |
| Scheduler utilization | `:scheduler.utilization` | None | Yes |
| Per-query DB timing | Telemetry `[:my_app, :repo, :query]` | None | Yes |

---

## `:timer.tc/1` — Quick Timing

```elixir
# Single call
{time_us, result} = :timer.tc(fn -> MyMod.slow_fun(arg) end)
IO.puts("#{div(time_us, 1000)}ms")

# MFA form (slightly less overhead)
{time_us, result} = :timer.tc(MyMod, :slow_fun, [arg])
```

**Returns microseconds**. Divide by 1000 for ms, 1_000_000 for seconds.

**Caveat:** First run often includes JIT warm-up / module load. Discard the first sample for steady-state analysis.

```elixir
# Warm up, then measure 5 runs
_ = MyMod.slow_fun(arg)
times = for _ <- 1..5, do: elem(:timer.tc(fn -> MyMod.slow_fun(arg) end), 0)
IO.inspect(times, label: "runs (μs)")
```

---

## Benchee — Comparative Benchmarking

### Basic

```elixir
Benchee.run(%{
  "old_impl" => fn -> Old.sort(large_list) end,
  "new_impl" => fn -> New.sort(large_list) end
})
```

### With inputs

```elixir
Benchee.run(
  %{
    "old" => fn input -> Old.process(input) end,
    "new" => fn input -> New.process(input) end
  },
  inputs: %{
    "small (100)" => Enum.to_list(1..100),
    "medium (10k)" => Enum.to_list(1..10_000),
    "large (1M)" => Enum.to_list(1..1_000_000)
  },
  time: 5,              # seconds per scenario
  warmup: 2,            # warmup seconds
  memory_time: 2,       # measure memory usage
  print: %{configuration: false}
)
```

### Reading output

Benchee reports:

- **ips** — iterations per second. Higher = faster.
- **average** — mean time per iteration.
- **deviation** — stability (low % = consistent).
- **median** — robust central tendency.
- **99th %** — tail latency.
- **Memory Usage** — bytes allocated per iteration.

**Comparison table** shows relative speed: `1.5x slower` means `new` is 1.5× slower than the fastest.

### Formatters

```elixir
Benchee.run(%{...},
  formatters: [
    {Benchee.Formatters.Console, comparison: true},
    {Benchee.Formatters.HTML, file: "bench.html"}
  ]
)
```

---

## `:fprof` — Full Call Tree Profile

**Use when:** you need to see every function call and the time spent in each, including callees.

**Cost:** 10-50× slowdown. Dev/staging only.

```elixir
:fprof.apply(&MyMod.slow_fun/1, [arg])
:fprof.profile()
:fprof.analyse(dest: ~c"/tmp/fprof.txt", sort: :own)

# Read it
File.read!("/tmp/fprof.txt")
```

**Key columns:**
- `CNT` — number of calls
- `ACC` — accumulated time (self + children)
- `OWN` — own time (excluding children)

Sort by `:own` to find the slowest functions; sort by `:acc` to find the heaviest call chains.

---

## `:eprof` — Time Per Function

**Use when:** you want a summary of "which functions consumed the most time" without the call tree.

**Cost:** Lower than fprof, still not production-safe.

```elixir
:eprof.start()
:eprof.profile(fn -> MyMod.do_work(data) end)
:eprof.analyze()          # prints to stdout
:eprof.stop()

# Or analyze to a file
:eprof.log(~c"/tmp/eprof.txt")
:eprof.analyze(:total)
:eprof.stop_profiling()
```

**Key columns:**
- `CALLS` — number of calls
- `% TIME` — proportion of total time

Use when the top-3 slowest functions are suspected — less detail than fprof, faster to read.

---

## `:cprof` — Call Counts

**Use when:** you want to know "which functions run the most," regardless of time.

Good for finding code hot paths that might not be slow individually but run very often.

```elixir
:cprof.start()
_ = MyMod.do_work(data)
analysis = :cprof.analyse()
:cprof.stop()

analysis
|> Enum.take(20)
|> Enum.each(fn {mfa, count, _} -> IO.puts("#{inspect(mfa)}: #{count}") end)
```

---

## `:tprof` — Statistical Sampling (OTP 27+)

**Use when:** you need production-safe profiling, or want low-overhead analysis in dev.

```elixir
:tprof.start(%{type: :call_count})
:tprof.set_pattern({MyMod, :_, :_})
_ = MyMod.do_work(data)
result = :tprof.stop()
:tprof.format(result)
```

Three modes:
- `:call_count` — how many times each function was called
- `:call_time` — time spent in each function (similar to eprof)
- `:call_memory` — memory allocated per call

---

## `:observer.start()` — GUI Inspector

**Use when:** you need to explore a live system interactively — running processes, applications, ETS tables, tracing.

**Staging/dev only.** Not for production (GUI requires remote shell access).

```elixir
iex> :observer.start()
```

Tabs worth knowing:
- **System** — version, schedulers, memory
- **Applications** — supervision tree
- **Processes** — sortable list; right-click → inspect state
- **ETS** — tables and sizes
- **Trace Overview** — wire up ad-hoc tracing

---

## `:recon` — Production-Safe Introspection

`:recon` is the production toolbox. Bounded, deadlock-free, won't crash your node.

### Top processes

```elixir
# Top 10 by memory
:recon.proc_count(:memory, 10)

# Top 10 by message queue
:recon.proc_count(:message_queue_len, 10)

# Top 10 by reductions (CPU budget)
:recon.proc_count(:reductions, 10)

# Window sampling (top 10 that consumed most reductions in last 1s)
:recon.proc_window(:reductions, 10, 1000)
```

### Binary leak

```elixir
# Force GC on top 10 processes, report freed binary memory
:recon.bin_leak(10)
```

### Trace live function calls

```elixir
# Trace 100 calls to MyMod.fun/* (any arity), with their args
:recon_trace.calls({MyMod, :fun, :_}, 100)

# Trace with a match spec — only calls where first arg is :active
:recon_trace.calls({MyMod, :handle, [{[:active, :_], [], []}]}, 10)

# Stop tracing
:recon_trace.clear()
```

Always pass an explicit count limit — unbounded tracing can overwhelm a node.

---

## Memory Analysis

### System-wide breakdown

```elixir
:erlang.memory()
# [
#   total: 80_000_000,    # total used
#   processes: 20_000_000,
#   system: 60_000_000,
#   atom: 1_200_000,
#   atom_used: 1_100_000,
#   binary: 5_000_000,
#   code: 25_000_000,
#   ets: 8_000_000
# ]

# Human-readable
:erlang.memory() |> Enum.map(fn {k, v} -> {k, div(v, 1024 * 1024)} end)
```

### Per-process

```elixir
Process.info(pid, [:memory, :heap_size, :stack_size, :total_heap_size, :message_queue_len, :binary])
```

### ETS

```elixir
:ets.all()
|> Enum.map(fn tab ->
  {:ets.info(tab, :name), :ets.info(tab, :size), :ets.info(tab, :memory)}
end)
|> Enum.sort_by(fn {_, _, m} -> -m end)
|> Enum.take(10)
```

### Binary reference tracking

A process holds a "ref" to a refcounted binary (>64 bytes) until it GCs. Processes that don't GC often can hold many refs.

```elixir
Process.info(pid, :binary)  # List of binary refs this process holds
length(Process.info(pid, :binary) |> elem(1))  # How many
```

---

## Telemetry — Production Metrics

Lightweight, production-safe metrics via `[:app, :subsystem, :event]` names.

```elixir
# Instrument an operation
:telemetry.span([:my_app, :search], %{query: q}, fn ->
  result = do_search(q)
  {result, %{result_count: length(result)}}
end)
# Emits :start and :stop events with duration measured in :native time units

# Attach a handler (ideally in application.ex or a dedicated module)
:telemetry.attach(
  "slow-search-log",
  [:my_app, :search, :stop],
  fn _event, %{duration: d}, meta, _cfg ->
    if System.convert_time_unit(d, :native, :millisecond) > 500,
      do: Logger.warning("Slow search: #{inspect(meta)}")
  end,
  nil
)
```

Common auto-emitted events:
- `[:phoenix, :endpoint, :stop]` — request duration
- `[:phoenix, :router_dispatch, :stop]` — controller-level time
- `[:ecto, :my_app, :repo, :query]` — SQL query timings
- `[:oban, :job, :stop]` — job durations

---

## Scheduler Utilization

```elixir
# Sample utilization for 5 seconds
samples = :scheduler.utilization(5)
# [{1, 0.42}, {2, 0.38}, ...]  # scheduler id → fraction busy

# Or with recon
:recon.scheduler_usage(5000)
```

High (>0.8) and sustained → CPU-bound. Check:
- Busy processes via `:recon.proc_count(:reductions, 10)`.
- Tight loops (a function that never yields to the scheduler).
- NIF overuse (NIFs can't be preempted under 1ms).

---

## Common Profiling Traps

### 1. Measuring only first run

JIT warmup, module loading, and caches aren't representative. Always do a warm-up run first.

### 2. Measuring with `Process.sleep` in the target

Sleeping doesn't consume CPU — don't benchmark a function that sleeps; you'll measure wall-clock not work.

### 3. Benchmarking in release vs dev build

Dev build has `--warnings-as-errors`, no optimizations. Release build has consolidated protocols. Measure in `MIX_ENV=prod`:

```sh
MIX_ENV=prod mix run bench.exs
```

### 4. Ignoring GC pauses

Large-heap processes may show artificially consistent timing because GC happens between benchmarks. Use `memory_time: 2` in Benchee to surface allocation patterns.

### 5. Profiling the benchmark harness

`fprof` captures everything — including the wrapping function. Filter to your target modules:

```elixir
:fprof.apply(&MyMod.target/1, [arg], procs: [self()], trace: [:call])
:fprof.profile()
```

### 6. Measuring end-to-end time with external deps

If the function calls `HTTPoison.get!`, you're timing the network. Separate:
- `MyMod.transform_response(pre_fetched_body)` — pure code
- full end-to-end — including network

### 7. Hot vs cold cache

Database/page cache, connection pool warm-up, etc. Decide which scenario you want to measure and configure accordingly.

---

## Workflow: Suspected Performance Bug

1. **Reproduce** — get a repeatable trigger (fixture, prod-similar workload).
2. **Baseline** — measure end-to-end time with `:timer.tc` or Benchee.
3. **Localize** — run `:fprof`/`:eprof` to find the hot functions.
4. **Hypothesize** — pick ONE suspected bottleneck.
5. **Fix** — apply the minimum change.
6. **Verify** — rerun the exact baseline measurement; record improvement.
7. **Repeat** — pick the next bottleneck if SLO not met.

**Don't skip step 6.** Without an after-measurement, you don't have evidence the fix helped.

---

## Cross-References

- **Symptom → diagnosis playbook:** `./debugging-playbook-deep.md`
- **Common performance pitfalls + fixes:** `./performance-catalog.md`
- **Main reviewing skill (§5 Profile + §9 Playbook):** `./SKILL.md`
- **Original Elixir profiling reference:** `../elixir/debugging-profiling.md`
