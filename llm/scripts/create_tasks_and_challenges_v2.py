#!/usr/bin/env python3
"""
Script to create tasks and challenges from CSV mapping file (V2 - with proper parent/child handling).
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
            response = json.loads(result.stdout)
            if 'error' in response:
                print(f"    API Error: {response['error']}")
                return None
            return response
        except:
            print(f"    Failed to parse response: {result.stdout}")
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
        print(f"    WARNING: Trigger not found: {key}")
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
        print(f"    ERROR: Failed to create task '{name}'")
        return None

def create_challenge(task_id, trigger_id, quantity, require_all, parent_challenge_id=None):
    """Create a challenge"""
    if trigger_id is None:
        print(f"    ERROR: Cannot create challenge with null trigger_id")
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
        print(f"    ERROR: Failed to create challenge")
        return None

def process_csv(csv_path):
    """Process the CSV and create all tasks and challenges"""
    print(f"\nProcessing CSV: {csv_path}")

    # First pass: Organize all rows by tile and task
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

            # Organize challenges by type
            direct_challenges = []
            parent_challenges = []
            child_challenges = []
            child_parent_challenges = []
            grandchild_challenges = []

            for row in rows:
                challenge_type = row['Challenge_Type']
                if challenge_type == 'DIRECT':
                    direct_challenges.append(row)
                elif challenge_type == 'PARENT':
                    parent_challenges.append(row)
                elif challenge_type == 'CHILD':
                    child_challenges.append(row)
                elif challenge_type == 'CHILD_PARENT':
                    child_parent_challenges.append(row)
                elif challenge_type == 'GRANDCHILD':
                    grandchild_challenges.append(row)

            # Create direct challenges first
            for row in direct_challenges:
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
                        print(f"      ✓ DIRECT: {row['Challenge_Trigger_Name']} (qty={quantity})")

            # Handle parent/child hierarchies
            if parent_challenges:
                # Group children by parent description
                children_by_parent = defaultdict(list)
                for child in child_challenges:
                    parent_desc = child.get('Parent_Challenge_Description', '')
                    children_by_parent[parent_desc].append(child)

                # Process each parent with its children
                for parent_row in parent_challenges:
                    parent_desc = parent_row['Parent_Challenge_Description']
                    children = children_by_parent.get(parent_desc, [])

                    if not children:
                        print(f"      WARNING: Parent '{parent_desc}' has no children")
                        continue

                    # Use first child's trigger for the parent
                    first_child = children[0]
                    parent_trigger_id = get_trigger_id(
                        first_child['Challenge_Trigger_Name'],
                        first_child['Challenge_Trigger_Source'],
                        first_child['Challenge_Trigger_Type']
                    )

                    if not parent_trigger_id:
                        continue

                    # Extract quantity from parent description
                    import re
                    match = re.search(r'qty=(\d+)', parent_desc)
                    parent_quantity = int(match.group(1)) if match else 1
                    parent_require_all = parent_row['Challenge_Require_All'].upper() == 'TRUE'

                    # Create parent challenge
                    parent_id = create_challenge(task_id, parent_trigger_id, parent_quantity, parent_require_all)
                    if parent_id:
                        print(f"      ✓ PARENT: {parent_desc}")

                        # Create all children under this parent
                        for child_row in children:
                            child_trigger_id = get_trigger_id(
                                child_row['Challenge_Trigger_Name'],
                                child_row['Challenge_Trigger_Source'],
                                child_row['Challenge_Trigger_Type']
                            )
                            if child_trigger_id:
                                child_quantity = int(child_row['Challenge_Quantity'])
                                child_require_all = child_row['Challenge_Require_All'].upper() == 'TRUE'
                                child_id = create_challenge(task_id, child_trigger_id, child_quantity, child_require_all, parent_id)
                                if child_id:
                                    print(f"        ✓ CHILD: {child_row['Challenge_Trigger_Name']}")

            # Handle 3-level hierarchies (parent -> child_parent -> grandchild)
            if child_parent_challenges:
                # Group child_parents and grandchildren
                child_parents_by_main_parent = defaultdict(list)
                grandchildren_by_child_parent = defaultdict(list)

                for cp_row in child_parent_challenges:
                    parent_desc = cp_row['Parent_Challenge_Description']
                    child_parents_by_main_parent[parent_desc].append(cp_row)

                for gc_row in grandchild_challenges:
                    # Extract child_parent description from Notes
                    notes = gc_row.get('Notes', '')
                    if 'of ' in notes:
                        child_parent_desc = notes.split('of ')[1].strip()
                        grandchildren_by_child_parent[child_parent_desc].append(gc_row)

                # Find the parent row
                main_parent_row = None
                for p_row in parent_challenges:
                    if p_row['Parent_Challenge_Description'] in child_parents_by_main_parent:
                        main_parent_row = p_row
                        break

                if main_parent_row:
                    parent_desc = main_parent_row['Parent_Challenge_Description']
                    child_parent_rows = child_parents_by_main_parent[parent_desc]

                    # Get first grandchild's trigger for main parent
                    first_cp = child_parent_rows[0] if child_parent_rows else None
                    if first_cp:
                        # Find grandchildren for this child_parent
                        cp_notes = first_cp.get('Notes', '')
                        # Extract description from notes (e.g., "Dharok's set parent, require_all=true")
                        cp_desc = cp_notes.split(',')[0] if cp_notes else ''

                        grandchildren = grandchildren_by_child_parent.get(cp_desc, [])
                        if grandchildren:
                            first_gc = grandchildren[0]
                            main_parent_trigger_id = get_trigger_id(
                                first_gc['Challenge_Trigger_Name'],
                                first_gc['Challenge_Trigger_Source'],
                                first_gc['Challenge_Trigger_Type']
                            )

                            if main_parent_trigger_id:
                                # Extract quantity from parent description
                                import re
                                match = re.search(r'qty=(\d+)', parent_desc)
                                main_parent_quantity = int(match.group(1)) if match else 1
                                main_parent_require_all = main_parent_row['Challenge_Require_All'].upper() == 'TRUE'

                                # Create main parent
                                main_parent_id = create_challenge(task_id, main_parent_trigger_id, main_parent_quantity, main_parent_require_all)
                                if main_parent_id:
                                    print(f"      ✓ MAIN PARENT: {parent_desc}")

                                    # Create each child_parent under main parent
                                    for cp_row in child_parent_rows:
                                        cp_notes = cp_row.get('Notes', '')
                                        cp_desc = cp_notes.split(',')[0] if cp_notes else ''
                                        cp_grandchildren = grandchildren_by_child_parent.get(cp_desc, [])

                                        if cp_grandchildren:
                                            # Use first grandchild's trigger for child_parent
                                            first_gc = cp_grandchildren[0]
                                            cp_trigger_id = get_trigger_id(
                                                first_gc['Challenge_Trigger_Name'],
                                                first_gc['Challenge_Trigger_Source'],
                                                first_gc['Challenge_Trigger_Type']
                                            )

                                            if cp_trigger_id:
                                                cp_require_all = cp_row['Challenge_Require_All'].upper() == 'TRUE'
                                                cp_id = create_challenge(task_id, cp_trigger_id, 1, cp_require_all, main_parent_id)
                                                if cp_id:
                                                    print(f"        ✓ CHILD_PARENT: {cp_desc}")

                                                    # Create grandchildren under this child_parent
                                                    for gc_row in cp_grandchildren:
                                                        gc_trigger_id = get_trigger_id(
                                                            gc_row['Challenge_Trigger_Name'],
                                                            gc_row['Challenge_Trigger_Source'],
                                                            gc_row['Challenge_Trigger_Type']
                                                        )
                                                        if gc_trigger_id:
                                                            gc_quantity = int(gc_row['Challenge_Quantity'])
                                                            gc_require_all = gc_row['Challenge_Require_All'].upper() == 'TRUE'
                                                            gc_id = create_challenge(task_id, gc_trigger_id, gc_quantity, gc_require_all, cp_id)
                                                            if gc_id:
                                                                print(f"          ✓ GRANDCHILD: {gc_row['Challenge_Trigger_Name']}")

def main():
    csv_path = '/tmp/bingo_mapping.csv'

    print("="*80)
    print("TASK AND CHALLENGE CREATION SCRIPT V2")
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
