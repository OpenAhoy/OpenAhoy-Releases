"""Build the release artifact directly from this checkout's plugin sources."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import stat
from zipfile import ZipFile, ZipInfo, ZIP_STORED

if __package__:
    from .check_relative_imports import check_relative_imports
else:
    from check_relative_imports import check_relative_imports

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = 'wechat-ecosystem'
MANIFEST = 'package-manifest.json'


def sources(checkout=ROOT):
    """Load the Git marketplace package, including its checked-in native helpers."""
    package = checkout / 'plugins' / PLUGIN
    if package.is_symlink() or not package.is_dir():
        raise ValueError('OpenAhoy plugin source directory is missing')
    entries = {}
    for path in sorted(package.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Symbolic link in plugin source: {path.name}')
        if path.is_dir():
            continue
        relative = path.relative_to(package).as_posix()
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode) or mode & 0o7000:
            raise ValueError(f'Unsupported source file mode: {relative}')
        entries[relative] = (path.read_bytes(), 0o755 if mode & 0o111 else 0o644)
    metadata = json.loads(entries['plugin.json'][0])
    if metadata['name'] != PLUGIN or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', metadata['version']):
        raise ValueError('Invalid OpenAhoy release identity')
    check_relative_imports(entries)
    return package, metadata['version'], entries


def manifest_bytes(entries):
    value = {'schema': 1, 'files': {path: sha256(raw).hexdigest()
             for path, (raw, _) in sorted(entries.items()) if path != MANIFEST}}
    return (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode()


def build(destination, checkout=ROOT):
    _, version, entries = sources(checkout)
    manifest = manifest_bytes(entries)
    if (entries.get(MANIFEST) != (manifest, 0o644)
            or (checkout / MANIFEST).read_bytes() != manifest):
        raise ValueError('Release manifests do not match the source files. Run --refresh-manifest after reviewing changes.')
    destination = Path(destination).absolute()
    archive = destination.with_name(destination.name + '.zip')
    if destination.exists() or archive.exists():
        raise FileExistsError('Choose an unused build destination')
    if destination.is_relative_to(checkout / 'plugins'):
        raise ValueError('Choose a build destination outside the plugin source directory')
    destination.mkdir(parents=True)
    for relative, (data, mode) in entries.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)
    # Stored entries make the output independent of the builder's zlib version.
    with ZipFile(archive, 'x', compression=ZIP_STORED) as zipped:
        for relative, (data, mode) in sorted(entries.items()):
            info = ZipInfo(f'{PLUGIN}/{relative}', date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = ZIP_STORED
            zipped.writestr(info, data)
    return {'version': version, 'directory': str(destination), 'archive': str(archive),
            'archive_sha256': sha256(archive.read_bytes()).hexdigest(),
            'manifest_sha256': sha256(manifest).hexdigest(),
            'files': len(entries) - 1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, nargs='?')
    parser.add_argument('--refresh-manifest', action='store_true')
    args = parser.parse_args()
    if args.refresh_manifest:
        if args.destination is not None:
            parser.error('Refresh the manifest before building into a separate destination.')
        package, _, entries = sources()
        manifest = manifest_bytes(entries)
        (package / MANIFEST).write_bytes(manifest)
        (ROOT / MANIFEST).write_bytes(manifest)
    elif args.destination is None:
        parser.error('Provide an unused build destination.')
    else:
        print(json.dumps(build(args.destination)))


if __name__ == '__main__':
    main()
