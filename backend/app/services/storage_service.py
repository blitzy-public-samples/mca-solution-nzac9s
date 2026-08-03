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
import re
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

# Applied when a caller supplies no MIME type, and when the one supplied
# cannot be trusted as metadata (see _resolve_content_type), so the stored
# metadata stays honest about what is actually known about the payload.
DEFAULT_CONTENT_TYPE = "application/octet-stream"

# A declared content type is CLIENT TEXT: it arrives as a multipart header
# or an e-mail part header and is then stored as object metadata that a
# later reader trusts, so its shape is checked before it is forwarded to the
# provider. RFC 9110 builds a media type as type/subtype with optional
# parameters, drawn from one fixed token alphabet plus quoted strings, so
# anything outside that alphabet - control characters included - is not a
# media type and has no business being written to an object.
_MEDIA_TOKEN = r"[0-9A-Za-z!#$%&'*+.^_`|~-]+"
_MEDIA_QUOTED = r'"[^"\\\x00-\x1f\x7f]*"'
MEDIA_TYPE_PATTERN = re.compile(
    "^{0}/{0}(?:[ \t]*;[ \t]*{0}=(?:{0}|{1}))*$".format(
        _MEDIA_TOKEN, _MEDIA_QUOTED))

# Types a browser EXECUTES rather than displays. Both buckets are private
# today (infrastructure/terraform/main.tf lines 43-51), but a stored object
# outlives that decision, and active content served from the bucket's own
# origin would be a scripting vector rather than a document. Recording such
# a declaration as an opaque stream keeps the bytes intact and inert.
ACTIVE_CONTENT_TYPES = frozenset([
    "application/ecmascript",
    "application/javascript",
    "application/x-javascript",
    "application/xhtml+xml",
    "image/svg+xml",
    "text/ecmascript",
    "text/html",
    "text/javascript",
])

# Cloud Storage accepts an object name of 1 to 1024 bytes once UTF-8
# encoded, and the WHOLE key counts against that - prefix, date partition
# and uuid4 included, not just the filename. The bound is applied in this
# module rather than left to the provider so an over-long client filename
# is caught before an upload is issued instead of surfacing as a rejected
# request after the write path has been entered.
MAX_OBJECT_NAME_BYTES = 1024

# Cloud Storage REFUSES an object name that contains a Carriage Return or a
# Line Feed, and warns that the control characters XML 1.0 forbids
# (#x7F-#x84 and #x86-#x9F) break object listing. A filename reaches this
# module straight out of a multipart header or an e-mail part, which is
# exactly where such a character enters. That band is taken whole rather than
# with #x85 punched out of the middle of it, and the remaining C0 controls
# and the U+2028/U+2029 line separators are folded in as well, because those
# are the same code points that let caller text forge a second record inside
# a log line - so ONE set serves both the provider requirement and the
# log-safety one, and neither can be satisfied while forgetting the other.
UNSAFE_CODE_POINTS = frozenset(
    list(range(0x00, 0x20)) + list(range(0x7F, 0xA0)) + [0x2028, 0x2029])

# Substituting rather than deleting keeps the substitution visible in the
# stored key, and "_" is already what this module puts in place of a path
# separator, so a sanitised name still reads as one name.
_CONTROL_TABLE = {code: "_" for code in UNSAFE_CODE_POINTS}

# Ceiling on a single stored object, enforced HERE because this module is the
# one place every upload passes through: the route at
# app/api/attachments.py lines 9-17 declares no limit, and neither does
# anything else in this repository. The figure is not arbitrary - Cloud
# Vision reads these objects back through get_file_content, and it documents
# 20 MB as the ceiling for inline content and errors above it, so a larger
# document could be stored and then never processed. The decimal reading of
# 20 MB is used because it is the smaller, and therefore the safe, one.
# Refusing before the write is what bounds how much of this process's memory
# and of the bucket an unauthenticated caller can spend.
MAX_UPLOAD_BYTES = 20 * 1000 * 1000

# Read granularity for a streamed body: one mebibyte, which is the point at
# which Starlette spools a multipart part to disk, so a chunk here is a unit
# the request machinery already deals in.
UPLOAD_CHUNK_BYTES = 1024 * 1024

