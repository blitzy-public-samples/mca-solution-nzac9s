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
from typing import Dict, Optional
from urllib.parse import ParseResult, unquote, urlparse

import google.auth
from fastapi import UploadFile
from google.api_core import exceptions as google_exceptions
from google.auth import credentials as google_auth_credentials
from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_auth_transport
from google.cloud import storage

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Single source of truth for the key namespace, so every object this service
# writes stays under one prefix that lifecycle rules can target later. It is
# also the namespace an identifier must fall inside to be resolvable: see
# _resolve_object_name.
ATTACHMENT_PREFIX = "attachments"

# Cloud Storage wants a content type on write, and both e-mail parts and
# browser uploads routinely omit one. Declaring the payload opaque is safer
# than guessing a type the bytes may not actually have.
DEFAULT_CONTENT_TYPE = "application/octet-stream"

# Cloud Storage refuses an object name longer than 1024 UTF-8 bytes, so a
# supplied filename may only occupy what the prefix, the date partition and
# the UUID leave behind. Enforced on the way in by _build_object_name and on
# the way back by _resolve_object_name.
MAX_OBJECT_NAME_BYTES = 1024

# A V4 signature is valid for at most seven days. Naming the ceiling here
# lets generate_download_url refuse an impossible window before it resolves
# credentials, rather than letting the client raise after that work is done.
MAX_EXPIRATION_MINUTES = 7 * 24 * 60

# Control characters are excluded from object names on two independent
# grounds: Cloud Storage rejects carriage return and line feed outright, and
# either one carried into a log record could forge a second record there
# (CWE-117). C0, DEL and C1 are all covered; printable non-ASCII is
# deliberately left alone, because filenames legitimately contain it.
CONTROL_CHARACTERS = frozenset(
    chr(code) for code in list(range(0x00, 0x20)) + list(range(0x7F, 0xA0))
)

# The only origins an identifier may name. Cloud Storage publishes two
# endpoint layouts per host - path-style, which carries the bucket as the
# first path segment, and virtual-hosted, which carries it as a hostname
# prefix - and both are accepted for these hosts alone. Anything else is a
# foreign origin, and is refused rather than quietly re-pointed at our own
# bucket: see _bucket_relative_path.
GCS_ENDPOINT_HOSTS = ("storage.googleapis.com", "storage.cloud.google.com")

# Scope requested for the identity that signs download URLs. cloud-platform
# is what authorises the IAM signBlob call described in _get_signing_kwargs.
SIGNING_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

# Cached client handle; stays None until the first storage operation runs.
# See _get_client for why that emptiness at import time is the whole point.
_client = None

# Cached signing identity, resolved only when generate_download_url runs and
# empty until then, for the same import-time reason as _client above.
_signing_credentials = None


def _log_safe(value: str) -> str:
    # Escapes anything that could break out of a single log record before it
    # is interpolated into one. Both name producers below already refuse
    # control characters, so this is the second line of defence rather than
    # the first - but a log file is the wrong place to discover that the
    # first one was bypassed, because a forged record is indistinguishable
    # from a genuine one after the fact (CWE-117).
    return "".join(
        "\\x{0:02x}".format(ord(char)) if char in CONTROL_CHARACTERS else char
        for char in value
    )


def _require_setting(name: str, value: str) -> str:
    # Presence and usefulness are not the same thing, and Settings only
    # guarantees the first. GOOGLE_CLOUD_PROJECT and
    # GOOGLE_CLOUD_STORAGE_BUCKET are declared as required str fields
    # (app/core/config.py lines 9-10), so pydantic refuses a MISSING
    # variable - but an exported-yet-empty one satisfies that annotation and
    # travels on into the client library, where it fails in two unhelpful
    # ways: an empty project is retained verbatim by storage.Client and
    # resurfaces much later as an unattributable API fault, while an empty
    # bucket name raises IndexError from inside the library the moment a
    # blob reference is built. An empty bucket name would also neuter the
    # bucket-identity check in _bucket_relative_path, because every
    # candidate bucket would then only have to match the empty string to be
    # accepted as ours.
    #
    # So both values are settled here, before any client, bucket or origin
    # decision can rest on them, and the message names the exact variable an
    # operator has to set instead of leaving a library-internal exception to
    # be decoded. No default is substituted and no second configuration path
    # is opened: get_settings() remains the only source.
    stripped = (value or "").strip()
    if not stripped:
        raise ValueError(
            "{0} is empty; the runtime environment must set it".format(name))
    return stripped


