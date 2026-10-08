"""A tiny Firestore emulator client over REST, enough to exercise security rules.

Requests carry an unsigned ID token for an anonymous user (the emulator accepts
them), or the `owner` token, which bypasses rules, to seed data. Stdlib only.
"""

import base64
import datetime as dt
import json
import os
import urllib.error
import urllib.request

PROJECT = "demo-group-polls"
HOST = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
DOCS = f"projects/{PROJECT}/databases/(default)/documents"
OWNER = "owner"


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def token(uid: str) -> str:
    now = int(dt.datetime.now(dt.UTC).timestamp())
    payload = {
        "iss": f"https://securetoken.google.com/{PROJECT}",
        "aud": PROJECT,
        "sub": uid,
        "user_id": uid,
        "iat": now,
        "exp": now + 3600,
        "auth_time": now,
        "firebase": {"sign_in_provider": "anonymous", "identities": {}},
    }
    return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(payload)}."


def _request(
    method: str, path: str, body: dict | None, auth: str | None
) -> tuple[int, dict]:
    req = urllib.request.Request(f"http://{HOST}/{path}", method=method)
    req.add_header("Content-Type", "application/json")
    if auth:
        req.add_header("Authorization", f"Bearer {auth}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data) as res:
            raw = res.read()
            return res.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as err:
        raw = err.read()
        return err.code, json.loads(raw) if raw else {}


def load_rules(source: str) -> None:
    status, body = _request(
        "PUT",
        f"emulator/v1/projects/{PROJECT}:securityRules",
        {"rules": {"files": [{"name": "firestore.rules", "content": source}]}},
        None,
    )
    assert status == 200, body


def clear() -> None:
    _request("DELETE", f"emulator/v1/{DOCS}", None, None)


# --- Values --------------------------------------------------------------------------


class ServerTime:
    """Marker: set this field to the request time (FieldValue.serverTimestamp())."""


class Increment:
    """Marker: add n to this field (FieldValue.increment(n))."""

    def __init__(self, n: int = 1):
        self.n = n


def value(v) -> dict:
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, dt.datetime):
        return {
            "timestampValue": v.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        }
    raise TypeError(v)


def _write(path: str, fields: dict, *, exists: bool | None, merge: bool) -> dict:
    plain = {
        k: v for k, v in fields.items() if not isinstance(v, (ServerTime, Increment))
    }
    transforms = []
    for k, v in fields.items():
        if isinstance(v, ServerTime):
            transforms.append({"fieldPath": k, "setToServerValue": "REQUEST_TIME"})
        elif isinstance(v, Increment):
            transforms.append({"fieldPath": k, "increment": {"integerValue": str(v.n)}})
    write: dict = {
        "update": {
            "name": f"{DOCS}/{path}",
            "fields": {k: value(v) for k, v in plain.items()},
        }
    }
    if merge:
        write["updateMask"] = {"fieldPaths": list(plain)}
    if transforms:
        write["updateTransforms"] = transforms
    if exists is not None:
        write["currentDocument"] = {"exists": exists}
    return write


def create(path: str, fields: dict) -> dict:
    return _write(path, fields, exists=False, merge=False)


def update(path: str, fields: dict) -> dict:
    return _write(path, fields, exists=True, merge=True)


def commit(auth: str | None, *writes: dict) -> bool:
    status, _ = _request("POST", f"v1/{DOCS}:commit", {"writes": list(writes)}, auth)
    return status == 200


def get(auth: str | None, path: str) -> bool:
    status, _ = _request("GET", f"v1/{DOCS}/{path}", None, auth)
    return status == 200


def read(path: str) -> dict:
    """A document's fields as plain values, read as owner."""
    _, body = _request("GET", f"v1/{DOCS}/{path}", None, OWNER)
    out = {}
    for k, v in body.get("fields", {}).items():
        kind, raw = next(iter(v.items()))
        out[k] = int(raw) if kind == "integerValue" else raw
    return out


def query(
    auth: str | None,
    collection: str,
    filters: list[tuple[str, str, object]],
    parent: str = "",
    all_descendants: bool = False,
) -> bool:
    ops = {"==": "EQUAL", ">": "GREATER_THAN"}
    where = [
        {"fieldFilter": {"field": {"fieldPath": f}, "op": ops[op], "value": value(v)}}
        for f, op, v in filters
    ]
    structured: dict = {
        "from": [{"collectionId": collection, "allDescendants": all_descendants}]
    }
    if where:
        structured["where"] = (
            where[0]
            if len(where) == 1
            else {"compositeFilter": {"op": "AND", "filters": where}}
        )
    base = f"{DOCS}/{parent}" if parent else DOCS
    status, _ = _request(
        "POST", f"v1/{base}:runQuery", {"structuredQuery": structured}, auth
    )
    return status == 200