# The two GCS endpoints that address an object as /<bucket>/<object>: on
# these the first path segment is the bucket and has to be dropped. The
# other layout this module emits and accepts is virtual-hosted,
# <bucket>.storage.googleapis.com, which carries the bucket in the hostname
# and so keeps its whole path as the object name.
PATH_STYLE_HOSTS = ("storage.googleapis.com", "storage.cloud.google.com")

_client = None


def _loggable(value: str) -> str:
    # Every name this module logs is at least partly CALLER TEXT: the tail of
    # a generated key is a client filename, and the identifier handed to each
    # read helper is whatever the caller passed. Writing that verbatim into a
    # log record would let a crafted value end the line and forge a second
    # one, so exactly the code points a log consumer could read as a record
    # boundary are escaped. Everything printable survives, non-ASCII
    # included, because merchant filenames legitimately carry it and a record
    # nobody can read is no better than one that lies.
    #
    # The rendering is bounded as well. A generated key cannot exceed
    # MAX_OBJECT_NAME_BYTES, but an identifier arriving from a caller is
    # under no such limit, and an unbounded one would let a single failed
    # read write an arbitrarily large record.
    rendered = "".join(
        "\\u{0:04x}".format(ord(c)) if ord(c) in UNSAFE_CODE_POINTS else c
        for c in value[:MAX_OBJECT_NAME_BYTES])
    if len(value) > MAX_OBJECT_NAME_BYTES:
        rendered += "...[truncated]"
    return rendered


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
    # Control code points go in the same pass, per UNSAFE_CODE_POINTS: a
    # Carriage Return or Line Feed would have the provider reject the upload
    # outright, and the rest of that set either breaks object listing or
    # travels on into a log record. Substituting after strip() is what keeps
    # a name that is merely PADDED with CR, LF or tab from carrying those
    # positions forward as underscores.
    #
    # Its LENGTH is untrusted too, and the key leaving here has to be one the
    # provider will accept, so whatever is left of MAX_OBJECT_NAME_BYTES once
    # the fixed part is spent bounds the readable tail. Shortening that tail
    # rather than refusing the upload is deliberate: the uuid4 already
    # carries the identity, so nothing that ADDRESSES the object is lost,
    # while rejecting would cost a merchant a document - or an e-mail poll
    # its whole run - over a filename attribute. The warning keeps it seen.
    safe_name = (filename or "").strip().replace("\\", "/").replace("/", "_")
    safe_name = safe_name.translate(_CONTROL_TABLE)
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


def _resolve_content_type(content_type: Optional[str]) -> str:
    # The declared type is checked rather than forwarded, for the reason given
    # at MEDIA_TYPE_PATTERN. A value that is not a well-formed media type is
    # replaced with the documented fallback instead of refused: the bytes are
    # still whatever the merchant submitted, and losing a document over a
    # malformed header would be the worse outcome of the two. The same
    # substitution is applied to a declaration a browser would execute, per
    # ACTIVE_CONTENT_TYPES, and only the type itself is inspected - any
    # parameters ride along with it.
    #
    # No allow-list of document types is applied. This application defines no
    # such policy anywhere, and inventing one here would start refusing the
    # legitimate statements and contracts the pipeline exists to read.
    if not content_type:
        return DEFAULT_CONTENT_TYPE
    candidate = content_type.strip()
    if not MEDIA_TYPE_PATTERN.match(candidate):
        logger.warning(
            f"Malformed content type {_loggable(candidate)} recorded as "
            f"{DEFAULT_CONTENT_TYPE}")
        return DEFAULT_CONTENT_TYPE
    if candidate.split(";")[0].strip().lower() in ACTIVE_CONTENT_TYPES:
        logger.warning(
            f"Active content type {_loggable(candidate)} recorded as "
            f"{DEFAULT_CONTENT_TYPE}")
        return DEFAULT_CONTENT_TYPE
    return candidate


