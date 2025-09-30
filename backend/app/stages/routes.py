from __future__ import annotations

from typing import Any, Optional

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from app import db
from app.stages.models import Stage

stages_bp = Blueprint("stages", __name__)


def _include_flag(param_name: str, *, default: bool = False) -> bool:
    value = request.args.get(param_name)
    if value is None:
        return default
    return value.strip().lower() == "true"


def _parse_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_stage_code(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        str_value = str(int(value)) if float(value).is_integer() else str(value)
    else:
        str_value = str(value)

    normalized = str_value.strip()
    return normalized or None


def _resolve_stage(identifier: Any) -> Stage | None:
    if identifier is None:
        return None

    if isinstance(identifier, Stage):
        return identifier

    if isinstance(identifier, int):
        return Stage.query.get(identifier)

    normalized = _normalize_stage_code(identifier)
    if not normalized:
        return None

    if normalized.isdigit():
        stage = Stage.query.get(int(normalized))
        if stage:
            return stage

    return Stage.query.filter(func.lower(Stage.code) == normalized.lower()).first()


def _update_stage_metadata(
    stage: Stage,
    *,
    display_name: Optional[str],
    total_levels: Optional[int],
) -> None:
    updated = False

    if display_name and stage.display_name != display_name:
        stage.display_name = display_name
        updated = True

    if total_levels is not None:
        if stage.total_levels is None or stage.total_levels != total_levels:
            stage.total_levels = total_levels
            updated = True

    if updated:
        db.session.flush()


@stages_bp.route("/stages", methods=["GET"])
def list_stages():
    include_scores = _include_flag("includeScores", default=True)
    include_levels = _include_flag("includeLevels")
    include_incomplete = _include_flag("includeIncomplete")
    limit = request.args.get("limit", type=int)

    stages = Stage.query.order_by(Stage.code.asc()).all()
    return jsonify(
        [
            stage.to_dict(
                include_scores=include_scores,
                include_levels=include_levels,
                limit=limit,
                only_completed=not include_incomplete,
            )
            for stage in stages
        ]
    )


@stages_bp.route("/stages", methods=["POST"])
def create_or_update_stage():
    payload = request.get_json(silent=True) or {}

    stage_identifier = (
        payload.get("stageId")
        or payload.get("code")
        or payload.get("stageCode")
        or payload.get("id")
    )
    stage_code = _normalize_stage_code(stage_identifier)

    if not stage_code:
        return jsonify({"error": "stageId is required"}), 400

    display_name = payload.get("stageName") or payload.get("displayName")
    total_levels = _parse_int(payload.get("totalLevels"))

    stage = _resolve_stage(stage_code)
    created = False

    if not stage:
        stage = Stage(code=stage_code, display_name=display_name, total_levels=total_levels)
        db.session.add(stage)
        db.session.flush()
        created = True
    else:
        _update_stage_metadata(stage, display_name=display_name, total_levels=total_levels)

    db.session.commit()

    response = stage.to_dict(include_scores=False)
    status_code = 201 if created else 200
    return jsonify(response), status_code


@stages_bp.route("/stages/<stage_identifier>", methods=["GET"])
def get_stage_details(stage_identifier: str):
    include_scores = _include_flag("includeScores")
    include_levels = _include_flag("includeLevels")
    include_incomplete = _include_flag("includeIncomplete")
    limit = request.args.get("limit", type=int)

    stage = _resolve_stage(stage_identifier)
    if not stage:
        return jsonify({"error": "Stage not found"}), 404

    return jsonify(
        stage.to_dict(
            include_scores=include_scores,
            include_levels=include_levels,
            limit=limit,
            only_completed=not include_incomplete,
        )
    )


@stages_bp.route("/stages/<stage_identifier>", methods=["PATCH"])
def update_stage(stage_identifier: str):
    stage = _resolve_stage(stage_identifier)
    if not stage:
        return jsonify({"error": "Stage not found"}), 404

    payload = request.get_json(silent=True) or {}
    display_name = payload.get("stageName") or payload.get("displayName")
    provided_total_levels = payload.get("totalLevels")
    total_levels = _parse_int(provided_total_levels)

    if provided_total_levels is not None and total_levels is None:
        return jsonify({"error": "totalLevels must be an integer"}), 400

    _update_stage_metadata(stage, display_name=display_name, total_levels=total_levels)

    include_scores = _include_flag("includeScores")
    include_levels = _include_flag("includeLevels")
    include_incomplete = _include_flag("includeIncomplete")
    limit = request.args.get("limit", type=int)

    db.session.commit()

    return jsonify(
        stage.to_dict(
            include_scores=include_scores,
            include_levels=include_levels,
            limit=limit,
            only_completed=not include_incomplete,
        )
    )
