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
# interpreter start-up, so the attachment router never registered, the e-mail
# poller could not be loaded, and OCR could not read a document. The public
# surface below is therefore fixed BY those call sites - awaitability, arity
# and return type are contracts rather than choices - so the three import
# statements above and the call shapes around them stand unedited.
#
# Cloud Storage is the provisioned object store: main.tf declares the target
# bucket as google_storage_bucket.mca_documents. The AWS S3 named in
# README.md is stale scaffold text with no counterpart in code or Terraform.

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

ATTACHMENT_PREFIX = "attachments"

# Applied when a caller supplies no MIME type, so the stored metadata stays
# honest about what is actually known about the payload.
DEFAULT_CONTENT_TYPE = "application/octet-stream"

# Cloud Storage accepts an object name of 1 to 1024 bytes once UTF-8
# encoded, and the WHOLE key counts against that - prefix, date partition
# and uuid4 included, not just the filename. The bound is applied in this
# module rather than left to the provider so an over-long client filename
# is caught before an upload is issued instead of surfacing as a rejected
# request after the write path has been entered.
MAX_OBJECT_NAME_BYTES = 1024

# The two GCS endpoints that address an object as /<bucket>/<object>: on
# these the first path segment is the bucket and has to be dropped. The
# other layout this module emits and accepts is virtual-hosted,
# <bucket>.storage.googleapis.com, which carries the bucket in the hostname
# and so keeps its whole path as the object name.
PATH_STYLE_HOSTS = ("storage.googleapis.com", "storage.cloud.google.com")

_client = None


def _get_client() -> storage.Client:
    # Construction is lazy and cached so that IMPORTING this module never
    # requires credentials and never touches the network - three modules
    # import it at start-up, one of them a FastAPI router - which is the
    # deliberate opposite of app/db/database.py line 5. get_settings() is not
    # memoised (app/core/config.py lines 18-19), so the client handle, not
    # the settings object, is what has to be held here.
    global _client
    if _client is None:
        _client = storage.Client(project=get_settings().GOOGLE_CLOUD_PROJECT)
    return _client


def _get_bucket() -> storage.Bucket:
    # bucket() builds a local reference and performs no existence check, so
    # no extra existence-check request is issued ahead of the operation the
    # caller actually asked for. Terraform provisions the bucket, not this
    # service, so proving it exists on every call would buy nothing.
    return _get_client().bucket(get_settings().GOOGLE_CLOUD_STORAGE_BUCKET)


def _build_object_name(filename: str) -> str:
    # The uuid4 prefix makes key collisions structurally impossible: two
    # uploads of the same filename on the same day cannot overwrite one
    # another. utcnow() rather than now() matches the UTC-only convention
    # used at every other timestamp site in this backend.
    #
    # The filename is untrusted, so separators are flattened before any of it
    # becomes a key: "a/b/evil.pdf" lands at "a_b_evil.pdf" and cannot escape
    # the prefix, and a missing name becomes "unnamed". Printable non-ASCII
    # survives verbatim, because the canonical URL percent-encodes it and
    # _resolve_object_name decodes it back, so the round trip is lossless.
    #
    # Its LENGTH is untrusted too, and the key leaving here has to be one the
    # provider will accept, so whatever is left of MAX_OBJECT_NAME_BYTES once
    # the fixed part is spent bounds the readable tail. Shortening that tail
    # rather than refusing the upload is deliberate: the uuid4 already
    # carries the identity, so nothing that ADDRESSES the object is lost,
    # while rejecting would cost a merchant a document - or an e-mail poll
    # its whole run - over a filename attribute. The warning keeps it seen.
    safe_name = (filename or "").strip().replace("\\", "/").replace("/", "_")
    if not safe_name:
        safe_name = "unnamed"
    day = datetime.utcnow().strftime("%Y/%m/%d")
    prefix = "{0}/{1}/{2}-".format(ATTACHMENT_PREFIX, day, uuid.uuid4().hex)
    budget = MAX_OBJECT_NAME_BYTES - len(prefix.encode("utf-8"))
    encoded = safe_name.encode("utf-8")
    if len(encoded) > budget:
        # The cut lands on the byte budget, then errors="ignore" discards the
        # partial sequence it may have severed, so a multi-byte character is
        # never left half-written into the key.
        safe_name = encoded[:budget].decode("utf-8", "ignore")
        logger.warning(
            f"Filename of {len(encoded)} bytes truncated to {budget} to "
            f"keep the object name within {MAX_OBJECT_NAME_BYTES} bytes")
    return prefix + safe_name


