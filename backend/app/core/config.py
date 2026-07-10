"""アプリ設定。環境変数から読む（10-phase0-implementation-plan.md の実装規約：シークレットは環境変数）。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+psycopg://tennis:tennis@postgres:5432/tennis"
    redis_url: str = "redis://redis:6379/0"

    # S3互換ストレージ（本番はCloudflare R2、devはMinIO）
    s3_endpoint_url: str = "http://minio:9000"
    # ブラウザが直接叩く署名付きURL用のエンドポイント（Dockerサービス名はホストから解決できないため）。
    # 未設定時は s3_endpoint_url にフォールバック（本番のR2はブラウザからも同一URLで到達可能なため不要）。
    s3_public_endpoint_url: str | None = None
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "tennis-analyzer"
    # "us-east-1"はS3互換実装（MinIO等）で最も互換性が高い既定値
    # （バケット作成時のLocationConstraint省略が許される特別扱いの region）。
    # 本番でCloudflare R2に接続する場合は環境変数 S3_REGION=auto を設定する。
    s3_region: str = "us-east-1"

    # セッション（Redisにserver-side session。10 §認証）
    session_secret: str = "dev-only-change-me"
    session_ttl_days: int = 30

    # LINE Login（v2.1 authorization code flow。未設定ならLINE無効でdevログインのみ）
    line_channel_id: str | None = None
    line_channel_secret: str | None = None
    line_redirect_uri: str = "http://localhost:8000/api/auth/line/callback"
    line_messaging_channel_access_token: str | None = None

    # メール送信（channels/email。10で言及のResend想定）
    resend_api_key: str | None = None
    email_from: str = "no-reply@tennis-analyzer.example"

    # devモード：認証なしで固定ユーザーを使う（M1〜M4。10 §API契約）
    dev_auto_user: bool = True

    # アップロード制約（10 §アップロードAPI: サイズ16GB かつ 2.5時間の二軸）
    upload_max_bytes: int = 16 * 1024 * 1024 * 1024
    upload_part_size: int = 64 * 1024 * 1024
    upload_expire_hours: int = 48

    # 共有リンクの署名URL有効期間（10: 12h — VOD再生セッション長との整合）
    share_signed_url_ttl_seconds: int = 12 * 60 * 60

    # ジョブのポイズンピル対策（10 §冪等性: 配送回数ベースの打ち切り）
    job_max_attempts: int = 5

    # コンテンツ処理（02: GOP2s・8Mbps）
    normalize_gop_seconds: int = 2
    normalize_bitrate: str = "8M"
    hls_segment_seconds: int = 6
    encoder: str = "libx264"  # dev/CIはlibx264、本番はNVENC系に差し替え（環境変数）

    # レート制限（10: 10本/日）
    upload_daily_limit: int = 10

    # GPU単価（08 §コストモデル。通貨をキー名に焼き込まない設計方針7の実践）
    gpu_unit_price_amount: float = 0.75  # $0.5〜1.0/h の中央値
    gpu_unit_price_currency: str = "USD"

    # アドバイス文面生成（05 §技術選定: Claude API。CLAUDE.md不変原則4で入力は集計済みJSONのみ）
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
