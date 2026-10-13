# Optional offline Python planner

The skill works with host tools alone. The repository Python package is optional,
requires Python 3.11+, and never launches agents.

```text
python -m model_effort_router request.json --dry-run
```

Dry run validates the request and emits decision payloads without network calls.
A real host still enforces dependencies, concurrency, ownership and task execution.

Model catalogue fields: id, provider, efforts, optional capabilities/description.
Use the exact T3 providerInstanceId as provider. Prefer explicit allowed triples:

```json
{"provider": "exact-instance", "model": "exact-model", "effort": "exact-effort"}
```

Providers may share model IDs. Legacy {model,effort} is accepted when the eligible
provider is unambiguous. pair_N is request-local and input-order-dependent, not a
persistent model ID. The package emits assignments/waves, not running-task handles.
See the repository README for optional Jev/checkpoint CLI arguments.
