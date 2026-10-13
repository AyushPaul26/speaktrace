"""Dependency-free frontend contract, markup and token drift checks."""
from pathlib import Path
from html.parser import HTMLParser
import argparse
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def token_css():
    text = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
    front = text.split("---", 2)[1]
    lines = ["/* Generated from DESIGN.md by web/check_ui.py --write-tokens. Do not edit. */", ":root {"]
    group = ""
    font = ""
    for line in front.splitlines():
        heading = re.fullmatch(r"([a-z]+):", line)
        if heading:
            group = heading.group(1)
            continue
        if group in {"colors", "rounded", "spacing"}:
            match = re.fullmatch(r'  ([\w-]+): "([^"]+)"', line)
            if match:
                prefix = {"colors": "color", "rounded": "radius", "spacing": "space"}[group]
                lines.append(f"  --{prefix}-{match.group(1)}: {match.group(2)};")
        if group == "typography":
            match = re.fullmatch(r"  ([\w-]+):", line)
            if match:
                font = match.group(1)
            match = re.fullmatch(r'    fontFamily: "([^"]+)"', line)
            if match:
                lines.append(f"  --font-{font}: {match.group(1)};")
    lines.append("}")
    return "\n".join(lines) + "\n"


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.labels = []
        self.described = []
        self.errors = []

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if "id" in attrs:
            if attrs["id"] in self.ids:
                self.errors.append(f"Duplicate id: {attrs['id']}")
            self.ids.add(attrs["id"])
        if tag == "label" and "for" in attrs:
            self.labels.append(attrs["for"])
        if "aria-describedby" in attrs:
            self.described.extend(attrs["aria-describedby"].split())
        if tag == "form" and "novalidate" not in attrs:
            self.errors.append("Form missing novalidate")
        if tag == "button" and attrs.get("type") != "button":
            self.errors.append("Static action button has no explicit type")
        if tag == "script" and attrs.get("src", "").startswith("http"):
            self.errors.append("Remote script dependency")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-tokens", action="store_true")
    args = parser.parse_args()
    expected = token_css()
    token_path = ROOT / "web/tokens.css"
    if args.write_tokens:
        token_path.write_text(expected, encoding="utf-8")
    errors = []
    if not token_path.exists() or token_path.read_text(encoding="utf-8") != expected:
        errors.append("Token drift: run python web/check_ui.py --write-tokens")
    markup = Markup()
    markup.feed((ROOT / "web/index.html").read_text(encoding="utf-8"))
    errors.extend(markup.errors)
    errors.extend(f"Missing label/description target: {target}" for target in markup.labels + markup.described if target not in markup.ids)
    css = (ROOT / "web/styles.css").read_text(encoding="utf-8")
    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    for pattern, name in [(r"\.innerHTML\s*=", "Unsafe HTML assignment"), (r"\b(?:alert|confirm|prompt)\s*\(", "Native product dialog"), (r"localStorage\.", "Persistent browser storage")]:
        if re.search(pattern, js):
            errors.append(name)
    for requirement in ["scrollbar-color:", "::-webkit-scrollbar", "prefers-reduced-motion", "forced-colors", "resize: none", ":focus-visible", "max-width: 760px"]:
        if requirement not in css:
            errors.append(f"Missing required style: {requirement}")
    declared = set(re.findall(r"(--[\w-]+):", expected))
    used = set(re.findall(r"var\((--[\w-]+)\)", css))
    errors.extend(f"Undefined token: {token}" for token in used - declared)
    for path in ["/api/demos", "/api/analyze", "/api/jobs/", "/api/results/", "AbortController", "generation !== state.generation"]:
        if path not in js:
            errors.append(f"Missing API/async invariant: {path}")
    result = {"check": "frontend-static-contract", "passed": not errors, "errors": errors, "tokens": len(declared), "static_ids": len(markup.ids), "scope": "Static markup, token drift, accessibility structure and async invariants; browser behavior requires separate QA."}
    print(json.dumps(result, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
