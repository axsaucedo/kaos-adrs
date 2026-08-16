"""Spike A — serve KAOS's existing Agent HTTP contract from a coding harness.

The bet under test: the KAOS operator never talks to the process inside an agent
pod. It resolves dependencies into env vars and talks HTTP to :8000. So if a
harness image serves the same routes the pydantic-ai runtime serves, the operator
cannot tell the difference and **no new CRD is needed**.

Routes the operator and clients actually depend on (from pais/server.py and
agent_controller.go:657-690):

    GET  /health                    liveness probe
    GET  /ready                     readiness probe
    GET  /.well-known/agent.json    A2A agent card
    GET  /tools                     tool listing
    GET  /memory/events             UI memory tab (2s poll)
    GET  /memory/sessions
    POST /v1/chat/completions       CLI + UI chat, SSE
    POST /                          A2A JSON-RPC (SendMessage/GetTask/...)

Configuration arrives entirely as env vars, exactly as the operator sets them.

    uvicorn harness_driver:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# --- configuration, from the operator's env vars ------------------------------

AGENT_NAME = os.environ.get("AGENT_NAME", "harness")
AGENT_DESCRIPTION = os.environ.get("AGENT_DESCRIPTION", "coding harness")
AGENT_INSTRUCTIONS = os.environ.get("AGENT_INSTRUCTIONS", "")
MODEL_API_URL = os.environ.get("MODEL_API_URL", "")
MODEL_NAME = os.environ.get("MODEL_NAME", "mock-model")
WORKSPACE = os.environ.get("HARNESS_WORKSPACE", "/workspace")
STATE_DIR = os.environ.get("HARNESS_STATE_DIR", "/state")
PI_BIN = os.environ.get("HARNESS_BIN", "pi")
PORT = int(os.environ.get("AGENT_PORT", "8000"))

app = FastAPI(title=f"kaos-harness/{AGENT_NAME}")

# In-process task + event state, mirroring LocalTaskManager/LocalMemory semantics.
TASKS: dict[str, dict[str, Any]] = {}
EVENTS: dict[str, list[dict[str, Any]]] = {}


def _provider_config() -> str:
    """Write a pi custom provider pointing at the operator-supplied ModelAPI."""
    cfg_dir = os.path.join(STATE_DIR, ".pi", "agent")
    os.makedirs(cfg_dir, exist_ok=True)
    base_url = (MODEL_API_URL.rstrip("/") + "/v1") if MODEL_API_URL else ""
    with open(os.path.join(cfg_dir, "models.json"), "w") as fh:
        json.dump({"providers": {"kaos-modelapi": {
            "name": "KAOS ModelAPI", "baseUrl": base_url,
            "apiKey": os.environ.get("MODEL_API_KEY", "not-needed"),
            "api": "openai-completions",
            "models": [{"id": MODEL_NAME, "name": MODEL_NAME,
                        "contextWindow": 128000, "maxTokens": 8192}],
        }}}, fh)
    return STATE_DIR


def _record(session_id: str, event_type: str, content: Any) -> None:
    EVENTS.setdefault(session_id, []).append({
        "event_type": event_type, "content": content,
        "timestamp": time.time(), "session_id": session_id,
    })


async def _run_harness(prompt: str, session_id: str):
    """Drive the harness once. Yields (kind, payload) as it goes."""
    home = _provider_config()
    env = {**os.environ, "HOME": home}
    argv = [PI_BIN, "-p", "--provider", "kaos-modelapi", "--model", MODEL_NAME,
            "--session-dir", os.path.join(STATE_DIR, "sessions"),
            "--session-id", session_id,
            "--no-extensions", "--no-skills", "--no-context-files"]
    if AGENT_INSTRUCTIONS:
        argv += ["--append-system-prompt", AGENT_INSTRUCTIONS]
    argv.append(prompt)

    _record(session_id, "user_message", prompt)
    yield ("progress", {"type": "progress", "step": 1, "max_steps": 1,
                        "action": "tool_call", "target": "harness"})

    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=WORKSPACE if os.path.isdir(WORKSPACE) else None,
        env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    text = (out or b"").decode().strip() or (err or b"").decode().strip()

    _record(session_id, "agent_response", text)
    yield ("final", text)


def _chunk(session_id: str, content: str | None, finish: str | None = None):
    return {"id": session_id, "object": "chat.completion.chunk",
            "created": int(time.time()), "model": MODEL_NAME,
            "choices": [{"index": 0,
                         "delta": ({"content": content} if content is not None else {}),
                         "finish_reason": finish}]}


# --- routes -------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    return {"status": "ready", "harness": PI_BIN, "available": bool(shutil.which(PI_BIN))}


@app.get("/.well-known/agent.json")
async def agent_card():
    return {
        "name": AGENT_NAME, "description": AGENT_DESCRIPTION,
        "url": f"http://localhost:{PORT}", "version": "0.1.0",
        "protocolVersion": "0.3.0",
        "capabilities": {"streaming": True, "pushNotifications": False},
        "skills": [{"id": "code", "name": "code",
                    "description": "edit code in a workspace",
                    "tags": ["coding"]}],
        "supportedProtocols": ["jsonrpc"],
        "defaultInputModes": ["text"], "defaultOutputModes": ["text"],
    }


@app.get("/tools")
async def tools():
    # The harness owns its toolset; KAOS sees it as opaque.
    return {"tools": [{"name": n, "description": f"harness builtin: {n}"}
                      for n in ("bash", "edit", "read", "write")]}


@app.get("/memory/events")
async def memory_events(session_id: str = ""):
    return {"events": EVENTS.get(session_id, []) if session_id
            else [e for evs in EVENTS.values() for e in evs]}


@app.get("/memory/sessions")
async def memory_sessions():
    return {"sessions": list(EVENTS.keys())}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    prompt = next((m.get("content", "") for m in reversed(messages)
                   if m.get("role") == "user"), "")
    session_id = (request.headers.get("X-Session-ID")
                  or body.get("session_id") or str(uuid.uuid4()))

    if not body.get("stream"):
        final = ""
        async for kind, payload in _run_harness(prompt, session_id):
            if kind == "final":
                final = payload
        return JSONResponse({
            "id": session_id, "object": "chat.completion",
            "created": int(time.time()), "model": MODEL_NAME,
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": final},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })

    async def stream():
        async for kind, payload in _run_harness(prompt, session_id):
            content = json.dumps(payload) if kind == "progress" else payload
            yield f"data: {json.dumps(_chunk(session_id, content))}\n\n"
        yield f"data: {json.dumps(_chunk(session_id, None, 'stop'))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/")
async def a2a(request: Request):
    """A2A JSON-RPC. Method names match KAOS's (SendMessage + tasks/* aliases)."""
    req = await request.json()
    method, params, rid = req.get("method"), req.get("params", {}), req.get("id")

    def ok(result):
        return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": result})

    def err(code, msg):
        return JSONResponse({"jsonrpc": "2.0", "id": rid,
                             "error": {"code": code, "message": msg}})

    if method in ("SendMessage", "tasks/send", "message/send"):
        msg = params.get("message", {})
        text = " ".join(p.get("text", "") for p in msg.get("parts", [])
                        if p.get("type") == "text")
        session_id = params.get("contextId") or str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        TASKS[task_id] = {"id": task_id, "contextId": session_id,
                          "status": {"state": "working"}, "artifacts": []}
        final = ""
        async for kind, payload in _run_harness(text, session_id):
            if kind == "final":
                final = payload
        TASKS[task_id].update({
            "status": {"state": "completed"},
            "artifacts": [{"parts": [{"type": "text", "text": final}]}]})
        return ok(TASKS[task_id])

    if method in ("GetTask", "tasks/get"):
        t = TASKS.get(params.get("id") or params.get("taskId"))
        return ok(t) if t else err(-32001, "Task not found")

    if method in ("ListTasks", "tasks/list"):
        return ok({"tasks": list(TASKS.values())})

    if method in ("CancelTask", "tasks/cancel"):
        t = TASKS.get(params.get("id") or params.get("taskId"))
        if not t:
            return err(-32001, "Task not found")
        t["status"] = {"state": "canceled"}
        return ok(t)

    return err(-32601, f"Method not found: {method}")
