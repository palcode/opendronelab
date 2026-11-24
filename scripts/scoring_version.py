# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
"""scoring_version for summary.json (recorded, not fingerprinted).

localization_metrics writes ``scoring_version`` into every metrics JSON
(``SCORING_VERSION`` there). The summary takes it from the metrics files
that were actually written, so a run scored by an older install reports
the version that really scored it. Metrics written before the field
existed are version 1. No metrics at all gives None.

Kept out of scenario_fingerprint on purpose: the fingerprint covers what
was flown (model, flight profile, world, overlay, mask). The scoring
version describes how the recorded flight was scored; the same bag can be
re-scored under either version. Compare numbers only when both the
fingerprint and scoring_version match.
"""


def summary_scoring_version(*metrics):
    versions = set()
    for m in metrics:
        if isinstance(m, dict) and m:
            versions.add(int(m.get('scoring_version', 1)))
    if not versions:
        return None
    if len(versions) > 1:
        # Two metrics files from different scorers: report the oldest so the
        # run is never taken for a fully re-scored one.
        return min(versions)
    return versions.pop()
