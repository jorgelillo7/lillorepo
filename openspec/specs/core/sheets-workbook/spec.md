# Capability: sheets-workbook

Reads a whole Google Sheets spreadsheet, every tab, for the competitions page.
The spreadsheet is kept by hand by the league.

- **Source:** `core/sdk/gcp.py` (`get_workbook`, `get_google_service`)
- **Verified by:** `core/tests/test_gcp_services.py`

---

### Requirement: Every tab in two calls, returned untouched

`get_workbook(service, spreadsheet_id)` SHALL return every tab as
`(title, rows)` in the owner's order, using one metadata call and one
`values.batchGet`, whatever the number of tabs. Tab names SHALL be quoted as
ranges. An empty tab SHALL come back as an empty row list. A spreadsheet with
no tabs SHALL return `[]` without asking for values. Rows SHALL be returned
ragged, exactly as the API sends them. The reader does not decide which tabs
matter.

The league keeps adding competitions as tabs, so one call per tab does not
scale. An empty `batchGet` is an API error, which is why no tabs means no
values call. A tab name with a space, such as "Copa Castolo", is a parse error
unless it is quoted. Deciding what a tab is belongs to the caller, which can
then report what it ignored: an earlier reader imposed a fixed column shape
here and silently dropped any tab under six rows.

#### Scenario: many tabs, empty tab, no tabs
- **WHEN** the spreadsheet has several tabs **THEN** exactly one metadata call
  and one `batchGet` are made, and each tab is returned under its title
- **WHEN** a tab has no values **THEN** it is returned with `[]`
- **WHEN** there are no tabs **THEN** `[]` is returned and no values call is
  made
- *Verifies:* `test_get_workbook_reads_every_tab_in_two_calls`,
  `test_get_workbook_returns_empty_tabs_as_empty`,
  `test_get_workbook_with_no_tabs_makes_no_values_call`

### Requirement: The Sheets client authenticates with a service account

`get_google_service` SHALL build an API client from a mounted service-account
key file and the given scopes.

Sheets is the one Google API here that still reads through a mounted key
instead of ADC.

> **GAP — unverified.** Client construction is untested. A test would patch
> `service_account.Credentials.from_service_account_file` and `build`, and
> assert that the scopes and API version are passed through. Candidate for the
> next test-hardening pass.
