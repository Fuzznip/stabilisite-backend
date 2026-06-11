"""
Adds 3-level hierarchy (root → group → leaf) to 5 territories that have
natural named sub-groups. All other territories stay as flat OR groups.

Affected:
  - Karamja & Asgarnia T1: Bandos or Armadyl  → Armadyl group / Bandos group
  - Karamja & Asgarnia T2: Saradomin or Zamorak → Sara group / Zammy group
  - Morytania T3: Araxxor or GG's              → Araxxor group / GG group
  - Morytania T5: Barrows Unique               → 6 brother groups (4 items each)
  - Varlamore T2: Moons of Peril               → Blood / Blue / Eclipse Moon groups

Resets event progress at the end (challenge_statuses cascade on delete anyway).
"""

import uuid
import psycopg2
import psycopg2.extras

conn = psycopg2.connect(
    host='metro.proxy.rlwy.net', port=18969,
    user='postgres', password='LKQvXMhlGSXmKAXbJrpLbzzVkSnuhdOi',
    database='railway',
)
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

EVENT_ID = '8986ee4e-e5e2-4d55-ad99-b9f26436a14e'


def get_children(root_id):
    cur.execute("""
        SELECT c.id, c.trigger_id, t.name AS trigger_name, t.source AS trigger_source
        FROM new_stability.challenges c
        JOIN new_stability.triggers t ON t.id = c.trigger_id
        WHERE c.parent_challenge_id = %s AND c.trigger_id IS NOT NULL
    """, (root_id,))
    return cur.fetchall()


def delete_flat_children(root_id):
    cur.execute("DELETE FROM new_stability.challenges WHERE parent_challenge_id = %s", (root_id,))
    print(f"    deleted {cur.rowcount} flat children")


def make_group(parent_id):
    gid = str(uuid.uuid4())
    cur.execute("""
        INSERT INTO new_stability.challenges
            (id, event_id, parent_challenge_id, trigger_id, quantity, require_all, count_per_action)
        VALUES (%s, %s, %s, NULL, 1, false, 1)
    """, (gid, EVENT_ID, parent_id))
    return gid


def make_leaf(parent_id, trigger_id):
    cur.execute("""
        INSERT INTO new_stability.challenges
            (id, event_id, parent_challenge_id, trigger_id, quantity, require_all, count_per_action)
        VALUES (%s, %s, %s, %s, 1, false, 1)
    """, (str(uuid.uuid4()), EVENT_ID, parent_id, trigger_id))


# ---------------------------------------------------------------------------
# Karamja & Asgarnia T1: Bandos or Armadyl
# ---------------------------------------------------------------------------
print("Karamja T1: Bandos or Armadyl")
root = 'c5750f03-3b94-42bc-a3cc-eb5a4bb6df11'
children = get_children(root)
armadyl = [c['trigger_id'] for c in children if c['trigger_source'] == "Kree'arra"]
bandos   = [c['trigger_id'] for c in children if c['trigger_source'] == 'General Graardor']
print(f"    Armadyl: {len(armadyl)}, Bandos: {len(bandos)}")
assert len(armadyl) == 5 and len(bandos) == 5, f"unexpected counts: {len(armadyl)}, {len(bandos)}"
delete_flat_children(root)
g = make_group(root)
for tid in armadyl: make_leaf(g, tid)
g = make_group(root)
for tid in bandos: make_leaf(g, tid)

# ---------------------------------------------------------------------------
# Karamja & Asgarnia T2: Saradomin or Zamorak
# ---------------------------------------------------------------------------
print("Karamja T2: Saradomin or Zamorak")
root = '94343e66-4905-40d9-bbd2-7825b43346ea'
children = get_children(root)
sara  = [c['trigger_id'] for c in children if c['trigger_source'] == 'Commander Zilyana']
zammy = [c['trigger_id'] for c in children if c['trigger_source'] == "K'ril Tsutsaroth"]
print(f"    Sara: {len(sara)}, Zammy: {len(zammy)}")
assert len(sara) == 5 and len(zammy) == 5, f"unexpected counts: {len(sara)}, {len(zammy)}"
delete_flat_children(root)
g = make_group(root)
for tid in sara: make_leaf(g, tid)
g = make_group(root)
for tid in zammy: make_leaf(g, tid)

