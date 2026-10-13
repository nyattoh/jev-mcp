---
name: bench-ledger-router
description: Select available provider, model and reasoning-effort combinations for a task graph, delegate independent tasks concurrently, and validate the combined result. Use for multi-agent task decomposition, provider selection, model/effort routing and parallel execution across supported agent hosts. Keep small, inseparable tasks in the parent.
---

# Provider, Model and Effort Router

Use the host's actual delegation tools to complete the user's work. A routing plan
alone is not execution. Explicit user choices, permissions and workspace boundaries
take precedence. Do not expand the task into accounts, purchases or publication.

## Choose the execution shape

Identify deliverables, dependencies, file ownership, acceptance checks and the
intended workspace. Consider **serial_parent** and **parallel_disjoint**, adding
independent review when useful or requested. Choose useful parallelism, without
splitting a trivial edit to use more providers. Record the practical reason,
not internal reasoning transcripts or invented confidence scores.

Start only dependency-ready tasks. Two writers must not own the same files at the
same time. Each worker receives its deliverable, owned files, inputs, acceptance
checks and a reminder to preserve others' edits. The parent owns integration.

## Discover exact runtime choices

- Obtain the current provider/model/options catalogue from the host, including
  configured custom models. The native spawn tool's list may not be the full list.
- Execution identity is **(provider instance, model ID, effort option)**. A brand
  or display label is not an instance ID; providers may share a model name.
- Preserve exact model IDs, option keys, values and types. `reasoningEffort`,
  `effort` and `reasoning_effort` are not interchangeable API fields.
- If effort is encoded in a model ID, select that ID. If no effort control is
  exposed, record `host_default` and omit an invented argument. Similar labels
  across providers do not establish equivalent behaviour.
- Exclude providers that cannot run child tasks and targets the executor cannot
  represent. Shortlist a few valid choices **per task**, not the whole catalogue.
- Record catalogue timestamp, workspace and selection. Recheck when the runtime,
  available models, permissions or user constraints change.

For T3 Code, read [references/t3-code.md](references/t3-code.md). For other hosts,
read [references/adapters.md](references/adapters.md). Use
[references/routing-policy.md](references/routing-policy.md) for selection criteria;
there is no fixed provider hierarchy.

## Select and dispatch

Prefer the least resource-intensive supported combination likely to satisfy the
acceptance checks. Increase effort for ambiguity, interacting constraints or hard
validation; reduce it for bounded transformations. Honour user-mandated targets.
Tools, permissions, context capacity and workspace are hard constraints. Do not
invent prices, capability rankings, speed-ups or cost savings.
Effort labels are relative to their provider: a target exposing `low` is not
automatically cheaper or more suitable than another target exposing `medium`.
Select for the acceptance check first. A model catalogue alone may not establish
whether a child has search, filesystem or other task-specific tools.

Default to `decision_source: framework_only_local` and
`Jev API call: not made`. Jev is optional: read
[references/decision-gates.md](references/decision-gates.md) only when its configured
adapter and authorised use can materially help. An unavailable optional service
must not stop otherwise authorised local work.

Dispatch independent ready tasks concurrently within discovered host/user limits.
Retain actual selections and returned task handles. Prefer native spawn for a
same-provider target **only if** it supports the chosen model and effort. Otherwise
use the host's provider-aware child delegation tool. Ordinary top-level threads
or shell-launched provider CLIs are not substitutes for delegation; a documented
host transport fallback is permitted.

Check the **actual workspace binding** before delegating writes. A different path
in a prompt does not rebind the child. When the caller is in another project, use
a supported explicit-workspace executor or continue serially at the authorised
path. Create a new top-level conversation only when the user explicitly asks.

## Manage results and failures

Use completion notifications or bounded host waits, not busy polling. Distinguish
queued, running, waiting-for-children, result-available and terminal states. When
async work is running and no useful parent work is ready, end the turn so the host
can deliver its completion notification.

Capture concise task results:

```yaml
task_id: host-returned identifier
status: complete | partial | blocked | failed | cancelled
selection: {provider: exact_instance, model: exact_id, effort: exact_option_or_host_default}
deliverables: []
evidence: []
validation_run: []
unverified: []
hand_over: next required action, if any
```

A cancelled task or partial result is not successful completion. Preserve edits,
identify the unmet acceptance check and continue locally, revise the task, or
choose a supported alternative within the user's authority. Do not repeat an
unchanged failure or bypass an approval, account or billing restriction with a
different provider/transport.

Each new T3 review round needs a new delegated task, the original brief, prior
findings/responses, unresolved objections and a request ID stable across retries
of that round. Avoid duplicate active work when a request's result is unknown.

## Integrate and prove the result

