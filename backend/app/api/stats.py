from flask import Blueprint, jsonify

from ..models import PracticeSession
from .auth import require_user

stats_bp = Blueprint("stats", __name__)

SCORE_MAP = {
    "A+": 5.0,
    "A": 4.7,
    "A-": 4.4,
    "B+": 4.0,
    "B": 3.7,
    "B-": 3.4,
    "C+": 3.0,
    "C": 2.7,
    "C-": 2.4,
}


def _average_score(rows):
    values = []
    labels = []
    for row in rows:
        if row.result and row.result.score:
            labels.append(row.result.score)
            if row.result.score in SCORE_MAP:
                values.append(SCORE_MAP[row.result.score])
    if not values:
        return {"label": "-", "numeric": None}
    avg = sum(values) / len(values)
    closest = min(SCORE_MAP, key=lambda label: abs(SCORE_MAP[label] - avg))
    return {"label": closest, "numeric": round(avg, 2)}


@stats_bp.get("/stats/summary")
def summary():
    user = require_user()
    query = PracticeSession.query
    if user.role != "teacher":
        query = query.filter_by(user_id=user.id)
    rows = query.order_by(PracticeSession.created_at.asc()).all()
    completed = [row for row in rows if row.status == "completed"]
    return jsonify(
        {
            "total_practices": len(rows),
            "completed_practices": len(completed),
            "estimated_minutes": sum(max(row.interval_seconds, 1) for row in rows) // 60,
            "average_score": _average_score(completed),
            "recent": [row.to_dict() for row in list(reversed(rows[-5:]))],
        }
    )
