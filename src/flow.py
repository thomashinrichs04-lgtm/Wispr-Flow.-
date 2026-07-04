#!/usr/bin/env python3
"""
flow — a minimal local Wispr Flow clone (macOS-first).

Pipeline:  hotkey → record mic → Whisper (STT) → Ollama (clean-up) → paste at cursor.

Prereqs
-------
  1. Ollama running with a small model:   ollama pull llama3.2:3b
  2. pip install -r requirements.txt

Usage
-----
  python src/flow.py                 # interactive: global hotkey, paste at cursor
  python src/flow.py --once         # record ONE utterance (Enter to stop), print result
  python src/flow.py --wav file.wav # transcribe a wav file, print result (no mic needed)
  python src/flow.py --no-ollama    # skip the LLM pass, raw Whisper output only

Modes (config.yaml → mode):
  toggle        press hotkey once to start, again to stop
  push_to_talk  hold hotkey to record, release to stop

macOS
-----
  Grant your terminal app BOTH permissions in System Settings → Privacy & Security:
    * Microphone            (to record)
    * Accessibility         (for the global hotkey + Cmd+V paste)
  flow checks both at startup and tells you exactly what is missing.
"""

import argparse
import os
import sys
import threading
import time

import numpy as np
import requests

# ----------------------------- Config ---------------------------------------

SAMPLE_RATE = 16_000  # Whisper wants 16 kHz mono

DEFAULT_CONFIG = {
    # "toggle" (press to start / press to stop) or "push_to_talk" (hold to record)
    "mode": "toggle",
    # chord of modifier/regular keys, e.g. "ctrl+alt" or "cmd+shift+space"
    "hotkey": "ctrl+alt",
    # tiny / base / small / medium — bigger = slower + more accurate.
    # "small" is a good default on Apple Silicon.
    "whisper_model": "small",
    "whisper_compute": "int8",   # int8 (CPU) / float16 (GPU)
    "language": None,             # None = autodetect, or "en", "de", ...
    "use_ollama": True,
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3.2:3b",
    "ollama_timeout_s": 60,
    # System prompt for the clean-up pass. The raw transcript is sent as the
    # user message (small models reliably ignore transcripts embedded in one
    # big /api/generate prompt, so we use /api/chat with a system/user split).
    "edit_prompt": (
        "You are a dictation post-processor. The user's message is a raw "
        "speech-to-text transcript. Return it VERBATIM — the same words in the "
        "same order — with only these fixes: correct punctuation and "
        "capitalization, remove filler words (um, uh, like, you know), and apply "
        "spoken self-corrections (e.g. '5pm, actually 6' -> '6pm'; obey 'scratch "
        "that'). Never paraphrase, reword, shorten, expand, answer questions, or "
        "add comments. Output ONLY the corrected transcript."
    ),
}


def load_config(path: str) -> dict:
    """Read config.yaml over the defaults. Missing file or missing pyyaml → defaults."""
    cfg = dict(DEFAULT_CONFIG)
    if not os.path.exists(path):
        return cfg
    try:
        import yaml  # optional dependency
    except ImportError:
        print(f"[config] pyyaml not installed; ignoring {path} and using defaults")
        return cfg
    try:
        with open(path) as f:
            user = yaml.safe_load(f) or {}
        unknown = set(user) - set(cfg)
        if unknown:
            print(f"[config] ignoring unknown keys: {', '.join(sorted(unknown))}")
        cfg.update({k: v for k, v in user.items() if k in cfg})
    except Exception as e:  # noqa: BLE001
        print(f"[config] could not read {path} ({e}); using defaults")
    return cfg


# ----------------------------- Whisper --------------------------------------

_whisper = None


