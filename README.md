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

## Quickstart

```bash
# 1. Install Ollama (https://ollama.com) and pull a small, fast model
ollama pull llama3.2:3b

# 2. Python deps
pip install -r requirements.txt

# 3. Smoke-test the pipeline without touching your mic or hotkeys
python src/flow.py --once            # record one utterance, Enter to stop, prints result

# 4. Run for real
python src/flow.py
```

Then press **Ctrl+Alt** (configurable) to dictate. The cleaned text is pasted
into whatever field has focus.

**macOS first run:** grant your terminal app **Microphone** and **Accessibility**
permissions (System Settings → Privacy & Security). flow checks both at startup
and tells you exactly what's missing. On the very first run the Whisper model is
downloaded once; after that everything runs fully offline.

## Configuration — `config.yaml`

| Key | Default | Meaning |
|---|---|---|
| `mode` | `toggle` | `toggle` (press to start/stop) or `push_to_talk` (hold to record) |
| `hotkey` | `ctrl+alt` | key chord, e.g. `cmd+shift`, `alt+space` |
| `whisper_model` | `small` | `tiny`/`base`/`small`/`medium` — bigger = slower + better |
| `language` | autodetect | or pin e.g. `en` |
| `use_ollama` | `true` | LLM clean-up pass; falls back to raw transcript if Ollama is down |
| `ollama_model` | `llama3.2:3b` | any Ollama model |
| `edit_prompt` | built-in | customize how speech is rewritten |

## Testing flags

```bash
python src/flow.py --once           # one utterance from the mic, print (no paste)
python src/flow.py --wav test.wav   # transcribe a file — works headless, no mic
python src/flow.py --no-ollama      # raw Whisper output (compare vs. cleaned)
```

If Ollama is down or the model isn't pulled, flow warns with the exact command
to fix it and keeps working with raw transcripts — it never crashes mid-dictation.

## Status

Working MVP: hotkey (toggle **and** push-to-talk) → Whisper → Ollama clean-up →
Cmd+V paste, with config file, permission checks, and graceful degradation.
Roadmap for status overlay, context-aware tone, custom dictionary, and Command
Mode is in [`docs/02-architecture-and-roadmap.md`](docs/02-architecture-and-roadmap.md).

## Note

This reimplements *behavior* from public information using open-source components.
It contains no Wispr Flow code, models, or assets, and is not affiliated with Wispr.
