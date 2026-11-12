"""What `moderate.py restore` and `remove` change, and what they ask first."""

import sys
from unittest import mock

import pytest

from packages.group_polls.scripts import moderate

CODE = "abcdefghijkm"


class FakeDoc:
    def __init__(self, path, store, data=None):
        self.path, self.store, self.data = path, store, data

    @property
    def id(self):
        return self.path.rsplit("/", 1)[-1]

    @property
    def reference(self):
        return self

    @property
    def exists(self):
        return self.path in self.store.docs

    def to_dict(self):
        return self.store.docs[self.path]

    def get(self):
        return self

    def update(self, fields):
        self.store.docs[self.path].update(fields)
        self.store.log.append(("update", self.path, fields))

    def delete(self):
        del self.store.docs[self.path]
        self.store.log.append(("delete", self.path))

    def collection(self, name):
        return FakeCollection(f"{self.path}/{name}", self.store)


class FakeCollection:
    def __init__(self, path, store):
        self.path, self.store = path, store

    def document(self, doc_id):
        return FakeDoc(f"{self.path}/{doc_id}", self.store)

    def stream(self):
        prefix = f"{self.path}/"
        return [
            FakeDoc(p, self.store)
            for p in list(self.store.docs)
            if p.startswith(prefix) and "/" not in p[len(prefix) :]
        ]


class FakeStore:
    """An in-memory Firestore: `docs` maps a path to its fields, `log` the writes."""

    def __init__(self):
        self.docs = {
            f"polls/{CODE}": {
                "question": "¿Playa o montaña?",
                "red": "Playa",
                "blue": "Montaña",
                "hidden": True,
                "reports": 3,
                "redVotes": 2,
                "blueVotes": 1,
            },
            "polls/otherpoll222": {"hidden": True, "reports": 3},
            "polls/otherpoll222/reports/z": {"at": 1},
        }
        for uid in ("v1", "v2", "v3"):
            self.docs[f"polls/{CODE}/votes/{uid}"] = {"side": "red"}
        for uid in ("r1", "r2", "r3"):
            self.docs[f"polls/{CODE}/reports/{uid}"] = {"at": 1}
        self.log = []

    def collection(self, name):
        return FakeCollection(name, self)


def run(action, code, answer, store):
    """Run `moderate <action> <code>` answering the prompt with `answer`."""
    ask = mock.Mock(side_effect=EOFError) if answer is None else mock.Mock()
    if answer is not None:
        ask.return_value = answer
    with (
        mock.patch.object(sys, "argv", ["moderate", action, code]),
        mock.patch.object(moderate, "PROJECT", "demo"),
        mock.patch.object(moderate.firestore, "Client", return_value=store),
        mock.patch("builtins.input", ask),
    ):
        return moderate.main(), ask


def test_restore_unhides_the_poll_and_clears_only_its_reports():
    store = FakeStore()
    code, ask = run("restore", CODE, "y", store)
    assert code == 0
    ask.assert_called_once()
    assert store.docs[f"polls/{CODE}"]["hidden"] is False
    assert store.docs[f"polls/{CODE}"]["reports"] == 0
    assert not [p for p in store.docs if p.startswith(f"polls/{CODE}/reports/")]
    assert len([p for p in store.docs if p.startswith(f"polls/{CODE}/votes/")]) == 3
    assert "polls/otherpoll222/reports/z" in store.docs
    assert store.docs["polls/otherpoll222"]["hidden"] is True


def test_remove_deletes_the_poll_with_its_votes_and_reports():
    store = FakeStore()
    code, ask = run("remove", CODE, "y", store)
    assert code == 0
    ask.assert_called_once()
    assert [p for p in store.docs if p.startswith(f"polls/{CODE}")] == []
    assert "polls/otherpoll222" in store.docs
    assert "polls/otherpoll222/reports/z" in store.docs


@pytest.mark.parametrize("action", ["restore", "remove"])
@pytest.mark.parametrize("answer", ["", "n", "yes please", None])
def test_nothing_is_written_unless_the_answer_is_y(action, answer):
    store = FakeStore()
    code, ask = run(action, CODE, answer, store)
    assert code == 0
    ask.assert_called_once()
    assert store.log == []


@pytest.mark.parametrize("action", ["restore", "remove"])
def test_an_unknown_poll_is_reported_and_never_prompts(action):
    store = FakeStore()
    code, ask = run(action, "nosuchpoll22", "y", store)
    assert code == 1
    ask.assert_not_called()
    assert store.log == []
