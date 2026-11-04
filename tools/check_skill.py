#!/usr/bin/env python3
"""Small stdlib structural validator. This does not assess agent behavior."""
import json
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
    if root.name == 'iterm2-launch':
        # Check documentation examples only; this does not execute or prove a launch.
        try:
            content = (root/'references/resume.md').read_text()
            examples = json.loads(re.search(r'```json\n(.*?)\n```', content, re.S)[1])
            if not isinstance(examples, list) or len(examples) != 2:
                raise ValueError()
            for example in examples:
                title, argv = example['processTitle'], example['expected_argv']
                if not isinstance(title, str) or not title or not isinstance(argv, list) or not argv:
                    raise ValueError()
                commands = [' '.join([title, *(['--no-daemon']*n), *argv]) for n in range(3)]
                if type(example['matches']) is not bool or example['matches'] != (example['commandLine'] in commands):
                    raise ValueError()
            if {example['matches'] for example in examples} != {True, False}:
                raise ValueError()
        except (OSError, ValueError, TypeError, KeyError):
            errors.append('Invalid launch command examples')
    return errors


if __name__ == '__main__':
    roots = [Path(sys.argv[1])] if len(sys.argv) > 1 else [
        Path(__file__).resolve().parents[1]/'skills'/name
        for name in ('iterm2-setup', 'iterm2-launch', 'iterm2-projects')]
    errors = [(root.name+': ' if len(roots) > 1 else '')+error
              for root in roots for error in check(root)]
    for error in errors:
        print(error, file=sys.stderr)
    if not errors:
        print((f'{len(roots)} skills structurally valid' if len(roots) > 1 else 'Skill structure valid')+
              ' (not a behavioral evaluation).')
    raise SystemExit(bool(errors))
