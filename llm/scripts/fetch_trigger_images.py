#!/usr/bin/env python3
"""
Script to fetch OSRS Wiki images for triggers without img_path.
"""

import subprocess
import json
import time
import urllib.parse
import re

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

def curl_put(url, data):
    """Make a PUT request using curl"""
    result = subprocess.run(
        ['curl', '-s', '-X', 'PUT', url, '-H', 'Content-Type: application/json', '-d', json.dumps(data)],
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
            return None
    return None

def fetch_wiki_image(item_name):
    """Fetch the main image URL for an item from OSRS Wiki"""
    # Clean up the item name for wiki search
    search_name = item_name.strip()

    # Direct image URLs for items that need special handling
    direct_urls = {
        'Beaver': 'https://oldschool.runescape.wiki/images/Beaver_%28follower%29.png?15794',
        'Blood moon chestplate': 'https://oldschool.runescape.wiki/images/Blood_moon_chestplate_detail.png?2eba8',
        'Blood moon helm': 'https://oldschool.runescape.wiki/images/Blood_moon_helm_detail.png?2eba8',
        'Blood moon tassets': 'https://oldschool.runescape.wiki/images/Blood_moon_tassets_detail.png?2eba8',
        'Blue moon chestplate': 'https://oldschool.runescape.wiki/images/Blue_moon_chestplate_detail.png?2eba8',
        'Blue moon helm': 'https://oldschool.runescape.wiki/images/Blue_moon_helm_detail.png?2eba8',
        'Blue moon tassets': 'https://oldschool.runescape.wiki/images/Blue_moon_tassets_detail.png?2eba8',
        'Eclipse moon chestplate': 'https://oldschool.runescape.wiki/images/Eclipse_moon_chestplate_detail.png?2eba8',
        'Eclipse moon helm': 'https://oldschool.runescape.wiki/images/Eclipse_moon_helm_detail.png?2eba8',
        'Eclipse moon tassets': 'https://oldschool.runescape.wiki/images/Eclipse_moon_tassets_detail.png?2eba8',
        'Torva full helm (damaged)': 'https://oldschool.runescape.wiki/images/Torva_full_helm_detail.png?d115d',
        'Torva platebody (damaged)': 'https://oldschool.runescape.wiki/images/Torva_platebody_detail.png?d115d',
        'Torva platelegs (damaged)': 'https://oldschool.runescape.wiki/images/Torva_platelegs_detail.png?d115d',
        'Araxyte head': 'https://oldschool.runescape.wiki/images/Araxyte_head_detail.png?43deb',
        'Daily Challenge': 'https://oldschool.runescape.wiki/images/Clue_scroll_%28master%29_detail.png?f3c22',
        'Ring roll': 'https://oldschool.runescape.wiki/images/Gold_ring_detail.png?8793d',
        'Vale totem': 'https://oldschool.runescape.wiki/images/Vale_offerings_detail.png?fc9df',
        'Woodcutting': 'https://oldschool.runescape.wiki/images/Woodcutting_icon_%28detail%29.png?a4903',
        'Sunfire fanatic helm': 'https://oldschool.runescape.wiki/images/Sunfire_fanatic_helm_detail.png',
        'Sunfire fanatic cuirass': 'https://oldschool.runescape.wiki/images/Sunfire_fanatic_cuirass_detail.png',
        'Sunfire fanatic chausses': 'https://oldschool.runescape.wiki/images/Sunfire_fanatic_chausses_detail.png',
    }

    # Return direct URL if exists
    if search_name in direct_urls:
        return direct_urls[search_name]

    # Special cases for wiki page names
    name_mappings = {
        'Bludgeon piece': 'Abyssal bludgeon',
        'Araxyte head': 'Araxyte head (mounted)',
        'Corrupted avernic treads': 'Avernic treads',
        'Tome of water (empty)': 'Tome of water',
        'Trident of the seas (full)': 'Trident of the seas',
        'Eye of ayak (uncharged)': 'Eye of ayak',
        'Tonalztics of ralos (uncharged)': 'Tonalztics of ralos',
        'Soulreaper axe piece': 'Soulreaper axe',
        'Tempoross pet': 'Tempoross',
        'Sailing pet': 'Sailing',
        'Hueycoatl pet': 'Hueycoatl',
        "Huey's horn": 'Hueycoatl',
        'Vale totem': 'Vale',
        'Woodcutting': 'Woodcutting',
    }

    # Use mapping if exists
    if search_name in name_mappings:
        search_name = name_mappings[search_name]

    # URL encode the search name
    encoded_name = urllib.parse.quote(search_name.replace(' ', '_'))
    wiki_api_url = f"https://oldschool.runescape.wiki/api.php?action=query&titles={encoded_name}&prop=pageimages&format=json&pithumbsize=500"

    try:
        # Use curl to fetch wiki API
        result = subprocess.run(['curl', '-s', wiki_api_url], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            pages = data.get('query', {}).get('pages', {})

            # Get the first (and usually only) page
            for page_id, page_data in pages.items():
                if page_id == '-1':
                    # Page not found, try alternate search
                    return None

                thumbnail = page_data.get('thumbnail', {})
                if 'source' in thumbnail:
                    return thumbnail['source']

        return None
    except Exception as e:
        print(f"    Error fetching image for '{item_name}': {e}")
        return None

def main():
    print("="*80)
    print("FETCHING OSRS WIKI IMAGES FOR TRIGGERS")
    print("="*80)

    # Fetch all triggers
    print("\nFetching triggers...")
    response = curl_get(f"{BASE_URL}/v2/triggers?per_page=300")

    if not response or 'data' not in response:
        print("Failed to fetch triggers!")
        return

    # Filter triggers without img_path
    triggers_without_images = [
        t for t in response['data']
        if not t.get('img_path') or t.get('img_path') == ''
    ]

    print(f"Found {len(triggers_without_images)} triggers without images")

    # Process each trigger
    updated_count = 0
    failed_count = 0
    skipped_count = 0

    for i, trigger in enumerate(triggers_without_images, 1):
        name = trigger['name']
        source = trigger.get('source') or 'NULL'
        trigger_id = trigger['id']

        print(f"\n[{i}/{len(triggers_without_images)}] {name} ({source})")

        # Fetch wiki image
        img_url = fetch_wiki_image(name)

        if img_url:
            # Update trigger with image - need to send full trigger data for PUT
            update_data = {
                'name': trigger['name'],
                'source': trigger.get('source'),
                'type': trigger['type'],
                'img_path': img_url
            }
            result = curl_put(f"{BASE_URL}/v2/triggers/{trigger_id}", update_data)

            if result:
                print(f"  ✓ Updated with image: {img_url}")
                updated_count += 1
            else:
                print(f"  ✗ Failed to update trigger")
                failed_count += 1
        else:
            print(f"  - No image found on wiki")
            skipped_count += 1

        # Rate limit to be nice to the wiki
        time.sleep(0.5)

    print("\n" + "="*80)
    print("COMPLETED!")
    print("="*80)
    print(f"Updated: {updated_count}")
    print(f"Failed: {failed_count}")
    print(f"Skipped (no image found): {skipped_count}")

if __name__ == "__main__":
    main()
