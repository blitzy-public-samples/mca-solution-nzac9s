# Google Cloud Storage persistence for merchant application documents.
#
# This module exists because three modules import it at module scope, and
# each of them names a different symbol:
#
#     app/api/attachments.py line 5        upload_file
#     app/services/email_processor.py:6    upload_attachment
#     app/services/ocr_service.py line 3   get_file_content
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

import hashlib
import logging
import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import ParseResult, unquote, urlparse

from fastapi import UploadFile
from google.api_core import exceptions as google_exceptions
from google.api_core import retry as google_retry
from google.cloud import storage

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ATTACHMENT_PREFIX = "attachments"

# Every key this module writes begins with this, and the read helpers accept
# nothing outside it - see _validated_object_name. The bucket is provisioned
# for the whole application rather than for this module alone, so the prefix
# is what separates "a document this service stored" from "anything else that
# happens to live in the same bucket".
OBJECT_NAME_NAMESPACE = ATTACHMENT_PREFIX + "/"

# Applied when a caller supplies no MIME type, and when the one supplied
# cannot be trusted as metadata (see _resolve_content_type), so the stored
# metadata stays honest about what is actually known about the payload.
DEFAULT_CONTENT_TYPE = "application/octet-stream"

# A declared content type is client text - a multipart or e-mail part header -
# stored as object metadata a later reader trusts, so its shape is checked
# before it is forwarded. The pattern is a deliberately conservative subset of
# the RFC 9110 grammar: type/subtype with token or quoted-string parameters,
# but no quoted-pair escapes. Whatever it rejects is recorded as
# DEFAULT_CONTENT_TYPE rather than refused.
_MEDIA_TOKEN = r"[0-9A-Za-z!#$%&'*+.^_`|~-]+"
_MEDIA_QUOTED = r'"[^"\\\x00-\x1f\x7f]*"'
MEDIA_TYPE_PATTERN = re.compile(
    "^{0}/{0}(?:[ \t]*;[ \t]*{0}=(?:{0}|{1}))*$".format(
        _MEDIA_TOKEN, _MEDIA_QUOTED))

# Types a browser executes rather than displays. Terraform provisions no
# public grant on the bucket (infrastructure/terraform/main.tf lines 43-51),
# but a stored object outlives any access policy, so recording an active
# declaration as an opaque stream reduces the browser-execution risk should
# that policy ever widen.
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

# Cloud Storage refuses an object name containing CR or LF, and documents the
# XML 1.0 control range (#x7F-#x84, #x86-#x9F) as breaking object listing; a
# filename reaches this module straight from a multipart or e-mail header.
# The remaining C0 controls and the U+2028/U+2029 separators fold in, and the
# bidirectional formatting characters join them because they change how a name
# renders without changing what it addresses. One set then serves both
# directions - substituted by _build_object_name, refused by
# _validated_object_name - so no name this service could not have minted can
# be addressed through it.
UNSAFE_CODE_POINTS = frozenset(
    list(range(0x00, 0x20)) + list(range(0x7F, 0xA0))
    + [0x2028, 0x2029, 0x200E, 0x200F]
    + list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)))

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
VIRTUAL_HOSTED_SUFFIX = ".storage.googleapis.com"

# The schemes the resolver accepts. Every identifier this service emits is
# HTTPS - blob.public_url on the write path, a signed URL at read time - while
# gs:// is accepted as input only. Any other scheme is refused rather than
# reduced to its tail, a value carrying one not having come from here.
ALLOWED_URI_SCHEMES = frozenset(["gs", "https"])

# Ceiling on the raw identifier, applied before it is parsed. Every form this
# service emits is bounded by construction - a scheme, a host, a bucket and a
# percent-encoded name of at most MAX_OBJECT_NAME_BYTES, which even tripled by
# escaping stays well inside this - so a value beyond it is not an identifier
# that went out of here, and no parsing, decoding or normalising is spent on
# it.
MAX_IDENTIFIER_CHARS = 4096

