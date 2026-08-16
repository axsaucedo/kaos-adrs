#!/usr/bin/env bash
# Spike S — can a harness hold the agent loop while a SEPARATE process owns the
# workspace and does all execution?
#
# Setup mirrors the two-pod split:
#   pod 1 (harness)  claude -p, every native filesystem/shell tool disallowed
#   pod 2 (sandbox)  sandbox_mcp.py over streamable HTTP, owns the workspace
#
# Passes only if the harness completes real work in the sandbox while provably
# holding no filesystem tools of its own.
set -uo pipefail
cd "$(dirname "$0")"

MOCK_PORT=8087
MCP_PORT=9101
SANDBOX=/tmp/kaos-spike-s-sandbox
HOMEDIR=/tmp/kaos-spike-s-home
MOCK=../H-harness-survey/mock-modelapi/server.py

# Native tools that must NOT reach the model when execution is remote.
NATIVE=(Bash Edit Write Read Glob Grep NotebookEdit WebFetch WebSearch Agent)

rm -rf "$SANDBOX" "$HOMEDIR"; mkdir -p "$SANDBOX" "$HOMEDIR"

python3 "$MOCK" $MOCK_PORT >/tmp/spike-s-mock.log 2>&1 & MOCKPID=$!
SANDBOX_ROOT="$SANDBOX" uv run --quiet --with fastmcp sandbox_mcp.py --port $MCP_PORT \
  >/tmp/spike-s-mcp.log 2>&1 & MCPPID=$!
trap 'kill $MOCKPID $MCPPID 2>/dev/null' EXIT

for _ in $(seq 60); do curl -sf "http://127.0.0.1:$MOCK_PORT/v1/models" >/dev/null && break; sleep 0.3; done

# The MCP server must be genuinely serving tools before Claude connects — a port
# that merely accepts TCP is not enough, and a cold `uv run` takes ~15s. Claude
# reports no error when an MCP server is unreachable; the tools are just silently
# absent, which reads exactly like "the split does not work".
echo -n "waiting for sandbox MCP"
for _ in $(seq 40); do
  if uv run --quiet --with fastmcp python -c "
import asyncio,sys
from fastmcp import Client
async def m():
    async with Client('http://127.0.0.1:$MCP_PORT/mcp') as c:
        sys.exit(0 if await c.list_tools() else 1)
asyncio.run(m())" >/dev/null 2>&1; then echo " ready"; break; fi
  echo -n "."; sleep 1
done

cat > "$HOMEDIR/mcp.json" <<EOF
{"mcpServers": {"sandbox": {"type": "http", "url": "http://127.0.0.1:$MCP_PORT/mcp"}}}
EOF

DISALLOW=(); for t in "${NATIVE[@]}"; do DISALLOW+=(--disallowedTools "$t"); done

claude_run() {
  echo "$1" | HOME="$HOMEDIR" \
    ANTHROPIC_BASE_URL="http://127.0.0.1:$MOCK_PORT" ANTHROPIC_AUTH_TOKEN=not-needed \
    CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1 \
    timeout 120 command claude -p --model mock-model \
      --mcp-config "$HOMEDIR/mcp.json" --strict-mcp-config \
      "${DISALLOW[@]}" \
      --permission-mode bypassPermissions 2>&1
}

pass=0; fail=0
check() { if [ "$2" = "0" ]; then echo "  PASS  $1"; pass=$((pass+1));
          else echo "  FAIL  $1"; fail=$((fail+1)); fi; }

echo "== 1/3 sandbox tools reach the harness, native tools do not =="
curl -sf -X POST "http://127.0.0.1:$MOCK_PORT/_script" \
  -d '{"responses":[{"type":"text","text":"INSPECT"}]}' >/dev/null
claude_run "list your tools" >/dev/null
# Read the richest call, not the first: the preflight turn carries no tools.
TOOLS=$(curl -sf "http://127.0.0.1:$MOCK_PORT/_calls" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print(' '.join(max((c['tools'] for c in d), key=len)) if d else '')")
echo "  tools on the wire: ${TOOLS:-<none>}"
echo "$TOOLS" | grep -q "mcp__sandbox__remote_write"; check "remote sandbox tools present" $?
LEAKED=""
for t in "${NATIVE[@]}"; do echo "$TOOLS" | grep -qw "$t" && LEAKED="$LEAKED $t"; done
[ -z "$LEAKED" ]; check "no native filesystem/shell tool leaked (${LEAKED:-none})" $?

echo "== 2/3 harness performs real work through the remote sandbox =="
curl -sf -X POST "http://127.0.0.1:$MOCK_PORT/_script" -d '{"responses":[
  {"type":"tool","name":"mcp__sandbox__remote_write",
   "args":{"path":"hello.txt","content":"written via remote sandbox"}},
  {"type":"text","text":"SPLIT_OK"}]}' >/dev/null
OUT=$(claude_run "create hello.txt in the workspace")
echo "$OUT" | tail -3
if [ -f "$SANDBOX/hello.txt" ]; then
  echo "  sandbox file: $(cat "$SANDBOX/hello.txt")"; check "file created in the SANDBOX process" 0
else
  echo "  sandbox contents: $(ls -A "$SANDBOX" 2>/dev/null || echo empty)"
  check "file created in the SANDBOX process" 1
fi

echo "== 3/3 sandbox refuses path escape =="
ESC=$(SANDBOX_ROOT="$SANDBOX" uv run --quiet --with fastmcp python -c "
import asyncio, sys
from fastmcp import Client
async def main():
    async with Client('http://127.0.0.1:$MCP_PORT/mcp') as c:
        try:
            await c.call_tool('remote_write', {'path':'../escaped.txt','content':'x'})
            print('ESCAPED')
        except Exception:
            print('BLOCKED')
asyncio.run(main())" 2>/dev/null | tail -1)
echo "  escape attempt: $ESC"
[ "$ESC" = "BLOCKED" ] && [ ! -f /tmp/escaped.txt ]; check "path traversal blocked" $?

echo; echo "RESULT pass=$pass fail=$fail"
[ "$fail" = "0" ]
