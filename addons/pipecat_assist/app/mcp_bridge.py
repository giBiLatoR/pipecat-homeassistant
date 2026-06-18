"""Home Assistant MCP bridge for Pipecat and text requests."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import httpx
from loguru import logger
from mcp.client.session_group import StreamableHttpParameters

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import LLMService
from pipecat.services.mcp_service import MCPClient


class MCPAuthenticationError(RuntimeError):
    """Raised when Home Assistant rejects the MCP bearer token."""


class HomeAssistantMCPBridge:
    """Small wrapper around Pipecat's MCPClient."""

    def __init__(self, url: str, token: str, tool_allowlist: Sequence[str] | None = None):
        self.url = url
        self.token = token
        self.tool_allowlist = list(tool_allowlist or [])
        self.client: MCPClient | None = None

    async def __aenter__(self) -> "HomeAssistantMCPBridge":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def start(self) -> None:
        """Connect to Home Assistant MCP."""

        if not self.token:
            raise RuntimeError("Home Assistant MCP token is not configured")
        if self.client:
            return
        await self._preflight_auth()
        self.client = MCPClient(
            server_params=StreamableHttpParameters(
                url=self.url,
                headers={"Authorization": f"Bearer {self.token}"},
            ),
            tools_filter=self.tool_allowlist or None,
        )
        await self.client.start()
        logger.info("Connected to Home Assistant MCP at {}", self.url)

    async def _preflight_auth(self) -> None:
        """Detect auth failures before MCPClient starts background tasks."""

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        payload = {"jsonrpc": "2.0", "id": "pipecat-assist-preflight", "method": "ping"}

        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                response = await client.post(self.url, headers=headers, json=payload)
        except httpx.HTTPError as err:
            raise RuntimeError(f"Home Assistant MCP is not reachable: {err}") from err

        if response.status_code in {401, 403}:
            raise MCPAuthenticationError(
                "Home Assistant MCP rejected the token. Paste a Home Assistant "
                "long-lived access token in Integrations > Home Assistant MCP > "
                "Access token, save, and retry."
            )
        if response.status_code == 404:
            raise RuntimeError(f"Home Assistant MCP endpoint was not found at {self.url}")
        if response.status_code >= 500:
            raise RuntimeError(
                f"Home Assistant MCP returned HTTP {response.status_code}. Check the Home Assistant logs."
            )

    async def close(self) -> None:
        """Close the MCP connection."""

        client = self.client
        self.client = None
        if not client:
            return
        try:
            await client.close()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            logger.debug("Ignoring MCP close error: {}", err)

    async def tools_schema(self) -> ToolsSchema:
        """Return MCP tools in Pipecat schema format."""

        if not self.client:
            raise RuntimeError("MCP bridge is not started")
        return await self.client.get_tools_schema()

    async def register_tools_schema(self, tools: ToolsSchema, llm: LLMService) -> None:
        """Register MCP tools with a Pipecat LLM service."""

        if not self.client:
            raise RuntimeError("MCP bridge is not started")
        await self.client.register_tools_schema(tools, llm)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call one MCP tool and return text content."""

        if not self.client:
            raise RuntimeError("MCP bridge is not started")
        session = self.client._ensure_connected()  # Pipecat exposes no public call_tool yet.
        result = await session.call_tool(name, arguments=arguments)
        chunks: list[str] = []
        for content in getattr(result, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
        return "\n".join(chunks) if chunks else "Tool returned no text content."


async def check_mcp(url: str, token: str, tool_allowlist: Sequence[str] | None = None) -> dict[str, Any]:
    """Probe MCP connectivity for the status endpoint."""

    try:
        async with HomeAssistantMCPBridge(url, token, tool_allowlist) as bridge:
            tools = await bridge.tools_schema()
            return {
                "ok": True,
                "tool_count": len(tools.standard_tools),
                "tools": [tool.name for tool in tools.standard_tools[:50]],
            }
    except asyncio.CancelledError as err:
        logger.warning("MCP check was cancelled: {}", err)
        return {"ok": False, "error": "MCP check was cancelled", "tool_count": 0, "tools": []}
    except Exception as err:
        logger.warning("MCP check failed: {}", err)
        return {"ok": False, "error": str(err), "tool_count": 0, "tools": []}
