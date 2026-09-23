# Capability: firestore-store

The thin Firestore layer every package reads and writes through: single
documents, simple queries, bulk writes and transactions, authenticated with
Application Default Credentials.

- **Source:** `core/sdk/firestore.py`
- **Verified by:** `core/tests/test_firestore_sdk.py`, **against the local
  emulator only**. The module skips when `FIRESTORE_EMULATOR_HOST` is unset,
  so CI does not run it. Run it by hand as its docstring describes before
  relying on these scenarios.

---

### Requirement: Keyless access through ADC

The client SHALL be created once per process, lazily, from Application
Default Credentials. The project SHALL come from `FIRESTORE_PROJECT` or
`GOOGLE_CLOUD_PROJECT` when either is set, and otherwise from the ambient
credentials.

Removing the service-account key file was the reason to move the data layer
to Firestore. Inside Cloud Run the runtime service account is picked up with
nothing mounted. Locally, `gcloud auth application-default login` is enough.

> **GAP — unverified.** Nothing tests project resolution from the environment
> or the reuse of a single client. A test would patch `firestore.Client` and
> assert which `project` it is built with, and that it is built once.
> Candidate for the next test-hardening pass.

### Requirement: Document CRUD with Firestore's own semantics

`get_document` SHALL return the document as a dict, or `None` when it does not
exist. `set_document` SHALL overwrite the document, or with `merge=True`
update only the given fields. `delete_document` SHALL succeed whether or not
the document exists. `list_documents` SHALL yield every `(doc_id, data)` pair
in a collection. Collection paths are `/`-joined strings and are not validated
here: the callers build them.

"Missing" is a normal answer for a document, not an error. Deleting a missing
document is a success in Firestore itself, which keeps clean-up code
re-runnable.

#### Scenario: get, missing, merge, delete, list
- **WHEN** a document is set and read back **THEN** the same dict is returned,
  and a missing id returns `None`
- **WHEN** a merge-set touches one field **THEN** the other fields survive
- **WHEN** a document is deleted, or a missing one is deleted **THEN** neither
  raises, and the document reads as `None`
- **WHEN** a collection is listed **THEN** every id maps to its data
- *Verifies:* `test_set_and_get_document`, `test_set_document_merge`,
  `test_delete_document`, `test_list_documents`

### Requirement: Single-clause queries

`query` SHALL apply at most one field filter, an optional order and an
optional limit, and return the matching documents' data.

#### Scenario: filter and order
- **WHEN** a collection is queried on `team == "X"` ordered by `n` **THEN**
  only the X documents come back, in ascending `n`
- *Verifies:* `test_query_filter_and_order`

### Requirement: Bulk operations respect the 500-write batch cap

`batch_write` SHALL write any number of `(doc_id, data)` pairs as full
overwrites, committed in batches of at most 500, and return the count
written. `delete_collection` SHALL delete every document in a collection,
page by page, and return the count deleted. It SHALL NOT recurse into
subcollections. `count` SHALL return a collection's size through an
aggregation query.

Firestore rejects a batch above 500 writes. Full overwrites keyed by id make a
re-run idempotent, which is what lets a backfill be re-run safely. An
aggregation count costs a small fixed number of reads whatever the collection
size, so verifying parity stays inside the free tier.

#### Scenario: across the cap, count, clear
- **WHEN** 1,100 documents are batch-written **THEN** 1,100 are reported and
  counted
- **WHEN** a collection of ten is deleted **THEN** ten are reported and the
  count is zero
- *Verifies:* `test_batch_write_and_count`, `test_delete_collection`

### Requirement: Atomic read-modify-write

`run_transaction(fn)` SHALL run `fn(transaction)` inside a Firestore
transaction and return its result. `fn` must be idempotent, because Firestore
re-runs it on write conflicts.

This guards races such as two picks claiming the same document.

#### Scenario: increment in a transaction
- **WHEN** a transaction reads `n = 1` and writes `n + 1` **THEN** it returns 1
  and the document holds 2
- *Verifies:* `test_run_transaction_reads_and_writes_atomically`
