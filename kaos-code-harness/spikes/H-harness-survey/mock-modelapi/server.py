"""Minimal OpenAI-compatible /v1/chat/completions server.

Stands in for a KAOS ModelAPI (LiteLLM proxy) so a harness can be pointed at an
arbitrary base URL without any real credential or network egress.

Scripted turns: each request pops the next response off RESPONSES. A response is
either plain text or a tool call, so a harness's tool loop can be exercised.

    python3 server.py [port]
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# Scripted turns, consumed in order. Set via /_script before driving the harness.
RESPONSES = [{"type": "text", "text": "ack"}]
CALLS = []


def _chunk(model, delta, finish=None):
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # keep the spike output readable

    def _send(self, code, body, ctype="application/json"):
        raw = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/v1/models"):
            self._send(200, json.dumps({"object": "list", "data": [
                {"id": "mock-model", "object": "model", "owned_by": "kaos"}]}))
        elif self.path == "/_calls":
            self._send(200, json.dumps(CALLS))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            req = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            req = {}

        if self.path == "/_script":
            RESPONSES[:] = req.get("responses", [])
            CALLS.clear()
            return self._send(200, json.dumps({"ok": True, "n": len(RESPONSES)}))

        if not self.path.startswith("/v1/chat/completions"):
            return self._send(404, json.dumps({"error": "not found"}))

        CALLS.append({
            "n_messages": len(req.get("messages", [])),
            "tools": sorted(
                t.get("function", {}).get("name", "?") for t in req.get("tools", []) or []
            ),
            "auth": self.headers.get("Authorization", ""),
        })

        model = req.get("model", "mock-model")
        nxt = RESPONSES.pop(0) if RESPONSES else {"type": "text", "text": "done"}

        if nxt["type"] == "tool":
            msg = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": nxt["name"], "arguments": json.dumps(nxt["args"])},
            }]}
            finish = "tool_calls"
        else:
            msg = {"role": "assistant", "content": nxt["text"]}
            finish = "stop"

        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            delta = dict(msg)
            delta.pop("role", None)
            for c in (_chunk(model, {"role": "assistant"}), _chunk(model, delta),
                      _chunk(model, {}, finish)):
                self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        self._send(200, json.dumps({
            "id": "chatcmpl-mock", "object": "chat.completion",
            "created": int(time.time()), "model": model,
            "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    print(f"mock ModelAPI on :{port}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
