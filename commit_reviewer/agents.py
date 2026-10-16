"""Agent wrappers that use the google-adk package for LLM-driven steps.

This file creates agents by instantiating ADK `Agent` objects for the
LLM-driven steps (commit collector, static analysis, LLM review, issue
creation orchestration). The actual pause/resume and persistence is still
managed by the local DatabaseSessionService so the pipeline can checkpoint
between steps.

NOTE: This POC assumes `google-adk` is installed (package name
`google-adk>=2.12.0`). If imports fail the code raises informative errors.
"""
from typing import Any, Dict, Optional
import json
import traceback

try:
    from google.adk.agents import Agent
    from google.adk.models.google_llm import Gemini
    from google.adk.runners import InMemoryRunner
    # Attempt to import MCP/GitHub tool names; try several plausible names
    try:
        from google.adk.tools import GitHubMCP as _GitHubMCP  # type: ignore
        GitHubMCP = _GitHubMCP
    except Exception:
        GitHubMCP = None
    try:
        from google.adk.tools import GitHubMCPTool as _GitHubMCPTool  # type: ignore
        GitHubMCPTool = _GitHubMCPTool
    except Exception:
        GitHubMCPTool = None
except Exception:
    # Re-raise with a clearer message to the user
    tb = traceback.format_exc()
    raise ImportError(
        "google-adk imports failed. Ensure google-adk is installed and available.\n"
        "Original import error:\n" + tb
    )


def _run_adk_agent(agent: Agent, prompt: str) -> Dict[str, Any]:
    """Run a google-adk Agent with an InMemoryRunner and return parsed JSON.

    The agent is expected to return JSON text. We attempt to parse it; if
    parsing fails we return the raw text under the 'raw' key.
    """
    runner = InMemoryRunner(agent=agent)
    resp = runner.run_debug(prompt)
    # If run_debug is async in the installed ADK, this will return a coroutine
    # or a future-like. Handle both sync and async shapes.
    if hasattr(resp, "__await__"):
        import asyncio

        resp = asyncio.get_event_loop().run_until_complete(resp)

    # Normalize to string then try JSON
    text = str(resp)
    try:
        parsed = json.loads(text)
        return {"json": parsed, "raw": text}
    except Exception:
        return {"raw": text}


class CommitCollectorAgent:
    """ADK-backed agent that collects commit metadata.

    For the POC this agent asks the model to summarize commit info given a
    repo and commit sha. In production you would implement a true Git fetcher
    tool rather than prompting the model to invent diffs.
    """

    def __init__(self, model_name: str = "gemini-3.5-flash-lite"):
        self.agent = Agent(
            name="commit_collector",
            model=Gemini(model=model_name),
            instruction=(
                "You are a commit metadata collector. Given repo and commit sha, "
                "return a JSON object with keys: files_changed (array of paths) "
                "and summary (string). Respond with valid JSON only."
            ),
        )

    def run(self, session: Dict[str, Any], db: Any, tools: Any) -> Dict[str, Any]:
        prompt = json.dumps({"repo": session["repo"], "commit_sha": session["commit_sha"]})
        result = _run_adk_agent(self.agent, prompt)
        # persist best-effort
        if "json" in result:
            db.update_session(session["id"], {"commit_info": result["json"], "next_step": "static_analyzer", "status": "RUNNING"})
        else:
            db.update_session(session["id"], {"commit_info": {"summary": result.get("raw", "")}, "next_step": "static_analyzer", "status": "RUNNING"})
        return session


