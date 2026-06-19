"""Home Assistant MCP bridge for Pipecat and text requests."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger
from mcp.client.session_group import StreamableHttpParameters

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import LLMService
from pipecat.services.mcp_service import MCPClient


class MCPAuthenticationError(RuntimeError):
    """Raised when Home Assistant rejects the MCP bearer token."""


MCP_CALL_HISTORY: deque[dict[str, Any]] = deque(maxlen=100)


def _compact_json(value: Any, limit: int = 1200) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        except TypeError:
            text = str(value)
    if len(text) > limit:
        return f"{text[:limit]}..."
    return text


def list_mcp_call_history() -> dict[str, Any]:
    """Return recent Home Assistant MCP tool calls."""

    return {"calls": list(reversed(MCP_CALL_HISTORY))}


def clear_mcp_call_history() -> dict[str, Any]:
    """Clear recent Home Assistant MCP tool calls."""

    MCP_CALL_HISTORY.clear()
    return list_mcp_call_history()


def _new_history_item(name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], float]:
    return (
        {
            "id": uuid.uuid4().hex[:12],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "tool": name,
            "arguments": _compact_json(arguments),
        },
        time.perf_counter(),
    )


def _finish_history_item(
    history_item: dict[str, Any],
    started: float,
    *,
    ok: bool,
    result: str = "",
    error: str = "",
) -> None:
    history_item.update(
        {
            "ok": ok,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }
    )
    if ok:
        history_item["result"] = _compact_json(result, limit=1000)
    else:
        history_item["error"] = error or result or "MCP tool failed"
    MCP_CALL_HISTORY.append(history_item)


class RecordingMCPClient(MCPClient):
    """Pipecat MCP client that records tool calls for the Runtime UI."""

    async def _call_tool(self, session, function_name, arguments, result_callback):
        history_item, started = _new_history_item(function_name, dict(arguments or {}))
        logger.debug("Calling mcp tool '{}'", function_name)
        results = None
        error = ""
        try:
            results = await session.call_tool(function_name, arguments=arguments)
        except Exception as err:
            error = f"Error calling mcp tool {function_name}: {err}"
            logger.error(error)

        response = ""
        if results:
            if hasattr(results, "content") and results.content:
                for index, content in enumerate(results.content):
                    if hasattr(content, "text") and content.text:
                        logger.debug("Tool response chunk {}: {}", index, content.text)
                        response += content.text
            else:
                logger.error("Error getting content from {} results.", function_name)

        if function_name in self._tools_output_filters:
            try:
                response = self._tools_output_filters[function_name](response)
                logger.debug("Final response after filter: {}", response)
            except Exception:
                logger.error("Error applying output filter for {}", function_name)
                response = ""

        ok = bool(response and isinstance(response, str) and not error)
        if ok:
            logger.info("Tool '{}' completed successfully", function_name)
            logger.debug("Final response: {}", response)
        else:
            response = "Sorry, could not call the mcp tool"

        _finish_history_item(
            history_item,
            started,
            ok=ok,
            result=response,
            error=error,
        )
        await result_callback(response)


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
        self.client = RecordingMCPClient(
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
                "Home Assistant MCP rejected the token. The add-on normally uses "
                "the Home Assistant Supervisor token automatically. If you are "
                "running outside the Supervisor or using a custom MCP URL, configure "
                "a long-lived access token."
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
        history_item, started = _new_history_item(name, arguments)
        try:
            session = self.client._ensure_connected()  # Pipecat exposes no public call_tool yet.
            result = await session.call_tool(name, arguments=arguments)
            chunks: list[str] = []
            for content in getattr(result, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    chunks.append(text)
            text_result = "\n".join(chunks) if chunks else "Tool returned no text content."
            _finish_history_item(history_item, started, ok=True, result=text_result)
            return text_result
        except Exception as err:
            _finish_history_item(history_item, started, ok=False, error=str(err))
            raise



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
