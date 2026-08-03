# Google Cloud Storage persistence for merchant application documents.
#
# This module exists because three modules import it at module scope, and
# each of them names a different symbol:
#
#     app/api/attachments.py line 5        upload_file
#     app/services/email_processor.py:6    upload_attachment
#     app/services/ocr_service.py line 4   get_file_content
#
# While no file sat at this import path every one of those statements raised
# ModuleNotFoundError: No module named 'app.services.storage_service' at
# interpreter start-up, so the attachment router never registered, the email
# poller could not be loaded, and OCR could not read a document. The public
# surface below is therefore fixed BY those call sites - awaitability, arity
# and return type are contracts rather than choices - which is what lets all
# three consumers stay byte-identical.
#
# Cloud Storage is the documented and provisioned object store for this
# application: infrastructure/terraform/main.tf declares the target bucket as
# google_storage_bucket.mca_documents, named ${var.project_id}-mca-documents.
# The AWS S3 named in README.md is stale scaffold text with no counterpart in
# the code, the Terraform, or the technical specification.

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import unquote, urlparse

from fastapi import UploadFile
from google.api_core import exceptions as google_exceptions
from google.cloud import storage

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Single source of truth for the key namespace, so every object this service
# writes stays under one prefix that lifecycle rules can target later.
ATTACHMENT_PREFIX = "attachments"

# Cloud Storage wants a content type on write, and both e-mail parts and
# browser uploads routinely omit one. Declaring the payload opaque is safer
# than guessing a type the bytes may not actually have.
DEFAULT_CONTENT_TYPE = "application/octet-stream"

# Cached client handle; stays None until the first storage operation runs.
# See _get_client for why that emptiness at import time is the whole point.
_client = None


def _get_client() -> storage.Client:
    # Construction is lazy and cached so that IMPORTING this module never
    # requires credentials and never touches the network. That matters
    # because three modules import it at start-up, one of them a FastAPI
    # router, and it is the deliberate opposite of the import-time settings
    # access at app/db/database.py line 5. get_settings() is not memoised
    # (app/core/config.py lines 18-19), so the client handle - not the
    # settings object - is what has to be held here.
    global _client
    if _client is None:
        settings = get_settings()
        _client = storage.Client(project=settings.GOOGLE_CLOUD_PROJECT)
    return _client


def _get_bucket() -> storage.Bucket:
    # bucket() builds a local reference and performs no existence check, so
    # every public call below costs exactly one storage round trip instead of
    # two. The bucket is provisioned by Terraform, not by this service, so
    # proving it exists on each request would buy nothing.
    settings = get_settings()
    return _get_client().bucket(settings.GOOGLE_CLOUD_STORAGE_BUCKET)


def _build_object_name(filename: str) -> str:
    # The uuid4 prefix is what makes key collisions structurally impossible:
    # two uploads of the same filename on the same day cannot overwrite one
    # another. utcnow() rather than now() matches the UTC-only convention
    # used at every other timestamp site in this backend. Separators in the
    # supplied name are flattened so that a traversal attempt such as
    # "a/b/evil.pdf" lands at "a_b_evil.pdf" and cannot escape the prefix,
    # and a missing name becomes "unnamed" rather than an empty key.
    # Non-ASCII characters are kept verbatim: the canonical URL percent-
    # encodes them and _resolve_object_name decodes them on the way back.
    safe_name = (filename or "").strip().replace("\\", "/").replace("/", "_")
    if not safe_name:
        safe_name = "unnamed"
    day = datetime.utcnow().strftime("%Y/%m/%d")
    return "{0}/{1}/{2}-{3}".format(
        ATTACHMENT_PREFIX, day, uuid.uuid4().hex, safe_name
    )


def _resolve_object_name(file_path: str) -> str:
    # Callers legitimately hand back whatever this service emitted. The
    # canonical URL returned by the upload functions is persisted in
    # Attachment.storage_url (app/db/models.py line 50), travels through the
    # API schema and the Celery task, and arrives back here by way of
    # get_file_content - so EVERY emitted form has to reduce to the same
    # bucket-relative object name. If it did not, an upload would succeed and
    # the matching download would 404, a silent failure no import test can
    # see. Bare object names are accepted unchanged for the same reason.
    if file_path is None:
        raise ValueError("file_path is required to address an object")
    candidate = str(file_path).strip()
    if not candidate:
        raise ValueError("file_path must not be empty")
    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()
    if scheme in ("gs", "http", "https"):
        # urlparse has already dropped the query string, which is how a
        # signed URL's X-Goog-* credentials get discarded. The raw path is
        # split before unquoting so that an encoded separator cannot
        # masquerade as a real one.
        path = parsed.path.lstrip("/")
        if scheme != "gs":
            # Path-style URLs carry the bucket as the first path segment and
            # it has to go. The virtual-hosted layout carries the bucket in
            # the hostname instead, so there the path already IS the object
            # name and stripping a segment would corrupt it.
            virtual_hosted = parsed.netloc.lower().endswith(
                (".storage.googleapis.com", ".storage.cloud.google.com")
            )
            if not virtual_hosted:
                path = path.partition("/")[2]
    else:
        # A bare object name, with or without a leading slash.
        path = candidate.lstrip("/")
    object_name = unquote(path)
    if not object_name:
        raise ValueError(
            "file_path does not address an object: {0}".format(candidate)
        )
    return object_name


