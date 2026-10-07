import json

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings

# Room for multipart boundaries and part headers around the file itself.
MULTIPART_OVERHEAD = 64 * 1024


class UploadSizeLimitMiddleware:
    """Reject oversized uploads from their Content-Length, before any body is read.

    Starlette parses the whole multipart body before an endpoint runs, so a size check
    inside the endpoint only fires after the client has sent everything.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == "/api/files/":
            max_bytes = get_settings().max_upload_bytes
            headers = dict(scope["headers"])
            declared = headers.get(b"content-length")
            if declared is not None and declared.isdigit() and int(declared) > max_bytes + MULTIPART_OVERHEAD:
                body = json.dumps(
                    {"detail": f"File exceeds the {max_bytes // (1024 * 1024)} MB limit."}
                ).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
