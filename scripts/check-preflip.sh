#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
#
# Pre-flip checks for palcode/opendronelab. Confirms a known-good commit
# is served and that the pre-rewrite SHA 04d2c43 is not.
#
# Usage: scripts/check-preflip.sh
# Checks, in order:
#   1. origin/main (or HEAD) must not have 04d2c43 as an ancestor.
#      A leftover object in this clone's store (reflog, another remote)
#      is only a note, not a failure.
#   2. If `origin` is configured, a throwaway fetch of the full SHAs
#      (empty bare repo, so local objects cannot satisfy the request).
#   3. GitHub API, if `gh` is authenticated or GH_TOKEN / GITHUB_TOKEN
#      is set. Unauthenticated calls are inconclusive while the
#      repository is private. GitHub may return 404 or 422 with
#      "No commit found" for a missing SHA.
#
# This script never prints a token. It does not change repository
# settings or delete workflow runs.

set -euo pipefail

REPO="${ODL_GITHUB_REPO:-palcode/opendronelab}"
ABSENT_SHA="04d2c43"
ABSENT_FULL="04d2c4351d2a8d74930c4e751924542926ca0789"
# First commit that landed on the new palcode/opendronelab (CODEOWNERS / CHANGELOG).
PRESENT_SHA="${ODL_KNOWN_COMMIT:-bccb5a1d651a7783ce6a8c624754b38e43c1a22c}"

echo "Repository: ${REPO}"
echo "Expect present: ${PRESENT_SHA}"
echo "Expect absent:  ${ABSENT_FULL}"

fail=0

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    tip="origin/main"
    if ! git rev-parse --verify "${tip}" >/dev/null 2>&1; then
        tip="HEAD"
    fi
    if git cat-file -t "${ABSENT_SHA}" >/dev/null 2>&1; then
        if git merge-base --is-ancestor "${ABSENT_SHA}" "${tip}" 2>/dev/null; then
            echo "FAIL: ${ABSENT_SHA} is an ancestor of ${tip}."
            fail=1
        else
            echo "NOTE: ${ABSENT_SHA} exists as a local object (for example a reflog entry) but is not reachable from ${tip}."
        fi
    else
        echo "OK: ${ABSENT_SHA} is not in the local git object store."
    fi
fi

probe_origin() {
    local sha="$1"
    local url="$2"
    local tmp
    tmp="$(mktemp -d)"
    git init --bare "${tmp}" >/dev/null 2>&1
    git -C "${tmp}" remote add origin "${url}"
    set +e
    git -C "${tmp}" fetch --depth=1 origin "${sha}" >/dev/null 2>&1
    local rc=$?
    set -e
    rm -rf "${tmp}"
    return "${rc}"
}

if git remote get-url origin >/dev/null 2>&1; then
    origin_url="$(git remote get-url origin)"
    if probe_origin "${PRESENT_SHA}" "${origin_url}"; then
        echo "OK: origin served ${PRESENT_SHA}."
    else
        echo "FAIL: origin did not serve known-good ${PRESENT_SHA}."
        fail=1
    fi
    if probe_origin "${ABSENT_FULL}" "${origin_url}"; then
        echo "FAIL: origin served pre-rewrite ${ABSENT_FULL}."
        fail=1
    else
        echo "OK: origin refused ${ABSENT_FULL} (not our ref)."
    fi
fi

api_status() {
    local sha="$1"
    if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
        local raw
        raw="$(gh api -i "repos/${REPO}/commits/${sha}" 2>/dev/null || true)"
        echo "${raw}" | awk 'BEGIN{IGNORECASE=1} /^HTTP\//{print $2; exit}'
        return 0
    fi
    local url="https://api.github.com/repos/${REPO}/commits/${sha}"
    local args=(-sS -o /dev/null -w "%{http_code}" -H "Accept: application/vnd.github+json")
    if [ -n "${GH_TOKEN:-}" ]; then
        args+=(-H "Authorization: Bearer ${GH_TOKEN}")
    elif [ -n "${GITHUB_TOKEN:-}" ]; then
        args+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
    fi
    curl "${args[@]}" "${url}"
}

authenticated=0
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    authenticated=1
elif [ -n "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]; then
    authenticated=1
fi

if [ "${authenticated}" -eq 1 ]; then
    present_code="$(api_status "${PRESENT_SHA}")"
    absent_code="$(api_status "${ABSENT_SHA}")"
    echo "GET commits/${PRESENT_SHA} -> HTTP ${present_code}"
    echo "GET commits/${ABSENT_SHA} -> HTTP ${absent_code}"
    if [ "${present_code}" != "200" ]; then
        echo "FAIL: expected HTTP 200 for ${PRESENT_SHA}, got ${present_code}."
        fail=1
    fi
    # GitHub returns 422 "No commit found" or 404 for a SHA it does not serve.
    if [ "${absent_code}" != "404" ] && [ "${absent_code}" != "422" ]; then
        echo "FAIL: expected HTTP 404 or 422 for ${ABSENT_SHA}, got ${absent_code}."
        fail=1
    else
        echo "OK: ${ABSENT_SHA} is not served on ${REPO} (HTTP ${absent_code})."
    fi
else
    echo "NOTE: no gh auth or GH_TOKEN; skipping the GitHub REST check. Unauthenticated 404s are inconclusive while the repository is private. Re-run after the flip or with gh / GH_TOKEN."
fi

if [ "${fail}" -ne 0 ]; then
    exit 1
fi
echo "OK: pre-flip checks passed."
