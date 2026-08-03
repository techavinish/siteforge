"""Registers the daily evaluation schedule with Temporal — the cron of the
blueprint, owned by the orchestrator. Idempotent."""

import asyncio

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleSpec,
)


async def main() -> None:
    client = await Client.connect("localhost:7233")
    try:
        await client.create_schedule(
            "daily-site-evaluation",
            Schedule(
                action=ScheduleActionStartWorkflow(
                    "EvaluateSitesWorkflow",
                    id="eval-sites-scheduled",
                    task_queue="siteforge",
                ),
                spec=ScheduleSpec(cron_expressions=["30 3 * * *"]),  # 03:30 daily
            ),
        )
        print("schedule created: daily-site-evaluation @ 03:30")
    except ScheduleAlreadyRunningError:
        print("schedule already exists")


if __name__ == "__main__":
    asyncio.run(main())
