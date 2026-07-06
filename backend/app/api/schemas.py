import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class UploadCreateRequest(BaseModel):
    filename: str
    total_size: int = Field(gt=0)
    content_type: str


class UploadCreateResponse(BaseModel):
    upload_id: uuid.UUID
    part_size: int


class UploadPartsRequest(BaseModel):
    part_numbers: list[int] = Field(min_length=1)


class UploadPartsResponse(BaseModel):
    urls: dict[int, str]


class UploadStatusResponse(BaseModel):
    status: str
    completed_parts: list[dict]


class MatchCreateRequest(BaseModel):
    upload_id: uuid.UUID
    title: str


class MatchCreateResponse(BaseModel):
    id: uuid.UUID
    status: str


class ProgressInfo(BaseModel):
    stage: str | None
    pct: int


class MatchResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    failure_reason: dict | None
    preflight_report: dict | None
    assets: list[dict]
    progress: ProgressInfo
    created_at: datetime


class SegmentRaw(BaseModel):
    id: uuid.UUID
    revision: int
    op: str
    base_segment_id: uuid.UUID | None
    start_s: float | None
    end_s: float | None
    source: str


class SegmentEffective(BaseModel):
    start_s: float
    end_s: float


class SegmentsResponse(BaseModel):
    revision: int
    effective: list[SegmentEffective]
    raw: list[SegmentRaw]


class SegmentOpRequest(BaseModel):
    op: str  # add | remove | adjust
    base_segment_id: uuid.UUID | None = None
    start_s: float | None = None
    end_s: float | None = None


class SegmentsPatchRequest(BaseModel):
    base_revision: int
    ops: list[SegmentOpRequest]


class ShareLinkResponse(BaseModel):
    url: str


class PlaybackResponse(BaseModel):
    playlist_url: str
    thumbnail_url: str | None
