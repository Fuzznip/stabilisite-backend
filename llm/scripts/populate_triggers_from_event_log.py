import csv
import subprocess
import json
import time
from collections import defaultdict

BASE_URL = "http://localhost:8000"
WIKI_API_URL = "http://localhost:3000"

def curl_get(url):
    """Make a GET request using curl"""
    result = subprocess.run(['curl', '-s', url], capture_output=True, text=True)
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

def get_wiki_item_data(item_name):
    """Fetch item data from wiki API"""
    url = f"{WIKI_API_URL}/api/items/search?name={item_name}"
    data = curl_get(url)
    if data and len(data) > 0:
        # Return first match
        item = data[0]
        return {
            'wiki_id': item.get('id'),
            'img_path': item.get('icon')
        }
    return None

def determine_trigger_type(trigger, source, event_type):
    """Determine the type of trigger based on name and source"""
    trigger_lower = trigger.lower()

    # KC tracking
    if source and source in trigger:
        return 'KC'

    # Skill XP
    if 'xp' in trigger_lower or trigger.startswith('99 '):
        return 'SKILL'

    # Manual entries
    if event_type == 'MANUAL':
        return 'DROP'

    # Points/waves
    if 'points' in trigger_lower or 'wave' in trigger_lower:
        return 'ACHIEVEMENT'

    # Default to DROP for most items
    return 'DROP'

def main():
    print("Loading event log data...")

    # Extract unique trigger-source-type combinations
    triggers_set = set()
    trigger_types = {}

    with open('/Users/tyler/Documents/code/stabilisite-backend/event_log_dump.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            trigger = row['trigger']
            source = row['source'] if row['source'] else None
            event_type = row['type']

            key = (trigger, source)
            triggers_set.add(key)

            # Store type for this trigger
            if key not in trigger_types:
                trigger_types[key] = determine_trigger_type(trigger, source, event_type)

    print(f"Found {len(triggers_set)} unique trigger-source combinations")

    # Sort for consistent processing (handle None values)
    triggers_list = sorted(list(triggers_set), key=lambda x: (x[0], x[1] or ''))

    created_count = 0
    skipped_count = 0
    failed_count = 0

    for i, (trigger, source) in enumerate(triggers_list):
        print(f"\n[{i+1}/{len(triggers_list)}] Processing: {trigger} (source: {source or 'None'})")

        trigger_type = trigger_types[(trigger, source)]

        # Fetch wiki data (disabled for now - wiki API has issues)
        if trigger_type == 'DROP':
            print(f"  Fetching wiki data for '{trigger}'...")
            wiki_data = get_wiki_item_data(trigger)
            if wiki_data:
                print(f"  ✓ Found wiki data: ID={wiki_data['wiki_id']}, img={wiki_data['img_path'][:50] if wiki_data['img_path'] else 'None'}...")
            else:
                print(f"  ⚠ No wiki data found")
            # time.sleep(0.1)  # Rate limiting

        # Create trigger
        trigger_data = {
            'name': trigger,
            'type': trigger_type,
        }

        if source:
            trigger_data['source'] = source

        if wiki_data:
            if wiki_data.get('wiki_id'):
                trigger_data['wiki_id'] = wiki_data['wiki_id']
            if wiki_data.get('img_path'):
                trigger_data['img_path'] = wiki_data['img_path']

        result = curl_post(f"{BASE_URL}/v2/triggers", trigger_data)

        if result and result.get('id'):
            print(f"  ✓ Created trigger: {result['id']}")
            created_count += 1
        elif result and 'error' in result and 'already exist' in result['error']:
            print(f"  ⊘ Trigger already exists")
            skipped_count += 1
        else:
            print(f"  ✗ Failed to create trigger: {result}")
            failed_count += 1

    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"  Created: {created_count}")
    print(f"  Skipped (already exists): {skipped_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total processed: {len(triggers_list)}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
