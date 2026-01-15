#!/usr/bin/env python3
"""
Update Slayer Unique challenge point values based on the provided mapping.
"""

import subprocess
import json

BASE_URL = "http://localhost:8000"

# Point values mapping from the image
POINT_VALUES = {
    # Grotesque Guardians
    "Black tourmaline core": 3,
    "Granite gloves": 1,
    "Granite ring": 1,
    "Granite hammer": 1,
    "Jar of stone": 2,
    "Noon": 3,

    # Abyssal Sire
    "Unsired": 2,
    "Abyssal orphan": 3,  # Pet
    "Bludgeon piece": 2,  # Assuming 2 points (uncommon drop)
    "Jar of miasma": 2,  # Jar (same as other jars)

    # Kraken
    "Kraken tentacle": 2,
    "Trident of the seas (full)": 1,
    "Jar of dirt": 2,
    "Pet kraken": 3,

    # Cerberus
    "Eternal crystal": 1,
    "Primordial crystal": 1,
    "Pegasian crystal": 1,
    "Jar of souls": 2,
    "Smouldering stone": 1,
    "Hellpuppy": 3,

    # Araxxor
    "Noxious pommel": 2,
    "Noxious point": 2,
    "Noxious blade": 2,
    "Araxyte fang": 3,  # Database uses "Araxyte fang"
    "Araxyte head": 1,  # Database uses "Araxyte head"
    "Jar of venom": 2,
    "Nid": 3,

    # Thermonuclear Smoke Devil
    "Occult necklace": 1,
    "Smoke battlestaff": 2,
    "Dragon chainbody": 1,
    "Jar of smoke": 2,
    "Pet smoke devil": 3,
    "Thermy": 3,  # Pet (same as Pet smoke devil)

    # Alchemical Hydra
    "Hydra's claw": 3,
    "Hydra tail": 1,
    "Hydra leather": 2,
    "Hydra's fang": 1,
    "Hydra's eye": 1,
    "Hydra's heart": 1,
    "Jar of chemicals": 2,
    "Alchemical hydra heads": 1,
    "Ikkle hydra": 3,
}

def curl_get(url):
    result = subprocess.run(['curl', '-s', '-X', 'GET', url], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout:
        try:
            return json.loads(result.stdout)
        except:
            return None
    return None

def curl_put(url, data):
    result = subprocess.run(
        ['curl', '-s', '-X', 'PUT', url, '-H', 'Content-Type: application/json', '-d', json.dumps(data)],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout:
        try:
            return json.loads(result.stdout)
        except:
            return None
    return None

def main():
    print("="*80)
    print("UPDATING SLAYER UNIQUE POINT VALUES")
    print("="*80)

    # Get Slayer Unique tile
    SLAYER_TILE_ID = "89ceb07d-d9aa-448f-99f2-5eddc5594cdf"
    tile = curl_get(f"{BASE_URL}/v2/tiles/{SLAYER_TILE_ID}")

    if not tile:
        print("ERROR: Could not fetch Slayer Unique tile")
        return

    updated_count = 0
    not_found_count = 0
    skipped_count = 0
    not_found_triggers = set()

    # Process each task
    for task in tile['tasks']:
        print(f"\nTask: {task['name']}")

        # Process each challenge in the task
        for challenge in task['challenges']:
            trigger_name = challenge['trigger']['name']
            current_value = challenge.get('value', 1)

            # Skip parent challenges (they don't have point values, only children do)
            if challenge['parent_challenge_id'] is None and len([c for c in task['challenges'] if c['parent_challenge_id'] is not None]) > 0:
                print(f"  [SKIP] {trigger_name} (parent challenge)")
                skipped_count += 1
                continue

            # Check if we have a point value for this trigger
            if trigger_name in POINT_VALUES:
                new_value = POINT_VALUES[trigger_name]

                if current_value == new_value:
                    print(f"  [OK] {trigger_name}: {current_value} points (already correct)")
                    skipped_count += 1
                else:
                    # Update the challenge
                    update_data = {"value": new_value}
                    result = curl_put(f"{BASE_URL}/v2/challenges/{challenge['id']}", update_data)

                    if result:
                        print(f"  [UPDATE] {trigger_name}: {current_value} -> {new_value} points")
                        updated_count += 1
                    else:
                        print(f"  [ERROR] Failed to update {trigger_name}")
            else:
                print(f"  [NOT FOUND] {trigger_name}: no point value mapping")
                not_found_count += 1
                not_found_triggers.add(trigger_name)

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Updated: {updated_count}")
    print(f"Skipped (already correct or parent): {skipped_count}")
    print(f"Not found in mapping: {not_found_count}")

    if not_found_triggers:
        print("\nTriggers not found in point mapping:")
        for trigger in sorted(not_found_triggers):
            print(f"  - {trigger}")

    print("="*80)

if __name__ == "__main__":
    main()
