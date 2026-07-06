"""失敗したmatchの手動再投入（10 §冪等性・リトライ）。`make requeue MATCH=<id>` から呼ぶ。

status=failed のmatchのみ受け付ける。最後に失敗したstageから再開する。
"""

import sys
import uuid

from sqlalchemy import desc

from app.core.db import SessionLocal
from app.jobs.tasks import run_analyze, run_edit, run_ingest, run_precheck
from app.models.job import AnalysisJob, JobStatus
from app.models.match import Match, MatchStatus

STAGE_TASKS = {
    "precheck": run_precheck,
    "ingest": run_ingest,
    "analyze": run_analyze,
    "edit": run_edit,
}


def requeue(match_id: str) -> None:
    db = SessionLocal()
    try:
        match = db.get(Match, uuid.UUID(match_id))
        if match is None:
            print(f"match {match_id} not found")
            return
        if match.status != MatchStatus.failed:
            print(f"match {match_id} is not in failed status (current: {match.status.value})")
            return

        last_failed = (
            db.query(AnalysisJob)
            .filter(AnalysisJob.match_id == match.id, AnalysisJob.status == JobStatus.failed)
            .order_by(desc(AnalysisJob.created_at))
            .first()
        )
        stage = last_failed.stage.value if last_failed else "precheck"

        match.status = MatchStatus.queued
        match.failure_reason = None
        db.commit()

        STAGE_TASKS[stage].delay(match_id)
        print(f"requeued match {match_id} from stage {stage}")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m app.jobs.requeue <match_id>")
        sys.exit(1)
    requeue(sys.argv[1])
