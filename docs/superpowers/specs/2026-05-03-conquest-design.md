# Conquest Event Type — Design Spec

**Date:** 2026-05-03
**Branch:** conquest-vibes

---

## Overview

Conquest is a new event type for the OSRS clan management system. Teams compete to control territories within regions by completing challenges. Territory and region control shifts live as player actions are processed. All meaningful state changes are written to an append-only `event_logs` table for timeline visualization; current state is always stored directly on entity rows — never derived from logs.

---

## Scope

- New SQLAlchemy models: `Region`, `Territory`, `TerritoryChallengeMappings`, `EventLog`
- Single Alembic migration creating all new tables
- `services/conquest_service.py` with four service functions
- `event_handlers/conquest/conquest.py` handler registered via `@EventHandler.register_handler`
- REST endpoints (with conquest-event validation) under `endpoints/v2/`
- SSE endpoint for live event log streaming

Out of scope: `territories.json` static file and `genTer.py` (live in frontend repo).

---

## Data Layer

### New Models (added to `models/new_events.py`)

**Region**
- `id` uuid PK
- `event_id` FK → events (CASCADE DELETE)
- `name` varchar
- `controlling_team_id` nullable FK → teams (SET NULL)
- `green_logged_teams` ARRAY(UUID), default `{}`
- `image_url` varchar(512), nullable
- `offset_x`, `offset_y` integer, nullable

**Territory**
- `id` uuid PK
- `region_id` FK → regions (CASCADE DELETE)
- `name` varchar
- `tier` varchar, nullable
- `controlling_team_id` nullable FK → teams (SET NULL)
- `display_order` integer, nullable
- `offset_x`, `offset_y` integer, nullable
- `polygon_points` JSONB, nullable

**TerritoryChallengeMappings**
- `id` uuid PK
- `territory_id` unique FK → territories (CASCADE DELETE)
- `challenge_id` unique FK → challenges (CASCADE DELETE)
- `created_at` timestamptz

**EventLog**
- `id` uuid PK
- `event_id` FK → events (CASCADE DELETE)
- `team_id` FK → teams (CASCADE DELETE)
- `type` varchar(50) — one of: `TERRITORY_CONTROL`, `REGION_CONTROL`, `GREEN_LOG`, `CHALLENGE_COMPLETED`
- `entity_type` varchar(50), nullable — `'territory'` | `'region'` | `'challenge'`
- `entity_id` uuid, nullable
- `metadata` JSONB, nullable — e.g. `{ previousTeamId, completionCount, challengeName }`
- `created_at` timestamptz

Indexes on `(event_id, created_at)`, `(event_id, type)`, `(entity_id, type)`.

### Migration

Single new Alembic migration (`013_conquest_tables.py`) creating all four tables with all columns. No alterations to existing tables — regions and territories are net-new.

---

## Scoring Constants

Defined as a module-level dict in `services/conquest_service.py`:

```python
CONQUEST_SCORING = {
    "TERRITORY_OWNED": 10,   # per territory currently controlled — live, can be lost
    "REGION_OWNED": 50,      # per region currently controlled — live, can be lost
    "TASK_COMPLETION": 1,    # per challenge completion — cumulative, never lost
    "GREEN_LOG_BONUS": 15,   # one-time per region — never lost
}
```

---

## Service Layer (`services/conquest_service.py`)

All four functions accept a SQLAlchemy session. Each runs within the caller's transaction — they do not commit.

### `update_territory_control(territory_id, session)`

Queries completion counts (`floor(quantity / challenge.quantity)`) for all teams for the territory's mapped challenge. Applies tie-break: challenger must strictly exceed current holder. Updates `territories.controlling_team_id`. Returns `{ changed, previous_team_id, new_team_id }`.

### `update_region_control(region_id, session)`

Counts territories per controlling team within the region. Same tie-break logic. Updates `regions.controlling_team_id`. Returns `{ changed, previous_team_id, new_team_id }`.

### `check_green_log(team_id, region_id, session)`

Skips immediately if `team_id` already in `regions.green_logged_teams`. Otherwise checks that every territory-mapped challenge in the region has `floor(quantity / challenge.quantity) >= 1` for this team. If so, appends team to `green_logged_teams` array. Returns bool.

