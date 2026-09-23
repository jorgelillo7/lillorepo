# Capability: cloud-storage

Writes and reads single objects in Google Cloud Storage over the JSON API with
Application Default Credentials. It is used for public images and for small
manifests rewritten in place.

- **Source:** `core/sdk/gcp.py` (`upload_object`, `download_object`)
- **Verified by:** `core/tests/test_gcp_services.py`

---

### Requirement: Uploads carry their cache policy as object metadata

`upload_object` SHALL overwrite `gs://{bucket}/{name}` with a single
`multipart` upload whose metadata part names the object and, when given,
carries `cacheControl`. It SHALL return the object's public URL, and SHALL
raise `requests.HTTPError` on any non-2xx.

A `uploadType=media` upload accepts a `Cache-Control` request header and then
silently ignores it. The object stays on the bucket's one-hour default, which
is how a replaced front page kept serving the old image. Multipart is the only
single-request form that carries metadata. A denied write (403: the runtime
service account cannot write the bucket) has to surface, not turn into a
silent no-op. The raw JSON API is used because `google-cloud-storage` is not
in the lock file, and adding it for two calls would bring a dependency bump
into a feature change.

#### Scenario: metadata part, no cache policy, denied write
- **WHEN** an object is uploaded with `cache_control` **THEN** the request is
  `uploadType=multipart`, authorised with a bearer token, the metadata part
  holds the name and `cacheControl`, the payload part holds the bytes, and the
  public URL is returned
- **WHEN** no `cache_control` is given **THEN** the metadata carries only the
  name
- **WHEN** the bucket answers 403 **THEN** `requests.HTTPError` is raised
- *Verifies:* `test_upload_object_sends_cache_control_as_object_metadata`,
  `test_upload_object_omits_cache_control_when_not_given`,
  `test_upload_object_raises_on_denied_write`

### Requirement: Reads are authenticated, uncached, and treat missing as None

`download_object` SHALL return the object's bytes through an authenticated
request that sends `Cache-Control: no-cache`. It SHALL return `None` on a 404,
and SHALL raise on any other error.

These reads feed read-modify-write cycles. Merging onto a cached copy would
silently drop whatever was written since, and a public object is cacheable by
its content, so authentication alone does not guarantee fresh bytes. A
missing object is the normal state before the first write (a season that has
published nothing yet), not a failure.

#### Scenario: bytes, missing
- **WHEN** the object exists **THEN** its bytes are returned, and the request
  carried the bearer token and `no-cache`
- **WHEN** it does not exist **THEN** `None` is returned
- *Verifies:* `test_download_object_returns_bytes`,
  `test_download_object_returns_none_when_missing`
