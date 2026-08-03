"""The Temporal worker — polls the task queue and executes workflow +
activity code. Kill it mid-run and restart it: the workflow resumes from
its event history. That demo is the whole point of Phase 5."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from activities import generate_draft, publish_draft
from workflows import GenerateSiteWorkflow

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TASK_QUEUE = "siteforge"


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)
    print(f"worker connected to {TEMPORAL_ADDRESS}, queue={TASK_QUEUE}")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[GenerateSiteWorkflow],
        activities=[generate_draft, publish_draft],
        # our activities are sync functions — they run in this thread pool
        activity_executor=ThreadPoolExecutor(max_workers=4),
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
