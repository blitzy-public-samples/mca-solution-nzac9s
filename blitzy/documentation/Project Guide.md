# Blitzy Project Guide — MCA Cloud Storage Persistence Layer Restoration

---

## 1. Executive Summary

### 1.1 Project Overview

The MCA (Merchant Cash Advance) platform ingests funding applications and their supporting documents through a FastAPI backend on Google Cloud, extracting data with Cloud Vision OCR and persisting attachments to Cloud Storage. Its entire document-handling path was inert: `app/services/storage_service.py` did not exist while three backend modules imported three distinct symbols from it at module scope, so six modules raised `ModuleNotFoundError` before loading. This engagement restored that persistence layer, cleared a second independent import failure in the OCR service, and created the dependency manifest that four automation paths already read. Target users are underwriting operations staff and the automated intake pipeline; the business impact is that documents can now be stored, retrieved and OCR'd at all.

### 1.2 Completion Status

```mermaid
%%{init: {'theme':'base','themeVariables':{'pie1':'#5B39F3','pie2':'#FFFFFF','pieStrokeColor':'#B23AF2','pieStrokeWidth':'2px','pieOuterStrokeColor':'#B23AF2','pieTitleTextSize':'16px','pieSectionTextSize':'14px','pieLegendTextSize':'13px'}}}%%
pie showData title 60.7% Complete
    "Completed Work" : 100.5
    "Remaining Work" : 65.0
```

> **Legend** — Completed = Dark Blue `#5B39F3` · Remaining = White `#FFFFFF`

| Metric | Value |
|---|---|
| **Total Hours** | **165.5** |
| **Completed Hours (AI + Manual)** | **100.5** (AI / autonomous 100.5 · Manual 0.0) |
| **Remaining Hours** | **65.0** |
| **Percent Complete** | **60.7 %** |

**Calculation shown explicitly (PA1 methodology, AAP-scoped work only):**

```
Completed Hours = 100.5   (25 AAP-specified items, all classified COMPLETED)
Remaining Hours =  65.0   (11 path-to-production items, all classified NOT STARTED)
Total Hours     = 100.5 + 65.0 = 165.5
Completion %    = (100.5 / 165.5) x 100 = 60.7 %
```

The work universe is exactly the two categories PA1 permits: (a) every deliverable the Agent Action Plan specifies, and (b) the standard path-to-production activities required to deploy those deliverables. **100 % of the AAP-specified scope (100.5 h of 100.5 h) is delivered and validated**; the entire 65.0 h remainder is path-to-production work, most of which the AAP itself enumerated as deferred follow-ups in §0.6.2.4.

### 1.3 Key Accomplishments

- ✅ **`backend/app/services/storage_service.py` created** — 667 lines, 6 public functions and 12 private helpers, **0 lint findings**. The public surface was derived from the existing call sites rather than invented, so `attachments.py`, `email_processor.py` and `config.py` required **zero edits**.
- ✅ **The reported defect is eradicated** — `ModuleNotFoundError: No module named 'app.services.storage_service'` no longer appears anywhere: a grep across **all eight** backend modules' import output returns **0**.
- ✅ **The masked second root cause is fixed** — `ocr_service.py` line 2 (`from google.cloud.vision import types`, removed in `google-cloud-vision` 2.0) deleted and line 15 substituted with `vision.Image`, in **exactly two line changes**.
- ✅ **`backend/requirements.txt` created** — 18 pinned distributions across 7 commented groups plus a 28-line ledger of residual advisories. Installs with exit 0 and a clean `pip check` on a **virgin Python 3.9.25 interpreter**.
- ✅ **All six AAP verification gates pass**, independently re-run and re-confirmed during this assessment: import resolution 5/5, signature eradication 0, contract conformance exact for all six signatures, functional suite 116/116, manifest resolvability exit 0, configuration compatibility correct with `config.py` unedited.
- ✅ **Zero-net regression, measured in both directions** — repository-wide flake8 is **exactly 160**, identical to the pre-change baseline; `storage_service.py` scores **0**; `ocr_service.py` holds at **8** (its pre-existing findings deliberately preserved). Test collection yields **exactly 3 errors**, the AAP's stated pass condition.
- ✅ **The storage boundary is proven at runtime, not just at import** — a real Chrome multipart upload through the real, unmodified router wrote a 611-byte object to `attachments/2026/08/04/…` with a byte-exact sha256 round trip, corroborated three independent ways.
- ✅ **Credentials are never touched at import** — `_client is None` immediately after import and still `None` after 8 object writes plus reads and deletes under live traffic.
- ✅ **Container build succeeds** — `docker build --no-cache` exit 0, with the deliverable present in the image and all gates green in-image.
- ✅ **Scope discipline held** — the diff against the pre-agent baseline touches **4 paths**, +809/−4 lines, across 29 commits all authored and committed as `Blitzy Agent <agent@blitzy.com>`.

### 1.4 Critical Unresolved Issues

Every item below is a **pre-existing defect in a file the AAP explicitly placed out of scope**. None is a regression, and none originates in the three delivered files.

