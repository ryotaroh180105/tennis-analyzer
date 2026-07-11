"""Celeryタスク本体（10 §ジョブフロー）。

precheck(cpu) → ingest(gpu) → analyze(gpu) → edit(cpu) の一連。
各タスクは冒頭で orchestration.start_attempt を呼び、ポイズンピル対策のゲートを通す。
"""

import logging
import tempfile
import time
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.channels.factory import notify_user
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.jobs.celery_app import celery_app
from app.jobs.orchestration import (
    PermanentJobError,
    build_metrics,
    finish_failure,
    finish_success,
    start_attempt,
)
from app.models.job import JobStage
from app.models.match import STAGE_TO_STATUS, Match, MatchStatus, VideoAsset
from app.models.segment import Segment, SegmentOp, SegmentSource
from app.models.match import EventStream
from app.services import segments as segments_service
from app.services import storage

logger = logging.getLogger("jobs.tasks")


def _mark_stage_status(db: Session, match: Match, stage: str) -> None:
    match.status = STAGE_TO_STATUS[stage]
    db.commit()


def _notify_failure(db: Session, match: Match, message: str) -> None:
    from app.models.user import User

    user = db.get(User, match.user_id)
    if user:
        notify_user(user, f"「{match.title}」の解析でエラーが発生しました：{message}")


def _notify_done(db: Session, match: Match) -> None:
    from app.models.user import User

    user = db.get(User, match.user_id)
    if user:
        notify_user(user, f"「{match.title}」の編集が完了しました。アプリでご確認ください。")


def _current_asset_key(db: Session, match_id: uuid.UUID, kind: str) -> tuple[str, int] | None:
    from sqlalchemy import desc

    asset = (
        db.query(VideoAsset)
        .filter(VideoAsset.match_id == match_id, VideoAsset.kind == kind)
        .order_by(desc(VideoAsset.generation))
        .first()
    )
    if asset is None:
        return None
    return asset.r2_key, asset.generation


@celery_app.task(name="app.jobs.tasks.run_precheck")
def run_precheck(match_id: str) -> None:
    from cvpipeline.precheck import run_precheck as cv_precheck

    db = SessionLocal()
    job = None
    match = None
    try:
        match = db.get(Match, uuid.UUID(match_id))
        if match is None:
            return

        job = start_attempt(db, match.id, JobStage.precheck)
        if job is None:
            _mark_failed_final(db, match, "retry_exhausted", "precheck exceeded max attempts")
            return

        _mark_stage_status(db, match, "precheck")
        wall_start = time.monotonic()

        original_key, _ = _current_asset_key(db, match.id, "original")
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = str(Path(tmpdir) / "original.mp4")
            storage.download_to_file(original_key, local_path)

            try:
                report = cv_precheck(local_path)
            except Exception as exc:  # noqa: BLE001 — ffprobeの失敗等は入力不正として扱う
                raise PermanentJobError("input_invalid", str(exc)) from exc

        if not report["input_valid"]:
            raise PermanentJobError("input_invalid", report.get("reason", "invalid input"))

        match.preflight_report = {
            "checks": report["checks"],
            "degraded": report["degraded"],
            "sampled_range_s": report["sampled_range_s"],
        }
        match.recorded_at = match.recorded_at or match.created_at
        db.commit()

        metrics = build_metrics(time.monotonic() - wall_start, gpu_seconds=0, breakdown={})
        finish_success(db, job, metrics)

        run_ingest.delay(match_id)

    except PermanentJobError as exc:
        if job is not None:
            finish_failure(db, job, exc.message)
        if match is not None:
            _mark_failed_final(db, match, exc.code, exc.message)
            _notify_failure(db, match, exc.message)
    except Exception as exc:  # noqa: BLE001
        logger.exception("precheck failed for %s", match_id)
        if job is not None:
            finish_failure(db, job, str(exc))
        # 一時失敗はbackoffで再投入（DBのattemptカウンタがポイズンピルを止める）
        run_precheck.apply_async(args=[match_id], countdown=30)
    finally:
        db.close()


def _mark_failed_final(db: Session, match: Match, code: str, message: str) -> None:
    match.status = MatchStatus.failed
    match.failure_reason = {"code": code, "message": message}
    db.commit()


