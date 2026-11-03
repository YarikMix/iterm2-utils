"""Single-request native SDK worker. No terminal text, session writes or retries."""
import asyncio
from contextlib import redirect_stderr, redirect_stdout
import json
import os
import sys

from .config.iterm import (BAR_KEYS, existing, identifier, same, validate_bar,
                           validate_inventory, validate_position)


def _request(request):
    if type(request) is not dict:
        raise ValueError()
    operation = request.get('operation')
    fields = {'operation'}
    if operation == 'inspect' and 'reference_guids' in request:
        fields.add('reference_guids')
        if type(request['reference_guids']) is not list:
            raise ValueError()
        for guid in request['reference_guids']:
            identifier(guid)
    if operation == 'inspect' and 'replaced_bars' in request:
        fields.add('replaced_bars')
        rows = request['replaced_bars']
        if type(rows) is not list or len(rows) > 256:
            raise ValueError()
        guids = set()
        for row in rows:
            if type(row) is not dict or set(row) != {'guid','bar'} or row['guid'] in guids:
                raise ValueError()
            guids.add(identifier(row['guid'])); validate_bar(row['bar'])
    if operation in {'read_bar','write_bar'}:
        fields.add('guid'); identifier(request.get('guid'))
    if operation in {'write_bar','write_position'}:
        fields.update({'value','expected'})
        validator = validate_bar if operation == 'write_bar' else validate_position
        validator(request.get('value')); existing(request.get('expected'), validator)
    if operation not in {'inspect','read_bar','write_bar','read_position','write_position'} or set(request) != fields:
        raise ValueError()
    return operation


def _refs(properties, guids, names):
    found = set()
    parent = properties.get('Dynamic Profile Parent Name')
    if parent:
        if type(parent) is not str or parent not in names:
            raise ValueError('Unknown dynamic profile parent')
        found.add(names[parent])
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                visit(key); visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            # Include opaque/encoded and hidden fields, even when not visible in the bar.
            found.update(guid for guid in guids if guid in value)
            try:
                decoded = json.loads(value)
            except ValueError:
                return
            if isinstance(decoded, (dict,list,str)) and decoded != value:
                visit(decoded)
    visit({k:v for k,v in properties.items() if k not in {'Guid','Name'}})
    return sorted(found)


def _bar(properties):
    return validate_bar({key:properties[key] for key in BAR_KEYS})


async def _inventory(sdk, connection, reference_guids=(), replaced_bars=()):
    profiles = await sdk.Profile.async_get(connection)
    raw = [p.all_properties for p in profiles]
    persistent_guids = {identifier(p['Guid']) for p in raw}
    guids = persistent_guids | set(reference_guids)
    names = {identifier(p['Name']):p['Guid'] for p in raw}
    replacements = {p['guid']:p['bar'] for p in replaced_bars}
    if not set(replacements) <= persistent_guids:
        raise ValueError('Replaced profile unavailable')
    rows = []
    for p in raw:
        properties = p
        if p['Guid'] in replacements:
            if not same(_bar(p),replacements[p['Guid']]):
                raise ValueError('Replaced profile bar changed')
            properties = {k:v for k,v in p.items() if k not in BAR_KEYS}
        rows.append(dict(guid=p['Guid'], name=p['Name'], bar=_bar(p),
            working_directory=p.get('Working Directory'), references=_refs(properties,guids,names)))
    app = await sdk.async_get_app(connection)
    sessions = [s for window in app.terminal_windows for tab in window.tabs for s in tab.all_sessions]
    sessions.extend(app.buried_sessions)
    records = []
    for session in sessions:
        properties = (await session.async_get_profile()).all_properties
        original = properties.get('Original Guid')
        guid = identifier(original if original is not None else properties.get('Guid'))
        records.append(dict(id=session.session_id, profile_guid=guid, bar=_bar(properties),
                            references=_refs(properties, guids, names), provenance=guid in persistent_guids))
    default = await sdk.Profile.async_get_default(connection)
    position = await sdk.preferences.async_get_preference(connection, sdk.preferences.PreferenceKey.STATUS_BAR_POSITION)
    return validate_inventory(dict(complete=True, profiles=rows, sessions=records,
                                   default_guid=default.guid, position=position))


def _profile(snapshot, guid):
    matches = [p for p in snapshot['profiles'] if p['guid'] == guid]
    if len(matches) != 1:
        raise ValueError()
    return matches[0]


def _sessions(snapshot, guid, bar):
    for session in snapshot['sessions']:
        if not session['provenance'] or (session['profile_guid'] == guid and not same(session['bar'], bar)):
            raise ValueError()


async def _operate(request):
    connection, sent = None, False
    try:
        operation = _request(request)
        import iterm2
        connection = await iterm2.Connection.async_create()
        snapshot = await _inventory(iterm2, connection, request.get('reference_guids', ()), request.get('replaced_bars', ()))
        if operation == 'inspect':
            return {'status':'ok','value':snapshot}
        bar = operation.endswith('_bar')
        current = _profile(snapshot, request['guid'])['bar'] if bar else snapshot['position']
        if operation.startswith('write_'):
            if not same({'exists':True,'value':current}, request['expected']):
                raise ValueError()
            if bar:
                _sessions(snapshot, request['guid'], current)
                # Refresh both parent and session provenance immediately before dispatch.
                fresh = await _inventory(iterm2, connection)
                if not same(_profile(fresh, request['guid'])['bar'], current):
                    raise ValueError()
                _sessions(fresh, request['guid'], current)
                sent = True
                await iterm2.rpc.async_set_profile_properties_json(connection, None,
                    [(key,json.dumps(request['value'][key], allow_nan=False)) for key in sorted(BAR_KEYS)],
                    guids=[request['guid']])
            else:
                current = await iterm2.preferences.async_get_preference(connection, iterm2.preferences.PreferenceKey.STATUS_BAR_POSITION)
                if not same({'exists':True,'value':current}, request['expected']):
                    raise ValueError()
                sent = True
                await iterm2.preferences.async_set_preference(connection,
                    iterm2.preferences.PreferenceKey.STATUS_BAR_POSITION, request['value'])
            snapshot = await _inventory(iterm2, connection)
            current = _profile(snapshot, request['guid'])['bar'] if bar else snapshot['position']
            if not same(current, request['value']):
                raise ValueError()
            if bar:
                _sessions(snapshot, request['guid'], current)
        return {'status':'ok','value':{'exists':True,'value':current}}
    except (Exception, SystemExit, asyncio.CancelledError):
        return {'status':'unknown' if sent else 'conflict'}
    finally:
        if connection is not None:
            try:
                async with asyncio.timeout(.2):
                    await connection.websocket.close()
            except (Exception, SystemExit, asyncio.CancelledError):
                pass


def main():
    result = {'status':'conflict'}
    try:
        raw = sys.stdin.read(1048577)
        if len(raw) > 1048576:
            raise ValueError()
        request = json.loads(raw)
        with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
            result = asyncio.run(_operate(request))
    except (Exception, SystemExit):
        pass
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':
    main()
