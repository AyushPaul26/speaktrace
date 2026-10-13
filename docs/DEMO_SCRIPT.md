# SpeakTrace demo - approximately five minutes

Record the actual local app with your voice. Keep the project folder and terminal available. Choose generated examples by their visible names and call them generated; do not present them as mistakes made by the archive speaker. This is a recording script, not a claim that a video has been recorded or uploaded.

## Before recording

1. Run `start.bat` and open http://127.0.0.1:8765. Close unrelated tabs and private notifications.
2. Test the chosen clean, pause and energy examples on the final version. Let the output determine the narrative. Use the real compute time and backend shown in the app; a cached run must not be described as fresh inference.
3. Keep `docs/TECHNICAL_REPORT.md` and `reports/evaluation.json` available for the results segment. The complete benchmark includes misses.
4. Use Windows' screen recording capability or another free recorder. Check that both system sound and microphone narration are captured, without echo. Export a readable landscape video between 3 and 10 minutes.

## 0:00-0:35 - The problem
"A speaking score is only useful if I can understand and hear why I received it. SpeakTrace compares a reference recording with a reading of the same words and connects measured differences to playable evidence. It is a local prototype, free to run, with no training or paid API."

Show the studio, local address and ready-model status. Explain that the objective is comparison against a selected reference, not a universal rating of confidence, emotion or speaking ability.

## 0:35-1:10 - A control
Open a public-domain example and analyze its original clean control. Explain that this compares identical source samples, so it tests whether the pipeline invents differences. Show the real outcome. This does not establish accuracy on a second person's voice.

## 1:10-2:10 - A visible and audible intervention
Choose a generated severe pause example that the final run detects. Run analysis. Select its evidence interval, play the participant segment, then the corresponding reference segment. Show the measured durations, exact location and textual explanation. Point out that each track has its own time axis, because inserted pauses change total duration.

If a region is skipped, show the coverage and warning. Explain why the app avoids a confident judgment when alignment is uncertain.

## 2:10-2:50 - Energy and word navigation
Choose a generated energy variant. Show an actual detected interval, relative-energy measurement and selected words. Click an unflagged word and show both tracks seeking to their respective times. Note that microphone movement can also affect energy and that recording-wide gain is normalized.

## 2:50-3:30 - Real user flow
Switch to Your recordings. Show the two audio inputs and the shared transcript. Upload a pair you are permitted to use. An archive pair is acceptable for demonstrating this flow, but explicitly describe its origin. Run the real job and show loading/error handling or completed results. Change rubric weights and rerun. Download JSON and open the printable report.

## 3:30-4:25 - Method and honest evaluation
Open How it works and the technical report. Explain wav2vec2 emissions, CTC word alignment, confidence gates and deterministic acoustic measurements. Show the final event precision/recall, localization results, clean controls and per-type misses directly from the report. State that original baseline results were inspected before the development rerun. Explain the synthetic pacing artifact and lack of independent human validation.

## 4:25-5:00 - Reproduction and next step
Show the repository structure, source provenance, manifest labels, setup/start scripts and verification record. State AI assistance. Close with the next research step: consenting participants, independent time annotations and a genuinely unopened validation group.

## After recording
Listen to the entire exported video and check text legibility, audio and duration. Upload to YouTube with visibility accepted by the organizer; test the link in a signed-out browser. Add the real link to Devpost. Publishing and submission require the entrant's accounts and have not been performed by this local build.