def _get_project_id() -> str:
    # Read per call rather than held, because get_settings() is not memoised
    # (app/core/config.py lines 18-19); what gets cached is the client this
    # value builds, in _get_client.
    return _require_setting(
        "GOOGLE_CLOUD_PROJECT", get_settings().GOOGLE_CLOUD_PROJECT)


def _get_bucket_name() -> str:
    # One validated source for the bucket name, used BOTH to address the
    # bucket and to decide whether an inbound identifier names our bucket.
    # Those two uses must never disagree, which is why neither of them reads
    # the setting directly.
    return _require_setting(
        "GOOGLE_CLOUD_STORAGE_BUCKET",
        get_settings().GOOGLE_CLOUD_STORAGE_BUCKET)


def _get_client() -> storage.Client:
    # Construction is lazy and cached so that IMPORTING this module never
    # requires credentials and never touches the network. That matters
    # because three modules import it at start-up, one of them a FastAPI
    # router, and it is the deliberate opposite of the import-time settings
    # access at app/db/database.py line 5. get_settings() is not memoised
    # (app/core/config.py lines 18-19), so the client handle - not the
    # settings object - is what has to be held here.
    #
    # TWO RUNTIME PREREQUISITES THIS MODULE CANNOT PROVISION FOR ITSELF,
    # both owned by the Cloud Run service at infrastructure/terraform/
    # main.tf lines 79-95, whose container spec declares nothing but an
    # image:
    #
    # 1. CONFIGURATION. That revision receives none of the seven no-default
    #    Settings fields - PROJECT_NAME, API_V1_STR, SECRET_KEY,
    #    DATABASE_URL, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_STORAGE_BUCKET,
    #    EMAIL_SUBMISSION_ADDRESS (app/core/config.py lines 5-11) - and no
    #    .env file is committed, so the first storage call fails inside
    #    get_settings() with a pydantic ValidationError naming every absent
    #    field, before any object is addressed. Making that revision usable
    #    means setting those values on it, GOOGLE_CLOUD_PROJECT from
    #    var.project_id and GOOGLE_CLOUD_STORAGE_BUCKET from
    #    "${var.project_id}-mca-documents", so that it addresses
    #    google_storage_bucket.mca_documents (main.tf lines 43-46) and not
    #    the unrelated processed bucket at lines 48-51.
    #
    # 2. IDENTITY. That revision also declares no service_account_name, so
    #    it runs as the Compute Engine default service account. Every grant
    #    at main.tf lines 116-145 - roles/editor, roles/storage.admin,
    #    roles/cloudsql.admin, roles/pubsub.admin - is bound to
    #    mca-service-account, a DIFFERENT principal, so object access
    #    currently rests on whatever the default account happens to carry
    #    rather than on the storage role the Terraform provisions. Attaching
    #    google_service_account.mca_service_account to the revision is what
    #    puts the granted role in force; _get_signing_kwargs records what
    #    the same gap costs a signed URL.
    #
    # Both are deployment facts rather than code defects, recorded at the
    # point of use because infrastructure/terraform/ is not modified from
    # here and neither one can be repaired in Python.
    global _client
    if _client is None:
        _client = storage.Client(project=_get_project_id())
    return _client


def _get_bucket() -> storage.Bucket:
    # bucket() builds a local reference and performs no existence check, so
    # every public call below costs exactly one storage round trip instead of
    # two. The bucket is provisioned by Terraform, not by this service, so
    # proving it exists on each request would buy nothing.
    return _get_client().bucket(_get_bucket_name())


