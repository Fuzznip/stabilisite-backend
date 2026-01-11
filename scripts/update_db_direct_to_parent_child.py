#!/usr/bin/env python3
"""
Update database to convert all tasks with multiple direct challenges
to parent/child pattern.
"""

import subprocess
import json
import csv
from collections import defaultdict

BASE_URL = "http://localhost:8000"

def curl_get(url):
    """Make a GET request using curl"""
    result = subprocess.run(['curl', '-s', '-X', 'GET', url], capture_output=True, text=True)
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

def curl_delete(url):
    """Make a DELETE request using curl"""
    result = subprocess.run(['curl', '-s', '-X', 'DELETE', url], capture_output=True, text=True)
    return result.returncode == 0

def main():
    print("="*80)
    print("CONVERTING DIRECT CHALLENGES TO PARENT/CHILD PATTERN")
    print("="*80)

    # Fetch all tasks
    print("\nFetching tasks...")
    response = curl_get(f"{BASE_URL}/v2/tasks?per_page=200")
    if not response or 'data' not in response:
        print("Failed to fetch tasks!")
        return

    all_tasks = {t['name']: t for t in response['data']}

    # Fetch all triggers
    print("Fetching triggers...")
    response = curl_get(f"{BASE_URL}/v2/triggers?per_page=300")
    if not response or 'data' not in response:
        print("Failed to fetch triggers!")
        return

    triggers_by_name_source = {}
    for t in response['data']:
        key = f"{t['name']}|{t.get('source') or 'NULL'}"
        triggers_by_name_source[key] = t['id']

    # Read CSV to get which tasks to convert
    csv_path = '/tmp/bingo_mapping.csv'
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Group by task
    tasks_by_name = defaultdict(list)
    for row in rows:
        tasks_by_name[row['Task_Name']].append(row)

    # Find tasks that have PARENT/CHILD structure (these are the converted ones)
    tasks_to_update = []
    for task_name, task_rows in tasks_by_name.items():
        has_parent = any(r['Challenge_Type'] == 'PARENT' for r in task_rows)
        has_child = any(r['Challenge_Type'] == 'CHILD' for r in task_rows)
        has_no_grandchildren = all(r['Challenge_Type'] != 'GRANDCHILD' for r in task_rows)

        if has_parent and has_child and has_no_grandchildren:
            # Check if task exists in DB
            if task_name in all_tasks:
                task_id = all_tasks[task_name]['id']
                parent_row = next(r for r in task_rows if r['Challenge_Type'] == 'PARENT')
                child_rows = [r for r in task_rows if r['Challenge_Type'] == 'CHILD']
                tasks_to_update.append((task_name, task_id, parent_row, child_rows))

    print(f"\nFound {len(tasks_to_update)} tasks to update\n")

    # Update each task
    for i, (task_name, task_id, parent_row, child_rows) in enumerate(tasks_to_update, 1):
        print(f"[{i}/{len(tasks_to_update)}] {task_name}")

        # Fetch tile to get existing challenges
        tile_response = curl_get(f"{BASE_URL}/v2/tiles?per_page=200")
        if not tile_response:
            print("  ✗ Failed to fetch tiles")
            continue

        # Find the task's challenges
        task_obj = None
        for tile in tile_response['data']:
            tile_detail = curl_get(f"{BASE_URL}/v2/tiles/{tile['id']}")
            if tile_detail and 'tasks' in tile_detail:
                for t in tile_detail['tasks']:
                    if t['id'] == task_id:
                        task_obj = t
                        break
            if task_obj:
                break

        if not task_obj:
            print("  ✗ Task not found in tiles")
            continue

        # Delete existing challenges
        for challenge in task_obj.get('challenges', []):
            curl_delete(f"{BASE_URL}/v2/challenges/{challenge['id']}")
        print(f"  - Deleted {len(task_obj.get('challenges', []))} existing challenges")

        # Create parent challenge (using first child's trigger as placeholder)
        first_child = child_rows[0]
        trigger_key = f"{first_child['Challenge_Trigger_Name']}|{first_child['Challenge_Trigger_Source']}"
        trigger_id = triggers_by_name_source.get(trigger_key)

        if not trigger_id:
            print(f"  ✗ Trigger not found: {trigger_key}")
            continue

        parent_data = {
            "task_id": task_id,
            "trigger_id": trigger_id,
            "quantity": 1,
            "require_all": False
        }
        parent_response = curl_post(f"{BASE_URL}/v2/challenges", parent_data)
        if not parent_response:
            print("  ✗ Failed to create parent challenge")
            continue

        parent_id = parent_response['id']
        print(f"  ✓ Created parent challenge")

        # Create child challenges
        child_count = 0
        for child_row in child_rows:
            trigger_key = f"{child_row['Challenge_Trigger_Name']}|{child_row['Challenge_Trigger_Source']}"
            trigger_id = triggers_by_name_source.get(trigger_key)

            if not trigger_id:
                print(f"    ⚠ Trigger not found: {trigger_key}")
                continue

            child_data = {
                "task_id": task_id,
                "trigger_id": trigger_id,
                "quantity": int(child_row['Challenge_Quantity']),
                "require_all": child_row['Challenge_Require_All'] == 'TRUE',
                "parent_challenge_id": parent_id
            }
            child_response = curl_post(f"{BASE_URL}/v2/challenges", child_data)
            if child_response:
                child_count += 1

        print(f"  ✓ Created {child_count} child challenges\n")

    print("="*80)
    print("COMPLETED!")
    print("="*80)

if __name__ == "__main__":
    main()
