#!/usr/bin/env python3
"""Small stdlib structural validator. This does not assess agent behavior."""
import re
import sys
from pathlib import Path


def check(root):
    errors = []
    entry = root/'SKILL.md'
    if not entry.is_file() or entry.is_symlink():
        return ['SKILL.md must be a regular file']
    text = entry.read_text()
    match = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
    if not match:
        return ['Missing standard frontmatter']
    fields = {}
    for line in match[1].splitlines():
        key, sep, value = line.partition(':')
        if not sep or key in fields:
            errors.append('Invalid or duplicate frontmatter field')
        fields[key] = value.strip()
    if fields.get('name') != root.name or not re.fullmatch(r'[a-z0-9-]{1,64}', fields.get('name', '')):
        errors.append('Invalid skill name')
    if not fields.get('description') or len(fields['description']) > 1024:
        errors.append('A concise discovery description is required')
    referenced = set()
    for file in root.rglob('*'):
        if file.is_symlink():
            errors.append('Exported package must contain no symlinks')
        if not file.is_file() or file.suffix != '.md':
            continue
        content = file.read_text()
        if re.search(r'/Users/|/home/|~/.paiw|\.ai/skills|ai-proxy\.vk\.team', content):
            errors.append('Machine-specific path or private dependency in '+str(file.relative_to(root)))
        for link in re.findall(r'\]\(([^)]+)\)', content):
            if '://' in link or link.startswith('#'):
                continue
            destination = (file.parent/link.split('#')[0]).resolve()
            if not destination.is_relative_to(root.resolve()) or not destination.is_file():
                errors.append('Broken or external local reference: '+link)
            else:
                referenced.add(destination)
    for file in (root/'references').glob('*.md'):
        if file.resolve() not in referenced:
            errors.append('Unlinked reference: '+file.name)
    return errors


if __name__ == '__main__':
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]/'skills/iterm2-setup'
    errors = check(root)
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print('Skill structure valid (not a behavioral evaluation).')
    raise SystemExit(bool(errors))