# A V4 signature cannot outlive seven days; the provider rejects anything
# longer. generate_download_url applies the bound itself so an out-of-policy
# request costs no settings read and no provider call.
MAX_SIGNED_URL_MINUTES = 7 * 24 * 60

_client = None


def _object_id(object_name: str) -> str:
    # Object names are never logged, only this digest of one: the tail of a
    # generated key is a client filename, and the identifier handed to a read
    # helper is whatever the caller passed, so between them they carry merchant
    # data and, for a signed URL, the X-Goog-Credential and X-Goog-Signature
    # parameters that are themselves authorisation to fetch the object. A
    # digest settles the only question a record needs of a name - whether two
    # concern the same object - and sixteen fixed hexadecimal characters cannot
    # reshape the record around it. Truncated sha256 suits an identifier rather
    # than a secret: one way, stable across processes, and unguessable because
    # every generated key carries a uuid4.
    return hashlib.sha256(object_name.encode("utf-8")).hexdigest()[:16]


def _provider_fault(exc: Exception) -> str:
    # The provider's exception string is not safe to log either: api_core
    # formats it as method, request URL and provider message, and the request
    # URL is what carries the object name and, for a signed request, the query
    # that went with it. What is diagnostically useful is the classification
    # around that prose, all of it library-controlled: the exception class, the
    # HTTP status behind it, and whether api_core's own predicate considers the
    # fault transient, which tells an operator to retry rather than
    # investigate. `code` is normalised through int() because api_core carries
    # it as an HTTPStatus, whose str() differs between Python versions.
    status = getattr(exc, "code", None)
    if isinstance(status, int):
        status = int(status)
    return "{0} status={1} transient={2}".format(
        type(exc).__name__, status, google_retry.if_transient_error(exc))


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


def _bucket_name() -> str:
    # The configured bucket is wanted in two places - to build a bucket
    # reference, and to check that a URI identifier names this bucket rather
    # than another - so both go through one accessor and cannot drift apart.
    # get_settings() is not memoised (app/core/config.py lines 18-19), so every
    # call re-reads the environment and probes the configured env_file; no
    # remote I/O is involved.
    return get_settings().GOOGLE_CLOUD_STORAGE_BUCKET


def _get_bucket() -> storage.Bucket:
    # bucket() builds a local reference and performs no existence check, so
    # no extra existence-check request is issued ahead of the operation the
    # caller actually asked for. Terraform provisions the bucket, not this
    # service, so proving it exists on every call would buy nothing.
    return _get_client().bucket(_bucket_name())


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
    # Control and bidirectional code points are substituted in the same pass,
    # per UNSAFE_CODE_POINTS; doing so after strip() keeps a name merely padded
    # with CR, LF or tab from carrying those positions forward as underscores.
    # Normalising to NFC last makes one spelling canonical for every key this
    # module emits, which is what lets _validated_object_name refuse a
    # decomposed identifier without ever refusing one of its own - the provider
    # treats the two spellings as different objects. The readable tail is then
    # bounded by what is left of MAX_OBJECT_NAME_BYTES once the fixed part is
    # spent; truncating rather than refusing keeps the uuid4 that addresses the
    # object, where a refusal would cost a merchant a document over a filename
    # attribute.
    safe_name = (filename or "").strip().replace("\\", "/").replace("/", "_")
    safe_name = unicodedata.normalize(
        "NFC", safe_name.translate(_CONTROL_TABLE))
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


def _percent_decoded(path: str) -> str:
    # Percent-decoding belongs to URI forms only: a URI path is an encoded
    # rendering of the name, whereas a bare object name already is the key and
    # may legally contain a literal '%' that the canonical URL renders as
    # '%25', so decoding one would address a different object on every read,
    # delete, probe and signature. errors="strict" rather than the default,
    # which would replace an invalid escape with U+FFFD and hand back a name
    # nobody asked for; the refusal is raised after the handler has ended
    # because UnicodeDecodeError quotes the undecodable bytes, and an exception
    # raised inside an except block leaves the original on __context__.
    decoded = None
    try:
        decoded = unquote(path, errors="strict")
    except UnicodeDecodeError:
        decoded = None
    if decoded is None:
        raise ValueError("file_path is not a valid object identifier")
    return decoded


