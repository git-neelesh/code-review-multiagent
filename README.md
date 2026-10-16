# Commit Security Review with Google ADK

This project implements a simple 4-agent Google ADK workflow for reviewing a git commit for likely security issues.

Architecture
- RepoFetchAgent: fetches repo and commit metadata
- SecurityReviewAgent: identifies likely security findings
- SummaryDecisionAgent: creates a summary and pauses for approval via ToolContext
- IssueReportAgent: creates or rejects the GitHub issue and returns the final report

The main flow is a SequentialAgent, which is the best fit for your ordered pipeline.

Project structure
- `commit_reviewer/agent_workflow.py`: ADK agent definitions and sequential workflow
- `commit_reviewer/db.py`: lightweight in-memory session store
- `app/main.py`: FastAPI server endpoints
- `requirements.txt`: dependency list

Requirements
- Python 3.11+
- Google ADK and MCP Python SDK (installed from `requirements.txt`)
- GitHub Copilot MCP access and a GitHub token with repository read and issue write permissions

Setup
1. Create and activate a virtual environment:

```bash
cd /Users/neelesh/PycharmProjects/WelcomeScreen
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. If using a real Google API model, set credentials:

```bash
export GOOGLE_API_KEY="YOUR_API_KEY"
# or
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
```

4. Configure the GitHub MCP token as an environment variable. Do not commit the token:

```bash
export GITHUB_TOKEN="YOUR_GITHUB_TOKEN"
```

The agents connect to `https://api.githubcopilot.com/mcp/` by default. Set
`MCP_SERVER_URL` only if you use a different MCP endpoint. The MCP request uses
`X-MCP-Toolsets: all` and writable mode; ADK tool filters expose only
`get_commit`, `get_file_contents`, and `pull_request_read` to the fetch agent,
and only `create_issue` to the report agent. The GitHub server's `get_diff`
operation is part of `pull_request_read` and retrieves pull-request diffs;
for a commit SHA, the fetch agent uses `get_commit` and reads changed files
at that SHA where needed. Issue creation also requires ADK tool confirmation.

Run the server

```bash
cd /Users/neelesh/PycharmProjects/WelcomeScreen
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open:
- http://localhost:8000/docs

Endpoints
- POST /api/v1/assistant
  - Sends a message to the `helpful_assistant` ADK agent.
  - Body:
    ```json
    {
      "message": "What is Google ADK?"
    }
    ```
  - Returns the agent response.

- POST /api/v1/mcp/verify
  - Checks GitHub MCP connectivity by fetching a commit and its changed files.
  - Body:
    ```json
    {
      "repo": "https://github.com/org/repo",
      "commit_sha": "abc123def456"
    }
    ```
  - Returns the repository, requested commit SHA, and the fetch agent's response.

- POST /api/v1/reviews
  - Body:
    ```json
    {
      "repo": "https://github.com/org/repo",
      "commit_sha": "abc123def456",
      "initiator": "user1"
    }
    ```
  - Returns a session id and current status

- GET /api/v1/reviews/{session_id}
  - Returns the review session state

- POST /api/v1/reviews/{session_id}/resume
  - Body:
    ```json
    {
      "action": "accept",
      "edits": {}
    }
    ```

Notes
- This POC intentionally avoids `session*.json` files and uses in-memory state only.
- Memory and testing are intentionally deferred for later.
- The issue agent is instructed to create an issue only when an explicit accept decision is available.
- The current API resume endpoint updates session state but does not resume the ADK runner; the human approval/resume lifecycle still needs implementation before issue creation can run end-to-end.

Example curl

```bash
curl -X POST "http://localhost:8000/api/v1/reviews" \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "https://github.com/example/project",
    "commit_sha": "abcdef123456",
    "initiator": "demo-user"
  }'
```
