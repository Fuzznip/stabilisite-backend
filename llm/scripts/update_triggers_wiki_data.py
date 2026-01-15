import subprocess
import json
import time
from urllib.parse import quote

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

def curl_put(url, data):
    """Make a PUT request using curl"""
    result = subprocess.run(
        ['curl', '-s', '-X', 'PUT', url, '-H', 'Content-Type: application/json', '-d', json.dumps(data)],
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
    url = f"{WIKI_API_URL}?name={quote(item_name)}"
    data = curl_get(url)

    # API returns a single object, not an array
    if data and isinstance(data, dict) and data.get('id'):
        return {
            'wiki_id': data.get('id'),
            'img_path': data.get('image')
        }
    return None

def update_trigger(trigger_id, wiki_id, img_path):
    """Update a trigger with wiki data"""
    update_data = {}
    if wiki_id:
        update_data['wiki_id'] = wiki_id
    if img_path:
        update_data['img_path'] = img_path

    if not update_data:
        return False

    result = curl_put(f"{BASE_URL}/v2/triggers/{trigger_id}", update_data)
    return result is not None

def main():
    print("="*60)
    print("Updating triggers with wiki data...")
    print("="*60)

    # Get all triggers
    response = curl_get(f"{BASE_URL}/v2/triggers?per_page=500")
    if not response or 'data' not in response:
        print("Failed to fetch triggers")
        return

    triggers = response['data']
    print(f"\nFound {len(triggers)} triggers to process")

    updated = 0
    skipped = 0
    failed = 0

    # Skip these triggers (abstract/meta triggers that don't have wiki pages)
    skip_triggers = {
        'Slayer Unique', 'Moons unique', 'Doom unique', 'Boss jar', 'Ring roll',
        'Soulreaper axe piece', 'Daily Challenge', 'Full Barrows Set'
    }

    # Skip XP and KC type triggers (they don't need wiki lookup)
    skip_types = {'XP', 'KC'}

    for trigger in triggers:
        name = trigger['name']
        trigger_type = trigger['type']
        trigger_id = trigger['id']

        # Skip if already has wiki data
        if trigger.get('wiki_id') and trigger.get('img_path'):
            print(f"⏭  Skipping {name} (already has wiki data)")
            skipped += 1
            continue

        # Skip meta triggers
        if name in skip_triggers:
            print(f"⏭  Skipping {name} (meta trigger)")
            skipped += 1
            continue

        # Skip XP/KC triggers
        if trigger_type in skip_types:
            print(f"⏭  Skipping {name} (type: {trigger_type})")
            skipped += 1
            continue

        print(f"\nProcessing: {name}")
        print(f"  Looking up wiki data...")

        wiki_data = get_wiki_data(name)
        if wiki_data:
            print(f"  ✓ Found wiki_id: {wiki_data.get('wiki_id')}")
            print(f"  ✓ Found img_path: {wiki_data.get('img_path')}")

            if update_trigger(trigger_id, wiki_data.get('wiki_id'), wiki_data.get('img_path')):
                print(f"  ✓ Updated trigger")
                updated += 1
            else:
                print(f"  ✗ Failed to update trigger")
                failed += 1
        else:
            print(f"  ⚠  No wiki data found for {name}")
            failed += 1

        # Small delay to avoid overwhelming the API
        time.sleep(0.15)

    print("\n" + "="*60)
    print(f"Summary: {updated} updated, {skipped} skipped, {failed} failed/not found")
    print("="*60)

if __name__ == "__main__":
    main()
