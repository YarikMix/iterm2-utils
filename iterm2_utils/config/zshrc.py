"""Only edit uniquely delimited package-owned blocks."""
import re


def markers(name):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise ValueError('Invalid block name')
    return f'# >>> iterm2-utils:{name} >>>\n', f'# <<< iterm2-utils:{name} <<<\n'


def blocks(content):
    text = content.decode()
    names = re.findall(r'^# >>> iterm2-utils:([A-Za-z0-9_-]+) >>>\n',text,re.M)
    result = {}
    for name in names:
        start, end = markers(name)
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('Ambiguous shell block')
        a, b = text.index(start), text.index(end)
        if b < a:
            raise ValueError('Invalid shell block')
        result[name] = text[a+len(start):b].removesuffix('\n')
    if text.count('# >>> iterm2-utils:') != len(names) or text.count('# <<< iterm2-utils:') != len(names):
        raise ValueError('Invalid shell block')
    return result


def block(content: bytes, name: str, replacement: str | None) -> bytes:
    text = content.decode()
    existing = blocks(content)
    start, end = markers(name)
    value = '' if replacement is None else start + replacement.rstrip('\n') + '\n' + end
    if name in existing:
        a, b = text.index(start), text.index(end)+len(end)
        text = text[:a]+value+text[b:]
    elif replacement is not None:
        if text and not text.endswith('\n'):
            raise ValueError('Shell configuration needs final newline')
        text += value
    return text.encode()