def _resolve_object_name(file_path: str) -> str:
    # Callers legitimately hand back whatever this service emitted: the
    # canonical URL is persisted in Attachment.storage_url (app/db/models.py
    # line 50), travels through the API schema and the Celery task, and
    # arrives back here by way of get_file_content - so EVERY emitted form
    # has to reduce to the same bucket-relative object name, or an upload
    # would succeed and its download 404, a silent failure no import test can
    # see. Bare names with or without a leading slash, gs:// URIs and both
    # HTTPS host layouts are accepted for that reason, with any signature
    # query string discarded by urlparse.
    #
    # PERCENT-DECODING APPLIES TO URI AND URL FORMS ONLY, and that
    # distinction is the whole point of the branch below. A URL path is an
    # ENCODED rendering of the name, so decoding recovers it. A bare object
    # name is not encoded - it already IS the key - and a filename may
    # legally contain a literal '%', which the canonical URL renders as
    # '%25'. Decoding a bare name would silently rewrite it, turning
    # "abc-report%2Ffinal.pdf" into "abc-report/final.pdf" and addressing a
    # different object on every read, delete, probe and signature.
    #
    # EMPTINESS IS JUDGED ON THE RESULT, NOT ON THE INPUT, because every
    # branch below can make nothing out of something. An identifier naming
    # only a bucket - gs://<bucket>, either HTTPS layout with nothing past
    # the bucket, or a lone "/" - is not blank, yet it addresses no object
    # and reduces to "". Carrying that on would build blob(""), spending a
    # settings read and a request on an object that cannot exist and
    # reporting it as a provider fault far from the caller that supplied it.
    # The normalised name is therefore checked once, after every branch, and
    # refused here - the same contract the None and blank inputs carry.
    #
    # THAT REFUSAL NAMES NO PART OF THE IDENTIFIER, which is a safety
    # property rather than terseness. A bucket-only form can arrive as a
    # signed URL, whose query IS authentication material - X-Goog-Credential
    # and X-Goog-Signature - and whose text may carry control characters
    # able to forge log records once an upstream FastAPI or Celery handler
    # writes the exception out. Echoing the value back would hand both to
    # that log for nothing: the caller already holds what it passed, and no
    # provider operation has been spent to learn more about it than that.
    if file_path is None or not file_path.strip():
        raise ValueError("file_path is required to address a stored object")
    candidate = file_path.strip()
    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()
    if scheme not in ("gs", "http", "https"):
        object_name = candidate.lstrip("/")
    else:
        path = parsed.path.lstrip("/")
        if scheme != "gs" and (parsed.hostname or "") in PATH_STYLE_HOSTS:
            path = path.partition("/")[2]
        object_name = unquote(path)
    if not object_name:
        raise ValueError("file_path addresses no object in the bucket")
    return object_name


def upload_attachment(
    filename: str,
    file_content: bytes,
    content_type: Optional[str] = None,
) -> str:
    # Synchronous BY CONTRACT: app/services/email_processor.py line 46 calls
    # this from a plain def and uses the result on the very next line, where
    # it is recorded as "storage_path" - so a coroutine returned here would
    # travel on in place of the URL string every downstream consumer expects
    # and break each of them. It is also called positionally with two
    # arguments there, which is why content_type carries a default.
    #
    # The value returned is the CANONICAL object URL, never a signed one:
    # storage_url is a non-nullable column (app/db/models.py line 50) whose
    # contents must stay resolvable for the life of the row, and a signature
    # would expire minutes after it was written. Signing belongs at read
    # time, in generate_download_url.
    #
    # An empty payload is a legitimate zero-byte attachment and is uploaded;
    # only None is rejected, and it is rejected before any network call.
    if file_content is None:
        raise ValueError("file_content is required to upload an attachment")
    object_name = _build_object_name(filename)
    blob = _get_bucket().blob(object_name)
    try:
        blob.upload_from_string(
            file_content,
            content_type=content_type or DEFAULT_CONTENT_TYPE,
        )
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Failed to upload {object_name}: {str(e)}")
        raise
    logger.info(f"Uploaded {len(file_content)} bytes to {object_name}")
    return blob.public_url


