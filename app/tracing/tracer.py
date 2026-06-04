from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


def setup_langsmith():
    """Configure LangSmith tracing via environment variables."""
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true":
        logger.info(
            "langsmith_enabled",
            project=os.getenv("LANGCHAIN_PROJECT", "autojudge"),
        )
    else:
        logger.info("langsmith_disabled")
