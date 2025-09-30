from datetime import datetime

from app import db


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    stage_scores = db.relationship(
        "StageScore",
        back_populates="player",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_scores: bool = False) -> dict:
        data = {
            "id": self.id,
            "username": self.username,
            "createdAt": self.created_at.isoformat(),
        }

        if include_scores:
            from app.scores.models import StageScore

            scores_query = self.stage_scores.order_by(StageScore.updated_at.desc())
            scores = list(scores_query)

            completed_scores = [score for score in scores if score.is_complete]

            total_score = sum(score.total_score for score in completed_scores if score.total_score is not None)
            total_time = sum(score.total_time for score in completed_scores if score.total_time is not None)
            total_distance = sum(
                score.total_distance for score in completed_scores if score.total_distance is not None
            )

            data.update(
                {
                    "stagesCompleted": len(completed_scores),
                    "overallScore": total_score,
                    "overallTime": total_time,
                    "overallDistance": total_distance,
                    "scores": [score.to_summary_dict(include_levels=True) for score in scores],
                }
            )

        return data