def upload_attachment(
    filename: str,
    file_content: bytes,
    content_type: Optional[str] = None,
) -> str:
    # Synchronous BY CONTRACT: app/services/email_processor.py line 46 calls
    # this from a plain def and uses the result on the very next line, so a
    # coroutine here would persist a coroutine object into storage_url. It is
    # also called positionally with two arguments there, which is why
    # content_type carries a default.
    #
    # The value returned is the CANONICAL object URL, never a signed one:
    # storage_url is a non-nullable column (app/db/models.py line 50) whose
    # contents must stay resolvable for the life of the row, and a signed URL
    # would expire minutes after it was written. Signing happens at read
    # time, in generate_download_url.
    #
    # An empty payload is a legitimate zero-byte attachment and is uploaded;
    # only None is rejected, and it is rejected before any network call.
    if file_content is None:
        raise ValueError("file_content is required to upload an attachment")
    object_name = _build_object_name(filename)
    bucket = _get_bucket()
    blob = bucket.blob(object_name)
    try:
        blob.upload_from_string(
            file_content,
            content_type=content_type or DEFAULT_CONTENT_TYPE,
        )
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to upload {object_name} to {bucket.name}: {str(e)}")
        raise
    logger.info(
        f"Uploaded {len(file_content)} bytes to {bucket.name}/{object_name}")
    return blob.public_url


async def upload_file(file: UploadFile) -> str:
    # Awaitable BY CONTRACT: app/api/attachments.py line 17 reads
    # "file_url = await upload_file(file)". UploadFile.read is itself a
    # coroutine, so the request body has to be awaited here before the
    # synchronous storage call can be handed bytes. Delegating rather than
    # duplicating keeps one key-building and one error-handling path for both
    # entry points, and FastAPI may leave filename or content_type empty, so
    # both fall through to the defaults applied downstream.
    if file is None:
        raise ValueError("file is required to upload an attachment")
    file_content = await file.read()
    return upload_attachment(file.filename, file_content, file.content_type)


def get_file_content(file_path: str) -> bytes:
    # Synchronous BY CONTRACT: app/services/ocr_service.py line 8 uses the
    # result directly, feeding it to a Vision image constructor that needs
    # raw bytes. A missing object is logged and RE-RAISED rather than
    # answered with empty bytes, because silently empty OCR input would
    # corrupt every downstream extraction instead of failing at the fault.
    object_name = _resolve_object_name(file_path)
    bucket = _get_bucket()
    blob = bucket.blob(object_name)
    try:
        return blob.download_as_bytes()
    except google_exceptions.NotFound as e:
        logger.error(
            f"Object {object_name} not found in {bucket.name}: {str(e)}")
        raise
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to download {object_name} from {bucket.name}: {str(e)}")
        raise


def delete_file(file_path: str) -> None:
    # Deletion is idempotent on purpose, and this is the ONE place in this
    # module that does not re-raise: an object that is already gone satisfies
    # the caller's intent, so a miss is a warning rather than a failure. Any
    # other API fault still surfaces.
    object_name = _resolve_object_name(file_path)
    bucket = _get_bucket()
    blob = bucket.blob(object_name)
    try:
        blob.delete()
    except google_exceptions.NotFound:
        logger.warning(
            f"Object {object_name} already absent from {bucket.name}")
        return
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to delete {object_name} from {bucket.name}: {str(e)}")
        raise
    logger.info(f"Deleted {object_name} from {bucket.name}")


def file_exists(file_path: str) -> bool:
    # A miss is an answer here, not a failure, so this returns False and lets
    # callers branch on it without a try block. Genuine transport faults are
    # still logged and re-raised, so an unreachable bucket can never
    # masquerade as an absent object.
    object_name = _resolve_object_name(file_path)
    bucket = _get_bucket()
    blob = bucket.blob(object_name)
    try:
        return bool(blob.exists())
    except google_exceptions.NotFound:
        return False
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to probe {object_name} in {bucket.name}: {str(e)}")
        raise


def generate_download_url(
    file_path: str,
    expiration_minutes: int = 15,
) -> str:
    # Time-limited distribution for read time only; deliberately NOT on the
    # write path.
    #
    # PREREQUISITE, NOT CURRENTLY PROVISIONED: V4 signing needs a credential
    # that can produce a signature. This backend runs on Cloud Run
    # (infrastructure/terraform/main.tf lines 79-95) under Application
    # Default Credentials, which supply an access token but NO private key,
    # and no service-account key file is deployed. The keyless alternative is
    # the IAM Service Account Credentials API, which requires that API to be
    # enabled and the role roles/iam.serviceAccountTokenCreator to be granted
    # to mca-service-account; main.tf lines 116-146 grant roles/editor,
    # roles/storage.admin, roles/cloudsql.admin and roles/pubsub.admin only.
    # NEITHER prerequisite exists today, so this call raises until the
    # Terraform grants them. That gap is exactly why upload_attachment
    # returns the canonical object URL instead of a signed one, and why that
    # canonical URL is what lands in the non-nullable storage_url column.
    if expiration_minutes <= 0:
        raise ValueError("expiration_minutes must be a positive integer")
    object_name = _resolve_object_name(file_path)
    bucket = _get_bucket()
    blob = bucket.blob(object_name)
    try:
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
        )
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to sign a download URL for {object_name}: {str(e)}")
        raise
