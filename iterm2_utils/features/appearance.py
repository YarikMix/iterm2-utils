"""Pure appearance configuration and content-addressed custom icon builder."""
import hashlib
import json
from pathlib import Path
import struct
import zlib

from runtime.appearance import BUILTIN_ICONS, load_rules
from .. import state
from ..models import ChangeSet, Context, FileEdit, Finding, Selection, UiStep


def _png(path):
    # Bound both source bytes and decoded image size before accepting local input.
    with path.open('rb') as source:
        data = source.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG')
    offset, kinds, compressed = 8, [], bytearray()
    while offset < len(data):
        if len(data) - offset < 12:
            raise ValueError('Truncated PNG')
        size = int.from_bytes(data[offset:offset+4], 'big')
        kind = data[offset+4:offset+8]
        payload = data[offset+8:offset+8+size]
        end = offset + size + 12
        if end > len(data) or zlib.crc32(kind+payload) != int.from_bytes(data[end-4:end], 'big'):
            raise ValueError('Invalid PNG chunk')
        if not kinds and kind != b'IHDR' or kind == b'IHDR' and kinds:
            raise ValueError('Invalid PNG header')
        if kind == b'IHDR':
            if size != 13:
                raise ValueError('Invalid PNG header')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            depths = {0:{1,2,4,8,16}, 2:{8,16}, 3:{1,2,4,8}, 4:{8,16}, 6:{8,16}}
            if not 0 < width <= 4096 or not 0 < height <= 4096 or depth not in depths.get(color, ()) or compression or filtering or interlace not in {0,1}:
                raise ValueError('Unsupported PNG header')
        elif kind == b'IDAT':
            if b'IDAT' in kinds and kinds[-1] != b'IDAT':
                raise ValueError('Invalid PNG data order')
            compressed.extend(payload)
        elif kind == b'IEND':
            if size or end != len(data) or not compressed:
                raise ValueError('Invalid PNG end')
        elif kind == b'PLTE':
            if b'PLTE' in kinds or b'IDAT' in kinds or size == 0 or size % 3 or size > 768:
                raise ValueError('Invalid PNG palette')
        elif not kind[0] & 32:
            raise ValueError('Unknown critical PNG chunk')
        kinds.append(kind)
        offset = end
    if not kinds or kinds[-1] != b'IEND' or color == 3 and b'PLTE' not in kinds:
        raise ValueError('Incomplete PNG')
    decoder = zlib.decompressobj()
    try:
        decoded = decoder.decompress(bytes(compressed), 128 * 1024 * 1024 + 1)
    except zlib.error as error:
        raise ValueError('Invalid PNG data') from error
    if not decoded or len(decoded) > 128 * 1024 * 1024 or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid PNG data')
    channels = {0:1, 2:3, 3:1, 4:2, 6:4}[color]
    passes = ((0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),(0,2,2,4),(1,0,2,2),(0,1,1,2)) if interlace else ((0,0,1,1),)
    offset = 0
    for x, y, dx, dy in passes:
        columns, rows = max(0,(width-x+dx-1)//dx), max(0,(height-y+dy-1)//dy)
        if not columns or not rows:
            continue
        stride = (columns*depth*channels+7)//8+1
        end = offset+rows*stride
        if end > len(decoded) or any(decoded[index] > 4 for index in range(offset,end,stride)):
            raise ValueError('Invalid PNG scanlines')
        offset = end
    if offset != len(decoded):
        raise ValueError('Invalid PNG pixel count')
    return data


def build(context: Context, selection: Selection) -> ChangeSet:
    changes = ChangeSet([], [], [])
    if not selection.agents_for('appearance'):
        return changes
    installed = context.paths.config/'appearance.json'
    receipt = state.load(context.paths.data/'receipt.json')
    owned = receipt and any(r['target'] == str(installed.resolve()) and
        {'appearance','codex:appearance'} & set(r['owners']) for r in receipt.resources)
    if context.appearance_config is None and not owned:
        changes.findings.append(Finding('appearance','codex','appearance_config_required','conflict',
            'First installation requires --appearance-config with valid project rules; repeat installation uses the owned installed configuration.'))
        return changes
    before = installed.read_bytes() if installed.exists() else None
    if before is not None:
        if owned:
            # Validate retained structure before replacing projects; never delete foreign keys.
            load_rules(installed)
        elif json.loads(before) != {}:
            raise ValueError('Existing nonempty configuration is not owned')
    rules = load_rules(context.appearance_config or installed)
    copies = {}
    for rule in rules:
        icon = rule['icon']
        if icon in BUILTIN_ICONS:
            content = _png(context.paths.repo/'runtime/assets/appearance'/(icon+'.png'))
            # Builtins remain stable registry names; payload owns their delivery.
            continue
        source = Path(icon)
        content = _png(source)
        target = context.paths.data/'appearance/icons'/(hashlib.sha256(content).hexdigest()+'.png')
        if context.appearance_config is None and source != target:
            raise ValueError('Installed custom icons must be content addressed')
        copies[target] = content
        rule['icon'] = str(target)
    for path, content in sorted(copies.items()):
        changes.edits.append(FileEdit(path, path.read_bytes() if path.exists() else None, content, 0o600, 'appearance'))
    content = (json.dumps({'projects':rules}, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode()
    changes.edits.append(FileEdit(installed, before, content, 0o600, 'appearance'))
    changes.findings.append(Finding('appearance','codex','appearance_api','pending_ui',
        'Explicit session Python API access and rendered appearance are not verified.'))
    changes.ui.append(UiStep('appearance_api', 'appearance', 'codex',
        'Enable iTerm2 Python API and authorize the selected Python, then reconcile appearance_api in an explicit iTerm2 session. This verifies access, not rendered appearance.'))
    return changes
