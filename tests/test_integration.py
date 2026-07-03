"""Integration test: flow.py against a live mock Ollama server on localhost.

Verifies the real HTTP code paths (check_ollama, clean_with_ollama) and the
full process_audio pipeline with a stubbed Whisper model — i.e. everything
except real model inference, mic, and paste (which need the user's Mac).
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import flow

PORT = 11499


class MockOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_GET(self):
        assert self.path == "/api/tags", self.path
        body = json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        assert self.path == "/api/generate", self.path
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        # sanity: the edit prompt made it through with the transcript embedded
        assert "dictation post-processor" in req["prompt"], req["prompt"][:80]
        assert "um so hello world" in req["prompt"]
        assert req["model"] == "llama3.2:3b"
        assert req["options"]["temperature"] == 0.2
        body = json.dumps({"response": "Hello, world."}).encode()
        self.send_response(200)
        self.end_headers()
        self.wfile.write(body)


server = HTTPServer(("127.0.0.1", PORT), MockOllama)
threading.Thread(target=server.serve_forever, daemon=True).start()

cfg = dict(flow.DEFAULT_CONFIG, ollama_url=f"http://127.0.0.1:{PORT}")

# 1. health check against a live server (model present)
assert flow.check_ollama(cfg) is True

# 2. health check catches a missing model
cfg_missing = dict(cfg, ollama_model="mistral:7b")
assert flow.check_ollama(cfg_missing) is False

# 3. real request/response through clean_with_ollama
out = flow.clean_with_ollama("um so hello world", cfg)
assert out == "Hello, world.", repr(out)

# 4. full pipeline with a stubbed Whisper model (real everything-else)
class FakeSeg:
    text = " um so hello world "

class FakeWhisper:
    def transcribe(self, audio, **kw):
        return [FakeSeg()], None

flow._whisper = FakeWhisper()
printed = []
import builtins
orig_print = builtins.print
builtins.print = lambda *a, **k: printed.append(" ".join(str(x) for x in a))
try:
    flow.process_audio("dummy.wav", cfg, do_paste=False)
finally:
    builtins.print = orig_print

assert any("raw: 'um so hello world'" in line for line in printed), printed
assert any("out: 'Hello, world.'" in line for line in printed), printed

server.shutdown()
print("INTEGRATION TEST PASSED: tags check, missing-model check, generate round-trip, full pipeline")
