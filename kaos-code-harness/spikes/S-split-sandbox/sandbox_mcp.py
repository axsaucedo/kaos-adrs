"""Spike S — the execution sandbox, as a remote MCP server.

Stands in for the second pod in the split architecture: the harness holds the
agent loop and touches no filesystem, while this process owns the workspace and
does all execution. In KAOS terms this is an `MCPServer` CR — a separate
Deployment on :8000 speaking streamable HTTP, which is exactly the transport KAOS
already mandates (every runtime in kaos-mcp-runtimes is `transport: http`).

Every tool refuses to escape SANDBOX_ROOT, since the point of the split is that
the harness cannot reach anything the sandbox does not hand it.

    SANDBOX_ROOT=/tmp/ws uv run --with fastmcp sandbox_mcp.py --port 9100
"""

import argparse
import os
import subprocess
from pathlib import Path

from fastmcp import FastMCP

ROOT = Path(os.environ.get("SANDBOX_ROOT", "/tmp/kaos-sandbox")).resolve()
ROOT.mkdir(parents=True, exist_ok=True)

mcp = FastMCP("kaos-sandbox")


def _resolve(rel: str) -> Path:
    p = (ROOT / rel).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError(f"path escapes sandbox root: {rel}")
    return p


@mcp.tool()
def remote_write(path: str, content: str) -> str:
    """Write a file in the sandbox workspace."""
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"wrote {len(content)} bytes to {path}"


@mcp.tool()
def remote_read(path: str) -> str:
    """Read a file from the sandbox workspace."""
    return _resolve(path).read_text()


@mcp.tool()
def remote_list(path: str = ".") -> str:
    """List files in the sandbox workspace."""
    p = _resolve(path)
    return "\n".join(sorted(x.name for x in p.iterdir())) or "(empty)"


@mcp.tool()
def remote_bash(command: str, timeout: int = 60) -> str:
    """Run a shell command inside the sandbox workspace."""
    r = subprocess.run(command, shell=True, cwd=ROOT, capture_output=True,
                       text=True, timeout=timeout)
    out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
    return f"[exit {r.returncode}]\n{out}".strip()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9100)
    args = ap.parse_args()
    print(f"sandbox MCP on :{args.port} root={ROOT}", flush=True)
    mcp.run(transport="http", host="127.0.0.1", port=args.port)