class StaticAnalyzerAgent:
    """ADK-backed static analysis agent.

    This agent receives commit_info and returns a JSON array of findings.
    In a real system you should call real static analysis tools; the ADK-based
    agent can be used to summarize or triage findings.
    """

    def __init__(self, model_name: str = "gemini-3.5-flash-lite"):
        self.agent = Agent(
            name="static_analyzer",
            model=Gemini(model=model_name),
            instruction=(
                "You are a static analyzer assistant. Given a commit summary and "
                "files changed, return a JSON array named findings. Each finding must"
                " include: id, type, file, line (optional), description, severity. "
                "Respond with valid JSON only."
            ),
        )

    def run(self, session: Dict[str, Any], db: Any, tools: Any) -> Dict[str, Any]:
        s = db.get_session(session["id"])
        prompt = json.dumps({"commit_info": s.get("commit_info", {})})
        result = _run_adk_agent(self.agent, prompt)
        if "json" in result and isinstance(result["json"], dict) and "findings" in result["json"]:
            findings = result["json"]["findings"]
        else:
            # fallback: empty findings
            findings = []
        db.append_findings(session["id"], findings)
        db.update_session(session["id"], {"next_step": "llm_reviewer"})
        return session


class LLMReviewerAgent:
    """LLM agent that turns findings into proposed GitHub issues.

    This agent produces a JSON array of proposed issues with keys: index,
    title, body, labels, severity.
    """

    def __init__(self, model_name: str = "gemini-3.5-flash-lite"):
        self.agent = Agent(
            name="llm_reviewer",
            model=Gemini(model=model_name),
            instruction=(
                "You are a security reviewer. Given a list of findings, return a JSON "
                "array `issues` where each element has: index, title, body, labels, severity. "
                "Return valid JSON only."
            ),
        )

    def run(self, session: Dict[str, Any], db: Any, tools: Any) -> Dict[str, Any]:
        s = db.get_session(session["id"])
        prompt = json.dumps({"findings": s.get("findings", [])})
        result = _run_adk_agent(self.agent, prompt)
        if "json" in result and isinstance(result["json"], dict) and "issues" in result["json"]:
            proposed = result["json"]["issues"]
        elif "json" in result and isinstance(result["json"], list):
            proposed = result["json"]
        else:
            # attempt to parse raw text for JSON
            try:
                proposed = json.loads(result.get("raw", "[]"))
            except Exception:
                proposed = []

        db.set_proposed_issues(session["id"], proposed)
        db.add_model_invocation(session["id"], {"invocation_id": result.get("raw", ""), "model": "gemini", "finish_reason": "success"})
        db.update_session(session["id"], {"next_step": "confirmation"})
        return session


class ConfirmationAgent:
    """Create a pending action and pause for confirmation. The actual confirmation
    is provided via the external resume API which updates the DB and restarts
    the runner from the next step.
    """

    def run(self, session: Dict[str, Any], db: Any, tools: Any) -> Dict[str, Any]:
        s = db.get_session(session["id"])
        proposed = s.get("proposed_issues", [])
        action = {"id": f"action-{session['id']}", "type": "confirmation", "payload": {"proposed_issues": proposed}, "resume_token": f"token-{session['id']}"}
        db.set_pending_action(session["id"], action)
        return session


class IssueCreatorAgent:
    """Create issues using the ADK-provided GitHub MCP tool.

    This agent expects `tools` to expose an attribute `github_mcp` that is an
    instance of the ADK MCP tool wrapper. The exact tool class name may vary
    between ADK versions; the app should import the correct symbol.
    """

    def run(self, session: Dict[str, Any], db: Any, tools: Any) -> Dict[str, Any]:
        s = db.get_session(session["id"])
        proposed = s.get("proposed_issues", [])
        created = []
        mcp = getattr(tools, "github_mcp", None)
        if mcp is None:
            raise RuntimeError("GitHub MCP tool not available in tools; ensure google.adk.tools provides MCP integration")

        for issue in proposed:
            # try to call the MCP tool's create method; exact signature may vary
            if hasattr(mcp, "create_issue"):
                resp = mcp.create_issue(repo=s["repo"], title=issue["title"], body=issue["body"], labels=issue.get("labels", []))
            elif hasattr(mcp, "create"):
                resp = mcp.create(repo=s["repo"], title=issue["title"], body=issue["body"], labels=issue.get("labels", []))
            else:
                raise RuntimeError("MCP tool does not expose a known creation method")
            created.append(resp)

        db.update_session(session["id"], {"status": "ISSUES_CREATED", "issues": created, "next_step": None})
        db.clear_pending_action(session["id"])
        return session

