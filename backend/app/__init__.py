from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import os
from dotenv import load_dotenv
from flask_cors import CORS  # For enabling CORS

# Load environment variables
load_dotenv()

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Configure app with environment variables
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///scores.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["IMAGE_ENDPOINT"] = os.getenv("IMAGE_ENDPOINT", "http://localhost:5000/images/")
    app.config["PORT"] = os.getenv("API_PORT", "5000")
    app.config["HOST"] = os.getenv("API_HOST", "http://localhost")
    app.config["BASE_URL"] = f"{app.config['HOST']}:{app.config['PORT']}"

    # Initialize the CORS extension
    CORS(app, resources={r"/*": {"origins": os.getenv("CLIENT_ORIGIN", "http://localhost:5173")}})

    # Initialize the database with the app
    db.init_app(app)

    # Register blueprints
    from app.players.routes import players_bp
    from app.stages.routes import stages_bp
    from app.scores.routes import scores_bp
    from app.media.routes import media_bp
    from app.rounds.routes import rounds_bp

    app.register_blueprint(players_bp)
    app.register_blueprint(stages_bp)
    app.register_blueprint(scores_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(rounds_bp)

    return app