def load_whisper(cfg: dict):
    global _whisper
    print(f"Loading Whisper model '{cfg['whisper_model']}' ...", flush=True)
    from faster_whisper import WhisperModel

    try:
        _whisper = WhisperModel(
            cfg["whisper_model"], device="cpu", compute_type=cfg["whisper_compute"]
        )
    except Exception as e:  # noqa: BLE001 — usually a first-run download failure
        sys.exit(
            f"error: could not load Whisper model '{cfg['whisper_model']}' ({e}).\n"
            "On first run the model is downloaded from Hugging Face, which needs\n"
            "internet access once; after that flow runs fully offline. Check your\n"
            "connection, or set a smaller model (e.g. 'tiny') in config.yaml."
        )
    print("Whisper ready.", flush=True)


def transcribe(audio, cfg: dict) -> str:
    """audio: float32 numpy array at 16 kHz, or a path to an audio file."""
    segments, _ = _whisper.transcribe(
        audio,
        language=cfg["language"],
        vad_filter=True,  # trims silence -> faster + cleaner
        beam_size=1,      # greedy = lower latency
    )
    return " ".join(s.text.strip() for s in segments).strip()


# ----------------------------- Ollama ---------------------------------------

def check_ollama(cfg: dict) -> bool:
    """Return True if Ollama is reachable and the model is available."""
    base = cfg["ollama_url"].rstrip("/")
    try:
        resp = requests.get(f"{base}/api/tags", timeout=3)
        resp.raise_for_status()
    except Exception:  # noqa: BLE001
        print(
            f"[ollama] not reachable at {base}.\n"
            f"         Start it with:  ollama serve   (or open the Ollama app)\n"
            f"         flow will fall back to RAW Whisper transcripts until then."
        )
        return False
    names = [m.get("name", "") for m in resp.json().get("models", [])]
    want = cfg["ollama_model"]
    if not any(n == want or n.split(":")[0] == want.split(":")[0] for n in names):
        print(
            f"[ollama] model '{want}' not found. Pull it with:\n"
            f"         ollama pull {want}\n"
            f"         flow will fall back to RAW transcripts until then."
        )
        return False
    print(f"[ollama] ready ({want} @ {base})")
    return True


def clean_with_ollama(text: str, cfg: dict) -> str:
    if not text:
        return text
    try:
        resp = requests.post(
            f"{cfg['ollama_url'].rstrip('/')}/api/chat",
            json={
                "model": cfg["ollama_model"],
                "messages": [
                    {"role": "system", "content": cfg["edit_prompt"]},
                    {"role": "user", "content": text},
                ],
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=cfg["ollama_timeout_s"],
        )
        resp.raise_for_status()
        cleaned = resp.json().get("message", {}).get("content", "").strip()
        return cleaned or text
    except Exception as e:  # noqa: BLE001 — never crash the loop; degrade to raw
        print(f"[ollama] skipped ({e}); using raw transcript", flush=True)
        return text


# ----------------------------- macOS permission checks ----------------------

def check_accessibility() -> bool:
    """True if this process may control the keyboard (macOS Accessibility)."""
    if sys.platform != "darwin":
        return True
    try:
        import ctypes.util

        lib = ctypes.util.find_library("ApplicationServices")
        appsvc = __import__("ctypes").cdll.LoadLibrary(lib)
        return bool(appsvc.AXIsProcessTrusted())
    except Exception:  # noqa: BLE001 — can't determine; don't block
        return True


def check_microphone() -> bool:
    """Try to open the default input device for a moment."""
    try:
        import sounddevice as sd

        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32"):
            pass
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[mic] could not open microphone: {e}")
        return False


def first_run_checks(cfg: dict, need_paste: bool) -> bool:
    """Print exactly what's missing. Returns False if we cannot run at all."""
    ok = True
    if not check_microphone():
        ok = False
        if sys.platform == "darwin":
            print(
                "  → System Settings → Privacy & Security → Microphone:\n"
                "    enable your terminal app (e.g. Terminal / iTerm), then rerun."
            )
    if need_paste and not check_accessibility():
        ok = False
        print(
            "[accessibility] this process is NOT trusted to control the keyboard,\n"
            "so the global hotkey and Cmd+V paste will not work.\n"
            "  → System Settings → Privacy & Security → Accessibility:\n"
            "    enable your terminal app, then rerun flow."
        )
    check_ollama(cfg) if cfg["use_ollama"] else None
    return ok


# ----------------------------- Recorder -------------------------------------

class Recorder:
    def __init__(self):
        self._frames = []
        self._stream = None
        self.recording = False
        self.level = 0.0  # live RMS of the last audio block (for the overlay)

    def _callback(self, indata, frames, time_info, status):  # noqa: ARG002
        if status:
            print(f"[audio] {status}", flush=True)
        self._frames.append(indata.copy())
        self.level = float(np.sqrt(np.mean(indata ** 2)))

    def start(self):
        import sounddevice as sd

        self._frames = []
        self.recording = True
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> np.ndarray:
        self.recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self._frames, axis=0).flatten()


