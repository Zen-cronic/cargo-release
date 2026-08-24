from __future__ import annotations

import os

import vertexai
from vertexai import agent_engines, types

from cargo_release.adk_agent import root_agent


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main() -> None:
    project = required("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    bucket = required("CARGO_RELEASE_STAGING_BUCKET")
    client = vertexai.Client(project=project, location=location)
    app = agent_engines.AdkApp(agent=root_agent)
    remote_agent = client.agent_engines.create(
        agent=app,
        config={
            "display_name": "Cargo Release Coordinator",
            "requirements": [
                "google-cloud-aiplatform[agent_engines,adk]>=1.112.0,<2.0.0",
                "httpx>=0.28.0,<1.0.0",
            ],
            "extra_packages": ["src/cargo_release"],
            "staging_bucket": bucket,
            "env_vars": {
                "CARGO_RELEASE_CONTROLLER_URL": required("CARGO_RELEASE_CONTROLLER_URL"),
                "CARGO_RELEASE_MODEL": os.getenv("CARGO_RELEASE_MODEL", "gemini-3.5-flash"),
            },
            "identity_type": types.IdentityType.AGENT_IDENTITY,
        },
    )
    print(remote_agent.api_resource.name)


if __name__ == "__main__":
    main()
