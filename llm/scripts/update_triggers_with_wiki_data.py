import subprocess
import json
import time
import urllib.parse

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

def get_wiki_item_data(item_name):
    """Fetch item data from wiki API"""
    encoded_name = urllib.parse.quote(item_name)
    url = f"{WIKI_API_URL}/api/items/search?name={encoded_name}"
    data = curl_get(url)

    if data and isinstance(data, dict) and not data.get('error'):
        # Single item response
        return {
            'wiki_id': data.get('id'),
            'img_path': data.get('image')
        }
    return None

def main():
    print("Fetching all triggers...")

    # Get all triggers (paginated)
    all_triggers = []
    page = 1
    per_page = 100

    while True:
        response = curl_get(f"{BASE_URL}/v2/triggers?page={page}&per_page={per_page}")
        if not response or not response.get('data'):
            break

        all_triggers.extend(response['data'])

        if len(response['data']) < per_page:
            break

        page += 1

    print(f"Found {len(all_triggers)} triggers to process")

    updated_count = 0
    skipped_count = 0
    failed_count = 0
    not_found_count = 0

    # Only process DROP type triggers
    drop_triggers = [t for t in all_triggers if t['type'] == 'DROP']
    print(f"Processing {len(drop_triggers)} DROP triggers (skipping {len(all_triggers) - len(drop_triggers)} non-DROP triggers)")

    for i, trigger in enumerate(drop_triggers):
        trigger_id = trigger['id']
        trigger_name = trigger['name']

        # Skip if already has wiki_id
        if trigger.get('wiki_id'):
            print(f"[{i+1}/{len(drop_triggers)}] {trigger_name}: Already has wiki_id, skipping")
            skipped_count += 1
            continue

        print(f"[{i+1}/{len(drop_triggers)}] Processing: {trigger_name}")

        # Fetch wiki data
        wiki_data = get_wiki_item_data(trigger_name)

        if wiki_data and wiki_data.get('wiki_id'):
            print(f"  ✓ Found wiki data: ID={wiki_data['wiki_id']}, img={wiki_data['img_path'][:60] if wiki_data['img_path'] else 'None'}...")

            # Update trigger
            update_data = {
                'wiki_id': wiki_data['wiki_id']
            }
            if wiki_data.get('img_path'):
                update_data['img_path'] = wiki_data['img_path']

            result = curl_put(f"{BASE_URL}/v2/triggers/{trigger_id}", update_data)

            if result and result.get('id'):
                print(f"  ✓ Updated trigger")
                updated_count += 1
            else:
                print(f"  ✗ Failed to update trigger: {result}")
                failed_count += 1
        else:
            print(f"  ⚠ No wiki data found")
            not_found_count += 1

        # Rate limiting
        time.sleep(0.15)

    print(f"\n{'='*60}")
    print(f"SUMMARY:")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped (already has wiki_id): {skipped_count}")
    print(f"  Not found in wiki: {not_found_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total DROP triggers processed: {len(drop_triggers)}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
