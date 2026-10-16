"""Authenticated MCP JSON-RPC HTTP and workspace inspection routes."""

from __future__ import annotations

import hmac
import json
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from agentdrift import __version__
from agentdrift.mcp.workspace_tools import TOOLS, call_tool, get_service

router = APIRouter()


async def require_service_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("AGENTDRIFT_SERVICE_TOKEN", "").strip()
    presented = (
        authorization[7:].strip()
        if authorization and authorization.lower().startswith("bearer ")
        else ""
    )
    if not expected or not presented or not hmac.compare_digest(expected, presented):
        raise HTTPException(
            401, "valid service bearer token required", headers={"WWW-Authenticate": "Bearer"}
        )


class RpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/api/v1/mcp/tools/call")
async def mcp_http_call(body: RpcRequest, authorization: str | None = Header(default=None)):
    await require_service_token(authorization)
    if body.jsonrpc != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": body.id,
            "error": {"code": -32600, "message": "jsonrpc must be 2.0"},
        }
    if body.method == "initialize":
        result = {
            "protocolVersion": body.params.get("protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "agentdrift-workspace-memory", "version": __version__},
        }
    elif body.method in {"notifications/initialized", "notifications/cancelled"}:
        return Response(status_code=202)
    elif body.method == "ping":
        result = {}
    elif body.method == "tools/list":
        result = {"tools": TOOLS}
    elif body.method == "tools/call":
        name = body.params.get("name")
        args = body.params.get("arguments", {})
        try:
            data = await call_tool(name, args)
        except KeyError as exc:
            return {"jsonrpc": "2.0", "id": body.id, "error": {"code": -32601, "message": str(exc)}}
        except (TypeError, ValueError) as exc:
            return {"jsonrpc": "2.0", "id": body.id, "error": {"code": -32602, "message": str(exc)}}
        structured = data if isinstance(data, dict) else {"items": data}
        result = {
            "content": [{"type": "text", "text": json.dumps(data, default=str)}],
            "structuredContent": structured,
        }
    else:
        return {
            "jsonrpc": "2.0",
            "id": body.id,
            "error": {"code": -32601, "message": f"unsupported MCP method: {body.method}"},
        }
    return {"jsonrpc": "2.0", "id": body.id, "result": result}


@router.get("/api/v1/workspace/{session_id}/timeline")
async def workspace_timeline(session_id: str, authorization: str | None = Header(default=None)):
    await require_service_token(authorization)
    service = get_service()
    return {"session_id": session_id, "actions": await service.timeline(session_id)}