def _object_name_from_uri(parsed: ParseResult, scheme: str) -> str:
    # A URI has to be proved to address this bucket before its path may be
    # treated as an object name, and the whole authority is compared rather
    # than the host alone: netloc carries userinfo and port too, so
    # credential-prefixed, port-suffixed and look-alike authorities all fail a
    # comparison a hostname-only check would pass. Only case is normalised,
    # host names being case-insensitive where object names are not. The three
    # recognised layouts differ only in where the bucket sits, and one naming
    # another bucket is refused rather than retargeted into the configured one,
    # which would turn a reference to something elsewhere into an operation
    # against the only bucket this service can reach.
    bucket = _bucket_name()
    authority = parsed.netloc.lower()
    path = parsed.path.lstrip("/")
    if scheme == "gs":
        if authority != bucket.lower():
            raise ValueError("file_path names a different bucket")
    elif authority in PATH_STYLE_HOSTS:
        first, _, remainder = path.partition("/")
        if first != bucket:
            raise ValueError("file_path names a different bucket")
        path = remainder
    elif authority != bucket.lower() + VIRTUAL_HOSTED_SUFFIX:
        raise ValueError("file_path does not address Cloud Storage")
    return _percent_decoded(path)


def _validated_object_name(object_name: str) -> str:
    # The namespace gate: every read, delete, probe and signature in this
    # module reaches the bucket through here, and the identifier is caller
    # text - persisted in a database column, carried through an API schema and
    # a Celery task, with nothing on that path proving it is still a key this
    # service minted. Non-emptiness is not a sufficient test, the bucket being
    # provisioned for the whole application rather than for these attachments,
    # so a plausible-looking name would point this module's credentials at an
    # object it was never meant to touch.
    #
    # Each refusal below therefore names something a generated key cannot
    # contain: one prefix, flattened separators, substituted code points, a
    # composed spelling, non-empty segments and a bounded byte length. The
    # messages name no part of the identifier, a rejected value being able to
    # carry a signed query that is itself authorisation material into whichever
    # upstream handler writes the exception out.
    if not object_name:
        raise ValueError("file_path addresses no object in the bucket")
    if len(object_name.encode("utf-8")) > MAX_OBJECT_NAME_BYTES:
        raise ValueError("file_path names an object the provider cannot hold")
    if "\\" in object_name:
        raise ValueError("file_path is not a name this service writes")
    if any(ord(char) in UNSAFE_CODE_POINTS for char in object_name):
        raise ValueError("file_path is not a name this service writes")
    if unicodedata.normalize("NFC", object_name) != object_name:
        raise ValueError("file_path is not a name this service writes")
    if not object_name.startswith(OBJECT_NAME_NAMESPACE):
        raise ValueError("file_path is outside the attachments namespace")
    if any(part in ("", ".", "..") for part in object_name.split("/")):
        raise ValueError("file_path is not a name this service writes")
    return object_name


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
    # Accepting those forms is not the same as accepting any string. The work
    # splits into three questions asked once each: is the identifier small
    # enough to be worth parsing, does it address this bucket
    # (_object_name_from_uri), and is what it addresses a name this service
    # could have written (_validated_object_name). A scheme nobody here emits
    # is refused rather than stripped to its tail, which would turn a reference
    # to something elsewhere into an operation against the one bucket this
    # service holds credentials for. Emptiness is judged again on the result
    # because every branch can make nothing out of something: an identifier
    # naming only a bucket is not blank yet reduces to "", and blob("") would
    # spend a request on an object that cannot exist.
    if file_path is None or not file_path.strip():
        raise ValueError("file_path is required to address a stored object")
    candidate = file_path.strip()
    if len(candidate) > MAX_IDENTIFIER_CHARS:
        raise ValueError("file_path is too long to be an object identifier")
    parsed = urlparse(candidate)
    scheme = parsed.scheme.lower()
    if not scheme:
        object_name = candidate.lstrip("/")
    elif scheme in ALLOWED_URI_SCHEMES:
        object_name = _object_name_from_uri(parsed, scheme)
    else:
        raise ValueError("file_path does not address Cloud Storage")
    return _validated_object_name(object_name)


