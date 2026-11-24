# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
"""git_sha / git_dirty for summary.json (informational, not fingerprinted).

The host-side scripts read the checkout with git and pass the result into
the container as ODL_GIT_SHA (40-hex HEAD, empty if unknown) and
ODL_GIT_DIRTY ("1" = tracked files modified, "0" = clean, empty = unknown).
A missing git binary or a directory that is not a git checkout gives empty
values, which become JSON null here. These fields are deliberately not part
of scenario_fingerprint: the fingerprint covers what was flown (model,
world, overlay, mask), not which commit ran it.
"""
import os
import re

_SHA = re.compile(r'^[0-9a-f]{40}$')


def git_fields(env=None) -> dict:
    env = os.environ if env is None else env
    sha = (env.get('ODL_GIT_SHA') or '').strip().lower()
    if not _SHA.match(sha):
        return {'git_sha': None, 'git_dirty': None}
    dirty = {'1': True, '0': False}.get((env.get('ODL_GIT_DIRTY') or '').strip())
    return {'git_sha': sha, 'git_dirty': dirty}
