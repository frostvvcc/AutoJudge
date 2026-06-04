from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class ResourceManager:
    """
    System-level concurrency control:
    - Max N concurrent debate sessions (constrained by LLM API rate limits)
    - LLM call-level semaphore shared across all sessions
    """

    def __init__(
        self,
        max_concurrent_debates: int = 5,
        max_concurrent_llm_calls: int = 20,
    ):
        self.debate_semaphore = asyncio.Semaphore(max_concurrent_debates)
        self.llm_semaphore = asyncio.Semaphore(max_concurrent_llm_calls)

    @asynccontextmanager
    async def acquire_debate_slot(self, request_id: str = ""):
        try:
            acquired = await asyncio.wait_for(
                self.debate_semaphore.acquire(), timeout=30
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                "All debate slots are busy. Please retry later."
            )

        try:
            yield
        finally:
            self.debate_semaphore.release()

    @asynccontextmanager
    async def acquire_llm_slot(self):
        await self.llm_semaphore.acquire()
        try:
            yield
        finally:
            self.llm_semaphore.release()
