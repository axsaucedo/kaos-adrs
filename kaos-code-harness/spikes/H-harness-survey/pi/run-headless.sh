#!/usr/bin/env bash
# Spike H — prove `pi` runs headless against an arbitrary OpenAI-compatible
# endpoint (standing in for a KAOS ModelAPI), with no real credential.
#
# Asserts four things the design depends on:
#   1. non-interactive `-p` returns a result and exits
#   2. a custom provider with an arbitrary baseUrl is honoured
#   3. built-in tools are offered to the model (so the harness is a real harness)
#   4. `--no-builtin-tools` removes them (the Spike S question)
set -uo pipefail
cd "$(dirname "$0")"

PORT=8099
PI_HOME="$PWD/.pi-home"
PI=./node_modules/.bin/pi

rm -rf "$PI_HOME"; mkdir -p "$PI_HOME/.pi/agent"

# Custom provider → arbitrary base URL, fake key. This is the KAOS ModelAPI shape.
cat > "$PI_HOME/.pi/agent/models.json" <<EOF
{
  "providers": {
    "kaos-modelapi": {
      "name": "KAOS ModelAPI",
      "baseUrl": "http://127.0.0.1:$PORT/v1",
      "apiKey": "not-needed",
      "api": "openai-completions",
      "models": [
        { "id": "mock-model", "name": "mock", "contextWindow": 8192, "maxTokens": 1024 }
      ]
    }
  }
}
EOF

python3 ../mock-modelapi/server.py $PORT >/tmp/spike-h-mock.log 2>&1 &
MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
for _ in $(seq 30); do
  curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null && break; sleep 0.2
done

script() { curl -sf -X POST "http://127.0.0.1:$PORT/_script" -d "$1" >/dev/null; }
calls()  { curl -sf "http://127.0.0.1:$PORT/_calls"; }

pass=0; fail=0
check() { # name, condition-result
  if [ "$2" = "0" ]; then echo "  PASS  $1"; pass=$((pass+1));
  else echo "  FAIL  $1"; fail=$((fail+1)); fi
}

echo "== 1/3 headless text turn against custom baseUrl =="
script '{"responses":[{"type":"text","text":"HEADLESS_OK"}]}'
OUT=$(HOME="$PI_HOME" timeout 90 "$PI" -p --provider kaos-modelapi --model mock-model \
        --no-session --no-extensions --no-skills --no-context-files \
        "say hello" 2>&1)
echo "$OUT" | tail -3
echo "$OUT" | grep -q "HEADLESS_OK"; check "returns model output and exits" $?

echo "== 2/3 built-in tools are advertised =="
TOOLS=$(calls | python3 -c "import json,sys; d=json.load(sys.stdin); print(','.join(d[0]['tools']) if d else '')")
echo "  tools offered: ${TOOLS:-<none>}"
[ -n "$TOOLS" ]; check "harness advertises its built-in toolset" $?

echo "== 3/3 --no-builtin-tools strips them (Spike S question) =="
script '{"responses":[{"type":"text","text":"NOTOOLS_OK"}]}'
HOME="$PI_HOME" timeout 90 "$PI" -p --provider kaos-modelapi --model mock-model \
    --no-builtin-tools --no-session --no-extensions --no-skills --no-context-files \
    "say hello" >/dev/null 2>&1
TOOLS2=$(calls | python3 -c "import json,sys; d=json.load(sys.stdin); print(','.join(d[0]['tools']) if d else '')")
echo "  tools offered: ${TOOLS2:-<none>}"
[ -z "$TOOLS2" ]; check "built-in tools can be disabled" $?

echo
echo "RESULT pass=$pass fail=$fail"
[ "$fail" = "0" ]
