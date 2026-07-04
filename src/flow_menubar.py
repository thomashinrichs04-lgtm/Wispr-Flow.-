#!/usr/bin/env python3
"""
flow (menu-bar) — run the local Wispr Flow clone as a macOS menu-bar app,
with NO terminal window to keep open.

    pip install rumps
    python3 src/flow_menubar.py

A small icon appears in the top-right menu bar:
    ●  idle       (ready — press your hotkey to dictate)
    ●  recording  (listening)
    ●  thinking   (transcribing + cleaning)
Click it for a menu: current hotkey/mode, and Quit.

To launch it like a normal app (double-click, no Terminal at all), see
scripts/install_launchagent.sh which starts it automatically at login.

This reuses the exact same engine as src/flow.py (FlowEngine) — same hotkey,
Whisper, Ollama, and Cmd+V paste — so behavior is identical to the CLI.
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flow  # noqa: E402  — the shared engine + config + checks

try:
    import rumps
except ImportError:
    sys.exit(
        "error: the menu-bar app needs 'rumps'.\n"
        "  pip install rumps\n"
        "(rumps is macOS-only; on other platforms use: python3 src/flow.py)"
    )

ICONS = {"idle": "🎙️", "recording": "🔴", "thinking": "✨"}
TITLES = {"idle": "flow: ready", "recording": "flow: recording…",
          "thinking": "flow: thinking…"}


class FlowApp(rumps.App):
    def __init__(self, cfg):
        super().__init__(ICONS["idle"], quit_button=None)
        self.cfg = cfg
        mode = "hold to talk" if cfg["mode"] == "push_to_talk" else "toggle"
        self.menu = [
            rumps.MenuItem(f"Hotkey: {cfg['hotkey']} ({mode})", callback=None),
            rumps.MenuItem(
                f"Model: {cfg['ollama_model']}" if cfg["use_ollama"] else "Model: Whisper only",
                callback=None,
            ),
            None,  # separator
            rumps.MenuItem("Quit flow", callback=self._quit),
        ]
        self.engine = flow.FlowEngine(cfg, on_status=self._on_status)

    def _on_status(self, state):
        # Called from the engine's worker thread; marshal to the UI thread.
        def apply():
            self.title = ICONS.get(state, ICONS["idle"])
        try:
            rumps.Timer(lambda _: apply(), 0.01).start()
        except Exception:  # noqa: BLE001 — fall back to a direct set
            self.title = ICONS.get(state, ICONS["idle"])

    def _quit(self, _):
        self.engine.stop()
        rumps.quit_application()


def main():
    cfg = flow.load_config(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml"))
    if cfg["mode"] not in ("toggle", "push_to_talk"):
        sys.exit(f"error: config 'mode' must be toggle or push_to_talk, got {cfg['mode']!r}")

    # Same first-run permission + dependency checks as the CLI.
    if not flow.first_run_checks(cfg, need_paste=True):
        sys.exit(1)
    flow.load_whisper(cfg)

    app = FlowApp(cfg)
    # start the hotkey listener once the app is up
    threading.Thread(target=app.engine.start, daemon=True).start()
    app.run()


if __name__ == "__main__":
    main()
