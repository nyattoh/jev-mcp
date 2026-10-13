"""Check an exact T3 delegation target against a saved live catalogue. No I/O effects."""

import json
import sys
from pathlib import Path


class TargetError(ValueError):
    pass


def validate_target(catalogue, target):
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get('providers'), list):
        raise TargetError('invalid_catalogue')
    caller = catalogue.get('inheritedProviderInstanceId')
    if not isinstance(caller, str) or not caller.strip() or not any(
        isinstance(p, dict) and p.get('providerInstanceId') == caller for p in catalogue['providers']
    ):
        raise TargetError('unknown_caller_provider')
    fields = {'providerInstanceId', 'model', 'driverKind', 'options'}
    if not isinstance(target, dict) or set(target) - fields:
        raise TargetError('invalid_target_fields')
    provider_id, model_id = target.get('providerInstanceId'), target.get('model')
    if not isinstance(provider_id, str) or not isinstance(model_id, str):
        raise TargetError('explicit_provider_and_model_required')
    providers = [p for p in catalogue['providers'] if isinstance(p, dict)
                 and p.get('providerInstanceId') == provider_id]
    if len(providers) != 1:
        raise TargetError('unknown_or_ambiguous_provider')
    provider = providers[0]
    if provider.get('canRunChildTask') is not True:
        raise TargetError('provider_cannot_run_child_task')
    if caller != provider_id and provider.get('canRunCrossProviderChildTask') is not True:
        raise TargetError('cross_provider_delegation_unavailable')
    if 'driverKind' in target and target['driverKind'] != provider.get('driverKind'):
        raise TargetError('driver_mismatch')
    models = [m for m in provider.get('models', []) if isinstance(m, dict) and m.get('id') == model_id]
    if len(models) != 1:
        raise TargetError('unknown_or_ambiguous_model')
    option_specs = {o['id']: o for o in (models[0].get('options') or [])}
    raw_options = target.get('options')
    if raw_options is None:
        supplied = []
    elif isinstance(raw_options, dict):
        supplied = [{'id': key, 'value': value} for key, value in raw_options.items()]
    elif isinstance(raw_options, list):
        supplied = raw_options
    else:
        raise TargetError('invalid_options')
    options, seen = [], set()
    for option in supplied:
        if not isinstance(option, dict) or set(option) != {'id', 'value'}:
            raise TargetError('invalid_option_fields')
        key, value = option['id'], option['value']
        if not isinstance(key, str) or key not in option_specs:
            raise TargetError('unsupported_option')
        if key in seen:
            raise TargetError('duplicate_option')
        seen.add(key)
        spec = option_specs[key]
        if spec['type'] == 'select':
            if not isinstance(value, str) or value not in {v['id'] for v in spec['options']}:
                raise TargetError('unsupported_option_value')
        elif spec['type'] == 'boolean':
            if type(value) is not bool:
                raise TargetError('boolean_option_required')
        else:
            raise TargetError('unsupported_option_type')
        options.append({'id': key, 'value': value})
    result = {'providerInstanceId': provider_id, 'model': model_id}
    if 'driverKind' in target:
        result['driverKind'] = target['driverKind']
    if options:
        result['options'] = options
    return result


def validate_dispatch(catalogue, request):
    fields = {'task', 'target', 'mode', 'clientRequestId', 'title', 'role',
              'runtimeMode', 'interactionMode', 'timeoutMs'}
    if not isinstance(request, dict) or set(request) - fields:
        raise TargetError('invalid_dispatch_fields')
    if not isinstance(request.get('task'), str) or not request['task'].strip():
        raise TargetError('task_required')
    if request.get('mode', 'async') not in ('async', 'wait'):
        raise TargetError('unsupported_dispatch_mode')
    result = dict(request)
    result['target'] = validate_target(catalogue, request.get('target'))
    return result


def main():
    if len(sys.argv) != 3:
        print('Usage: validate_t3_target.py catalogue.json target.json', file=sys.stderr)
        return 2
    try:
        catalogue, target = (json.loads(Path(p).read_text(encoding='utf-8-sig')) for p in sys.argv[1:])
        if isinstance(target, dict) and 'target' in target:
            result = {'valid': True, 'dispatch': validate_dispatch(catalogue, target)}
        else:
            result = {'valid': True, 'target': validate_target(catalogue, target)}
    except TargetError as error:
        result = {'valid': False, 'error': str(error)}
    except (OSError, ValueError, KeyError, TypeError):
        result = {'valid': False, 'error': 'invalid_or_unreadable_input'}
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0 if result['valid'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
