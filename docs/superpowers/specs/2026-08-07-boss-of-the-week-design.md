# Boss of the Week on the new event schema

## Goal

Replace the hardcoded Boss of the Week handler with a configurable event on the
`new_stability` schema. An admin creates a BOTW event, picks one or more bosses,
and gets a KC challenge plus a challenge for every collection log drop from each
boss, each with an editable point value. Players score individually.

## Current state

`event_handlers/botw/boss_of_the_week_handler.py` scores against two module-level
dicts (`kc_point_dict`, `item_point_dict`) hardcoded to Fortis Colosseum, and
accumulates points in `public.events.data` keyed by RSN. Changing the boss means
editing and deploying the file.

The new schema (`models/new_events.py`) already models everything the config side
needs: `Trigger` is what to match, `Challenge.value` is what it's worth,
`Challenge.quantity = NULL` means repeatable. What it lacks is per-player
progress — `ChallengeStatus` is keyed on `team_id`.

## Decisions

| Question | Decision |
| --- | --- |
| Who scores | Individual players, not teams |
| Bosses per event | One or more, all live simultaneously (e.g. the four DT2 awakened bosses) |
| Drop list source | Auto-seeded from `collection_log_items`, point values editable afterward |
| Duplicate drops | Score every time, unlimited |
| Legacy handler | Stays registered alongside the new one |
| Progress storage | Extend `challenge_statuses` to be player-aware rather than adding a parallel table |

## Constraints discovered

These are load-bearing; the feature does not work without them.

**KC quantity is cumulative.** `kill_count_handler.py` in stabiliserver submits
`quantity=count`, where `count` is the boss's total kill count (143), not 1.
Incrementing challenge progress by `submission.quantity` would award 143 kills'
worth of points on a single kill. The KC challenge must set
`count_per_action = 1`.

**The whitelist gates delivery.** stabiliserver fetches `/events/whitelist` and
discards any drop or KC not on it before calling this backend. BOTW triggers must
be reachable from that endpoint or the event scores nothing.

**Collection log pages are activities, not bosses.** The catalog page is
`Fortis Colosseum`; Dink reports the kill as `Sol Heredit`. The drop source and
the KC trigger name are therefore separate fields.

**The catalog has no images.** `collection_log_items.image_url` is null in the
published catalog. Drop icons are derived client-side from the OSRS item id,
stored on `Trigger.wiki_id`.

**`actions.request_id` is globally unique, but handlers are not.** Every handler
writes its own `Action` for the same submission. When a conquest or bingo event
runs alongside a botw event — which is the normal case — the action already
exists by the time this handler runs, and inserting a second one aborts the
transaction and silently drops the score. The handler reuses the existing action
and detects real duplicates by asking whether that action already produced
proofs against *this* event's challenges.

**`challenges.min_quantity_per_action` had no migration.** The column is in the
model and read by the conquest handler, but was only ever added to the deployed
database by hand, so any database built from migrations alone failed every
challenge insert with `UndefinedColumn`. Migration 016 adds it idempotently.

## Data model

### `new_stability.challenge_statuses` (migration)

- Add `player_id UUID NULL REFERENCES public.users(id) ON DELETE CASCADE`.
- Drop `NOT NULL` from `team_id`.
- Drop the `challenge_statuses_unique_team_challenge` constraint. Replace with
  two partial unique indexes:
  - `UNIQUE (team_id, challenge_id) WHERE team_id IS NOT NULL`
  - `UNIQUE (player_id, challenge_id) WHERE player_id IS NOT NULL`
- Add `CHECK ((team_id IS NULL) <> (player_id IS NULL))` — exactly one owner.

Existing rows all have `team_id` and are unaffected. Bingo and conquest query
`filter_by(team_id=...)`, so player-owned rows (where `team_id IS NULL`) never
appear in team results. No change is required in those handlers.

`ChallengeProof` hangs off `challenge_status_id` and works unchanged for
player-owned rows.

### `new_stability.botw_bosses` (new)

| Column | Notes |
| --- | --- |
| `id` | uuid pk |
| `event_id` | → `new_stability.events` ON DELETE CASCADE |
| `name` | Display name and KC trigger name, e.g. `Sol Heredit` |
| `clog_page` | Catalog page the drops came from, e.g. `Fortis Colosseum` |
| `image_url` | Optional banner/icon |
| `display_order` | Ordering on the board |
| `challenge_id` | unique → `new_stability.challenges` ON DELETE SET NULL |
| `created_at` | |

`challenge_id` anchors a container challenge to the event exactly the way
`Territory.challenge_id` does in conquest, so the existing challenge-tree
endpoints (`GET /v2/challenges/<id>/tree`) work without modification.

### Challenge tree per boss

