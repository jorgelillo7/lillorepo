# Capability: catalog-reads

The pages that list or compare waters read the catalogue from a short-lived
in-process copy, so a page view does not cost a read of every document.

- **Source:** `packages/be_water/web/repository.py` (`get_all_waters`, `all_analyses`,
  `clear_cache`)
- **Verified by:** `packages/be_water/web/tests/test_repository.py`

---

### Requirement: The catalogue and the analyses are read once a minute

`get_all_waters` and `all_analyses` SHALL reuse their last read for
`CACHE_SECONDS` and hand each caller its own list. A write through this module
(a water, an analysis, its sources or community, a delete) SHALL drop the copy at
once, so the instance that wrote shows its own change immediately. Another
instance can show a write made elsewhere for at most `CACHE_SECONDS`.

Nearly every page needs the whole catalogue (the grid, similar waters, the place
recommender, the community ranking), and it changes a few times a day, so reading
it per request spends the free Firestore allowance on repeats.

#### Scenario: the window
- **WHEN** the catalogue is read twice inside the window **THEN** Firestore is read once, and mutating one caller's list does not change the next
- **WHEN** the window has passed **THEN** it is read again
- **WHEN** this instance saves a water or an analysis **THEN** the next read goes to Firestore
- *Verifies:* `test_the_catalogue_is_read_once_inside_the_window`,
  `test_callers_get_their_own_list`,
  `test_the_catalogue_is_read_again_after_the_window`,
  `test_a_write_on_this_instance_drops_the_cache`,
  `test_the_analyses_are_cached_and_a_saved_entry_drops_them`
