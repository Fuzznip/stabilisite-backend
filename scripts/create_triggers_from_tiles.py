import subprocess
import json
import time

BASE_URL = "http://localhost:8000"
WIKI_API_URL = "http://localhost:3000/api/items/search"

def curl_get(url):
    """Make a GET request using curl"""
    result = subprocess.run(
        ['curl', '-s', url],
        capture_output=True,
        text=True
    )
    if result.returncode == 0 and result.stdout:
        try:
            return json.loads(result.stdout)
        except:
            return None
    return None

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

def get_wiki_data(item_name):
    """Fetch wiki_id and image from the wiki API"""
    url = f"{WIKI_API_URL}?name={item_name}"
    data = curl_get(url)

    if data and isinstance(data, list) and len(data) > 0:
        item = data[0]  # Take first result
        return {
            'wiki_id': item.get('id'),
            'img_path': item.get('image')
        }
    return None

def create_trigger(name, trigger_type, source=None, skip_wiki=False):
    """Create a trigger with wiki data"""
    trigger_data = {
        "name": name,
        "type": trigger_type
    }

    if source:
        trigger_data["source"] = source

    # Get wiki data unless skipped
    if not skip_wiki:
        print(f"  Looking up wiki data for: {name}")
        wiki_data = get_wiki_data(name)
        if wiki_data:
            if wiki_data['wiki_id']:
                trigger_data['wiki_id'] = wiki_data['wiki_id']
            if wiki_data['img_path']:
                trigger_data['img_path'] = wiki_data['img_path']
            print(f"    ✓ Found wiki_id: {wiki_data.get('wiki_id')}, img_path: {wiki_data.get('img_path')}")
        else:
            print(f"    ⚠ No wiki data found for {name}")

        # Small delay to avoid overwhelming the API
        time.sleep(0.1)

    # Create trigger
    trigger = curl_post(f"{BASE_URL}/v2/triggers", trigger_data)
    if trigger and trigger.get("id"):
        print(f"  ✓ Created trigger: {name} (type: {trigger_type}, source: {source or 'N/A'})")
        return trigger["id"]
    else:
        print(f"  ✗ Failed to create trigger: {name} - {trigger}")
        return None

