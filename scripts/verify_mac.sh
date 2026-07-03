#!/usr/bin/env bash
# One-command verification of the flow pipeline on macOS.
#
#   bash scripts/verify_mac.sh
#
# Steps:
#   1. environment checks (python3, pip deps, ollama + model)
#   2. headless integration test (mock Ollama, no mic/model needed)
#   3. REAL pipeline on a bundled speech sample: Whisper + Ollama, no mic
#   4. tells you the two live commands to finish with your own voice
set -u
cd "$(dirname "$0")/.."

pass=0; fail=0
ok()   { echo "  ✓ $1"; pass=$((pass+1)); }
bad()  { echo "  ✗ $1"; fail=$((fail+1)); }

echo "== 1. Environment =="
if command -v python3 >/dev/null; then ok "python3: $(python3 --version 2>&1)"; else bad "python3 not found"; fi

if python3 -c "import faster_whisper, numpy, requests, sounddevice, pynput, pyperclip" 2>/dev/null; then
  ok "python deps installed"
else
  echo "    installing deps: pip3 install -r requirements.txt"
  pip3 install -q -r requirements.txt && ok "python deps installed" || bad "pip install failed"
fi

if command -v ollama >/dev/null; then
  ok "ollama CLI present"
  if curl -s --max-time 3 http://localhost:11434/api/tags >/dev/null; then
    ok "ollama server running"
  else
    bad "ollama server not running — start the Ollama app or run: ollama serve"
  fi
  if ollama list 2>/dev/null | grep -q "llama3.2:3b"; then
    ok "model llama3.2:3b pulled"
  else
    echo "    pulling model (one time, ~2 GB)..."
    ollama pull llama3.2:3b && ok "model llama3.2:3b pulled" || bad "ollama pull failed"
  fi
else
  bad "ollama not installed — get it from https://ollama.com (flow degrades to raw transcripts without it)"
fi

echo
echo "== 2. Headless integration test (mock Ollama) =="
if python3 tests/test_integration.py; then ok "integration test"; else bad "integration test"; fi

echo
echo "== 3. Real pipeline on bundled sample (Whisper + Ollama, no mic) =="
echo "   (first run downloads the Whisper model once)"
if python3 src/flow.py --wav tests/jfk.wav; then
  ok "wav pipeline ran — check the raw:/out: lines above"
else
  bad "wav pipeline failed"
fi

echo
echo "== Result: $pass passed, $fail failed =="
if [ "$fail" -eq 0 ]; then
  cat <<'EOF'

All automated checks passed. Two live steps remain (they need your voice/GUI):

  python3 src/flow.py --once    # speak, press Enter -> raw + cleaned printed
  python3 src/flow.py           # Ctrl+Alt to dictate into any app (Cmd+V paste)

macOS will prompt for Microphone (and Accessibility for the full mode);
flow prints the exact System Settings path if a permission is missing.
EOF
else
  echo; echo "Fix the ✗ items above and rerun: bash scripts/verify_mac.sh"
  exit 1
fi
