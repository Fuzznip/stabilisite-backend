#!/usr/bin/env python3
"""
Script to create tasks and challenges from CSV mapping file.
Reads the bingo mapping CSV and creates all tasks and challenges via API.
"""

import subprocess
import json
import csv
import sys
from collections import defaultdict

BASE_URL = "http://localhost:8000"
EVENT_ID = "f73a21d2-2644-410b-b037-c0e99b375a68"

# Cache for created entities
trigger_cache = {}
tile_cache = {}
task_cache = {}
challenge_cache = {}

def curl_get(url):
    """Make a GET request using curl"""
    result = subprocess.run(
        ['curl', '-s', '-X', 'GET', url],
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
            print(f"Failed to parse response: {result.stdout}")
            return None
    return None

def load_triggers():
    """Load all triggers from API into cache"""
    print("Loading triggers...")
    response = curl_get(f"{BASE_URL}/v2/triggers")
    if response and 'data' in response:
        for trigger in response['data']:
            source = trigger.get('source') or 'NULL'
            key = f"{trigger['name']}|{source}|{trigger['type']}"
            trigger_cache[key] = trigger['id']
        print(f"  Loaded {len(trigger_cache)} triggers")
    else:
        print("  Failed to load triggers!")
        sys.exit(1)

def load_tiles():
    """Load all tiles for the event into cache"""
    print("Loading tiles...")
    response = curl_get(f"{BASE_URL}/v2/tiles?event_id={EVENT_ID}")
    if response and 'data' in response:
        for tile in response['data']:
            tile_cache[tile['index']] = tile['id']
        print(f"  Loaded {len(tile_cache)} tiles")
    else:
        print("  Failed to load tiles!")
        sys.exit(1)

def get_trigger_id(name, source, type_):
    """Get trigger ID from cache"""
    source = source if source != 'NULL' else 'NULL'
    key = f"{name}|{source}|{type_}"
    if key not in trigger_cache:
        print(f"  WARNING: Trigger not found: {key}")
        return None
    return trigger_cache[key]

def create_task(tile_id, name, require_all):
    """Create a task"""
    task_data = {
        "tile_id": tile_id,
        "name": name,
        "require_all": require_all
    }
    response = curl_post(f"{BASE_URL}/v2/tasks", task_data)
    if response and 'id' in response:
        return response['id']
    else:
        print(f"  ERROR: Failed to create task '{name}': {response}")
        return None

def create_challenge(task_id, trigger_id, quantity, require_all, parent_challenge_id=None):
    """Create a challenge"""
    if trigger_id is None:
        print(f"  ERROR: Cannot create challenge with null trigger_id")
        return None

    challenge_data = {
        "task_id": task_id,
        "trigger_id": trigger_id,
        "quantity": quantity,
        "require_all": require_all
    }
    if parent_challenge_id:
        challenge_data["parent_challenge_id"] = parent_challenge_id

    response = curl_post(f"{BASE_URL}/v2/challenges", challenge_data)
    if response and 'id' in response:
        return response['id']
    else:
        print(f"  ERROR: Failed to create challenge: {response}")
        return None

def process_csv(csv_path):
    """Process the CSV and create all tasks and challenges"""
    print(f"\nProcessing CSV: {csv_path}")

    # Group rows by tile and task
    tasks_by_tile = defaultdict(lambda: defaultdict(list))

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            tile_idx = int(row['Tile_Index'])
            task_name = row['Task_Name']
            tasks_by_tile[tile_idx][task_name].append(row)

    print(f"\nFound {len(tasks_by_tile)} tiles with tasks")

    # Process each tile
    for tile_idx in sorted(tasks_by_tile.keys()):
        tile_id = tile_cache.get(tile_idx)
        if not tile_id:
            print(f"\nERROR: Tile {tile_idx} not found in cache!")
            continue

        print(f"\n{'='*80}")
        print(f"Tile {tile_idx}: {tasks_by_tile[tile_idx][list(tasks_by_tile[tile_idx].keys())[0]][0]['Tile_Name']}")
        print(f"{'='*80}")

        # Process each task in this tile
        for task_name, rows in tasks_by_tile[tile_idx].items():
            print(f"\n  Task: {task_name}")

            # Get task require_all from first row
            task_require_all = rows[0]['Task_Require_All'].upper() == 'TRUE'

            # Create the task
            task_id = create_task(tile_id, task_name, task_require_all)
            if not task_id:
                print(f"    FAILED to create task!")
                continue

            print(f"    ✓ Created task: {task_id}")

            # Track parent challenges for this task
            parent_challenges = {}
            child_parent_challenges = {}

            # Process challenges in order
            for row in rows:
                challenge_type = row['Challenge_Type']

                if challenge_type == 'DIRECT':
                    # Direct challenge - create it
                    trigger_id = get_trigger_id(
                        row['Challenge_Trigger_Name'],
                        row['Challenge_Trigger_Source'],
                        row['Challenge_Trigger_Type']
                    )
                    if trigger_id:
                        quantity = int(row['Challenge_Quantity'])
                        require_all = row['Challenge_Require_All'].upper() == 'TRUE'
                        challenge_id = create_challenge(task_id, trigger_id, quantity, require_all)
                        if challenge_id:
                            print(f"      ✓ Created DIRECT challenge: {row['Challenge_Trigger_Name']} (qty={quantity})")

                elif challenge_type == 'PARENT':
                    # Parent challenge - create placeholder for now, will be created when we see first child
                    parent_desc = row['Parent_Challenge_Description']
                    if parent_desc not in parent_challenges:
                        # Extract quantity from description
                        import re
                        match = re.search(r'qty=(\d+)', parent_desc)
                        quantity = int(match.group(1)) if match else 1

                        # For parent challenges without a real trigger, we need to use a placeholder
                        # We'll create the parent when we see the first child
                        parent_challenges[parent_desc] = {
                            'quantity': quantity,
                            'require_all': row['Challenge_Require_All'].upper() == 'TRUE',
                            'id': None,
                            'children_count': 0
                        }
                        print(f"      → Registered PARENT: {parent_desc}")

                elif challenge_type == 'CHILD':
                    # Child challenge - find parent and create
                    parent_desc = row['Parent_Challenge_Description']
                    if parent_desc in parent_challenges:
                        parent_info = parent_challenges[parent_desc]

                        # Create parent if not yet created (use first child's trigger as placeholder)
                        if parent_info['id'] is None:
                            trigger_id = get_trigger_id(
                                row['Challenge_Trigger_Name'],
                                row['Challenge_Trigger_Source'],
                                row['Challenge_Trigger_Type']
                            )
                            if trigger_id:
                                parent_id = create_challenge(
                                    task_id,
                                    trigger_id,
                                    parent_info['quantity'],
                                    parent_info['require_all']
                                )
                                if parent_id:
                                    parent_info['id'] = parent_id
                                    print(f"      ✓ Created PARENT challenge: {parent_desc}")

                        # Create child challenge
                        if parent_info['id']:
                            trigger_id = get_trigger_id(
                                row['Challenge_Trigger_Name'],
                                row['Challenge_Trigger_Source'],
                                row['Challenge_Trigger_Type']
                            )
                            if trigger_id:
                                quantity = int(row['Challenge_Quantity'])
                                require_all = row['Challenge_Require_All'].upper() == 'TRUE'
                                child_id = create_challenge(
                                    task_id,
                                    trigger_id,
                                    quantity,
                                    require_all,
                                    parent_info['id']
                                )
                                if child_id:
                                    parent_info['children_count'] += 1
                                    print(f"        ✓ Created CHILD: {row['Challenge_Trigger_Name']}")

                elif challenge_type == 'CHILD_PARENT':
                    # Child that is also a parent (for 3-level hierarchies)
                    parent_desc = row['Parent_Challenge_Description']
                    child_parent_desc = row.get('Notes', '').split(',')[0] if row.get('Notes') else parent_desc

                    # This is a child of the main parent, but also a parent itself
                    # We'll need to track it separately
                    if parent_desc in parent_challenges:
                        parent_info = parent_challenges[parent_desc]

                        # Create main parent if needed
                        if parent_info['id'] is None:
                            # For child_parent, we don't have a real trigger yet, skip for now
                            # It will be created when we see the first grandchild
                            pass

                        # Store this child_parent for later
                        child_parent_key = f"{parent_desc}|{child_parent_desc}"
                        child_parent_challenges[child_parent_key] = {
                            'parent_id': parent_info.get('id'),
                            'require_all': row['Challenge_Require_All'].upper() == 'TRUE',
                            'id': None,
                            'grandchildren_count': 0
                        }
                        print(f"      → Registered CHILD_PARENT: {child_parent_desc}")

                elif challenge_type == 'GRANDCHILD':
                    # Grandchild challenge - find child_parent and create
                    parent_desc = row['Parent_Challenge_Description']
                    child_parent_desc = row.get('Notes', '').split('of ')[1].strip() if 'of ' in row.get('Notes', '') else ''
                    child_parent_key = f"{parent_desc}|{child_parent_desc}"

                    if child_parent_key in child_parent_challenges:
                        child_parent_info = child_parent_challenges[child_parent_key]
                        parent_info = parent_challenges.get(parent_desc)

                        # Create main parent if not created
                        if parent_info and parent_info['id'] is None:
                            # Use first grandchild's trigger as placeholder for main parent
                            trigger_id = get_trigger_id(
                                row['Challenge_Trigger_Name'],
                                row['Challenge_Trigger_Source'],
                                row['Challenge_Trigger_Type']
                            )
                            if trigger_id:
                                parent_id = create_challenge(
                                    task_id,
                                    trigger_id,
                                    parent_info['quantity'],
                                    parent_info['require_all']
                                )
                                if parent_id:
                                    parent_info['id'] = parent_id
                                    child_parent_info['parent_id'] = parent_id
                                    print(f"      ✓ Created MAIN PARENT: {parent_desc}")

                        # Create child_parent if not created
                        if child_parent_info['id'] is None and child_parent_info['parent_id']:
                            trigger_id = get_trigger_id(
                                row['Challenge_Trigger_Name'],
                                row['Challenge_Trigger_Source'],
                                row['Challenge_Trigger_Type']
                            )
                            if trigger_id:
                                child_parent_id = create_challenge(
                                    task_id,
                                    trigger_id,
                                    1,  # Quantity is always 1 for set completion
                                    child_parent_info['require_all'],
                                    child_parent_info['parent_id']
                                )
                                if child_parent_id:
                                    child_parent_info['id'] = child_parent_id
                                    print(f"        ✓ Created CHILD_PARENT: {child_parent_desc}")

                        # Create grandchild
                        if child_parent_info['id']:
                            trigger_id = get_trigger_id(
                                row['Challenge_Trigger_Name'],
                                row['Challenge_Trigger_Source'],
                                row['Challenge_Trigger_Type']
                            )
                            if trigger_id:
                                quantity = int(row['Challenge_Quantity'])
                                require_all = row['Challenge_Require_All'].upper() == 'TRUE'
                                grandchild_id = create_challenge(
                                    task_id,
                                    trigger_id,
                                    quantity,
                                    require_all,
                                    child_parent_info['id']
                                )
                                if grandchild_id:
                                    child_parent_info['grandchildren_count'] += 1
                                    print(f"          ✓ Created GRANDCHILD: {row['Challenge_Trigger_Name']}")

def main():
    csv_path = '/tmp/bingo_mapping.csv'

    print("="*80)
    print("TASK AND CHALLENGE CREATION SCRIPT")
    print("="*80)

    # Load caches
    load_triggers()
    load_tiles()

    # Process CSV
    process_csv(csv_path)

    print("\n" + "="*80)
    print("COMPLETED!")
    print("="*80)

if __name__ == "__main__":
    main()
