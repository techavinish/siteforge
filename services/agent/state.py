"""The agent's state — everything the graph knows, in one typed object.

LangGraph's core idea: nodes are functions State -> partial State update.
The graph engine merges updates, checkpoints the result after every node,
and routes to the next node. The state IS the agent's working memory —
and because it's checkpointed to Postgres, a conversation can pause for
days (or survive a crash) and resume mid-interview.
"""

from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

Phase = Literal["thinking", "interviewing", "planning", "writing", "critiquing", "done"]


class AgentState(TypedDict):
    # add_messages is a REDUCER: node updates append, never overwrite.
    # This is how multi-turn chat history accumulates safely.
    messages: Annotated[list, add_messages]

    # what the interview has learned about the business (grows each turn)
    brief: dict

    # set by the interview node when the brief has enough to build from
    brief_complete: bool

    # the structured site plan: {"site_name", "theme", "pages": [...]}
    spec: dict

    # rendered copy per page: {"/": "...", "/menu": "...", ...}
    pages: dict

    # critique verdict + revision bookkeeping (max one rewrite pass)
    critique: dict
    revisions: int

    phase: Phase
