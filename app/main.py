"""FastAPI app exposing the simple 4-agent commit review workflow."""
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from commit_reviewer.db import DatabaseSessionService
from commit_reviewer.agent_workflow import RepoFetchAgent, run_review_pipeline
from commit_reviewer.helpful_assistant import root_agent as helpful_assistant
from google.adk.runners import InMemoryRunner

app = FastAPI()
DB = DatabaseSessionService()


class StartRequest(BaseModel):
    repo: str
    commit_sha: str
    initiator: str = "cli-user"


class ResumeRequest(BaseModel):
    action: str
    edits: Optional[dict] = None


class AssistantRequest(BaseModel):
    message: str


class McpVerificationRequest(BaseModel):
    repo: str
    commit_sha: str
    initiator: str = "mcp-verification"


@app.post("/api/v1/assistant")
async def test_helpful_assistant(req: AssistantRequest):
    runner = InMemoryRunner(agent=helpful_assistant)
    response = await runner.run_debug(req.message)
    return {"response": str(response)}


@app.post("/api/v1/mcp/verify")
async def verify_mcp_commit(req: McpVerificationRequest):
    """Check MCP connectivity by fetching a commit and its changed files."""
    try:
        runner = InMemoryRunner(agent=RepoFetchAgent())
        prompt = (
            f"Repository: {req.repo}\n"
            f"Commit SHA: {req.commit_sha}\n"
            "Use the GitHub MCP get_commit tool to retrieve this commit. "
            "Return the commit SHA and changed file paths from the tool response. "
            "Do not guess if the commit cannot be retrieved."
        )
        response = await runner.run_debug(
            prompt,
            user_id=req.initiator,
            session_id=f"mcp-check-{req.commit_sha[:12]}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"MCP commit verification failed: {exc}",
        ) from exc
    response_text = next(
        (
            part.text
            for event in reversed(response)
            for part in reversed(event.content.parts)
            if getattr(part, "text", None)
        ),
        str(response),
    )
    return {
        "repo": req.repo,
        "commit_sha": req.commit_sha,
        "response": response_text,
    }


@app.post("/api/v1/reviews")
async def start_review(req: StartRequest):
    session_id = DB.create_session(req.repo, req.commit_sha, req.initiator)
    session = DB.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=500, detail="failed to create session")
    try:
        result = await run_review_pipeline(req.repo, req.commit_sha, user_id=req.initiator)
        session["status"] = "RUNNING"
        session["state"]["pipeline_result"] = result
    except Exception as exc:
        session["status"] = "FAILED"
        session["state"]["error"] = str(exc)
    return {"session_id": session_id, "status": session["status"]}


@app.get("/api/v1/reviews/{session_id}")
def get_review(session_id: str):
    session = DB.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@app.post("/api/v1/reviews/{session_id}/resume")
async def resume_review(session_id: str, req: ResumeRequest):
    session = DB.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    if session.get("status") != "AWAITING_USER_DECISION":
        raise HTTPException(status_code=400, detail="session is not awaiting user decision")

    session["user_decision"] = req.action
    session["status"] = "RESUMED"
    session["state"]["resume_action"] = req.action
    session["state"]["resume_edits"] = req.edits or {}
    return {"session_id": session_id, "status": "RESUMED", "decision": req.action}
