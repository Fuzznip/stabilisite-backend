#!/usr/bin/env python3
"""
Convert all tasks with multiple DIRECT challenges (require_all=false)
to use PARENT/CHILD pattern instead.
"""

import csv
from collections import defaultdict

csv_path = '/tmp/bingo_mapping.csv'

# Read all rows
with open(csv_path, 'r') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

# Group by task
tasks_by_name = defaultdict(list)
for row in rows:
    task_key = (row['Tile_Index'], row['Task_Name'])
    tasks_by_name[task_key].append(row)

# New rows list
new_rows = []

# Process each task
for (tile_idx, task_name), task_rows in tasks_by_name.items():
    # Count DIRECT challenges
    direct_challenges = [r for r in task_rows if r['Challenge_Type'] == 'DIRECT']
    require_all = task_rows[0]['Task_Require_All']

    # If multiple DIRECT challenges with require_all=false, convert to parent/child
    if len(direct_challenges) > 1 and require_all == 'FALSE':
        print(f"Converting: Tile {tile_idx} - {task_name} ({len(direct_challenges)} directs)")

        # Create parent row
        parent_row = direct_challenges[0].copy()
        parent_row['Challenge_Type'] = 'PARENT'
        parent_row['Challenge_Trigger_Name'] = ''
        parent_row['Challenge_Trigger_Source'] = ''
        parent_row['Challenge_Trigger_Type'] = ''
        parent_row['Challenge_Quantity'] = ''
        parent_row['Challenge_Require_All'] = 'FALSE'
        parent_row['Parent_Challenge_Description'] = f'Parent challenge qty=1, require_all=false'
        parent_row['Notes'] = f'Any 1 of {len(direct_challenges)} options'
        new_rows.append(parent_row)

        # Convert each DIRECT to CHILD
        for direct_row in direct_challenges:
            child_row = direct_row.copy()
            child_row['Challenge_Type'] = 'CHILD'
            child_row['Parent_Challenge_Description'] = f'Child of {task_name} parent'
            new_rows.append(child_row)
    else:
        # Keep non-DIRECT rows and tasks that don't need conversion
        for row in task_rows:
            new_rows.append(row)

# Write back
with open(csv_path, 'w', newline='') as f:
    fieldnames = ['Tile_Index', 'Tile_Name', 'Task_Name', 'Task_Require_All', 'Challenge_Type',
                  'Challenge_Trigger_Name', 'Challenge_Trigger_Source', 'Challenge_Trigger_Type',
                  'Challenge_Quantity', 'Challenge_Require_All', 'Parent_Challenge_Description', 'Notes']
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(new_rows)

print("\nConversion complete!")
