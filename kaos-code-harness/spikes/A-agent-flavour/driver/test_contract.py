"""Spike A conformance test — does the harness driver satisfy KAOS's Agent contract?

Each assertion maps to a real consumer in the KAOS codebase, cited inline. If all
pass, the operator, CLI, and UI cannot distinguish this pod from a pydantic-ai one,
which is the whole claim of Option A in design question 2.

    uv run --with fastapi --with httpx --with pytest pytest test_contract.py -v
"""

import json
import os
import subprocess
import sys
import time

import httpx
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SURVEY = os.path.normpath(os.path.join(HERE, "..", "..", "H-harness-survey"))
MOCK = os.path.join(SURVEY, "mock-modelapi", "server.py")

# `pi` is installed via npm and gitignored, so a worktree checkout will not have
# it. Default to the main checkout; override with SPIKE_PI_BIN.
PI = os.environ.get("SPIKE_PI_BIN") or os.path.join(
    SURVEY, "pi", "node_modules", ".bin", "pi")
if not os.access(PI, os.X_OK):
    PI = os.path.expanduser(
        "~/Programming/agentic/kaos-ai-docs/kaos-code-harness/spikes/"
        "H-harness-survey/pi/node_modules/.bin/pi")

MOCK_PORT, DRV_PORT = 8089, 8088
BASE = f"http://127.0.0.1:{DRV_PORT}"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    state = tmp_path_factory.mktemp("state")
    work = tmp_path_factory.mktemp("work")

    mock = subprocess.Popen([sys.executable, MOCK, str(MOCK_PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    env = {**os.environ,
           "AGENT_NAME": "coder", "AGENT_DESCRIPTION": "spike A harness",
           "MODEL_API_URL": f"http://127.0.0.1:{MOCK_PORT}", "MODEL_NAME": "mock-model",
           "HARNESS_WORKSPACE": str(work), "HARNESS_STATE_DIR": str(state),
           "HARNESS_BIN": PI, "AGENT_PORT": str(DRV_PORT)}
    drv = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "harness_driver:app",
         "--host", "127.0.0.1", "--port", str(DRV_PORT), "--log-level", "warning"],
        cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for _ in range(80):
        try:
            if httpx.get(f"{BASE}/health", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.25)
    else:
        mock.kill(); drv.kill()
        pytest.fail("driver did not start")

    yield
    drv.kill(); mock.kill()


def script(responses):
    httpx.post(f"http://127.0.0.1:{MOCK_PORT}/_script",
               json={"responses": responses}, timeout=5)


# --- operator-facing: agent_controller.go:657-690 sets these two probes --------

def test_liveness_probe(server):
    assert httpx.get(f"{BASE}/health", timeout=5).status_code == 200


def test_readiness_probe(server):
    r = httpx.get(f"{BASE}/ready", timeout=5)
    assert r.status_code == 200 and r.json()["available"] is True


# --- A2A: serverutils.py AgentCard, consumed by RemoteAgent + kaos-ui ---------

def test_agent_card_shape(server):
    c = httpx.get(f"{BASE}/.well-known/agent.json", timeout=5).json()
    for k in ("name", "description", "url", "version", "protocolVersion",
              "capabilities", "skills", "supportedProtocols"):
        assert k in c, f"AgentCard missing {k}"
    # RemoteAgent.process_message picks the A2A path on this exact check
    assert "jsonrpc" in c["supportedProtocols"]


# --- chat: kaos_cli/agent/invoke.py + kaos-ui lib/agent-client.ts -------------

def test_chat_completions_non_streaming(server):
    script([{"type": "text", "text": "NONSTREAM_OK"}])
    r = httpx.post(f"{BASE}/v1/chat/completions", timeout=120,
                   json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert "NONSTREAM_OK" in r.json()["choices"][0]["message"]["content"]


def test_chat_completions_sse_shape(server):
    """kaos-ui detects progress events by 'content starts with { and parses'
    (agent-client.ts:151-162); the CLI uses the same heuristic (invoke.py:248)."""
    script([{"type": "text", "text": "STREAM_OK"}])
    saw_progress = saw_final = saw_done = False
    with httpx.stream("POST", f"{BASE}/v1/chat/completions", timeout=120,
                      headers={"X-Session-ID": "sess-1"},
                      json={"messages": [{"role": "user", "content": "hi"}],
                            "stream": True}) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            body = line[6:]
            if body == "[DONE]":
                saw_done = True
                continue
            chunk = json.loads(body)
            assert chunk["object"] == "chat.completion.chunk"
            assert chunk["id"] == "sess-1", "id must carry the session id"
            content = chunk["choices"][0]["delta"].get("content")
            if content and content.startswith("{"):
                ev = json.loads(content)
                if ev.get("type") == "progress":
                    assert {"step", "max_steps", "action"} <= ev.keys()
                    saw_progress = True
            elif content and "STREAM_OK" in content:
                saw_final = True
    assert saw_progress and saw_final and saw_done


# --- A2A JSON-RPC: pais/a2a.py dispatcher, driven by kaos agent a2a ----------

def test_a2a_send_get_list(server):
    script([{"type": "text", "text": "A2A_OK"}])
    send = httpx.post(BASE, timeout=120, json={
        "jsonrpc": "2.0", "id": 1, "method": "SendMessage",
        "params": {"message": {"parts": [{"type": "text", "text": "hi"}]},
                   "contextId": "sess-a2a"}}).json()
    assert "error" not in send, send
    task = send["result"]
    assert task["status"]["state"] == "completed"
    assert "A2A_OK" in task["artifacts"][0]["parts"][0]["text"]

    got = httpx.post(BASE, timeout=10, json={
        "jsonrpc": "2.0", "id": 2, "method": "GetTask",
        "params": {"id": task["id"]}}).json()
    assert got["result"]["id"] == task["id"]

    lst = httpx.post(BASE, timeout=10, json={
        "jsonrpc": "2.0", "id": 3, "method": "ListTasks", "params": {}}).json()
    assert any(t["id"] == task["id"] for t in lst["result"]["tasks"])


def test_a2a_unknown_method_is_jsonrpc_error(server):
    r = httpx.post(BASE, timeout=10, json={
        "jsonrpc": "2.0", "id": 9, "method": "Nope", "params": {}}).json()
    assert r["error"]["code"] == -32601


# --- UI memory tab: 2s poll of /memory/events -------------------------------

def test_memory_events_populated(server):
    evs = httpx.get(f"{BASE}/memory/events",
                    params={"session_id": "sess-1"}, timeout=5).json()["events"]
    kinds = {e["event_type"] for e in evs}
    assert {"user_message", "agent_response"} <= kinds


# --- the ceiling: can ONE pod serve N addressable parallel sessions? ----------

def test_parallel_sessions_in_one_pod(server):
    """`replicas` is int32(1) with no spec field, so an Agent is always one pod.
    The question that decides design question 2 is whether one pod can still serve
    N concurrent, separately-addressable sessions with distinct workspaces."""
    import concurrent.futures as cf

    n = 4
    script([{"type": "text", "text": f"S{i}"} for i in range(n)] * 4)

    def one(i):
        r = httpx.post(f"{BASE}/v1/chat/completions", timeout=180,
                       headers={"X-Session-ID": f"par-{i}"},
                       json={"messages": [{"role": "user", "content": f"task {i}"}]})
        return r.status_code, r.json()["id"]

    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=n) as ex:
        results = list(ex.map(one, range(n)))
    elapsed = time.time() - t0

    assert all(code == 200 for code, _ in results), results
    ids = {sid for _, sid in results}
    assert ids == {f"par-{i}" for i in range(n)}, ids

    # Each session must have its own workspace directory.
    sess = httpx.get(f"{BASE}/sessions", timeout=5).json()["sessions"]
    wss = {s["id"]: s["workspace"] for s in sess if s["id"].startswith("par-")}
    assert len(set(wss.values())) == len(wss), f"workspaces collided: {wss}"
    print(f"\n  {n} concurrent sessions in one pod in {elapsed:.1f}s; "
          f"{len(set(wss.values()))} distinct workspaces")
