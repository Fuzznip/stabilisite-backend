#!/usr/bin/env python3
"""
Targeted fix script for parent/child challenges that failed in V2 script.
Creates parent challenges with their children for specific complex cases.
"""

import subprocess
import json
import csv

BASE_URL = "http://localhost:8000"

# Cache
trigger_cache = {}
task_cache = {}

def curl_get(url):
    result = subprocess.run(['curl', '-s', '-X', 'GET', url], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout:
        try:
            return json.loads(result.stdout)
        except:
            return None
    return None

def curl_post(url, data):
    result = subprocess.run(
        ['curl', '-s', '-X', 'POST', url, '-H', 'Content-Type: application/json', '-d', json.dumps(data)],
        capture_output=True, text=True
    )
    if result.returncode == 0 and result.stdout:
        try:
            response = json.loads(result.stdout)
            if 'error' in response:
                print(f"      API Error: {response['error']}")
                return None
            return response
        except:
            return None
    return None

def load_triggers():
    print("Loading triggers...")
    response = curl_get(f"{BASE_URL}/v2/triggers")
    if response and 'data' in response:
        for trigger in response['data']:
            source = trigger.get('source') or 'NULL'
            key = f"{trigger['name']}|{source}|{trigger['type']}"
            trigger_cache[key] = trigger['id']
        print(f"  Loaded {len(trigger_cache)} triggers\n")

def get_trigger_id(name, source, type_):
    source = source if source != 'NULL' else 'NULL'
    key = f"{name}|{source}|{type_}"
    return trigger_cache.get(key)

def create_challenge(task_id, trigger_id, quantity, require_all, parent_id=None):
    challenge_data = {
        "task_id": task_id,
        "trigger_id": trigger_id,
        "quantity": quantity,
        "require_all": require_all
    }
    if parent_id:
        challenge_data["parent_challenge_id"] = parent_id

    response = curl_post(f"{BASE_URL}/v2/challenges", challenge_data)
    if response and 'id' in response:
        return response['id']
    return None

def fix_task_with_children(task_id, task_name, csv_rows):
    """Fix a task that has parent/child challenges"""
    print(f"\n  Fixing task: {task_name}")
    print(f"    Task ID: {task_id}")

    # Get first child's trigger for the parent challenge
    first_child = None
    for row in csv_rows:
        if row['Challenge_Type'] == 'CHILD':
            first_child = row
            break

    if not first_child:
        print(f"    ERROR: No children found!")
        return

    # Get parent info
    parent_row = next((r for r in csv_rows if r['Challenge_Type'] == 'PARENT'), None)
    if not parent_row:
        print(f"    ERROR: No parent row found!")
        return

    # Extract quantity from parent description
    import re
    match = re.search(r'qty=(\d+)', parent_row['Parent_Challenge_Description'])
    parent_quantity = int(match.group(1)) if match else 1
    parent_require_all = parent_row['Challenge_Require_All'].upper() == 'TRUE'

    # Get first child's trigger for parent
    parent_trigger_id = get_trigger_id(
        first_child['Challenge_Trigger_Name'],
        first_child['Challenge_Trigger_Source'],
        first_child['Challenge_Trigger_Type']
    )

    if not parent_trigger_id:
        print(f"    ERROR: Parent trigger not found: {first_child['Challenge_Trigger_Name']}")
        return

    # Create parent challenge
    parent_id = create_challenge(task_id, parent_trigger_id, parent_quantity, parent_require_all)
    if not parent_id:
        print(f"    ERROR: Failed to create parent challenge")
        return

    print(f"    ✓ Created parent (qty={parent_quantity}, require_all={parent_require_all})")

    # Create all children
    child_count = 0
    for row in csv_rows:
        if row['Challenge_Type'] == 'CHILD':
            trigger_id = get_trigger_id(
                row['Challenge_Trigger_Name'],
                row['Challenge_Trigger_Source'],
                row['Challenge_Trigger_Type']
            )
            if trigger_id:
                quantity = int(row['Challenge_Quantity'])
                require_all = row['Challenge_Require_All'].upper() == 'TRUE'
                child_id = create_challenge(task_id, trigger_id, quantity, require_all, parent_id)
                if child_id:
                    child_count += 1

    print(f"    ✓ Created {child_count} children")

def fix_task_with_grandchildren(task_id, task_name, csv_rows):
    """Fix a task that has parent/child_parent/grandchild hierarchy"""
    print(f"\n  Fixing task (3-level): {task_name}")
    print(f"    Task ID: {task_id}")

    # Find first grandchild to use for main parent
    first_grandchild = next((r for r in csv_rows if r['Challenge_Type'] == 'GRANDCHILD'), None)
    if not first_grandchild:
        print(f"    ERROR: No grandchildren found!")
        return

    # Get parent info
    parent_row = next((r for r in csv_rows if r['Challenge_Type'] == 'PARENT'), None)
    if not parent_row:
        print(f"    ERROR: No parent row found!")
        return

    # Extract quantity from parent description
    import re
    match = re.search(r'qty=(\d+)', parent_row['Parent_Challenge_Description'])
    parent_quantity = int(match.group(1)) if match else 1
    parent_require_all = parent_row['Challenge_Require_All'].upper() == 'TRUE'

    # Get trigger for main parent
    parent_trigger_id = get_trigger_id(
        first_grandchild['Challenge_Trigger_Name'],
        first_grandchild['Challenge_Trigger_Source'],
        first_grandchild['Challenge_Trigger_Type']
    )

    if not parent_trigger_id:
        print(f"    ERROR: Parent trigger not found")
        return

    # Create main parent
    main_parent_id = create_challenge(task_id, parent_trigger_id, parent_quantity, parent_require_all)
    if not main_parent_id:
        print(f"    ERROR: Failed to create main parent")
        return

    print(f"    ✓ Created main parent (qty={parent_quantity})")

    # Create any direct children first (non-child_parent children)
    direct_child_count = 0
    for row in csv_rows:
        if row['Challenge_Type'] == 'CHILD':
            trigger_id = get_trigger_id(
                row['Challenge_Trigger_Name'],
                row['Challenge_Trigger_Source'],
                row['Challenge_Trigger_Type']
            )
            if trigger_id:
                quantity = int(row['Challenge_Quantity'])
                require_all = row['Challenge_Require_All'].upper() == 'TRUE'
                child_id = create_challenge(task_id, trigger_id, quantity, require_all, main_parent_id)
                if child_id:
                    direct_child_count += 1

    if direct_child_count > 0:
        print(f"    ✓ Created {direct_child_count} direct children")

    # Group grandchildren by child_parent
    from collections import defaultdict
    grandchildren_by_cp = defaultdict(list)

    for row in csv_rows:
        if row['Challenge_Type'] == 'GRANDCHILD':
            parent_desc = row.get('Parent_Challenge_Description', '')
            if 'of ' in parent_desc:
                cp_desc = parent_desc.split('of ')[1].strip()
                grandchildren_by_cp[cp_desc].append(row)

    # Create each child_parent with its grandchildren
    cp_count = 0
    gc_total = 0
    for cp_desc, grandchildren in grandchildren_by_cp.items():
        # Use first grandchild's trigger for child_parent
        first_gc = grandchildren[0]
        cp_trigger_id = get_trigger_id(
            first_gc['Challenge_Trigger_Name'],
            first_gc['Challenge_Trigger_Source'],
            first_gc['Challenge_Trigger_Type']
        )

        if not cp_trigger_id:
            continue

        # Find the child_parent row to get require_all (match against Parent_Challenge_Description)
        cp_row = next((r for r in csv_rows if r['Challenge_Type'] == 'CHILD_PARENT' and cp_desc in r.get('Parent_Challenge_Description', '')), None)
        cp_require_all = cp_row['Challenge_Require_All'].upper() == 'TRUE' if cp_row else True

        # Create child_parent
        cp_id = create_challenge(task_id, cp_trigger_id, 1, cp_require_all, main_parent_id)
        if cp_id:
            cp_count += 1

            # Create grandchildren under this child_parent
            for gc_row in grandchildren:
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
                        gc_total += 1

    print(f"    ✓ Created {cp_count} child_parents with {gc_total} grandchildren")

def main():
    load_triggers()

    # Read CSV to get task definitions
    csv_path = '/tmp/bingo_mapping.csv'
    tasks_by_tile_task = {}

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (int(row['Tile_Index']), row['Task_Name'])
            if key not in tasks_by_tile_task:
                tasks_by_tile_task[key] = []
            tasks_by_tile_task[key].append(row)

    # Define the failing tasks that need fixing
    # Format: (tile_index, task_name, has_grandchildren)
    failing_tasks = [
        (1, "8 Slayer Unique Points", False),
        (1, "16 Slayer Unique Points", False),
        (1, "24 Slayer Unique Points", False),
        (2, "Rare salvage drop", False),
        (3, "8 moons uniques", False),
        (3, "Full Barrows Set", True),  # Has grandchildren
        (4, "1 Doom Unique", False),
        (4, "3 Doom Uniques", False),
        (4, "5 Doom Uniques", False),
        (10, "Full Masori/3x Ward/Pet", True),  # Has grandchildren
        (21, "4 Ring Rolls", False),
        (21, "3 SR Axe Pieces OR Full Virtus", True),  # Has grandchildren
        (23, "3x Justiciar or Scythe", False),
    ]

    print("="*80)
    print("FIXING PARENT/CHILD CHALLENGES")
    print("="*80)

    # Get all tiles
    EVENT_ID = "f73a21d2-2644-410b-b037-c0e99b375a68"
    tiles_response = curl_get(f"{BASE_URL}/v2/tiles?event_id={EVENT_ID}&per_page=100")
    tiles_by_index = {}
    if tiles_response and 'data' in tiles_response:
        for tile in tiles_response['data']:
            tiles_by_index[tile['index']] = tile['id']

    # Fix each failing task
    for tile_index, task_name, has_grandchildren in failing_tasks:
        print(f"\n{'='*80}")
        print(f"Tile {tile_index}")

        # Get tile
        tile_id = tiles_by_index.get(tile_index)
        if not tile_id:
            print(f"  ERROR: Tile {tile_index} not found")
            continue

        # Get tile with tasks
        tile_data = curl_get(f"{BASE_URL}/v2/tiles/{tile_id}")
        if not tile_data:
            print(f"  ERROR: Failed to get tile data")
            continue

        # Find the task
        task = next((t for t in tile_data.get('tasks', []) if t['name'] == task_name), None)
        if not task:
            print(f"  ERROR: Task '{task_name}' not found")
            continue

        # Get CSV rows for this task
        csv_rows = tasks_by_tile_task.get((tile_index, task_name), [])
        if not csv_rows:
            print(f"  ERROR: No CSV data for task")
            continue

        # Fix the task
        if has_grandchildren:
            fix_task_with_grandchildren(task['id'], task_name, csv_rows)
        else:
            fix_task_with_children(task['id'], task_name, csv_rows)

    print("\n" + "="*80)
    print("COMPLETED!")
    print("="*80)

if __name__ == "__main__":
    main()
