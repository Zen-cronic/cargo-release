from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROMOTION_SCRIPT = REPOSITORY_ROOT / "deploy" / "promote_recording_candidate.sh"
APPROVAL = (
    "I_APPROVE_PROMOTE_RECORDING_59B2AED_CONTROLLER_00021_WEB_00016_"
    "KEEP_00019_00014_ROLLBACK"
)
CONTROLLER_CANDIDATE = "cargo-release-controller-00021-tac"
CONTROLLER_ROLLBACK = "cargo-release-controller-00019-ton"
WEB_CANDIDATE = "cargo-release-web-00016-nol"
WEB_ROLLBACK = "cargo-release-web-00014-pag"


def _write_executable(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source).lstrip(), encoding="utf-8")
    path.chmod(0o755)


def _mock_environment(tmp_path: Path) -> dict[str, str]:
    bin_path = tmp_path / "bin"
    state_path = tmp_path / "state"
    bin_path.mkdir()
    state_path.mkdir()
    (state_path / "controller").write_text(CONTROLLER_ROLLBACK, encoding="utf-8")
    (state_path / "web").write_text(WEB_ROLLBACK, encoding="utf-8")

    _write_executable(
        bin_path / "gcloud",
        r'''
        #!/usr/bin/env python3
        import json
        import os
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        state = Path(os.environ["MOCK_PROMOTION_STATE"])
        controller_candidate = "cargo-release-controller-00021-tac"
        controller_rollback = "cargo-release-controller-00019-ton"
        web_candidate = "cargo-release-web-00016-nol"
        web_rollback = "cargo-release-web-00014-pag"
        images = {
            controller_candidate: (
                "us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/backend@sha256:"
                "19e842e379fed15c4692b699fb903508eaff5de59dc1f7edc4555a6c165fe4aa"
            ),
            web_candidate: (
                "us-central1-docker.pkg.dev/ata-2026-cargo/cargo-release/web@sha256:"
                "76d2b0ef3e23c3a7307c8ad3f6ef91980b6bde842dcfba509440ab709f2b9b8b"
            ),
            controller_rollback: "rollback-controller",
            web_rollback: "rollback-web",
        }

        if args[:3] == ["config", "get-value", "account"]:
            print("operator@example.test")
            raise SystemExit(0)
        if args[:3] == ["config", "get-value", "project"]:
            print("ata-2026-cargo")
            raise SystemExit(0)

        if args[:3] == ["run", "services", "describe"]:
            service = args[3]
            key = "controller" if service == "cargo-release-controller" else "web"
            revision = (state / key).read_text(encoding="utf-8")
            print(json.dumps({"status": {"traffic": [{"percent": 100, "revisionName": revision}]}}))
            raise SystemExit(0)

        if args[:3] == ["run", "revisions", "describe"]:
            revision = args[3]
            print(json.dumps({
                "spec": {"containers": [{"image": images[revision]}]},
                "status": {"conditions": [{"type": "Ready", "status": "True"}]},
            }))
            raise SystemExit(0)

        if args[:3] == ["run", "services", "update-traffic"]:
            service = args[3]
            key = "controller" if service == "cargo-release-controller" else "web"
            encoded_target = next(
                value for value in args if value.startswith("--to-revisions=")
            )
            target = encoded_target.removeprefix("--to-revisions=").rsplit("=", 1)[0]
            with (state / "calls").open("a", encoding="utf-8") as stream:
                stream.write(f"{key}:{target}\n")
            if os.environ.get("MOCK_FAIL_WEB_PROMOTION") == "1" and target == web_candidate:
                raise SystemExit(9)
            (state / key).write_text(target, encoding="utf-8")
            raise SystemExit(0)

        print(f"unexpected gcloud arguments: {args}", file=sys.stderr)
        raise SystemExit(90)
        ''',
    )
    _write_executable(
        bin_path / "curl",
        r'''
        #!/usr/bin/env python3
        import json
        from pathlib import Path
        import sys

        args = sys.argv[1:]
        url = args[-1]
        status = "200" if url.endswith("/api/cargo/health") else (
            "400" if "?debug=1" in url else "404"
        )
        payload = json.dumps({"status": "ok", "mode": "FIXTURE", "database": "postgresql"})
        if "--output" in args:
            output = Path(args[args.index("--output") + 1])
            output.write_text(payload if status == "200" else "denied", encoding="utf-8")
        elif status == "200":
            print(payload)
        if "--write-out" in args:
            print(status, end="")
        raise SystemExit(0)
        ''',
    )
    return {
        **os.environ,
        "PATH": f"{bin_path}:{os.environ['PATH']}",
        "MOCK_PROMOTION_STATE": str(state_path),
    }


def _run(
    tmp_path: Path, *, approved: bool, fail_web: bool = False
) -> subprocess.CompletedProcess[str]:
    environment = _mock_environment(tmp_path)
    if approved:
        environment["CARGO_RELEASE_RECORDING_PROMOTION_APPROVED"] = APPROVAL
    if fail_web:
        environment["MOCK_FAIL_WEB_PROMOTION"] = "1"
    return subprocess.run(
        [str(PROMOTION_SCRIPT)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _calls(tmp_path: Path) -> list[str]:
    calls_path = tmp_path / "state" / "calls"
    return calls_path.read_text(encoding="utf-8").splitlines() if calls_path.exists() else []


def test_missing_approval_performs_no_traffic_change(tmp_path: Path) -> None:
    result = _run(tmp_path, approved=False)

    assert result.returncode == 3
    assert "Promotion preflight passed; no traffic changed." in result.stderr
    assert _calls(tmp_path) == []


def test_success_promotes_controller_before_web(tmp_path: Path) -> None:
    result = _run(tmp_path, approved=True)

    assert result.returncode == 0, result.stderr
    assert _calls(tmp_path) == [
        f"controller:{CONTROLLER_CANDIDATE}",
        f"web:{WEB_CANDIDATE}",
    ]
    assert (tmp_path / "state" / "controller").read_text(encoding="utf-8") == CONTROLLER_CANDIDATE
    assert (tmp_path / "state" / "web").read_text(encoding="utf-8") == WEB_CANDIDATE
    assert "RELAY_PROOF=health:200,forbidden:404,query:400" in result.stdout


def test_failed_web_promotion_restores_pinned_pair(tmp_path: Path) -> None:
    result = _run(tmp_path, approved=True, fail_web=True)

    assert result.returncode == 9
    assert _calls(tmp_path) == [
        f"controller:{CONTROLLER_CANDIDATE}",
        f"web:{WEB_CANDIDATE}",
        f"web:{WEB_ROLLBACK}",
        f"controller:{CONTROLLER_ROLLBACK}",
    ]
    assert (tmp_path / "state" / "controller").read_text(encoding="utf-8") == CONTROLLER_ROLLBACK
    assert (tmp_path / "state" / "web").read_text(encoding="utf-8") == WEB_ROLLBACK
    assert "restoring the pinned pair" in result.stderr
