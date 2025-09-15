from app import app, db
from flask import request, jsonify
from models.bingo import BingoChallenges, BingoTiles
from models.models import EventChallenges, EventTasks, EventTriggers, Events, EventTeams
from datetime import datetime, timezone
from helper.helpers import ModelEncoder
import json
import logging

@app.route("/teams", methods=['GET'])
def get_bingo_teams():
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

@app.route("/board", methods=['GET'])
def get_bingo_board():
    # Find the latest bingo event
    event = Events.query.filter(
        Events.type == "BINGO"
    ).order_by(Events.start_time.desc()).first()

    if event is None:
        return jsonify({"error": "No active Bingo event found"}), 404
    
    # Loop through each bingo tile
    bingo_tiles: list[BingoTiles] = BingoTiles.query.filter_by(event_id=event.id).all()
    if not bingo_tiles:
        return jsonify({"error": "No bingo tiles found for the Bingo event"}), 404
    
    response = []

    for tile in bingo_tiles:
        tile_data = {
            "id": str(tile.id),
            "name": tile.name, 
            "index": tile.index,
            "tasks": []}
        tile_tasks: list[BingoChallenges] = BingoChallenges.query.filter_by(tile_id=tile.id).all()
        for i, task in enumerate(tile_tasks):
            challenges_list: list[list[str]] = []
            for challenge_id in task.challenges:
                challenge = EventChallenges.query.filter_by(id=challenge_id).first()
                if challenge is None:
                    logging.error(f"Challenge {challenge_id} not found for bingo task {task.id}.")
                    continue

                triggers = []
                for task_id in challenge.tasks:
                    event_task: EventTasks = EventTasks.query.filter_by(id=task_id).first()
                    if event_task is None:
                        logging.error(f"Event task {task_id} not found for challenge {challenge_id}.")
                        continue
                    for trigger_id in event_task.triggers:
                        event_trigger: EventTriggers = EventTriggers.query.filter_by(id=trigger_id).first()
                        if event_trigger is None:
                            logging.error(f"Event trigger {trigger_id} not found for task {task_id}.")
                            continue
                        
                        triggers.append(event_trigger.trigger)
                
                challenges_list.append(triggers)

            task = {
                "id": str(task.id),
                "index": i,             
                "name": challenges_list.join(f" {challenge.type} "),
                "required": challenge_id,
                "triggers": challenges_list,
            }
            tile_data["tasks"].append(task)

    return jsonify(response), 200   
    # Return the event data field
    return jsonify(event.data), 200