| Issue | Impact | Owner | ETA |
|---|---|---|---|
| Upload route returns HTTP 500 *after* the storage write succeeds — `attachments.py:20-24` builds `Attachment(application_id, file_name, file_url)` while the schema's only fields, all required, are `storage_url`/`type`/`upload_date`, then passes a pydantic instance to `db.add()` | Attachment API unusable end to end; objects are written but orphaned with no database row | Backend engineer | 6.0 h (R4) |
| FastAPI app cannot boot — 4 defects: `applications.py:5` missing `ApplicationCreate`; `main.py:6` missing `init_db`; `main.py:18` `HTTPException` unimported; `main.py:24` undeclared `CORS_ORIGINS` read at import | Attachment router never registers, so the delivered module is unreachable over HTTP | Backend engineer | 6.0 h (R3) |
| Celery worker cannot boot — `webhook_service.py:2` imports a `Webhook` model absent from `models.py` | OCR/document task tier unreachable; the worker now advances *past* the storage barrier but stops here | Backend engineer | 5.0 h (R5) |
| Container package flattening — `Dockerfile.backend:24` `COPY ./app /app` with `:30 CMD uvicorn main:app`; reproduced as `ModuleNotFoundError: No module named 'app'` inside the built image | The module ships in the image but cannot be imported there | DevOps engineer | 4.0 h (R2) |
| `generate_download_url` will raise on Cloud Run — V4 signing needs a private key that ADC does not supply, and `roles/iam.serviceAccountTokenCreator` is confirmed **absent from all of `infrastructure/`** | Read-time signed URLs unavailable; documented in-code at the helper | Cloud/IAM engineer | 3.0 h (R6) |
| No committed automated coverage for the storage/OCR path — the committed suite collects 0 tests with 3 errors (the AAP's own pass condition) and `test_api.py:48` is an assertion-free `pass` stub | Verification lives only in out-of-tree harnesses and will not survive the next checkout; no coverage % can be reported | QA engineer | 12.0 h (R8) |
| Frontend does not render — `/` 404s, `/index.html` serves statically from `public/` with **zero `<script>` elements**, 50 TypeScript errors, 5 components absent from the repository, no `vite.config.*` | `DocumentViewer` cannot consume `storage_url`. **Provably pre-existing: zero frontend files differ from baseline `543db77d`** and no request in the whole browser session reached a backend origin | Frontend engineer | Excluded from hours — outside AAP scope (see §2.2 note) |
| Retained scope deviation — `infrastructure/docker/Dockerfile.backend` was modified by a prior agent to add `pip==26.0.1` / `wheel==0.47.0` CVE floors although AAP §0.6.2.1 marks the file do-not-touch | Reverting reintroduces CVE-2026-24049; retaining leaves one authorised-scope breach on the record | Tech lead | 1.0 h decision (in R2) |

### 1.5 Access Issues

| System/Resource | Type of Access | Issue Description | Resolution Status | Owner |
|---|---|---|---|---|
| Google Cloud project `mca-dev` | Application Default Credentials | No GCP project or network egress exists in the validation environment, so the module has never run against a live Cloud Storage bucket. This is the AAP's own declared residual (3 % of a 97 %-confidence verification). Every API used was confirmed present on the installed client by runtime introspection, and all behaviour was proven against a mocked client. | **Open** — requires a provisioned project; task R1 | Cloud engineer |
| `google_storage_bucket.mca_documents` | Object read/write | Bucket is declared in Terraform (`main.tf:43-46`) but has never been reached. `roles/storage.admin` is already granted (`main.tf:132`), so no new privilege is required. | **Open** — blocked by the item above; task R1 | Cloud engineer |
| IAM Service Account Credentials API + `roles/iam.serviceAccountTokenCreator` | Token minting for V4 signing | Confirmed **absent from every file under `infrastructure/`** by repository-wide grep. Without it `generate_download_url` raises on Cloud Run. The upload path deliberately returns a canonical URL so it operates entirely within the already-granted `roles/storage.admin`. | **Open** — Terraform change, out of AAP scope; task R6 | Cloud/IAM engineer |
| Cloud SQL / PostgreSQL | Database connection | `DATABASE_URL` is supplied from the shell only; no instance was reachable, so the persistence half of the attachment flow is unverified. `db.commit()` is never reached because the ValidationError fires first. | **Open** — tasks R1 + R4 | Backend/DBA |
| Cloud Vision API | Document text detection | No live `document_text_detection` call was ever made; quota, billing and per-document latency are unknown. The image object construction was verified for real (`google.cloud.vision_v1.types.image_annotator.Image`). | **Open** — task R1 | Cloud engineer |
| Celery broker (Redis) | Broker connection | `celery_tasks.py:9` reads an undeclared `CELERY_BROKER_URL` at import time and the worker cannot boot, so no task has ever dispatched. | **Open** — task R5 | Backend engineer |
| Secret storage | Secret Manager / env vars | Secrets come from `/opt/mca-setup/env.sh`, deliberately outside the checkout because the AAP forbids committing `.env` or `.env.example`. There is therefore no committed template and no Secret Manager wiring. | **Open** — task R1 | DevOps engineer |
| Repository (`blitzy-45010d62-f978-408b-9671-3305d7056f1e`) | Read/write | No access issue. All 29 commits landed successfully; working tree clean; `git diff HEAD` empty. | **Resolved** | — |
| Docker daemon | Image build | No access issue. `docker build --no-cache` completed with exit 0 during this assessment. | **Resolved** | — |
| PyPI / npm registries | Package download | No access issue. Manifest installed on three separate virgin interpreters with exit 0; `npm install` succeeded. | **Resolved** | — |

### 1.6 Recommended Next Steps

1. **[High]** Unblock application and worker boot — define `ApplicationCreate`, add `init_db`, import `HTTPException`, declare `CORS_ORIGINS`, and add the `Webhook` model. Until this lands, the delivered storage module cannot be reached by any request or task in production. *(R3 + R5, 11.0 h)*
2. **[High]** Repair the attachment persistence contract and add authentication plus the application-existence check left as a TODO — this converts a proven-good storage write into a working end-to-end endpoint and stops orphaning objects. *(R4, 6.0 h)*
3. **[High]** Provision the GCP project and ADC, wire the seven no-default settings into Cloud Run / Secret Manager, and run the module against a live bucket to close the AAP's declared 3 % residual. *(R1, 7.0 h)*
4. **[High]** Fix the container package flattening so `import app.*` resolves inside the image, and ratify or revert the retained `Dockerfile.backend` CVE-floor deviation. *(R2, 4.0 h)*
5. **[Medium]** Commit an in-tree regression suite for the storage/OCR path and repair the three collection blockers, so `ci.yml:37` becomes a meaningful gate and a coverage figure exists at all. *(R8, 12.0 h)*

---

## 2. Project Hours Breakdown

### 2.1 Completed Work Detail

Every row traces to a specific Agent Action Plan section. Totals to **100.5 h**, matching Completed Hours in §1.2.

| Component | Hours | Description |
|---|---|---|
| **[AAP §0.5.1.1] Contract derivation from the three call sites** | 4.0 | Awaitability, arity, argument and return types, and the non-obvious round-trip contract inferred from `attachments.py:17`, `email_processor.py:46` and `ocr_service.py:7` so that no call site required an edit. Verified by Gate 3 — all six signatures string-exact. |
| **[AAP §0.5.1.1] Lazy cached client and bucket resolution** | 3.0 | `_get_client`, `_bucket_name`, `_get_bucket`; settings read inside functions, never at import. Proven by `_client is None` post-import and still `None` after 8 live writes — deliberately unlike the import-time pattern at `database.py:5`. |
| **[AAP §0.5.1.1] `upload_attachment` (synchronous by contract)** | 3.0 | `(filename: str, file_content: bytes, content_type: Optional[str] = None) -> str`; returns the canonical HTTPS object URL, applies the content-type fallback and enforces the upload ceiling before any I/O. |
| **[AAP §0.5.1.1] `upload_file` (awaitable by contract)** | 2.5 | `(file: UploadFile) -> str` with `_read_bounded`, so an unbounded request body cannot be materialised whole in-process; delegates to the synchronous path for one key-building and error-handling route. |
| **[AAP §0.5.1.1] `get_file_content` (synchronous by contract)** | 2.0 | `(file_path: str) -> bytes`; `NotFound` logged and re-raised rather than swallowed, so callers observe a miss instead of receiving empty bytes. |
| **[AAP §0.5.1.1] `_build_object_name` — collision-proof keys** | 3.0 | `attachments/%Y/%m/%d/<uuid4hex>-<safe_filename>` on `datetime.utcnow()`; filename sanitisation (`a/b/evil.pdf` → `a_b_evil.pdf`, empty → `unnamed`) and byte-budget truncation under `MAX_OBJECT_NAME_BYTES`. |
| **[AAP §0.5.1.1] `_resolve_object_name` — the normalising resolver** | 6.0 | Reduces every identifier the service has ever emitted back to one bucket-relative name: bare, leading-slash, `gs://`, and all three HTTPS host layouts, with signature query strings discarded and URI-only percent-decoding. Adds a namespace gate (`attachments/` prefix, NFC normalisation, control-code-point and segment checks) and refuses foreign buckets and foreign schemes rather than retargeting them. |
| **[AAP §0.5.1.1] `delete_file`, `file_exists`, `generate_download_url`** | 3.0 | Idempotent deletion (absent object logs a warning and returns), a non-raising existence probe, and a V4 signing helper shipped with its unmet infrastructure prerequisite stated in full in an in-code comment. |
| **[AAP §0.5.1.1] Error handling and telemetry redaction** | 3.0 | Eight handlers, every one naming a specific type — `UnicodeDecodeError`, `GoogleAPIError` ×4, `RequestRangeNotSatisfiable`, `NotFound`. Zero bare `except`, zero `except Exception`, zero `print()`. `ValueError` raised before any network call; `_object_id` and `_provider_fault` keep caller-supplied identifiers out of log records. |
| **[AAP §0.8.1] Convention conformance and the mandated comment programme** | 4.0 | UTC-only timestamps, module-level standard-library logger, full annotations on every parameter and return, zero docstrings (matching all eight existing service/API modules), flat top-level functions, 79-column discipline. **667 lines at 0 flake8 findings.** |
| **[AAP §0.5.1.4] Dependency discovery from source** | 2.0 | Every distribution the codebase actually imports, mapped against the four consumers that already read the manifest — `ci.yml:29`, `Dockerfile.backend:8` and `:11`, `setup_environment.sh:13`. |
| **[AAP §0.5.1.4] Compatibility-envelope resolution** | 8.0 | Empirically established: pydantic below 2.0 because `config.py:1` imports `BaseSettings`, which in turn caps FastAPI at 0.125.0; SQLAlchemy 2.x because `models.py:1` imports `UUID` from the root namespace; Cloud Vision on a release that publishes `Image` at the package root, after executing and rejecting the backwards-pin route; the bcrypt provider bound narrowed to 4.0.1 after observing passlib's over-length probe fail on bcrypt 5 and `__about__` removal on 4.1.0+. |
| **[AAP §0.5.1.4] CVE floor research and the residual-advisory ledger** | 5.0 | Security floors raised where a remedy exists inside the Python 3.9 envelope, and a 28-line in-file ledger recording the eight residuals that do not — each checked against this tree and documented as unreachable. |
| **[AAP §0.5.2.3] Manifest authoring and citation audit** | 3.0 | 18 `==` pins across 7 commented groups with per-pin rationale, plus an exhaustive audit of all 34 `file:line` citations across the three in-scope files to 34/34 accurate. |
| **[AAP §0.7.1.5] Gate 5 — manifest resolvability** | 2.5 | Install verified on virgin Python 3.9.25 interpreters with `pip check` clean and every pin introspected. Re-confirmed during this assessment on a freshly created venv: exit 0, no broken requirements, resolver results matching the manifest's own documented claims. |
| **[AAP §0.5.1.3] Root-cause-2 diagnosis** | 3.0 | `vision.types` removal established by runtime introspection (`hasattr(vision,'types')` False, `hasattr(vision,'Image')` True) and upstream issue evidence; the competing backwards-pin remedy executed and rejected on three separately observed failure modes. |
| **[AAP §0.5.2.1] The two-line OCR edit** | 1.5 | Line 2 deleted, line 15 substituted, two mandated explanatory comment lines added, and byte-level non-regression enforced — the unused `settings` assignment and the absent trailing newline both deliberately preserved, holding the file at its pre-fix flake8 count of 8. |
| **[AAP §0.7.1.1-3] Gates 1-3 harness** | 2.0 | Import resolution across five modules, error-signature eradication grepped across all eight, and contract conformance asserted by runtime introspection rather than source reading. |
| **[AAP §0.7.1.4] Gate 4 — functional suite** | 8.0 | 116 assertions against a mocked storage client: the canonical-URL round trip, all identifier forms, and the boundary cases — zero-byte accepted, `None` rejected, missing content type defaulted, traversal sanitised, collisions structurally impossible, non-ASCII lossless, absent-object semantics. |
| **[AAP §0.7.2] Gate 6, lazy client, byte-compile and parity measurement** | 3.0 | Configuration compatibility with `config.py` unedited; lazy-client assertion; `compileall` exit 0; lint parity measured in **both** directions against the 160 baseline; test-collection parity proven against a tree extracted from the pre-fix commit. |
| **[AAP §0.7] Runtime re-proof suite** | 4.0 | 22 checks exercising real uvicorn serving the unmodified attachments router, genuine `vision_v1` image construction on the OCR path, and the e-mail poller's synchronous call site. |
| **[AAP §0.7] Browser runtime validation** | 5.0 | Real Chrome multipart upload with byte-exact sha256 round trip, Swagger UI cross-verified against `/openapi.json`, and full console/network capture. 87 screenshots and 21 recordings retained under `blitzy/`. |
| **[AAP §0.7] Container validation** | 3.0 | `docker build --no-cache` exit 0 with the gates re-run inside the `python:3.9-slim` image; independently reproduced during this assessment, including the documented flattening defect. |
| **[AAP §0.8] Review-driven rework across 29 commits** | 14.0 | QA, security and code-review closure cycles: comment-defect corrections, AAP-freeze restorations after over-reach, boundary hardening, telemetry redaction, concurrency-safe caches, bcrypt provider bounding, and the final citation correction. |
| **[AAP §0.8.3] Zero-net-regression enforcement** | 3.0 | Lint baseline captured before design work and held at exactly 160 afterwards; pre/post tree extraction and byte-level confinement of the diff to the authorised paths. |
| **TOTAL** | **100.5** | Matches Completed Hours in §1.2 |

### 2.2 Remaining Work Detail

Totals to **65.0 h**, matching Remaining Hours in §1.2 and the "Remaining Work" value in §7.

| Category | Hours | Priority |
|---|---|---|
| **R1 — GCP environment, credentials and live-bucket verification** *(project/ADC/Secret Manager wiring for the 7 no-default settings; first run of all six public functions against a real bucket)* | 7.0 | High |
| **R2 — Container image import resolution and deviation ratification** *(fix `Dockerfile.backend` package flattening; ratify or revert the retained CVE-floor change)* | 4.0 | High |
| **R3 — Application boot unblock** *(`ApplicationCreate`, `init_db`, `HTTPException` import, `CORS_ORIGINS` declaration; verify router registration)* | 6.0 | High |
| **R4 — Attachment persistence contract and upload-route hardening** *(ORM/schema alignment; authentication; application-existence check; orphan-object cleanup)* | 6.0 | High |
| **R5 — Worker tier boot unblock and Celery task defects** *(`Webhook` model, `WEBHOOK_TIMEOUT`, three `celery_tasks.py` call defects; verify dispatch)* | 5.0 | High |
| **R6 — V4 signed-URL infrastructure prerequisites** *(Service Account Credentials API, `roles/iam.serviceAccountTokenCreator`, dangling Terraform output)* | 3.0 | Medium |
| **R7 — Browser-readable document delivery** *(authenticated proxy route or read-time signing for the private buckets; verify the `documentUrl` contract)* | 5.0 | Medium |
| **R8 — Committed regression suite and coverage instrumentation** *(repair 3 collection blockers, port the 116-assertion harness in-tree, add conftest fixtures and coverage)* | 12.0 | Medium |
| **R9 — CI/CD green run and staging deploy** *(`ci.yml` test and lint steps, node version and lock file, `npm test` target; exercise `cd.yml`)* | 6.0 | Medium |
| **R10 — Observability and operational readiness** *(health/readiness endpoint, upload/download metrics and alerts, bucket lifecycle policy, runbook, rollback)* | 6.0 | Medium |
| **R11 — Production readiness review and sign-off** *(least-privilege IAM review, latency/throughput baseline, handover documentation)* | 5.0 | Low |
| **TOTAL** | **65.0** | — |

**Priority distribution:** High 28.0 h · Medium 32.0 h · Low 5.0 h = 65.0 h.

#### 2.2.1 Task-level breakdown (rolls up exactly to the 11 categories above)

| # | Task | Cat. | Hours | Priority | Confidence |
|---|---|---|---|---|---|
| H1 | Provision/confirm the GCP project, both buckets and Cloud Run ADC; wire the 7 no-default settings into env vars / Secret Manager | R1 | 3.0 | High | Medium |
| H2 | First live-bucket verification of all six public functions against real ADC | R1 | 4.0 | High | Medium |
| H3 | Fix `Dockerfile.backend` package flattening (`:24` COPY, `:30` CMD); rebuild and re-run gates in-image | R2 | 3.0 | High | High |
| H4 | Ratify or revert the retained `pip`/`wheel` CVE-floor deviation and record the decision | R2 | 1.0 | High | High |
| H5 | Define `ApplicationCreate` in `application_schema.py` | R3 | 2.0 | High | High |
| H6 | Add `init_db` to `database.py`; import `HTTPException`; declare `CORS_ORIGINS` on `Settings` | R3 | 2.5 | High | High |
| H7 | Verify boot, all four router registrations, and route reachability | R3 | 1.5 | High | High |
| H8 | Align the `Attachment` persistence contract (ORM model, correct fields, stop `db.add()` of a pydantic instance) | R4 | 3.5 | High | High |
| H9 | Add authentication, the application-existence check, and orphan cleanup via `delete_file` | R4 | 2.5 | High | High |
| H10 | Add the `Webhook` model to `models.py`; declare `WEBHOOK_TIMEOUT` | R5 | 2.0 | High | Medium |
| H11 | Fix the three `celery_tasks.py` defects; verify worker boot and OCR dispatch | R5 | 3.0 | High | Medium |
| M1 | Enable the Service Account Credentials API, grant `roles/iam.serviceAccountTokenCreator`, clear the dangling `outputs.tf` reference | R6 | 2.0 | Medium | High |
| M2 | Verify `generate_download_url` yields a working V4 signature on Cloud Run | R6 | 1.0 | Medium | High |
| M3 | Implement browser-readable delivery — authenticated proxy route or read-time signing | R7 | 4.0 | Medium | Medium |
| M4 | Verify the `DocumentViewer` `documentUrl` contract end to end | R7 | 1.0 | Medium | Medium |
| M5 | Repair the three collection blockers and the assertion-free stub at `test_api.py:48` | R8 | 4.0 | Medium | Low |
| M6 | Commit the storage/OCR regression suite in-tree (port the 116-assertion harness) | R8 | 6.0 | Medium | Low |
| M7 | Add `conftest.py` environment fixtures and coverage instrumentation | R8 | 2.0 | Medium | Low |
| M8 | Get `ci.yml` green — pytest, node version, lock file, `npm test`, lint | R9 | 4.0 | Medium | Medium |
| M9 | Exercise `cd.yml` through a staging deploy and smoke the upload path | R9 | 2.0 | Medium | Medium |
| M10 | Add a health/readiness endpoint and wire Cloud Run probes | R10 | 2.0 | Medium | Medium |
| M11 | Add upload/download success-rate metrics, log-based alerts and a dashboard | R10 | 2.5 | Medium | Medium |
| M12 | Add bucket lifecycle/retention/versioning policy; write the runbook and rollback procedure | R10 | 1.5 | Medium | Medium |
| L1 | Least-privilege IAM review (narrow `roles/editor` plus three admin roles) | R11 | 2.0 | Low | Low |
| L2 | Establish an upload/OCR latency and throughput baseline | R11 | 1.5 | Low | Low |
| L3 | Handover documentation and production readiness sign-off | R11 | 1.5 | Low | Low |
| | **TOTAL (26 tasks)** | | **65.0** | | |

> **Note on exclusions (PA1 discipline).** Four bodies of work are deliberately carried at **0 h** because they lie outside the AAP scope *and* are not required to deploy the AAP deliverables; they appear in §6 as risks instead. (i) **Frontend build repair** — 50 pre-existing TypeScript errors, 36 imports through an unconfigured `@/` alias, five components absent from the repository, no `vite.config.*`; zero frontend files differ from baseline `543db77d`. (ii) **Backend lint-debt burn-down** — the AAP mandates *parity* at 160 and defines a count **below** 160 as a failure, so reducing it is prohibited, not pending. (iii) **`README.md` stale scaffold** (Node/Express/MongoDB/AWS S3/Redis-Bull) — the AAP instructs that it be ignored, not corrected. (iv) **OCR feature enhancements** suggested by the standing comment block at `ocr_service.py:29-35`.

---

## 3. Test Results

All rows below originate from Blitzy's autonomous validation logs for this project. Where a row is marked *(re-verified)*, this assessment independently re-executed it and reproduced the stated result.

| Test Category | Framework | Total Tests | Passed | Failed | Coverage % | Notes |
|---|---|---|---|---|---|---|
| Unit / functional — storage service (AAP Gate 4) | Python `unittest.mock` harness, out-of-tree | 116 | 116 | 0 | Not instrumented | Mocked Cloud Storage client. Round trip, all identifier forms, and 19 boundary cases. *(re-verified by an independent 27-check harness: 27/27)* |
| Import resolution (AAP Gate 1) | `python -c "import <module>"` | 5 | 5 | 0 | n/a | `storage_service`, `attachments`, `email_processor`, `ocr_service`, `data_extraction` — all exit 0. *(re-verified)* |
| Error-signature eradication (AAP Gate 2) | `grep -c` across all 8 backend modules | 1 | 1 | 0 | n/a | Count of `storage_service` + `cannot import name 'types'` = **0**. *(re-verified)* |
| Contract conformance (AAP Gate 3) | `inspect` runtime introspection | 6 | 6 | 0 | n/a | All six signatures string-exact; `upload_file` a coroutine, the other five synchronous. *(re-verified)* |
| Manifest resolvability (AAP Gate 5) | `pip install` + `pip check` on virgin py3.9.25 | 4 | 4 | 0 | n/a | Install exit 0, `pip check` clean, 18/18 pins verified, Gate 1 green with the manifest as the only thing installed. *(re-verified on a freshly created venv)* |
| Configuration compatibility (AAP Gate 6) | `python -c` against `get_settings()` | 1 | 1 | 0 | n/a | Prints `mca-dev-mca-documents mca-dev` with `config.py` unedited. *(re-verified)* |
| Runtime re-proof | Custom harness on real uvicorn | 22 | 22 | 0 | n/a | Real router, real OCR image construction, real e-mail poller call site. *(re-verified via a 15-assertion `/selfcheck`: 15/15)* |
| Browser / UI — backend harness | Chrome DevTools (headless Chrome 151) | 8 | 8 | 0 | n/a | Health, routes, self-check, Swagger + OpenAPI, round trip, in-page self-check, real multipart upload, storage-state assertion. Verdict **PASS**. |
| Browser / UI — frontend | Chrome DevTools (headless Chrome 151) | 6 | 0 | 6 | n/a | `/` 404; `/index.html` 200 with **0** `<script>` elements; `#root` childless; 100.0000 % white; no backend request. Verdict **FAIL — pre-existing, zero frontend files changed**. |
| Static analysis — byte-compile | `compileall` | 1 | 1 | 0 | n/a | `app` + `tests` exit 0. *(re-verified)* |
| Static analysis — lint parity | flake8 7.3.0 | 3 | 3 | 0 | n/a | Repository-wide **exactly 160** (unchanged baseline); `storage_service.py` **0**; `ocr_service.py` **8** (pre-fix parity). *(re-verified)* |
| Container validation | Docker 29.7.0 + `python:3.9-slim` | 6 | 6 | 0 | n/a | `docker build --no-cache` exit 0; in-image pip 26.0.1 / wheel 0.47.0; deliverable present at 667 lines; Gates 1/3/6/lazy green in-image. *(re-verified)* |
| Regression — committed suite (parity gate) | pytest 7.4.4 `--collect-only` | 0 collected | n/a | 3 collection errors | 0 % | **This is the AAP's explicit pass condition** (§0.7.2.1): exactly three errors, identical before and after the change. Fewer would prove an out-of-scope file was edited; more would prove the fix broke collection. All three trace to named out-of-scope defects; none involves storage. *(re-verified)* |
| **Totals (in-scope suites)** | — | **173** | **173** | **0** | Not instrumented | The frontend row and the committed-suite parity row are reported separately above because neither is an in-scope pass/fail suite. |

**Coverage note.** No coverage percentage can be honestly reported. The AAP (§0.6.2.3) prohibited committing test files, so all 173 in-scope assertions ran from out-of-tree harnesses with no coverage instrumentation, and the committed suite collects zero tests. Establishing a real coverage figure is remaining task M7.

---

## 4. Runtime Validation & UI Verification

### 4.1 Backend runtime health

- ✅ **Operational** — Import resolution: all five in-scope modules import cleanly on both the project venv and a virgin Python 3.9.25 interpreter carrying only the new manifest.
- ✅ **Operational** — Byte-compilation: `python -m compileall -q app tests` exits 0.
- ✅ **Operational** — Lazy credential acquisition: `_client is None` immediately after import, and **still `None` after 8 object writes plus multiple reads and deletes under live HTTP traffic**. No credential lookup, metadata-server call or network I/O occurs at import.
- ✅ **Operational** — Storage round trip on real uvicorn: `sha256_uploaded == sha256_downloaded == c048f40dba4e201997ce1037d2bee851714e7139e779adb34ce4ea50687a77c6`, with the canonical URL `https://storage.googleapis.com/mca-dev-mca-documents/attachments/2026/08/04/…-probe%20document.pdf` resolving back to the exact object and percent-decoding `%20` to a space.
- ✅ **Operational** — OCR path: `process_document` returns `str` and constructs a genuine `google.cloud.vision_v1.types.image_annotator.Image` carrying the correct content bytes. `hasattr(vision, 'types')` is `False`; `hasattr(vision, 'Image')` is `True`.
- ✅ **Operational** — E-mail poller path: `email_processor.upload_attachment` **is** `storage_service.upload_attachment` and is synchronous, satisfying the un-awaited call at `email_processor.py:46`.
- ✅ **Operational** — Container: `docker build --no-cache` exit 0; the 667-line module ships at `/app/services/storage_service.py`; Gates 1/3/6 and the lazy check all pass inside the image.
- ⚠ **Partial** — Container import path: with the image's own default layout, `import app.services.storage_service` fails with `ModuleNotFoundError: No module named 'app'` because `Dockerfile.backend` flattens the package. Reproduced deliberately; AAP §0.6.2.4 records it as an out-of-scope follow-up (R2).
- ❌ **Failing** — Full application boot: `uvicorn app.main:app` exits at `applications.py:5` (`ImportError: cannot import name 'ApplicationCreate'`). AAP §0.3.3.1 states outright that application boot cannot be this fix's success criterion (R3).
- ❌ **Failing** — Celery worker boot: exits at `webhook_service.py:2` (`ImportError: cannot import name 'Webhook'`). Critically, the worker now advances **past** `celery_tasks.py:3-5` — all three of those imports are newly satisfiable — and neither traceback mentions `storage_service` or `cannot import name 'types'` (grep count 0), so the barrier provably moved (R5).

### 4.2 API integration verification

- ✅ **Operational** — Router mounting: the real, unmodified `app.api.attachments` router registers `POST /applications/{application_id}/attachments/` and `GET /attachments/{attachment_id}`; 12 routes enumerated in total.
- ✅ **Operational** — OpenAPI contract: `requestBody.required = true`; content types `["multipart/form-data"]` as the only option; body schema `{"file": {"type": "string", "format": "binary"}}` with `required: ["file"]`; the 200 response `$ref` resolves to `#/components/schemas/Attachment`.
- ✅ **Operational** — Real multipart upload through the real route: a genuine 611-byte PDF was posted from Chrome (`content-length: 820`, boundary `----WebKitFormBoundary…`, part header `name="file"; filename="mca_harness_upload_fixture.pdf"`, `Content-Type: application/pdf`). **The storage write succeeded**: object count rose, the object landed at `attachments/2026/08/04/350996da6fca4d5c882774d2bf28512e-mca_harness_upload_fixture.pdf`, and the event record shows `{"op":"upload","bytes":611,"content_type":"application/pdf"}`. Corroborated three independent ways — browser-rendered state, out-of-browser `curl`, and the server log line `Uploaded 611 bytes to object …` appearing **before** the traceback.
- ❌ **Failing** — Route response serialisation: the same request returns **HTTP 500** with `pydantic.error_wrappers.ValidationError: 3 validation errors for Attachment / type / storage_url / upload_date field required` raised at `attachments.py:20`, so `db.commit()` is never reached. This is precisely the persistence mismatch AAP §0.6.2.2 catalogues and **forbids repairing**. The storage boundary is proven working; the defect is strictly downstream (R4).
- ⚠ **Partial** — `generate_download_url`: returns a well-formed HTTPS signed URL against a mocked client, but will raise on Cloud Run until the Service Account Credentials API is enabled and `roles/iam.serviceAccountTokenCreator` granted — confirmed absent from every file under `infrastructure/`. This is exactly why the upload path returns a canonical URL, which operates entirely within the already-granted `roles/storage.admin` (R6).

### 4.3 UI verification

- ❌ **Failing** — Root route `/` returns **HTTP 404** with `Content-Length: 0`; the browser substitutes its own interstitial. No application content of any kind renders.
- ❌ **Failing** — `/index.html` returns **HTTP 200** (842 bytes) but is served by Vite's *static-asset* middleware out of `public/` rather than transformed as the entry document — proven by the `etag` and `last-modified` headers, by the served bytes being byte-identical to the on-disk file, by the `%PUBLIC_URL%` placeholders surviving unsubstituted, and by the complete absence of a Vite HMR log.
- ❌ **Failing** — The served document contains **zero `<script>` elements** (confirmed by two DOM APIs and a byte-level grep). `#root` exists but has 0 children and carries no `__reactContainer$` / `__reactFiber$` internal key, which is positive proof `ReactDOM.createRoot()` was never invoked. `document.body.innerText` is empty; the accessibility tree contains a single childless node; the capture is **exactly one colour (`#FFFFFF`) across all 1,152,000 pixels**. The blankness is terminal, not transitional — four seconds of idle produced no change, no spinner and no error overlay.
- ❌ **Failing** — `npx tsc --noEmit` reports **exactly 50 errors** (TS2307 ×39, TS7006 ×5, TS2614 ×2, TS2305 ×2, TS2459 ×1, TS2339 ×1). Of the 39 unresolved-module errors, **36** reference an `@/` path alias configured nowhere and 3 reference bare `app/…` specifiers. Five components are imported but absent from the repository entirely: `Layout`, `ApplicationListItem`, `KPIChart`, `RecentActivities`, `SystemLogs`.
- ✅ **Verified untouched** — **Not one frontend file differs from the pre-agent baseline**: `git diff 543db77d --name-only -- frontend/` returns zero paths at HEAD `f12eeed76`. Further, **no network request in the entire browser session reached a backend origin** — established four independent ways, including a Performance-API origin audit returning a single origin and zero matches for `:8000`, `:8099` or `/api/`. Nothing observed in the frontend is attributable to this change, and the AAP requires the frontend to remain unchanged (§0.7.2.3).

### 4.4 Console and network observations

- ✅ **Operational** — Backend harness session: **no console error originated from application code**. The messages observed were a browser-initiated `/favicon.ico` 404, a DevTools markup *issue* raised against the third-party Swagger UI bundle, two resource-status errors reporting the documented route 500, and one uncaught rejection traced to the out-of-tree validation harness's own `fetch` helper (it double-reads the response body). Server-side, exactly two `ERROR` lines appear across 15 KB of log, both the documented `ValidationError`; the four `WARNING: Object … already absent, not deleted` lines are produced deliberately by the idempotent-delete assertion.
- ⚠ **Partial** — Backend network: the only responses ≥ 400 across a 23-request server log were one `/favicon.ico` 404 and the two documented attachment-POST 500s. Everything else returned 200.
- ❌ **Failing** — Frontend network: 4 real requests, all to the frontend origin. Two subresource requests return **500** — `/%PUBLIC_URL%/manifest.json` and `/%PUBLIC_URL%/favicon.ico` — because the unsubstituted `%` characters make Vite's `decodeURI()` throw `URI malformed`. All four console entries are network-layer failures; **no JavaScript exception of any kind was raised**, because not one line of application JavaScript executed. The 50 TypeScript defects are therefore *masked* by the more fundamental failure that the document loads no script at all.

---

## 5. Compliance & Quality Review

### 5.1 AAP deliverable compliance matrix

| AAP requirement | Benchmark | Status | Evidence |
|---|---|---|---|
| §0.6.1 File 1 — CREATE `backend/app/services/storage_service.py` | Module exists at the exact import path with the three required symbols | ✅ **PASS** | 667 lines committed; `git diff 543db77d` shows `A backend/app/services/storage_service.py` (+667/−0) |
| §0.5.1.1 Public surface exactly matches the call sites | 6 functions, signatures string-exact | ✅ **PASS** | Gate 3: `upload_file` coroutine `(UploadFile) -> str`; `upload_attachment (str, bytes, Optional[str]=None) -> str`; `get_file_content (str) -> bytes`; `delete_file (str) -> None`; `file_exists (str) -> bool`; `generate_download_url (str, int=15) -> str` |
| §0.5.1.1 Lazy client — no credentials at import | `_client is None` post-import | ✅ **PASS** | `lazy OK`; still `None` after 8 live writes |
| §0.5.1.2 Canonical URL, not signed, on the write path | Returns `blob.public_url` | ✅ **PASS** | Round-trip probe returned an `https://storage.googleapis.com/...` URL that resolved back to the same object |
| §0.3.1.5 Round-trip contract holds | Upload's return value is resolvable by the download | ✅ **PASS** | sha256 identical both ways; all identifier forms reduce to one object name |
| §0.6.1 File 2 — CREATE `backend/requirements.txt` | Manifest resolves on the documented runtime | ✅ **PASS** | 127 lines / 18 pins; Gate 5 exit 0 on virgin py3.9.25 + `pip check` clean |
| §0.5.1.4 pydantic held below 2.0 so `config.py` is unedited | `from pydantic import BaseSettings` still resolves | ✅ **PASS** | Gate 6 prints the configured bucket and project; `config.py` byte-identical to baseline |
| §0.5.1.4 SQLAlchemy pinned at 2.x | Root-namespace `UUID` import works | ✅ **PASS** | `SQLAlchemy==2.0.23` installed and verified |
| §0.5.1.4 `python-multipart` declared | Upload route can receive form data | ✅ **PASS** | `python-multipart==0.0.20`; real multipart upload accepted by the real route |
| §0.5.2.3 No `multipart`, no `setuptools`, no `protobuf` pin | Prohibited entries absent | ✅ **PASS** | Manifest inspected: none present; `protobuf 6.33.6` is a resolver result, not a pin |
| §0.6.1 File 3 — MODIFY `ocr_service.py`, exactly 2 line changes | 1 deletion + 1 substitution | ✅ **PASS** | `git diff` shows `+3/−2`: line 2 deleted, line 15 substituted, 2 mandated comment lines added |
| §0.5.1.3 `process_document` signature unchanged | `(file_path: str) -> str` | ✅ **PASS** | Confirmed at `ocr_service.py:5`; OCR path returns `str` at runtime |
| §0.6.2.2 Unused `settings` at `ocr_service.py:10` NOT removed | Pre-existing lint finding preserved | ✅ **PASS** | Assignment present; flake8 for the file holds at 8 |
| §0.6.1.1 `attachments.py`, `email_processor.py`, `config.py` unedited | Byte-identical to baseline | ✅ **PASS** | Absent from `git diff 543db77d --name-status` |
| §0.6.2.1 Do-not-modify list respected | No prohibited file changed | ⚠ **PARTIAL** | 14 of 15 respected. **`infrastructure/docker/Dockerfile.backend` was modified** by a prior agent (+12/−2) to add CVE floors. Retained and validated rather than reverted; decision escalated (H4) |
| §0.6.2.2 Do-not-refactor list respected | No unrequested cleanup | ✅ **PASS** | Lint count exactly 160 — a value *below* the baseline would itself prove a violation |
| §0.6.2.3 Do-not-add list respected | No tests, `.env`, config fields, routes, lint config, `__init__.py`, S3 code | ✅ **PASS** | Working tree contains none of these; verified by inspection and by the 4-path diff |
| §0.2.1.1 No `__init__.py` added anywhere | PEP 420 namespace packages left intact | ✅ **PASS** | None present under `backend/` |

### 5.2 Code quality benchmarks

| Benchmark | Target | Result | Status |
|---|---|---|---|
| Zero placeholders in delivered files | No TODO / FIXME / XXX / HACK / `NotImplementedError` / stub / dummy / TBD | None present in any of the three files | ✅ **PASS** |
| No bare exception handling | Every handler names a specific type | 8 handlers, all specific: `UnicodeDecodeError`, `GoogleAPIError` ×4, `RequestRangeNotSatisfiable`, `NotFound`. Zero bare `except`, zero `except Exception` | ✅ **PASS** |
| Logging convention | Module-level `logging.getLogger(__name__)`, never `print()` | Conformant; zero `print()` calls | ✅ **PASS** |
| Type annotations | Every parameter and return annotated | Complete across all 18 functions | ✅ **PASS** |
| Documentation convention | `#` comments, zero docstrings (matching all 8 existing service/API modules) | Zero `"""` occurrences | ✅ **PASS** |
| Timestamp convention | `datetime.utcnow()` only | Conformant; `datetime.now(` never appears | ✅ **PASS** |
| Lint cleanliness of new code | 0 findings | **0** on 667 lines | ✅ **PASS** |
| Lint parity (regression gate, both directions) | Exactly 160 repository-wide | **160** | ✅ **PASS** |
| Byte-compilation | exit 0 | exit 0 | ✅ **PASS** |
| Test-collection parity | Exactly 3 errors | **3** | ✅ **PASS** |
| Commit authorship | `Blitzy Agent <agent@blitzy.com>` | 29/29 commits, author **and** committer | ✅ **PASS** |
| Working tree hygiene | No build artifacts, venvs, credentials or ad-hoc test files committed | `git diff HEAD` empty; only 4 permitted untracked paths | ✅ **PASS** |

### 5.3 Fixes applied during autonomous validation

| Fix | Type | Detail |
|---|---|---|
| Upload size ceiling on both entry points | Security hardening | `MAX_UPLOAD_BYTES` (20 MB) enforced before the key build and the settings read, so an over-sized payload costs one comparison and no I/O |
| Object-name and identifier bounds | Security hardening | `MAX_OBJECT_NAME_BYTES` (1024) with byte-budget truncation; `MAX_IDENTIFIER_CHARS` (4096) checked before parsing |
| Namespace gate on every read path | Security hardening | Reads, deletes, probes and signatures all pass `_validated_object_name`: `attachments/` prefix required, NFC normalisation enforced, control code points and empty/`.`/`..` segments refused |
| Foreign-bucket and foreign-scheme refusal | Security hardening | A URI naming another bucket is *refused*, not silently retargeted into the only bucket this service can reach; the full authority is compared so credential-prefixed and look-alike hosts fail |
| Telemetry redaction | Security hardening | `_object_id` and `_provider_fault` keep caller-supplied identifiers — potentially carrying signature query material — out of log records |
| Concurrency-safe client cache | Correctness | Cached handles made safe for concurrent first use |
| Dependency security floors raised | Security | FastAPI to 0.125.0 (closing a Content-Type ReDoS and, via starlette 0.49.3, three further DoS vectors incl. two unauthenticated multipart vectors on the upload route); `python-multipart` to 0.0.20; `python-jose` to 3.5.0; `requests` to 2.32.5; Vision/Logging raised so the resolver can take protobuf 6.33.6 |
| bcrypt provider bounded to 4.0.1 | Correctness | Discovered empirically: passlib's over-length probe fails on bcrypt 5, and bcrypt 4.1.0+ removed the `__about__` attribute passlib reads — so an unbounded extra installs cleanly and then fails on first hash |
| Base-image packaging floors | Security | `pip==26.0.1` and `wheel==0.47.0` in the Dockerfile, closing CVE-2026-24049 in `wheel` 0.45.1 (its unpack chmods the archive-recorded path). *This is the retained scope deviation.* |
| 34 `file:line` citations audited | Documentation accuracy | All references across the three in-scope files verified against original source; the final two stale `Dockerfile.backend` line numbers corrected in commit `f12eeed76` |
| 15 comment defects corrected | Documentation accuracy | Across three review rounds, ensuring the mandated motive-bearing comments state the actual diagnosis |
| AAP-freeze restorations | Scope discipline | Five commits restored the manifest or the module after reviews found over-reach beyond the frozen shape |

### 5.4 Outstanding compliance items

| Item | Nature | Disposition |
|---|---|---|
| `Dockerfile.backend` modified despite being on the do-not-modify list | Authorised-scope breach by a prior agent | **Escalated for human ratification (H4).** Retained because reverting reintroduces CVE-2026-24049 and orphans two manifest cross-references. Validated in place: build exit 0, floors confirmed in-image, all gates green in the container. |
| Delivered module is 667 lines against the AAP's 196-line reference | Justified superset | **Accepted.** Every AAP-required symbol, signature and behaviour is present, the additions are security bounds and a namespace gate, and the file scores 0 lint findings. |
| Manifest carries 18 pins with versions above the AAP's proposed set | Justified drift | **Accepted.** Both hard compatibility constraints (pydantic < 2.0, SQLAlchemy 2.x) are preserved; every upward move closes a specific advisory; each residual is ledgered in-file with its unreachability argument. |
| Eight dependency advisories remain unfixed | Runtime-envelope limitation | **Accepted and documented.** Every one requires a release that needs Python 3.10+, which `ci.yml:19` and `Dockerfile.backend:2` fix at 3.9. Each was checked against this tree and the affected code path shown to be unused. |
| No committed tests | AAP prohibition | **By design** (§0.6.2.3). Converting to committed coverage is task M6. |
| No `.env` / `.env.example` | AAP prohibition | **By design.** The working environment is supplied from `/opt/mca-setup/env.sh`, outside the checkout. Task H1 replaces it with Secret Manager wiring. |

---

## 6. Risk Assessment

25 risks across the four PA3 categories. **Not one originates in the three AAP-delivered files** — every HIGH-severity entry is a pre-existing defect in a file the AAP explicitly placed out of scope.

| Risk | Category | Severity | Probability | Mitigation | Status |
|---|---|---|---|---|---|
| Upload route 500s after a successful storage write (`attachments.py:20` ValidationError) | Technical | High | Certain | Align the ORM/schema contract; construct the ORM model, not the pydantic schema (H8) | Open — AAP-forbidden to repair |
| FastAPI app cannot boot (4 defects across `applications.py` and `main.py`) | Technical | High | Certain | Define `ApplicationCreate`, add `init_db`, import `HTTPException`, declare `CORS_ORIGINS` (H5–H7) | Open — AAP §0.3.3.1 excludes boot as a criterion |
| Celery worker cannot boot (`Webhook` model absent) | Technical | High | Certain | Add the model and fix three `celery_tasks.py` call defects (H10–H11) | Open — barrier provably moved past storage |
| Container flattening makes the shipped module unimportable | Technical | High | Certain | Fix `COPY`/`CMD` layout; re-run gates in-image (H3) | Open — AAP §0.6.2.4 follow-up |
| No committed regression coverage; verification is out-of-tree only | Technical | Medium | Certain | Repair collection blockers and commit the suite (M5–M7) | Open — AAP prohibited committing tests |
| Python 3.9 runtime past end of life | Technical | Medium | High | Runtime upgrade; the manifest cannot fix this and says so | Accepted and documented |
| No performance baseline anywhere in the repository | Technical | Low | Medium | Establish a latency/throughput baseline (L2) | Open |
| Upload endpoint has no authentication and no application-existence check | Security | High | High | Add auth plus the check left as a TODO at `attachments.py:13-14` (H9). Partially mitigated today by the 20 MB ceiling and the `attachments/` namespace gate | Open — AAP forbade route changes |
| Eight dependency advisories unfixable inside the Python 3.9 envelope | Security | Medium | Low | Runtime upgrade. Each was checked against this tree and its code path shown unused (`FileResponse`, `StaticFiles`, `TrustedHost`, `extract_zipped_paths`, `set_key`/`unset_key`, `click.edit` all unused; the `cryptography` extra keeps `ecdsa` idle) | Accepted, ledgered in-manifest |
| Service account holds `roles/editor` plus three admin roles | Security | Medium | Medium | Least-privilege review (L1). The design deliberately requires no privilege beyond the already-granted `roles/storage.admin` | Open — `infrastructure/` out of scope |
| Secrets supplied by shell environment; no Secret Manager wiring, no committed template | Security | Medium | High | Wire Secret Manager / Cloud Run env (H1) | Open — AAP forbade `.env` files |
| CVE-2026-24049 in the base image's `wheel` 0.45.1 | Security | Medium | Low | Closed by the retained `pip`/`wheel` floors, verified in-image. Residual: `pip` 26.0.1 still carries reports whose remedy needs Python 3.10+ | Mitigated; ratification pending (H4) |
| Permanent canonical URLs persisted in a non-nullable column | Security | Low | Low | By design (AAP §0.5.1.2): the buckets are private so the URL is not itself an access grant, and identifiers are redacted from logs | Accepted by design |
| No health-check endpoint (`main.py:41` open comment) | Operational | Medium | Certain | Add health/readiness and wire Cloud Run probes (M10) | Open |
| No metrics or alerting on upload/download outcomes | Operational | Medium | Certain | Add success-rate metrics, log-based alerts and a dashboard (M11) | Open |
| No bucket lifecycle, retention or versioning, against a deliberately idempotent delete | Operational | Medium | High | Add lifecycle policy in Terraform (M12) | Open |
| CI has never completed a green run | Operational | Medium | Certain | The manifest lets the install step pass for the first time; the test, node and lint steps still need work (M8–M9) | Open |
| No runbook or rollback procedure for the storage path | Operational | Low | Certain | Write both (M12, L3) | Open |
| Fragile configuration — 7 no-default fields plus 6 read-but-undeclared attributes that pydantic v1 silently ignores | Operational | Medium | High | Declare the missing settings and wire the rest (H1, H6, H10) | Open |
| Module never run against a live bucket with real ADC | Integration | Medium | Medium | Live verification (H2). This is the AAP's own declared 3 % residual; every API used was confirmed present by runtime introspection | Open — no GCP project in the environment |
| `generate_download_url` raises on Cloud Run until IAM prerequisites land | Integration | Medium | Certain | Enable the Service Account Credentials API and grant `roles/iam.serviceAccountTokenCreator` (M1–M2) | Open by design; documented in-code |
| Cloud Vision never exercised against the live API | Integration | Medium | Medium | Live verification (H2). Image construction was verified for real | Open |
| Cloud SQL / PostgreSQL never connected | Integration | Medium | High | Provision and verify (H1, H8) | Open |
| Celery broker / Redis never dispatched a task | Integration | Medium | High | Unblock the worker and verify dispatch (H11) | Open |
| Frontend cannot consume `storage_url` — private buckets *and* the frontend does not build or render | Integration | Medium | Certain | Backend seam via proxy or signing (M3–M4). The frontend build itself is outside the AAP-scoped hours: **zero frontend files differ from baseline** and no browser request reached a backend origin | Open, pre-existing, provably untouched |

**Profile:** 5 High · 16 Medium · 4 Low. Categories: 7 technical, 6 security, 6 operational, 6 integration.

---

## 7. Visual Project Status

### 7.1 Project hours

```mermaid
%%{init: {'theme':'base','themeVariables':{'pie1':'#5B39F3','pie2':'#FFFFFF','pieStrokeColor':'#B23AF2','pieStrokeWidth':'2px','pieOuterStrokeColor':'#B23AF2','pieTitleTextSize':'15px','pieSectionTextSize':'13px','pieLegendTextSize':'12px'}}}%%
pie showData title Project Hours Breakdown — 60.7% Complete
    "Completed Work" : 100.5
    "Remaining Work" : 65.0
```

> Completed Work = Dark Blue `#5B39F3` · Remaining Work = White `#FFFFFF` · outline Violet-Black `#B23AF2`

### 7.2 Remaining hours by priority

```mermaid
%%{init: {'theme':'base','themeVariables':{'pie1':'#5B39F3','pie2':'#A8FDD9','pie3':'#FFFFFF','pieStrokeColor':'#B23AF2','pieStrokeWidth':'2px','pieTitleTextSize':'15px','pieSectionTextSize':'13px','pieLegendTextSize':'12px'}}}%%
pie showData title Remaining 65.0h by Priority
    "High" : 28.0
    "Medium" : 32.0
    "Low" : 5.0
```

### 7.3 Remaining hours by category

```mermaid
%%{init: {'theme':'base','themeVariables':{'xyChart':{'plotColorPalette':'#5B39F3'},'fontSize':'12px'}}}%%
xychart-beta
    title "Remaining Hours per Category (total 65.0h)"
    x-axis ["R1 GCP/creds", "R2 Container", "R3 App boot", "R4 Persistence", "R5 Worker", "R6 Signing IAM", "R7 Doc delivery", "R8 Tests", "R9 CI/CD", "R10 Observability", "R11 Sign-off"]
    y-axis "Hours" 0 --> 14
    bar [7, 4, 6, 6, 5, 3, 5, 12, 6, 6, 5]
```

### 7.4 AAP scope versus path-to-production

| Work universe segment | Hours | Share of total | Status |
|---|---|---|---|
| AAP-specified deliverables and verification (§0.5–§0.8) | 100.5 | 60.7 % | ✅ 100 % complete and validated |
| Path-to-production activities required to deploy them | 65.0 | 39.3 % | ⬜ 0 % started |
| **Total project** | **165.5** | **100 %** | **60.7 % complete** |

---

## 8. Summary & Recommendations

### 8.1 What was achieved

The reported defect is closed, and so is a second defect the report never mentioned. `backend/app/services/storage_service.py` now exists as a 667-line Google Cloud Storage persistence module whose public surface was derived from its three existing call sites rather than invented — which is why `attachments.py`, `email_processor.py` and `config.py` needed no edits at all, a genuine scope reduction against the authorisation the report granted. The `ModuleNotFoundError` the user predicted verbatim is gone: a grep across all eight backend modules' import output returns zero. So is the `ImportError` on `google.cloud.vision.types` that was firing two lines earlier in `ocr_service.py` and masking the storage failure there — removed in exactly two line changes, with the file's pre-existing lint findings deliberately left intact. And `backend/requirements.txt` now exists, satisfying four automation paths that had been reading a file that was never there, so CI clears its install step for the first time in the repository's history.

The evidence behind those claims is measured rather than asserted. All six AAP verification gates pass, and this assessment re-executed every one of them independently: import resolution 5/5, signature eradication 0, six string-exact signatures, a 116-assertion functional suite re-proved by a separate 27-check harness, manifest install exit 0 with a clean `pip check` on a freshly created virgin Python 3.9.25 interpreter, and configuration compatibility with `config.py` untouched. Repository-wide lint sits at exactly 160 — the same number as before the change, in a codebase where a *lower* count would itself constitute a failure — while the new 667-line module scores zero. Test collection yields exactly three errors, which is the AAP's stated pass condition. Beyond the import gates, the storage boundary was proven at runtime: a real Chrome multipart upload through the real, unmodified router wrote a 611-byte object under `attachments/2026/08/04/` with a byte-exact sha256 round trip, corroborated by the browser, by `curl`, and by a server log line that appears *before* the downstream failure. The credential path stays lazy throughout — `_client` is still `None` after eight live writes.

### 8.2 What remains

**The project is 60.7 % complete.** That figure carries a specific and important shape: **100 % of the AAP-specified scope is delivered and validated (100.5 h of 100.5 h)**, and the entire 65.0 h remainder is path-to-production work — most of which the AAP itself enumerated as deferred follow-ups in §0.6.2.4 rather than leaving to be discovered.

The honest reading is that the fix is finished and the pipeline still cannot run end to end, for reasons that sit outside the three files this engagement was permitted to touch. Four blockers stand between a proven-good storage module and a working document path: the FastAPI application cannot boot, so the attachment router never registers; the Celery worker cannot boot, so the OCR tier is unreachable; the upload route returns 500 *after* a successful write because it constructs its response model with fields the schema does not declare; and the container image flattens the package so `import app.*` fails inside it even though the file is physically present. Each was reproduced during this assessment, each is located to an exact `file:line`, and each was explicitly forbidden to repair.

### 8.3 Critical path to production

1. **Unblock boot** (R3 + R5, 11.0 h) — nothing else can be exercised until the app and worker start.
2. **Repair the persistence contract and secure the route** (R4, 6.0 h) — converts a working storage write into a working endpoint and stops orphaning objects.
3. **Provision GCP and verify live** (R1, 7.0 h) — closes the AAP's own declared 3 % residual, the single thing that could not be exercised in this environment.
4. **Fix the container and settle the deviation** (R2, 4.0 h) — makes the deliverable reachable in the deployed image.
5. **Commit coverage, then green CI** (R8 + R9, 18.0 h) — moves verification from out-of-tree harnesses into the repository so it survives the next checkout.
6. **Signing, delivery, observability, sign-off** (R6 + R7 + R10 + R11, 19.0 h).

Steps 1–4 (28.0 h, all High priority) are the true blocking path; steps 5–6 (37.0 h) harden and operationalise.

### 8.4 Success metrics

| Metric | Target | Current | Status |
|---|---|---|---|
| AAP verification gates passing | 6 / 6 | **6 / 6** | ✅ |
| In-scope test assertions passing | 100 % | **173 / 173 (100 %)** | ✅ |
| `ModuleNotFoundError` occurrences on the storage path | 0 | **0** | ✅ |
| Lint findings in delivered code | 0 | **0** on 667 lines | ✅ |
| Repository-wide lint parity | exactly 160 | **160** | ✅ |
| Test-collection parity | exactly 3 errors | **3** | ✅ |
| Files changed versus authorised scope | 3 | **4** (one prior-agent deviation, retained and escalated) | ⚠ |
| Storage round-trip integrity | byte-exact | **sha256 identical** | ✅ |
| Container build | exit 0 | **exit 0** | ✅ |
| Attachment endpoint end-to-end | 200 with a persisted row | **500 after a successful write** | ❌ (R4) |
| Application boot | `uvicorn app.main:app` serves | **fails at `applications.py:5`** | ❌ (R3) |
| Live-bucket verification | passing | **not executed — no GCP project** | ❌ (R1) |
| Committed automated coverage | > 0 % | **0 %, suite collects nothing** | ❌ (R8) |

### 8.5 Production readiness assessment

**Verdict: the AAP change set is production-ready; the surrounding document pipeline is not.**

Take the three delivered files on their own terms and they are ready to ship. They compile, import, satisfy their contracts by runtime introspection, pass 173 assertions, run under real uvicorn, build into the deployment image, hold their lint and collection baselines exactly, and contain no placeholder of any kind. The module is materially more defensive than the plan required — bounded uploads, bounded identifiers, a namespace gate on every read, foreign-bucket refusal rather than silent retargeting, and redacted telemetry — and it acquires no credentials at import.

What is not ready is everything the module has to plug into. The application cannot start, the worker cannot start, the endpoint cannot return a response, the image cannot import its own package, and no GCP project has ever been reached. Those are not defects in this work — they are the pre-existing conditions the AAP catalogued with exact locations and deliberately left alone, and they are why the completion figure is 60.7 % rather than higher. **Recommendation: merge this change set, then execute remaining items R1–R5 (28.0 h) as a single follow-on before any deployment attempt.** The frontend, separately, does not build or render at all; that is provably untouched by this work — zero frontend files differ from the baseline — and is tracked outside the AAP-scoped hours.

---

## 9. Development Guide

Every command below was executed during this assessment with the stated result. All commands are copy-pasteable. `$REPO` denotes the repository root.

### 9.1 System prerequisites

| Requirement | Version | Why |
|---|---|---|
| Python | **3.9.x** (validated on 3.9.25) | `ci.yml:19` and `Dockerfile.backend:2` both fix 3.9. Newer interpreters will not resolve this manifest. |
| pip | ≥ 26.0.1 | Mirrors the floor `Dockerfile.backend` installs |
| wheel | ≥ 0.47.0 | Closes CVE-2026-24049 in the base image's 0.45.1 |
| Docker | 20.10+ (validated on 29.7.0) | Container build verification |
| Git | 2.30+ (validated on 2.51.0) | — |
| Node.js / npm | Only needed for frontend work (validated on v22.23.2 / 11.18.0) | Not required for any backend gate |
| OS | Linux x86-64 (validated on Ubuntu 25.10) | `psycopg2-binary` wheels |
| Disk / RAM | ~2 GB free · 4 GB RAM | Virtualenv plus Docker layers |

```bash
# Verify prerequisites — run from anywhere
python3.9 --version    # -> Python 3.9.25
docker --version       # -> Docker version 29.7.0, build c1eba93
git --version          # -> git version 2.51.0
```

### 9.2 Environment setup

The AAP prohibits committing `.env` or `.env.example`, so configuration is supplied by the shell. Seven `Settings` fields at `backend/app/core/config.py:5-11` have **no defaults** and the application raises without them.

```bash
# 1. Create the virtualenv on the documented runtime
cd "$REPO"
python3.9 -m venv .venv
source .venv/bin/activate

# 2. Seed the packaging floors the deployment image uses
python -m pip install --upgrade "pip==26.0.1" "wheel==0.47.0"

# 3. Point the interpreter at the backend package root (PEP 420 namespace packages —
#    there are deliberately no __init__.py files anywhere under backend/)
export PYTHONPATH="$REPO/backend"

# 4. Export the seven Settings fields that have no defaults
export PROJECT_NAME="mca"
export API_V1_STR="/api/v1"
export SECRET_KEY="dev"                                   # replace in any shared environment
export DATABASE_URL="postgresql://user:password@127.0.0.1:5432/myapp"
export GOOGLE_CLOUD_PROJECT="mca-dev"
export GOOGLE_CLOUD_STORAGE_BUCKET="mca-dev-mca-documents"
export EMAIL_SUBMISSION_ADDRESS="intake@example.com"
```

A ready-made script exists **outside** the checkout for exactly this reason:

```bash
source /opt/mca-setup/env.sh    # sets PATH, PYTHONPATH and all seven fields
```

> **Important.** Six further attributes are read by code but never declared on `Settings`: `CORS_ORIGINS` (`main.py:24`), `CELERY_BROKER_URL` (`celery_tasks.py:9`), `WEBHOOK_TIMEOUT` (`webhook_service.py:37`), `ALGORITHM`, `LOG_LEVEL`, `RUNNING_IN_GCP`. Because pydantic v1 `BaseSettings` silently ignores undeclared environment variables, **exporting them does not help** — those are source-code defects, tracked as H6 and H10.

### 9.3 Dependency installation

```bash
cd "$REPO/backend"
pip install -r requirements.txt        # -> exit 0
pip check                             # -> "No broken requirements found."
```

Expected: 18 pinned distributions plus their resolver results. Verify any pin with:

```bash
python -c "import importlib.metadata as m; print(m.version('google-cloud-storage'))"   # -> 2.14.0
python -c "import importlib.metadata as m; print(m.version('pydantic'))"               # -> 1.10.13
python -c "import importlib.metadata as m; print(m.version('starlette'))"              # -> 0.49.3 (resolver result)
```

### 9.4 Verification — the six AAP gates

Run all of these from `$REPO/backend` with the environment from §9.2 active.

```bash
# --- Byte-compilation ---
python -m compileall -q app tests                     # -> exit 0

# --- GATE 1: import resolution (expect 5 PASS, 0 FAIL) ---
for m in app.services.storage_service app.api.attachments \
         app.services.email_processor app.services.ocr_service \
         app.services.data_extraction; do
  python -c "import $m" >/dev/null 2>&1 && echo "PASS $m" || echo "FAIL $m"
done

# --- GATE 2: error-signature eradication (expect exactly 0) ---
for m in app.services.storage_service app.api.attachments app.services.email_processor \
         app.services.ocr_service app.services.data_extraction app.tasks.celery_tasks \
         app.api.applications app.main; do python -c "import $m" 2>&1; done \
  | grep -c -e storage_service -e "cannot import name 'types'"

# --- GATE 3: contract conformance (expect "contracts OK") ---
python -c "import inspect; from app.services.storage_service import upload_file, \
upload_attachment, get_file_content; \
assert inspect.iscoroutinefunction(upload_file), 'upload_file must be awaitable'; \
assert not inspect.iscoroutinefunction(upload_attachment); \
assert not inspect.iscoroutinefunction(get_file_content); print('contracts OK')"

# --- GATE 5: manifest resolvability (expect exit 0 and a clean check) ---
pip install -r requirements.txt && pip check

# --- GATE 6: configuration compatibility (expect the two exported values) ---
python -c "from app.core.config import get_settings; s = get_settings(); \
print(s.GOOGLE_CLOUD_STORAGE_BUCKET, s.GOOGLE_CLOUD_PROJECT)"
# -> mca-dev-mca-documents mca-dev

# --- Lazy client: no credentials at import (expect "lazy OK") ---
python -c "import app.services.storage_service as s; assert s._client is None; print('lazy OK')"
```

**Regression parity gates — both directions matter.**

```bash
python -m flake8 . --count                                  # -> 160  (NOT fewer, NOT more)
python -m flake8 app/services/storage_service.py --count    # -> 0
python -m flake8 app/services/ocr_service.py --count        # -> 8   (pre-fix parity, preserved deliberately)
python -m pytest tests --collect-only -q                    # -> 0 collected, exactly 3 collection errors
```

> A repository-wide count **below** 160 is a **failure**, not an improvement: it means pre-existing violations were "helpfully" corrected, which the AAP classifies as an unrequested refactor. Likewise, **fewer than three** collection errors means an out-of-scope file was modified.

Signature reference, as printed by `inspect`:

| Symbol | Coroutine | Signature |
|---|---|---|
| `upload_attachment` | no | `(filename: str, file_content: bytes, content_type: Optional[str] = None) -> str` |
| `upload_file` | **yes** | `(file: fastapi.datastructures.UploadFile) -> str` |
| `get_file_content` | no | `(file_path: str) -> bytes` |
| `delete_file` | no | `(file_path: str) -> None` |
| `file_exists` | no | `(file_path: str) -> bool` |
| `generate_download_url` | no | `(file_path: str, expiration_minutes: int = 15) -> str` |

### 9.5 Container build

```bash
cd "$REPO"
docker build --no-cache -f infrastructure/docker/Dockerfile.backend \
  -t mca-backend:local backend/                      # -> exit 0

# Confirm the CVE floors and the deliverable landed in the image
docker run --rm --entrypoint sh mca-backend:local -c \
  'python --version; pip --version | head -1; \
   python -c "import importlib.metadata as m; print(\"wheel\", m.version(\"wheel\"))"; \
   wc -l /app/services/storage_service.py'
# -> Python 3.9.25 / pip 26.0.1 / wheel 0.47.0 / 667 /app/services/storage_service.py
```

**Known container defect (task R2).** The image flattens the package, so `import app.*` fails inside it even though the file is present:

```bash
docker run --rm --entrypoint sh mca-backend:local -c \
  'cd /app && python -c "import app.services.storage_service"'
# -> ModuleNotFoundError: No module named 'app'
```

The cause is `Dockerfile.backend:24` `COPY ./app /app` combined with `:30 CMD ["uvicorn","main:app",...]`. Until R2 lands, mount the un-flattened tree and set `PYTHONPATH` to verify in-image behaviour:

```bash
docker run --rm -v "$REPO/backend:/src:ro" -e PYTHONPATH=/src \
  -e PROJECT_NAME=mca -e API_V1_STR=/api/v1 -e SECRET_KEY=dev \
  -e DATABASE_URL=postgresql://u:p@localhost/mca -e GOOGLE_CLOUD_PROJECT=mca-dev \
  -e GOOGLE_CLOUD_STORAGE_BUCKET=mca-dev-mca-documents \
  -e EMAIL_SUBMISSION_ADDRESS=intake@example.com \
  --entrypoint sh mca-backend:local -c \
  'python -c "import app.services.storage_service; print(\"in-image import OK\")"'
# -> in-image import OK
```

### 9.6 Application startup

**What works today.** The storage and OCR modules import and run. Individual routers can be mounted and served.

**What does not.** `uvicorn app.main:app` **fails** — this is expected and documented:

```bash
cd "$REPO/backend"
python -c "import app.main"
# -> ImportError: cannot import name 'ApplicationCreate' from 'app.schema.application_schema'
celery -A app.tasks.celery_tasks worker --loglevel=info
# -> ImportError: cannot import name 'Webhook' from 'app.db.models'
```

AAP §0.3.3.1 states explicitly that application boot cannot be this fix's success criterion. Tasks H5–H7 (app) and H10–H11 (worker) remove these blockers.

**To serve the attachment router today**, mount it directly. Create `harness.py` outside the checkout, substitute the bucket accessor, and mount the real router unchanged:

```python
# /tmp/mca-harness/harness.py  — keep OUTSIDE the repository
import os
from urllib.parse import quote
from fastapi import FastAPI

BUCKET = os.environ["GOOGLE_CLOUD_STORAGE_BUCKET"]
STORE = {}


class FakeBlob:
    def __init__(self, name):
        self.name = name

    def upload_from_string(self, data, content_type=None, **kw):
        STORE[self.name] = bytes(data)

    def download_as_bytes(self, **kw):
        from google.api_core import exceptions as gexc
        if self.name not in STORE:
            raise gexc.NotFound(self.name)
        return STORE[self.name]

    def delete(self, **kw):
        STORE.pop(self.name, None)

    def exists(self, *a, **kw):
        return self.name in STORE

    @property
    def public_url(self):
        return "https://storage.googleapis.com/%s/%s" % (
            BUCKET, quote(self.name, safe="/"))


class FakeBucket:
    name = BUCKET

    def blob(self, name):
        return FakeBlob(name)


import app.services.storage_service as ss
ss._get_bucket = lambda: FakeBucket()          # remove once ADC is available (task H1)

import app.api.attachments as attachments

app = FastAPI(title="MCA storage-boundary harness")
app.include_router(attachments.router, prefix="/api/attachments", tags=["attachments"])


@app.get("/health")
def health():
    return {"ok": True, "bucket": BUCKET, "objects": len(STORE),
            "lazy_client_is_none": ss._client is None}
```

```bash
cd "$REPO/backend"
export PYTHONPATH="$PYTHONPATH:/tmp/mca-harness"
python -m uvicorn harness:app --host 127.0.0.1 --port 8099 &
sleep 5
curl -s http://127.0.0.1:8099/health | python3 -m json.tool
# -> {"ok": true, "bucket": "mca-dev-mca-documents", "objects": 0, "lazy_client_is_none": true}
curl -s http://127.0.0.1:8099/openapi.json | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print(sorted(d['paths']))"
```

Stop it by the exact PID you captured — never with a broad `pkill`:

```bash
python -m uvicorn harness:app --host 127.0.0.1 --port 8099 & pid=$!
# ... work ...
kill $pid
```

### 9.7 Example usage

```bash
cd "$REPO/backend"

# 1. Upload bytes and read them straight back (the round-trip contract)
python - <<'PY'
from unittest import mock
from urllib.parse import quote
import app.services.storage_service as ss

STORE = {}


class B:
    def __init__(self, n):
        self.name = n

    def upload_from_string(self, d, content_type=None, **k):
        STORE[self.name] = bytes(d)

    def download_as_bytes(self, **k):
        return STORE[self.name]

    @property
    def public_url(self):
        return "https://storage.googleapis.com/bkt/" + quote(self.name, safe="/")


class K:
    def blob(self, n):
        return B(n)


with mock.patch.object(ss, "_get_bucket", return_value=K()):
    url = ss.upload_attachment("contract.pdf", b"hello", "application/pdf")
    print("stored at:", url)
    print("read back:", ss.get_file_content(url))
PY
# -> stored at: https://storage.googleapis.com/bkt/attachments/2026/08/04/<uuid4hex>-contract.pdf
# -> read back: b'hello'

# 2. Multipart upload through the real route (needs the §9.6 harness running)
printf '%%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%%%EOF\n' > /tmp/sample.pdf
curl -s -o /dev/null -w "HTTP %%{http_code}\n" \
  -F "file=@/tmp/sample.pdf;type=application/pdf" \
  "http://127.0.0.1:8099/api/attachments/applications/11111111-1111-1111-1111-111111111111/attachments/"
# -> HTTP 500  *** EXPECTED *** — the object IS written; only the response model fails (task R4)

# 3. OCR path — proves vision.Image replaced the removed vision.types
python -c "
from google.cloud import vision
print('vision.types present:', hasattr(vision, 'types'))   # -> False
print('vision.Image present:', hasattr(vision, 'Image'))   # -> True
print('constructed:', type(vision.Image(content=b'x')).__module__)
"
```

### 9.8 Troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| `ModuleNotFoundError: No module named 'app'` | `PYTHONPATH` does not point at `backend/` | `export PYTHONPATH="$REPO/backend"`. Do **not** add `__init__.py` files — PEP 420 namespace packages resolve correctly and AAP §0.2.1.1 disproves that hypothesis explicitly. |
| `pydantic.error_wrappers.ValidationError: 7 validation errors for Settings … field required` | The seven no-default `Settings` fields are not exported | Run §9.2 step 4, or `source /opt/mca-setup/env.sh` |
| `ImportError: cannot import name 'ApplicationCreate'` | Pre-existing defect at `applications.py:5`; blocks `import app.main` | Expected. Task H5. Never use `import app.main` as a gate. |
| `ImportError: cannot import name 'Webhook'` | Pre-existing defect at `webhook_service.py:2`; blocks the Celery worker | Expected. Task H10. |
| `AttributeError: 'Settings' object has no attribute 'CORS_ORIGINS'` (or `CELERY_BROKER_URL`, `WEBHOOK_TIMEOUT`) | Read by code, never declared on `Settings`. pydantic v1 ignores undeclared env vars, so exporting does not help | Declare the field on `Settings`. Tasks H6, H10. |
| Upload returns 500 but the object exists in the bucket | `attachments.py:20-24` builds the response model with `application_id`/`file_name`/`file_url`, while the schema's only required fields are `storage_url`/`type`/`upload_date` | Expected today. Task H8. Confirm the write with your bucket listing, or `/objects` on the §9.6 harness. |
| `ModuleNotFoundError: No module named 'app'` **inside the container** | `Dockerfile.backend:24`/`:30` flatten the package | Task H3. Meanwhile use the mount-plus-`PYTHONPATH` workaround in §9.5. |
| `google.auth.exceptions.DefaultCredentialsError` on first storage call | No ADC in the environment. Note the error appears on **first use**, never at import — that is by design | `gcloud auth application-default login`, or substitute `_get_bucket` as in §9.6. Task H1. |
| `generate_download_url` raises about signing | Cloud Run ADC supplies no private key; `roles/iam.serviceAccountTokenCreator` is absent from all of `infrastructure/` | Task M1. The write path deliberately returns a canonical URL instead, so uploads are unaffected. |
| `pip install` resolves `ResolutionImpossible` | Interpreter is not Python 3.9 | Recreate the venv with `python3.9 -m venv`. FastAPI 0.126.0+ requires pydantic ≥ 2.7, which conflicts with the `pydantic==1.10.13` pin that keeps `config.py` working unedited. |
| First `passlib` hash raises `ValueError` | An unbounded `bcrypt` resolved to 5.x, which refuses secrets over 72 bytes instead of truncating | Already prevented by `bcrypt==4.0.1` in the manifest. Do not raise it: 4.1.0+ removed the `__about__` attribute passlib reads. |
| `flake8 . --count` returns fewer than 160 | Pre-existing violations were "helpfully" fixed | Revert the cleanup. Parity is the gate; a lower count is a failure. |
| `pytest` fails at collection with 3 errors | Pre-existing: `test_api.py:3` → `app.main`; `test_services.py:3-6` → a top-level `services` package that never existed; `test_tasks.py:3` → a top-level `backend` package that never existed | **This is the expected pass condition.** Task M5 repairs it. |
| Frontend `/` returns 404 and `/index.html` renders blank | No `vite.config.*`; `index.html` lives in `public/` so it is served statically with zero `<script>` elements | Pre-existing and outside AAP scope. Zero frontend files differ from baseline. |

---

## 10. Appendices

### Appendix A — Command Reference

| Purpose | Command | Expected |
|---|---|---|
| Load the environment | `source /opt/mca-setup/env.sh` | PATH, PYTHONPATH and 7 settings exported |
| Install dependencies | `cd backend && pip install -r requirements.txt` | exit 0 |
| Check dependency graph | `pip check` | `No broken requirements found.` |
| Byte-compile | `cd backend && python -m compileall -q app tests` | exit 0 |
| Gate 1 — imports | see §9.4 | 5 PASS / 0 FAIL |
| Gate 2 — signatures gone | see §9.4 | `0` |
| Gate 3 — contracts | see §9.4 | `contracts OK` |
| Gate 5 — manifest | `pip install -r requirements.txt && pip check` | exit 0, clean |
| Gate 6 — config | see §9.4 | `mca-dev-mca-documents mca-dev` |
| Lazy client | `python -c "import app.services.storage_service as s; assert s._client is None; print('lazy OK')"` | `lazy OK` |
| Lint parity (repo) | `cd backend && python -m flake8 . --count` | `160` exactly |
| Lint (new module) | `python -m flake8 app/services/storage_service.py --count` | `0` |
| Lint (OCR file) | `python -m flake8 app/services/ocr_service.py --count` | `8` |
| Collection parity | `cd backend && python -m pytest tests --collect-only -q` | 0 collected, 3 errors |
| Container build | `docker build --no-cache -f infrastructure/docker/Dockerfile.backend -t mca-backend:local backend/` | exit 0 |
| Diff vs baseline | `git diff 543db77d --stat` | 4 files, +809/−4 |
| Verify authorship | `git log --format='%an <%ae>' 543db77d..HEAD \| sort -u` | `Blitzy Agent <agent@blitzy.com>` |
| Frontend type-check | `cd frontend && npx tsc --noEmit` | 50 errors (pre-existing) |

### Appendix B — Port Reference

| Service | Default port | Source | Notes |
|---|---|---|---|
| Backend (FastAPI / uvicorn) | 8000 | `Dockerfile.backend:27` `EXPOSE 8000` | Shifts by `CLONE_INDEX` in the dev env script |
| Frontend (Vite dev server) | 3000 | dev env script | `docker-compose.yml` also maps 3000:3000 |
| PostgreSQL | 5432 | `docker-compose.yml` | `DATABASE_URL` DSN |
| Redis (Celery broker) | 6379 | dev env script | `CELERY_BROKER_URL` |
| Backend per `docker-compose.yml` | 5000 | `docker-compose.yml` | **Inconsistent** with `EXPOSE 8000`; that compose file is stale and out of scope |
| Validation harness (this assessment) | 8099 | ad-hoc | Chosen to avoid collision with 8000 |
| Frontend probe (this assessment) | 3099 | ad-hoc | Chosen to avoid collision with 3000 |

### Appendix C — Key File Locations

| Path | Role | Change |
|---|---|---|
| `backend/app/services/storage_service.py` | **The deliverable** — GCS persistence module, 667 lines, 6 public + 12 private functions | **CREATED** |
| `backend/requirements.txt` | **The deliverable** — 18 pinned distributions, 7 groups, residual-advisory ledger | **CREATED** |
| `backend/app/services/ocr_service.py` | **The deliverable** — `vision.types` → `vision.Image` | **MODIFIED** (2 line changes) |
| `infrastructure/docker/Dockerfile.backend` | pip/wheel CVE floors | **MODIFIED** — prior-agent deviation, retained and escalated |
| `backend/app/api/attachments.py` | Consumer — `await upload_file(file)` at `:17` | Unchanged (proven unnecessary) |
| `backend/app/services/email_processor.py` | Consumer — `upload_attachment(filename, file_content)` at `:46` | Unchanged (proven unnecessary) |
| `backend/app/core/config.py` | Supplies `GOOGLE_CLOUD_STORAGE_BUCKET` `:10` and `GOOGLE_CLOUD_PROJECT` `:9` | Unchanged (proven unnecessary) |
| `backend/app/db/models.py` | `Attachment.storage_url` non-nullable at `:50` | Unchanged (do-not-modify) |
| `backend/app/schema/application_schema.py` | `Attachment` pydantic contract; missing `ApplicationCreate` | Unchanged (do-not-modify) |
| `backend/app/main.py` | App entry point; 3 own defects | Unchanged (out of scope) |
| `backend/app/tasks/celery_tasks.py` | Worker tier; consumes `process_document` | Unchanged (out of scope) |
| `backend/tests/` | 3 modules, all failing at collection | Unchanged (do-not-modify) |
| `infrastructure/terraform/main.tf` | Buckets `:43-51`; IAM `:116-145`; Cloud Run `:79-95` | Unchanged (reference only) |
| `.github/workflows/ci.yml` | Reads the manifest at `:29` | Unchanged (needed none) |
| `scripts/setup_environment.sh` | Reads the manifest at `:13` | Unchanged (needed none) |
| `frontend/src/components/DocumentViewer.tsx` | Consumes `storage_url` as `documentUrl` `:10`/`:60` | Unchanged (out of scope) |
| `/opt/mca-setup/env.sh` | Dev environment, deliberately **outside** the checkout | Not in the repository |
| `blitzy/screenshots/` · `blitzy/screen_recordings/` | 87 screenshots · 21 recordings of runtime evidence | Untracked artifacts |

### Appendix D — Technology Versions

| Component | Version | Source |
|---|---|---|
| Python | 3.9.25 | `ci.yml:19`, `Dockerfile.backend:2` |
| pip | 26.0.1 | `Dockerfile.backend:19` |
| wheel | 0.47.0 | `Dockerfile.backend:20` |
| fastapi | 0.125.0 | manifest — ceiling imposed by the pydantic pin |
| pydantic | 1.10.13 | manifest — **must** stay < 2.0 for `config.py:1` |
| starlette | 0.49.3 | resolver result of the fastapi bound |
| python-multipart | 0.0.20 | manifest — mandatory for `UploadFile = File(...)` |
| uvicorn | 0.23.2 | manifest — named at `Dockerfile.backend:30` |
| SQLAlchemy | 2.0.23 | manifest — **must** be 2.x for `models.py:1` |
| psycopg2-binary | 2.9.9 | manifest |
| google-cloud-storage | **2.14.0** | manifest — **the one genuinely new dependency** |
| google-cloud-vision | 3.14.0 | manifest — publishes `Image` at the package root |
| google-cloud-logging | 3.15.0 | manifest — `logging.py:2` |
| protobuf | 6.33.6 | resolver result of the two Google bounds |
| celery | 5.3.4 | manifest — `celery_tasks.py:1` |
| redis | 5.0.1 | manifest — broker client |
| python-jose[cryptography] | 3.5.0 | manifest — `security.py:2` |
| passlib[bcrypt] | 1.7.4 | manifest — `security.py:8` |
| bcrypt | 4.0.1 | manifest — provider bound, measured not preferred |
| cryptography | 50.0.0 | resolver result of the jose extra |
| requests | 2.32.5 | manifest — `webhook_service.py:1` |
| python-dotenv | 1.0.0 | manifest — backs `env_file` |
| urllib3 | 2.6.3 | resolver result |
| pytest | 7.4.4 | manifest — `ci.yml:37` |
| httpx | 0.25.2 | manifest — FastAPI `TestClient` |
| flake8 | 7.3.0 (pycodestyle 2.14.0 · pyflakes 3.4.0 · mccabe 0.7.0) | lint gate |
| Docker | 29.7.0 | container validation |
| Node.js / npm | v22.23.2 / 11.18.0 | frontend only |
| TypeScript | 5.9.3 | frontend only |
| Vite | 4.5.14 | frontend only |
| git | 2.51.0 | — |

### Appendix E — Environment Variable Reference

**Declared on `Settings` (`backend/app/core/config.py`) — the seven with no default are mandatory.**

| Variable | Required | Example | Consumed at |
|---|---|---|---|
| `PROJECT_NAME` | ✅ | `mca` | `config.py:5` |
| `API_V1_STR` | ✅ | `/api/v1` | `config.py:6` |
| `SECRET_KEY` | ✅ | *(secret)* | `config.py:7`, JWT signing |
| `DATABASE_URL` | ✅ | `postgresql://user:password@127.0.0.1:5432/myapp` | `config.py:8`, `database.py:5` at import |
| `GOOGLE_CLOUD_PROJECT` | ✅ | `mca-dev` | `config.py:9` → `storage_service._get_client` |
| `GOOGLE_CLOUD_STORAGE_BUCKET` | ✅ | `mca-dev-mca-documents` | `config.py:10` → `storage_service._bucket_name` |
| `EMAIL_SUBMISSION_ADDRESS` | ✅ | `intake@example.com` | `config.py:11` |
| `SENTRY_DSN` | optional | *(unset)* | `config.py:12`, defaults to `None` |

**Read by code but NEVER declared on `Settings` — exporting these does nothing (pydantic v1 ignores undeclared env vars). Each is a source-code defect.**

| Variable | Read at | Consequence today | Task |
|---|---|---|---|
| `CORS_ORIGINS` | `main.py:24` (import time) | `AttributeError` on app import | H6 |
| `CELERY_BROKER_URL` | `celery_tasks.py:9` (import time) | `AttributeError` on worker import | H11 |
| `WEBHOOK_TIMEOUT` | `webhook_service.py:37` | `AttributeError` on webhook dispatch | H10 |
| `ALGORITHM` | `security.py` | `AttributeError` on token operations | H6 |
| `LOG_LEVEL` | `logging.py` | `AttributeError` during logging setup | H6 |
| `RUNNING_IN_GCP` | `logging.py` | `AttributeError` during logging setup | H6 |

**Not used by this codebase but present in stale scaffolding:** `NODE_ENV`, `REACT_APP_API_URL` (`docker-compose.yml`), `REACT_APP_API_BASE_URL` (`frontend/src/services/api.ts` — a Create-React-App variable Vite never defines).

**Not required at import.** The storage module reads its two settings *inside* functions and constructs its client lazily, so `GOOGLE_APPLICATION_CREDENTIALS` / ADC are consulted only on first storage use — deliberately unlike the import-time pattern at `database.py:5`.

### Appendix F — Developer Tools Guide

| Tool | Invocation | Notes |
|---|---|---|
| flake8 7.3.0 | `python -m flake8 . --count` | **Parity gate at 160.** No `.flake8`/`setup.cfg` exists and the AAP forbids adding one, so default rules apply (79-column limit). Never pass `--fix`-style options. |
| pytest 7.4.4 | `python -m pytest tests --collect-only -q` | Use `--collect-only`. Bare `pytest` is **not** a gate: 3 collection errors are the expected result. |
| `compileall` | `python -m compileall -q app tests` | Fast syntax gate. Remove any `__pycache__` it leaves before committing. |
| `inspect` | see Gate 3 in §9.4 | Asserts awaitability and arity by introspection rather than by reading source — the only way to catch a module that imports but exposes the wrong shape. |
| pip | `pip install -r requirements.txt` · `pip check` | Always on Python 3.9. `pip check` catches provider conflicts that `install` alone does not. |
| Docker | `docker build --no-cache -f infrastructure/docker/Dockerfile.backend -t mca-backend:local backend/` | Build context is `backend/`, not the repository root — the Dockerfile copies `requirements.txt` relative to its own context. |
| curl | `curl -s http://127.0.0.1:8099/health \| python3 -m json.tool` | Harness probing |
| git | `git diff 543db77d --name-status` | `543db77d` is the pre-agent baseline. Never run `git config user.name`/`user.email`. |
| uvicorn | `python -m uvicorn harness:app --host 127.0.0.1 --port 8099 & pid=$!` | Always capture the PID and stop with `kill $pid`. Never use a broad `pkill`. |
| npx tsc | `cd frontend && npx tsc --noEmit` | Reports the 50 pre-existing errors; not a gate for this work. |

### Appendix G — Glossary

| Term | Meaning |
|---|---|
| **AAP** | Agent Action Plan — the authoritative specification of scope for this engagement. Its §0.6.1 change set is exhaustive: two file creations and one two-line modification. |
| **AAP gate** | One of the six verification checks defined in AAP §0.7 (import resolution, signature eradication, contract conformance, functional validation, manifest resolvability, configuration compatibility). |
| **ADC** | Application Default Credentials — the keyless credential chain Cloud Run supplies. It provides an access token but **no private key**, which is why V4 signing needs an extra IAM grant. |
| **Blast radius** | The six modules rendered unimportable by the missing module: three direct importers and three transitive victims. |
| **Canonical URL** | The stable, permanent `https://storage.googleapis.com/<bucket>/<object>` form. Returned by the upload path because `Attachment.storage_url` is non-nullable and must stay resolvable for the row's lifetime. |
| **Contract (sync/async by)** | A shape imposed by an existing call site rather than chosen. `upload_file` must be awaitable because `attachments.py:17` awaits it; `upload_attachment` must be synchronous because `email_processor.py:46` uses its result directly. |
| **Lint parity** | The regression gate: repository-wide flake8 must equal exactly 160. A count **below** the baseline is also a failure, because it means unrequested cleanup occurred. |
| **Namespace gate** | `_validated_object_name` — every read, delete, probe and signature must pass it: `attachments/` prefix, NFC normalisation, no control code points, no empty/`.`/`..` segments, bounded byte length. |
| **NOT-gate** | A command documented to fail for reasons outside this fix, which must therefore never be used as a success criterion: `import app.main`, the Celery worker, and bare `pytest`. |
| **PEP 420 namespace package** | A package directory with no `__init__.py`. The repository has none anywhere under `backend/`, and this is correct — adding them would be scope creep against a hypothesis AAP §0.2.1.1 disproves empirically. |
| **Path-to-production** | Work required to deploy the AAP deliverables that the AAP itself deferred. All 65.0 remaining hours fall in this category. |
| **Resolver result** | A dependency version chosen by pip from another pin's bound rather than pinned directly — e.g. starlette 0.49.3, protobuf 6.33.6, urllib3 2.6.3. |
| **Round-trip contract** | The constraint that the identifier returned by an upload is the same string later handed to `get_file_content`, so every emitted form must resolve back to one object name. A naive implementation would upload fine and 404 on read. |
| **V4 signed URL** | A time-limited Cloud Storage URL requiring a signing credential. Unavailable on this deployment until the Service Account Credentials API is enabled and `roles/iam.serviceAccountTokenCreator` granted. |