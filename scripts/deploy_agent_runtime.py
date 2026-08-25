from __future__ import annotations

import os
import subprocess
from pathlib import Path

import vertexai
from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as UserCredentials
from vertexai import agent_engines, types

from cargo_release.adk_agent import DEFAULT_MODEL, DEFAULT_MODEL_LOCATION, root_agent


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def deployment_credentials() -> Credentials | None:
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


def main() -> None:
    project = required("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    bucket = required("CARGO_RELEASE_STAGING_BUCKET")
    wheel = Path(required("CARGO_RELEASE_WHEEL"))
    if not wheel.is_file():
        raise RuntimeError(f"CARGO_RELEASE_WHEEL does not exist: {wheel}")
    try:
        wheel_package = wheel.resolve().relative_to(Path.cwd().resolve())
    except ValueError as exc:
        raise RuntimeError(
            "CARGO_RELEASE_WHEEL must be inside the deployment working directory"
        ) from exc
    credentials = deployment_credentials()
    vertexai.init(
        project=project,
        location=location,
        credentials=credentials,
        staging_bucket=bucket,
    )
    client = vertexai.Client(
        project=project,
        location=location,
        credentials=credentials,
    )
    app = agent_engines.AdkApp(agent=root_agent)
    controller_url = required("CARGO_RELEASE_CONTROLLER_URL")
    config = {
        "display_name": "Cargo Release Coordinator",
        "requirements": [
            "google-cloud-aiplatform[agent_engines,adk]>=1.112.0,<2.0.0",
            "httpx>=0.28.0,<1.0.0",
            "cloudpickle>=3.0.0,<4.0.0",
            "pydantic>=2.11.0,<3.0.0",
            str(wheel_package),
        ],
        "extra_packages": [str(wheel_package)],
        "staging_bucket": bucket,
        "env_vars": {
            "CARGO_RELEASE_CONTROLLER_URL": controller_url,
            "CARGO_RELEASE_CONTROLLER_AUDIENCE": os.getenv(
                "CARGO_RELEASE_CONTROLLER_AUDIENCE", controller_url
            ),
            "CARGO_RELEASE_CALLER_SERVICE_ACCOUNT": required(
                "CARGO_RELEASE_CALLER_SERVICE_ACCOUNT"
            ),
            "CARGO_RELEASE_MODEL": os.getenv(
                "CARGO_RELEASE_MODEL", DEFAULT_MODEL
            ),
            "CARGO_RELEASE_MODEL_LOCATION": os.getenv(
                "CARGO_RELEASE_MODEL_LOCATION", DEFAULT_MODEL_LOCATION
            ),
            "CARGO_RELEASE_MODEL_PROJECT": project,
        },
        "identity_type": types.IdentityType.AGENT_IDENTITY,
        "python_version": "3.12",
    }
    gateway = os.getenv("CARGO_RELEASE_AGENT_GATEWAY")
    if gateway:
        config["agent_gateway_config"] = {
            "agent_to_anywhere_config": {"agent_gateway": gateway}
        }
    runtime = os.getenv("CARGO_RELEASE_AGENT_RUNTIME")
    if runtime:
        remote_agent = client.agent_engines.update(
            name=runtime,
            agent=app,
            config=config,
        )
    else:
        remote_agent = client.agent_engines.create(agent=app, config=config)
    print(remote_agent.api_resource.name)


if __name__ == "__main__":
    main()
