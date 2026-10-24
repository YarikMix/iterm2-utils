"""Conservative statement-span TOML edits, validated with tomllib.

Inline/dotted forms and arrays of tables are deliberately unsupported for edits.
Multiline scalar statements are consumed whole before looking for another key.
"""
import json
import re
import tomllib

_NAME = re.compile(r'[A-Za-z0-9_-]+\Z')


def parse(content):
    try:
        return tomllib.loads(content.decode())
    except (ValueError, UnicodeError):
        raise ValueError('Invalid TOML configuration') from None


def literal(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return '[' + ', '.join(literal(v) for v in value) + ']'
    if isinstance(value, dict):
        if any(not _NAME.fullmatch(k) for k in value):
            raise ValueError('Unsupported TOML key')
        return '{' + ', '.join(k+' = '+literal(v) for k,v in value.items()) + '}'
    raise ValueError('Unsupported TOML value')


def _spans(content):
    lines = content.decode().splitlines(keepends=True)
    result, table, i = [], (), 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped or stripped.startswith('#'):
            i += 1
            continue
        if stripped.startswith('['):
            match = re.fullmatch(r'\[(.+)\]\s*(?:#.*)?', stripped)
            if not match:
                raise ValueError('Unsupported TOML table form')
            parsed = tomllib.loads('['+match[1]+']')
            address = []
            while isinstance(parsed,dict) and len(parsed) == 1:
                key, parsed = next(iter(parsed.items()))
                address.append(key)
            if parsed != {}:
                raise ValueError('Unsupported TOML table form')
            table = tuple(address)
            result.append(('table',table,i,i+1))
            i += 1
            continue
        start = i
        while i < len(lines):
            i += 1
            try:
                item = tomllib.loads(''.join(lines[start:i]))
                break
            except tomllib.TOMLDecodeError:
                continue
        else:
            raise ValueError('Unsupported TOML statement')
        # Match one complete key token; dots/equals inside quotes are data.
        match = re.match(r'''\s*("(?:[^"\\]|\\.)*"|'[^']*'|[A-Za-z0-9_-]+)\s*=''', lines[start])
        if not match or len(item) != 1:
            raise ValueError('Unsupported dotted TOML key')
        key = next(iter(tomllib.loads(match[1] + ' = 0')))
        result.append(('value',table+(key,),start,i))
    return lines, result


def patch(content: bytes, pointer: tuple[str, ...], value, *, remove=False):
    parse(content)
    if not pointer or any(not isinstance(p,str) or not p or '\n' in p for p in pointer):
        raise ValueError('Unsupported TOML address')
    lines, spans = _spans(content)
    parent, key = pointer[:-1], pointer[-1]
    # Editing through an inline table would silently replace neighboring values.
    for kind, address, start, end in spans:
        if kind == 'value' and len(address) < len(pointer) and pointer[:len(address)] == address:
            raise ValueError('Inline TOML table cannot be edited')
    token = key if _NAME.fullmatch(key) else json.dumps(key, ensure_ascii=False)
    replacement = '' if remove else token + ' = ' + literal(value) + '\n'
    matches = [s for s in spans if s[0]=='value' and s[1] == pointer]
    if matches:
        _, _, start, end = matches[0]
        lines[start:end] = [replacement]
    elif remove:
        return content
    else:
        headers = [s for s in spans if s[0]=='table' and s[1] == parent]
        if headers:
            start = headers[0][3]
            end = next((s[2] for s in spans if s[0]=='table' and s[2]>=start),len(lines))
            if end and not lines[end-1].endswith('\n'):
                lines[end-1] += '\n'
            lines.insert(end,replacement)
        elif not parent:
            lines.insert(0,replacement)
        else:
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += '\n'
            lines.extend(['\n['+'.'.join(p if _NAME.fullmatch(p) else json.dumps(p) for p in parent)+']\n',replacement])
    result = ''.join(lines).encode()
    parse(result)
    return result


def set_tui_key(content: bytes, key: str, value: object) -> bytes:
    return patch(content,('tui',key),value)
