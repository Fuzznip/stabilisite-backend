"""
Conquest territory remap script.

Connects directly to the Railway production DB via psycopg2.

Steps:
  1. Create all missing triggers (standard drops only)
  2. Reset all conquest event progress
  3. Rebuild every territory's challenge to match the new spec

Territories left untouched (special triggers, noted at bottom):
  3.5  Penance queen kc      (Kandarin T5)
  4.2  Vorkath points        (Fremennik T2)
  7.3  Gwenith glide laps    (Tirannwn T3)
  7.5  Zalcano points        (Tirannwn T5)
  9.1  Vardorvis points OR Awakener's orb  (Varlamore T1)
  9.5  Hunter rumour completion            (Varlamore T5)
"""

import psycopg2
import psycopg2.extras

conn = psycopg2.connect(
    host='metro.proxy.rlwy.net',
    port=18969,
    user='postgres',
    password='LKQvXMhlGSXmKAXbJrpLbzzVkSnuhdOi',
    database='railway',
)
conn.autocommit = False
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

EVENT_ID = '8986ee4e-e5e2-4d55-ad99-b9f26436a14e'

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_trigger(name, source='', type_='DROP'):
    cur.execute("""
        SELECT id FROM new_stability.triggers
        WHERE lower(name) = lower(%s) AND lower(COALESCE(source,'')) = lower(%s)
    """, (name, source))
    row = cur.fetchone()
    if row:
        return str(row['id'])
    cur.execute("""
        INSERT INTO new_stability.triggers (name, source, type)
        VALUES (%s, %s, %s) RETURNING id
    """, (name, source, type_))
    new_id = cur.fetchone()['id']
    print(f"  + created trigger: {name!r} source={source!r}")
    return str(new_id)


def T(name, source=''):
    cur.execute("""
        SELECT id FROM new_stability.triggers
        WHERE lower(name) = lower(%s) AND lower(COALESCE(source,'')) = lower(%s)
    """, (name, source))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Trigger not found: {name!r} source={source!r}")
    return str(row['id'])


def set_single(territory_id, trigger_id):
    cur.execute("""
        SELECT challenge_id FROM new_stability.territories WHERE id = %s::uuid
    """, (territory_id,))
    row = cur.fetchone()
    if not row or not row['challenge_id']:
        raise ValueError(f"Territory {territory_id} has no challenge_id")
    cur.execute("""
        UPDATE new_stability.challenges
        SET trigger_id = %s::uuid, parent_challenge_id = NULL
        WHERE id = %s::uuid
    """, (trigger_id, str(row['challenge_id'])))


