from flask import Blueprint, jsonify, request

from app import db
from app.players.models import Player

players_bp = Blueprint("players", __name__)


def _include_flag(param_name: str, default: bool = False) -> bool:
    value = request.args.get(param_name)
    if value is None:
        return default
    return value.strip().lower() == "true"


@players_bp.route("/players", methods=["GET"])
def list_players():
    include_scores = _include_flag("includeScores")
    players = Player.query.order_by(Player.username.asc()).all()
    return jsonify([player.to_dict(include_scores=include_scores) for player in players])


@players_bp.route("/players", methods=["POST"])
def create_player():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()

    if not username:
        return jsonify({"error": "Username is required"}), 400

    if Player.query.filter_by(username=username).first():
        return jsonify({"error": "Username is already taken"}), 409

    player = Player(username=username)
    db.session.add(player)
    db.session.commit()

    return jsonify(player.to_dict()), 201


@players_bp.route("/players/availability", methods=["GET"])
def check_username_availability():
    username = (request.args.get("username") or "").strip()
    if not username:
        return jsonify({"error": "Username query parameter is required"}), 400

    is_taken = Player.query.filter_by(username=username).first() is not None
    return jsonify({"username": username, "available": not is_taken})


@players_bp.route("/players/<string:username>", methods=["GET"])
def get_player_details(username: str):
    include_scores = _include_flag("includeScores", default=True)

    player = Player.query.filter_by(username=username).first()
    if not player:
        return jsonify({"error": "Player not found"}), 404

    return jsonify(player.to_dict(include_scores=include_scores))


@players_bp.route("/players/<int:player_id>", methods=["GET"])
def get_player_details_by_id(player_id: int):
    include_scores = _include_flag("includeScores", default=True)

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    return jsonify(player.to_dict(include_scores=include_scores))
