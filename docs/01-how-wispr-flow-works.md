# How Wispr Flow Works (Research)

Wispr Flow is a system-wide voice-dictation app for macOS, Windows, iOS, and
Android. You hold/press a hotkey, speak naturally, and cleaned-up text appears
in whatever text field currently has focus — email, Slack, code editor, browser,
etc. The whole loop (keypress → text inserted) takes ~2–4 seconds.

The important thing for our clone: **it is not "just transcription."** The magic
is a transcription pass followed by an LLM editing pass that reshapes raw speech
into finished writing. That two-stage design is exactly what maps onto
**Whisper (speech→text) + Ollama (text→better text)** locally.

## The user-visible pipeline

```
[hotkey down] → [record mic] → [hotkey up]
      → [transcribe speech to raw text]
      → [LLM cleanup / formatting / command handling]
      → [inject final text at the cursor of the active app]
```

## Feature breakdown (what "base functionality" means)

| Feature | What it does | Where it lives in our clone |
|---|---|---|
| Global hotkey | Start/stop capture from any app | OS hotkey listener |
| Mic capture | Records audio while key held / toggled | Audio input library |
| Transcription | Speech → raw text, 100+ languages | **Whisper (local)** |
| AI auto-edit | Adds punctuation, removes "um/uh", fixes casing, splits sentences | **Ollama LLM** |
| Self-correction | "5pm, actually 6" → "6pm"; handles restarts/"scratch that" | **Ollama LLM** |
| Tone / context | Slack = casual, email = professional; knows the active app | **Ollama LLM** + active-app detection |
| Command mode | Voice instructions edit/format text ("make this a bullet list") | **Ollama LLM** (different prompt) |
| Text injection | Puts final text into the focused field system-wide | Clipboard-paste or keystroke simulation |
| Custom dictionary | Names/jargon spelled correctly | Prompt injection + Whisper `initial_prompt` |
| Whisper (quiet speech) | Recognizes whispered audio | Whisper handles natively |
| Overlay UI | Small floating indicator: idle / recording / thinking | Optional tray/overlay |

## What's actually novel vs. commodity

- **Commodity (easy to match locally):** transcription quality, punctuation,
  filler removal. Open Whisper models + a small LLM get you most of the way.
- **Harder to match:** end-to-end latency (their cloud runs streaming ASR on
  GPUs), and the polish of the editing model tuned specifically for dictation.
- **Their moat is cloud + a fine-tuned editing model**, not a secret algorithm.
  Wispr Flow itself is **cloud-only with no offline mode** — which is precisely
  the gap a local clone fills (privacy, no subscription, works offline).

## Key architectural insight (read this before planning)

**Ollama does not do speech-to-text.** Ollama serves *text* (and some vision)
LLMs. So "run it locally on Ollama" resolves to a **two-model** design:

1. **Whisper** (via `faster-whisper` or `whisper.cpp`) does the audio → text.
2. **Ollama** runs a small LLM (e.g. `llama3.2:3b`, `qwen2.5:3b`, `gemma2:2b`)
   that does the editing/formatting/command pass.

Everything else (hotkey, mic, text injection) is OS plumbing.

## Sources

- [Wispr Flow — official site](https://wisprflow.ai/) and
  [Features](https://wisprflow.ai/features)
- [Wispr Flow review (willowvoice)](https://willowvoice.com/blog/wispr-flow-review-voice-dictation)
- [Does Wispr Flow work offline? (cloud-only)](https://weesperneonflow.ai/en/blog/2026-02-09-wispr-flow-review-cloud-dictation-2026/)
- [What is Wispr Flow / WhisperAI backend](https://whisperai.com/blog/wispr-flow)
- [sebsto/wispr — on-device Whisper dictation for macOS (reference architecture)](https://github.com/sebsto/wispr)
- [whisper.cpp vs faster-whisper (2026 benchmarks)](https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026)
- [Turning Whisper into a real-time system (arXiv)](https://arxiv.org/pdf/2307.14743)
