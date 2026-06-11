from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from typing import Any


class ObjectStorageError(RuntimeError):
    pass


class MinioDocumentObjectStore:
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        region: str = "local",
        use_ssl: bool = False,
    ) -> None:
        try:
            from minio import Minio
        except ImportError as exc:  # pragma: no cover - 只在部署依赖缺失时触发
            raise ObjectStorageError("minio dependency is required for document ingestion") from exc
        normalized_endpoint = endpoint.strip().removeprefix("http://").removeprefix("https://")
        self.client = Minio(
            normalized_endpoint,
            access_key=access_key,
            secret_key=secret_key,
            region=region,
            secure=use_ssl or endpoint.strip().startswith("https://"),
        )

    def get_bytes(self, bucket: str, key: str) -> bytes:
        try:
            response = self.client.get_object(bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()
        except Exception as exc:  # pragma: no cover - MinIO 集成错误由部署联调覆盖
            raise ObjectStorageError(str(exc)) from exc

    def put_bytes(self, bucket: str, key: str, content: bytes, content_type: str) -> None:
        try:
            if not self.client.bucket_exists(bucket):
                self.client.make_bucket(bucket)
            self.client.put_object(bucket, key, io.BytesIO(content), len(content), content_type=content_type)
        except Exception as exc:  # pragma: no cover - MinIO 集成错误由部署联调覆盖
            raise ObjectStorageError(str(exc)) from exc


def artifact_key(job_id: str, title: str, extension: str = ".txt") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-") or "artifact"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    return f"knowledge-ingestion/{job_id}/{stamp}-{slug}{extension}"


class InMemoryDocumentObjectStore:
    def __init__(self, objects: dict[tuple[str, str], bytes] | None = None) -> None:
        self.objects = objects or {}

    def get_bytes(self, bucket: str, key: str) -> bytes:
        try:
            return self.objects[(bucket, key)]
        except KeyError as exc:
            raise ObjectStorageError(f"object not found: {bucket}/{key}") from exc

    def put_bytes(self, bucket: str, key: str, content: bytes, content_type: str) -> None:
        self.objects[(bucket, key)] = content

    def snapshot(self) -> dict[str, Any]:
        return {f"{bucket}/{key}": len(value) for (bucket, key), value in self.objects.items()}
