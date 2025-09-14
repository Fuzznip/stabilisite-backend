import os

import logging
import json
from logging.config import dictConfig

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask import Flask, render_template
from dotenv import load_dotenv
from flask_swagger_ui import get_swaggerui_blueprint
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
from scripts.combine_swagger import combine_swagger_files

load_dotenv()

# Configure logging before creating the Flask app
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# Define logging configuration dictionary
dictConfig({
    'version': 1,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        },
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'detailed',
            'level': LOG_LEVEL
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'detailed',
            'filename': 'stability-backend.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'level': LOG_LEVEL
        }
    },
    'root': {
        'level': LOG_LEVEL,
        'handlers': ['console', 'file']
    },
    # You can also set levels for specific modules/packages
    'loggers': {
        'event_handlers': {
            'level': LOG_LEVEL,
            'handlers': ['console', 'file'],
            'propagate': False
        },
        'endpoints': {
            'level': LOG_LEVEL,
            'handlers': ['console', 'file'],
            'propagate': False
        },
        # Set SQLAlchemy to be less verbose (only show warnings and errors)
        'sqlalchemy.engine': {
            'level': 'WARNING',
            'handlers': ['console', 'file'],
            'propagate': False
        },
        # Flask's internal logger - Control its verbosity
        'werkzeug': {
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False
        }
    }
})

DATABASE_USERNAME = os.getenv("DATABASE_USERNAME")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")
DATABASE_URL = os.getenv("DATABASE_URL")
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI']=f"postgresql://{DATABASE_USERNAME}:{DATABASE_PASSWORD}@{DATABASE_URL}"
app_context = app.app_context()
db = SQLAlchemy(app)

cred = credentials.Certificate(json.loads(FIREBASE_CREDENTIALS))
firebase_admin.initialize_app(FIREBASE_CREDENTIALS)
firestore_db = firestore.client()

migrate = Migrate(app, db)

# Ensure swagger.json is generated at app startup
project_root = os.path.dirname(os.path.abspath(__file__))
swagger_input_dir = os.path.join(project_root, "static/swagger")
swagger_output_file = os.path.join(project_root, "static/swagger.json")

# Ensure the static directory exists
if not os.path.exists(os.path.join(project_root, "static")):
    os.makedirs(os.path.join(project_root, "static"))

# Generate the combined swagger file
combine_swagger_files(swagger_input_dir, swagger_output_file)

# Configure Swagger UI
SWAGGER_URL = '/docs'  # URL for exposing Swagger UI
API_URL = '/static/swagger.json'  # Path to the Swagger JSON file

# Register Swagger UI blueprint
swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Needed to auto generate tables using SQLAlchemy
from models import models, stability_party_3, bingo

# make app aware of all endpoints
from endpoints import users, announcements, splits, applications, diary, ranks, raid_tier, discord_management
from endpoints.events import item_whitelist, submit, sp3_moderation, sp3_game, events, items, bingo

# Initialize event handlers
from event_handlers import event_handler_init

if __name__ == '__main__':
    app.run(debug=False)

