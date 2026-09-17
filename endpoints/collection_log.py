from app import app
from flask import jsonify
from models.models import CollectionLogItem


@app.route("/collection-log/catalog", methods=['GET'])
def get_collection_log_catalog():
    """Full clog structure grouped category -> page -> items, in in-game order."""
    items = CollectionLogItem.query.order_by(
        CollectionLogItem.page_order, CollectionLogItem.sequence
    ).all()

    categories = []
    cat_index = {}
    page_index = {}
    for item in items:
        if item.category not in cat_index:
            cat_index[item.category] = {"category": item.category, "pages": []}
            categories.append(cat_index[item.category])
        cat = cat_index[item.category]

        page_key = (item.category, item.page)
        if page_key not in page_index:
            page_index[page_key] = {"page": item.page, "items": []}
            cat["pages"].append(page_index[page_key])

        page_index[page_key]["items"].append({
            "item_id": item.item_id,
            "name": item.name,
            "image_url": item.image_url,
        })

    return jsonify(categories)
