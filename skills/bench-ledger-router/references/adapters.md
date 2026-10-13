# Other host adapters

Keep policy separate from execution. An adapter needs a current catalogue, exact
target selection, task handles, completion/status and authorised cancellation.

| Host | Execution constraint |
| --- | --- |
| Native Codex | Same-provider supported model/effort, permitted fork mode, inherited permissions and actual checkout |
| T3 Code | Read [t3-code.md](t3-code.md); use native spawn or provider-aware delegate as supported |
| Claude Task/Agent | Only model aliases and effort controls advertised by the live tool schema |
| Gemini host | Current subagent/delegate interface; without one execute serially and report no child dispatch |
| Existing CLI/API orchestrator | Authorised adapter, allow-list, task IDs and bounded concurrency; no new runner to bypass missing tools |

Normalise each route as provider instance, exact model ID, exact effort or
`host_default`, executor, and executor-specific options. Providers may share model
names. Preserve boolean/select value types and option keys; do not silently
translate unsupported triples. Credentials, tools and permissions may differ even
when model labels match. Successful discovery is not execution evidence.
