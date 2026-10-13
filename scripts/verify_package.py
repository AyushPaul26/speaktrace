"""Verify delivered data, provenance, current results and safe source packaging."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify(root=ROOT, archive=None):
    import soundfile as sf
    root = Path(root).resolve()
    manifest = json.loads((root / 'data/manifest.json').read_text(encoding='utf-8'))
    groups = {}
    count = 0
    variants = 0
    for reference in manifest['references']:
        groups.setdefault(reference['source_group'], set()).add(reference['split'])
        if not reference['source_url'].startswith('https://') or not reference['license']:
            raise ValueError('Missing source provenance')
        for item in [reference, *reference['variants']]:
            path = (root / item['audio']).resolve()
            if not path.is_relative_to(root / 'data') or not path.is_file():
                raise ValueError(f'Invalid deliverable audio path: {item["audio"]}')
            if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError(f'Audio checksum mismatch: {item["audio"]}')
            info = sf.info(path)
            duration = info.frames / info.samplerate
            if info.samplerate != 16000 or info.channels != 1 or abs(duration - item['duration']) > 0.001:
                raise ValueError(f'Unexpected audio format/duration: {item["audio"]}')
            for label in item.get('labels', []):
                if not 0 <= label['start'] < label['end'] <= duration + 0.001:
                    raise ValueError('Label outside its actual waveform')
            if item.get('flaw') == 'clean' and path.read_bytes() != (root / reference['audio']).read_bytes():
                raise ValueError('Control differs from reference')
            count += 1
        variants += len(reference['variants'])
    if any(len(splits) != 1 for splits in groups.values()):
        raise ValueError('Source family leaks across splits')
    evaluation = json.loads((root / 'reports/evaluation.json').read_text(encoding='utf-8'))
    if evaluation['manifest_sha256'] != hashlib.sha256((root / 'data/manifest.json').read_bytes()).hexdigest():
        raise ValueError('Evaluation belongs to a different dataset manifest')
    for key, filename in [('alignment_code_sha256', 'speaktrace/alignment.py'),
                          ('comparison_code_sha256', 'speaktrace/core/comparison.py'),
                          ('alignment_policy_code_sha256', 'speaktrace/pipeline.py')]:
        if evaluation.get(key) != hashlib.sha256((root / filename).read_bytes()).hexdigest():
            raise ValueError(f'Evaluation is stale for {filename}; rerun the benchmark')
    required = ['README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'start.bat', 'setup.bat',
                'docs/TECHNICAL_REPORT.md', 'docs/DEVPOST.md', 'docs/DEMO_SCRIPT.md',
                'docs/DATASET_CARD.md', 'docs/HUMAN_VALIDATION.md',
                'output/pdf/SpeakTrace-technical-report.pdf', 'reports/verification.json']
    if any(not (root / name).is_file() for name in required):
        raise ValueError('Missing deliverables: ' + ', '.join(name for name in required if not (root / name).is_file()))
    archive_files = None
    if archive:
        with zipfile.ZipFile(archive) as source:
            names = source.namelist()
            forbidden = {'.venv', '.runtime', '.cache', '.models', 'raw', '__pycache__', 'runtime', '.git'}
            if any(forbidden.intersection(Path(name).parts) or Path(name).is_absolute() or '..' in Path(name).parts for name in names):
                raise ValueError('Archive contains private/runtime or unsafe paths')
            for name in required:
                if 'SpeakTrace/' + name not in names:
                    raise ValueError(f'Missing archive deliverable: {name}')
            if source.testzip():
                raise ValueError('Archive CRC failed')
            archive_files = len(names)
    return {'status': 'passed', 'references': len(manifest['references']), 'variants': variants,
            'verified_audio_files': count, 'source_groups': len(groups), 'archive_files': archive_files}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    arguments = parser.parse_args()
    print(json.dumps(verify(archive=arguments.archive), indent=2))
