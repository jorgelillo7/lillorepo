#!/usr/bin/env python3
"""Remove every "fabricante" source from be_water's Firestore (ADC, be-water-app).

A mineral marked `manufacturer` came from the retired seed dataset, not from
the bottle anyone photographed. Each one ends in one of two ways:

- **The same label backs it.** An analysis entry whose ficha shares its label
  photo, and holds the same value marked as read off that label: the value is
  real and only the mark is wrong, so it becomes label-verified.
- **Nothing backs it.** The value is removed. On a ficha the previous document
  is snapshotted to `water_revisions` first, so `revert_water` can undo it.

    bazel run //packages/be_water/scripts:purge_manufacturer_sources  # dry run
    bazel run //packages/be_water/scripts:purge_manufacturer_sources -- --apply
"""

import argparse
import os

os.environ.setdefault("FIRESTORE_PROJECT", "be-water-app")

from core.sdk import firestore  # noqa: E402
from packages.be_water.web import repository  # noqa: E402
from packages.be_water.web.domain import Water  # noqa: E402

MANUFACTURER = "manufacturer"


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
    for field in sorted(k for k, v in sources.items() if v == MANUFACTURER):
        del sources[field]
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
        if MANUFACTURER not in (doc.get("sources") or {}).values():
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
                replaced_by="purge_manufacturer_sources",
                reason="unbacked_values_removed",
            )
        firestore.set_document(collection, doc_id, new_doc)

    if not touched:
        print("No 'fabricante' source left anywhere.")
    elif not args.apply:
        print(f"\nDry run: {touched} document(s). Re-run with --apply to write.")


if __name__ == "__main__":
    main()
