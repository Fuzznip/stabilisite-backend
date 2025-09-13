from app import db
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from helper.helpers import Serializer
import uuid

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
    tile_id = db.Column(UUID(as_uuid=True), db.ForeignKey('bingo_tiles.id', ondelete="CASCADE"))  # Cascade delete
    challenges = db.Column(ARRAY(UUID(as_uuid=True)), nullable=False)  # List of challenges for the bingo task

    def serialize(self):
        return Serializer.serialize(self)
    
# Helper class for Bingo Teams
class BingoTriggerProgress:
    name: str
    value: int

    def __init__(self, name: str, value: int):
        self.name = name
        self.value = value

    def __init__(self, name: str, value: int):
        self.name = name
        self.value = value

class BingoTaskProgress:
    task_id: str
    task: str
    completed: bool
    value: int
    required: int
    proof: str
    log: list[BingoTriggerProgress]

class BingoTileProgress:
    tile_id: str
    tile_id: str
    name: str
    progress: list[list[BingoTaskProgress]]

class BingoTeam:
    team_id: str
    name: str
    members: list[str]
    image_url: str
    points: int
    board_state: list[int] # 0 = not completed, 1 = bronze, 2 = silver, 3 = gold
    board_progress: list[BingoTileProgress]

    def get_tile_progress(self, tile_id: int) -> BingoTileProgress | None:
        for tile in self.board_progress:
            if tile.tile_id == tile_id:
                return tile
        return None
    
    def update_tile_progress(self, new_tile_progress: BingoTileProgress) -> None:
        for i, tile in enumerate(self.board_progress):
            if tile.tile_id == new_tile_progress.tile_id:
                self.board_progress[i] = new_tile_progress
                return
        self.board_progress.append(new_tile_progress)

class BingoTask:
    task_id: int
    task: str
    required: int
    triggers: list[str | list[str]]

class BingoTile:
    tile_id: int
    name: str
    tasks: list[BingoTask]
