from __future__ import annotations
from app import db
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from helper.helpers import Serializer
import uuid
import logging

class BingoTiles(db.Model, Serializer):
    __tablename__ = 'bingo_tiles'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = db.Column(UUID(as_uuid=True), db.ForeignKey('events.id', ondelete="CASCADE"))  # Cascade delete
    name = db.Column(db.String, nullable=False)
    index = db.Column(db.Integer, nullable=False)  # Position on the bingo board (0-24 for a 5x5 board)
    data = db.Column(JSONB)  # Store additional data as JSONB for flexibility
    
    def serialize(self):
        return Serializer.serialize(self)

class BingoChallenges(db.Model, Serializer):
    __tablename__ = 'bingo_challenges'
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_index = db.Column(db.Integer)  # Index of the task within the tile (0-2 for a tile with 3 tasks)
    tile_id = db.Column(UUID(as_uuid=True), db.ForeignKey('bingo_tiles.id', ondelete="CASCADE"))  # Cascade delete
    challenges = db.Column(ARRAY(UUID(as_uuid=True)), nullable=False)  # List of challenges for the bingo task
    name = db.Column(db.String, default="")

    def serialize(self):
        return Serializer.serialize(self)
    
# Helper class for Bingo Teams
class BingoTriggerProgress:
    name: str
    value: int

    def __init__(self, name: str, value: int):
        self.name = name
        self.value = value

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value
        }
    
    @staticmethod
    def from_dict(data: dict) -> "BingoTriggerProgress":
        return BingoTriggerProgress(
            name=data.get("name", ""),
            value=data.get("value", 0)
        )
    
class BingoChallengeProgress:
    challenge_id: str
    value: int
    required: int
    completed: bool
    triggers: list[BingoTriggerProgress]
    type: str # e.g., "AND", "OR"

    def to_dict(self) -> dict:
        return {
            "challenge_id": self.challenge_id,
            "value": self.value,
            "required": self.required,
            "completed": self.completed,
            "triggers": [trigger.to_dict() for trigger in self.triggers],
            "type": self.type
        }
    
    @staticmethod
    def from_dict(data: dict) -> "BingoChallengeProgress":
        challenge_progress = BingoChallengeProgress()
        challenge_progress.challenge_id = data.get("challenge_id", "")
        challenge_progress.value = data.get("value", 0)
        challenge_progress.required = data.get("required", 0)
        challenge_progress.completed = data.get("completed", False)
        challenge_progress.triggers = [BingoTriggerProgress.from_dict(trigger) for trigger in data.get("triggers", [])]
        challenge_progress.type = data.get("type", "OR")
        return challenge_progress

class BingoTaskProgress:
    task_id: str
    task_index: str
    completed: bool
    proof: str
    log: list[BingoChallengeProgress]

    def to_dict(self) -> dict:
        return {
            "task_id": str(self.task_id),
            "task_index": str(self.task_index),
            "completed": self.completed,
            "proof": self.proof,
            "log": [entry.to_dict() for entry in self.log]
        }
    
    @staticmethod
    def from_dict(data: dict) -> "BingoTaskProgress":
        task_progress = BingoTaskProgress()
        task_progress.task_id = data.get("task_id", "")
        task_progress.task_index = data.get("task_index", "")
        task_progress.completed = data.get("completed", False)
        task_progress.proof = data.get("proof", "")
        task_progress.log = [BingoChallengeProgress.from_dict(log_entry) for log_entry in data.get("log", [])]
        return task_progress

