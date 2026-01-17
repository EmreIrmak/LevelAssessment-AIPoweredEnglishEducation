from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case, func

from app.extensions import db
from app.models import (
    CEFRLevel,
    ModuleType,
    Question,
    Report,
    ReportStatus,
    Response,
    Student,
    TestSession,
)


@dataclass(frozen=True)
class InstructorDashboardData:
    kpis: dict[str, Any]
    leaderboard: list[dict[str, Any]]
    charts: dict[str, Any]
    widgets: dict[str, Any]


class InstructorDashboardService:
    @staticmethod
    def build(*, days: int = 7, max_rows: int = 8) -> InstructorDashboardData:
        """Builds instructor dashboard data.

        Notes:
        - Designed for demo-scale SQLite: uses a few simple queries + small N+1 loops.
        - Uses latest session/report per student when available.
        """

        since_dt = datetime.utcnow() - timedelta(days=days)

        total_students = Student.query.count()

        active_student_ids = (
            db.session.query(TestSession.user_id)
            .filter(TestSession.start_time >= since_dt)
            .distinct()
            .all()
        )
        active_this_week = len([r[0] for r in active_student_ids])

        # Completion rate: % of sessions with a READY report (overall, last N days)
        sessions_total = db.session.query(func.count(TestSession.id)).filter(TestSession.start_time >= since_dt).scalar() or 0
        sessions_ready = (
            db.session.query(func.count(Report.id))
            .join(TestSession, TestSession.id == Report.session_id)
            .filter(TestSession.start_time >= since_dt)
            .filter(Report.status == ReportStatus.READY)
            .scalar()
            or 0
        )
        completion_rate = round((sessions_ready / sessions_total * 100.0), 1) if sessions_total else 0.0

        # Avg score from READY reports in timeframe
        avg_score = (
            db.session.query(func.avg(Report.score))
            .join(TestSession, TestSession.id == Report.session_id)
            .filter(TestSession.start_time >= since_dt)
            .filter(Report.status == ReportStatus.READY)
            .scalar()
        )
        avg_score = round(float(avg_score), 1) if avg_score is not None else 0.0

        # Leaderboard rows: latest session/report per student
        students = Student.query.order_by(Student.id.desc()).limit(max(50, max_rows * 6)).all()
        leaderboard: list[dict[str, Any]] = []

        module_order = [
            ModuleType.VOCABULARY.value,
            ModuleType.GRAMMAR.value,
            ModuleType.READING.value,
            ModuleType.WRITING.value,
            ModuleType.LISTENING.value,
            ModuleType.SPEAKING.value,
        ]

        level_dist: Counter[str] = Counter()

        def _module_scores_for_session(session_id: int) -> dict[str, float]:
            if not session_id:
                return {}
            totals = (
                db.session.query(Question.module, func.count(Response.id))
                .join(Response, Response.question_id == Question.id)
                .filter(Response.session_id == session_id)
                .group_by(Question.module)
                .all()
            )
            corrects = (
                db.session.query(Question.module, func.count(Response.id))
                .join(Response, Response.question_id == Question.id)
                .filter(Response.session_id == session_id)
                .filter(Response.is_correct == True)  # noqa: E712
                .group_by(Question.module)
                .all()
            )
            total_by_mod = {m.value if m else "": int(c or 0) for (m, c) in totals}
            corr_by_mod = {m.value if m else "": int(c or 0) for (m, c) in corrects}
            out: dict[str, float] = {}
            for name in module_order:
                t = total_by_mod.get(name, 0)
                if t <= 0:
                    continue
                out[name] = round((corr_by_mod.get(name, 0) / t) * 100.0, 1)
            return out

        for s in students:
            last_session = (
                TestSession.query.filter_by(user_id=s.id)
                .order_by(TestSession.start_time.desc())
                .first()
            )
            if not last_session:
                # Still include student in distribution using current_level
                if s.current_level:
                    level_dist[s.current_level.value] += 1
                continue

            last_report = Report.query.filter_by(session_id=last_session.id).first()
            level_val = last_report.level_result.value if (last_report and last_report.level_result) else None

            # Distribution: prefer latest report level; otherwise student's current_level
            dist_level = level_val or (s.current_level.value if s.current_level else None)
            if dist_level:
                level_dist[dist_level] += 1

            module_scores: dict[str, float] = {}
            if last_report and last_report.module_stats_json:
                try:
                    raw = json.loads(last_report.module_stats_json)
                    if isinstance(raw, dict):
                        for k in module_order:
                            v = raw.get(k)
                            if isinstance(v, (int, float)):
                                module_scores[k] = float(v)
                except Exception:
                    module_scores = {}

            if not module_scores:
                module_scores = _module_scores_for_session(last_session.id)

            leaderboard.append(
                {
                    "student": {
                        "id": s.id,
                        "name": s.name,
                        "email": s.email,
                        "level": getattr(s.current_level, "value", None),
                    },
                    "last_attempt": last_session.start_time,
                    "report": {
                        "session_id": last_session.id,
                        "overall": round(float(last_report.score or 0.0), 1) if last_report else None,
                        "level": level_val,
                        "status": (last_report.status.value if (last_report and last_report.status) else "No report"),
                    },
                    "module_scores": module_scores,
                }
            )

        # sort by overall desc when available
        leaderboard.sort(key=lambda r: (r.get("report") or {}).get("overall") or -1, reverse=True)
        leaderboard = leaderboard[:max_rows]

        # CEFR distribution: ensure stable ordering A1..C2
        cefr_levels = [lvl.value for lvl in CEFRLevel]
        cefr_distribution = [{"level": lv, "count": int(level_dist.get(lv, 0))} for lv in cefr_levels]

        # Average by module (directly from responses in timeframe, so it works even without reports)
        # avg = correct / total * 100
        mod_rows = (
            db.session.query(
                Question.module,
                func.count(Response.id).label("total"),
                func.sum(case((Response.is_correct == True, 1), else_=0)).label("correct"),  # noqa: E712
            )
            .join(Response, Response.question_id == Question.id)
            .join(TestSession, TestSession.id == Response.session_id)
            .filter(TestSession.start_time >= since_dt)
            .group_by(Question.module)
            .all()
        )
        totals_by_mod = {m.value if m else "": int(t or 0) for (m, t, _c) in mod_rows}
        corr_by_mod = {m.value if m else "": int(c or 0) for (m, _t, c) in mod_rows}

        avg_by_module = []
        for name in module_order:
            t = totals_by_mod.get(name, 0)
            c = corr_by_mod.get(name, 0)
            avg_by_module.append({"module": name, "avg": round((c / t) * 100.0, 1) if t else 0.0})

        # Attempts per day (last N days)
        day_counts: dict[str, int] = defaultdict(int)
        sessions = (
            TestSession.query.filter(TestSession.start_time >= since_dt)
            .order_by(TestSession.start_time.asc())
            .all()
        )
        for sess in sessions:
            d = (sess.start_time or datetime.utcnow()).date().isoformat()
            day_counts[d] += 1
        attempts_series = []
        for i in range(days - 1, -1, -1):
            d = (datetime.utcnow().date() - timedelta(days=i)).isoformat()
            attempts_series.append({"date": d, "count": int(day_counts.get(d, 0))})

        # Top mistake categories (by module, last N days)
        wrong = (
            db.session.query(Question.module, func.count(Response.id))
            .join(Response, Response.question_id == Question.id)
            .join(TestSession, TestSession.id == Response.session_id)
            .filter(TestSession.start_time >= since_dt)
            .filter(Response.is_correct == False)  # noqa: E712
            .group_by(Question.module)
            .order_by(func.count(Response.id).desc())
            .limit(5)
            .all()
        )
        top_mistakes = [
            {"module": (m.value if m else "Unknown"), "count": int(c or 0)} for (m, c) in wrong
        ]

        return InstructorDashboardData(
            kpis={
                "total_students": int(total_students),
                "active_this_week": int(active_this_week),
                "avg_score": float(avg_score),
                "completion_rate": float(completion_rate),
                "timeframe_days": int(days),
            },
            leaderboard=leaderboard,
            charts={
                "cefr_distribution": cefr_distribution,
                "avg_by_module": avg_by_module,
                "attempts_series": attempts_series,
            },
            widgets={
                "top_mistakes": top_mistakes,
            },
        )
