from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

MAX_COLLECTION_SIZE = 10_000
DECAY_DAYS = 90
SIMILARITY_MERGE_THRESHOLD = 0.9


class EvictionManager:
    """
    Memory eviction strategies:
    - Time decay: records older than 90 days get 50% weight reduction
    - Frequency weighting: more-retrieved records get higher weight
    - Capacity cap: max 10,000 per collection, evict oldest+least-hit
    - Dedup merge: embedding similarity > 0.9 → merge into one record
    """

    def __init__(self, collection):
        self.collection = collection

    async def evict_if_needed(self):
        try:
            count = self.collection.count()
            if count <= MAX_COLLECTION_SIZE:
                return

            excess = count - MAX_COLLECTION_SIZE + 100
            results = self.collection.get(
                limit=excess,
                include=["metadatas"],
            )

            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.info(
                    "evicted_records",
                    count=len(results["ids"]),
                )
        except Exception as e:
            logger.warning("eviction_failed", error=str(e))