def _build_object_name(filename: str) -> str:
    # The uuid4 prefix is what makes key collisions structurally impossible:
    # two uploads of the same filename on the same day cannot overwrite one
    # another. utcnow() rather than now() matches the UTC-only convention
    # used at every other timestamp site in this backend.
    #
    # The filename itself arrives from an e-mail part or a browser upload and
    # is therefore untrusted, so three things happen to it before any of it
    # becomes a key. Separators are flattened, so a traversal attempt such as
    # "a/b/evil.pdf" lands at "a_b_evil.pdf" and cannot escape the prefix.
    # Control characters are replaced, because Cloud Storage rejects carriage
    # return and line feed in an object name and either one would otherwise
    # travel into the log line in upload_attachment. What survives is then
    # trimmed to whatever the 1024-byte name limit leaves after the prefix,
    # the date and the UUID, cut on a UTF-8 boundary so that a multi-byte
    # character is never split into an invalid fragment. A missing name
    # becomes "unnamed" rather than an empty key.
    #
    # Printable non-ASCII survives all three unchanged: the canonical URL
    # percent-encodes it and _resolve_object_name decodes it on the way back,
    # so the round trip stays lossless.
    stem = "{0}/{1}/{2}-".format(
        ATTACHMENT_PREFIX,
        datetime.utcnow().strftime("%Y/%m/%d"),
        uuid.uuid4().hex,
    )
    flattened = (filename or "").strip().replace("\\", "/").replace("/", "_")
    safe_name = "".join(
        "_" if char in CONTROL_CHARACTERS else char for char in flattened
    ).strip()
    if not safe_name:
        safe_name = "unnamed"
    budget = MAX_OBJECT_NAME_BYTES - len(stem.encode("utf-8"))
    encoded_name = safe_name.encode("utf-8")
    if len(encoded_name) > budget:
        safe_name = encoded_name[:budget].decode("utf-8", "ignore")
    return stem + safe_name


def _bucket_relative_path(parsed: ParseResult, candidate: str) -> str:
    # Reduces a URI form to the still-encoded object path it addresses, and
    # refuses anything this service could not have emitted.
    #
    # The identifier reaching get_file_content and its siblings arrives from
    # the storage_url column, so it deserves exactly as much trust as any
    # other request input: none. A resolver that inspected only the scheme
    # would happily reduce gs://someone-elses-bucket/attachments/x, or
    # https://example.com/anything/attachments/x, to a name inside OUR bucket
    # and then read, delete, probe or sign that object instead. So the origin
    # is checked against the two published Cloud Storage endpoint layouts and
    # the bucket the identifier names must be the configured one - both here,
    # before any network call is made.
    #
    # urlparse has already separated the query string, which is how a signed
    # URL's X-Goog-* parameters get discarded. The path stays percent-encoded
    # for now so that an encoded separator cannot masquerade as a real one
    # while the bucket segment is removed; _resolve_object_name decodes it
    # once that segment is gone.
    #
    # The name compared against arrives through _get_bucket_name rather than
    # from the setting directly, so a blank configuration value cannot reduce
    # the comparison below to a formality that every candidate satisfies.
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path.lstrip("/")
    bucket_name = _get_bucket_name()
    if scheme == "gs":
        if host != bucket_name.lower():
            raise ValueError(
                "file_path names bucket '{0}', not the configured "
                "bucket: {1}".format(host, _log_safe(candidate)))
        return path
    if scheme != "https":
        raise ValueError(
            "file_path uses unsupported scheme '{0}': {1}".format(
                scheme, _log_safe(candidate)))
    if host in GCS_ENDPOINT_HOSTS:
        # Path-style: the bucket is the first path segment and has to go,
        # but only once it has been confirmed to be ours.
        first, separator, remainder = path.partition("/")
        if first != bucket_name or not separator:
            raise ValueError(
                "file_path names bucket '{0}', not the configured "
                "bucket: {1}".format(first, _log_safe(candidate)))
        return remainder
    for endpoint in GCS_ENDPOINT_HOSTS:
        # Virtual-hosted: the bucket is a hostname prefix instead, so the
        # path already IS the object name and stripping a segment from it
        # would corrupt the name.
        if host == "{0}.{1}".format(bucket_name.lower(), endpoint):
            return path
    raise ValueError(
        "file_path is not a Cloud Storage identifier for the configured "
        "bucket: {0}".format(_log_safe(candidate)))


