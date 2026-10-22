#!/usr/bin/env python3
"""Verify vendored bytes against explicit, repository-relative lock entries."""
import hashlib
import json
from pathlib import Path


def check(root):
    lock = json.loads((root / 'sources.lock.json').read_text())
    for entry in lock['sources']:
        path = root / entry['path']
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('Source path escapes repository')
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError('Vendored source digest mismatch: '+entry['path'])
    return len(lock['sources'])


if __name__ == '__main__':
    print(f'{check(Path(__file__).resolve().parents[1])} pinned sources verified')