### `recalculate_team_points(team_id, event_id, session)`

Single query across all four scoring sources:
- Territories currently controlled by this team in this event × `TERRITORY_OWNED`
- Regions currently controlled × `REGION_OWNED`
- Sum of `floor(cs.quantity / c.quantity)` for all completed challenges × `TASK_COMPLETION`
- Count of regions where team is in `green_logged_teams` × `GREEN_LOG_BONUS`

Writes result to `teams.points`. Returns the computed integer.

---

## Conquest Event Handler (`event_handlers/conquest/conquest.py`)

Registered via `@EventHandler.register_handler` for event type `conquest`. Processes each incoming action inside a single DB transaction; SSE broadcast happens after commit.

### Pipeline

```
1. INSERT into actions
2. Match action → triggers by (name, source, type), case-insensitive. Batch-load triggers for
   the event upfront to avoid N+1 queries (same pattern as bingo handler).
3. For each matched trigger:
   a. Find challenges for this trigger scoped to this event
   b. Identify acting player's team via team_members
   c. old_completions = floor(current quantity / challenge.quantity)
   d. UPDATE challenge_statuses SET quantity += action.quantity
   e. new_completions = floor(new quantity / challenge.quantity)
   f. Update completed boolean (bingo compatibility)

   g. If new_completions > old_completions:
      i.   Append EventLog: CHALLENGE_COMPLETED
      ii.  Look up territory_challenge_mappings for this challenge_id.
           If a mapping exists (territory_id found):
             Call update_territory_control(territory_id)
             If changed:
             Append EventLog: TERRITORY_CONTROL
               { team_id: new_team_id, entity_type: 'territory', entity_id: territory_id,
                 metadata: { previousTeamId } }
             Call update_region_control(region_id)
             If changed:
               Append EventLog: REGION_CONTROL
                 { team_id: new_team_id, entity_type: 'region', entity_id: region_id,
                   metadata: { previousTeamId } }
      iii. Call check_green_log(team_id, territory.region_id)
           If true:
             Append EventLog: GREEN_LOG

4. Call recalculate_team_points for ALL teams in event
5. COMMIT
6. broadcast_delta(event_id, new_log_entries)  ← after commit
```

Returns a `NotificationResponse` (Discord embed) summarizing the action — same shape as bingo/botw handlers.

---

## REST Endpoints (`endpoints/v2/conquest.py`)

All routes validate that `event.type == 'conquest'` and return 400 if not.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v2/events/<event_id>/regions` | All regions with controlling_team_id |
| GET | `/v2/events/<event_id>/territories` | All territories with controlling_team_id |
| GET | `/v2/events/<event_id>/event-logs` | Paginated event logs, newest first |
| POST | `/v2/territory-challenge-mappings` | Create a mapping |
| GET | `/v2/territory-challenge-mappings/<id>` | Get a mapping |
| DELETE | `/v2/territory-challenge-mappings/<id>` | Delete a mapping |

---

## SSE Endpoint

```
GET /v2/events/<event_id>/scoreboard/stream
```

**Server implementation:**
- Module-level `dict[event_id → set[SimpleQueue]]` registry in `endpoints/v2/conquest.py`
- Flask `Response` with generator function, `Content-Type: text/event-stream`
- On connect: fetch last 10 `event_logs` for the event, write as initial payload, then block on queue
- `broadcast_delta(event_id, log_entries)`: called post-commit, puts serialized entries onto every connected client's queue
- Heartbeat comment (`: ping`) every 30 seconds to keep connection alive
- On disconnect: generator exits, queue removed from registry

Each SSE message is a serialized `EventLog` entry (id, type, entity_type, entity_id, metadata, created_at, team_id).

---

## Design Principles

- **Current state on entity rows** — `controlling_team_id` on territories/regions, `green_logged_teams` on regions, `points` on teams. No joins through history needed.
- **`event_logs` is purely historical** — never read back to derive current state.
- **Completion-based territory control** — a team controls a territory only by having more full completions (`floor(quantity / challenge.quantity)`) than every other team. Raw quantity does not determine control.
- **Ties preserve the current holder** — a challenger must strictly exceed, not match.
- **All state changes in one transaction** — SSE broadcast always happens after commit.