def _resolve_content_type(content_type: Optional[str]) -> str:
    # The declared type is checked rather than forwarded, for the reason given
    # at MEDIA_TYPE_PATTERN. A value that is not a well-formed media type is
    # replaced with the documented fallback rather than refused, losing a
    # document over a malformed header being the worse outcome, and the same
    # substitution covers a declaration a browser would execute. Only the type
    # itself is inspected, and no allow-list of document types is applied:
    # this application defines no such policy, and inventing one would start
    # refusing the statements and contracts the pipeline exists to read.
    #
    # Neither warning echoes a rejected declaration. The malformed case has
    # validated nothing about it; the active-content case may name the type it
    # matched, that value having just been proved one of this module's own
    # constants.
    if not content_type:
        return DEFAULT_CONTENT_TYPE
    candidate = content_type.strip()
    if not MEDIA_TYPE_PATTERN.match(candidate):
        logger.warning(
            f"Malformed content type declaration recorded as "
            f"{DEFAULT_CONTENT_TYPE}")
        return DEFAULT_CONTENT_TYPE
    declared = candidate.split(";")[0].strip().lower()
    if declared in ACTIVE_CONTENT_TYPES:
        logger.warning(
            f"Active content type {declared} recorded as "
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
    logged = _object_id(object_name)
    stored_type = _resolve_content_type(content_type)
    blob = _get_bucket().blob(object_name)
    try:
        blob.upload_from_string(file_content, content_type=stored_type)
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to upload object {logged}: {_provider_fault(e)}")
        raise
    logger.info(f"Uploaded {len(file_content)} bytes to object {logged}")
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
    # The body is drawn through _read_bounded rather than a bare file.read(),
    # so an unbounded request body cannot be materialised whole in this
    # process. Authenticating the caller, proving the application exists and
    # undoing a write whose database row never lands belong to the route at
    # app/api/attachments.py lines 9-17, which owns the request and the
    # session; delete_file is exported for the last of them.
    file_content = await _read_bounded(file)
    return upload_attachment(file.filename, file_content, file.content_type)


def get_file_content(file_path: str) -> bytes:
    # Synchronous BY CONTRACT: app/services/ocr_service.py line 7 uses the
    # result directly, feeding it to a Vision image constructor that needs
    # raw bytes. A missing object is logged and RAISED rather than answered
    # with empty bytes, because silently empty OCR input would corrupt every
    # downstream extraction instead of failing at the fault.
    #
    # The re-raise is bare, so the original google.api_core exception travels
    # on with its type, traceback, response and retry state intact: a caller
    # can still tell a NotFound from a transport fault, which a substituted
    # exception would have taken away from it.
    #
    # The read is bounded, which is why this is not a bare
    # download_as_bytes(): the identifier is caller-controlled, so the size of
    # what it names is not this module's to assume, and an object written
    # before MAX_UPLOAD_BYTES existed would otherwise be materialised whole
    # before anyone could object. Asking for the range 0..MAX_UPLOAD_BYTES
    # requests one byte more than policy allows, which makes an over-sized
    # object detectable without holding it, and one ranged request needs no
    # generation precondition where a metadata read first would.
    #
    # raw_download=True is load-bearing: under decompressive transcoding Cloud
    # Storage ignores the Range header and returns the whole object, so the
    # ceiling would silently stop applying, and checksum=None follows because
    # none is published for a partial read. An empty object is the one case a
    # range cannot satisfy - the provider answers 416 - so that answer is read
    # as "holds nothing", as the client library's own BlobReader does, a
    # zero-byte attachment being legitimate.
    object_name = _resolve_object_name(file_path)
    logged = _object_id(object_name)
    blob = _get_bucket().blob(object_name)
    try:
        content = blob.download_as_bytes(
            start=0,
            end=MAX_UPLOAD_BYTES,
            raw_download=True,
            checksum=None,
        )
    except google_exceptions.RequestRangeNotSatisfiable:
        logger.info(f"Object {logged} holds no bytes")
        return b""
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to download object {logged}: {_provider_fault(e)}")
        raise
    if len(content) > MAX_UPLOAD_BYTES:
        logger.error(
            f"Object {logged} exceeds the {MAX_UPLOAD_BYTES} byte read "
            f"limit and was not returned")
        raise ValueError(
            "stored object exceeds the {0} byte read limit".format(
                MAX_UPLOAD_BYTES))
    logger.info(f"Read {len(content)} bytes from object {logged}")
    return content


def delete_file(file_path: str) -> None:
    # Deletion is idempotent on purpose, and this is the ONE place in this
    # module that does not raise: an object that is already gone satisfies
    # the caller's intent, so a miss is a warning rather than a failure. Any
    # other API fault still surfaces unchanged, which is why the NotFound
    # handler comes first - NotFound is a subclass of GoogleAPIError, so the
    # broader handler would otherwise swallow the idempotent case.
    #
    # As everywhere here, the identifier is validated before any network
    # access, so a None, blank, foreign, out-of-namespace or bucket-only one
    # raises ValueError without a request being issued. Validating a URI form
    # does read the configured bucket name, since that is what the URI is
    # checked against, but that read is an environment lookup and touches
    # nothing remote.
    object_name = _resolve_object_name(file_path)
    logged = _object_id(object_name)
    blob = _get_bucket().blob(object_name)
    try:
        blob.delete()
    except google_exceptions.NotFound:
        logger.warning(f"Object {logged} already absent, not deleted")
        return
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to delete object {logged}: {_provider_fault(e)}")
        raise
    logger.info(f"Deleted object {logged}")


def file_exists(file_path: str) -> bool:
    # A miss is an answer here, not a failure, so this returns False and lets
    # callers branch on it without a try block - the client library turns the
    # 404 into False itself. Genuine transport faults are still logged and
    # re-raised, so an unreachable bucket cannot masquerade as an absent one.
    object_name = _resolve_object_name(file_path)
    logged = _object_id(object_name)
    blob = _get_bucket().blob(object_name)
    try:
        return bool(blob.exists())
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to probe object {logged}: {_provider_fault(e)}")
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
    #
    # The lifetime is a policy checked here rather than left to the signer:
    # whole-minute integers from 1 to MAX_SIGNED_URL_MINUTES, validated ahead
    # of any settings read or provider call. A zero or negative value would
    # mint a URL that has already expired, failing at whoever was given it
    # rather than whoever asked for it, and bool is excluded explicitly
    # because it subclasses int, which would otherwise accept True as one
    # minute. The message carries the bound and never the value rejected.
    valid_expiration = (
        isinstance(expiration_minutes, int)
        and not isinstance(expiration_minutes, bool)
        and 1 <= expiration_minutes <= MAX_SIGNED_URL_MINUTES)
    if not valid_expiration:
        raise ValueError(
            "expiration_minutes must be an integer of 1 to {0}".format(
                MAX_SIGNED_URL_MINUTES))
    object_name = _resolve_object_name(file_path)
    logged = _object_id(object_name)
    blob = _get_bucket().blob(object_name)
    try:
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="GET",
        )
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Failed to sign a URL for object {logged}: {_provider_fault(e)}")
        raise
