from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import subprocess
from collections.abc import Awaitable
from typing import Any, cast

import vertexai
from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as UserCredentials


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def runtime_credentials() -> Credentials | None:
    if os.getenv("CARGO_RELEASE_USE_GCLOUD_AUTH") != "1":
        return None
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty access token")
    return UserCredentials(token=token)  # type: ignore[no-untyped-call]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one managed Cargo Release Agent Engine query and emit JSONL proof."
    )
    parser.add_argument("message")
    parser.add_argument("--user-id", default="cargo-release-proof")
    parser.add_argument("--session-id")
    return parser.parse_args()


async def run_query(args: argparse.Namespace) -> None:
    project = required("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    runtime = required("CARGO_RELEASE_AGENT_RUNTIME")
    client = vertexai.Client(
        project=project,
        location=location,
        credentials=runtime_credentials(),
    )
    remote_agent = client.agent_engines.get(name=runtime)
    session_id = args.session_id
    if not session_id:
        pending_session = remote_agent.async_create_session(user_id=args.user_id)
        session = await cast(Awaitable[dict[str, Any]], pending_session)
        session_id = str(session["id"])

    print(
        json.dumps(
            {
                "kind": "managed-query",
                "runtime": runtime,
                "session_id": session_id,
                "user_id": args.user_id,
            },
            sort_keys=True,
        )
    )
    events = remote_agent.async_stream_query(
        user_id=args.user_id,
        session_id=session_id,
        message=args.message,
    )
    if inspect.isawaitable(events):
        events = await events
    async for event in events:
        print(json.dumps(event, default=str, sort_keys=True))


def main() -> None:
    asyncio.run(run_query(parse_args()))


if __name__ == "__main__":
    main()
