# chucknorris_bot — Release Notes

Chuck Norris doesn't need release notes. Release notes need Chuck Norris.

### **v1.1 - Now With a Paper Trail (26 July 2026)**

The bot didn't change — reality did. It got its first written contract and its behaviour is now documented like a grown-up service, even though it tells jokes for a living.

* **📐 A behaviour spec (the headline)**: `openspec/specs/chucknorris_bot/chuck-jokes/spec.md` pins what the bot must do — secret-gated webhook, persistent keyboard, command/label dispatch, `/version`, and the graceful fallback when `chucknorris.io` is down — each scenario linked to the test that verifies it. The joke about it living in the wrong GCP project is still true; now it's *documented* as true.
* **📊 Real coverage numbers**: rode the repo-wide `bazel coverage` fix — the bot's suite (18 tests: auth, routing, empty bodies, error fallback) now reports honest line coverage instead of a false zero.
* **🔗 Ops points at the spec**: `OPERATIONS.md` now links the behaviour spec for the *what* and keeps only the *how*.

---

### **v1.0 - The Resurrection (2015 → Cloud Run)**

A joke bot from 2015, dragged out of retirement and dropped onto Cloud Run — freeloading on the `biwenger-tools` GCP project and Artifact Registry, because standing up a second project for a Chuck Norris bot would be, in the words of the README, more effort than anyone could be bothered with.

* **💬 On-demand facts**: `/random`, `/science`, `/food`, `/animal`, `/dev` — plus a persistent reply keyboard so the categories sit under the input field. `/start` and `/help` show the menu; `/version` reports the deployed commit.
* **🔐 Secured webhook**: the Telegram webhook validates the `X-Telegram-Bot-Api-Secret-Token`; anything without it gets a 401, anything from the wrong chat is silently ignored.
* **🛟 Fails funny, not hard**: if the upstream jokes API is unreachable, the bot returns a safe Chuck-Norris-flavoured fallback line instead of crashing. Empty bodies and text-less messages are shrugged off.
* **♻️ Zero new infrastructure**: same `python_service` Bazel macro, same CI pipeline, same cost model as everything else — a whole extra service for the price of a `BUILD.bazel`.
