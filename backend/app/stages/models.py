from datetime import datetime
from typing import Optional

from app import db


class Stage(db.Model):
    __tablename__ = "stages"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(128))
    total_levels = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    stage_scores = db.relationship(
        "StageScore",
        back_populates="stage",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(
        self,
        include_scores: bool = False,
        include_levels: bool = False,
        limit: Optional[int] = None,
        only_completed: bool = True,
    ) -> dict:
        data = {
            "id": self.id,
            "stageId": self.code,
            "stageName": self.display_name,
            "totalLevels": self.total_levels,
            "createdAt": self.created_at.isoformat(),
        }

        if include_scores:
            from app.scores.models import StageScore

            query = self.stage_scores
            if only_completed:
                query = query.filter(StageScore.is_complete.is_(True))

            query = query.order_by(
                StageScore.total_score.desc(),
                StageScore.total_time.is_(None),
                StageScore.total_time.asc(),
                StageScore.updated_at.asc(),
            )
            if limit:
                query = query.limit(limit)

            data["scores"] = [
                score.to_summary_dict(include_levels=include_levels)
                for score in query
            ]

        return data
