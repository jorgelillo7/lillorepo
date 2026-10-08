# group_polls — backend of "¿Qué votáis?"

Red-or-blue polls between friends (private, by link, results with names) and for everyone
(public feed for a week, percentages only). The app is Android, in
[`lillo-android-apps/apps/group-polls`](https://github.com/jorgelillo7/lillo-android-apps/tree/master/apps/group-polls)
(`com.jorgelillo.grouppolls`). There is no server: the app talks to Firestore directly, so this
package is the backend's whole logic and its operations:

| File | What |
|---|---|
| [`firestore.rules`](firestore.rules) | Security rules: the only boundary between users and the data |
| [`tests/test_rules.py`](tests/test_rules.py) | The rules against the Firestore emulator (22 cases) |
| [`scripts/moderate.py`](scripts/moderate.py) | Review queue, restore and remove for public polls |
| [`../../infra/group_polls.tf`](../../infra/group_polls.tf) | The GCP project: APIs, Firestore, indexes, rules release |
| [`OPERATIONS.md`](OPERATIONS.md) | Every command: create the project, test and deploy rules, moderate, delete data |

## Data model

```
polls/{code}                 visibility, question, red, blue, creatorId, creatorName, language,
                             createdAt (server time), durationDays (1 | 7 | 0 = no limit),
                             closedAt?, redVotes, blueVotes, reports, hidden
polls/{code}/votes/{uid}     voterId, side, prediction, votedAt, name (private polls only)
polls/{code}/reports/{uid}   at
```

- The 12-character random code is the poll's id and, for private polls, its only key.
- Users are Firebase anonymous users; App Check (Play Integrity) is enforced on Firestore.
- A vote and its counter (+1) are one batch; the rules reject either one alone.
- Public polls never store voter names; private ones show who voted what.
- Three reports hide a public poll from the feed until it is reviewed (`scripts/moderate.py`).
- "Delete my data" blanks the user's name on their polls and votes; the votes stay counted.
