"""GitHub MCP tool configuration for the ADK workflow.

Use a GitHub MCP server URL via the MCP_SERVER_URL environment variable.
This follows the real ADK MCP pattern, not the stdio example.
"""

import os
from typing import Any, Optional

try:
    from google.adk.tools import McpToolset as _McpToolset  # type: ignore
except Exception:
    _McpToolset = None

try:
    from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams  # type: ignore
except Exception:
    StreamableHTTPConnectionParams = None


class Tools:
    """Expose a GitHub MCP toolset when MCP_SERVER_URL is configured."""

    def __init__(self):
        self.github_mcp = self._build_github_mcp()

    def _build_github_mcp(self) -> Optional[Any]:
        url = os.environ.get("MCP_SERVER_URL")
        if not url:
            return None

        if _McpToolset is None:
            raise ImportError("google-adk MCPToolset is not available in this environment")

        if StreamableHTTPConnectionParams is None:
            raise ImportError(
                "The installed google-adk version does not expose StreamableHTTPConnectionParams"
            )

        try:
            return _McpToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=url,
                    timeout=30,
                    sse_read_timeout=300,
                ),
                tool_filter=None,
                tool_name_prefix="github_",
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to GitHub MCP server at {url}: {exc}") from exc
