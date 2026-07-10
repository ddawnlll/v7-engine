#!/bin/bash
# Praxis MCP helper — sends JSON-RPC to the Praxis MCP server via stdio
# Usage: .praxis_mcp.sh <method> [plan_file] [evidence_file]
#   method: verify, validate, status, cache

METHOD="$1"
PLAN_PATH="${2:-}"
EVIDENCE_PATH="${3:-}"
PRAXIS_SRC="/workspace/praxis/packages/mcp-server/src/index.ts"
BUN="/root/.bun/bin/bun"
PIPE=" | timeout 30 $BUN run $PRAXIS_SRC 2>/dev/null"

case "$METHOD" in
  status)
    PAYLOAD='{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"praxis_status","arguments":{}}}'
    echo "$PAYLOAD" | timeout 10 $BUN run $PRAXIS_SRC 2>/dev/null | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
result = json.loads(data['result']['content'][0]['text'])
print(json.dumps(result, indent=2))
"
    ;;

  validate)
    python3 -c "
import json, sys
with open('$PLAN_PATH') as f:
    plan_yaml = f.read()
req = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'praxis_validate','arguments':{'planYaml': plan_yaml}}}
print(json.dumps(req))
" | timeout 15 $BUN run $PRAXIS_SRC 2>/dev/null | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
if 'result' in data and 'content' in data['result']:
    print(data['result']['content'][0]['text'])
else:
    print(json.dumps(data, indent=2))
"
    ;;

  verify)
    python3 -c "
import json, sys
with open('$PLAN_PATH') as f:
    plan_yaml = f.read()
args = {'planYaml': plan_yaml, 'stopOnHold': True}
if '$EVIDENCE_PATH':
    args['evidenceLedgerPath'] = '$EVIDENCE_PATH'
req = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'praxis_verify','arguments': args}}
print(json.dumps(req))
" | timeout 30 $BUN run $PRAXIS_SRC 2>/dev/null | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
if 'result' in data and 'content' in data['result']:
    print(data['result']['content'][0]['text'])
else:
    print(json.dumps(data, indent=2))
"
    ;;

  cache)
    PAYLOAD='{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"praxis_cache_stats","arguments":{}}}'
    echo "$PAYLOAD" | timeout 10 $BUN run $PRAXIS_SRC 2>/dev/null | python3 -c "
import sys, json
data = json.loads(sys.stdin.read())
result = json.loads(data['result']['content'][0]['text'])
print(json.dumps(result, indent=2))
"
    ;;

  *)
    echo "Usage: $0 {status|validate|verify|cache} [plan_file] [evidence_file]"
    exit 1
    ;;
esac
