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

import hashlib
import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import ParseResult, unquote, urlparse

import google.auth
from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
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

# How many hexadecimal characters of a SHA-256 digest stand in for an
# identifier that must be named in a log record or an error message. Sixteen
# is 64 bits - far more than enough to tell two documents apart in a support
# conversation - while the digest itself remains one way, which is the whole
# point: the value in the record cannot be turned back into the filename it
# refers to. See _digest.
REF_DIGEST_LENGTH = 16

# The shape of the token _build_object_name puts in front of every key it
# generates, so that _object_ref can recognise its own work and quote the
# UUID instead of hashing the whole name.
UUID_HEX_CHARACTERS = frozenset("0123456789abcdef")
UUID_HEX_LENGTH = 32

# Cached client handle; stays None until the first storage operation runs.
# See _get_client for why that emptiness at import time is the whole point.
_client = None

# Cached signing identity, resolved only when generate_download_url runs and
# empty until then, for the same import-time reason as _client above.
_signing_credentials = None

# Cached authentication transport, built on the first credential refresh and
# reused afterwards. See _get_auth_transport.
_auth_request = None

# The three caches above are read by every worker thread this process runs -
# uvicorn's request pool, the thread run_in_threadpool hands uploads to, and
# each Celery worker thread - so "if it is None, build it" is a race, not an
# initialisation. Each guard below turns its cache into a
# build-exactly-once, and they are SEPARATE locks on purpose: a request
# waiting for a storage client must not queue behind an unrelated token
# refresh. None of them is ever held across a Cloud Storage or IAM call.
_client_lock = threading.Lock()
_credentials_lock = threading.Lock()
_refresh_lock = threading.Lock()


def _log_safe(value: str) -> str:
    # Escapes anything that could break out of a single log record before it
    # is interpolated into one. Its remaining inputs are deliberately narrow:
    # the configured bucket name and the host of a rejected identifier. It is
    # NOT what protects a filename, because a filename never reaches a record
    # at all - _object_ref and _candidate_ref replace those with opaque
    # values before anything is written. Escaping still matters for what is
    # left, since an environment variable or a URL host can carry a newline,
    # and a forged log record is indistinguishable from a genuine one after
    # the fact (CWE-117).
    return "".join(
        "\\x{0:02x}".format(ord(char)) if char in CONTROL_CHARACTERS else char
        for char in value
    )


def _digest(value: str) -> str:
    # One way, stable, and short enough to quote. Two records about the same
    # object carry the same digest, so an operator can still join them
    # together, but nothing in the digest says what the object was called.
    encoded = value.encode("utf-8", "replace")
    return "sha256:{0}".format(
        hashlib.sha256(encoded).hexdigest()[:REF_DIGEST_LENGTH])


def _object_ref(object_name: str) -> str:
    # The correlation value that stands in for an object name in EVERY record
    # this module writes, because an object name ends in the filename the
    # merchant supplied. Those filenames describe the document and often the
    # person - "Jane_Doe_SSN-1234_tax_return.pdf" is an entirely ordinary one
    # for a funding application - so writing one into a log line copies
    # personal data out of a private bucket and into a log sink with a
    # different audience, a different retention period and, in this
    # deployment, a different access-control story altogether. High-cardinality
    # document metadata in a log index is a disclosure, not a diagnostic.
    #
    # The uuid4 token _build_object_name already places in front of every key
    # is preferred wherever it is present: it is unique per object, contains
    # nothing of the filename, and one prefix listing turns it back into the
    # object when an operator legitimately needs to. An identifier this module
    # did not generate carries no such token, so it is reduced to a digest of
    # itself instead - correlatable, never reversible.
    token = object_name.rsplit("/", 1)[-1].split("-", 1)[0]
    if (len(token) == UUID_HEX_LENGTH
            and set(token) <= UUID_HEX_CHARACTERS):
        return token
    return _digest(object_name)