def _resolve_object_name(file_path: str) -> str:
    # Callers legitimately hand back whatever this service emitted. The
    # canonical URL returned by the upload functions is persisted in
    # Attachment.storage_url (app/db/models.py line 50), travels through the
    # API schema and the Celery task, and arrives back here by way of
    # get_file_content - so EVERY emitted form has to reduce to the same
    # bucket-relative object name. If it did not, an upload would succeed and
    # the matching download would 404, a silent failure no import test can
    # see. Bare object names, with or without a leading slash, are accepted
    # for the same reason.
    #
    # What is NOT accepted is anything this service could not have emitted.
    # _bucket_relative_path settles the origin and the bucket; the checks
    # below settle the name itself, on the DECODED form so that an encoded
    # traversal such as %2E%2E%2F is inspected as the "../" it really is.
    # Every key this module writes lives under ATTACHMENT_PREFIX, so a name
    # outside that namespace, a relative or empty segment, a control
    # character or an over-long name is refused here rather than turned into
    # a read, a deletion, a probe or a signature over an unintended object.
    if file_path is None:
        raise ValueError("file_path is required to address an object")
    candidate = str(file_path).strip()
    if not candidate:
        raise ValueError("file_path must not be empty")
    parsed = urlparse(candidate)
    if parsed.scheme:
        path = _bucket_relative_path(parsed, candidate)
    else:
        path = candidate.lstrip("/")
    object_name = unquote(path)
    if not object_name.startswith(ATTACHMENT_PREFIX + "/"):
        raise ValueError(
            "file_path does not address an object under '{0}/': {1}".format(
                ATTACHMENT_PREFIX, _log_safe(candidate)))
    segments = object_name.split("/")
    if any(not segment or segment in (".", "..") for segment in segments):
        raise ValueError(
            "file_path has an empty or relative path segment: {0}".format(
                _log_safe(candidate)))
    if any(char in CONTROL_CHARACTERS for char in object_name):
        raise ValueError(
            "file_path has control characters: {0}".format(
                _log_safe(candidate)))
    if len(object_name.encode("utf-8")) > MAX_OBJECT_NAME_BYTES:
        raise ValueError(
            "file_path exceeds the {0}-byte object name limit".format(
                MAX_OBJECT_NAME_BYTES))
    return object_name


