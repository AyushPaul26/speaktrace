"""Render a six-page technical report and matching Markdown from actual results.

Optional document dependencies: pip install -r requirements-report.txt
"""
from pathlib import Path
from datetime import datetime, timezone
from html import escape
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from pypdf import PdfReader

    report = json.loads((ROOT / 'reports/evaluation.json').read_text(encoding='utf-8'))
    verification = json.loads((ROOT / 'reports/verification.json').read_text(encoding='utf-8'))
    hardware = json.loads((ROOT / 'reports/device-benchmark.json').read_text(encoding='utf-8'))
    rubric = report['rubric']
    test = report['splits']['test']['overall']
    dev = report['splits']['dev']['overall']
    def number(value, digits=3):
        return 'N/A' if value is None else f'{value:.{digits}f}'
    def metric_rows():
        rows = [['Split / type', 'TP / FP / FN', 'Precision', 'Recall', 'F1']]
        for label, entry in [('Dev overall', dev), ('Test overall', test), *[(f'Test {key}', value) for key, value in report['splits']['test']['by_flaw'].items()]]:
            rows.append([label, f'{entry["tp"]} / {entry["fp"]} / {entry["fn"]}', number(entry['event_precision']), number(entry['event_recall']), number(entry['event_f1'])])
        return rows

    pages = [
        ('SpeakTrace', 'Track C: Contrastive Speech Analytics & Temporal Flaw Grounding', [
            ('p', 'A local speech comparison studio that connects a reference-relative score to words, acoustic measurements and audible intervals. This report describes an engineering prototype and its measured limitations; no independent human-performance validation is claimed.'),
            ('h', 'Problem and contribution'),
            ('p', 'A single score hides the delivery decisions behind it. SpeakTrace accepts two recordings of the same English text, aligns their words independently, detects selected local deviations and explains the measured difference. A reviewer can seek both recordings to the corresponding words, replay evidence and inspect the scoring rule. A reference is a selected comparison target, not an objective ideal for every speaker or rhetorical context.'),
            ('h', 'System architecture'),
            ('table', [['Layer', 'Implementation and responsibility'], ['Interface', 'Buildless HTML/CSS/JavaScript; waveforms, word navigation, contours and exports.'], ['Local service', 'FastAPI; validated uploads; serial bounded job queue; local result retention.'], ['Alignment', 'Pinned wav2vec2 emissions followed by blank-interleaved CTC Viterbi alignment.'], ['Measurement', 'NumPy/SciPy timing, relative energy, pitch and spectral diagnostics.'], ['Assessment', 'Versioned deterministic rules, configurable weights and reliability gates.']]),
            ('h', 'Deployment and scope'),
            ('p', 'No model training, paid account, cloud API, remote font or runtime CDN is needed. A one-time setup downloads open dependencies and the approximately 378 MB model. CPU inference is supported; optional NVIDIA inference remains local and falls back to CPU on CUDA out-of-memory. The interface reports the actual backend and cache use.'),
            ('p', f'Hardware check: RTX 3050 A (4 GB), float32. Three warm uncached alignments of one 22-second clip had median CPU {hardware["devices"]["cpu"]["warm_median_seconds"]:.3f} s and GPU {hardware["devices"]["cuda"]["warm_median_seconds"]:.3f} s; matched word boundaries agreed. A 60-second inference stress test used {hardware["devices"]["cuda"]["maximum_length_memory_check"]["peak_allocated_mib"]:.0f} MiB peak allocated GPU memory. This is not an end-to-end speed claim.'),
            ('p', 'Inputs: single-speaker English readings, the same supplied transcript, 2-60 seconds and at most 20 MB per recording. Audio is resampled to mono 16 kHz and canonical PCM16; measurements use the exact playback samples. Any protective uniform gain is recorded. The transcript limit is 150 words / 1600 characters; numerals must be written as spoken words.'),
        ]),
        ('01 / Data engineering', 'Real archive speech, controlled edits, explicit provenance', [
            ('p', 'The included dataset contains four reference excerpts, four identical clean controls and 36 generated variants. All 44 delivered audio files are mono 16 kHz PCM-16 WAV. Original source recordings are public-domain US federal-government works with item-level evidence; the project claims no endorsement.'),
            ('table', [['Excerpt', 'Duration', 'Source / split'], ['A university welcome', '22.014 s', 'Kennedy 1963 / development'], ['Learning and public service', '27.549 s', 'Kennedy 1963 / development'], ['A moment of remembrance', '23.950 s', 'Reagan 1986 / test'], ['Speaking to the families', '22.012 s', 'Reagan 1986 / test']]),
            ('p', 'Official transcript slices were checked against the model decode and aligned to contiguous audio. Automatic consistency checks are not human verification of every word boundary. The generator stores its alignment estimates separately from inference. File checksums, exact source offsets, rights evidence, transcripts and transformations are in the manifest and provenance files.'),
            ('h', 'The contrastive spectrum'),
            ('table', [['Intervention', 'Mild / moderate / severe', 'Ground truth'], ['Energy', '-5 / -9 / -14 dB', 'Exact gain-operation interval; 10 ms ramps'], ['Pause', '+0.65 / +1.10 / +1.80 s', 'Complete changed inter-word gap'], ['Pacing', '1.35 / 1.65 / 2.00 times', 'Compressed interval in participant time']]),
            ('p', 'The edit position is fixed at one third of the transcript before evaluation. Energy edits span six words and pacing edits ten. Rate changes shift subsequent audio. Clean controls retain the same PCM serialization path. These labels describe waveform operations, not independent perceptual judgments.'),
            ('h', 'Independence and a discovered limitation'),
            ('p', 'All descendants of each complete source recording stay in one split: Kennedy development, Reagan test. No operation labels or severity metadata enter scoring. Development diagnostics showed that the original librosa phase-vocoder pacing edit also reduces local RMS and damages recognizability. The original benchmark is retained and this confound is disclosed; it cannot establish clean sensitivity to natural rushing.'),
        ]),
        ('02 / Method and rubric', 'Alignment quality limits what can be assessed', [
            ('h', 'Actual alignment'),
            ('p', 'facebook/wav2vec2-base-960h produces acoustic token log probabilities. Dynamic programming selects a monotonic CTC path through interleaved character and blank states, including repeated-token constraints. Character spans are aggregated into words at approximately 20 ms acoustic resolution. Timestamps are inferred from the actual waveform, never evenly spaced or copied from the generator labels.'),
            ('p', 'The model is pinned to revision 22aad52d435eb6dbaf354bdad9b0da84ce7d6156. Inference uses evaluation mode and local files. Greedy decoding is compared independently with the supplied transcript using normalized word edit distance. Agreement below 45% withholds all scores; below 75% adds a warning. CTC probabilities are heuristic quality indicators, not calibrated assessment probabilities.'),
            ('h', 'Acoustic measurements'),
            ('p', 'Frame diagnostics use 40 ms windows and 20 ms hops: RMS energy, an autocorrelation pitch estimate, FFT spectral centroid and 13 MFCC summary coefficients. Pitch is expressed relative to the recording median in semitones; relative energy removes a recording-wide baseline. These normalizations do not establish speaker fairness. Pitch, MFCC and spectrum are explanatory diagnostics and do not directly award quality points.'),
            ('table', [['Dimension', 'Measured deviation and fixed rule'], ['Pacing', 'Sum aligned word durations within reliable phrases; ratio at least 1.25 and at least 0.25 s saved. Pauses are excluded.'], ['Pauses', 'Same transcript boundary; at least 0.30 s extra, 0.35 s total and 1.8 times the reference gap (0.12 s floor).'], ['Energy', 'Local word-RMS relative to each reliable-word median; decrease at least 5 dB.']]),
            ('p', f'Rubric version: {rubric["version"]}. Word quality must be at least 0.35; phrase mean quality at least 0.55. Global gates require sufficient reliable speech and assessed coverage. Skipped phrases are reported with assessed-word counts. A short uncertain run may still contain a measurable pause: reliable surrounding anchors and independently measured quiet audio corroborate that finding.'),
            ('p', 'Each dimension starts at 100 and subtracts capped, severity-weighted local penalties. Pacing severity is based on excess rate / 1.2; energy on dB drop / 18; pause on extra seconds / 1.5. Default weights are 40% pacing, 35% pauses and 25% energy, normalized when edited. The exact penalty aggregation and thresholds are exported with each result and in the source; the score measures this rubric only.'),
        ]),
        ('03 / Evaluation', 'All examples counted; synthetic results are not a human study', [
            ('p', f'This final run used {report["fresh_alignment_calls"]} fresh alignments and {report["alignment_cache_hits"]} cache hits, taking {report["elapsed_seconds"]:.1f} seconds. Recorded backend: {report["device"]}. The original 1.0.0 results were inspected before later development fixes. Consequently this is a source-disjoint development rerun, not a newly unopened external validation set.'),
            ('p', 'Predicted intervals match ground truth one-to-one by flaw type at interval intersection-over-union (IoU) of at least 0.30. Matching maximizes match count, then total overlap. Duplicate and wrong-type detections are false positives. Withheld/failed examples retain their missed labels. Boundary statistics include matched events only; event recall separately exposes the misses.'),
            ('table', metric_rows()),
            ('table', [['Test-group measure', 'Observed result'], ['Matched mean IoU', number(test['matched_mean_iou'])], ['Matched start/end boundary MAE', number(test['matched_boundary_mae_seconds']) + ' s'], ['Clean controls with any flags', f'{test["clean_controls_with_flags"]} / {test["clean_controls"]}'], ['Withheld or failed examples', str(test['withheld_or_failed'])], ['Severity ordering: strictly decreasing', f'{report["splits"]["test"]["severity_ordering"]["strictly_decreasing_count"]} / {report["splits"]["test"]["severity_ordering"]["triples"]} triples']]),
            ('h', 'Interpretation'),
            ('p', 'The per-type table is more informative than a single headline score. Weak local alignment can legitimately suppress a detector and reduce recall. A high score on assessed phrases does not prove that skipped speech matches the reference. Pacing edits in this archive set are confounded by phase-vocoder artifacts; zero or low pacing recall must be shown, not hidden behind clean-control accuracy.'),
            ('p', 'There is only one test source group and two test excerpts. Clean controls are identical-waveform checks, not independent acceptable readings. Localization quality on matched events does not compensate for missed events. No population-level confidence interval, cross-accent accuracy, clinical use or demonstrated improvement in speaking is claimed.'),
        ]),
        ('04 / Interface and reproduction', 'From audio upload to inspectable evidence', [
            ('p', 'The studio provides reference and participant waveforms on their own time axes. Word selection seeks both recordings to their corresponding measured timestamps. Finding cards expose intervals, numerical measurements and suggested practice. The acoustic contour view compares per-word feature medians on a shared transcript-word axis; unvoiced or weakly aligned values leave gaps. This avoids falsely equating different elapsed-time positions.'),
            ('p', 'Keyboard-accessible controls support demo selection, uploads, playback, rubric sliders, progress resume and exports. Reports contain the score, evidence, transcript, provenance, limitations, model revision and rubric version. DOM text creation and escaped report generation keep uploaded text from executing as markup.'),
            ('h', 'Reproduce'),
            ('table', [['Action', 'Project-root command'], ['CPU setup', 'py -3.12 scripts/setup.py'], ['Optional GPU setup', 'py -3.12 scripts/setup.py --gpu'], ['Start', 'start.bat (open http://127.0.0.1:8765)'], ['Rebuild included variants offline', '.venv/Scripts/python.exe scripts/build_dataset.py --variants-only'], ['Fresh benchmark', '.venv/Scripts/python.exe scripts/evaluate.py'], ['Code verification', '.venv/Scripts/python.exe scripts/verify.py'], ['Source package audit', '.venv/Scripts/python.exe scripts/verify_package.py']]),
            ('p', f'Latest automated verification status: {verification["status"]}. Exact command outputs, exit codes and checked source hashes are retained in reports/verification.json. Browser evidence records actual upload, playback, word seeking, JSON/HTML export, desktop/narrow layout, keyboard behavior and stale-response handling. A screen-reader session and independent human study are not claimed.'),
            ('h', 'Local privacy and resource limits'),
            ('p', 'The launcher binds only to 127.0.0.1. Requests have body/file/duration limits and same-origin write checks; the queue processes one model job at a time. Upload-derived alignments do not enter the persistent public-demo cache. Jobs, media and reports expire after 24 hours, with physical cleanup on startup, access or new analysis. Stopping the app stops cleanup. Runtime folders and recordings are excluded from the source archive.'),
        ]),
        ('05 / Limits, next steps and references', 'A reviewable prototype with a defined validation gap', [
            ('p', 'Prepared historical public addresses differ from natural laptop recordings. The dataset contains two adult male American-English speakers, a narrow content domain and old broadcast conditions. It does not demonstrate robustness across accents, genders, ages, microphone placements, speech differences, noise or spontaneous speech. A solemn or expressive pause may be appropriate. Energy differences may reflect equipment, not effort. Template advice is a practice suggestion, not a causal diagnosis of the speaker.'),
            ('h', 'Next validation step'),
            ('p', 'Collect neutral short readings from consenting participants and separate permission to publish their voices. Include acceptable readings and deliberately changed takes, with uncontrolled natural variation. Have two listeners independently annotate type, interval and uncertainty while blinded to the detector. Freeze the rubric before opening a new speaker/source-disjoint group. Report agreement, all failures, per-group errors and human results separately from controlled synthetic edits.'),
            ('h', 'Sources and reproducibility references'),
            ('p', '1. JFK Presidential Library, sound item JFKWHA-190-002, American University address (1963), item-level public-domain notice: https://www.jfklibrary.org/asset-viewer/archives/jfkwha-190-002'),
            ('p', '2. Reagan Presidential Library, Challenger address transcript (1986): https://www.reaganlibrary.gov/archives/speech/address-nation-explosion-space-shuttle-challenger'),
            ('p', '3. National Archives / DocsTeach, item 6014714 and rights evidence: https://docsteach.org/document/reagan-challenger/ . The downloaded Commons derivative and full provenance are recorded in data/sources.json.'),
            ('p', '4. Meta wav2vec2-base-960h model card and Apache-2.0 model: https://huggingface.co/facebook/wav2vec2-base-960h . PyTorch installation variants: https://docs.pytorch.org/get-started/previous-versions/'),
            ('p', '5. Supplied organizer documents: Track C and Multimodal AI Hackathon 2026 - Submission Guidelines. This report stays within the six-page limit. Public repository, YouTube video and real team details are separate submission steps.'),
            ('h', 'Disclosure and availability'),
            ('p', 'Original SpeakTrace code is MIT licensed. Source archives retain their documented rights; dependencies and model notices are in THIRD_PARTY_NOTICES.md. OpenAI Codex/ChatGPT assisted with research, design, implementation, tests and documentation. Entrants must review and understand the work and disclose assistance. The local build includes source, labeled short audio, reports, setup instructions and demo narration guidance; it does not claim that a repository or video has been published.'),
        ]),
    ]
    out = ROOT / 'output/pdf/SpeakTrace-technical-report.pdf'
    out.parent.mkdir(parents=True, exist_ok=True)
    ink, teal, grey = colors.HexColor('#152f43'), colors.HexColor('#08766f'), colors.HexColor('#587082')
    styles = {
        'title': ParagraphStyle('Title', fontName='Helvetica-Bold', fontSize=24, leading=28, textColor=ink, spaceAfter=8),
        'subtitle': ParagraphStyle('Subtitle', fontName='Helvetica', fontSize=11, leading=15, textColor=teal, spaceAfter=18),
        'p': ParagraphStyle('Body', fontName='Helvetica', fontSize=9.4, leading=13.4, textColor=ink, spaceAfter=10, splitLongWords=True),
        'h': ParagraphStyle('Heading', fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=ink, spaceBefore=8, spaceAfter=7),
        'cell': ParagraphStyle('Cell', fontName='Helvetica', fontSize=8.5, leading=11.5, textColor=ink, splitLongWords=True),
    }
    story, markdown = [], []
    for page_index, (title, subtitle, blocks) in enumerate(pages):
        if page_index: story.append(PageBreak())
        story.extend([Paragraph(escape(title), styles['title']), Paragraph(escape(subtitle), styles['subtitle'])])
        markdown.extend([f'# {title}', '', subtitle, ''])
        for kind, value in blocks:
            if kind != 'table':
                story.append(Paragraph(escape(value), styles[kind])); markdown.extend([('## ' if kind == 'h' else '') + value, ''])
            else:
                width = 491
                widths = [width / len(value[0])] * len(value[0])
                if len(widths) == 2: widths = [147, 344]
                elif len(widths) == 3: widths = [145, 148, 198]
                table = Table([[Paragraph(escape(str(cell)), styles['cell']) for cell in row] for row in value], colWidths=widths, repeatRows=1, hAlign='LEFT')
                table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e2f3ef')), ('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 7), ('TOPPADDING', (0,0), (-1,-1), 7), ('LINEBELOW', (0,0), (-1,-1), .4, colors.HexColor('#d6e1e6'))]))
                story.extend([table, Spacer(1, 12)])
                markdown.append('| ' + ' | '.join(value[0]) + ' |'); markdown.append('|' + '|'.join(['---'] * len(value[0])) + '|')
                markdown.extend('| ' + ' | '.join(map(str, row)) + ' |' for row in value[1:]); markdown.append('')
    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor('#d6e1e6')); canvas.line(52, 45, 543, 45)
        canvas.setFont('Helvetica', 8); canvas.setFillColor(grey)
        canvas.drawString(52, 31, 'SpeakTrace | Technical report | 13 October 2026')
        canvas.drawRightString(543, 31, f'{doc.page} / 6')
    doc = SimpleDocTemplate(str(out), pagesize=A4, rightMargin=52, leftMargin=52, topMargin=43, bottomMargin=58, title='SpeakTrace - Technical report', author='SpeakTrace project')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    count = len(PdfReader(out).pages)
    if count != 6:
        raise ValueError(f'Report must have exactly six reviewed pages, got {count}')
    (ROOT / 'docs/TECHNICAL_REPORT.md').write_text('\n'.join(markdown), encoding='utf-8')
    print(json.dumps({'pdf': str(out), 'pages': count, 'generated_at': datetime.now(timezone.utc).isoformat()}))


if __name__ == '__main__':
    main()