def _candidate_ref(parsed: ParseResult, candidate: str) -> str:
    # Describes a REJECTED identifier without reproducing it, for the
    # ValueError messages raised by the two resolver helpers below.
    #
    # A rejected candidate is the most dangerous string this module handles.
    # It arrives from the storage_url column or a Celery task argument, it may
    # well be a signed URL, and a signed URL keeps its authorisation IN THE
    # QUERY STRING: X-Goog-Signature together with X-Goog-Credential is a
    # bearer token for the object it names. get_file_content resolves the
    # identifier OUTSIDE its try block, and neither app/services/ocr_service.py
    # nor app/tasks/celery_tasks.py catches ValueError, so whatever this text
    # holds travels into a worker traceback and from there into a log sink.
    # That is precisely how a credential escapes inside an error message.
    #
    # So the raw value is never echoed. What is reported is the scheme and the
    # host - enough for an operator to see WHY it was refused, whether that is
    # a foreign origin, a wrong bucket or an impossible scheme - plus a digest
    # that ties this message to one specific request. Path, query and fragment
    # are all dropped. hostname rather than netloc is used, so any userinfo in
    # a "https://user:secret@host/..." form is dropped with them.
    origin = "opaque"
    if parsed.scheme:
        origin = "{0}://{1}".format(
            parsed.scheme.lower(), parsed.hostname or "")
    return "origin={0} ref={1}".format(_log_safe(origin), _digest(candidate))


def _error_detail(error: BaseException) -> str:
    # Names a failure by its type and, where the client library exposes one,
    # its numeric status - and nothing else. str(error) is never interpolated:
    # a google.api_core exception renders itself as the request that failed,
    # so its text carries the full object path (filename included), whatever
    # query parameters that request was signed with, and a verbatim slice of
    # the response body. The exception object is re-raised untouched, so a
    # caller that needs the detail still has every byte of it; what changes is
    # only what this module WRITES DOWN about it.
    detail = type(error).__name__
    code = getattr(error, "code", None)
    if isinstance(code, int):
        detail = "{0}(status={1:d})".format(detail, int(code))
    return detail


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
    #
    # Called EXACTLY ONCE per public operation, at the top, and then passed
    # down to everything that needs it. That is not tidiness: get_settings()
    # is not memoised (app/core/config.py lines 18-19), so every call
    # constructs a fresh Settings and re-runs pydantic's validation over the
    # environment and the .env file. When the resolver read the setting for
    # itself and _get_bucket read it again, one canonical-URL read, delete,
    # existence probe or signature paid for two of those passes before it
    # reached the network. Threading one already-validated value through
    # instead also guarantees the two uses above see the SAME name even if
    # the environment were mutated mid-request.
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
    #
    # The build is double-checked under a lock because "cached" and "built
    # once" are not the same claim. A cold start serves its first requests
    # concurrently, and an unguarded check-then-set lets every one of those
    # threads see None, construct its own storage.Client, resolve
    # Application Default Credentials for itself, and then overwrite the
    # cache - so the very burst that most needs a warm connection pool is
    # the one that fragments into N of them and pays N metadata round trips.
    # The fast path stays a plain read of the global: the lock is taken only
    # while the cache is still empty.
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = storage.Client(project=_get_project_id())
    return _client


def _get_bucket(bucket_name: str) -> storage.Bucket:
    # bucket() builds a local reference and performs no existence check, so
    # every public call below costs exactly one storage round trip instead of
    # two. The bucket is provisioned by Terraform, not by this service, so
    # proving it exists on each request would buy nothing.
    #
    # The name is taken as an argument rather than read here, because the
    # caller has already validated it once through _get_bucket_name and a
    # second read would repeat a whole pydantic validation pass for a value
    # it is already holding.
    return _get_client().bucket(bucket_name)


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


