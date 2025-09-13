from app import app, db
from flask import request, jsonify
from models.models import Events, EventTeams
from datetime import datetime, timezone
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/events/teams", methods=['GET'])
def get_teams():
    # Find the latest bingo event
    event = Events.query.filter(
        Events.type == "BINGO"
    ).order_by(Events.start_time.desc()).first()

    # Find the teams with that event ID
    if event is None:
        return jsonify({"error": "No active Bingo event found"}), 404

    teams = EventTeams.query.filter_by(event_id=event.id).all()
    # return a list of the data field from each team
    if not teams:
        return jsonify({"error": "No teams found for the Bingo event"}), 404
    
    data = [team.data for team in teams]
    return jsonify(data), 200

@app.route("/events/board", methods=['GET'])
def get_events():
    # Find the latest bingo event
    event = Events.query.filter(
        Events.type == "BINGO"
    ).order_by(Events.start_time.desc()).first()

    if event is None:
        return jsonify({"error": "No active Bingo event found"}), 404
    
    # Return the event data field
    return jsonify(event.data), 200