```
container Challenge          task_id=NULL, trigger_id=NULL, quantity=NULL, value=0
├── KC child                 Trigger(name="Duke Sucellus", source="Duke Sucellus", type=KC)
│                            quantity=NULL, value=<kc points>, count_per_action=1
└── drop child × N           Trigger(name="Awakener's orb", source="Duke Sucellus",
                                     type=DROP, wiki_id=<item_id>)
                             quantity=NULL, value=<points>
```

`quantity=NULL` marks a challenge repeatable — it accumulates forever and never
completes, which is what "every drop scores, always" requires. It has to be
written as a SQL `null()` literal: `Challenge.quantity` carries a column default
of 1, and SQLAlchemy applies that default to an attribute explicitly set to
`None`.

Triggers are get-or-create on `(name, source)` so BOTW reuses trigger rows other
events already created rather than duplicating them.

## API

All new routes live in `endpoints/v2/botw.py`.

| Route | Purpose |
| --- | --- |
| `GET /v2/botw/catalog/pages` | The 57 boss pages in the catalog with item counts — feeds the boss picker |
| `POST /v2/events/<event_id>/botw/bosses` | Seed a boss: creates triggers, container, KC challenge, and one challenge per catalog drop |
| `GET /v2/events/<event_id>/botw/bosses` | Bosses with their challenge trees and trigger details |
| `DELETE /v2/botw/bosses/<id>` | Remove a boss and its challenges (statuses cascade) |
| `PUT /v2/botw/bosses/<id>/points` | Bulk point edit: `{challenge_id: value}` |
| `GET /v2/events/<event_id>/botw/leaderboard` | Player standings |

Seeding body: `{name, clog_page, kc_points, drop_points, drop_source?, image_url?}`.
`clog_page` defaults to `name`; `drop_source` defaults to `name`. `drop_points`
is the starting value applied to every generated drop challenge. Seeding rejects
events whose `type` is not `botw`, and rejects a `clog_page` with no rows in
`collection_log_items`.

Single point values can also be edited through the existing
`PUT /v2/challenges/<id>`; the bulk route exists because a boss has 10–40 drops.

Deleting a boss removes its challenge rows with a bulk delete rather than
`session.delete(container)`. The self-referencing children relationship has no
ORM cascade, so deleting the container through the session nullifies
`parent_challenge_id` on its children and leaves them — and their statuses —
orphaned in the table instead of letting the `ON DELETE CASCADE` FKs run.

Leaderboard rows: player id, RSN, total points, and a per-boss breakdown, from
`SUM(challenge_statuses.quantity * challenges.value)` grouped by player.
`challenge_statuses` carries no event id, so the query scopes to the event by
joining challenges to their parent container and on to `botw_bosses.event_id`,
and filters to `player_id IS NOT NULL`. Points
are computed at read time, so correcting a point value mid-event rescales the
whole leaderboard instead of stranding already-awarded scores.

## Handler

New file `event_handlers/botw/botw_event_handler.py` exporting
`botw_event_handler`, registered alongside the legacy `botw_handler` (the names
must differ — both are imported into `event_handler_init.py`). Flow:

1. Find the active `Event` where `type = 'botw'`; return `[]` if none.
2. Resolve the user via the shared rsn → discord_id → alt_names helper.
3. Idempotency: skip if an `Action` already exists with this `request_id`.
4. Record the `Action`.
5. Batch-load the event's bosses, their container challenges, children, and
   triggers.
6. For each leaf challenge: `fnmatch` the trigger name against the submission
   trigger; match source when the trigger has one (empty source = wildcard).
7. On a match, get-or-create the player-owned `ChallengeStatus`
   (`player_id=user.id`, `team_id=NULL`) and increment `quantity` with an atomic
   SQL `UPDATE`, by `count_per_action` when set and `submission.quantity`
   otherwise. Record a `ChallengeProof` linked to the action.
8. Return one Discord notification summarising points earned and the player's
   new total.

There is no team lookup and no enrollment step: any clan member whose submission
matches scores.

## Whitelist

`endpoints/events/item_whitelist.py` gains a BOTW path beside the existing bingo
and conquest paths: collect `botw_bosses.challenge_id` for events in the active
window, load those containers' children, and emit each trigger as `item:source`
into `triggers` (DROP) or the boss name into `killCountTriggers` (KC).

## Refactor folded in

The rsn → discord_id → alt_names user-resolution ladder is duplicated verbatim in
`bingo.py` and `conquest.py` and would become a third copy here. Extract it to a
shared helper and call it from all three.

## Testing

`tests/test_botw.py`:

- Seeding a boss builds the container, one KC challenge with
  `count_per_action=1`, and one challenge per catalog item for that page.
- A KC submission with `quantity=143` awards one kill's worth of points.
- The same drop submitted three times scores three times.
- Player-owned statuses do not appear in team queries, and team scoring for a
  concurrent conquest event is unaffected.
- `/events/whitelist` includes BOTW drop triggers and boss KC names while the
  event is live.
- A drop from a boss that isn't configured is ignored.