def _bucket_relative_path(
    parsed: ParseResult,
    candidate: str,
    bucket_name: str,
) -> str:
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
    # at this stage so that an encoded separator cannot masquerade as a real
    # one while the bucket segment is removed; _resolve_object_name decodes it
    # once that segment is gone.
    #
    # The name compared against is the one the calling public function
    # already validated through _get_bucket_name, handed down rather than
    # re-read: a blank configuration value cannot reduce the comparison below
    # to a formality that every candidate satisfies, and the object this
    # request goes on to address is guaranteed to be in the very bucket the
    # identifier was checked against.
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path.lstrip("/")
    #
    # Every refusal below reports the candidate through _candidate_ref rather
    # than quoting it, and none of them repeats a value taken from the PATH -
    # not the bucket segment a path-style URL carries, and certainly not the
    # object name. The scheme and host in that reference already say which
    # rule was broken.
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path.lstrip("/")
    if scheme == "gs":
        if host != bucket_name.lower():
            raise ValueError(
                "file_path does not name the configured bucket: "
                "{0}".format(_candidate_ref(parsed, candidate)))
        return path
    if scheme != "https":
        raise ValueError(
            "file_path uses an unsupported scheme: {0}".format(
                _candidate_ref(parsed, candidate)))
    if host in GCS_ENDPOINT_HOSTS:
        # Path-style: the bucket is the first path segment and has to go,
        # but only once it has been confirmed to be ours.
        first, separator, remainder = path.partition("/")
        if first != bucket_name or not separator:
            raise ValueError(
                "file_path does not name the configured bucket: "
                "{0}".format(_candidate_ref(parsed, candidate)))
        return remainder
    for endpoint in GCS_ENDPOINT_HOSTS:
        # Virtual-hosted: the bucket is a hostname prefix instead, so the
        # path already IS the object name and stripping a segment from it
        # would corrupt the name.
        if host == "{0}.{1}".format(bucket_name.lower(), endpoint):
            return path
    raise ValueError(
        "file_path is not a Cloud Storage identifier for the configured "
        "bucket: {0}".format(_candidate_ref(parsed, candidate)))


def _resolve_object_name(file_path: str, bucket_name: str) -> str:
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
    #
    # None of those refusals quotes the candidate either - see _candidate_ref
    # for why an identifier that reaches this function must be treated as
    # potentially credential-bearing, and for what is reported instead.
    if file_path is None:
        raise ValueError("file_path is required to address an object")
    candidate = str(file_path).strip()
    if not candidate:
        raise ValueError("file_path must not be empty")
    parsed = urlparse(candidate)
    if parsed.scheme:
        path = _bucket_relative_path(parsed, candidate, bucket_name)
    else:
        path = candidate.lstrip("/")
    object_name = unquote(path)
    if not object_name.startswith(ATTACHMENT_PREFIX + "/"):
        raise ValueError(
            "file_path does not address an object under '{0}/': {1}".format(
                ATTACHMENT_PREFIX, _candidate_ref(parsed, candidate)))
    segments = object_name.split("/")
    if any(not segment or segment in (".", "..") for segment in segments):
        raise ValueError(
            "file_path has an empty or relative path segment: {0}".format(
                _candidate_ref(parsed, candidate)))
    if any(char in CONTROL_CHARACTERS for char in object_name):
        raise ValueError(
            "file_path has control characters: {0}".format(
                _candidate_ref(parsed, candidate)))
    if len(object_name.encode("utf-8")) > MAX_OBJECT_NAME_BYTES:
        raise ValueError(
            "file_path exceeds the {0}-byte object name limit".format(
                MAX_OBJECT_NAME_BYTES))
    return object_name


def _get_auth_transport() -> google_auth_transport.Request:
    # One transport for the life of the process. google.auth's Request builds
    # itself a brand-new requests.Session whenever it is constructed without
    # one, and a Session is where the connection pool lives - so building a
    # Request per refresh discards the pooled connection and its TLS handshake
    # every time, on a metadata call that sits directly on the critical path
    # of a signed URL.
    #
    # Called only while _refresh_lock is held, which is what serialises its
    # construction; it deliberately has no lock of its own.
    global _auth_request
    if _auth_request is None:
        _auth_request = google_auth_transport.Request()
    return _auth_request


def _needs_refresh(
    credentials: google_auth_credentials.Credentials,
) -> bool:
    # A token is refreshed when it is actually unusable, never on principle.
    # credentials.valid is the same gate google-auth applies internally in
    # Credentials._blocking_refresh: a token is present AND is not yet within
    # the library's own refresh threshold of its expiry. Refreshing a token
    # that still satisfies that is pure cost - on Cloud Run the metadata
    # server is allowed up to five three-second attempts - and it buys
    # nothing, because the signature that follows would have been produced
    # with the same token either way.
    #
    # The second condition is an identity question rather than an expiry one:
    # a compute-engine credential reports service_account_email as the
    # literal string "default" until a refresh has answered with the real
    # address, and the IAM signBlob route cannot name a signer with a
    # placeholder. So a credential that is otherwise valid but still
    # anonymous is refreshed once to learn who it is.
    if not credentials.valid:
        return True
    email = getattr(credentials, "service_account_email", None)
    return email == "default"


