"""Portable, escaped HTML report; never includes executable user content."""
from html import escape


def html_report(result: dict) -> str:
    def esc(value):
        return escape(str(value))
    score = result["summary"]["score"]
    score_text = "Withheld" if score is None else f"{score:.0f} / 100"
    dimensions = "".join(f'<tr><td>{esc(d["label"])}</td><td>{esc(d["score"] if d["score"] is not None else "Withheld")}</td><td>{esc(d["weight"])}</td></tr>' for d in result["summary"]["dimensions"])
    findings = "".join(f'<article><h3>{esc(f["title"])} <small>{f["start"]:.2f}–{f["end"]:.2f}s</small></h3><p>{esc(f["explanation"])}</p><p><strong>Practice:</strong> {esc(f["advice"])}</p><small>{esc(f["severity"])} · Alignment quality {f["confidence"]:.0%}</small></article>' for f in result["findings"])
    warnings = "".join(f'<li>{esc(w)}</li>' for w in result["warnings"])
    provenance = result.get("provenance", {})
    source = f'<p>Source: {esc(provenance.get("source_url", "User-provided recordings"))}<br>License: {esc(provenance.get("license", "User-owned input"))}<br>Artificially modified example: {esc(provenance.get("synthetic", False))}</p>'
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SpeakTrace comparison report</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;color:#172e40;max-width:900px;margin:48px auto;padding:0 28px}}h1{{font-size:42px;letter-spacing:-2px}}h2{{margin-top:32px}}small{{font-size:12px;color:#526575}}.score{{font-size:32px;color:#087d70}}article{{border-top:1px solid #d8e2e7;padding:12px 0}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:9px;border-bottom:1px solid #d8e2e7}}blockquote{{margin:0;padding:16px;background:#f2f6f8}}@media print{{body{{margin:12px;font-size:11pt}}article{{break-inside:avoid}}}}</style>
<p><strong>SpeakTrace</strong> · Local speech comparison</p><h1>{esc(result["title"])}</h1><p>{esc(result["created_at"])} · Report {esc(result["id"])}</p>
<p class="score">{score_text}</p><p>{esc(result["summary"]["caption"])}</p>
<h2>Rubric scores</h2><table><thead><tr><th>Dimension</th><th>Score / 100</th><th>Weight</th></tr></thead><tbody>{dimensions}</tbody></table>
<h2>Evidence</h2>{findings or '<p>No scored deviations were found, or scoring was withheld. Check the status above.</p>'}
<h2>Transcript</h2><blockquote>{esc(result["transcript"])}</blockquote>
<h2>Limitations and provenance</h2><ul>{warnings}</ul>{source}
<p>Scores compare measured delivery against this reference and rubric; they are not universal speaking-quality ratings. A different style may be appropriate. Energy is relative and can be affected by microphone placement. Synthetic evaluation does not establish performance on independent human recordings.</p>
<p><small>Model: {esc(result["compute"]["model"])} · revision {esc(result["compute"]["revision"])}<br>Rubric: {esc(result["rubric"]["version"])} · Alignment device: {esc(result["compute"]["device"])} · {esc(result["compute"].get("precision", "float32"))} · Processing {esc(result["compute"]["seconds"])} seconds · Cached alignment: {esc(result["compute"].get("cached_alignment", False))}. Acoustic features run on CPU. Use your browser's Print command to save this report as PDF.</small></p></html>'''
