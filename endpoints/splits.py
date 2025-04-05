from app import app, db
from helper.helpers import ModelEncoder
from flask import request, jsonify
from models.models import Splits, Users
import json
import requests
from datetime import datetime
from helper.clan_points_helper import increment_clan_points, PointTag

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
    if user is None:
        return "Could not find User", 404
    data.id = None
    if int(data.group_size) <= 0:
        return "Group size cannot be less than or equal to zero", 400
    if int(data.item_price) <= 0:
        return "Item price cannot be less than or equal to zero", 400
    split_per_person = int(data.item_price) / int(data.group_size)
    if split_per_person < 1_000_000:
        return "Split per person cannot be less than 1,000,000", 400
    data.split_contribution = int((int(data.item_price) / int(data.group_size)) * (int(data.group_size) - 1)) # Truncating the split contribution to the nearest integer

    split_points = data.split_contribution * (10 / 4_000_000)
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

    splits = splits_query.all()
    return jsonify([split.serialize() for split in splits])

