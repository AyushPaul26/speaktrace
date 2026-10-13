"""Run the implementation checks and retain their actual exit codes/output."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    checks = [
        ('Python behavior tests', [sys.executable, '-m', 'pytest', '-q', '--tb=short', '--basetemp', f'.runtime/pytest-verification-{uuid.uuid4().hex[:8]}']),
        ('Frontend behavior tests', ['node', '--test', 'web/core.test.cjs', 'web/diagnostics.test.cjs', 'web/hosted.test.cjs']),
        ('Frontend markup and tokens', [sys.executable, 'web/check_ui.py']),
        ('Frontend syntax', ['node', '--check', 'web/app.js']),
        ('Diagnostic chart syntax', ['node', '--check', 'web/diagnostics.js']),
        ('Hosted transport syntax', ['node', '--check', 'web/hosted.js']),
        ('Python compilation', [sys.executable, '-m', 'compileall', '-q', 'speaktrace', 'scripts', 'api', 'run.py']),
    ]
    records = []
    for name, command in checks:
        print(name, flush=True)
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
        records.append({'name': name, 'command': command, 'exit_code': result.returncode,
                        'output': result.stdout + result.stderr})
        print(result.stdout + result.stderr, flush=True)
    sources = {}
    for folder in ['speaktrace', 'web', 'tests', 'scripts', 'api']:
        for path in (ROOT / folder).rglob('*'):
            if path.is_file() and path.suffix in {'.py', '.js', '.cjs', '.html', '.css'} and '__pycache__' not in path.parts:
                sources[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'python': sys.version,
              'status': 'passed' if all(item['exit_code'] == 0 for item in records) else 'failed',
              'checks': records, 'source_sha256': sources,
              'browser_evidence': 'docs/frontend-verification.md',
              'scope': 'Automated code checks; real audio inference and human listening validation are separate evidence.'}
    (ROOT / 'reports').mkdir(exist_ok=True)
    (ROOT / 'reports/verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