def _resolve_signing_credentials() -> google_auth_credentials.Credentials:
    # Double-checked under its own lock, for the reason given in _get_client
    # and with a sharper edge: concurrent first signatures would each run
    # Application Default Credentials discovery AND then each refresh their
    # own copy, so a burst would turn one shared token into N tokens minted
    # in parallel while N threads overwrote the same cache. Resolution is
    # serialised here; the signBlob call it enables happens later, in
    # generate_download_url, outside every lock.
    global _signing_credentials
    if _signing_credentials is None:
        with _credentials_lock:
            if _signing_credentials is None:
                try:
                    credentials, _ = google.auth.default(
                        scopes=list(SIGNING_SCOPES))
                except google_auth_exceptions.GoogleAuthError as e:
                    logger.error(
                        f"Failed to resolve signing credentials: "
                        f"error={_error_detail(e)}")
                    raise
                _signing_credentials = credentials
    return _signing_credentials


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
    # are supplied - which is what this helper supplies. It refreshes the
    # credential only when _needs_refresh says the token is unusable or the
    # identity is still the compute-engine placeholder, so a warm cached token
    # is reused across signatures instead of being reminted for each one. A
    # credential that CAN sign locally, such as a service-account key or an
    # impersonated identity, is returned untouched and never refreshed at all,
    # so a deployment that grows a signing key needs no change here.
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
    credentials = _resolve_signing_credentials()
    if isinstance(credentials, google_auth_credentials.Signing):
        return {"credentials": credentials}
    if _needs_refresh(credentials):
        with _refresh_lock:
            # Re-checked inside the lock so that a burst of requests which all
            # saw the same stale token performs ONE refresh between them
            # rather than one each, and so that no two of them mutate the
            # shared credential's token and expiry at the same moment. Only
            # the refresh is serialised - the signBlob round trip stays
            # outside, in generate_download_url, or one slow IAM call would
            # hold up every other signature in the process.
            if _needs_refresh(credentials):
                try:
                    credentials.refresh(_get_auth_transport())
                except google_auth_exceptions.GoogleAuthError as e:
                    logger.error(
                        f"Failed to refresh signing credentials: "
                        f"error={_error_detail(e)}")
                    raise
    email = getattr(credentials, "service_account_email", None)
    token = getattr(credentials, "token", None)
    if not email or email == "default" or not token:
        message = (
            "The active credentials cannot sign a download URL: they carry "
            "no private key and no service account identity for the IAM "
            "signBlob API")
        logger.error(message)
        raise google_auth_exceptions.GoogleAuthError(message)
    return {
        "credentials": credentials,
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
    bucket_name = _get_bucket_name()
    bucket = _get_bucket(bucket_name)
    blob = bucket.blob(object_name)
    try:
        blob.upload_from_string(
            file_content,
            content_type=content_type or DEFAULT_CONTENT_TYPE,
        )
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Upload failed: object={_object_ref(object_name)} "
            f"bucket={_log_safe(bucket_name)} error={_error_detail(e)}")
        raise
    logger.info(
        f"Uploaded {len(file_content)} bytes: "
        f"object={_object_ref(object_name)} "
        f"bucket={_log_safe(bucket_name)}")
    return blob.public_url


