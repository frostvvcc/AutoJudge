from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class AttackKnowledgeBase:
    """
    Layer 1: Attack Experience Memory.
    Stores verified findings from completed debates.
    Retrieves similar past attack experiences for new tasks.
    """

    def __init__(self, chromadb_path: str = "./data/chromadb"):
        try:
            import chromadb

            self.client = chromadb.PersistentClient(path=chromadb_path)
            self.collection = self.client.get_or_create_collection(
                name="attack_findings",
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
        except Exception as e:
            logger.warning("%s: %s", "chromadb_init_failed", e)
            self._available = False

    async def store_findings(
        self,
        task: str,
        language: str,
        findings: list[dict],
    ):
        if not self._available:
            return

        for finding in findings:
            if not finding.get("was_accepted", False):
                continue

            doc = (
                f"Task: {task}\n"
                f"Category: {finding.get('category', 'unknown')}\n"
                f"Issue: {finding.get('description', '')}\n"
                f"Severity: {finding.get('severity', 'medium')}\n"
                f"Fix: {finding.get('fix_applied', '')}"
            )

            finding_id = f"finding_{uuid.uuid4().hex[:12]}"

            try:
                self.collection.add(
                    documents=[doc],
                    metadatas=[
                        {
                            "category": finding.get("category", "unknown"),
                            "severity": finding.get("severity", "medium"),
                            "attacker": finding.get("attacker", "unknown"),
                            "language": language,
                        }
                    ],
                    ids=[finding_id],
                )
            except Exception as e:
                logger.warning("%s: %s", "store_finding_failed", e)

    async def retrieve_relevant(
        self, task: str, top_k: int = 5
    ) -> list[dict]:
        if not self._available:
            return []

        try:
            results = self.collection.query(
                query_texts=[task],
                n_results=top_k,
            )

            if not results["documents"] or not results["documents"][0]:
                return []

            return [
                {
                    "content": doc,
                    "category": meta.get("category", "unknown"),
                    "severity": meta.get("severity", "medium"),
                }
                for doc, meta in zip(
                    results["documents"][0], results["metadatas"][0]
                )
            ]
        except Exception as e:
            logger.warning("%s: %s", "retrieve_failed", e)
            return []

    def build_experience_prompt(self, experiences: list[dict]) -> str:
        if not experiences:
            return ""

        lines = [
            "以下是历史上类似任务常见的问题，请重点关注但不限于此："
        ]
        for i, exp in enumerate(experiences, 1):
            lines.append(
                f"  {i}. [{exp['severity']}] {exp['content']}"
            )

        return "\n".join(lines)