# All unique triggers extracted from create_bingo_tiles.py
# Format: (name, type, source, skip_wiki)
triggers = [
    # KC Triggers - use boss/raid name for image
    ("Chambers of Xeric", "KC", None, False),
    ("Tombs of Amascut", "KC", None, False),
    ("Theatre of Blood", "KC", None, False),
    ("Amoxliatl", "KC", None, False),
    ("Hueycoatl", "KC", None, False),
    ("The Nightmare", "KC", None, False),
    ("Callisto", "KC", None, False),
    ("Corporeal Beast", "KC", None, False),

    # Skill XP Triggers - skip wiki
    ("Slayer", "XP", None, True),
    ("Mining", "XP", None, True),
    ("Woodcutting", "XP", None, True),
    ("Sailing", "XP", None, True),

    # Special/Abstract Triggers - will need manual handling
    ("Slayer Unique", "DROP", None, True),  # Will be tracked via actual slayer drops
    ("Moons unique", "DROP", None, True),  # Any moons of peril unique
    ("Doom unique", "DROP", None, True),  # Any doom of mokhaiotl unique
    ("Boss jar", "DROP", None, True),  # Any boss jar
    ("Ring roll", "DROP", None, True),  # DT2 vestige/ring
    ("Soulreaper axe piece", "DROP", None, True),  # Any SR axe piece
    ("Daily Challenge", "UNIQUE", None, True),  # Changed from ACHIEVEMENT per your note

    # Sailing Drops
    ("Rare salvage", "DROP", None, False),
    ("Barracuda paint", "DROP", None, False),
    ("Inky paint", "DROP", None, False),
    ("Salvors paint", "DROP", None, False),
    ("Anglers paint", "DROP", None, False),
    ("Sailing pet", "DROP", None, False),
    ("Echo pearl", "DROP", None, False),
    ("Broken Dragon Hook", "DROP", None, False),
    ("Bottled Storm", "DROP", None, False),
    ("Dragon Cannon Barrel", "DROP", None, False),

    # Corrupted Gauntlet
    ("Crystal armor seed", "DROP", "Corrupted Gauntlet", False),
    ("Enhanced crystal weapon seed", "DROP", "Corrupted Gauntlet", False),

    # Full Barrows Set - individual pieces
    ("Ahrim's hood", "DROP", "Barrows", False),
    ("Ahrim's robetop", "DROP", "Barrows", False),
    ("Ahrim's robeskirt", "DROP", "Barrows", False),
    ("Ahrim's staff", "DROP", "Barrows", False),
    ("Torag's helm", "DROP", "Barrows", False),
    ("Torag's platebody", "DROP", "Barrows", False),
    ("Torag's platelegs", "DROP", "Barrows", False),
    ("Torag's hammers", "DROP", "Barrows", False),
    ("Verac's helm", "DROP", "Barrows", False),
    ("Verac's brassard", "DROP", "Barrows", False),
    ("Verac's plateskirt", "DROP", "Barrows", False),
    ("Verac's flail", "DROP", "Barrows", False),
    ("Guthan's helm", "DROP", "Barrows", False),
    ("Guthan's platebody", "DROP", "Barrows", False),
    ("Guthan's chainskirt", "DROP", "Barrows", False),
    ("Guthan's warspear", "DROP", "Barrows", False),
    ("Dharok's helm", "DROP", "Barrows", False),
    ("Dharok's platebody", "DROP", "Barrows", False),
    ("Dharok's platelegs", "DROP", "Barrows", False),
    ("Dharok's greataxe", "DROP", "Barrows", False),
    ("Karil's coif", "DROP", "Barrows", False),
    ("Karil's leathertop", "DROP", "Barrows", False),
    ("Karil's leatherskirt", "DROP", "Barrows", False),
    ("Karil's crossbow", "DROP", "Barrows", False),
    ("Full Barrows Set", "DROP", None, True),  # Meta trigger

    # COX
    ("Dexterous prayer scroll", "DROP", "Chambers of Xeric", False),
    ("Arcane prayer scroll", "DROP", "Chambers of Xeric", False),
    ("Twisted ancestral colour kit", "DROP", "Chambers of Xeric", False),
    ("Twisted bow", "DROP", "Chambers of Xeric", False),
    ("Metamorphic dust", "DROP", "Chambers of Xeric", False),
    ("Olmlet", "DROP", "Chambers of Xeric", False),

    # GWD
    ("Bandos chestplate", "DROP", "General Graardor", False),
    ("Armadyl helmet", "DROP", "Kree'arra", False),
    ("Godsword blade", "DROP", None, False),
    ("Staff of the dead", "DROP", "K'ril Tsutsaroth", False),
    ("Armadyl crossbow", "DROP", "Kree'arra", False),
    ("Armadyl hilt", "DROP", None, False),
    ("Bandos hilt", "DROP", None, False),
    ("Saradomin hilt", "DROP", None, False),
    ("Zamorak hilt", "DROP", None, False),

    # TOA
    ("Lightbearer", "DROP", "Tombs of Amascut", False),
    ("Osmumten's fang", "DROP", "Tombs of Amascut", False),
    ("Tumeken's shadow", "DROP", "Tombs of Amascut", False),
    ("Masori body", "DROP", "Tombs of Amascut", False),
    ("Elidinis' ward", "DROP", "Tombs of Amascut", False),
    ("Tumeken's guardian", "DROP", "Tombs of Amascut", False),

    # Slayer/Misc
    ("Belle's folly", "DROP", None, False),
    ("Horn of plenty", "DROP", None, False),
    ("Brimstone key", "DROP", None, False),

    # Dragons
    ("Tanzanite fang", "DROP", "Zulrah", False),
    ("Draconic visage", "DROP", "Vorkath", False),
    ("Jar of decay", "DROP", "Vorkath", False),
    ("Dragonbone necklace", "DROP", "Vorkath", False),
    ("Vorki", "DROP", "Vorkath", False),

    # Corp
    ("Arcane sigil", "DROP", "Corporeal Beast", False),
    ("Elysian sigil", "DROP", "Corporeal Beast", False),
    ("Spectral sigil", "DROP", "Corporeal Beast", False),
    ("Dragon warhammer", "DROP", None, False),

    # Nex
    ("Nihil shard", "DROP", "Nex", False),
    ("Zaryte crossbow", "DROP", "Nex", False),
    ("Torva full helm", "DROP", "Nex", False),
    ("Torva platebody", "DROP", "Nex", False),
    ("Torva platelegs", "DROP", "Nex", False),

    # Skilling
    ("Rock golem", "DROP", None, False),
    ("Beaver", "DROP", None, False),
    ("Golden tench", "DROP", None, False),
    ("Pearl", "DROP", None, False),
    ("Vale totem", "DROP", None, False),
    ("Tome of water", "DROP", None, False),
    ("Tempoross pet", "DROP", None, False),
    ("Dragon harpoon", "DROP", "Tempoross", False),

    # Peril
    ("Venator shard", "DROP", None, False),
    ("Dragon metal shard", "DROP", None, False),
    ("Amoxliatl pet", "DROP", None, False),

    # Hueycoatl
    ("Sunfire splinter", "DROP", "Hueycoatl", False),
    ("Huey's horn", "DROP", "Hueycoatl", False),
    ("Hueycoatl pet", "DROP", "Hueycoatl", False),

    # Colosseum
    ("Echo crystal", "DROP", "Colosseum", False),
    ("Sunfire splinter", "DROP", "Colosseum", False),
    ("Uncut onyx", "DROP", "Colosseum", False),
    ("Tonalztics of ralos", "DROP", "Colosseum", False),

    # DT2
    ("Awakener's orb", "DROP", None, False),
    ("Virtus robe top", "DROP", None, False),

    # TOB
    ("Avernic defender hilt", "DROP", "Theatre of Blood", False),
    ("Justiciar faceguard", "DROP", "Theatre of Blood", False),
    ("Scythe of vitur", "DROP", "Theatre of Blood", False),
    ("Sanguine ornament kit", "DROP", "Theatre of Blood", False),
    ("Sanguine dust", "DROP", "Theatre of Blood", False),
    ("Lil' zik", "DROP", "Theatre of Blood", False),

    # Nightmare
    ("Tormented synapse", "DROP", None, False),
    ("Inquisitor's great helm", "DROP", "Phosani's Nightmare", False),
    ("Inquisitor's hauberk", "DROP", "Phosani's Nightmare", False),
    ("Inquisitor's plateskirt", "DROP", "Phosani's Nightmare", False),
    ("Nightmare staff", "DROP", "Phosani's Nightmare", False),
    ("Zenyte shard", "DROP", None, False),
]

def main():
    print("="*60)
    print("Creating triggers from tile definitions...")
    print("="*60)

    created = 0
    failed = 0

    for trigger_def in triggers:
        name, trigger_type, source, skip_wiki = trigger_def

        print(f"\nCreating trigger: {name}")
        trigger_id = create_trigger(name, trigger_type, source, skip_wiki)

        if trigger_id:
            created += 1
        else:
            failed += 1

    print("\n" + "="*60)
    print(f"Summary: {created} created, {failed} failed")
    print("="*60)

if __name__ == "__main__":
    main()
