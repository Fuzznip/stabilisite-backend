# Manual BOTW boss configuration

**Date:** 2026-08-15
**Status:** Approved, not yet implemented
**Supersedes parts of:** `2026-08-07-boss-of-the-week-design.md`

## Problem

Boss of the week seeds a boss's drop list from the collection log: `seed_boss()`
queries `CollectionLogItem` by `clog_page` and creates one challenge per row.
That coupling costs more than it gives.

- The catalog dictates the drop list. Trimming it to the drops actually worth
  points means creating the boss and then deleting challenges.
- The catalog carries no images, so every seeded trigger lands with
  `img_path = NULL` and the UI falls back to placeholder glyphs.
- Pages are activities, not bosses, so the page name and the name Dink sends
  diverge often enough to need the separate `clog_page` column.
- Tests need a seeded collection log before they can create a boss at all.

Configuration should be stated outright rather than derived.

## Decisions

| Question | Decision |
| --- | --- |
| Keep catalog seeding as an option? | No. Remove it entirely. |
| Edit the drop list after creation? | Yes — per-drop add and remove endpoints. |
| Validate hand-typed item names? | No validation. |
| Shape of the boss PUT | Generic: any model field. |
| Default `source` on triggers | None. Triggers are created sourceless. |

## API

| Endpoint | Change |
| --- | --- |
| `POST /v2/events/<event_id>/botw/bosses` | Rewritten — explicit `drops` array |
| `PUT /v2/botw/bosses/<boss_id>` | New — generic field update |
| `POST /v2/botw/bosses/<boss_id>/drops` | New — add one drop |
| `DELETE /v2/botw/drops/<challenge_id>` | New — remove one drop |
| `PUT /v2/botw/bosses/<boss_id>/points` | Unchanged |
| `DELETE /v2/botw/bosses/<boss_id>` | Unchanged |
| `GET /v2/botw/catalog/pages` | Deleted |

### Creating a boss

```json
{
  "name": "Vardorvis",
  "image_url": "https://…/vardorvis.png",
  "kc_points": 2,
  "drop_points": 15,
  "display_order": 1,
  "drops": [
    {"name": "Butch", "points": 60, "img_path": "https://…/butch.png"},
    {"name": "Ultor vestige", "points": 40},
    {"name": "Awakener's orb"}
  ]
}
```

`name` is required; everything else is optional. `drop_points` supplies the
value for any drop omitting `points`, so a flat-rate boss stays terse.
`img_path` writes to `Trigger.img_path` — the field the leaderboard and boss
cards read for icons, so icons are set at creation rather than backfilled.

An empty or absent `drops` list is legal and produces a KC-only boss. The
current code raises `ValueError` when a page yields no rows; with manual entry a
KC-only week is a real configuration, not an error.

### Generic boss update

`PUT /v2/botw/bosses/<boss_id>` delegates to `CRUDService.update`, matching
`PUT /v2/events/<id>`. That helper already skips `id` and `created_at` and
ignores keys absent from the model, so no extra filtering is added.

`PUT .../points` stays. Point values live on `Challenge` rows, not on
`BotwBoss`, so a generic model update cannot reach them.

**Risk accepted:** the generic update can set `challenge_id`. Pointing it at the
wrong container orphans the boss's whole challenge tree — its KC and drops
become unreachable and the leaderboard join stops matching. Same exposure
`PUT /v2/events/<id>` already carries. Flagged, not guarded.

### Adding and removing drops

`POST /v2/botw/bosses/<boss_id>/drops` takes `{name, points, img_path?, source?}`
and appends one challenge to the boss's container.

`DELETE /v2/botw/drops/<challenge_id>` removes one. It must first confirm the
challenge's parent is a BOTW boss container, so the route cannot delete
arbitrary challenges. Deleting cascades the drop's `challenge_statuses`, so
players lose points earned on it — correct, but destructive, and noted in the
docstring.

## Service

`seed_boss()` becomes `create_boss()`. The `CollectionLogItem` import and query
go; the function builds the same tree — container → KC + one child per drop —
from the supplied list. `catalog_pages()` is deleted with its endpoint.

### Triggers are created without a source

`get_or_create_trigger` no longer defaults `source` to the boss name. KC and
drop triggers are created with `source = None` unless a payload supplies one
explicitly. The boss-level `drop_source` default is removed.

This changes matching. The handler computes:

```python
source_match = (not trigger_source_lower) or (trigger_source_lower == submission_source_lower)
```

A sourceless trigger matches **any** submission source, so matching is by item
name alone. Consequences:

- Submissions no longer need a correct `source` to score. Today a KC submission
  with `source: null` silently records nothing.
- A drop shared between bosses scores wherever it is configured. An
  `Awakener's orb` from Duke Sucellus will score on a Vardorvis drop challenge.
  Intended: a BOTW week is usually themed around a boss group.
- `triggers_unique_name_source` does not dedupe NULL sources, since Postgres
  treats NULLs as distinct. `get_or_create_trigger` still finds existing rows —
  `filter_by(source=None)` emits `IS NULL` — so duplicates arise only from
  concurrent creation of the same name. Accepted.
- Triggers already seeded *with* a source are not reused. New sourceless rows
  are created alongside them.

`img_path` is backfilled onto an existing trigger only when it is null,
mirroring the existing `wiki_id` treatment. Triggers are global, so overwriting
one event's icon from another event's payload would be wrong.

Names are matched with `fnmatch`, so manual entry can use wildcards —
`Virtus*` covers the mask and both robe pieces in one challenge.

## Schema

New alembic migration dropping `botw_bosses.clog_page`, currently `NOT NULL`.
Safe: production has no BOTW tables, and local holds a single row. The model
docstring loses its `clog_page` paragraph.

## Errors

400 on: missing `name`; `drops` not a list; a drop missing `name`; non-integer
points. 404 on unknown boss or drop. 400 when the event is not `type = 'botw'`,
as today.

No item-name validation. A name that does not match what Dink sends simply never
scores.

## Testing

`tests/test_botw.py` currently seeds from `PAGE = "Duke Sucellus"` and asserts
the children match the catalog exactly. Those cases are rewritten against
explicit drop lists, which also makes the suite hermetic — it no longer needs a
seeded collection log.

New cases:

- create a boss with an explicit drop list
- create a KC-only boss from an empty `drops` list
- `drop_points` fills in for drops omitting `points`
- add a drop, then score it
- delete a drop; confirm its statuses go and the other drops' scores survive
- delete rejects a challenge that is not a BOTW drop
- generic PUT updates `name` and `display_order`
- a submission with no `source` scores against a sourceless trigger

## Downstream

`clog_page: string` in the frontend's `src/lib/types/v2.tsx` must go once the
API stops returning it.
