#!/usr/bin/env python3
"""Build a deterministic, allowlisted beta archive and basename-only checksum."""
import argparse
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

try:
    from .check_export import EXPORT_FILES, check
except ImportError:  # direct script execution
    from check_export import EXPORT_FILES, check

VERSION = 'v0.1.0-beta.1'


def build(repo: Path, destination: Path) -> Path:
    repo, destination = Path(repo).resolve(), Path(destination).resolve()
    errors = check(repo)
    if errors:
        raise ValueError('Export validation failed: '+'; '.join(errors))
    # Read the validated files once; no symlinks, recursive discovery or state.
    files = [(name, (repo/name).read_bytes(), (repo/name).stat().st_mode & 0o111)
             for name in EXPORT_FILES]
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination/f'iterm2-utils-{VERSION}.tar.gz'
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', filename='', mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w') as tar:
            for name, content, executable in files:
                info = tarfile.TarInfo(f'iterm2-utils-{VERSION}/{name}')
                info.size = len(content)
                info.mode = 0o755 if executable else 0o644
                info.mtime = 0
                tar.addfile(info, io.BytesIO(content))
    payload = buffer.getvalue()
    archive.write_bytes(payload)
    archive.with_name(archive.name+'.sha256').write_text(hashlib.sha256(payload).hexdigest()+'  '+archive.name+'\n')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--destination', type=Path, default=Path('dist'))
    args = parser.parse_args()
    print(build(args.repo, args.destination))
