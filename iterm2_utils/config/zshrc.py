"""Only edit uniquely delimited package-owned blocks."""
import re


class PlacementConflict(ValueError):
    """A recognized legacy block cannot be restored at its original location."""



def markers(name):
    if name in {'legacy-status','legacy-restore'}:
        label = 'codex-iterm2-status' if name == 'legacy-status' else 'codex-resume'
        return '# >>> '+label+' >>>\n', '# <<< '+label+' <<<\n'
    if name == 'root':
        return '# >>> iterm2-utils >>>\n', '# <<< iterm2-utils <<<\n'
    if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
        raise ValueError('Invalid block name')
    return f'# >>> iterm2-utils:{name} >>>\n', f'# <<< iterm2-utils:{name} <<<\n'


def blocks(content):
    text = content.decode()
    names = re.findall(r'^# >>> iterm2-utils:([A-Za-z0-9_-]+) >>>\n',text,re.M)
    if '# >>> iterm2-utils >>>\n' in text:
        names.append('root')
    own_count = len(names)
    for name in ('legacy-status','legacy-restore'):
        start, end = markers(name)
        if start in text or end in text:
            names.append(name)
    result = {}
    spans = []
    for name in names:
        start, end = markers(name)
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('Ambiguous shell block')
        a, b = text.index(start), text.index(end)
        if b < a:
            raise ValueError('Invalid shell block')
        spans.append((a,b+len(end)))
        result[name] = text[a+len(start):b].removesuffix('\n')
    if (text.count('# >>> iterm2-utils') != own_count or
            text.count('# <<< iterm2-utils') != own_count):
        raise ValueError('Invalid shell block')
    ordered = sorted(spans)
    if any(left[1] > right[0] for left,right in zip(ordered,ordered[1:])):
        raise ValueError('Overlapping shell blocks')
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


def _spans(content):
    text = content.decode()
    return {name:(text.index(markers(name)[0]),text.index(markers(name)[1])+len(markers(name)[1]))
            for name in blocks(content)}


def _foreign_lines(content):
    import hashlib
    spans = list(_spans(content).values())
    lines, offset = [], 0
    for line in content.decode().splitlines(keepends=True):
        end = offset + len(line)
        if not any(start <= offset < stop for start,stop in spans):
            lines.append((offset,end,hashlib.sha256(line.encode()).hexdigest()))
        offset = end
    return lines


def placement(content, name):
    """Record no foreign text, only unambiguous line hashes and legacy order."""
    spans = _spans(content)
    start,end = spans[name]
    lines = _foreign_lines(content)
    before = next((line for line in reversed(lines) if line[1] <= start),None)
    after = next((line for line in lines if line[0] >= end),None)
    for anchor in (before,after):
        if anchor and sum(line[2] == anchor[2] for line in lines) != 1:
            raise PlacementConflict('Ambiguous legacy placement anchor')
    left = before[1] if before else 0
    right = after[0] if after else len(content.decode())
    order = [key for key,(a,b) in sorted(spans.items(),key=lambda item:item[1][0])
             if key in {'legacy-status','legacy-restore'} and left <= a and b <= right]
    return {'before':before[2] if before else None,'after':after[2] if after else None,'order':order}


def restore(content, name, replacement, location):
    """Restore a recognized block at its old gap, or refuse ambiguous anchors."""
    text = content.decode()
    spans = _spans(content)
    if name in spans:
        raise PlacementConflict('Legacy block already present')
    lines = _foreign_lines(content)
    def locate(key):
        wanted = location[key]
        if wanted is None:
            return -1 if key=='before' else len(lines)
        matches = [i for i,line in enumerate(lines) if line[2]==wanted]
        if len(matches) != 1:
            raise PlacementConflict('Legacy placement anchor changed')
        return matches[0]
    a,b = locate('before'),locate('after')
    if b != a+1:
        raise PlacementConflict('Foreign content changed at legacy placement')
    left = lines[a][1] if a >= 0 else 0
    right = lines[b][0] if b < len(lines) else len(text)
    order = location['order']
    existing = [key for key in order if key in spans]
    if any(not (left <= spans[key][0] and spans[key][1] <= right) for key in existing):
        raise PlacementConflict('Legacy block moved')
    if existing != sorted(existing,key=lambda key:spans[key][0]):
        raise PlacementConflict('Legacy block order changed')
    earlier = [key for key in existing if order.index(key) < order.index(name)]
    later = [key for key in existing if order.index(key) > order.index(name)]
    offset = spans[earlier[-1]][1] if earlier else spans[later[0]][0] if later else left
    start,end = markers(name)
    return (text[:offset]+start+replacement.rstrip('\n')+'\n'+end+text[offset:]).encode()
