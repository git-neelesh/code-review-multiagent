"""GitHub MCP toolsets used by the commit review agents."""

import os

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams


GITHUB_MCP_SERVER_URL = "https://api.githubcopilot.com/mcp/"


def build_github_mcp_toolset(
    tool_names: list[str], *, require_confirmation: bool = False
) -> McpToolset:
    """Create a GitHub MCP toolset with only the requested tools exposed."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN must be set to use GitHub MCP tools")

    return McpToolset(
        connection_params=StreamableHTTPServerParams(
            url=os.environ.get("MCP_SERVER_URL", GITHUB_MCP_SERVER_URL),
            headers={
                "Authorization": f"Bearer {token}",
                "X-MCP-Toolsets": "all",
                "X-MCP-Readonly": "false",
            },
            timeout=30,
            sse_read_timeout=300,
        ),
        tool_filter=tool_names,
        require_confirmation=require_confirmation,
    )