def _get_signing_kwargs() -> Dict[str, object]:
    # Produces the keyword arguments generate_download_url must hand the
    # client for a V4 signature to be produced AT ALL on this deployment.
    #
    # Signing needs something that can produce a signature, and here that is
    # not a private key. The backend runs on Cloud Run
    # (infrastructure/terraform/main.tf lines 79-95) under Application
    # Default Credentials, which return an access token and nothing else: the
    # credential is not an instance of google.auth.credentials.Signing, so
    # asking the client to sign locally raises AttributeError inside
    # google/cloud/storage/_signing.py instead of returning a URL.
    #
    # The supported keyless route is the IAM signBlob API, and the pinned
    # client takes it only when BOTH service_account_email and access_token
    # are supplied - which is what this helper supplies. The credential is
    # refreshed first for two reasons: the token has to be current, and a
    # compute-engine credential reports its service_account_email as the
    # literal string "default" until the metadata server has answered. A
    # credential that CAN sign locally, such as a service-account key or an
    # impersonated identity, is passed through untouched instead, so a
    # deployment that grows a signing key needs no change here.
    #
    # STILL UNMET INFRASTRUCTURE PREREQUISITES, and there are three of them
    # rather than one. signBlob needs the IAM Service Account Credentials API
    # enabled AND roles/iam.serviceAccountTokenCreator held by the identity
    # the revision actually runs as - and that identity is not the one the
    # Terraform provisions. main.tf lines 79-95 attach no
    # service_account_name to the Cloud Run service, so the revision runs as
    # the Compute Engine default service account, while lines 116-145 grant
    # roles/editor, roles/storage.admin, roles/cloudsql.admin and
    # roles/pubsub.admin to mca-service-account instead. Signing therefore
    # becomes possible only once the revision is given that account (or the
    # token-creator role is granted to the identity it does run as), the
    # credentials API is enabled, and that token-creator grant exists. Until
    # all three hold, this path fails at the signBlob call with a logged
    # error - loudly, at read time, with a message that names the cause.
    #
    # The same identity gap is why the upload path returns the canonical
    # object URL and why that URL is what lands in the non-nullable
    # storage_url column: a canonical URL needs no signing credential at all,
    # only ordinary object permissions on whichever identity is in force, so
    # it is the form least able to break on this deployment.
    global _signing_credentials
    if _signing_credentials is None:
        try:
            _signing_credentials, _ = google.auth.default(
                scopes=list(SIGNING_SCOPES))
        except google_auth_exceptions.GoogleAuthError as e:
            logger.error(f"Failed to resolve signing credentials: {str(e)}")
            raise
    if isinstance(_signing_credentials, google_auth_credentials.Signing):
        return {"credentials": _signing_credentials}
    try:
        _signing_credentials.refresh(google_auth_transport.Request())
    except google_auth_exceptions.GoogleAuthError as e:
        logger.error(f"Failed to refresh signing credentials: {str(e)}")
        raise
    email = getattr(_signing_credentials, "service_account_email", None)
    token = getattr(_signing_credentials, "token", None)
    if not email or email == "default" or not token:
        message = (
            "The active credentials cannot sign a download URL: they carry "
            "no private key and no service account identity for the IAM "
            "signBlob API")
        logger.error(message)
        raise google_auth_exceptions.GoogleAuthError(message)
    return {
        "credentials": _signing_credentials,
        "service_account_email": email,
        "access_token": token,
    }


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
            f"Failed to upload {_log_safe(object_name)} to "
            f"{bucket.name}: {str(e)}")
        raise
    logger.info(
        f"Uploaded {len(file_content)} bytes to "
        f"{bucket.name}/{_log_safe(object_name)}")
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
            f"Object {_log_safe(object_name)} not found in "
            f"{bucket.name}: {str(e)}")
        raise
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to download {_log_safe(object_name)} from "
            f"{bucket.name}: {str(e)}")
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
            f"Object {_log_safe(object_name)} already absent from "
            f"{bucket.name}")
        return
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to delete {_log_safe(object_name)} from "
            f"{bucket.name}: {str(e)}")
        raise
    logger.info(f"Deleted {_log_safe(object_name)} from {bucket.name}")


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
            f"Failed to probe {_log_safe(object_name)} in "
            f"{bucket.name}: {str(e)}")
        raise


def generate_download_url(
    file_path: str,
    expiration_minutes: int = 15,
) -> str:
    # Time-limited distribution for read time only; deliberately NOT on the
    # write path, because a signature expires and storage_url must not.
    # _get_signing_kwargs carries the full account of how signing is wired on
    # this deployment and which infrastructure grant it still waits on.
    #
    # The window is validated before anything else because a V4 signature is
    # capped at seven days and the client discovers an over-long one only
    # after credentials have been resolved and a bucket reference built.
    # Refusing it here keeps an impossible request cheap and its error
    # specific, and it is the same argument-before-I/O rule the rest of this
    # module follows.
    if expiration_minutes < 1 or expiration_minutes > MAX_EXPIRATION_MINUTES:
        raise ValueError(
            "expiration_minutes must be between 1 and {0}".format(
                MAX_EXPIRATION_MINUTES))
    object_name = _resolve_object_name(file_path)
    signing_kwargs = _get_signing_kwargs()
    bucket = _get_bucket()
    blob = bucket.blob(object_name)
    try:
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
            **signing_kwargs
        )
    except (
        google_auth_exceptions.GoogleAuthError,
        google_exceptions.GoogleAPIError,
    ) as e:
        # Both families are expected here and neither is swallowed: an
        # unauthorised signBlob call arrives as a GoogleAuthError, while a
        # storage-side fault arrives as a GoogleAPIError.
        logger.error(
            f"Failed to sign a download URL for "
            f"{_log_safe(object_name)}: {str(e)}")
        raise
