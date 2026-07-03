#!/usr/bin/env python3
"""
flow — a minimal local Wispr Flow clone.

Pipeline:  hotkey → record mic → Whisper (STT) → Ollama (clean-up) → paste at cursor.

This is a Phase-1/2 MVP meant to prove the loop end-to-end, not a polished app.
See docs/02-architecture-and-roadmap.md for the full plan.

Prereqs
-------
  1. Ollama running with a small model:   ollama pull llama3.2:3b
  2. pip install faster-whisper sounddevice pynput pyperclip numpy requests

Usage
-----
  python src/flow.py
  Press the hotkey (default: Ctrl+Alt) once to start recording, again to stop.
  The cleaned text is copied to the clipboard and pasted into the focused field.

Notes
-----
  * macOS: grant the terminal/app Accessibility + Microphone permissions.
  * Linux Wayland: synthetic paste may be blocked; use ydotool/wtype instead.
  * Set USE_OLLAMA = False to see the raw Whisper transcript with no LLM edit.
"""

import sys
import time
import threading

import numpy as np
import requests
import sounddevice as sd
import pyperclip
from pynput import keyboard

# ----------------------------- Config ---------------------------------------

SAMPLE_RATE = 16_000          # Whisper wants 16 kHz mono
WHISPER_MODEL = "base"        # tiny/base/small/medium — bigger = slower + better
WHISPER_COMPUTE = "int8"      # int8 (CPU) / float16 (GPU)
LANGUAGE = None               # None = autodetect, or e.g. "en"

USE_OLLAMA = True
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b"

# Hotkey: press once to start, again to stop (toggle). Ctrl+Alt held together.
HOTKEY = {keyboard.Key.ctrl_l, keyboard.Key.alt_l}

EDIT_PROMPT = (
    "You are a dictation post-processor. Rewrite the raw speech-to-text below "
    "into clean written text. Add correct punctuation and capitalization, remove "
    "filler words (um, uh, like, you know), and resolve spoken self-corrections "
    "(e.g. '5pm, actually 6' -> '6pm'; obey 'scratch that'). Do NOT add content, "
    "answer questions, or explain. Output ONLY the cleaned text.\n\n"
    "Raw transcript:\n{text}\n\nCleaned text:"
)

# ----------------------------- Whisper --------------------------------------

print(f"Loading Whisper model '{WHISPER_MODEL}' ...", flush=True)
from faster_whisper import WhisperModel  # imported here so config errors surface first

_whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type=WHISPER_COMPUTE)
print("Whisper ready.", flush=True)


def transcribe(audio: np.ndarray) -> str:
    segments, _ = _whisper.transcribe(
        audio,
        language=LANGUAGE,
        vad_filter=True,               # trims silence -> faster + cleaner
        beam_size=1,                   # greedy = lower latency
    )
    return " ".join(s.text.strip() for s in segments).strip()


# ----------------------------- Ollama ---------------------------------------

def clean_with_ollama(text: str) -> str:
    if not text:
        return text
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": EDIT_PROMPT.format(text=text),
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json().get("response", text).strip()
    except Exception as e:  # noqa: BLE001 — fall back to raw text on any failure
        print(f"[ollama] skipped ({e}); using raw transcript", flush=True)
        return text


# ----------------------------- Recorder -------------------------------------

class Recorder:
    def __init__(self):
        self._frames = []
        self._stream = None
        self.recording = False

    def _callback(self, indata, frames, time_info, status):  # noqa: ARG002
        if status:
            print(f"[audio] {status}", flush=True)
        self._frames.append(indata.copy())

    def start(self):
        self._frames = []
        self.recording = True
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        print("● recording... (press hotkey again to stop)", flush=True)

    def stop(self) -> np.ndarray:
        self.recording = False
        self._stream.stop()
        self._stream.close()
        self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames, axis=0).flatten()


# ----------------------------- Injection ------------------------------------

_kbd = keyboard.Controller()


def paste_text(text: str):
    """Copy to clipboard and simulate paste, restoring the previous clipboard."""
    if not text:
        return
    try:
        previous = pyperclip.paste()
    except Exception:  # noqa: BLE001
        previous = ""
    pyperclip.copy(text)
    time.sleep(0.05)

    paste_mod = keyboard.Key.cmd if sys.platform == "darwin" else keyboard.Key.ctrl
    with _kbd.pressed(paste_mod):
        _kbd.press("v")
        _kbd.release("v")

    # give the target app a moment to read the clipboard before we restore it
    time.sleep(0.15)
    try:
        pyperclip.copy(previous)
    except Exception:  # noqa: BLE001
        pass


# ----------------------------- Orchestration --------------------------------

recorder = Recorder()
_busy = threading.Lock()


def handle_stop_and_process():
    audio = recorder.stop()
    if audio.size == 0:
        print("(no audio captured)", flush=True)
        return
    print("… transcribing", flush=True)
    raw = transcribe(audio)
    print(f"raw: {raw!r}", flush=True)
    final = clean_with_ollama(raw) if USE_OLLAMA else raw
    print(f"out: {final!r}", flush=True)
    paste_text(final)
    print("✓ pasted\n", flush=True)


def toggle():
    # run processing off the listener thread so hotkeys stay responsive
    if not _busy.acquire(blocking=False):
        return
    try:
        if recorder.recording:
            handle_stop_and_process()
        else:
            recorder.start()
    finally:
        _busy.release()


# --- global hotkey detection (chord: all keys in HOTKEY held together) -------

_pressed = set()
_fired = False


def on_press(key):
    global _fired
    if key in HOTKEY:
        _pressed.add(key)
        if _pressed >= HOTKEY and not _fired:
            _fired = True
            threading.Thread(target=toggle, daemon=True).start()


def on_release(key):
    global _fired
    _pressed.discard(key)
    if not (_pressed >= HOTKEY):
        _fired = False


def main():
    mode = "Whisper + Ollama" if USE_OLLAMA else "Whisper only"
    print(f"\nflow ready ({mode}). Hotkey: Ctrl+Alt (toggle). Ctrl+C to quit.\n",
          flush=True)
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye")