class BingoTileProgress:
    tile_id: str
    name: str
    progress: list[BingoTaskProgress]

    def get_completed_task_count(self) -> int:
        count = 0
        for task in self.progress:
            if task.completed:
                count += 1
        return count

    def add_task_progress_or(self, task_id: str, task_index: str, event_challenge: "EventChallenges", event_task: "EventTasks", trigger: str, quantity: int | None) -> bool:
        if quantity is None or quantity <= 0:
            quantity = 1  # Default to incrementing by 1 if no quantity is provided
        
        # If progress for this task doesn't exist yet, create it
        task_progress = next((t for t in self.progress if str(t.task_id) == str(task_id)), None)
        if task_progress is None:
            task_progress = BingoTaskProgress()
            task_progress.task_id = task_id
            task_progress.task_index = task_index # Will be filled in later
            task_progress.completed = False
            task_progress.proof = ""
            task_progress.log = []
            self.progress.append(task_progress)

        old_completed_status = task_progress.completed

        # Get the challenge progress object
        challenge_progress = next((c for c in task_progress.log if str(c.challenge_id) == str(event_challenge.id)), None)
        if challenge_progress is None:
            # Init new challenge progress with 0 progress
            challenge_progress = BingoChallengeProgress()
            challenge_progress.challenge_id = str(event_challenge.id)
            challenge_progress.value = quantity if quantity else 1
            challenge_progress.required = event_task.quantity
            challenge_progress.completed = challenge_progress.value >= challenge_progress.required
            if not task_progress.completed:
                task_progress.completed = challenge_progress.completed
            challenge_progress.triggers = [BingoTriggerProgress(name=trigger, value=quantity if quantity else 1)]
            challenge_progress.type = "OR"
            task_progress.log.append(challenge_progress)
            return task_progress.completed and not old_completed_status  # Return True if task was completed now

        # Update existing challenge progress
        challenge_progress.value += quantity if quantity else 1
        challenge_progress.completed = challenge_progress.value >= challenge_progress.required
        if not task_progress.completed:
            task_progress.completed = challenge_progress.completed

        # Update triggers
        for log_entry in challenge_progress.triggers:
            if log_entry.name == trigger:
                log_entry.value += quantity if quantity else 1
                return task_progress.completed and not old_completed_status  # Return True if task was completed now
        challenge_progress.triggers.append(BingoTriggerProgress(name=trigger, value=quantity if quantity else 1))
        return task_progress.completed and not old_completed_status  # Return True if task was completed now

    def add_task_progress_and(self, task_id: str, task_index: str, event_challenge: "EventChallenges", event_task: "EventTasks", trigger: str, quantity: int | None) -> bool:
        return False

    # Add or update progress for a specific task and challenge
    # Returns True if task was completed as a result of this progress addition, False otherwise
    def add_task_progress(self, task_id: str, task_index: str, event_challenge: "EventChallenges", event_task: "EventTasks", trigger: str, quantity: int | None, challenge_type: str) -> bool:
        if challenge_type in ["OR"]:
            return self.add_task_progress_or(task_id, task_index, event_challenge, event_task, trigger, quantity)
        elif challenge_type in ["AND"]:
            return self.add_task_progress_and(task_id, task_index, event_challenge, event_task, trigger, quantity)
        else:
            logging.warning(f"Unknown challenge type {challenge_type} for challenge {event_challenge.id}")
            return False
        
    def to_dict(self) -> dict:
        return {
            "tile_id": str(self.tile_id),
            "name": self.name,
            "progress": [task.to_dict() for task in self.progress]
        }
    
    @staticmethod
    def from_dict(data: dict) -> "BingoTileProgress":
        tile_progress = BingoTileProgress()
        tile_progress.tile_id = str(data.get("tile_id", ""))
        tile_progress.name = data.get("name", "")
        tile_progress.progress = []
        for task_data in data.get("progress", []):
            task_progress = BingoTaskProgress()
            task_progress.task_id = str(task_data.get("task_id", ""))
            task_progress.task_index = task_data.get("task_index", "")
            task_progress.completed = task_data.get("completed", False)
            task_progress.proof = task_data.get("proof", "")
            task_progress.log = [BingoChallengeProgress.from_dict(log_entry) for log_entry in task_data.get("log", [])]
            tile_progress.progress.append(task_progress)
        return tile_progress

class BingoTeam:
    team_id: str
    name: str
    members: list[str]
    image_url: str
    points: int
    board_state: list[int] # 0 = not completed, 1 = bronze, 2 = silver, 3 = gold
    board_progress: list[BingoTileProgress]

    def get_tile_progress(self, tile_id: str) -> BingoTileProgress | None:
        for tile in self.board_progress:
            if str(tile.tile_id) == str(tile_id):
                return tile
        return None
    
    def update_tile_progress(self, new_tile_progress: BingoTileProgress) -> None:
        for i, tile in enumerate(self.board_progress):
            if str(tile.tile_id) == str(new_tile_progress.tile_id):
                self.board_progress[i] = new_tile_progress
                return
        # If tile progress doesn't exist yet, add it
        self.board_progress.append(new_tile_progress)

    def to_dict(self) -> dict:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "members": self.members,
            "image_url": self.image_url,
            "points": self.points,
            "board_state": self.board_state,
            "board_progress": [tile.to_dict() for tile in self.board_progress]
        }

    @staticmethod
    def from_dict(data: dict) -> "BingoTeam":
        team = BingoTeam()
        team.team_id = data.get("team_id", "")
        team.name = data.get("name", "")
        team.members = data.get("members", [])
        team.image_url = data.get("image_url", "")
        team.points = data.get("points", 0)
        team.board_state = data.get("board_state", [0]*25)  # Default to a 5x5 board with all tiles not completed
        team.board_progress = [BingoTileProgress.from_dict(tile_data) for tile_data in data.get("board_progress", [])]
        return team

class BingoTask:
    task_id: int
    task: str
    required: int
    triggers: list[str | list[str]]

class BingoTile:
    tile_id: int
    name: str
    tasks: list[BingoTask]
