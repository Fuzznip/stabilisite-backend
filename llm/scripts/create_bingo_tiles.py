import subprocess
import json

BASE_URL = "http://localhost:8000"
EVENT_ID = "f73a21d2-2644-410b-b037-c0e99b375a68"

# Track created triggers to avoid duplicates
triggers_cache = {}

def curl_post(url, data):
    """Make a POST request using curl"""
    result = subprocess.run(
        ['curl', '-s', '-X', 'POST', url, '-H', 'Content-Type: application/json', '-d', json.dumps(data)],
        capture_output=True,
        text=True
    )
    if result.returncode == 0 and result.stdout:
        try:
            return json.loads(result.stdout)
        except:
            return None
    return None

def get_or_create_trigger(name, trigger_type, source=None):
    """Get or create a trigger, caching to avoid duplicates"""
    cache_key = f"{name}|{source or 'NULL'}|{trigger_type}"

    if cache_key in triggers_cache:
        return triggers_cache[cache_key]

    # Create new trigger (simplified - not checking for existing)
    trigger_data = {
        "name": name,
        "type": trigger_type
    }
    if source:
        trigger_data["source"] = source

    trigger = curl_post(f"{BASE_URL}/v2/triggers", trigger_data)
    if trigger and trigger.get("id"):
        triggers_cache[cache_key] = trigger["id"]
        return trigger["id"]
    else:
        print(f"Failed to create trigger {name}")
        return None

def create_tile(index, name):
    """Create a tile"""
    tile_data = {
        "event_id": EVENT_ID,
        "name": name,
        "index": index,
        "img_src": f"https://stability-event.s3.us-east-1.amazonaws.com/{index}.png"
    }
    return curl_post(f"{BASE_URL}/v2/tiles", tile_data)

def create_task(tile_id, name, require_all=False):
    """Create a task"""
    task_data = {
        "tile_id": tile_id,
        "name": name,
        "require_all": require_all
    }
    return curl_post(f"{BASE_URL}/v2/tasks", task_data)

def create_challenge(task_id, trigger_id, quantity=1, parent_challenge_id=None, require_all=False):
    """Create a challenge"""
    challenge_data = {
        "task_id": task_id,
        "trigger_id": trigger_id,
        "quantity": quantity,
        "require_all": require_all
    }
    if parent_challenge_id:
        challenge_data["parent_challenge_id"] = parent_challenge_id

    return curl_post(f"{BASE_URL}/v2/challenges", challenge_data)

