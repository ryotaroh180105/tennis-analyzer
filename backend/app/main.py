import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import auth, matches, score, share, uploads
from app.services import storage

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # バケットの存在確認は起動時に1回だけ（リクエストパスでの毎回チェックを避ける）
    storage.ensure_bucket()
    yield


app = FastAPI(title="Tennis Analyzer API", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(uploads.router)
app.include_router(matches.router)
app.include_router(score.router)
app.include_router(share.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """共通エラースキーマに正規化する（10 §共通事項）。"""
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(detail)}},
    )


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}