async def upload_file(file: UploadFile) -> str:
    # Awaitable BY CONTRACT: app/api/attachments.py line 17 reads
    # "file_url = await upload_file(file)". UploadFile.read is itself a
    # coroutine, so the request body has to be awaited here before the
    # synchronous storage call can be handed bytes. Delegating rather than
    # duplicating keeps one key-building and one error-handling path for both
    # entry points, and FastAPI may leave filename or content_type empty, so
    # both fall through to the defaults applied downstream.
    #
    # The delegate is OFFLOADED rather than called inline, and that is the
    # whole point of this line. upload_attachment is synchronous by contract
    # for the e-mail poller, and its blob.upload_from_string performs blocking
    # socket I/O with a sixty-second default timeout. Called directly from
    # this coroutine it would run ON the event-loop thread, where nothing else
    # can be serviced while it waits: every other request in flight, every
    # health probe and every keep-alive stalls for the duration of one
    # merchant's document upload, and on Cloud Run a stalled container looks
    # unhealthy. run_in_threadpool hands the call to Starlette's BOUNDED
    # worker pool - bounded matters, since an unbounded one would trade a
    # blocked loop for unbounded thread growth - so the loop returns to
    # servicing other work immediately and resumes here when the upload
    # finishes. The e-mail path is untouched: it still calls the synchronous
    # function directly from its own thread, where blocking is correct.
    if file is None:
        raise ValueError("file is required to upload an attachment")
    file_content = await file.read()
    return await run_in_threadpool(
        upload_attachment, file.filename, file_content, file.content_type)


def get_file_content(file_path: str) -> bytes:
    # Synchronous BY CONTRACT: app/services/ocr_service.py line 8 uses the
    # result directly, feeding it to a Vision image constructor that needs
    # raw bytes. A missing object is logged and RE-RAISED rather than
    # answered with empty bytes, because silently empty OCR input would
    # corrupt every downstream extraction instead of failing at the fault.
    bucket_name = _get_bucket_name()
    object_name = _resolve_object_name(file_path, bucket_name)
    bucket = _get_bucket(bucket_name)
    blob = bucket.blob(object_name)
    try:
        return blob.download_as_bytes()
    except google_exceptions.NotFound as e:
        logger.error(
            f"Object not found: object={_object_ref(object_name)} "
            f"bucket={_log_safe(bucket_name)} error={_error_detail(e)}")
        raise
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Download failed: object={_object_ref(object_name)} "
            f"bucket={_log_safe(bucket_name)} error={_error_detail(e)}")
        raise


def delete_file(file_path: str) -> None:
    # Deletion is idempotent on purpose, and this is the ONE place in this
    # module that does not re-raise: an object that is already gone satisfies
    # the caller's intent, so a miss is a warning rather than a failure. Any
    # other API fault still surfaces.
    bucket_name = _get_bucket_name()
    object_name = _resolve_object_name(file_path, bucket_name)
    bucket = _get_bucket(bucket_name)
    blob = bucket.blob(object_name)
    try:
        blob.delete()
    except google_exceptions.NotFound:
        logger.warning(
            f"Object already absent: object={_object_ref(object_name)} "
            f"bucket={_log_safe(bucket_name)}")
        return
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Delete failed: object={_object_ref(object_name)} "
            f"bucket={_log_safe(bucket_name)} error={_error_detail(e)}")
        raise
    logger.info(
        f"Deleted: object={_object_ref(object_name)} "
        f"bucket={_log_safe(bucket_name)}")


def file_exists(file_path: str) -> bool:
    # A miss is an answer here, not a failure, so this returns False and lets
    # callers branch on it without a try block. Genuine transport faults are
    # still logged and re-raised, so an unreachable bucket can never
    # masquerade as an absent object.
    bucket_name = _get_bucket_name()
    object_name = _resolve_object_name(file_path, bucket_name)
    bucket = _get_bucket(bucket_name)
    blob = bucket.blob(object_name)
    try:
        return bool(blob.exists())
    except google_exceptions.NotFound:
        return False
    except google_exceptions.GoogleAPIError as e:
        logger.error(
            f"Existence probe failed: object={_object_ref(object_name)} "
            f"bucket={_log_safe(bucket_name)} error={_error_detail(e)}")
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
    bucket_name = _get_bucket_name()
    object_name = _resolve_object_name(file_path, bucket_name)
    signing_kwargs = _get_signing_kwargs()
    bucket = _get_bucket(bucket_name)
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
            f"Signing failed: object={_object_ref(object_name)} "
            f"bucket={_log_safe(bucket_name)} error={_error_detail(e)}")
        raise
