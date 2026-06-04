from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


class FixPatternStore:
    """
    Layer 3: Fix Patterns Memory.
    Stores successful fix patterns for common defect types.
    Coder can reference past fixes for similar issues.
    """

    def __init__(self, chromadb_path: str = "./data/chromadb"):
        try:
            import chromadb

            self.client = chromadb.PersistentClient(path=chromadb_path)
            self.collection = self.client.get_or_create_collection(
                name="fix_patterns",
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
        except Exception as e:
            logger.warning("%s: %s", "fix_patterns_init_failed", e)
            self._available = False

    async def store_fix(
        self,
        finding_description: str,
        category: str,
        severity: str,
        fix_code: str,
    ):
        if not self._available or not fix_code:
            return

        doc = (
            f"Issue: {finding_description}\n"
            f"Category: {category}\n"
            f"Fix approach: {fix_code}\n"
            f"Verified: True"
        )

        fix_id = f"fix_{uuid.uuid4().hex[:12]}"

        try:
            self.collection.add(
                documents=[doc],
                metadatas=[
                    {"category": category, "severity": severity}
                ],
                ids=[fix_id],
            )
        except Exception as e:
            logger.warning("%s: %s", "store_fix_failed", e)

    async def retrieve_fixes(
        self, finding_description: str, top_k: int = 3
    ) -> list[str]:
        if not self._available:
            return []

        try:
            results = self.collection.query(
                query_texts=[finding_description],
                n_results=top_k,
            )

            if not results["documents"] or not results["documents"][0]:
                return []

            return results["documents"][0]
        except Exception as e:
            logger.warning("%s: %s", "retrieve_fixes_failed", e)
            return []
