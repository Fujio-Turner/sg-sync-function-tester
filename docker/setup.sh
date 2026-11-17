#!/usr/bin/env bash
# One-time setup of the local SG 4.x test stack (idempotent-ish: re-running is safe).
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE="docker compose -f docker-compose.yml"
CB_ADMIN=Administrator
CB_PASS=password
BUCKET=sync_gateway
SG_ADMIN="http://localhost:4985"

# wait_for <desc> <cmd...> : retry cmd every 2s, give up after 3 minutes
wait_for() { local d=$1; shift; for _ in $(seq 1 90); do "$@" >/dev/null 2>&1 && return 0; sleep 2; done; echo "Timed out waiting for $d" >&2; exit 1; }

echo "==> Waiting for Couchbase Server..."
wait_for "Couchbase Server" $COMPOSE exec -T cb-server curl -sf http://localhost:8091/ui/index.html

echo "==> Initialising cluster"
$COMPOSE exec -T cb-server couchbase-cli cluster-init -c localhost \
  --cluster-username "$CB_ADMIN" --cluster-password "$CB_PASS" \
  --services data,index,query --cluster-ramsize 1024 --cluster-index-ramsize 256 \
  --index-storage-setting default || echo "   (already initialised)"

echo "==> Creating bucket $BUCKET"
$COMPOSE exec -T cb-server couchbase-cli bucket-create -c localhost \
  -u "$CB_ADMIN" -p "$CB_PASS" --bucket "$BUCKET" --bucket-type couchbase \
  --bucket-ramsize 256 --wait || echo "   (bucket exists)"

echo "==> Creating RBAC user sync_gateway"
$COMPOSE exec -T cb-server couchbase-cli user-manage -c localhost \
  -u "$CB_ADMIN" -p "$CB_PASS" --set --rbac-username sync_gateway \
  --rbac-password password --auth-domain local \
  --roles "mobile_sync_gateway[*]"

echo "==> Waiting for Sync Gateway admin API..."
wait_for "Sync Gateway" curl -sf -u "$CB_ADMIN:$CB_PASS" "$SG_ADMIN/"
curl -s -u "$CB_ADMIN:$CB_PASS" "$SG_ADMIN/"; echo

echo "==> Creating SG database $BUCKET"
SYNC_FN=$(python3 -c 'import json,sys;print(json.dumps(open("sync-function.js").read()))')
curl -s -u "$CB_ADMIN:$CB_PASS" -X PUT "$SG_ADMIN/$BUCKET/" \
  -H 'Content-Type: application/json' \
  -d "{\"bucket\":\"$BUCKET\",\"num_index_replicas\":0,\"sync\":$SYNC_FN}"; echo

db_online() { curl -sf -u "$CB_ADMIN:$CB_PASS" "$SG_ADMIN/$BUCKET/" | grep -q '"state":"Online"'; }
wait_for "database online" db_online

echo "==> Creating SG user bob"
curl -s -u "$CB_ADMIN:$CB_PASS" -X PUT "$SG_ADMIN/$BUCKET/_user/bob" \
  -H 'Content-Type: application/json' \
  -d '{"name":"bob","password":"12345","admin_channels":["bob"]}'; echo

echo "==> Done. Public: http://localhost:4984/$BUCKET  Admin: $SG_ADMIN/$BUCKET  CB UI: http://localhost:28091"
