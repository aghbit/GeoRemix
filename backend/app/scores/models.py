from datetime import datetime

from app import db


class StageScore(db.Model):
    __tablename__ = "stage_scores"
    __table_args__ = (
        db.UniqueConstraint("player_id", "stage_id", name="uq_stage_scores_player_stage"),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    stage_id = db.Column(db.Integer, db.ForeignKey("stages.id", ondelete="CASCADE"), nullable=False)
    total_score = db.Column(db.Float, nullable=False)
    total_time = db.Column(db.Float)
    total_distance = db.Column(db.Float)
    completed_levels = db.Column(db.Integer, default=0, nullable=False)
    is_complete = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    player = db.relationship("Player", back_populates="stage_scores")
    stage = db.relationship("Stage", back_populates="stage_scores")
    levels = db.relationship(
        "LevelScore",
        back_populates="stage_score",
        cascade="all, delete-orphan",
        order_by="LevelScore.order",
    )

    def to_summary_dict(self, include_levels: bool = False) -> dict:
        data = {
            "id": self.id,
            "playerId": self.player_id,
            "username": getattr(self.player, "username", None),
            "stageId": getattr(self.stage, "code", None),
            "stageName": getattr(self.stage, "display_name", None),
            "totalScore": self.total_score,
            "totalTime": self.total_time,
            "totalDistance": self.total_distance,
            "completedLevels": self.completed_levels,
            "isComplete": self.is_complete,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }

        if include_levels:
            data["levels"] = [level.to_dict() for level in self.levels]

        return data


class LevelScore(db.Model):
    __tablename__ = "level_scores"
    __table_args__ = (
        db.Index("ix_level_scores_stage_level", "stage_id", "level_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    stage_score_id = db.Column(
        db.Integer,
        db.ForeignKey("stage_scores.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_id = db.Column(db.Integer, db.ForeignKey("stages.id", ondelete="CASCADE"), nullable=False)
    level_id = db.Column("level_code", db.String(64), nullable=False)
    level_name = db.Column(db.String(128))
    order = db.Column("order_index", db.Integer)
    score = db.Column(db.Float)
    time = db.Column("time_taken", db.Float)
    distance = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    stage_score = db.relationship("StageScore", back_populates="levels")
    stage = db.relationship("Stage", backref=db.backref("level_scores", lazy="dynamic"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "stageScoreId": self.stage_score_id,
            "levelId": self.level_id,
            "levelName": self.level_name,
            "order": self.order,
            "score": self.score,
            "time": self.time,
            "distance": self.distance,
            "createdAt": self.created_at.isoformat(),
        }