def set_or_group(territory_id, trigger_ids):
    cur.execute("""
        SELECT challenge_id FROM new_stability.territories WHERE id = %s::uuid
    """, (territory_id,))
    old_cid = cur.fetchone()['challenge_id']

    cur.execute("""
        INSERT INTO new_stability.challenges (event_id, require_all, quantity, value)
        VALUES (%s::uuid, false, 1, 1) RETURNING id
    """, (EVENT_ID,))
    parent_id = str(cur.fetchone()['id'])

    for trid in trigger_ids:
        cur.execute("""
            INSERT INTO new_stability.challenges
              (event_id, parent_challenge_id, trigger_id, require_all, quantity, value)
            VALUES (%s::uuid, %s::uuid, %s::uuid, false, 1, 1)
        """, (EVENT_ID, parent_id, trid))

    cur.execute("""
        UPDATE new_stability.territories
        SET challenge_id = %s::uuid
        WHERE id = %s::uuid
    """, (parent_id, territory_id))

    if old_cid:
        cur.execute("""
            DELETE FROM new_stability.challenges WHERE id = %s::uuid
        """, (str(old_cid),))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if True:

    # ===== STEP 1: CREATE MISSING TRIGGERS =====
    print("\n--- Step 1: Creating triggers ---")

    # 1.1 Ancient emblems
    ensure_trigger('Ancient emblem', '')
    ensure_trigger('Ancient totem', '')
    ensure_trigger('Ancient statuette', '')
    ensure_trigger('Ancient medallion', '')
    ensure_trigger('Ancient effigy', '')
    ensure_trigger('Ancient relic', '')
    # 1.2 / 1.3
    ensure_trigger("Larran's key", '')
    ensure_trigger('Dragon pickaxe', '')
    # 1.4 Corp
    ensure_trigger('Holy elixir', 'Corporeal Beast')
    ensure_trigger('Pet dark core', 'Corporeal Beast')
    # 1.5 TDs
    ensure_trigger('Burning claw', 'Tormented Demons')
    # 2.1 Bandos / Armadyl
    ensure_trigger('Bandos tassets', 'General Graardor')
    ensure_trigger('Bandos boots', 'General Graardor')
    ensure_trigger('Pet general graardor', 'General Graardor')
    ensure_trigger('Armadyl chestplate', "Kree'arra")
    ensure_trigger('Armadyl chainskirt', "Kree'arra")
    ensure_trigger("Pet kree'arra", "Kree'arra")
    # 2.2 Sara / Zammy
    ensure_trigger('Saradomin sword', 'Commander Zilyana')
    ensure_trigger("Saradomin's light", 'Commander Zilyana')
    ensure_trigger('Pet zilyana', 'Commander Zilyana')
    ensure_trigger('Zamorakian spear', "K'ril Tsutsaroth")
    ensure_trigger('Steam battlestaff', "K'ril Tsutsaroth")
    ensure_trigger("Pet k'ril tsutsaroth", "K'ril Tsutsaroth")
    # 2.3 Nex
    ensure_trigger('Torva full helm', 'Nex')
    ensure_trigger('Torva platebody', 'Nex')
    ensure_trigger('Torva platelegs', 'Nex')
    # 2.5 Whisperer extras
    ensure_trigger('Virtus mask', 'The Whisperer')
    ensure_trigger('Wisp', 'The Whisperer')
    # 2.5 / 4.4 shared
    ensure_trigger('Chromium ingot', '')
    # 4.4 Duke extras
    ensure_trigger('Virtus robe bottom', 'Duke Sucellus')
    ensure_trigger('Baron', 'Duke Sucellus')
    # 3.4 Infernal
    ensure_trigger('Infernal cape', '')
    # 4.1 Dagannoth rings
    ensure_trigger('Berserker ring', '')
    ensure_trigger("Archer's ring", '')
    ensure_trigger('Seers ring', '')
    ensure_trigger('Warrior ring', '')
    # 5.2 Desert raids
    ensure_trigger("Tumeken's shadow", 'Tombs of Amascut')
    # 5.4 Tempoross (matching existing Dragon harpoon source)
    ensure_trigger('Fish barrel', 'Reward pool (Tempoross)')
    ensure_trigger('Big harpoonfish', 'Reward pool (Tempoross)')
    ensure_trigger('Tackle box', 'Reward pool (Tempoross)')
    # 5.5 GOTR (source unknown — empty matches any)
    ensure_trigger('Abyssal lantern', '')
    ensure_trigger('Abyssal needle', '')
    ensure_trigger('Ring of the elements', '')
    ensure_trigger('Dye talisman', '')
    ensure_trigger('Rift guardian', '')
    ensure_trigger('Lost bag', '')
    ensure_trigger('Catalytic talisman', '')
    # 6.2 TOB
    ensure_trigger('Scythe of vitur', 'Theatre of Blood')
    ensure_trigger('Ghrazi rapier', 'Theatre of Blood')
    ensure_trigger('Sanguinesti staff', 'Theatre of Blood')
    # 7.1 Zulrah
    ensure_trigger('Pet snakeling', 'Zulrah')
    # 7.2 Crystal seeds
    ensure_trigger('Crystal weapon seed', '')
    # 7.4 Crystal teleport seed
    ensure_trigger('Crystal teleport seed', '')
    # 8.2 COX extras
    ensure_trigger('Ancestral robe bottoms', 'Chambers of Xeric')
    ensure_trigger('Twisted ancestral ornament kit', 'Chambers of Xeric')
    # 8.5 Yama
    ensure_trigger('Horn of yama', 'Yama')
    # 9.3 Doom
    ensure_trigger('Cloth of mokhaiotl', 'Doom of Mokhaiotl')
    ensure_trigger('Eye of ayak', 'Doom of Mokhaiotl')

    print("Triggers done.\n")

    # ===== STEP 2: RESET EVENT PROGRESS =====
    print("--- Step 2: Resetting event progress ---")

    cur.execute("DELETE FROM new_stability.event_logs WHERE event_id = %s::uuid", (EVENT_ID,))

    cur.execute("""
        DELETE FROM new_stability.challenge_statuses
        WHERE team_id IN (
            SELECT id FROM new_stability.teams WHERE event_id = %s::uuid
        )
    """, (EVENT_ID,))

    cur.execute("""
        UPDATE new_stability.territories SET controlling_team_id = NULL
        WHERE region_id IN (
            SELECT id FROM new_stability.regions WHERE event_id = %s::uuid
        )
    """, (EVENT_ID,))

    cur.execute("""
        UPDATE new_stability.regions
        SET controlling_team_id = NULL, green_logged_teams = '{}'
        WHERE event_id = %s::uuid
    """, (EVENT_ID,))

    cur.execute("""
        UPDATE new_stability.teams SET points = 0
        WHERE event_id = %s::uuid
    """, (EVENT_ID,))

    print("Reset done.\n")

    # ===== STEP 3: UPDATE TERRITORIES =====
    print("--- Step 3: Remapping territories ---")

    # ---- Region: Misthalin & Wilderness ----
    print("Misthalin & Wilderness...")

    # 1.1 Any Ancient Emblem
    set_or_group('12018118-34ab-4466-913e-6e206ed3ea54', [
        T('Ancient emblem'), T('Ancient totem'), T('Ancient statuette'),
        T('Ancient medallion'), T('Ancient effigy'), T('Ancient relic'),
    ])

    # 1.2 Larran's Key
    set_single('e74039a8-546c-4077-a513-2d39b1cbf56f', T("Larran's key"))

    # 1.3 Dragon Pickaxe
    set_single('bc68967b-1f70-40ef-8670-0ac5109fb717', T('Dragon pickaxe'))

    # 1.4 Corp Beast Unique
    set_or_group('209f87ec-1cdb-4598-9c24-9d908772fa48', [
        T('Arcane sigil', 'Corporeal Beast'),
        T('Spectral sigil', 'Corporeal Beast'),
        T('Elysian sigil', 'Corporeal Beast'),
        T('Holy elixir', 'Corporeal Beast'),
        T('Pet dark core', 'Corporeal Beast'),
    ])

    # 1.5 TD Unique
    set_or_group('307bc7db-409b-4d6e-a7c4-77a6bbcab50b', [
        T('Burning claw', 'Tormented Demons'),
        T('Tormented synapse', 'Tormented Demons'),
    ])

    # ---- Region: Karamja & Asgarnia ----
    print("Karamja & Asgarnia...")

    # 2.1 Bandos or Armadyl Unique
    set_or_group('c3859550-d435-42c0-bb46-517f068d2f6f', [
        T('Bandos chestplate', 'General Graardor'),
        T('Bandos tassets', 'General Graardor'),
        T('Bandos boots', 'General Graardor'),
        T('Bandos hilt', 'General Graardor'),
        T('Pet general graardor', 'General Graardor'),
        T('Armadyl helmet', "Kree'arra"),
        T('Armadyl chestplate', "Kree'arra"),
        T('Armadyl chainskirt', "Kree'arra"),
        T('Armadyl hilt', "Kree'arra"),
        T("Pet kree'arra", "Kree'arra"),
    ])

    # 2.2 Saradomin or Zamorak Unique
    set_or_group('6146558d-e52b-4334-bf65-904ff6120c7b', [
        T('Saradomin sword', 'Commander Zilyana'),
        T("Saradomin's light", 'Commander Zilyana'),
        T('Armadyl crossbow', 'Commander Zilyana'),
        T('Saradomin hilt', 'Commander Zilyana'),
        T('Pet zilyana', 'Commander Zilyana'),
        T('Zamorakian spear', "K'ril Tsutsaroth"),
        T('Staff of the dead', "K'ril Tsutsaroth"),
        T('Steam battlestaff', "K'ril Tsutsaroth"),
        T('Zamorak hilt', "K'ril Tsutsaroth"),
        T("Pet k'ril tsutsaroth", "K'ril Tsutsaroth"),
    ])

    # 2.3 Nex Unique
    set_or_group('218e54fa-78e0-46e6-851f-c58d041edee5', [
        T('Torva full helm', 'Nex'),
        T('Torva platebody', 'Nex'),
        T('Torva platelegs', 'Nex'),
        T('Nihil Horn'),
        T('Zaryte vambraces'),
        T('Ancient hilt'),
        T('Nexling'),
    ])

    # 2.4 Cerberus Unique
    set_or_group('e4cef34d-8ff2-45c3-bbd4-197620add559', [
        T('Primordial crystal', 'Cerberus'),
        T('Pegasian crystal', 'Cerberus'),
        T('Eternal crystal', 'Cerberus'),
        T('Smouldering stone', 'Cerberus'),
        T('Hellpuppy', 'Cerberus'),
        T('Jar of souls', 'Cerberus'),
    ])

    # 2.5 Any Whisperer Unique
    set_or_group('bf3fc6fb-4e77-4e19-819f-fda16620013b', [
        T('Bellator vestige', 'The Whisperer'),
        T('Virtus mask', 'The Whisperer'),
        T('Virtus robe top', 'The Whisperer'),
        T('Virtus robe bottom', 'The Whisperer'),
        T('Chromium ingot'),
        T("Siren's staff", 'The Whisperer'),
        T('Wisp', 'The Whisperer'),
    ])

    # ---- Region: Kandarin ----
    print("Kandarin...")

    # 3.1 Kraken Unique
    set_or_group('cf32cc07-e4b8-4e2c-a2f2-d06cd264c4b6', [
        T('Kraken tentacle', 'Kraken'),
        T('Trident of the seas (full)', 'Kraken'),
        T('Jar of dirt', 'Kraken'),
        T('Pet kraken', 'Kraken'),
    ])

    # 3.2 Thermy Unique
    set_or_group('5825ac0d-2602-4b26-9ed4-c1a6b74e015c', [
        T('Smoke battlestaff', 'Thermonuclear smoke devil'),
        T('Dragon chainbody', 'Thermonuclear smoke devil'),
        T('Occult necklace', 'Thermonuclear smoke devil'),
        T('Pet smoke devil', 'Thermonuclear smoke devil'),
    ])

    # 3.3 Zenyte Shard (single)
    set_single('1acd2926-2444-4446-812f-e2d5256e0d1c', T('Zenyte shard'))

    # 3.4 Infernal Cape (single)
    set_single('738887c8-04b2-4361-bd59-2ec4a571e6e8', T('Infernal cape'))

    # 3.5 SKIP — Penance queen kc

    # ---- Region: Fremennik ----
    print("Fremennik...")

    # 4.1 Dagannoth Ring
    set_or_group('8ed07d87-82e6-426f-b304-ac825b5c6439', [
        T('Berserker ring'),
        T("Archer's ring"),
        T('Seers ring'),
        T('Warrior ring'),
    ])

    # 4.2 SKIP — Vorkath points

    # 4.3 Venator Shard (single)
    set_single('65794647-a015-4546-8cb6-356def89a741', T('Venator shard', 'Phantom Muspah'))

    # 4.4 Duke Unique
    set_or_group('c9d19c0a-5ef7-49a7-93a5-edeb54c57b9b', [
        T('Magus vestige', 'Duke Sucellus'),
        T('Eye of the duke', 'Duke Sucellus'),
        T('Virtus mask', 'Duke Sucellus'),
        T('Virtus robe top', 'Duke Sucellus'),
        T('Virtus robe bottom', 'Duke Sucellus'),
        T('Chromium ingot'),
        T('Baron', 'Duke Sucellus'),
    ])

    # 4.5 Awakener's Orb (single)
    set_single('c8a4cb94-d601-46a7-bf66-b57afc6f860b', T("Awakener's orb"))

    # ---- Region: Desert ----
    print("Desert...")

    # 5.1 Lightbearer or Fang
    set_or_group('69866259-044e-4dc7-96ec-e3144bdbcd26', [
        T('Lightbearer'),
        T("Osmumten's fang"),
    ])

    # 5.2 Masori, Ward or Shadow
    set_or_group('c6b85440-6971-4981-a7f3-a1a159feb6e4', [
        T('Masori mask'),
        T('Masori body'),
        T('Masori chaps'),
        T("Elidinis' ward"),
        T("Tumeken's shadow", 'Tombs of Amascut'),
    ])

    # 5.3 Leviathan Awakener's Orb (single)
    set_single('87483322-526d-4f3f-9ef9-3e53852cdb8e', T("Awakener's orb"))

    # 5.4 Tempoross Unique
    set_or_group('9bd5cef8-b946-46c9-b4f8-cd7a40df67d5', [
        T('Fish barrel', 'Reward pool (Tempoross)'),
        T('Tome of water (empty)'),
        T('Big harpoonfish', 'Reward pool (Tempoross)'),
        T('Tiny tempor'),
        T('Tackle box', 'Reward pool (Tempoross)'),
        T('Dragon harpoon', 'Reward pool (Tempoross)'),
    ])

    # 5.5 GOTR Uniques
    set_or_group('d1cef670-9b25-40a8-aec5-139a4f9bf138', [
        T('Abyssal lantern'),
        T('Abyssal needle'),
        T('Ring of the elements'),
        T('Dye talisman'),
        T('Rift guardian'),
        T('Lost bag'),
        T('Catalytic talisman'),
    ])

    # ---- Region: Morytania ----
    print("Morytania...")

    # 6.1 Avernic Defender Hilt (single)
    set_single('094ed327-b03a-40ac-b4b5-b4f9542b0aff', T('Avernic defender hilt', 'Theatre of Blood'))

    # 6.2 Non-Avernic TOB Drop
    set_or_group('04c2447f-4ce4-41c6-b879-86373ee51d71', [
        T('Scythe of vitur', 'Theatre of Blood'),
        T('Ghrazi rapier', 'Theatre of Blood'),
        T('Sanguinesti staff', 'Theatre of Blood'),
        T('Justiciar faceguard', 'Theatre of Blood'),
        T('Justiciar chestguard'),
        T('Justiciar legguards', 'Theatre of Blood'),
        T("Lil' zik"),
        T('Holy ornament kit'),
        T('Sanguine ornament kit'),
    ])

    # 6.3 Araxxor or GG's Unique (NOT granite maul)
    set_or_group('c5f10fb0-a352-4721-b142-73747fe3b77a', [
        T('Noxious pommel', 'Araxxor'),
        T('Noxious point', 'Araxxor'),
        T('Noxious blade', 'Araxxor'),
        T('Araxyte fang', 'Araxxor'),
        T('Nid', 'Araxxor'),
        T('Granite gloves', 'Grotesque Guardians'),
        T('Granite ring', 'Grotesque Guardians'),
        T('Granite hammer'),
        T('Black tourmaline core', 'Grotesque Guardians'),
        T('Noon', 'Skotizo'),
    ])

    # 6.4 Nightmare or Phosani's Unique
    set_or_group('155b1cab-c283-4512-a996-184faf452731', [
        T("Inquisitor's great helm", "Phosani's Nightmare"),
        T("Inquisitor's hauberk", "Phosani's Nightmare"),
        T("Inquisitor's plateskirt", "Phosani's Nightmare"),
        T('Nightmare staff', "Phosani's Nightmare"),
        T('Volatile orb', "Phosani's Nightmare"),
        T('Harmonised orb', "Phosani's Nightmare"),
        T('Eldritch orb', "Phosani's Nightmare"),
        T('Jar of dreams', 'The Nightmare'),
        T('Little nightmare', "Phosani's Nightmare"),
    ])

    # 6.5 Barrows Unique (all 24 pieces)
    set_or_group('c1c623ce-c596-45ca-b1c2-703e76514431', [
        T("Ahrim's hood", 'Barrows'),
        T("Ahrim's robetop", 'Barrows'),
        T("Ahrim's robeskirt", 'Barrows'),
        T("Ahrim's staff", 'Barrows'),
        T("Dharok's helm", 'Barrows'),
        T("Dharok's platebody", 'Barrows'),
        T("Dharok's platelegs", 'Barrows'),
        T("Dharok's greataxe", 'Barrows'),
        T("Guthan's helm", 'Barrows'),
        T("Guthan's platebody", 'Barrows'),
        T("Guthan's chainskirt", 'Barrows'),
        T("Guthan's warspear", 'Barrows'),
        T("Karil's coif", 'Barrows'),
        T("Karil's leathertop", 'Barrows'),
        T("Karil's leatherskirt", 'Barrows'),
        T("Karil's crossbow", 'Barrows'),
        T("Torag's helm", 'Barrows'),
        T("Torag's platebody", 'Barrows'),
        T("Torag's platelegs", 'Barrows'),
        T("Torag's hammers", 'Barrows'),
        T("Verac's helm", 'Barrows'),
        T("Verac's brassard", 'Barrows'),
        T("Verac's plateskirt", 'Barrows'),
        T("Verac's flail", 'Barrows'),
    ])

    # ---- Region: Tirannwn ----
    print("Tirannwn...")

    # 7.1 Zulrah Unique
    set_or_group('ae99713b-ccc1-479d-8ab9-923ceb256bb8', [
        T('Tanzanite fang', 'Zulrah'),
        T('Magic fang', 'Zulrah'),
        T('Serpentine visage', 'Zulrah'),
        T('Pet snakeling', 'Zulrah'),
        T('Jar of swamp', 'Zulrah'),
    ])

    # 7.2 Crystal Weapon or Armour Seed
    set_or_group('55c93971-0dd2-49d6-b13b-1dc0cd7266ed', [
        T('Crystal weapon seed'),
        T('Crystal armour seed'),
        T('Enhanced crystal weapon seed', 'Corrupted Gauntlet'),
    ])

    # 7.3 SKIP — Gwenith glide laps

    # 7.4 Crystal Teleport Seed (single)
    set_single('cd599563-60b0-416b-a454-3d7bdd6c2ea5', T('Crystal teleport seed'))

    # 7.5 SKIP — Zalcano points

    # ---- Region: Kourend ----
    print("Kourend...")

    # 8.1 COX Prayer Scrolls
    set_or_group('13fb249b-79ee-4897-8fe0-41d7bd63750c', [
        T('Arcane prayer scroll', 'Chambers of Xeric'),
        T('Dexterous prayer scroll', 'Chambers of Xeric'),
    ])

    # 8.2 COX Non Prayer Scrolls
    set_or_group('ca9c49f9-6fd9-4074-bd98-d7e13dd7f8be', [
        T('Twisted bow'),
        T('Kodai insignia', 'Chambers of Xeric'),
        T('Elder maul'),
        T('Dragon claws'),
        T('Twisted buckler', 'Chambers of Xeric'),
        T('Dragon hunter crossbow'),
        T("Dinh's bulwark"),
        T('Ancestral hat', 'Chambers of Xeric'),
        T('Ancestral robe top', 'Chambers of Xeric'),
        T('Ancestral robe bottoms', 'Chambers of Xeric'),
        T('Olmlet'),
        T('Metamorphic dust'),
        T('Twisted ancestral ornament kit', 'Chambers of Xeric'),
    ])

    # 8.3 Molch Stuff
    set_or_group('939417b8-c879-45f6-8fe7-35aa5d92e1f0', [
        T('Molch pearl', 'Untradeable drop: Molch pearl'),
        T('Golden tench', 'The cormorant has brought you a very strange tench.'),
    ])

    # 8.4 Hydra or Unsired
    set_or_group('e76280b5-b905-4c0c-852e-220ef2df02fa', [
        T("Hydra's eye"),
        T("Hydra's fang", 'Alchemical Hydra'),
        T("Hydra's heart"),
        T('Hydra tail', 'Alchemical Hydra'),
        T('Hydra leather', 'Alchemical Hydra'),
        T("Hydra's claw"),
        T('Ikkle hydra', 'Alchemical Hydra'),
        T('Jar of chemicals', 'Alchemical Hydra'),
        T('Unsired', 'Abyssal Sire'),
    ])

    # 8.5 Yama Unique
    set_or_group('38b129ad-c5f3-44cf-8bef-4f92c0832f38', [
        T('Oathplate helm', 'Yama'),
        T('Oathplate chest', 'Yama'),
        T('Oathplate legs', 'Yama'),
        T('Horn of yama', 'Yama'),
        T('Yami', 'Yama'),
    ])

    # ---- Region: Varlamore ----
    print("Varlamore...")

    # 9.1 SKIP — Vardorvis points OR Awakener's orb

    # 9.2 Moons of Peril Unique
    set_or_group('fb473d1c-f3ce-4314-895e-1dafef86305c', [
        T('Blood moon helm', 'Lunar Chest'),
        T('Blood moon chestplate', 'Lunar Chest'),
        T('Blood moon tassets', 'Lunar Chest'),
        T('Blue moon helm', 'Lunar Chest'),
        T('Blue moon chestplate', 'Lunar Chest'),
        T('Blue moon tassets', 'Lunar Chest'),
        T('Blue moon spear', 'Lunar Chest'),
        T('Eclipse moon helm', 'Lunar Chest'),
        T('Eclipse moon chestplate', 'Lunar Chest'),
        T('Eclipse moon tassets', 'Lunar Chest'),
    ])

    # 9.3 Doom Unique
    set_or_group('848f77dc-b98d-4cc0-a4b8-98b9af597aa6', [
        T('Cloth of mokhaiotl', 'Doom of Mokhaiotl'),
        T('Eye of ayak', 'Doom of Mokhaiotl'),
        T('Avernic treads', 'Doom of Mokhaiotl'),
    ])

    # 9.4 Colosseum Unique
    set_or_group('a820f15b-9f11-45f9-ace8-e666b56eeaf0', [
        T('Sunfire fanatic helm'),
        T('Sunfire fanatic cuirass'),
        T('Sunfire fanatic chausses'),
        T('Echo crystal'),
        T('Tonalztics of ralos'),
        T('Smol heredit'),
    ])

    # 9.5 SKIP — Hunter rumour completion

    # ===== COMMIT =====
    conn.commit()
    cur.close()
    conn.close()
    print("\nAll done. Committed.\n")

    print("=" * 60)
    print("SKIPPED territories (special triggers — handle manually):")
    print("  3.5  Kandarin T5       — Penance queen kc")
    print("  4.2  Fremennik T2      — Vorkath points")
    print("  7.3  Tirannwn T3       — Gwenith glide laps")
    print("  7.5  Tirannwn T5       — Zalcano points")
    print("  9.1  Varlamore T1      — Vardorvis points OR Awakener's orb")
    print("  9.5  Varlamore T5      — Hunter rumour completion")
    print("=" * 60)
