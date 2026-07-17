"""One-shot seeder: writes the seed catalog to Firestore (be-water-app).

Idempotent — doc ids are stable slugs, re-running overwrites with the same
data. Run locally with ADC:

    bazel run //packages/be_water/web:seed_local
"""

from core.sdk import firestore
from core.utils import get_logger
from packages.be_water.web import config  # noqa: F401  (sets FIRESTORE_PROJECT)
from packages.be_water.web.domain import Water
from packages.be_water.web.repository import WATERS
from packages.be_water.web.seed_data import SEED_WATERS

logger = get_logger(__name__)


def main() -> None:
    docs = []
    for raw in SEED_WATERS:
        water = Water(
            id=raw["id"],
            name=raw["name"],
            brand=raw.get("brand", raw["name"]),
            spring=raw.get("spring", ""),
            province=raw.get("province", ""),
            community=raw.get("community", ""),
            sparkling=raw.get("sparkling", False),
            minerals=raw.get("minerals", {}),
            added_by="seed",
            verified=False,
        )
        docs.append((water.id, water.to_firestore()))
    written = firestore.batch_write(WATERS, docs)
    logger.info("Seed complete.", extra={"written": written})
    print(f"Seeded {written} waters into '{WATERS}'.")


if __name__ == "__main__":
    main()
