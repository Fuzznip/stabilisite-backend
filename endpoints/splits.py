from app import app, db
from helper.helpers import ModelEncoder
from flask import request, jsonify
from models.models import Splits, Users
import json
import requests
from datetime import datetime, timezone
from helper.clan_points_helper import increment_clan_points, PointTag
import decimal

@app.route("/splits", methods=['POST'])
def create_split():
    data = Splits(**request.get_json())
    if data is None:
        return "No JSON received", 400
    if data.item_id is None:
        headers = {
            'User-Agent': 'Stabilisite Backend',
            'From': 'stabilityosrs@gmail.com'
        }
        mapping = requests.get(f"https://prices.runescape.wiki/api/v1/osrs/mapping", headers=headers)
        if mapping.status_code != 200:
            return "Could not fetch item mapping from OSRS API. Please provide an item ID or try again later.", 500
        mapping = mapping.json()
        # mapping is an array of objects with id and name, sorted by name
        # do a binary search for the item name in the mapping array
        item_name = data.item_name.lower()
        low = 0
        high = len(mapping) - 1
        while low <= high:
            mid = (low + high) // 2
            if mapping[mid]['name'].lower() == item_name:
                data.item_id = mapping[mid]['id']
                break
            elif mapping[mid]['name'].lower() < item_name:
                low = mid + 1
            else:
                high = mid - 1

        if data.item_id is None:
            return "Item not found in OSRS API. Please provide a valid item name or ID.", 404
        
    user = Users.query.filter_by(discord_id=data.user_id).first()
    if user is None or not user.is_active:
        return "Could not find User", 404
    if user.is_member is False:
        return "User is not a member", 400
    data.id = None
    if int(data.group_size) <= 0:
        return "Group size cannot be less than or equal to zero", 400
    if int(data.item_price) <= 0:
        return "Item price cannot be less than or equal to zero", 400
    split_per_person = int(data.item_price) / int(data.group_size)
    if split_per_person < 1_000_000:
        return "Split per person cannot be less than 1,000,000", 400
    data.split_contribution = int(split_per_person * (int(data.group_size) - 1)) # Truncating the split contribution to the nearest integer
    # Get the current time in UTC
    data.timestamp = datetime.now(timezone.utc)

    split_points = data.split_contribution * decimal.Decimal(10) / decimal.Decimal(4_000_000)
    split_points = round(split_points, 2)

    increment_clan_points(
        user_id=data.user_id,
        points=split_points,
        tag=PointTag.SPLIT,
        message=f"Split: {data.item_name}"
    )

    db.session.add(data)
    db.session.commit()
    return json.dumps(data.serialize(), cls=ModelEncoder)

@app.route("/splits", methods=['GET'])
def get_splits():
    begin_date = request.args.get('begin_date')
    end_date = request.args.get('end_date')
    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # Clamp per_page to reasonable bounds
    per_page = max(1, min(per_page, 100))

    splits_query = Splits.query

    if begin_date:
        try:
            begin_date = datetime.strptime(begin_date, "%Y-%m-%d")
            splits_query = splits_query.filter(Splits.timestamp >= begin_date)
        except ValueError:
            return "Invalid begin_date format. Use YYYY-MM-DD.", 400

    if end_date:
        try:
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
            splits_query = splits_query.filter(Splits.timestamp <= end_date)
        except ValueError:
            return "Invalid end_date format. Use YYYY-MM-DD.", 400

    # Order by timestamp descending for consistent results
    splits_query = splits_query.order_by(Splits.timestamp.desc())

    # If page is provided, use pagination; otherwise return all results
    if page is not None:
        pagination = splits_query.paginate(page=page, per_page=per_page, error_out=False)
        return jsonify({
            "items": [split.serialize() for split in pagination.items],
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev
        })

    return jsonify([split.serialize() for split in splits_query.all()])

@app.route("/splits/<id>", methods=['PUT'])
def update_split(id):
    split = Splits.query.filter_by(id=id).first()
    if not split:
        return "Split not found", 404

    data = request.get_json()
    split.item_name = data.get("item_name", split.item_name)
    split.item_price = data.get("item_price", split.item_price)
    split.group_size = data.get("group_size", split.group_size)
    split.split_contribution = data.get("split_contribution", split.split_contribution)
    db.session.commit()
    return json.dumps(split.serialize(), cls=ModelEncoder)

@app.route("/splits/<id>", methods=['DELETE'])
def delete_split(id):
    split = Splits.query.filter_by(id=id).first()
    if not split:
        return "Split not found", 404
    
    # Remove the points from the user
    user = Users.query.filter_by(discord_id=split.user_id).first()
    if user:
        split_points = split.split_contribution * decimal.Decimal(10/4_000_000)  # Updated to use decimal.Decimal
        split_points = round(split_points, 2)
        increment_clan_points(
            user_id=user.discord_id,
            points=-split_points,
            tag=PointTag.SPLIT,
            message=f"Split deleted: {split.item_name}"
        )

    db.session.delete(split)
    db.session.commit()
    return "Split deleted successfully", 200

