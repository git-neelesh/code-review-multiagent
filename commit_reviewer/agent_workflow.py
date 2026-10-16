"""Simple 4-agent ADK workflow for commit security review.

Architecture:
- SequentialAgent root
  - RepoFetchAgent
  - SecurityReviewAgent
  - SummaryDecisionAgent (pauses with ToolContext)
  - IssueReportAgent

This keeps the workflow simple and aligned with the intended 4-step review.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools.tool_context import ToolContext


MODEL_NAME = "gemini-3.5-flash-lite"


def _safe_json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def request_issue_approval(issue: Dict[str, Any], tool_context: ToolContext):
    """Pause the workflow and wait for user approval before creating a GitHub issue."""
    tool_context.state["proposed_issue"] = issue
    tool_context.state["status"] = "AWAITING_USER_DECISION"
    tool_context.state["decision_required"] = True
    tool_context.state["review_stage"] = "approval_wait"
    return {
        "status": "paused",
        "message": "Please accept or reject the GitHub issue draft.",
        "issue": issue,
    }


class RepoFetchAgent(LlmAgent):
    def __init__(self):
        super().__init__(
            name="repo_fetch_agent",
            description="Fetch repo metadata and changed code for a commit.",
            model=Gemini(model=MODEL_NAME),
            instruction=(
                "You are a repo fetch agent. Given a repo and commit id, return JSON with: "
                "repo, commit_sha, files_changed, summary, diff_excerpt. "
                "Return valid JSON only."
            ),
        )


class SecurityReviewAgent(LlmAgent):
    def __init__(self):
        super().__init__(
            name="security_review_agent",
            description="Analyze the commit for security issues.",
            model=Gemini(model=MODEL_NAME),
            instruction=(
                "You are a security reviewer. Given repo metadata and changed source code, "
                "detect likely security issues. Return JSON with a 'findings' array. "
                "Each finding must include: id, type, severity, file, line, description, evidence. "
                "Return valid JSON only."
            ),
        )


class SummaryDecisionAgent(LlmAgent):
    def __init__(self):
        super().__init__(
            name="summary_decision_agent",
            description="Summarize findings and pause for user approval before creating a GitHub issue.",
            model=Gemini(model=MODEL_NAME),
            tools=[request_issue_approval],
            instruction=(
                "You are the review summarizer. Given the security findings, create a concise summary "
                "and a proposed GitHub issue draft. Use the request_issue_approval tool to pause the flow "
                "after creating the issue draft, and pass the issue JSON as its argument. "
                "Return valid JSON only when the tool is not needed."
            ),
        )


class IssueReportAgent(LlmAgent):
    def __init__(self):
        super().__init__(
            name="issue_report_agent",
            description="Create the GitHub issue if approved and produce the final report.",
            model=Gemini(model=MODEL_NAME),
            instruction=(
                "You are the final issue/report agent. Given the review findings and user decision, "
                "return a final JSON report with: repo, commit_sha, findings, decision, issue_url, summary. "
                "If the decision is reject, set issue_url to null and explain the rejection. Return valid JSON only."
            ),
        )


def build_review_pipeline() -> SequentialAgent:
    repo_fetch_agent = RepoFetchAgent()
    security_agent = SecurityReviewAgent()
    summary_agent = SummaryDecisionAgent()
    issue_agent = IssueReportAgent()

    return SequentialAgent(
        name="commit_review_pipeline",
        description="Sequential workflow for commit-based security review and GitHub issue creation.",
        sub_agents=[repo_fetch_agent, security_agent, summary_agent, issue_agent],
    )


def run_review_pipeline(repo: str, commit_sha: str, user_id: str = "user") -> Dict[str, Any]:
    root_agent = build_review_pipeline()
    runner = InMemoryRunner(agent=root_agent)
    payload = _safe_json_text({"repo": repo, "commit_sha": commit_sha})
    events = runner.run_debug(payload, user_id=user_id, session_id=f"review-{commit_sha[:12]}")
    return {"events": events, "status": "ok"}