# ---------------------------------------------------------------------------
# Morytania T3: Araxxor or GG's
# Noon's source is 'Skotizo' in DB but it's the GG pet — goes in GG group.
# Granite hammer has no source — also GG.
# ---------------------------------------------------------------------------
print("Morytania T3: Araxxor or GG's")
root = '07eb0e66-b290-4feb-9dfd-91ff14c2d9c2'
children = get_children(root)
araxxor = [c['trigger_id'] for c in children if c['trigger_source'] == 'Araxxor']
gg      = [c['trigger_id'] for c in children if c['trigger_source'] in ('Grotesque Guardians', 'Skotizo', '')]
print(f"    Araxxor: {len(araxxor)}, GG: {len(gg)}")
assert len(araxxor) == 5 and len(gg) == 5, f"unexpected counts: {len(araxxor)}, {len(gg)}"
delete_flat_children(root)
g = make_group(root)
for tid in araxxor: make_leaf(g, tid)
g = make_group(root)
for tid in gg: make_leaf(g, tid)

# ---------------------------------------------------------------------------
# Morytania T5: Barrows Unique — 6 brothers, 4 items each
# ---------------------------------------------------------------------------
print("Morytania T5: Barrows")
root = '41fb5a21-477d-47f7-9afa-2964bbe65f0f'
children = get_children(root)
brothers: dict[str, list] = {}
for c in children:
    prefix = c['trigger_name'].split("'s")[0] + "'s"  # "Ahrim's", "Dharok's", etc.
    brothers.setdefault(prefix, []).append(c['trigger_id'])
print(f"    {', '.join(f'{k}({len(v)})' for k, v in sorted(brothers.items()))}")
assert len(brothers) == 6 and all(len(v) == 4 for v in brothers.values()), \
    f"unexpected brothers: {[(k, len(v)) for k, v in brothers.items()]}"
delete_flat_children(root)
for _brother, tids in sorted(brothers.items()):
    g = make_group(root)
    for tid in tids:
        make_leaf(g, tid)

# ---------------------------------------------------------------------------
# Varlamore T2: Moons of Peril — Blood / Blue / Eclipse moon
# ---------------------------------------------------------------------------
print("Varlamore T2: Moons of Peril")
root = '65c0e6a7-40e7-4c39-a334-c088899210ef'
children = get_children(root)
moons: dict[str, list] = {}
for c in children:
    name = c['trigger_name'].lower()
    if name.startswith('blood moon'):
        key = 'Blood Moon'
    elif name.startswith('blue moon'):
        key = 'Blue Moon'
    elif name.startswith('eclipse moon'):
        key = 'Eclipse Moon'
    else:
        raise ValueError(f"Unexpected moon item: {c['trigger_name']}")
    moons.setdefault(key, []).append(c['trigger_id'])
print(f"    {', '.join(f'{k}({len(v)})' for k, v in sorted(moons.items()))}")
assert set(moons.keys()) == {'Blood Moon', 'Blue Moon', 'Eclipse Moon'}, f"unexpected keys: {moons.keys()}"
delete_flat_children(root)
for moon, tids in sorted(moons.items()):
    g = make_group(root)
    for tid in tids:
        make_leaf(g, tid)

# ---------------------------------------------------------------------------
# Reset event progress
# ---------------------------------------------------------------------------
print("\nResetting event progress...")
cur.execute("DELETE FROM new_stability.event_logs WHERE event_id = %s", (EVENT_ID,))
cur.execute("""
    DELETE FROM new_stability.challenge_statuses
    WHERE team_id IN (SELECT id FROM new_stability.teams WHERE event_id = %s)
""", (EVENT_ID,))
cur.execute("""
    UPDATE new_stability.territories SET controlling_team_id = NULL
    WHERE region_id IN (SELECT id FROM new_stability.regions WHERE event_id = %s)
""", (EVENT_ID,))
cur.execute("""
    UPDATE new_stability.regions SET controlling_team_id = NULL, green_logged_teams = '{}'
    WHERE event_id = %s
""", (EVENT_ID,))
cur.execute("UPDATE new_stability.teams SET points = 0 WHERE event_id = %s", (EVENT_ID,))

conn.commit()
print("Done.")
