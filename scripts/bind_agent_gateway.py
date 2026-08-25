from __future__ import annotations

import json
import os
import subprocess
import time

import httpx


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def gcloud_token() -> str:
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty access token")
    return token


def main() -> None:
    project = required("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    runtime = required("CARGO_RELEASE_AGENT_RUNTIME")
    gateway = required("CARGO_RELEASE_AGENT_GATEWAY")
    unbind = os.getenv("CARGO_RELEASE_UNBIND_GATEWAY") == "1"
    engine_id = runtime.rsplit("/", 1)[-1]
    url = (
        f"https://{location}-aiplatform.googleapis.com/v1beta1/projects/{project}"
        f"/locations/{location}/reasoningEngines/{engine_id}"
    )
    headers = {
        "Authorization": f"Bearer {gcloud_token()}",
        "Content-Type": "application/json; charset=utf-8",
    }
    gateway_config: dict[str, object] = {}
    if not unbind:
        gateway_config = {
            "agentToAnywhereConfig": {"agentGateway": gateway}
        }
    payload = {
        "spec": {
            "deploymentSpec": {
                "agentGatewayConfig": gateway_config
            }
        }
    }
    with httpx.Client(timeout=60) as client:
        operation_name = os.getenv("CARGO_RELEASE_BIND_OPERATION")
        if operation_name:
            patched = {"name": operation_name}
        else:
            response = client.patch(
                url,
                headers=headers,
                params={"updateMask": "spec.deploymentSpec.agentGatewayConfig"},
                json=payload,
            )
            response.raise_for_status()
            patched = response.json()
            operation_name = patched.get("name")
        if operation_name:
            operation_url = f"https://{location}-aiplatform.googleapis.com/v1beta1/{operation_name}"
            for _attempt in range(120):
                operation_response = client.get(operation_url, headers=headers)
                operation_response.raise_for_status()
                operation = operation_response.json()
                if operation.get("done"):
                    if operation.get("error"):
                        raise RuntimeError(
                            f"Agent Gateway bind operation failed: {operation['error']}"
                        )
                    break
                time.sleep(5)
            else:
                raise TimeoutError("Agent Gateway bind operation did not finish within 10 minutes")
        verified = client.get(url, headers=headers)
        verified.raise_for_status()
    binding = (
        verified.json()
        .get("spec", {})
        .get("deploymentSpec", {})
        .get("agentGatewayConfig")
    )
    print(
        json.dumps(
            {
                "patch_response_name": patched.get("name"),
                "runtime": runtime,
                "agent_gateway_config": binding,
            },
            sort_keys=True,
        )
    )
    if not unbind and binding is None:
        raise RuntimeError("Agent Runtime returned a null Agent Gateway binding")
    if unbind and binding:
        raise RuntimeError("Agent Runtime retained an Agent Gateway binding after rollback")


if __name__ == "__main__":
    main()
