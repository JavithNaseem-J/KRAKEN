"""
Planner Node — decomposes a user request into ordered steps.

For the IT helpdesk domain the plan is almost always 1-2 steps:
  Step 1: Retrieve relevant knowledge and reason over it.
  Step 2: Execute action (if needed) or respond directly.

The planner uses the LLM to classify intent and set up context.
It does NOT make action decisions — that is the decider's job.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

import structlog

from services.orchestrator.graph.state import GraphState
from services.orchestrator.llm import get_llm

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You are a planning agent for Xiarch cybersecurity consultancy.

Your job is to read the user's request and produce a short, ordered list of steps
needed to resolve or triage it. Keep plans concise — 1 to 3 steps maximum.

Rules:
- If the user is asking a compliance, SLA, pentest, or policy question → plan to retrieve info and answer.
- If the user wants to update ticket status (escalate, close, request_info) → plan to retrieve info, then execute the write action.
- Return ONLY a numbered list. No headers, no extra text.

Example for a question:
1. Retrieve relevant SLA rules, pentest rules of engagement, or policies.
2. Compose a clear, citation-backed answer.

Example for a ticket update:
1. Retrieve the relevant ticket details.
2. Execute the triage action to update the ticket database.
"""


def planner_node(state: GraphState) -> dict:
    """
    Decompose the user's message into a plan and add it to state.
    Always succeeds — worst case it produces a 1-step generic plan.
    """
    log.info("planner.start", session_id=state.get("session_id"))

    user_message = state.get("user_message", "")

    try:
        llm = get_llm()
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"User request: {user_message}"),
        ])
        raw_plan = response.content.strip()
        # Parse numbered list → list[str]
        steps = [
            line.split(". ", 1)[-1].strip()
            for line in raw_plan.splitlines()
            if line.strip() and line.strip()[0].isdigit()
        ]
        if not steps:
            steps = ["Retrieve relevant knowledge and compose an answer."]

        log.info("planner.done", session_id=state.get("session_id"), steps=len(steps))
        return {
            "plan_steps":   steps,
            "current_step": 0,
            "messages":     [{"role": "user", "content": user_message}],
        }

    except Exception as exc:
        log.error("planner.error", error=str(exc))
        return {
            "plan_steps":   ["Retrieve relevant knowledge and compose an answer."],
            "current_step": 0,
            "error":        str(exc),
            "messages":     [{"role": "user", "content": user_message}],
        }
