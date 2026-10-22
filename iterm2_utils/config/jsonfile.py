"""Strict JSON pointer edits; no diagnostic contains input bodies."""
import json


def parse(content: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('Invalid JSON constant')
    try:
        return json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError):
        raise ValueError('Invalid JSON configuration') from None


def patch(content: bytes, pointer: tuple[str | int, ...], value: object, *, remove: bool = False) -> bytes:
    root = parse(content)
    if not pointer:
        if remove:
            raise ValueError('Cannot remove JSON root')
        root = value
    else:
        node = root
        for part in pointer[:-1]:
            if isinstance(node, dict) and part not in node:
                node[part] = {}
            node = node[part]
        last = pointer[-1]
        if remove:
            del node[last]
        else:
            node[last] = value
    return (json.dumps(root, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
