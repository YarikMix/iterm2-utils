"""Typed native resources; SDK access stays in one bounded selected-Python child."""
import json
import re
import subprocess
from pathlib import Path

BAR_KEYS = frozenset({'Show Status Bar', 'Status Bar Layout'})
DOMAIN = 'com.googlecode.iterm2'
POSITION_BOTTOM = 1


class MutationUnknown(ValueError):
    """A native write may have dispatched; retain durable intent for recovery."""
    def __init__(self):
        super().__init__('Native mutation outcome unknown; recovery intent retained.')


def identifier(value):
    if type(value) is not str or not value or len(value) > 256 or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid native identifier')
    return value


def validate_bar(value):
    if (type(value) is not dict or set(value) != BAR_KEYS or
            type(value['Show Status Bar']) is not bool or type(value['Status Bar Layout']) is not dict):
        raise ValueError('Native bar requires both existing typed properties')
    try:
        encoded = json.dumps(value, allow_nan=False)
        if not same(value, json.loads(encoded)):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Invalid native bar layout') from None
    return value


def validate_position(value):
    if type(value) is not int or value not in (0, 1):
        raise ValueError('Invalid native status bar position')
    return value


def existing(value, validator):
    if type(value) is not dict or set(value) != {'exists','value'} or value['exists'] is not True:
        raise ValueError('Native value must exist')
    validator(value['value'])
    return value


def same(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(same(a,b) for a,b in zip(left,right))
    return left == right


def validate_inventory(value):
    if (type(value) is not dict or set(value) != {'complete','profiles','sessions','default_guid','position'} or
            value['complete'] is not True or type(value['profiles']) is not list or type(value['sessions']) is not list):
        raise ValueError('Native inventory coverage unavailable')
    validate_position(value['position'])
    identifier(value['default_guid'])
    guids, names, sessions = set(), set(), set()
    for profile in value['profiles']:
        if type(profile) is not dict or set(profile) != {'guid','name','bar','working_directory','references'}:
            raise ValueError('Native profile inventory unavailable')
        guid, name = identifier(profile['guid']), identifier(profile['name'])
        if guid in guids or name in names or (profile['working_directory'] is not None and type(profile['working_directory']) is not str):
            raise ValueError('Ambiguous native profile inventory')
        guids.add(guid); names.add(name)
        validate_bar(profile['bar'])
        _references(profile['references'])
    if value['default_guid'] not in guids:
        raise ValueError('Native default profile unavailable')
    for session in value['sessions']:
        if type(session) is not dict or set(session) != {'id','profile_guid','bar','references','provenance'}:
            raise ValueError('Native session inventory unavailable')
        sid = identifier(session['id'])
        identifier(session['profile_guid'])
        if sid in sessions or type(session['provenance']) is not bool:
            raise ValueError('Ambiguous native session inventory')
        if session['provenance'] and session['profile_guid'] not in guids:
            raise ValueError('Unknown native session provenance')
        sessions.add(sid)
        validate_bar(session['bar'])
        _references(session['references'])
    return value


def _references(values):
    if type(values) is not list or any(type(v) is not str for v in values) or len(set(values)) != len(values):
        raise ValueError('Native reference coverage unavailable')
    for value in values:
        identifier(value)


def _request(context, runner, request):
    mutation = request['operation'].startswith('write_')
    python = context.executables.get('python3')
    version = context.versions.get('python3', '')
    match = re.match(r'^(\d+)\.(\d+)', version)
    if python is None or not Path(python).is_absolute() or not match or tuple(map(int,match.groups())) < (3,11):
        raise ValueError('Selected Python 3.11+ unavailable')
    bootstrap = 'import runpy,sys; sys.path.insert(0,sys.argv[1]); runpy.run_module("iterm2_utils.profile_api",run_name="__main__")'
    try:
        result = runner.run([str(python), '-c', bootstrap, str(Path(__file__).resolve().parents[2])],
                            stdin=json.dumps(request, allow_nan=False), timeout=10)
        if result.returncode or len(result.stdout) > 1048576:
            raise ValueError()
        response = json.loads(result.stdout)
        if response == {'status':'conflict'}:
            raise _Conflict()
        if type(response) is not dict or set(response) != {'status','value'} or response['status'] != 'ok':
            raise ValueError()
        return response['value']
    except _Conflict:
        raise ValueError('Native state or session propagation conflict') from None
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        if mutation:
            raise MutationUnknown() from None
        raise ValueError('Native inventory unavailable; check Python SDK and API authorization') from None


class _Conflict(Exception):
    pass


def inspect(context, runner):
    return validate_inventory(_request(context, runner, {'operation':'inspect'}))


def read_bar(guid, context, runner):
    value = _request(context, runner, {'operation':'read_bar','guid':identifier(guid)})
    return existing(value, validate_bar)


def write_bar(guid, value, context, runner, *, expected):
    identifier(guid); validate_bar(value); existing(expected, validate_bar)
    result = _request(context, runner, {'operation':'write_bar','guid':guid,'value':value,'expected':expected})
    if not same(result, {'exists':True,'value':value}):
        raise MutationUnknown()


def read_position(context, runner):
    return existing(_request(context, runner, {'operation':'read_position'}), validate_position)


def write_position(value, context, runner, *, expected):
    validate_position(value); existing(expected, validate_position)
    result = _request(context, runner, {'operation':'write_position','value':value,'expected':expected})
    if not same(result, {'exists':True,'value':value}):
        raise MutationUnknown()


def ensure_unreferenced(removed_guids, owned_guids, context, runner, *, replaced_bars=()):
    removed, owned = set(removed_guids), set(owned_guids)
    for guid in removed | owned:
        identifier(guid)
    if not removed <= owned:
        raise ValueError('Native deletion ownership unavailable')
    request = {'operation':'inspect','reference_guids':sorted(removed)}
    if replaced_bars:
        for row in replaced_bars:
            identifier(row['guid']); validate_bar(row['bar'])
            if row['guid'] not in owned - removed:
                raise ValueError('Invalid replaced profile')
        request['replaced_bars'] = list(replaced_bars)
    snapshot = validate_inventory(_request(context, runner, request))
    if snapshot['default_guid'] in removed:
        raise ValueError('Native profile remains the default')
    for profile in snapshot['profiles']:
        if profile['guid'] not in removed and removed.intersection(profile['references']):
            raise ValueError('Native profile has surviving external references')
    for session in snapshot['sessions']:
        if not session['provenance'] or session['profile_guid'] in removed or removed.intersection(session['references']):
            raise ValueError('Native profile has live session references or unknown coverage')