# Tile definitions
tiles = [
    {
        "index": 0,
        "name": "COX KC",
        "tasks": [
            {"name": "100 KC", "challenges": [{"trigger": "Chambers of Xeric", "type": "KC", "quantity": 100}]},
            {"name": "150 KC", "challenges": [{"trigger": "Chambers of Xeric", "type": "KC", "quantity": 150}]},
            {"name": "200 KC", "challenges": [{"trigger": "Chambers of Xeric", "type": "KC", "quantity": 200}]}
        ]
    },
    {
        "index": 1,
        "name": "Slayer Unique Tile",
        "tasks": [
            {"name": "8 Slayer Unique Points", "challenges": [{"trigger": "Slayer Unique", "type": "DROP", "quantity": 8}]},
            {"name": "16 Slayer Unique Points", "challenges": [{"trigger": "Slayer Unique", "type": "DROP", "quantity": 16}]},
            {"name": "24 Slayer Unique Points", "challenges": [{"trigger": "Slayer Unique", "type": "DROP", "quantity": 24}]}
        ]
    },
    {
        "index": 2,
        "name": "Ahoy Sailor!",
        "tasks": [
            {"name": "Rare salvage drop", "challenges": [{"trigger": "Rare salvage", "type": "DROP", "quantity": 1}]},
            {"name": "Tradeable Boat Paint or Pet", "require_all": False, "challenges": [
                {"trigger": "Barracuda paint", "type": "DROP", "quantity": 1},
                {"trigger": "Inky paint", "type": "DROP", "quantity": 1},
                {"trigger": "Salvors paint", "type": "DROP", "quantity": 1},
                {"trigger": "Anglers paint", "type": "DROP", "quantity": 1},
                {"trigger": "Sailing pet", "type": "DROP", "quantity": 1}
            ]},
            {"name": "Rare Sailing Miscellaneous", "require_all": False, "challenges": [
                {"trigger": "Echo pearl", "type": "DROP", "quantity": 1},
                {"trigger": "Broken Dragon Hook", "type": "DROP", "quantity": 1},
                {"trigger": "Bottled Storm", "type": "DROP", "quantity": 1},
                {"trigger": "Dragon Cannon Barrel", "type": "DROP", "quantity": 1}
            ]}
        ]
    },
    {
        "index": 3,
        "name": "Ironman Pun Here",
        "tasks": [
            {"name": "CG (2x armor or enhanced)", "require_all": False, "challenges": [
                {"trigger": "Crystal armor seed", "type": "DROP", "source": "Corrupted Gauntlet", "quantity": 2},
                {"trigger": "Enhanced crystal weapon seed", "type": "DROP", "source": "Corrupted Gauntlet", "quantity": 1}
            ]},
            {"name": "8 moons uniques", "challenges": [{"trigger": "Moons unique", "type": "DROP", "quantity": 8}]},
            {"name": "Full Barrows Set", "challenges": [{"trigger": "Full Barrows Set", "type": "DROP", "quantity": 1}]}
        ]
    },
    {
        "index": 4,
        "name": "Glow-ee Hole",
        "tasks": [
            {"name": "1 Doom Unique", "challenges": [{"trigger": "Doom unique", "type": "DROP", "quantity": 1}]},
            {"name": "3 Doom Uniques", "challenges": [{"trigger": "Doom unique", "type": "DROP", "quantity": 3}]},
            {"name": "5 Doom Uniques", "challenges": [{"trigger": "Doom unique", "type": "DROP", "quantity": 5}]}
        ]
    },
    {
        "index": 5,
        "name": "Icy Adventure",
        "tasks": [
            {"name": "600 Amoxilatl KC or Pet", "require_all": False, "challenges": [
                {"trigger": "Amoxliatl", "type": "KC", "quantity": 600},
                {"trigger": "Amoxliatl pet", "type": "DROP", "quantity": 1}
            ]},
            {"name": "2x Venator Shards", "challenges": [{"trigger": "Venator shard", "type": "DROP", "quantity": 2}]},
            {"name": "25 Dragon Metal Sheets", "challenges": [{"trigger": "Dragon metal shard", "type": "DROP", "quantity": 25}]}
        ]
    },
    {
        "index": 6,
        "name": "COX 1",
        "tasks": [
            {"name": "3x Dex/Arcane", "require_all": False, "challenges": [
                {"trigger": "Dexterous prayer scroll", "type": "DROP", "source": "Chambers of Xeric", "quantity": 3},
                {"trigger": "Arcane prayer scroll", "type": "DROP", "source": "Chambers of Xeric", "quantity": 3}
            ]},
            {"name": "Ancy or TBOW", "require_all": False, "challenges": [
                {"trigger": "Twisted ancestral colour kit", "type": "DROP", "source": "Chambers of Xeric", "quantity": 1},
                {"trigger": "Twisted bow", "type": "DROP", "source": "Chambers of Xeric", "quantity": 1}
            ]},
            {"name": "CM Kit/Dust/Pet", "require_all": False, "challenges": [
                {"trigger": "Metamorphic dust", "type": "DROP", "source": "Chambers of Xeric", "quantity": 1},
                {"trigger": "Olmlet", "type": "DROP", "source": "Chambers of Xeric", "quantity": 1}
            ]}
        ]
    },
    {
        "index": 7,
        "name": "(Slayer) Level Up: Completed.",
        "tasks": [
            {"name": "1 mil Slayer XP", "challenges": [{"trigger": "Slayer", "type": "SKILL", "quantity": 1000000}]},
            {"name": "3 mil Slayer XP", "challenges": [{"trigger": "Slayer", "type": "SKILL", "quantity": 3000000}]},
            {"name": "5 mil Slayer XP", "challenges": [{"trigger": "Slayer", "type": "SKILL", "quantity": 5000000}]}
        ]
    },
    {
        "index": 8,
        "name": "GWD 1",
        "tasks": [
            {"name": "Bandos Chestplate", "challenges": [{"trigger": "Bandos chestplate", "type": "DROP", "source": "General Graardor", "quantity": 1}]},
            {"name": "Armadyl Helmet", "challenges": [{"trigger": "Armadyl helmet", "type": "DROP", "source": "Kree'arra", "quantity": 1}]},
            {"name": "Full Godsword", "challenges": [{"trigger": "Godsword blade", "type": "DROP", "quantity": 1}]}
        ]
    },
    {
        "index": 9,
        "name": "TOA KC",
        "tasks": [
            {"name": "100 KC", "challenges": [{"trigger": "Tombs of Amascut", "type": "KC", "quantity": 100}]},
            {"name": "150 KC", "challenges": [{"trigger": "Tombs of Amascut", "type": "KC", "quantity": 150}]},
            {"name": "200 KC", "challenges": [{"trigger": "Tombs of Amascut", "type": "KC", "quantity": 200}]}
        ]
    },
    {
        "index": 10,
        "name": "TOA 1",
        "tasks": [
            {"name": "2x LB", "challenges": [{"trigger": "Lightbearer", "type": "DROP", "source": "Tombs of Amascut", "quantity": 2}]},
            {"name": "2x Fang or 1x Shadow", "require_all": False, "challenges": [
                {"trigger": "Osmumten's fang", "type": "DROP", "source": "Tombs of Amascut", "quantity": 2},
                {"trigger": "Tumeken's shadow", "type": "DROP", "source": "Tombs of Amascut", "quantity": 1}
            ]},
            {"name": "Full Masori/3x Ward/Pet", "require_all": False, "challenges": [
                {"trigger": "Masori body", "type": "DROP", "source": "Tombs of Amascut", "quantity": 1},
                {"trigger": "Elidinis' ward", "type": "DROP", "source": "Tombs of Amascut", "quantity": 3},
                {"trigger": "Tumeken's guardian", "type": "DROP", "source": "Tombs of Amascut", "quantity": 1}
            ]}
        ]
    },
    {
        "index": 11,
        "name": "Slayer Skipping Sucks",
        "tasks": [
            {"name": "Gryphon Unique", "require_all": False, "challenges": [
                {"trigger": "Belle's folly", "type": "DROP", "quantity": 1},
                {"trigger": "Horn of plenty", "type": "DROP", "quantity": 1}
            ]},
            {"name": "3x Brimstone ring pieces", "challenges": [{"trigger": "Brimstone key", "type": "DROP", "quantity": 3}]},
            {"name": "2 Boss Jars", "challenges": [{"trigger": "Boss jar", "type": "DROP", "quantity": 2}]}
        ]
    },
    {
        "index": 12,
        "name": "PVM Daily Challenge 1",
        "tasks": [
            {"name": "Complete Daily Challenge", "challenges": [{"trigger": "Daily Challenge", "type": "ACHIEVEMENT", "quantity": 1}]},
            {"name": "Complete 3 Daily Challenges", "challenges": [{"trigger": "Daily Challenge", "type": "ACHIEVEMENT", "quantity": 3}]},
            {"name": "Complete 5 Daily Challenges", "challenges": [{"trigger": "Daily Challenge", "type": "ACHIEVEMENT", "quantity": 5}]}
        ]
    },
    {
        "index": 13,
        "name": "Scaly Surprise",
        "tasks": [
            {"name": "Tanzanite Fang", "challenges": [{"trigger": "Tanzanite fang", "type": "DROP", "source": "Zulrah", "quantity": 1}]},
            {"name": "Vorkath Unique", "require_all": False, "challenges": [
                {"trigger": "Draconic visage", "type": "DROP", "source": "Vorkath", "quantity": 1},
                {"trigger": "Jar of decay", "type": "DROP", "source": "Vorkath", "quantity": 1},
                {"trigger": "Dragonbone necklace", "type": "DROP", "source": "Vorkath", "quantity": 1},
                {"trigger": "Vorki", "type": "DROP", "source": "Vorkath", "quantity": 1}
            ]},
            {"name": "Corp Sigil OR Warhammer", "require_all": False, "challenges": [
                {"trigger": "Arcane sigil", "type": "DROP", "source": "Corporeal Beast", "quantity": 1},
                {"trigger": "Elysian sigil", "type": "DROP", "source": "Corporeal Beast", "quantity": 1},
                {"trigger": "Spectral sigil", "type": "DROP", "source": "Corporeal Beast", "quantity": 1},
                {"trigger": "Dragon warhammer", "type": "DROP", "quantity": 1}
            ]}
        ]
    },
    {
        "index": 14,
        "name": "GWD 2",
        "tasks": [
            {"name": "Staff of the Dead", "challenges": [{"trigger": "Staff of the dead", "type": "DROP", "source": "K'ril Tsutsaroth", "quantity": 1}]},
            {"name": "Armadyl Crossbow", "challenges": [{"trigger": "Armadyl crossbow", "type": "DROP", "source": "Kree'arra", "quantity": 1}]},
            {"name": "3x of any Hilt", "require_all": False, "challenges": [
                {"trigger": "Armadyl hilt", "type": "DROP", "quantity": 3},
                {"trigger": "Bandos hilt", "type": "DROP", "quantity": 3},
                {"trigger": "Saradomin hilt", "type": "DROP", "quantity": 3},
                {"trigger": "Zamorak hilt", "type": "DROP", "quantity": 3}
            ]}
        ]
    },
    {
        "index": 15,
        "name": "Nex",
        "tasks": [
            {"name": "60 nihil shards", "challenges": [{"trigger": "Nihil shard", "type": "DROP", "source": "Nex", "quantity": 60}]},
            {"name": "Nex unique", "require_all": False, "challenges": [
                {"trigger": "Zaryte crossbow", "type": "DROP", "source": "Nex", "quantity": 1},
                {"trigger": "Torva full helm", "type": "DROP", "source": "Nex", "quantity": 1},
                {"trigger": "Torva platebody", "type": "DROP", "source": "Nex", "quantity": 1},
                {"trigger": "Torva platelegs", "type": "DROP", "source": "Nex", "quantity": 1}
            ]},
            {"name": "2 Nex Uniques", "require_all": False, "challenges": [
                {"trigger": "Zaryte crossbow", "type": "DROP", "source": "Nex", "quantity": 2},
                {"trigger": "Torva full helm", "type": "DROP", "source": "Nex", "quantity": 2},
                {"trigger": "Torva platebody", "type": "DROP", "source": "Nex", "quantity": 2},
                {"trigger": "Torva platelegs", "type": "DROP", "source": "Nex", "quantity": 2}
            ]}
        ]
    },
    {
        "index": 16,
        "name": "We Want AFK TILE",
        "tasks": [
            {"name": "Mining XP or pet", "require_all": False, "challenges": [
                {"trigger": "Mining", "type": "SKILL", "quantity": 1000000},
                {"trigger": "Rock golem", "type": "DROP", "quantity": 1}
            ]},
            {"name": "Woodcutting XP or pet", "require_all": False, "challenges": [
                {"trigger": "Woodcutting", "type": "SKILL", "quantity": 1000000},
                {"trigger": "Beaver", "type": "DROP", "quantity": 1}
            ]},
            {"name": "Sailing XP", "challenges": [{"trigger": "Sailing", "type": "SKILL", "quantity": 1000000}]}
        ]
    },
    {
        "index": 17,
        "name": "TOB KC",
        "tasks": [
            {"name": "100 KC", "challenges": [{"trigger": "Theatre of Blood", "type": "KC", "quantity": 100}]},
            {"name": "150 KC", "challenges": [{"trigger": "Theatre of Blood", "type": "KC", "quantity": 150}]},
            {"name": "200 KC", "challenges": [{"trigger": "Theatre of Blood", "type": "KC", "quantity": 200}]}
        ]
    },
    {
        "index": 18,
        "name": "Skillers Unite!",
        "tasks": [
            {"name": "Golden Tench or 200 Pearls", "require_all": False, "challenges": [
                {"trigger": "Golden tench", "type": "DROP", "quantity": 1},
                {"trigger": "Pearl", "type": "DROP", "quantity": 200}
            ]},
            {"name": "Vale Totems", "challenges": [{"trigger": "Vale totem", "type": "DROP", "quantity": 10}]},
            {"name": "Tome of Water or Pet or Harpoon", "require_all": False, "challenges": [
                {"trigger": "Tome of water", "type": "DROP", "quantity": 1},
                {"trigger": "Tempoross pet", "type": "DROP", "quantity": 1},
                {"trigger": "Dragon harpoon", "type": "DROP", "source": "Tempoross", "quantity": 1}
            ]}
        ]
    },
    {
        "index": 19,
        "name": "Yama",
        "tasks": [
            {"name": "500 KC", "challenges": [{"trigger": "Hueycoatl", "type": "KC", "quantity": 500}]},
            {"name": "Oathplate Piece", "challenges": [{"trigger": "Sunfire splinter", "type": "DROP", "source": "Hueycoatl", "quantity": 1}]},
            {"name": "Horn or Pet", "require_all": False, "challenges": [
                {"trigger": "Huey's horn", "type": "DROP", "source": "Hueycoatl", "quantity": 1},
                {"trigger": "Hueycoatl pet", "type": "DROP", "source": "Hueycoatl", "quantity": 1}
            ]}
        ]
    },
    {
        "index": 20,
        "name": "Colo",
        "tasks": [
            {"name": "3 Echo Crystals", "challenges": [{"trigger": "Echo crystal", "type": "DROP", "source": "Colosseum", "quantity": 3}]},
            {"name": "3x sunfire (aka full)", "challenges": [{"trigger": "Sunfire splinter", "type": "DROP", "source": "Colosseum", "quantity": 3}]},
            {"name": "2x uncut onyxites or Ralos", "require_all": False, "challenges": [
                {"trigger": "Uncut onyx", "type": "DROP", "source": "Colosseum", "quantity": 2},
                {"trigger": "Tonalztics of ralos", "type": "DROP", "source": "Colosseum", "quantity": 1}
            ]}
        ]
    },
    {
        "index": 21,
        "name": "DT2",
        "tasks": [
            {"name": "10 Awakener's ORBS", "challenges": [{"trigger": "Awakener's orb", "type": "DROP", "quantity": 10}]},
            {"name": "4 Ring Rolls", "challenges": [{"trigger": "Ring roll", "type": "DROP", "quantity": 4}]},
            {"name": "3 SR Axe Pieces OR Full Virtus", "require_all": False, "challenges": [
                {"trigger": "Soulreaper axe piece", "type": "DROP", "quantity": 3},
                {"trigger": "Virtus robe top", "type": "DROP", "quantity": 1}
            ]}
        ]
    },
    {
        "index": 22,
        "name": "MASS MODE",
        "tasks": [
            {"name": "Nightmare Mass KC", "challenges": [{"trigger": "The Nightmare", "type": "KC", "quantity": 50}]},
            {"name": "Callisto Mass KC", "challenges": [{"trigger": "Callisto", "type": "KC", "quantity": 50}]},
            {"name": "Corp Mass KC", "challenges": [{"trigger": "Corporeal Beast", "type": "KC", "quantity": 50}]}
        ]
    },
    {
        "index": 23,
        "name": "TOB 1",
        "tasks": [
            {"name": "2x avernic", "challenges": [{"trigger": "Avernic defender hilt", "type": "DROP", "source": "Theatre of Blood", "quantity": 2}]},
            {"name": "3x Justiciar or Scythe", "require_all": False, "challenges": [
                {"trigger": "Justiciar faceguard", "type": "DROP", "source": "Theatre of Blood", "quantity": 3},
                {"trigger": "Scythe of vitur", "type": "DROP", "source": "Theatre of Blood", "quantity": 1}
            ]},
            {"name": "HMT kit/dust/pet", "require_all": False, "challenges": [
                {"trigger": "Sanguine ornament kit", "type": "DROP", "source": "Theatre of Blood", "quantity": 1},
                {"trigger": "Sanguine dust", "type": "DROP", "source": "Theatre of Blood", "quantity": 1},
                {"trigger": "Lil' zik", "type": "DROP", "source": "Theatre of Blood", "quantity": 1}
            ]}
        ]
    },
    {
        "index": 24,
        "name": "Leftovers are good too",
        "tasks": [
            {"name": "Tormented synapse", "challenges": [{"trigger": "Tormented synapse", "type": "DROP", "quantity": 1}]},
            {"name": "Phosani Unique", "require_all": False, "challenges": [
                {"trigger": "Inquisitor's great helm", "type": "DROP", "source": "Phosani's Nightmare", "quantity": 1},
                {"trigger": "Inquisitor's hauberk", "type": "DROP", "source": "Phosani's Nightmare", "quantity": 1},
                {"trigger": "Inquisitor's plateskirt", "type": "DROP", "source": "Phosani's Nightmare", "quantity": 1},
                {"trigger": "Nightmare staff", "type": "DROP", "source": "Phosani's Nightmare", "quantity": 1}
            ]},
            {"name": "3x Zenyte Shards", "challenges": [{"trigger": "Zenyte shard", "type": "DROP", "quantity": 3}]}
        ]
    }
]

def main():
    print("Creating tiles only (no tasks or challenges)...")

    created = 0
    failed = 0

    for tile_def in tiles:
        print(f"\nCreating Tile #{tile_def['index']}: {tile_def['name']}")

        # Create tile
        tile = create_tile(tile_def['index'], tile_def['name'])
        if not tile:
            print(f"  ✗ Failed to create tile {tile_def['name']}")
            failed += 1
            continue

        print(f"  ✓ Created tile: {tile['id']}")
        created += 1

    print(f"\n{'='*60}")
    print(f"Summary: {created} tiles created, {failed} failed")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
