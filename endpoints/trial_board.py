"""Register the backend trial API without changing existing application decisions."""
from app import app, db
from services.trial_board import TrialBoard
from services.trial_board_api import make_blueprint

app.register_blueprint(make_blueprint(lambda settings: TrialBoard(db.engine, shared_pool=settings.shared_pool)))
