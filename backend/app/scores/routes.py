from __future__ import annotations

from typing import Any, Dict, Iterable, List

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app import db
from app.players.models import Player
from app.scores.models import LevelScore, StageScore
from app.stages.models import Stage

scores_bp = Blueprint("scores", __name__)


def _resolve_stage(identifier) -> Stage | None:
    if identifier is None:
        return None

    if isinstance(identifier, int):
        return Stage.query.get(identifier)

    if isinstance(identifier, str):
        identifier = identifier.strip()
        if not identifier:
            return None

        if identifier.isdigit():
            stage = Stage.query.get(int(identifier))
            if stage:
                return stage

        return Stage.query.filter(func.lower(Stage.code) == identifier.lower()).first()

    return None


def _resolve_player(player_id=None, username: str | None = None) -> Player | None:
    if player_id:
        player = Player.query.get(player_id)
        if player:
            return player

    if username:
        normalized = username.strip()
        if normalized:
            return (
                Player.query.filter(func.lower(Player.username) == normalized.lower())
                .first()
            )

    return None


def _parse_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off"}:
            return False
    return None


def _parse_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sort_overall(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            -row.get("overallScore", 0),
            row["overallTime"] if row.get("overallTime") is not None else float("inf"),
            (row.get("username") or "").lower(),
        ),
    )


@scores_bp.route("/scores/stages", methods=["GET"])
def list_stage_leaderboards():
    limit = request.args.get("limit", type=int)
    include_levels = _parse_bool(request.args.get("includeLevels")) or False
    include_incomplete = _parse_bool(request.args.get("includeIncomplete")) or False

    stages = Stage.query.order_by(Stage.code.asc()).all()
    response = [
        stage.to_dict(
            include_scores=True,
            include_levels=include_levels,
            limit=limit,
            only_completed=not include_incomplete,
        )
        for stage in stages
    ]

    return jsonify(response)


@scores_bp.route("/scores/stages/<string:stage_identifier>", methods=["GET"])
def get_stage_leaderboard(stage_identifier: str):
    stage = _resolve_stage(stage_identifier)
    if not stage:
        return jsonify({"error": "Stage not found"}), 404

    include_levels = _parse_bool(request.args.get("includeLevels"))
    include_levels = True if include_levels is None else include_levels
    include_incomplete = _parse_bool(request.args.get("includeIncomplete")) or False

    scores_query = stage.stage_scores
    if not include_incomplete:
        scores_query = scores_query.filter(StageScore.is_complete.is_(True))

    scores_query = scores_query.order_by(
        StageScore.total_score.desc(),
        StageScore.total_time.is_(None),
        StageScore.total_time.asc(),
        StageScore.updated_at.asc(),
    )

    scores = [
        score.to_summary_dict(include_levels=bool(include_levels))
        for score in scores_query
    ]

    return jsonify({"stage": stage.to_dict(), "scores": scores})


@scores_bp.route("/scores/overall", methods=["GET"])
def overall_leaderboard():
    results = (
        db.session.query(
            Player.username,
            func.sum(StageScore.total_score),
            func.sum(StageScore.total_time),
            func.sum(StageScore.total_distance),
            func.count(StageScore.id),
            func.max(StageScore.updated_at),
        )
        .join(StageScore, StageScore.player_id == Player.id)
        .filter(StageScore.is_complete.is_(True))
        .group_by(Player.id, Player.username)
        .all()
    )

    leaderboard: List[Dict[str, Any]] = []
    for username, total_score, total_time, total_distance, stages_completed, last_played in results:
        overall_time_value = float(total_time) if total_time is not None else None
        overall_distance_value = float(total_distance) if total_distance is not None else None

        leaderboard.append(
            {
                "username": username,
                "overallScore": float(total_score or 0),
                "overallTime": overall_time_value,
                "overallDistance": overall_distance_value,
                "stagesCompleted": int(stages_completed or 0),
                "lastPlayedAt": last_played.isoformat() if last_played else None,
            }
        )

    return jsonify(_sort_overall(leaderboard))


@scores_bp.route("/scores/players/<string:username>", methods=["GET"])
def player_scores(username: str):
    player = _resolve_player(username=username)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    include_incomplete = _parse_bool(request.args.get("includeIncomplete")) or False

    scores_query = player.stage_scores
    if not include_incomplete:
        scores_query = scores_query.filter(StageScore.is_complete.is_(True))

    scores_query = scores_query.order_by(StageScore.updated_at.desc())
    stage_scores = list(scores_query)

    completed_scores = [score for score in stage_scores if score.is_complete]

    player_payload = {
        "id": player.id,
        "username": player.username,
        "createdAt": player.created_at.isoformat(),
        "stagesCompleted": len(completed_scores),
        "overallScore": float(
            sum(score.total_score for score in completed_scores if score.total_score is not None)
        ),
        "overallTime": float(
            sum(score.total_time for score in completed_scores if score.total_time is not None)
        )
        if completed_scores
        else 0.0,
        "overallDistance": float(
            sum(score.total_distance for score in completed_scores if score.total_distance is not None)
        )
        if completed_scores
        else 0.0,
    }

    scores_payload = [score.to_summary_dict(include_levels=True) for score in stage_scores]

    return jsonify({"player": player_payload, "scores": scores_payload})


