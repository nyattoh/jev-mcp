# T3 Code adapter

Use actual session tools; names may have an MCP prefix.

## Discover and check

Call `orchestrator_capabilities({})`. Read exact `providerInstanceId`,
`driverKind`, `canRunChildTask`, model IDs and each model's option schema.
Call `t3_worktree_status({})` when workspace identity affects delegation:
effective path is attached `worktreePath`, otherwise `projectWorkspaceRoot`.
Confirm it matches the user's checkout before delegating writes.

Keep unavailable providers out. Preserve option IDs and select/boolean types.
No effort option means omit it; model-encoded effort is selected by the exact ID.
Do not send hundreds of catalogue entries to each worker. If tools seem absent,
make one bounded direct call before declaring them unavailable. The documented
ACP MCP fallback is permitted when exposed; an ordinary CLI runner is not.

## Dispatch

Use native spawn for a supported same-provider target, with exact model and
reasoning-effort arguments. A full-history fork may disallow overrides: use a
permitted fork mode and provide the required context. Do not pass provider IDs to
a native tool that has no such parameter.
For a native schema advertising `reasoning_effort`, that is the argument name;
`reasoningEffort` is a T3 option key only when that provider advertises it. Inspect
each executor schema rather than copying option names between executors.

Otherwise use `delegate_task`:

```json
{
  "task": "Bounded brief, actual workspace, owned files, inputs, acceptance checks",
  "target": {
    "providerInstanceId": "EXACT_LIVE_INSTANCE",
    "model": "EXACT_LIVE_MODEL",
    "options": [{"id": "EXACT_LIVE_OPTION_KEY", "value": "EXACT_LIVE_OPTION_VALUE"}]
  },
  "mode": "async",
  "clientRequestId": "unique-task-round-id"
}
```

Uppercase values are illustrations, not available model entries. Omit options when
no override is needed. Do not escalate the runtime merely to avoid approval.
Provider options belong inside `target.options`, never at the top level of
`delegate_task`. A top-level options field may be ignored and lose the requested
effort. Validate the whole proposed dispatch when checking generated tool calls.
A read-only task can use a compact public fixture instead of private files.

`delegate_task` inherits the caller's actual project/checkout. A prompt path cannot
fix a mismatched binding. `t3_thread_launch` creates an ordinary top-level thread
and requires explicit user instruction, not merely a request for subagents.
For an authorised launch, specify project/workspaceStrategy in the launch call,
retain its ID and inspect preparation before claiming it runs. Do not repoint a
shared project's root to relocate one task.

## Lifecycle

- Retain `taskId`; use `task_status` when needed and `task_cancel` for an
  authorised stop. `childThreadId` is backing storage.
- Prefer async notifications. With no useful parent work ready, end the turn.
  Wait timeout is not cancellation.
- Inspect workState, pending child runs and terminal summary. A completed turn
  with live nested work is not a completed task. Later child turns do not reopen
  its published result or extend its cancellation scope.
- Each new review round uses another `delegate_task` with original brief,
  findings/responses and a new request ID stable across retries of that round.
  Do not start it with `t3_thread_send(childThreadId, ...)`.
- Permission denial, login, quota and pending approval are real limitations.
  Do not claim success or bypass gates. Reassign only within existing authority.

Optional exact target validation:

```text
python scripts/validate_t3_target.py catalogue.json target.json
```

This checks a saved structured catalogue, makes no network call and executes no
agent. Refresh stale catalogues before dispatch. Validity is not launch evidence.
The second file may instead contain a complete `delegate_task` request; the
validator then also rejects misplaced top-level options.
