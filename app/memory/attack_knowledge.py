from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

REBUTTAL_DECAY_THRESHOLD = 3
DISTRIBUTION_ALERT_RATIO = 0.4


class AttackKnowledgeBase:
    """
    Layer 1: Attack Experience Memory.
    Stores verified findings from completed debates.
    Retrieves similar past attack experiences for new tasks.

    Feedback loop protection:
    - confidence: tool-verified findings (0.9) rank higher than LLM-only (0.6)
    - rebuttal_count: findings repeatedly rebutted by Coder decay toward zero weight
    - Distribution monitoring via check_distribution()
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
        session_id: str | None = None,
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

            tool_verified = finding.get("tool_verified", False)
            confidence = 0.9 if tool_verified else 0.6

            meta = {
                "category": finding.get("category", "unknown"),
                "severity": finding.get("severity", "medium"),
                "attacker": finding.get("attacker", "unknown"),
                "language": language,
                "confidence": confidence,
                "rebuttal_count": 0,
            }
            if session_id:
                meta["session_id"] = session_id

            try:
                self.collection.add(
                    documents=[doc],
                    metadatas=[meta],
                    ids=[finding_id],
                )
            except Exception as e:
                logger.warning("%s: %s", "store_finding_failed", e)

    async def record_rebuttal(self, finding_id: str):
        if not self._available:
            return
        try:
            result = self.collection.get(ids=[finding_id], include=["metadatas"])
            if result["metadatas"]:
                meta = result["metadatas"][0]
                meta["rebuttal_count"] = meta.get("rebuttal_count", 0) + 1
                self.collection.update(ids=[finding_id], metadatas=[meta])
        except Exception as e:
            logger.warning("%s: %s", "record_rebuttal_failed", e)

    async def retrieve_relevant(
        self, task: str, top_k: int = 5
    ) -> list[dict]:
        if not self._available:
            return []

        try:
            results = self.collection.query(
                query_texts=[task],
                n_results=top_k * 2,
            )

            if not results["documents"] or not results["documents"][0]:
                return []

            items = []
            distances = results.get("distances", [[]])[0]
            for i, (doc, meta) in enumerate(
                zip(results["documents"][0], results["metadatas"][0])
            ):
                rebuttal_count = meta.get("rebuttal_count", 0)
                if rebuttal_count >= REBUTTAL_DECAY_THRESHOLD:
                    continue

                confidence = meta.get("confidence", 0.6)
                raw_similarity = (1 - distances[i]) if i < len(distances) else 0
                weighted_score = raw_similarity * confidence

                items.append({
                    "content": doc,
                    "category": meta.get("category", "unknown"),
                    "severity": meta.get("severity", "medium"),
                    "session_id": meta.get("session_id"),
                    "similarity": round(weighted_score * 100),
                    "confidence": confidence,
                })

            items.sort(key=lambda x: x["similarity"], reverse=True)
            return items[:top_k]
        except Exception as e:
            logger.warning("%s: %s", "retrieve_failed", e)
            return []

    async def check_distribution(self) -> dict[str, float]:
        if not self._available:
            return {}
        try:
            total = self.collection.count()
            if total == 0:
                return {}
            all_data = self.collection.get(include=["metadatas"])
            counts: dict[str, int] = {}
            for meta in all_data["metadatas"]:
                cat = meta.get("category", "unknown")
                counts[cat] = counts.get(cat, 0) + 1

            distribution = {cat: count / total for cat, count in counts.items()}
            for cat, ratio in distribution.items():
                if ratio > DISTRIBUTION_ALERT_RATIO:
                    logger.warning(
                        "memory_bias_alert category=%s ratio=%.2f total=%d",
                        cat, ratio, total,
                    )
            return distribution
        except Exception as e:
            logger.warning("%s: %s", "check_distribution_failed", e)
            return {}

    def build_experience_prompt(self, experiences: list[dict]) -> str:
        if not experiences:
            return ""

        lines = [
            "以下是历史上类似任务常见的问题，请重点关注但不限于此："
        ]
        for i, exp in enumerate(experiences, 1):
            conf_tag = "🔧" if exp.get("confidence", 0) >= 0.9 else "💭"
            lines.append(
                f"  {i}. {conf_tag} [{exp['severity']}] {exp['content']}"
            )

        return "\n".join(lines)
