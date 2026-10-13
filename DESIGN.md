---
version: alpha
name: SpeakTrace
description: A local speech analysis studio that makes audible differences inspectable.
colors:
  background: "#eef3f5"
  surface: "#ffffff"
  ink: "#152f43"
  muted: "#587082"
  primary: "#08766f"
  primary-hover: "#06665f"
  primary-soft: "#e2f3ef"
  border: "#d6e1e6"
  pacing: "#346cb4"
  pauses: "#a26714"
  energy: "#8160a8"
  danger: "#b53c36"
  danger-soft: "#fff0ee"
  warning-soft: "#fff5df"
  scrollbar-thumb: "#a5b8c4"
  scrollbar-track: "#eef3f5"
  scrollbar-hover: "#718e9f"
  scrollbar-active: "#587082"
typography:
  display:
    fontFamily: "Bahnschrift, Arial Narrow, sans-serif"
  body:
    fontFamily: "Segoe UI, Helvetica Neue, Arial, sans-serif"
  mono:
    fontFamily: "Cascadia Code, Consolas, monospace"
rounded:
  control: "0.5rem"
  panel: "0.875rem"
  pill: "999px"
spacing:
  unit: "0.25rem"
  panel: "1.5rem"
  section: "2rem"
components:
  button:
    minHeight: "2.75rem"
  panel:
    borderWidth: "1px"
  waveform:
    height: "7rem"
---

# SpeakTrace design system

## Overview

SpeakTrace is an instrument bench for people rehearsing an English reading and judges inspecting a hackathon prototype. Its single job is to connect differences in delivery to actual audio evidence. The North Star is the precision of an audio editor with the legibility of a research notebook. This is a product/tool register; there is no marketing landing page.

The memorable signature is a large pair of measured waveforms with independent elapsed-time axes, selected evidence bands, and synchronized word selection. One broad workspace gives that evidence priority over a score. A quiet example library and a compact inspector flank it. Avoid decorative fake signals, gamified score dashboards, ornamental gradients, and dark recording-console imitation.

English (en-US formatting) is the initial interface and transcript language per docs/API.md and the approved specification. No Japan-market scope is asserted. The usage scene is a laptop demonstration with a keyboard and headphones; the same workflow must work on a narrow phone.

Token ownership is **Model A**: the frontmatter above generates `web/tokens.css` through `web/check_ui.py --write-tokens`. The checker verifies exact byte-level drift without installing packages. Colors map to `--color-{key}`, font families to `--font-{key}`, rounded values to `--radius-{key}`, spacing to `--space-{key}`. `web/styles.css` and SVG CSS consume those variables directly. No framework adapter exists. The official designmd lint is optional tooling and must not introduce an npm dependency into this buildless project.

## Colors

Cool pale background and white evidence surfaces support navy text. Teal means a selected recording, primary action, or a measured waveform. Blue, amber, and violet distinguish pacing, pauses, and energy; type labels always accompany their color. Danger denotes failed input or unavailable analysis. Muted text still meets normal-text contrast on its background. The app has one light theme. Forced colors defer to platform colors and retain borders and text labels.

## Typography

Bahnschrift carries short headings and the wordmark, with an Arial Narrow fallback. Segoe UI carries readable body copy at 14–16px and a 1.5 line height. Cascadia Code/Consolas carries elapsed seconds and measured values. There are no remote font requests or font swaps. Headings are sentence case; numeric metrics use tabular figures. The transcript uses generous line-height and an 18px baseline so selections remain distinct.

## Layout

The desktop shell has a 220px library and a fluid workspace. Inside the workspace, the audio column flexes while the 292px inspector remains readable. Below 1180px the inspector becomes a two-column row; below 760px the library moves into normal flow and all content is one column. The document owns vertical scrolling. No shared viewport-height locks or clipped long forms. A four-pixel rhythm supports small evidence labels and 24px panel spacing. Player tracks reserve 112px before data arrives; help/error areas and the analysis button keep stable footprints.

## Elevation & Depth

Hierarchy comes from surface color and fine borders. Only the modal receives a broad shadow. No floating card stacks or decorative blur. The top bar stays in document flow to avoid obscuring focus.

## Shapes

Controls use an 8px radius, panels 14px, category tags a pill. Waveforms stay unboxed within their audio tracks. Line icons have a consistent 1.7px stroke. Corner treatment should feel like a useful instrument, never an ornamental frame.

## Components

Shared button classes define primary, neutral and ghost emphasis; 44px targets keep labels stable while busy. Hover changes tone, focus has a visible teal outline, active depresses slightly, and native disabled semantics stop events. Native file inputs, radio groups and range sliders own their keyboard behavior. No authored select popup is required.

`renderTrack` owns both recording players, charts and seek controls. `renderFindings` owns a list of native buttons. `selectFinding` owns chart bands, transcript highlights and the inspector. `setNotice` owns persistent scope-specific feedback. The methodology uses native dialog focus containment, Escape and restoration. File errors sit alongside their field. Empty results tell the user to analyze a comparison; unsafe alignment explicitly withholds scores.

Evidence replay adds 0.25 seconds of listening context on each side, clipped to each recording's duration. The shared `playbackInterval` helper owns that margin. Buttons explicitly say “context” and show the expanded playback range on a separate line so the narrow inspector remains legible. Finding bands, measurements, confidence ranges and exported evidence keep the exact original bounds, including a genuine zero-length reference quiet gap.

`web/diagnostics.js` owns word-indexed acoustic contours below the paired elapsed-time tracks. Energy, Pitch and Spectrum use shared toggle buttons. A solid teal reference and dashed navy participant encode recording identity without relying on color alone. Each point is the median of actual feature frames within the corresponding aligned word; unvoiced, missing or weakly aligned values leave gaps. The x-axis is explicitly transcript word index, never a rescaled shared recording clock. A bounded, expandable native table exposes exact values and keyboard-accessible word seeking. Spectral centroid is labelled a diagnostic rather than a vocal-clarity score.

Device badges report the actual backend returned by the local service. “GPU” is used only for CUDA metadata, “CPU” for CPU, and “GPU + CPU” for mixed recording alignment backends. Result timing is labelled total time and includes cache provenance when present; it is not presented as a hardware benchmark. Health describes the current runtime while each report preserves the backends that generated its alignments. Optional assessed-word counts and coverage accompany the score; long coverage captions wrap naturally in the inspector.

Motion is limited to 150ms control feedback and a progress spinner; reduced motion removes transforms and spinner rotation. The words “Analyze comparison,” “Reference,” “Participant,” and “Evidence” stay consistent. Staged progress is never represented as an ETA. Text explains relative energy, generation labels and rubric limitations. Every chart has an accessible description and exact text alternative. Waveforms provide native seek sliders; word-indexed contours provide a keyboard-operable values table.

## Do's and Don'ts

- Do show actual elapsed time on each recording's own axis.
- Do give each measured finding a playable interval and readable evidence.
- Do keep source provenance distinct from model conclusions.
- Don't draw fabricated waveforms, scores, or word times while loading.
- Don't use the rubric as a claim about universal speaking ability, emotion, or diagnosis.
- Don't place recordings or transcripts in persistent browser storage.
