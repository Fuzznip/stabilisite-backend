"""Generate the collection log catalog dataset from the OSRS Wiki.

Two wiki sources are combined:
  * Module:Collection_log/data.json  -> every clog item: {id, name, tabs:[page...]}
  * "Collection log" article wikitext -> the in-game hierarchy: ==Category== / ===Page===
    headers give the 5 tabs (Bosses/Raids/Clues/Minigames/Other) and their ordered pages.

Output: data/collection_log_catalog.json — a flat list of placements
  {item_id, name, category, page, page_order, sequence}
where an item may appear on multiple pages (shared rewards, pets, etc.).

Run:  python scripts/generate_collection_log_catalog.py
Re-run whenever the in-game collection log changes.
"""
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict

WIKI_API = "https://oldschool.runescape.wiki/api.php"
UA = "stabilisite-collection-log/1.0 (clan website catalog seed)"
CATEGORIES = {"Bosses", "Raids", "Clues", "Minigames", "Other"}
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "collection_log_catalog.json")


def _get(params: dict) -> dict:
    url = WIKI_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_item_data() -> list[dict]:
    d = _get({
        "action": "query", "titles": "Module:Collection_log/data.json",
        "prop": "revisions", "rvprop": "content", "rvslots": "main", "format": "json",
    })
    page = next(iter(d["query"]["pages"].values()))
    return json.loads(page["revisions"][0]["slots"]["main"]["*"])


def fetch_article_pages() -> list[tuple[str, str, int]]:
    """Ordered (category, page, page_order) from the article's header hierarchy."""
    d = _get({"action": "parse", "page": "Collection log", "prop": "wikitext", "format": "json"})
    wikitext = d["parse"]["wikitext"]["*"]
    category = None
    pages = []
    order = 0
    for line in wikitext.splitlines():
        level2 = re.match(r'^==\s*([^=].*?)\s*==$', line)
        level3 = re.match(r'^===\s*([^=].*?)\s*===$', line)
        if level2:
            name = level2.group(1).strip()
            category = name if name in CATEGORIES else None
        elif level3 and category:
            order += 1
            pages.append((category, level3.group(1).strip(), order))
    return pages


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).lower().replace("’", "'")
    name = re.sub(r'\btreasure trail rewards\b', 'treasure trails', name)
    name = re.sub(r'\btreasure trail\b', 'treasure trails', name)
    return re.sub(r'\s+', ' ', name).strip()


def build_catalog() -> list[dict]:
    items = fetch_item_data()
    pages = fetch_article_pages()

    items_by_page = defaultdict(list)
    for item in items:
        for tab in item.get("tabs", []):
            items_by_page[normalize(tab)].append(item)

    catalog = []
    for category, page, page_order in pages:
        for sequence, item in enumerate(items_by_page.get(normalize(page), [])):
            catalog.append({
                "item_id": item["id"],
                "name": item["name"],
                "category": category,
                "page": page,
                "page_order": page_order,
                "sequence": sequence,
            })
    return catalog


def main():
    catalog = build_catalog()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(catalog, f, indent=0, ensure_ascii=False)
    distinct_items = len({row["item_id"] for row in catalog})
    distinct_pages = len({(row["category"], row["page"]) for row in catalog})
    print(f"Wrote {len(catalog)} placements ({distinct_items} items, {distinct_pages} pages) -> {os.path.relpath(OUT_PATH)}")


if __name__ == "__main__":
    main()
