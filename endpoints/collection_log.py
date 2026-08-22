from app import app, db
from flask import jsonify, request
from sqlalchemy import func, distinct
from sqlalchemy.orm import aliased
from models.models import CollectionLogItem, CollectionLogDrop, Users

MAX_DROPS_PER_MEMBER = 10


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


@app.route("/collection-log/summary", methods=['GET'])
def get_collection_log_summary():
    """Per-item obtained stats for the grid: distinct members + total drops.

    Both counts ignore drops whose rsn never resolved to a member. /item/<id>
    inner-joins Users and so can only ever show matched drops; counting the
    unmatched ones here would put a total on the grid that the dialog can't
    account for.
    """
    rows = db.session.query(
        CollectionLogDrop.item_id,
        func.count(distinct(CollectionLogDrop.discord_id)).label("member_count"),
        func.count(CollectionLogDrop.id).label("total_count"),
    ).filter(
        CollectionLogDrop.discord_id.isnot(None)
    ).group_by(CollectionLogDrop.item_id).all()

    return jsonify([
        {"item_id": item_id, "member_count": member_count, "total_count": total_count}
        for item_id, member_count, total_count in rows
    ])


@app.route("/collection-log/item/<int:item_id>", methods=['GET'])
def get_collection_log_item_members(item_id):
    """Clan members who have received a given item, with counts, dates and drops.

    Each member carries their individual drops (newest first) so the site can
    show the screenshots behind a count. `count` stays authoritative: a member
    farming one item can have thousands of drops, so the list is capped at
    MAX_DROPS_PER_MEMBER and may be shorter than the count.
    """
    drops_by_member = {}
    drop_rows = db.session.query(CollectionLogDrop).filter(
        CollectionLogDrop.item_id == item_id,
        CollectionLogDrop.discord_id.isnot(None),
    ).order_by(CollectionLogDrop.timestamp.desc()).all()
    for drop in drop_rows:
        member_drops = drops_by_member.setdefault(drop.discord_id, [])
        if len(member_drops) < MAX_DROPS_PER_MEMBER:
            member_drops.append({
                "id": str(drop.id),
                "screenshot": drop.screenshot,
                "source": drop.source,
                "obtained_at": drop.timestamp.isoformat() if drop.timestamp else None,
            })

    rows = db.session.query(
        Users.discord_id,
        Users.runescape_name,
        Users.discord_avatar_url,
        Users.rank,
        func.count(CollectionLogDrop.id).label("count"),
        func.min(CollectionLogDrop.timestamp).label("first_obtained"),
        func.max(CollectionLogDrop.timestamp).label("last_obtained"),
    ).join(
        CollectionLogDrop, CollectionLogDrop.discord_id == Users.discord_id
    ).filter(
        CollectionLogDrop.item_id == item_id
    ).group_by(
        Users.discord_id, Users.runescape_name, Users.discord_avatar_url, Users.rank
    ).order_by(func.min(CollectionLogDrop.timestamp)).all()

    return jsonify([
        {
            "discord_id": discord_id,
            "runescape_name": runescape_name,
            "discord_avatar_url": discord_avatar_url,
            "rank": rank,
            "count": count,
            "first_obtained": first_obtained.isoformat() if first_obtained else None,
            "last_obtained": last_obtained.isoformat() if last_obtained else None,
            "drops": drops_by_member.get(discord_id, []),
        }
        for discord_id, runescape_name, discord_avatar_url, rank, count, first_obtained, last_obtained in rows
    ])


@app.route("/collection-log/items", methods=['GET'])
def get_collection_log_item_ids():
    """Distinct OSRS item ids in the catalog — consumed by stabiliserver's drop filter."""
    ids = [row[0] for row in db.session.query(distinct(CollectionLogItem.item_id)).all()]
    return jsonify(ids)


@app.route("/collection-log/recent", methods=['GET'])
def get_collection_log_recent():
    """First time each member received each collection log item, newest first.

    Deduplicated: a member who gets the same item repeatedly appears once for it,
    at their earliest drop. Without this the feed is dominated by whoever is
    farming one boss. Per-member counts still come from /collection-log/summary,
    which counts every drop.

    Paginated with the same envelope as /splits so the website can share its
    pagination handling. Falls back to the drop's own rsn when the drop was never
    matched to a member (discord_id is nullable, so it can't be the group key).
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    per_page = max(1, min(per_page, 100))

    player = func.coalesce(CollectionLogDrop.discord_id, CollectionLogDrop.rsn)

    # DISTINCT ON keeps the first row of each group, so ordering ascending by
    # timestamp within (player, item) picks each member's earliest drop.
    firsts = (
        db.session.query(CollectionLogDrop)
        .distinct(player, CollectionLogDrop.item_id)
        .order_by(player, CollectionLogDrop.item_id, CollectionLogDrop.timestamp.asc())
        .subquery()
    )
    drop = aliased(CollectionLogDrop, firsts)

    query = (
        db.session.query(drop, Users.runescape_name)
        .outerjoin(Users, Users.discord_id == drop.discord_id)
        .order_by(drop.timestamp.desc())
    )

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [
            {
                "id": str(row.id),
                "discord_id": row.discord_id,
                "runescape_name": runescape_name or row.rsn,
                "item_id": row.item_id,
                "item_name": row.item_name,
                "source": row.source,
                "quantity": row.quantity,
                "obtained_at": row.timestamp.isoformat() if row.timestamp else None,
            }
            for row, runescape_name in pagination.items
        ],
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    })
