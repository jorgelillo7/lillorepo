#!/usr/bin/env python3
"""Keep only minerals someone can stand behind (ADC, be-water-app).

A mineral is *backed* when it was read off a photographed label
(`verified_fields`) or carries a recorded source (`manual`: a contributor
submitted it). Everything else — values marked `manufacturer` by the retired
seed dataset, and values nobody recorded a source for — is unbacked, and ends
in one of two ways:

- **The same label backs it.** An analysis entry whose ficha shares its label
  photo, and holds the same value marked as read off that label: the value is
  real and only the mark is wrong, so it becomes label-verified.
- **Nothing backs it.** The value is removed. On a ficha the previous document
  is snapshotted to `water_revisions` first, so `revert_water` can undo it.

    bazel run //packages/be_water/scripts:purge_unbacked_minerals  # dry run
    bazel run //packages/be_water/scripts:purge_unbacked_minerals -- --apply
"""

import argparse
import os

os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from core.sdk import firestore  # noqa: E402
from packages.be_water.web import repository  # noqa: E402
from packages.be_water.web.domain import Water  # noqa: E402

MANUFACTURER = "manufacturer"


def unbacked(doc: dict) -> list[str]:
    """Minerals neither label-verified nor carrying a real source."""
    verified = set(doc.get("verified_fields") or [])
    sources = doc.get("sources") or {}
    return sorted(
        field
        for field in (doc.get("minerals") or {})
        if field not in verified and sources.get(field) in (None, MANUFACTURER)
    )


def plan(doc: dict, backing: dict | None) -> tuple[dict, list[str], list[str]]:
    """`(new_doc, verified, removed)` for one document.

    `backing` is the ficha an analysis entry belongs to (None for a ficha): a
    field it verified against the same label photo, at the same value, is
    real data with the wrong mark.
    """
    sources = dict(doc.get("sources") or {})
    minerals = dict(doc.get("minerals") or {})
    verified_fields = list(doc.get("verified_fields") or [])
    verified, removed = [], []
    for field in unbacked(doc):
        sources.pop(field, None)
        same_label = (
            backing is not None
            and backing.get("label_photo_url")
            and backing.get("label_photo_url") == doc.get("label_photo_url")
            and field in (backing.get("verified_fields") or [])
            and (backing.get("minerals") or {}).get(field) == minerals.get(field)
        )
        if same_label:
            verified_fields.append(field)
            verified.append(field)
        else:
            minerals.pop(field, None)
            removed.append(field)
    new_doc = dict(
        doc,
        sources=sources,
        minerals=minerals,
        verified_fields=sorted(set(verified_fields)),
    )
    return new_doc, verified, removed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()

    waters = dict(firestore.list_documents(repository.WATERS))
    targets = [(repository.WATERS, doc_id, doc, None) for doc_id, doc in waters.items()]
    targets += [
        (repository.ANALYSES, doc_id, doc, waters.get(doc_id.split("__")[0]))
        for doc_id, doc in firestore.list_documents(repository.ANALYSES)
    ]

    touched = 0
    for collection, doc_id, doc, backing in targets:
        stale_marks = MANUFACTURER in (doc.get("sources") or {}).values()
        if not unbacked(doc) and not stale_marks:
            continue
        touched += 1
        new_doc, verified, removed = plan(doc, backing)
        print(f"{collection}/{doc_id}")
        for field in verified:
            print(f"  ✓ {field} = {doc['minerals'].get(field)}  → leído de la etiqueta")
        for field in removed:
            print(f"  ✗ {field} = {doc['minerals'].get(field)}  → eliminado")
        if not args.apply:
            continue
        if collection == repository.WATERS and removed:
            repository.save_revision(
                Water.from_firestore(doc_id, doc),
                replaced_by="purge_unbacked_minerals",
                reason="unbacked_values_removed",
            )
        firestore.set_document(collection, doc_id, new_doc)

    if not touched:
        print("Every mineral left is backed by a label or a recorded source.")
    elif not args.apply:
        print(f"\nDry run: {touched} document(s). Re-run with --apply to write.")


if __name__ == "__main__":
    main()
