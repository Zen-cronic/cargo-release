from __future__ import annotations

from starlette.testclient import TestClient
from starlette.types import ASGIApp


class ASGITestClient(TestClient):
    """Current Starlette transport on uvloop for this host's selector limitation."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app, backend_options={"use_uvloop": True})