@scores_bp.route("/scores/stages", methods=["POST"])
def submit_stage_score():
    payload = request.get_json(silent=True) or {}

    player_id = payload.get("playerId")
    username = payload.get("username")
    stage_identifier = payload.get("stageId") or payload.get("stage") or payload.get("stageCode")
    total_score = payload.get("totalScore")
    total_time = payload.get("totalTime")
    total_distance = payload.get("totalDistance")
    completed_levels = payload.get("completedLevels")
    is_complete = payload.get("isComplete")
    levels_payload = payload.get("levels") or []
    stage_name_hint = payload.get("stageName") or payload.get("stageDisplayName")
    declared_total_levels = _parse_int(payload.get("totalLevels"))
    if declared_total_levels is not None and declared_total_levels < 0:
        return jsonify({"error": "totalLevels must be greater than or equal to 0"}), 400

    if total_score is None:
        return jsonify({"error": "totalScore is required"}), 400

    normalized_stage_identifier = None
    if stage_identifier is not None:
        normalized_stage_identifier = str(stage_identifier).strip()
        if not normalized_stage_identifier:
            normalized_stage_identifier = None

    stage = _resolve_stage(normalized_stage_identifier)

    if not stage:
        if not normalized_stage_identifier:
            return jsonify({"error": "stageId is required"}), 400

        inferred_total_levels = declared_total_levels
        if inferred_total_levels is None and levels_payload:
            inferred_total_levels = len(levels_payload)

        stage = Stage(
            code=normalized_stage_identifier,
            display_name=stage_name_hint,
            total_levels=inferred_total_levels,
        )
        db.session.add(stage)
        db.session.flush()
    else:
        updated = False
        if stage_name_hint and stage.display_name != stage_name_hint:
            stage.display_name = stage_name_hint
            updated = True

        inferred_total_levels = declared_total_levels
        if inferred_total_levels is None and levels_payload:
            inferred_total_levels = len(levels_payload)

        if inferred_total_levels is not None:
            if stage.total_levels is None or stage.total_levels != inferred_total_levels:
                stage.total_levels = inferred_total_levels
                updated = True

        if updated:
            db.session.flush()

    player = _resolve_player(player_id=player_id, username=username)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    total_score_value = _parse_float(total_score)
    if total_score_value is None:
        return jsonify({"error": "totalScore must be a number"}), 400

    total_time_value = _parse_float(total_time)
    total_distance_value = _parse_float(total_distance)
    completed_levels_value = _parse_int(completed_levels)

    if completed_levels_value is None:
        completed_levels_value = len(levels_payload)

    is_complete_value = _parse_bool(is_complete)
    if is_complete_value is None:
        if stage.total_levels is not None and stage.total_levels > 0:
            is_complete_value = completed_levels_value >= stage.total_levels
        else:
            is_complete_value = True

    prepared_levels: List[Dict[str, Any]] = []
    for index, raw_level in enumerate(levels_payload):
        level_id = raw_level.get("levelId") or raw_level.get("level_id")
        if not level_id:
            return jsonify({"error": f"levels[{index}].levelId is required"}), 400

        prepared_levels.append(
            {
                "stage_id": stage.id,
                "level_id": str(level_id),
                "level_name": raw_level.get("levelName") or raw_level.get("level_name"),
                "order": _parse_int(raw_level.get("order")) or index + 1,
                "score": _parse_float(raw_level.get("score")),
                "time": _parse_float(raw_level.get("time")),
                "distance": _parse_float(raw_level.get("distance")),
            }
        )

    stage_score = StageScore.query.filter_by(player_id=player.id, stage_id=stage.id).first()
    was_new = False
    if not stage_score:
        stage_score = StageScore(player_id=player.id, stage_id=stage.id)
        db.session.add(stage_score)
        was_new = True

    stage_score.total_score = total_score_value
    stage_score.total_time = total_time_value
    stage_score.total_distance = total_distance_value
    stage_score.completed_levels = completed_levels_value
    stage_score.is_complete = bool(is_complete_value)

    stage_score.levels = [LevelScore(**level_data) for level_data in prepared_levels]

    db.session.commit()

    response_payload = stage_score.to_summary_dict(include_levels=True)
    status_code = 201 if was_new else 200
    return jsonify(response_payload), status_code


@scores_bp.route("/scores", methods=["POST"])
def submit_stage_score_alias():
    return submit_stage_score()
