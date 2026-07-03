# Local Wispr Flow Clone — Architecture & Roadmap

Goal: a local, offline, no-subscription dictation tool that mimics Wispr Flow's
base behavior — press a hotkey anywhere, speak, get clean formatted text pasted
at your cursor — using **Whisper for speech-to-text** and **Ollama for the AI
editing pass**.

## 1. Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              flow (our app)                  │
                    │                                              │
 [Global hotkey] ──▶│  HotkeyListener ──▶ AudioRecorder            │
   (e.g. Ctrl+Space)│                         │ 16kHz mono WAV     │
                    │                         ▼                    │
                    │                    Transcriber ── Whisper    │
                    │                    (faster-whisper)          │
                    │                         │ raw text           │
                    │                         ▼                    │
                    │                    Editor ─────── Ollama HTTP │
                    │                    (llama3.2:3b) localhost:11434
                    │                         │ clean text         │
                    │                         ▼                    │
                    │                    TextInjector              │
                    │                  (clipboard + paste)         │
                    └─────────────────────────┬───────────────────┘
                                              ▼
                                   focused field in ANY app
```

Two local model servers:
- **Whisper** — bundled in-process via `faster-whisper` (no server needed), or
  `whisper.cpp` if you want C++/Metal speed.
- **Ollama** — a background service at `http://localhost:11434`, called over HTTP.

## 2. Tech stack (recommended MVP: Python)

Python is the fastest path to a working prototype. Move to Tauri/Electron/Swift
later only if you want a polished shippable app.

| Concern | Library | Notes |
|---|---|---|
| STT | `faster-whisper` | CTranslate2 backend; `int8` quantization; pick `base`/`small`/`medium` |
| Mic capture | `sounddevice` (+ `numpy`) | Records to a numpy buffer; feed straight to Whisper |
| Voice activity | `faster-whisper` built-in VAD, or `webrtcvad` | Trims silence, speeds transcription |
| Global hotkey | `pynput` | Cross-platform key listener; toggle or push-to-talk |
| LLM editing | Ollama HTTP API (`requests`/`httpx`) | `POST /api/generate` or `/api/chat` |
| Text injection | `pyperclip` + `pynput` paste | Copy result, simulate Cmd/Ctrl+V — most reliable across apps |
| Active app (context) | `pygetwindow` / platform APIs | Optional; feeds tone hints to the LLM |
| Tray/overlay UI | `pystray` / `rumps` (mac) | Optional; status indicator |

### Ollama model choice
Start with a **small, fast** instruction model so latency stays low:
- `llama3.2:3b` (good default), `qwen2.5:3b`, or `gemma2:2b`.
- The editing task is easy; a 3B model is plenty and keeps the LLM pass <1s.

### Whisper model choice
- `base` / `small` for speed on CPU; `medium` if you have a GPU and want accuracy.
- English-only variants (`base.en`) are faster if you only dictate in English.

## 3. The two prompts that do the real work

**Editing prompt (default dictation mode):**
> You are a dictation post-processor. Rewrite the raw speech-to-text below into
> clean written text. Add correct punctuation and capitalization, remove filler
> words (um, uh, like, you know), and resolve spoken self-corrections (e.g. "5pm,
> actually 6" → "6pm"; obey "scratch that" / "delete that"). Do NOT add content,
> answer questions, or explain. Output ONLY the cleaned text. Context: the user
> is typing into {active_app}.

**Command prompt (Command Mode):** same idea but the transcript is treated as an
*instruction* applied to previously dictated/selected text.

Keep temperature low (~0.2) and cap output; instruct "output only the text" to
avoid the model chatting back.

## 4. Cross-platform text injection notes (the gotcha)

Injecting into arbitrary apps is the least portable part:
- **macOS:** clipboard + `Cmd+V` works everywhere but requires granting
  **Accessibility** permission to the terminal/app. Native path = Accessibility API.
- **Windows:** clipboard + `Ctrl+V` via `pynput`/SendInput; generally smooth.
- **Linux X11:** `xdotool` or `pynput` work. **Wayland** blocks synthetic input —
  use `ydotool` (needs a daemon) or `wtype`.

MVP strategy: **clipboard + simulated paste** everywhere (save/restore the user's
existing clipboard so we don't clobber it).

## 5. Phased roadmap

**Phase 0 — Prereqs (½ day)**
- Install Ollama, `ollama pull llama3.2:3b`, verify `localhost:11434`.
- `pip install faster-whisper sounddevice pynput pyperclip numpy requests`.

**Phase 1 — MVP: hotkey → transcribe → paste (1–2 days)**
- Toggle hotkey records mic; on stop, run Whisper; paste raw text at cursor.
- Ship `src/flow.py` (included in this repo) and confirm end-to-end works.

**Phase 2 — Add the Ollama editing pass (1 day)**
- Route raw transcript through the editing prompt before pasting.
- Compare raw vs. cleaned output; tune the prompt and model size for latency.

**Phase 3 — Polish & parity features (ongoing)**
- Push-to-talk mode (hold to talk) in addition to toggle.
- Status overlay / tray icon (idle / recording / thinking).
- Active-app detection → context-aware tone.
- Custom dictionary (feed to Whisper `initial_prompt` + the LLM prompt).
- Command Mode (edit-by-voice on selected text).
- Config file (hotkey, model, language, prompt) + first-run model download.

**Phase 4 — Latency & productization (optional)**
- Streaming/partial transcription (chunked audio) for faster feedback.
- Keep Whisper + Ollama models warm/preloaded to avoid cold starts.
- Repackage as a native app (Tauri + Rust, or Swift on mac) for a real installer.

## 6. Expectations vs. the real product

- **Achievable now:** the full press→speak→clean-text→paste loop, offline, free.
- **Harder:** matching their ~2–4s cloud latency on a laptop, and the last 5% of
  editing polish (they use a purpose-tuned model). A local 3B model is close but
  not identical.
- **Your advantage:** fully offline, private, no subscription — the exact things
  Wispr Flow's cloud-only design can't offer.

## 7. Legal / ethical note

"Clone the base functionality" = reimplement the *behavior* from public info and
open-source models. Do **not** copy Wispr Flow's code, models, assets, or brand.
Everything above is built from open components (Whisper, Ollama, OSS libs).
