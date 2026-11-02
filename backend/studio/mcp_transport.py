"""Authenticated MCP mount. No render state lives in the protocol adapter."""

from starlette.responses import JSONResponse

from .auth import agent_token, bearer, matches


class AgentAuth:
    def __init__(self, app, workspace):
        self.app = app
        self.workspace = workspace

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            from starlette.datastructures import Headers

            if not matches(bearer(Headers(scope=scope)), agent_token(self.workspace)):
                await JSONResponse({"detail": "Agent connection needs its bearer token."}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)
