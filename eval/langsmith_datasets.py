"""
LangSmith dataset management: upload and version-control evaluation datasets.

Replaces hand-rolled JSON file loading with LangSmith's versioned dataset
infrastructure, enabling experiment tracking and reproducible comparisons.

Usage:
    python -m eval.langsmith_datasets upload
    python -m eval.langsmith_datasets list
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from langsmith import Client

logger = logging.getLogger(__name__)

TASKS_PATH = Path(__file__).parent / "datasets" / "tasks.json"
DATASET_NAME = "autojudge-eval-tasks"
DATASET_DESCRIPTION = (
    "Code generation tasks with known security/performance/correctness issues "
    "for evaluating AutoJudge debate effectiveness."
)


def _load_local_tasks() -> list[dict]:
    with open(TASKS_PATH) as f:
        return json.load(f)


def upload_dataset(client: Client | None = None) -> str:
    """Upload eval/datasets/tasks.json to LangSmith as a versioned dataset.

    Returns the dataset ID.
    """
    client = client or Client()
    tasks = _load_local_tasks()

    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        dataset = existing[0]
        logger.info(
            "Dataset '%s' already exists (id=%s), updating examples...",
            DATASET_NAME, dataset.id,
        )
    else:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description=DATASET_DESCRIPTION,
        )
        logger.info("Created dataset '%s' (id=%s)", DATASET_NAME, dataset.id)

    for task in tasks:
        client.create_example(
            dataset_id=dataset.id,
            inputs={
                "task": task["task"],
                "language": task.get("language", "python"),
                "framework": task.get("framework"),
                "difficulty": task.get("difficulty", "medium"),
            },
            outputs={
                "known_issues": task.get("known_issues", []),
                "task_id": task["id"],
            },
        )

    logger.info("Uploaded %d examples to dataset '%s'", len(tasks), DATASET_NAME)
    return str(dataset.id)


def list_datasets(client: Client | None = None) -> list[dict]:
    """List all AutoJudge-related datasets in LangSmith."""
    client = client or Client()
    datasets = list(client.list_datasets())
    return [
        {
            "name": ds.name,
            "id": str(ds.id),
            "description": ds.description,
            "example_count": ds.example_count,
        }
        for ds in datasets
        if "autojudge" in (ds.name or "").lower()
    ]


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    action = sys.argv[1] if len(sys.argv) > 1 else "upload"

    if action == "upload":
        dataset_id = upload_dataset()
        print(f"Dataset ID: {dataset_id}")
    elif action == "list":
        for ds in list_datasets():
            print(f"  {ds['name']} ({ds['example_count']} examples) — {ds['id']}")
    else:
        print(f"Unknown action: {action}. Use 'upload' or 'list'.")
