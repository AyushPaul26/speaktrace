"""Create a reviewable source/data archive; never include runtime user recordings."""
from pathlib import Path
import hashlib
import json
import zipfile
from verify_package import verify

ROOT = Path(__file__).resolve().parents[1]


def main():
    verify()
    destination = ROOT / 'dist/SpeakTrace-submission.zip'
    destination.parent.mkdir(exist_ok=True)
    allowed_roots = {'speaktrace', 'api', 'web', 'scripts', 'tests', 'docs', 'data', 'reports', 'output'}
    forbidden_parts = {'__pycache__', '.pytest_cache', '.runtime', '.venv', '.models', '.cache', 'raw', 'runtime'}
    excluded_artifacts = {'reports/browser-smoke-failure.jpg', 'reports/tests-current.txt'}
    files = []
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if not path.is_file() or path.is_symlink() or forbidden_parts.intersection(relative.parts):
            continue
        if len(relative.parts) == 1:
            include = path.suffix in {'.md', '.txt', '.py', '.bat', '.toml', '.json'} or path.name in {'LICENSE', '.gitignore', '.gitattributes', '.vercelignore', '.python-version'}
        else:
            include = relative.parts[0] in allowed_roots and path.suffix.lower() in {'.py', '.js', '.cjs', '.html', '.css', '.json', '.md', '.wav', '.jpg', '.png', '.pdf', '.txt'}
        if include and relative.parts[:2] != ('reports', 'package') and relative.as_posix() not in excluded_artifacts:
            files.append((path, relative.as_posix()))
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, relative in sorted(files, key=lambda item: item[1]):
            archive.write(path, 'SpeakTrace/' + relative)
    result = verify(archive=destination)
    result.update(path=str(destination), bytes=destination.stat().st_size,
                  sha256=hashlib.sha256(destination.read_bytes()).hexdigest())
    (ROOT / 'dist/package-manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
