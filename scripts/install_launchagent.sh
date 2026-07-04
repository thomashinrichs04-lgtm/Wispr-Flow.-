#!/usr/bin/env bash
# Install flow as a macOS LaunchAgent so the menu-bar app starts automatically
# at login and always runs in the background — no Terminal, ever.
#
#   bash scripts/install_launchagent.sh          # install + start now
#   bash scripts/install_launchagent.sh --remove # uninstall
set -eu

LABEL="ai.local.flow"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"

if [ "${1:-}" = "--remove" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "removed $PLIST"
  exit 0
fi

if [ "$(uname)" != "Darwin" ]; then
  echo "This installer is macOS-only. On other platforms run: python3 src/flow.py"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$REPO/src/flow_menubar.py</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><false/>
  <key>StandardOutPath</key><string>$REPO/flow.log</string>
  <key>StandardErrorPath</key><string>$REPO/flow.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "installed $PLIST"
echo "flow will now start at login and appear in your menu bar."
echo "logs: $REPO/flow.log   |   remove: bash scripts/install_launchagent.sh --remove"