# ----------------------------- Wave overlay ---------------------------------

class WaveOverlay:
    """Small floating pill with animated noise waves (styled after
    docs/noisewaves.png: layered teal→white→pink waves on dark grey).

    Tk must run on the main thread on macOS, so interactive mode runs this
    mainloop in the foreground and the hotkey listener in a thread. Other
    threads only touch `.phase` ("idle" | "recording" | "thinking") and
    read `recorder.level`; the overlay polls both from a Tk timer.
    """

    W, H = 230, 60
    FPS_MS = 33
    BG = "#2e2e30"
    COLORS = ("#8ff0dd", "#e9e9ec", "#f2a9c8")  # teal / white / pink

    def __init__(self, recorder: "Recorder"):
        import tkinter as tk

        self.recorder = recorder
        self.phase = "idle"
        self._smooth = 0.0
        self._t = 0.0
        self._visible = False

        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)  # no title bar / border
        for attr, val in (("-topmost", True), ("-alpha", 0.93)):
            try:
                root.attributes(attr, val)
            except tk.TclError:
                pass
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{self.W}x{self.H}+{(sw - self.W) // 2}+{sh - self.H - 80}")
        self.canvas = tk.Canvas(root, width=self.W, height=self.H,
                                bg=self.BG, highlightthickness=0)
        self.canvas.pack()
        self.root = root
        root.after(self.FPS_MS, self._tick)

    def _tick(self):
        if self.phase == "idle":
            if self._visible:
                self.root.withdraw()
                self._visible = False
        else:
            if not self._visible:
                self.root.deiconify()
                self.root.lift()
                self._visible = True
            self._draw()
        self.root.after(self.FPS_MS, self._tick)

    def _draw(self):
        import math

        # amplitude follows the mic while recording; gentle idle pulse while
        # transcribing so the pill shows flow is still working
        if self.phase == "recording":
            target = min(1.0, self.recorder.level * 14.0)
        else:
            target = 0.18 + 0.08 * math.sin(self._t * 0.5)
        self._smooth += (target - self._smooth) * 0.25
        self._t += 0.22

        c = self.canvas
        c.delete("wave")
        mid = self.H / 2
        n = 44  # points per line
        for wi, color in enumerate(self.COLORS):
            for sub in range(3):  # 3 offset strands per color -> mesh look
                pts = []
                for i in range(n + 1):
                    u = i / n
                    env = math.sin(math.pi * u) ** 0.8  # taper at both ends
                    amp = (7 + 5 * wi + 2 * sub) * (0.18 + 0.82 * self._smooth)
                    y = mid + env * amp * math.sin(
                        2 * math.pi * u * (1.4 + 0.5 * wi)
                        + self._t * (1.0 + 0.18 * wi) + wi * 2.1 + sub * 0.4)
                    pts += [u * self.W, y]
                c.create_line(*pts, fill=color, width=1, smooth=True, tags="wave")

    def run(self):
        self.root.mainloop()


def make_overlay(recorder: "Recorder"):
    """Overlay or None — flow works fine without a GUI (headless/SSH/no Tk)."""
    try:
        return WaveOverlay(recorder)
    except Exception as e:  # noqa: BLE001
        print(f"[overlay] disabled ({e}); running without the wave indicator",
              flush=True)
        return None


# ----------------------------- Injection ------------------------------------

def paste_text(text: str):
    """Copy to clipboard and simulate Cmd/Ctrl+V, restoring the previous clipboard."""
    if not text:
        return
    import pyperclip
    from pynput import keyboard

    try:
        previous = pyperclip.paste()
    except Exception:  # noqa: BLE001
        previous = ""
    pyperclip.copy(text)
    time.sleep(0.05)

    kbd = keyboard.Controller()
    paste_mod = keyboard.Key.cmd if sys.platform == "darwin" else keyboard.Key.ctrl
    with kbd.pressed(paste_mod):
        kbd.press("v")
        kbd.release("v")

    # give the target app a moment to read the clipboard before we restore it
    time.sleep(0.15)
    try:
        pyperclip.copy(previous)
    except Exception:  # noqa: BLE001
        pass


# ----------------------------- Hotkey parsing --------------------------------

def parse_hotkey(spec: str) -> set:
    """'ctrl+alt' -> {'ctrl', 'alt'}. Names are canonical (no left/right)."""
    keys = {part.strip().lower() for part in spec.split("+") if part.strip()}
    if not keys:
        raise ValueError(f"empty hotkey spec: {spec!r}")
    return keys


def key_name(key) -> str:
    """Canonical name for a pynput key: ctrl_l/ctrl_r -> 'ctrl', 'A' -> 'a'."""
    from pynput import keyboard

    if isinstance(key, keyboard.Key):
        name = key.name
        for base in ("ctrl", "alt", "shift", "cmd"):
            if name.startswith(base):
                return base
        return name
    # the fn/globe key has no pynput Key; macOS reports it as vk 63 (kVK_Function)
    if sys.platform == "darwin" and getattr(key, "vk", None) == 0x3F:
        return "fn"
    try:
        return key.char.lower()
    except AttributeError:
        return str(key)


# ----------------------------- Orchestration --------------------------------

def process_audio(audio, cfg: dict, do_paste: bool):
    if isinstance(audio, np.ndarray) and audio.size == 0:
        print("(no audio captured)", flush=True)
        return
    print("… transcribing", flush=True)
    raw = transcribe(audio, cfg)
    print(f"raw: {raw!r}", flush=True)
    final = clean_with_ollama(raw, cfg) if cfg["use_ollama"] else raw
    print(f"out: {final!r}", flush=True)
    if do_paste:
        paste_text(final)
        print("✓ pasted\n", flush=True)


class FlowEngine:
    """Hotkey → record → transcribe → clean → paste, reusable by the terminal
    runner and the menu-bar app. Reports state changes via on_status(state):
    one of "idle", "recording", "thinking". Non-blocking: start() returns a
    running pynput listener that the caller keeps alive (join() or an app loop).
    """

    def __init__(self, cfg: dict, on_status=None):
        self.cfg = cfg
        self.on_status = on_status or (lambda state: None)
        self.chord = parse_hotkey(cfg["hotkey"])
        self.ptt = cfg["mode"] == "push_to_talk"
        self.recorder = Recorder()  # public: the wave overlay reads .level
        self._busy = threading.Lock()
        self._pressed: set = set()
        self._fired = False
        self._listener = None

    def _status(self, state):
        try:
            self.on_status(state)
        except Exception:  # noqa: BLE001 — UI callback must never break the engine
            pass

    def _start_recording(self):
        self.recorder.start()
        self._status("recording")
        print("● recording...", flush=True)

    def _stop_and_process(self):
        audio = self.recorder.stop()
        # Wait for the chord to be released before pasting, else the synthetic
        # Cmd+V lands as e.g. Ctrl+Alt+Cmd+V and the target app ignores it.
        deadline = time.time() + 2.0
        while self._pressed and time.time() < deadline:
            time.sleep(0.05)
        self._status("thinking")
        try:
            process_audio(audio, self.cfg, do_paste=True)
        finally:
            self._status("idle")

    def _dispatch(self, action):
        def run():
            if not self._busy.acquire(blocking=False):
                return
            try:
                action()
            finally:
                self._busy.release()
        threading.Thread(target=run, daemon=True).start()

    def _on_press(self, key):
        self._pressed.add(key_name(key))
        if self._pressed >= self.chord and not self._fired:
            self._fired = True
            if self.ptt:
                if not self.recorder.recording:
                    self._dispatch(self._start_recording)
            else:
                self._dispatch(
                    self._stop_and_process if self.recorder.recording
                    else self._start_recording
                )

    def _on_release(self, key):
        self._pressed.discard(key_name(key))
        if not (self._pressed >= self.chord):
            self._fired = False
            if self.ptt and self.recorder.recording:
                self._dispatch(self._stop_and_process)

    def start(self):
        from pynput import keyboard

        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        self._listener.start()
        self._status("idle")
        return self._listener

    def stop(self):
        if self._listener is not None:
            self._listener.stop()


def run_interactive(cfg: dict):
    engine = FlowEngine(cfg)
    overlay = make_overlay(engine.recorder)
    if overlay is not None:
        # engine states ("idle"/"recording"/"thinking") drive the wave pill
        engine.on_status = lambda state: setattr(overlay, "phase", state)
    listener = engine.start()
    mode_desc = "hold to talk" if engine.ptt else "toggle"
    llm = f"Whisper + Ollama ({cfg['ollama_model']})" if cfg["use_ollama"] else "Whisper only"
    print(f"\nflow ready ({llm}). Hotkey: {cfg['hotkey']} ({mode_desc}). Ctrl+C to quit.\n",
          flush=True)
    try:
        if overlay is not None:
            overlay.run()  # Tk needs the main thread on macOS
        else:
            listener.join()
    finally:
        engine.stop()


def run_once(cfg: dict):
    """Record a single utterance from the mic; Enter stops. Prints, no paste."""
    recorder = Recorder()
    recorder.start()
    print("● recording — press Enter to stop", flush=True)
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    process_audio(recorder.stop(), cfg, do_paste=False)


def run_wav(cfg: dict, path: str):
    """Transcribe an audio file — end-to-end test with no mic or GUI needed."""
    process_audio(path, cfg, do_paste=False)


def main():
    ap = argparse.ArgumentParser(description="flow — local Wispr Flow clone")
    ap.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"),
        help="path to config.yaml")
    ap.add_argument("--once", action="store_true",
                    help="record one utterance (Enter to stop), print result, exit")
    ap.add_argument("--wav", metavar="FILE",
                    help="transcribe an audio file and print result (no mic needed)")
    ap.add_argument("--no-ollama", action="store_true",
                    help="skip the LLM pass; raw Whisper output only")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.no_ollama:
        cfg["use_ollama"] = False
    if cfg["mode"] not in ("toggle", "push_to_talk"):
        sys.exit(f"error: config 'mode' must be toggle or push_to_talk, got {cfg['mode']!r}")

    if args.wav:
        if not os.path.exists(args.wav):
            sys.exit(f"error: file not found: {args.wav}")
        if cfg["use_ollama"]:
            check_ollama(cfg)
        load_whisper(cfg)
        run_wav(cfg, args.wav)
        return

    # live-mic paths need permission checks before loading anything heavy
    if not first_run_checks(cfg, need_paste=not args.once):
        sys.exit(1)
    load_whisper(cfg)
    if args.once:
        run_once(cfg)
    else:
        run_interactive(cfg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye")
