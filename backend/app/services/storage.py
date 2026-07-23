import aioboto3
from typing import Optional
from app.core.config import get_settings

settings = get_settings()

class StorageService:
    def __init__(self):
        self.session = aioboto3.Session()
        self.endpoint = settings.minio_endpoint
        self.access_key = settings.minio_access_key
        self.secret_key = settings.minio_secret_key
        self.secure = settings.minio_secure
        self.docs_bucket = settings.minio_bucket_documents
        self.ocr_bucket = settings.minio_bucket_ocr

    async def _get_client(self):
        scheme = "https://" if self.secure else "http://"
        endpoint_url = self.endpoint if "://" in self.endpoint else f"{scheme}{self.endpoint}"
        return self.session.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            use_ssl=self.secure
        )

    async def initialize_buckets(self):
        async with await self._get_client() as s3:
            for bucket in [self.docs_bucket, self.ocr_bucket]:
                try:
                    await s3.head_bucket(Bucket=bucket)
                except Exception:
                    await s3.create_bucket(Bucket=bucket)

    async def upload_document(self, object_name: str, file_data: bytes, content_type: str = "application/pdf") -> str:
        async with await self._get_client() as s3:
            await s3.put_object(
                Bucket=self.docs_bucket,
                Key=object_name,
                Body=file_data,
                ContentType=content_type
            )
            return f"s3://{self.docs_bucket}/{object_name}"

    async def get_presigned_url(self, object_name: str, expires_in: int = 3600) -> str:
        async with await self._get_client() as s3:
            url = await s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.docs_bucket, 'Key': object_name},
                ExpiresIn=expires_in
            )
            return url

    async def download_document(self, storage_path: str) -> bytes:
        """
        Fetch raw file bytes given a storage_path as stored on the Document
        model / DocumentEnvelope, e.g. "s3://lmis-documents/patient123/scan.png".
        Needed by the OCR agent, which receives storage_path, not a local file.
        """
        bucket, key = self._parse_storage_path(storage_path)
        async with await self._get_client() as s3:
            response = await s3.get_object(Bucket=bucket, Key=key)
            async with response["Body"] as stream:
                return await stream.read()

    def _parse_storage_path(self, storage_path: str) -> tuple[str, str]:
        if storage_path.startswith("s3://"):
            without_scheme = storage_path[len("s3://"):]
            bucket, _, key = without_scheme.partition("/")
            return bucket, key
        # Fallback: assume it's a bare object key in the default documents bucket
        return self.docs_bucket, storage_path

storage_service = StorageService()