"""FastAPI app exposing the simple 4-agent commit review workflow."""
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from commit_reviewer.db import DatabaseSessionService
from commit_reviewer.agent_workflow import run_review_pipeline

app = FastAPI()
DB = DatabaseSessionService()


class StartRequest(BaseModel):
    repo: str
    commit_sha: str
    initiator: Optional[str] = "cli-user"


class ResumeRequest(BaseModel):
    action: str
    edits: Optional[dict] = None


@app.post("/api/v1/reviews")
async def start_review(req: StartRequest):
    session_id = DB.create_session(req.repo, req.commit_sha, req.initiator)
    session = DB.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=500, detail="failed to create session")
    try:
        result = run_review_pipeline(req.repo, req.commit_sha, user_id=req.initiator)
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
