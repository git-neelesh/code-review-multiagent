"""Simple in-memory session store for the ADK review workflow.

This keeps the POC small and avoids file-backed session state.
"""

import uuid
from typing import Any, Dict, Optional


class DatabaseSessionService:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, repo: str, commit_sha: str, initiator: str) -> str:
        session_id = str(uuid.uuid4())
        session = {
            "id": session_id,
            "repo": repo,
            "commit_sha": commit_sha,
            "initiator": initiator,
            "status": "PENDING",
            "next_step": "repo_fetch_agent",
            "findings": [],
            "proposed_issue": None,
            "user_decision": None,
            "final_report": None,
            "model_invocations": [],
            "pending_action": None,
            "state": {},
        }
        self._sessions[session_id] = session
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)

    def update_session(self, session_id: str, patch: Dict[str, Any]) -> None:
        if session_id not in self._sessions:
            raise KeyError("session not found")
        self._sessions[session_id].update(patch)

    def append_findings(self, session_id: str, findings):
        if session_id not in self._sessions:
            raise KeyError("session not found")
        self._sessions[session_id].setdefault("findings", [])
        self._sessions[session_id]["findings"].extend(findings)

    def set_proposed_issue(self, session_id: str, issue: Dict[str, Any]) -> None:
        self.update_session(session_id, {"proposed_issue": issue, "status": "AWAITING_USER_DECISION"})

    def set_pending_action(self, session_id: str, action: Dict[str, Any]) -> None:
        self.update_session(session_id, {"pending_action": action, "status": "AWAITING_USER_DECISION"})

    def clear_pending_action(self, session_id: str) -> None:
        self.update_session(session_id, {"pending_action": None})

    def add_model_invocation(self, session_id: str, invocation: Dict[str, Any]) -> None:
        if session_id not in self._sessions:
            raise KeyError("session not found")
        self._sessions[session_id].setdefault("model_invocations", []).append(invocation)

    def set_state(self, session_id: str, key: str, value: Any) -> None:
        if session_id not in self._sessions:
            raise KeyError("session not found")
        self._sessions[session_id].setdefault("state", {})[key] = value
