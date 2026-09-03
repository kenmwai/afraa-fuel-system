from storages.backends.s3boto3 import S3Boto3Storage
from botocore.exceptions import ClientError
from django.conf import settings


class R2Boto3Storage(S3Boto3Storage):
    bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
    custom_domain = getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None)
    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", None)
    file_overwrite = True  # Avoid calling HeadObject during upload on Cloudflare R2

    def exists(self, name):
        """
        Cloudflare R2 returns HTTP 403 Forbidden on HeadObject when an object does not exist
        if the API token lacks ListBucket permissions. Treat 403 and 404 as non-existent.
        """
        try:
            return super().exists(name)
        except ClientError as err:
            status_code = err.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status_code in (403, 404):
                return False
            raise