async def upload_file(file: UploadFile) -> str:
    # Awaitable BY CONTRACT: app/api/attachments.py line 17 reads
    # "file_url = await upload_file(file)". UploadFile.read is itself a
    # coroutine, so the request body has to be awaited here before the
    # synchronous storage call can be handed bytes. Delegating keeps one
    # key-building and one error-handling path for both entry points, and
    # FastAPI may leave filename or content_type empty, so both fall through
    # to the defaults applied downstream.
    file_content = await file.read()
    return upload_attachment(file.filename, file_content, file.content_type)


def get_file_content(file_path: str) -> bytes:
    # Synchronous BY CONTRACT: app/services/ocr_service.py line 8 uses the
    # result directly, feeding it to a Vision image constructor that needs
    # raw bytes. A missing object is logged and RAISED rather than answered
    # with empty bytes, because silently empty OCR input would corrupt every
    # downstream extraction instead of failing at the fault.
    #
    # The re-raise is bare, so the original google.api_core exception travels
    # on with its type, traceback, response and retry state intact: a caller
    # can still tell a NotFound from a transport fault, which a substituted
    # exception would have taken away from it.
    object_name = _resolve_object_name(file_path)
    blob = _get_bucket().blob(object_name)
    try:
        return blob.download_as_bytes()
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Failed to download {object_name}: {str(e)}")
        raise


def delete_file(file_path: str) -> None:
    # Deletion is idempotent on purpose, and this is the ONE place in this
    # module that does not raise: an object that is already gone satisfies
    # the caller's intent, so a miss is a warning rather than a failure. Any
    # other API fault still surfaces unchanged, which is why the NotFound
    # handler comes first - NotFound is a subclass of GoogleAPIError, so the
    # broader handler would otherwise swallow the idempotent case.
    #
    # As everywhere here, the identifier is validated before the settings
    # and the bucket are looked up, so a None, blank or bucket-only one
    # raises ValueError ahead of any configuration read or network access.
    object_name = _resolve_object_name(file_path)
    blob = _get_bucket().blob(object_name)
    try:
        blob.delete()
    except google_exceptions.NotFound:
        logger.warning(f"Object already absent, not deleted: {object_name}")
        return
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Failed to delete {object_name}: {str(e)}")
        raise
    logger.info(f"Deleted {object_name}")


def file_exists(file_path: str) -> bool:
    # A miss is an answer here, not a failure, so this returns False and lets
    # callers branch on it without a try block - the client library turns the
    # 404 into False itself. Genuine transport faults are still logged and
    # re-raised, so an unreachable bucket cannot masquerade as an absent one.
    object_name = _resolve_object_name(file_path)
    blob = _get_bucket().blob(object_name)
    try:
        return bool(blob.exists())
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Failed to probe {object_name}: {str(e)}")
        raise


def generate_download_url(
    file_path: str,
    expiration_minutes: int = 15,
) -> str:
    # Time-limited distribution for read time only, and deliberately NOT on
    # the write path, because a signature expires and storage_url must not.
    #
    # THIS HELPER HAS UNMET PREREQUISITES, recorded here so the gap stays
    # visible rather than latent. A V4 signature needs a credential that can
    # produce one, and the backend runs on Cloud Run
    # (infrastructure/terraform/main.tf lines 79-95) under Application
    # Default Credentials: an access token, NO private key, so local signing
    # is unavailable. Two infrastructure prerequisites for the documented
    # keyless signBlob remedy are BOTH absent - the IAM Service Account
    # Credentials API is enabled nowhere, the Terraform declaring no
    # google_project_service at all, and roles/iam.serviceAccountTokenCreator
    # is not granted: lines 121-145 give mca-service-account roles/editor,
    # roles/storage.admin, roles/cloudsql.admin and roles/pubsub.admin. That
    # account is not attached to the Cloud Run service either, which
    # declares nothing beyond a container image, so the revision runs as the
    # default compute identity.
    #
    # Provisioning both would still not be enough: under
    # google-cloud-storage 2.14.0 compute credentials are not signing
    # credentials, so a keyless signature also needs service_account_email
    # and access_token to be passed, or credentials that can sign in their
    # place, and the call below passes neither. infrastructure/terraform/ is
    # out of scope here, so this is reported rather than closed - and it is
    # why the write path returns a canonical URL, which works under the
    # roles/storage.admin grant already in place.
    object_name = _resolve_object_name(file_path)
    blob = _get_bucket().blob(object_name)
    try:
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
        )
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Failed to sign a URL for {object_name}: {str(e)}")
        raise
