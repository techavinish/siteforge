"""GenerateSiteWorkflow — the durable spine of site generation.

The WORKFLOW is deterministic orchestration: which steps, in what order,
with what retries, and where a human decides. Everything non-deterministic
(LLM calls, APIs, DB writes) lives in ACTIVITIES, which Temporal retries
and can survive worker crashes mid-run.

    generate (activity, retried) ──► wait for `approve` signal ──► publish
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class GenerateSiteWorkflow:
    def __init__(self) -> None:
        self.approved = False
        self.stage = "starting"

    @workflow.run
    async def run(self, thread_id: str, regenerate: bool = True) -> str:
        if regenerate:
            self.stage = "generating"
            await workflow.execute_activity(
                "generate_draft",
                thread_id,
                start_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=10),
                    backoff_coefficient=2.0,
                    maximum_attempts=5,  # rides out rate limits and blips
                ),
            )

        # human-in-the-loop: nothing publishes until the owner says so.
        # the workflow can wait here for DAYS — durably, costing nothing.
        self.stage = "awaiting_approval"
        await workflow.wait_condition(lambda: self.approved, timeout=timedelta(days=3))

        self.stage = "publishing"
        url = await workflow.execute_activity(
            "publish_draft",
            thread_id,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=4),
        )
        self.stage = "done"
        return url

    @workflow.signal
    def approve(self) -> None:
        self.approved = True

    @workflow.query
    def status(self) -> str:
        return self.stage
