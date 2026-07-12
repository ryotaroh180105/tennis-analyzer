"""S3互換ストレージ（本番: Cloudflare R2 / dev: MinIO）のラッパー。

アップロードのcompleteはクライアントのETagに依存しない —
サーバーがR2 ListPartsでパート一覧・ETagを取得してCompleteMultipartUploadを実行する
（10 §アップロードAPI。クライアント再起動でETagを失っても再開できる設計）。
"""

import uuid
from functools import lru_cache

import boto3
from botocore.client import Config

from app.core.config import get_settings

settings = get_settings()


@lru_cache
def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@lru_cache
def get_s3_public_client():
    """署名付きURL生成専用クライアント。ブラウザから直接叩かれるため、
    Dockerサービス名（例: minio:9000）ではなくホストから到達可能なエンドポイントを使う。"""
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_public_endpoint_url or settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    """R2の `region="auto"` はAWSのLocationConstraint列挙値として無効なため、
    バケット作成リクエストの地域と不整合になりうる（実機検証で判明）。
    バケット作成だけは互換性の高い us-east-1 相当（無指定）で試み、
    地域制約エラー時のみ明示的なLocationConstraintで再試行する。
    """
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
        return
    except Exception:
        pass

    try:
        client.create_bucket(Bucket=settings.s3_bucket)
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if error_code not in ("IllegalLocationConstraintException", "InvalidLocationConstraint"):
            raise
        region = settings.s3_region if settings.s3_region not in ("auto", "") else "us-east-1"
        client.create_bucket(
            Bucket=settings.s3_bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )


def build_upload_key(user_id: uuid.UUID, filename: str) -> str:
    upload_id = uuid.uuid4().hex
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "mp4"
    return f"uploads/{user_id}/{upload_id}.{ext}"


def create_multipart_upload(key: str, content_type: str) -> str:
    client = get_s3_client()
    resp = client.create_multipart_upload(Bucket=settings.s3_bucket, Key=key, ContentType=content_type)
    return resp["UploadId"]


def presign_part_url(key: str, r2_upload_id: str, part_number: int, expires_in: int = 3600) -> str:
    client = get_s3_public_client()
    return client.generate_presigned_url(
        "upload_part",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": key,
            "UploadId": r2_upload_id,
            "PartNumber": part_number,
        },
        ExpiresIn=expires_in,
    )


def list_parts(key: str, r2_upload_id: str) -> list[dict]:
    """クライアント再起動後の再開に使う。part_number/etag/sizeのみ返す。"""
    client = get_s3_client()
    parts: list[dict] = []
    kwargs = {"Bucket": settings.s3_bucket, "Key": key, "UploadId": r2_upload_id}
    while True:
        resp = client.list_parts(**kwargs)
        for p in resp.get("Parts", []):
            parts.append({"part_number": p["PartNumber"], "etag": p["ETag"], "size": p["Size"]})
        if not resp.get("IsTruncated"):
            break
        kwargs["PartNumberMarker"] = resp["NextPartNumberMarker"]
    return parts


def complete_multipart_upload(key: str, r2_upload_id: str) -> None:
    """サーバー側でListPartsからETagを取得して完了させる（クライアントにETagを持たせない）。"""
    client = get_s3_client()
    parts = list_parts(key, r2_upload_id)
    if not parts:
        raise ValueError("no parts uploaded")
    client.complete_multipart_upload(
        Bucket=settings.s3_bucket,
        Key=key,
        UploadId=r2_upload_id,
        MultipartUpload={"Parts": [{"PartNumber": p["part_number"], "ETag": p["etag"]} for p in parts]},
    )


def abort_multipart_upload(key: str, r2_upload_id: str) -> None:
    client = get_s3_client()
    client.abort_multipart_upload(Bucket=settings.s3_bucket, Key=key, UploadId=r2_upload_id)


def presign_get_url(key: str, expires_in: int) -> str:
    client = get_s3_public_client()
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": settings.s3_bucket, "Key": key}, ExpiresIn=expires_in
    )


def get_object_bytes(key: str) -> bytes:
    client = get_s3_client()
    resp = client.get_object(Bucket=settings.s3_bucket, Key=key)
    return resp["Body"].read()


def put_object_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    client = get_s3_client()
    client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)


def download_to_file(key: str, dest_path: str) -> None:
    client = get_s3_client()
    client.download_file(settings.s3_bucket, key, dest_path)


def upload_file(local_path: str, key: str, content_type: str = "application/octet-stream") -> None:
    client = get_s3_client()
    client.upload_file(local_path, settings.s3_bucket, key, ExtraArgs={"ContentType": content_type})


def delete_object(key: str) -> None:
    """データ保持ポリシー（08 §データライフサイクル）に基づく削除で使う。冪等
    （存在しないキーの削除はS3互換APIでは通常エラーにならない）。"""
    client = get_s3_client()
    client.delete_object(Bucket=settings.s3_bucket, Key=key)


def delete_prefix(prefix: str) -> None:
    """prefix配下の全オブジェクトを削除する（HLS: playlist.m3u8 + 複数の.tsセグメントが
    同一prefix配下にあり、VideoAssetはplaylistのキーしか持たないため）。"""
    client = get_s3_client()
    continuation_token = None
    while True:
        kwargs = {"Bucket": settings.s3_bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = client.list_objects_v2(**kwargs)
        objects = [{"Key": obj["Key"]} for obj in resp.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objects})
        if not resp.get("IsTruncated"):
            break
        continuation_token = resp.get("NextContinuationToken")