@celery_app.task(name="app.jobs.tasks.run_ingest")
def run_ingest(match_id: str) -> None:
    from cvpipeline.ingest import normalize

    settings = get_settings()
    db = SessionLocal()
    job = None
    try:
        match = db.get(Match, uuid.UUID(match_id))
        if match is None:
            return

        job = start_attempt(db, match.id, JobStage.ingest)
        if job is None:
            _mark_failed_final(db, match, "retry_exhausted", "ingest exceeded max attempts")
            return

        _mark_stage_status(db, match, "ingest")
        wall_start = time.monotonic()

        original_key, _ = _current_asset_key(db, match.id, "original")
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = str(Path(tmpdir) / "original.mp4")
            out_path = str(Path(tmpdir) / "normalized.mp4")
            storage.download_to_file(original_key, in_path)

            encode_start = time.monotonic()
            result = normalize(
                in_path,
                out_path,
                encoder=settings.encoder,
                gop_seconds=settings.normalize_gop_seconds,
                bitrate=settings.normalize_bitrate,
            )
            encode_s = time.monotonic() - encode_start

            key = f"matches/{match.id}/normalized.mp4"
            storage.upload_file(out_path, key, content_type="video/mp4")

        db.add(
            VideoAsset(
                match_id=match.id,
                kind="normalized",
                generation=0,
                r2_key=key,
                duration_s=result["output_meta"]["duration_s"],
                meta=result["output_meta"],
            )
        )
        db.commit()

        gpu_seconds = time.monotonic() - wall_start
        metrics = build_metrics(
            time.monotonic() - wall_start,
            gpu_seconds=gpu_seconds,
            breakdown={"encode_s": round(encode_s, 2)},
        )
        finish_success(db, job, metrics)

        run_analyze.delay(match_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("ingest failed for %s", match_id)
        if job is not None:
            finish_failure(db, job, str(exc))
        run_ingest.apply_async(args=[match_id], countdown=30)
    finally:
        db.close()


@celery_app.task(name="app.jobs.tasks.run_analyze")
def run_analyze(match_id: str) -> None:
    from cvpipeline.pipeline import run_analyze as cv_analyze

    db = SessionLocal()
    job = None
    try:
        match = db.get(Match, uuid.UUID(match_id))
        if match is None:
            return

        job = start_attempt(db, match.id, JobStage.analyze)
        if job is None:
            _mark_failed_final(db, match, "retry_exhausted", "analyze exceeded max attempts")
            return

        _mark_stage_status(db, match, "analyze")
        wall_start = time.monotonic()

        normalized_key, _ = _current_asset_key(db, match.id, "normalized")
        degraded = bool((match.preflight_report or {}).get("degraded", False))

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = str(Path(tmpdir) / "normalized.mp4")
            storage.download_to_file(normalized_key, local_path)
            analyze_start = time.monotonic()
            result = cv_analyze(local_path, degraded=degraded)
            analyze_s = time.monotonic() - analyze_start

        db.add(EventStream(match_id=match.id, version=1, payload=result["event_stream_payload"]))

        for seg in result["segments"]:
            db.add(
                Segment(
                    match_id=match.id,
                    revision=0,
                    op=SegmentOp.add,
                    base_segment_id=None,
                    start_s=seg["start_s"],
                    end_s=seg["end_s"],
                    source=SegmentSource.auto,
                )
            )
        db.commit()

        gpu_seconds = time.monotonic() - wall_start
        metrics = build_metrics(
            time.monotonic() - wall_start,
            gpu_seconds=gpu_seconds,
            breakdown={"stage1_4_s": round(analyze_s, 2)},
        )
        finish_success(db, job, metrics)

        run_edit.delay(match_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("analyze failed for %s", match_id)
        if job is not None:
            finish_failure(db, job, str(exc))
        run_analyze.apply_async(args=[match_id], countdown=30)
    finally:
        db.close()


@celery_app.task(name="app.jobs.tasks.run_edit")
def run_edit(match_id: str) -> None:
    from app.editing.ffmpeg_ops import build_edited_video, build_hls, build_thumbnail

    db = SessionLocal()
    job = None
    try:
        match = db.get(Match, uuid.UUID(match_id))
        if match is None:
            return

        job = start_attempt(db, match.id, JobStage.edit)
        if job is None:
            _mark_failed_final(db, match, "retry_exhausted", "edit exceeded max attempts")
            return

        _mark_stage_status(db, match, "edit")
        wall_start = time.monotonic()

        normalized_key, _ = _current_asset_key(db, match.id, "normalized")
        normalized_asset = (
            db.query(VideoAsset)
            .filter(VideoAsset.match_id == match.id, VideoAsset.kind == "normalized")
            .order_by(VideoAsset.generation.desc())
            .first()
        )
        duration_s = normalized_asset.duration_s

        rows = db.query(Segment).filter(Segment.match_id == match.id).all()
        effective = segments_service.compute_effective(rows)
        if not effective:
            raise PermanentJobError("edit_error", "no effective segments to edit")

        prev_edited = _current_asset_key(db, match.id, "edited")
        next_generation = (prev_edited[1] + 1) if prev_edited else 0

        with tempfile.TemporaryDirectory() as tmpdir:
            normalized_local = str(Path(tmpdir) / "normalized.mp4")
            storage.download_to_file(normalized_key, normalized_local)

            edited_local = str(Path(tmpdir) / "edited.mp4")
            build_edited_video(normalized_local, effective, duration_s, edited_local)
            from cvpipeline.video_io import ffprobe as _ffprobe

            edited_duration_s = _ffprobe(edited_local)["duration_s"]

            hls_dir = str(Path(tmpdir) / "hls")
            build_hls(edited_local, hls_dir)

            thumbnail_local = str(Path(tmpdir) / "thumbnail.jpg")
            build_thumbnail(edited_local, thumbnail_local)

            edited_key = f"matches/{match.id}/gen{next_generation}/edited.mp4"
            storage.upload_file(edited_local, edited_key, content_type="video/mp4")

            hls_prefix = f"matches/{match.id}/gen{next_generation}/hls"
            for f in Path(hls_dir).iterdir():
                content_type = "application/vnd.apple.mpegurl" if f.suffix == ".m3u8" else "video/mp2t"
                storage.upload_file(str(f), f"{hls_prefix}/{f.name}", content_type=content_type)

            thumbnail_key = f"matches/{match.id}/gen{next_generation}/thumbnail.jpg"
            storage.upload_file(thumbnail_local, thumbnail_key, content_type="image/jpeg")

        db.add(
            VideoAsset(
                match_id=match.id,
                kind="edited",
                generation=next_generation,
                r2_key=edited_key,
                duration_s=edited_duration_s,
            )
        )
        db.add(
            VideoAsset(
                match_id=match.id,
                kind="hls",
                generation=next_generation,
                r2_key=f"{hls_prefix}/playlist.m3u8",
            )
        )
        db.add(
            VideoAsset(match_id=match.id, kind="thumbnail", generation=next_generation, r2_key=thumbnail_key)
        )
        match.status = MatchStatus.done
        db.commit()

        metrics = build_metrics(time.monotonic() - wall_start, gpu_seconds=0, breakdown={})
        finish_success(db, job, metrics)

        _notify_done(db, match)
        run_immediate_feedback.delay(match_id)

    except PermanentJobError as exc:
        if job is not None:
            finish_failure(db, job, exc.message)
        _mark_failed_final(db, match, exc.code, exc.message)
        _notify_failure(db, match, exc.message)
    except Exception as exc:  # noqa: BLE001
        logger.exception("edit failed for %s", match_id)
        if job is not None:
            finish_failure(db, job, str(exc))
        run_edit.apply_async(args=[match_id], countdown=30)
    finally:
        db.close()


@celery_app.task(name="app.jobs.tasks.run_highlight")
def run_highlight(match_id: str) -> None:
    """ハイライト動画生成（04-miss-taxonomy.md / 01 §Phase1）。

    editパイプラインとは独立したオンデマンド生成（recutと同様、poison-pill対策の
    DBジョブ追跡は行わない）。ハイライト候補が無ければ何もせず終了する。
    """
    from app.editing.ffmpeg_ops import build_edited_video, build_hls
    from app.services.stats import aggregate_stats

    db = SessionLocal()
    try:
        match = db.get(Match, uuid.UUID(match_id))
        if match is None:
            return

        stream = (
            db.query(EventStream)
            .filter(EventStream.match_id == match.id)
            .order_by(EventStream.version.desc())
            .first()
        )
        if stream is None:
            return

        highlights = aggregate_stats(stream.payload)["highlights"]
        clips = [
            {"start_s": h["start_s"], "end_s": h["end_s"]}
            for h in highlights
            if h["start_s"] is not None and h["end_s"] is not None
        ]
        if not clips:
            return

        normalized_key, _ = _current_asset_key(db, match.id, "normalized")
        normalized_asset = (
            db.query(VideoAsset)
            .filter(VideoAsset.match_id == match.id, VideoAsset.kind == "normalized")
            .order_by(VideoAsset.generation.desc())
            .first()
        )
        duration_s = normalized_asset.duration_s

        prev_highlight = _current_asset_key(db, match.id, "highlight")
        next_generation = (prev_highlight[1] + 1) if prev_highlight else 0

        with tempfile.TemporaryDirectory() as tmpdir:
            normalized_local = str(Path(tmpdir) / "normalized.mp4")
            storage.download_to_file(normalized_key, normalized_local)

            highlight_local = str(Path(tmpdir) / "highlight.mp4")
            build_edited_video(normalized_local, clips, duration_s, highlight_local)

            hls_dir = str(Path(tmpdir) / "hls")
            build_hls(highlight_local, hls_dir)

            highlight_key = f"matches/{match.id}/gen{next_generation}/highlight.mp4"
            storage.upload_file(highlight_local, highlight_key, content_type="video/mp4")

            hls_prefix = f"matches/{match.id}/gen{next_generation}/highlight_hls"
            for f in Path(hls_dir).iterdir():
                content_type = "application/vnd.apple.mpegurl" if f.suffix == ".m3u8" else "video/mp2t"
                storage.upload_file(str(f), f"{hls_prefix}/{f.name}", content_type=content_type)

        db.add(
            VideoAsset(match_id=match.id, kind="highlight", generation=next_generation, r2_key=highlight_key)
        )
        db.add(
            VideoAsset(
                match_id=match.id,
                kind="highlight_hls",
                generation=next_generation,
                r2_key=f"{hls_prefix}/playlist.m3u8",
            )
        )
        db.commit()

    except Exception:  # noqa: BLE001
        logger.exception("highlight generation failed for %s", match_id)
    finally:
        db.close()


@celery_app.task(name="app.jobs.tasks.run_immediate_feedback")
def run_immediate_feedback(match_id: str) -> None:
    """解析完了直後の即時フィードバック生成（07 §配信の3層設計 ①）。

    Claude APIには集計済み構造化スタッツJSONのみを渡す（動画・イベントストリームは渡さない、
    CLAUDE.md 不変原則4）。失敗してもmatch.statusには影響させない（動画閲覧は継続可能に保つ）。
    """
    from app.models.advice import AdviceDelivery, AdviceDeliveryKind
    from app.services.advice_llm import generate_immediate_feedback
    from app.services.stats import aggregate_stats, compute_match_metrics

    db = SessionLocal()
    try:
        match = db.get(Match, uuid.UUID(match_id))
        if match is None:
            return

        stream = (
            db.query(EventStream)
            .filter(EventStream.match_id == match.id)
            .order_by(EventStream.version.desc())
            .first()
        )
        if stream is None:
            return

        stats = aggregate_stats(stream.payload)
        metrics = compute_match_metrics(stream.payload)
        feedback = generate_immediate_feedback(stats, metrics)

        db.add(
            AdviceDelivery(
                user_id=match.user_id,
                match_id=match.id,
                kind=AdviceDeliveryKind.immediate,
                content=feedback.model_dump(),
                metrics_snapshot=metrics,
            )
        )
        db.commit()

    except Exception:  # noqa: BLE001
        logger.exception("immediate feedback generation failed for %s", match_id)
    finally:
        db.close()


@celery_app.task(name="app.jobs.tasks.run_weekly_digest")
def run_weekly_digest() -> None:
    """週次ダイジェストのファンアウト（07 §配信の3層設計 ②③。celery beatから起動）。

    ユーザーごとの本体処理は run_weekly_digest_for_user に委譲し、1ユーザーの失敗が
    他ユーザーへの配信を止めないようにする。
    """
    from app.models.user import User

    db = SessionLocal()
    try:
        user_ids = [row[0] for row in db.query(User.id).all()]
    finally:
        db.close()

    for user_id in user_ids:
        run_weekly_digest_for_user.delay(str(user_id))


@celery_app.task(name="app.jobs.tasks.run_weekly_digest_for_user")
def run_weekly_digest_for_user(user_id: str) -> None:
    """1ユーザー分の週次ダイジェスト選定・生成・配信（07 §配信の3層設計 ②③）。

    「何を言うか」（cooldown_days・週次上限の適用）は services.weekly_digest、
    「どう言うか」（文面生成）は services.advice_llm が担う。
    直近試合が無いユーザーには何も送らない。
    """
    from app.models.advice import AdviceDelivery, AdviceDeliveryKind
    from app.models.user import User
    from app.services.advice_llm import generate_weekly_digest
    from app.services.weekly_digest import select_weekly_notifications

    db = SessionLocal()
    try:
        user = db.get(User, uuid.UUID(user_id))
        if user is None:
            return

        selection = select_weekly_notifications(db, user.id)
        if selection is None:
            return

        digest = generate_weekly_digest(
            selection["history"], selection["trigger"], selection["praise_fired"]
        )

        lines = [digest.headline, "", f"良かった点：{digest.positive_point}"]
        if digest.trend_note:
            lines.append(digest.trend_note)
        if digest.drill_suggestion:
            lines.append(f"今週のドリル：{digest.drill_suggestion}")
        notify_user(user, "\n".join(lines))

        latest_metrics = selection["history"][-1]
        db.add(
            AdviceDelivery(
                user_id=user.id,
                kind=AdviceDeliveryKind.weekly_digest,
                content=digest.model_dump(),
                metrics_snapshot=latest_metrics,
            )
        )
        if selection["trigger"] is not None:
            db.add(
                AdviceDelivery(
                    user_id=user.id,
                    kind=AdviceDeliveryKind.trigger,
                    trigger_id=selection["trigger"]["id"],
                    content=digest.model_dump(),
                    metrics_snapshot=latest_metrics,
                )
            )
        db.commit()

    except Exception:  # noqa: BLE001
        logger.exception("weekly digest generation failed for user %s", user_id)
    finally:
        db.close()


@celery_app.task(name="app.jobs.tasks.run_form_analyze")
def run_form_analyze(form_session_id: str) -> None:
    """フォーム解析（Phase 3拡張。12-form-analysis.md）。

    Matchの4段パイプラインとは別の単発ジョブ（編集・ハイライト・スコアが不要なため）。
    骨格が検出できない場合でもjob自体は失敗させず、全指標がunknownの結果を返す
    （CLAUDE.md不変原則1）。抽出済みランドマーク系列はS3にgzip保存し、指標定義変更時に
    骨格再抽出なしで再計算できるようにする（不変原則3）。
    """
    import gzip
    import json

    from cvpipeline.pose.orchestrator import analyze_form

    from app.models.form import FormAnalysis, FormSession, FormSessionStatus

    settings = get_settings()
    db = SessionLocal()
    session = None
    try:
        session = db.get(FormSession, uuid.UUID(form_session_id))
        if session is None:
            return

        session.status = FormSessionStatus.analyzing
        db.commit()

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = str(Path(tmpdir) / "original.mp4")
            storage.download_to_file(session.original_r2_key, local_path)

            from cvpipeline.video_io import ffprobe

            meta = ffprobe(local_path)
            if meta["duration_s"] <= 0:
                session.status = FormSessionStatus.failed
                session.failure_reason = {"code": "input_invalid", "message": "unreadable or zero-duration video"}
                db.commit()
                _notify_failure(db, session, "動画を読み込めませんでした")
                return

            session.duration_s = meta["duration_s"]
            backhand_style = session.backhand_style.value if session.backhand_style else None
            result = analyze_form(
                local_path,
                settings.pose_model_path,
                session.shot_type.value,
                backhand_style=backhand_style,
                hz=settings.pose_sample_hz,
            )

        landmark_series = result.pop("landmark_series")
        landmarks_key = f"form-sessions/{session.id}/landmarks.v1.json.gz"
        storage.put_object_bytes(
            landmarks_key,
            gzip.compress(json.dumps(landmark_series).encode("utf-8")),
            content_type="application/gzip",
        )
        session.landmarks_r2_key = landmarks_key

        db.add(FormAnalysis(form_session_id=session.id, payload=result))
        session.status = FormSessionStatus.done
        db.commit()

        from app.models.user import User

        user = db.get(User, session.user_id)
        if user:
            notify_user(user, f"「{session.title}」のフォーム解析が完了しました。アプリでご確認ください。")

    except Exception as exc:  # noqa: BLE001
        logger.exception("form analyze failed for %s", form_session_id)
        if session is not None:
            session.status = FormSessionStatus.failed
            session.failure_reason = {"code": "analyze_error", "message": str(exc)}
            db.commit()
    finally:
        db.close()
