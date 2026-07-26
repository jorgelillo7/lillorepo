# Capability: gemini-client

Minimal Gemini REST client for structured JSON extraction (OCR label parsing)
and image generation (studio-photo isolation).

- **Source:** `core/sdk/gemini.py`
- **Verified by:** `core/tests/test_gemini.py`

---

### Requirement: Structured JSON generation

`generate_json` SHALL POST the prompt (optionally with an inline base64 image
and a response schema) and parse the model's JSON text back into a dict. With a
schema it SHALL set `responseSchema` + `responseMimeType: application/json`. A
body it cannot parse SHALL raise `GeminiError("Unparseable…")`.

#### Scenario: parse output; send image + schema; malformed
- **WHEN** the model returns JSON text **THEN** it is parsed into a dict
- **WHEN** called with image + schema **THEN** the request carries the base64
  inline data, the schema, and the JSON mime type
- **WHEN** the body has no usable candidate **THEN** it raises "Unparseable"
- *Verifies:* `test_generate_json_parses_structured_output`,
  `test_generate_json_sends_image_and_schema`,
  `test_generate_json_raises_on_malformed_body`

### Requirement: Opt-in retry on transient overload

`generate_json` SHALL NOT retry by default. With `retries=N` it SHALL retry on
transient failures (e.g. 503), sleeping `_RETRY_BACKOFF_SECONDS`, and raise
`GeminiError` (naming the status) when retries exhaust or on a non-retried
error.

#### Scenario: default no-retry, opt-in retry, exhaust
- **WHEN** a 503 is returned with no `retries` **THEN** it raises immediately
  (one call)
- **WHEN** `retries=1` and a 503 precedes a success **THEN** it retries and
  returns
- **WHEN** the 503 persists with `retries=1` **THEN** it raises after 2 calls
- **WHEN** any HTTP error (e.g. 429) occurs **THEN** it raises `GeminiError`
  naming the status
- *Verifies:* `test_generate_json_does_not_retry_by_default`,
  `test_generate_json_retries_on_503_then_succeeds`,
  `test_generate_json_raises_after_exhausting_retries`,
  `test_generate_json_raises_on_http_error`

### Requirement: Image generation with diagnostic errors

`generate_image` SHALL request `responseModalities: [IMAGE]` and return the
decoded bytes of the inline image part. When no image part is present it SHALL
raise naming the cause, surfacing the `finishReason` (e.g. `IMAGE_SAFETY`) when
the candidate has no content, so logs explain the fallback.

#### Scenario: decode, missing part, safety block
- **WHEN** the response carries an inline image **THEN** its bytes are returned
- **WHEN** there is no image part **THEN** it raises "no image part"
- **WHEN** the candidate has only a `finishReason` **THEN** the error names it
  (e.g. `IMAGE_SAFETY`)
- *Verifies:* `test_generate_image_decodes_inline_data`,
  `test_generate_image_raises_without_image_part`,
  `test_generate_image_surfaces_finish_reason_when_content_missing`