Compare deliverables with the original request, reconcile contradictions against
source evidence, and run the smallest meaningful integrated checks. Do not release
dependent work solely on a worker's confidence or completion claim. Report failures
and unrun checks separately from passes.

Report **actual dispatch** separately from samples or proposed assignments.
Include provider/model/effort, completed checks and material limitations. Catalogue
presence does not prove launch success, authentication, quota or task completion.

The optional repository Python planner validates a DAG/allow-list and selects
routes; it does **not** execute agents. Read
[references/offline-router.md](references/offline-router.md) when using that CLI.
This self-contained skill works with existing host tools without installing Python
packages or provisioning API credentials.

## Benchmark-ledger evidence (bench_candidates.py)

The ledger is a **score table, not a filter**. Every live-catalogue model with an
effort option is a candidate; the ledger adds evidence where it exists.

When selecting a model for a delegated task:

1. Save the live catalogue (from `orchestrator_capabilities` or the host
   equivalent) as JSON, then run:

   ```
   python "<this skill>/scripts/bench_candidates.py" capabilities.json --requirements coding
   ```

   `--requirements` filters scores to matching benchmark names or domains (for
   example `coding`, `coding-implement`, `coding-verify`; the domain
   `coding-implement` matches the benchmark `terminal-bench-2-1`). A filtered
   query may return unknown-evidence candidates when no benchmark matches —
   retry without the filter for all ledger evidence.

2. The output ranks **performance-max × cost-min**: candidates with ledger
   evidence come first, ordered by score/cost efficiency (a small bonus for
   `measured` over `external`, higher `best_score` breaking ties), then
   unknown-evidence candidates in catalogue order.

3. Pick from the ranked list and state the evidence with the choice: rank,
   `best_score`, `best_source`, `cost.output`, and the chosen effort from the
   candidate's `efforts` list. Routine work may take a cheaper adequate
   candidate; design, integration and recovery justify the strongest. Models
   with `evidence: "unknown"` are legitimate choices — say that no benchmark
   evidence exists and why the choice still fits.

4. The ledger is read-only here. Do not invent, edit or extrapolate scores; to
   add measurements use the bench-ledger-engine project's record flow.

## Task-graph protocol (implement / verify / feedback loop)

When a decomposed task graph contains implementation tasks and their
independent verification tasks, run this protocol on top of the ranking:

1. **Diversified assignment.** For each implement/verify pair, pick the verify
   model from a **different vendor** than the implement model (use the
   `vendor` field). Reason: an independent family catches what the authoring
   family systematically misses. If no cross-vendor candidate exists, say so
   and fall back to the next-best same-vendor candidate. Mark that verify task
   `"no_cross_vendor_candidate": true` in the task-graph state so `task_gate.py` G3 accepts it.

2. **Hand-over contract.** Before dispatching a verify task, the implement
   task's output must be written to a file the verifier can read (diff,
   test results, or a short result note with paths). A verify task that
   receives no hand-over artifact must stop and ask, not guess.

3. **Verification verdict.** The verify task returns one of: `pass`,
   `fail <what and why>`, or `needs_review <question>`. A `fail` returns the
   work to the implement model with the verifier's report attached; re-run the
   same pair (max 2 rounds) before escalating to the user.

4. **Measured feedback (close the loop).** After a pair completes — pass OR
   fail — record the outcome into the ledger:

   ```
   python "<this skill>/scripts/record.py" --model <model id> \
       --bench <benchmark or task-domain name> --score <0-100> \
       --effort <effort used> --cost-per-task <USD if known> \
       --vendor <vendor, required the first time a model is recorded> \
       --notes "<one-line what was done>"
   ```

   Failures are recorded too (`--failure`): measured failures are evidence
   that reshapes the next ranking. This is how the ledger stops going stale.

5. **Ledger hygiene.** Never record a score for work the model did not do.
   External numbers go in via the ledger project, not through record.py.

## Machine enforcement (task_gate.py — do not skip)

The protocol above is enforced by scripts, not by goodwill. After each
implement/verify pair (and before reporting the graph complete), write a state
file and run the gate:

```
python "<this skill>/scripts/task_gate.py" state.json
```

Exit 0 = report complete. Exit 3 = the graph is NOT done; fix the listed
violations and re-run. Rules: G1 done-implements need a hand-over artifact,
G2 every implement needs a verify with verdict=pass, G3 verify must use a
different vendor than its implement, G4 total cost must stay within budget.

When decomposing, classify each task to pick the ledger requirements filter:

```
python "<this skill>/scripts/classify_task.py" "タスクの説明"
```

It prints kind (implement/verify/research/docs) and the `--requirements` value
to pass to bench_candidates.py. Verify tasks automatically fall back to
coding-implement scores when coding-verify has no benchmarks yet.
