# backend/s3_service.py
import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class S3ConfigurationError(RuntimeError):
    """Raised when Yandex Object Storage configuration is invalid."""


class S3UploadError(RuntimeError):
    """Raised when upload to Yandex Object Storage fails."""


class S3Service:
    def __init__(self):
        self.endpoint = os.getenv("YANDEX_ENDPOINT")
        self.access_key = os.getenv("YANDEX_ACCESS_KEY_ID")
        self.secret_key = os.getenv("YANDEX_SECRET_ACCESS_KEY")
        self.bucket_name = os.getenv("YANDEX_BUCKET_NAME")

        missing_fields = [
            key
            for key, value in {
                "YANDEX_ENDPOINT": self.endpoint,
                "YANDEX_ACCESS_KEY_ID": self.access_key,
                "YANDEX_SECRET_ACCESS_KEY": self.secret_key,
                "YANDEX_BUCKET_NAME": self.bucket_name,
            }.items()
            if not value
        ]
        if missing_fields:
            missing = ", ".join(missing_fields)
            raise S3ConfigurationError(
                f"Missing Yandex Object Storage configuration: {missing}"
            )

        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=Config(signature_version="s3v4"),
            region_name="ru-central1",
        )

    def upload_file(self, file_obj, object_name: str, content_type: Optional[str] = None):
        """Загружает файл в Yandex Object Storage"""
        if not object_name:
            raise ValueError("object_name must not be empty")

        try:
            if content_type:
                self.s3_client.upload_fileobj(
                    file_obj,
                    self.bucket_name,
                    object_name,
                    ExtraArgs={"ContentType": content_type},
                )
            else:
                self.s3_client.upload_fileobj(
                    file_obj,
                    self.bucket_name,
                    object_name,
                )
            print(f"✅ Файл загружен в Yandex Cloud: {object_name}")
            return True
        except (ClientError, BotoCoreError) as e:
            print(f"❌ Ошибка загрузки в Yandex Cloud: {e}")
            raise S3UploadError("Unable to upload file to Object Storage") from e

    def rename_object(self, old_key: str, new_key: str):
        if not old_key or not new_key:
            raise ValueError("old_key and new_key must not be empty")
        if old_key == new_key:
            return
        try:
            self.s3_client.copy_object(
                Bucket=self.bucket_name,
                CopySource={"Bucket": self.bucket_name, "Key": old_key},
                Key=new_key,
            )
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=old_key)
        except (ClientError, BotoCoreError) as e:
            raise S3UploadError("Unable to rename object in Object Storage") from e

    def delete_object(self, object_key: str):
        if not object_key:
            return
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_key)
        except (ClientError, BotoCoreError) as e:
            raise S3UploadError("Unable to delete object in Object Storage") from e

    def generate_presigned_url(
        self,
        object_name: str,
        expires_in: int = 3600,
        download_filename: Optional[str] = None,
    ):
        """Генерирует временную ссылку для скачивания"""
        if expires_in <= 0:
            raise ValueError("expires_in must be greater than zero")

        params = {"Bucket": self.bucket_name, "Key": object_name}
        if download_filename:
            params["ResponseContentDisposition"] = (
                f'attachment; filename="{download_filename}"'
            )

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=expires_in
            )
            return url
        except (ClientError, BotoCoreError) as e:
            print(f"❌ Ошибка генерации ссылки: {e}")
            raise