#!/usr/bin/env bash
#
# Applies the collection log migration (014) to the PRODUCTION database and
# seeds the catalog, which /collection-log/items serves to stabiliserver.
#
#   ./scripts/migrate_prod_collection_log.sh
#
# Credentials are read from the REMOTE_DATABASE_* entries in .env, so nothing
# secret is ever typed or printed. Nothing is written until you confirm.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# The revision prod must be on before this runs. If it is on anything else,
# `flask db upgrade` would apply other pending migrations too (conquest tables,
# ALTERs on teams/events/challenges) — far more than the collection log.
EXPECTED_BEFORE="a9b0c1d2e3f4"
TARGET="b1c2d3e4f5a6"

env_value() { grep -m1 "^$1=" .env | cut -d= -f2- | tr -d '"' | tr -d "'"; }

HOST="$(env_value REMOTE_DATABASE_HOST)"
PORT="$(env_value REMOTE_DATABASE_PORT)"
NAME="$(env_value REMOTE_DATABASE_DATABASE)"
export DATABASE_USERNAME="$(env_value REMOTE_DATABASE_USERNAME)"
export DATABASE_PASSWORD="$(env_value REMOTE_DATABASE_PASSWORD)"
export DATABASE_URL="$HOST:$PORT/$NAME"
export PYTHONPATH=.

if [[ -z "$HOST" || -z "$DATABASE_USERNAME" || -z "$DATABASE_PASSWORD" ]]; then
  echo "Could not read REMOTE_DATABASE_* values from .env" >&2
  exit 1
fi

# flask prints a lot of startup noise; keep only what matters.
quiet() { grep -viE "processed:|swagger|registered successfully|INFO -|WARNING -" || true; }

echo "Target: $HOST:$PORT/$NAME  (user: $DATABASE_USERNAME)"
echo

echo "==> Current revision on prod"
CURRENT="$(.venv/bin/flask db current 2>&1 | quiet | grep -oE '[a-f0-9]{12}' | head -1 || true)"

if [[ -z "$CURRENT" ]]; then
  echo "Could not read a revision from prod. Full output:" >&2
  .venv/bin/flask db current 2>&1 | quiet >&2
  exit 1
fi

echo "    $CURRENT"
echo

if [[ "$CURRENT" == "$TARGET" ]]; then
  echo "Prod is already at $TARGET — migration has been applied."
  echo "Skipping upgrade; will still verify the catalog below."
else
  if [[ "$CURRENT" != "$EXPECTED_BEFORE" ]]; then
    cat >&2 <<MSG

ABORTING. Prod is at $CURRENT, expected $EXPECTED_BEFORE.

Running 'flask db upgrade' from here would also apply every migration in
between, not just the collection log one. Check what those are first:

    .venv/bin/flask db history -r "$CURRENT:$TARGET"

MSG
    exit 1
  fi

  echo "Prod is at $EXPECTED_BEFORE. Migration $TARGET will:"
  echo "  - CREATE TABLE collection_log_items (+ unique constraint, index)"
  echo "  - CREATE TABLE collection_log_drops (+ index, FK to users.discord_id)"
  echo "  No ALTER or DROP on anything that already exists."
  echo
  read -r -p "Apply to PRODUCTION? [y/N] " reply
  [[ "$reply" == "y" || "$reply" == "Y" ]] || { echo "Aborted."; exit 1; }

  echo
  echo "==> Applying migration"
  .venv/bin/flask db upgrade 2>&1 | quiet
fi

echo
echo "==> Seeding the catalog (idempotent full refresh)"
.venv/bin/python scripts/seed_collection_log.py 2>&1 | quiet

echo
echo "==> Verifying"
.venv/bin/python - <<'PY' 2>&1 | quiet
from app import app, db
from models.models import CollectionLogItem, CollectionLogDrop
with app.app_context():
    items = db.session.query(CollectionLogItem).count()
    drops = db.session.query(CollectionLogDrop).count()
    ids = db.session.query(CollectionLogItem.item_id).distinct().count()
    print(f"    catalog placements : {items}")
    print(f"    distinct item ids  : {ids}   <- what /collection-log/items serves")
    print(f"    drops recorded     : {drops}")
PY

cat <<'MSG'

Done. Remaining step, on stabiliserver:

    curl -X POST <stabiliserver-url>/collection-log/reload

It caches the item-id set at startup, so until it reloads it will forward no
collection log drops — silently, with no error.
MSG
