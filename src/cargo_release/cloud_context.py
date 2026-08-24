from __future__ import annotations

import os

from cargo_release.models import TruthMode


def eventarc_truth_mode(
    *, event_id: str | None, event_source: str | None, trace_context: str | None
) -> TruthMode:
    """Label an ingress NATIVE only when Cloud Run and CloudEvents evidence agree."""

    on_cloud_run = bool(os.getenv("K_SERVICE") and os.getenv("GOOGLE_CLOUD_PROJECT"))
    has_cloud_event = bool(event_id and event_source)
    if on_cloud_run and has_cloud_event and trace_context:
        return TruthMode.NATIVE
    return TruthMode.FIXTURE
