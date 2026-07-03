# flow — a local, offline Wispr Flow clone

Press a hotkey anywhere, speak, and get clean, formatted text pasted at your
cursor — running **fully on your machine** with no cloud and no subscription.

- **Speech → text:** [Whisper](https://github.com/openai/whisper) locally via
  [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper).
- **Text → *better* text:** a small LLM on [Ollama](https://ollama.com)
  (adds punctuation, strips filler, resolves self-corrections, matches tone).

> **Why two models?** Ollama serves *language* models — it does not do
> speech-to-text. So the local design is **Whisper (STT) + Ollama (editing)**.
> This mirrors how Wispr Flow itself works: transcribe, then AI-edit. Wispr Flow
> is cloud-only; this clone's whole point is to do it offline and private.

## Docs

- [`docs/01-how-wispr-flow-works.md`](docs/01-how-wispr-flow-works.md) — research:
  how Wispr Flow works and what "base functionality" means, feature by feature.
- [`docs/02-architecture-and-roadmap.md`](docs/02-architecture-and-roadmap.md) —
  the plan: architecture, tech stack, the two key prompts, cross-platform
  injection notes, and a phased roadmap.

## Quickstart (MVP)

```bash
# 1. Install Ollama (https://ollama.com) and pull a small, fast model
ollama pull llama3.2:3b

# 2. Python deps
pip install -r requirements.txt

# 3. Run
python src/flow.py
```

Then press **Ctrl+Alt** once to start recording, again to stop. The cleaned text
is pasted into whatever field has focus.

- **macOS:** grant your terminal/app **Accessibility** + **Microphone** permissions.
- **Linux (Wayland):** synthetic paste is blocked; use `ydotool`/`wtype` (see docs).
- Set `USE_OLLAMA = False` in `src/flow.py` to see the raw Whisper output alone.

## Status

Phase 1–2 MVP (hotkey → transcribe → LLM clean-up → paste). Roadmap for
push-to-talk, status overlay, context-aware tone, custom dictionary, and Command
Mode is in [`docs/02-architecture-and-roadmap.md`](docs/02-architecture-and-roadmap.md).

## Note

This reimplements *behavior* from public information using open-source components.
It contains no Wispr Flow code, models, or assets, and is not affiliated with Wispr.