async def _read_bounded(file: UploadFile) -> bytes:
    # Reading the body in chunks and stopping at MAX_UPLOAD_BYTES is what
    # keeps an upload's cost bounded. `await file.read()` with no argument
    # materialises the entire body in this process in one go, however large
    # the client chose to make it, and the route that reaches this module
    # accepts an arbitrary multipart body, so the size is not something this
    # module may assume. Refusing here - before upload_attachment is called -
    # also means an over-sized body never reaches the bucket, so there is no
    # orphaned object to compensate for afterwards.
    #
    # `size` is consulted first only as a shortcut: Starlette sets it from the
    # bytes it actually spooled rather than from a client header, but it is
    # absent on a hand-constructed UploadFile, so the loop remains the
    # authority and the ceiling is never delegated to the attribute alone.
    declared = getattr(file, "size", None)
    if isinstance(declared, int) and declared > MAX_UPLOAD_BYTES:
        raise ValueError(
            "upload of {0} bytes exceeds the {1} byte limit".format(
                declared, MAX_UPLOAD_BYTES))
    body = bytearray()
    while True:
        chunk = await file.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        body.extend(chunk)
        if len(body) > MAX_UPLOAD_BYTES:
            raise ValueError(
                "upload exceeds the {0} byte limit".format(MAX_UPLOAD_BYTES))
    return bytes(body)


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
    #
    # The MAX_UPLOAD_BYTES ceiling is enforced here as well as on the streamed
    # path, because this is the entry point the e-mail poller uses and its
    # bytes arrive already materialised - a part decoded from a message is no
    # more trustworthy in size than a multipart body. Both refusals precede
    # the key build and the settings read, so an over-sized payload costs one
    # length comparison and no I/O at all, and the message carries only byte
    # counts: the filename it came with is caller text and stays out of it.
    if file_content is None:
        raise ValueError("file_content is required to upload an attachment")
    if len(file_content) > MAX_UPLOAD_BYTES:
        raise ValueError(
            "attachment of {0} bytes exceeds the {1} byte limit".format(
                len(file_content), MAX_UPLOAD_BYTES))
    object_name = _build_object_name(filename)
    logged = _loggable(object_name)
    stored_type = _resolve_content_type(content_type)
    blob = _get_bucket().blob(object_name)
    try:
        blob.upload_from_string(file_content, content_type=stored_type)
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Failed to upload {logged}: {_loggable(str(e))}")
        raise
    logger.info(f"Uploaded {len(file_content)} bytes to {logged}")
    return blob.public_url


async def upload_file(file: UploadFile) -> str:
    # Awaitable BY CONTRACT: app/api/attachments.py line 17 reads
    # "file_url = await upload_file(file)". UploadFile.read is itself a
    # coroutine, so the request body has to be awaited here before the
    # synchronous storage call can be handed bytes. Delegating keeps one
    # key-building and one error-handling path for both entry points, and
    # FastAPI may leave filename or content_type empty, so both fall through
    # to the defaults applied downstream.
    #
    # The body is drawn through _read_bounded rather than by a bare
    # file.read(), so an unbounded request body cannot be materialised whole
    # in this process. What this function CANNOT do from here is authenticate
    # the caller, prove the application exists, or undo a write whose
    # database row never lands - all three belong to the route at
    # app/api/attachments.py lines 9-17, which owns the request and the
    # session; delete_file is already exported for the last of them. This
    # module bounds what it can bound rather than fabricating a security
    # boundary it has no position to enforce.
    file_content = await _read_bounded(file)
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
    logged = _loggable(object_name)
    blob = _get_bucket().blob(object_name)
    try:
        return blob.download_as_bytes()
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Failed to download {logged}: {_loggable(str(e))}")
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
    logged = _loggable(object_name)
    blob = _get_bucket().blob(object_name)
    try:
        blob.delete()
    except google_exceptions.NotFound:
        logger.warning(f"Object already absent, not deleted: {logged}")
        return
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Failed to delete {logged}: {_loggable(str(e))}")
        raise
    logger.info(f"Deleted {logged}")


def file_exists(file_path: str) -> bool:
    # A miss is an answer here, not a failure, so this returns False and lets
    # callers branch on it without a try block - the client library turns the
    # 404 into False itself. Genuine transport faults are still logged and
    # re-raised, so an unreachable bucket cannot masquerade as an absent one.
    object_name = _resolve_object_name(file_path)
    logged = _loggable(object_name)
    blob = _get_bucket().blob(object_name)
    try:
        return bool(blob.exists())
    except google_exceptions.GoogleAPIError as e:
        logger.error(f"Failed to probe {logged}: {_loggable(str(e))}")
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
    logged = _loggable(object_name)
    blob = _get_bucket().blob(object_name)
    try:
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
        )
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to sign a URL for {logged}: {_loggable(str(e))}")
        raise
