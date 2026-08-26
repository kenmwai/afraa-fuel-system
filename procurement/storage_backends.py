from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class R2Boto3Storage(S3Boto3Storage):
    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    custom_domain = getattr(settings, "AWS_S3_CUSTOM_DOMAIN", None)
    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", None)
