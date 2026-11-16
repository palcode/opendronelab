#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
#
# Pre-flip checks for palcode/opendronelab. Confirms a known-good commit
# is served and that the pre-rewrite SHA 04d2c43 is not.
#
# Usage: scripts/check-preflip.sh
# Prefers authenticated `gh api`. Falls back to curl with GH_TOKEN or
# GITHUB_TOKEN, then to unauthenticated curl (a 404 is inconclusive
# while the repository is still private). This script never prints a
# token. It does not change repository settings or delete workflow runs.

set -euo pipefail

REPO="${ODL_GITHUB_REPO:-palcode/opendronelab}"
ABSENT_SHA="04d2c43"
# First commit that landed on the new palcode/opendronelab (CODEOWNERS / CHANGELOG).
PRESENT_SHA="${ODL_KNOWN_COMMIT:-bccb5a1d651a7783ce6a8c624754b38e43c1a22c}"

status_for() {
    local sha="$1"
    local headers
    headers="$(mktemp)"
    # Body is discarded; we only need the HTTP status and a short message.
    if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
        gh api -i "repos/${REPO}/commits/${sha}" >/dev/null 2>"${headers}" || true
        # gh api -i writes the response (headers+body) to stdout on success.
        # Re-run capturing only the status line.
        local raw
        raw="$(gh api -i "repos/${REPO}/commits/${sha}" 2>/dev/null || true)"
        echo "${raw}" | awk 'BEGIN{IGNORECASE=1} /^HTTP\//{print $2; exit}'
        rm -f "${headers}"
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
    rm -f "${headers}"
}

authenticated=0
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    authenticated=1
elif [ -n "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]; then
    authenticated=1
fi

echo "Repository: ${REPO}"
echo "Expect present: ${PRESENT_SHA}"
echo "Expect absent:  ${ABSENT_SHA}"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if git cat-file -t "${ABSENT_SHA}" >/dev/null 2>&1; then
        echo "FAIL: ${ABSENT_SHA} exists in the local git object store."
        exit 1
    fi
    echo "OK: ${ABSENT_SHA} is not in the local git object store."
fi

present_code="$(status_for "${PRESENT_SHA}")"
absent_code="$(status_for "${ABSENT_SHA}")"

echo "GET commits/${PRESENT_SHA} -> HTTP ${present_code}"
echo "GET commits/${ABSENT_SHA} -> HTTP ${absent_code}"

if [ "${present_code}" != "200" ]; then
    if [ "${authenticated}" -eq 0 ] && [ "${present_code}" = "404" ]; then
        echo "INCONCLUSIVE: unauthenticated request got 404 for a known-good commit (repository is probably still private). Authenticate with gh or set GH_TOKEN and re-run."
        exit 2
    fi
    echo "FAIL: expected HTTP 200 for ${PRESENT_SHA}, got ${present_code}."
    exit 1
fi

if [ "${absent_code}" != "404" ]; then
    echo "FAIL: expected HTTP 404 for ${ABSENT_SHA} (pre-rewrite SHA must not be served), got ${absent_code}."
    exit 1
fi

echo "OK: ${ABSENT_SHA} is not served on ${REPO}."
