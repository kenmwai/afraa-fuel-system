from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Tender, VolumeRequirement, Bid, Currency, UnitOfMeasure, GlobalConfig, ExchangeRate, Airline, Supplier, Airport, SupplierDocument
from .Converters import BidAnalyzer
from .forms import UserRegistrationForm, SupplierDocumentForm
from decimal import Decimal, InvalidOperation
from collections import defaultdict
import json

# New imports for presign
import time
import boto3
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST


@login_required
@require_POST
def presign_upload(request):
    filename = request.POST.get("filename")
    if not filename:
        return JsonResponse({"error": "filename required"}, status=400)

    key = f"supplier_documents/{request.user.id}/{int(time.time())}_{filename}"

    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=boto3.session.Config(signature_version="s3v4"),
    )

    # limit to 10MB
    conditions = [["content-length-range", 0, 10 * 1024 * 1024]]
    fields = {}

    presigned = s3_client.generate_presigned_post(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=3600,
    )

    return JsonResponse({"presigned": presigned, "key": key})


# --- rest of views unchanged ---
# (we will only patch supplier_documents logic below)
