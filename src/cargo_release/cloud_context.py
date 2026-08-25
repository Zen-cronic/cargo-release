from __future__ import annotations

import os
import re

from cargo_release.models import TruthMode


def eventarc_truth_mode(
    *, event_id: str | None, event_source: str | None, trace_context: str | None
) -> TruthMode:
    """Label an ingress NATIVE only when Cloud Run and CloudEvents evidence agree."""

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    on_cloud_run = bool(os.getenv("K_SERVICE") and project)
    native_source = f"//pubsub.googleapis.com/projects/{project}/topics/"
    has_native_cloud_event = bool(
        event_id and event_source and event_source.startswith(native_source)
    )
    # Google documents the legacy suffix as ``;o=OPTIONS``, but authenticated
    # Eventarc deliveries can omit the sampling option. Sampling is not
    # provenance: retain the exact trace-id/span grammar and make only that
    # non-authoritative flag optional.
    has_native_trace = bool(
        trace_context
        and re.fullmatch(r"[0-9a-f]{32}/[0-9]+(?:;o=[01])?", trace_context, re.IGNORECASE)
    )
    if on_cloud_run and has_native_cloud_event and has_native_trace:
        return TruthMode.NATIVE
    return TruthMode.FIXTURE
