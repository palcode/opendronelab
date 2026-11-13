#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Pallab Sarkar
#
# Resolve ODL_ROOT (repository) and ODL_DATA (bags, PX4 build, results).
# Source this file from other scripts:
#   source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/odl-env.sh"
#
# Defaults:
#   ODL_ROOT  — parent of the scripts/ directory (the git checkout)
#   ODL_DATA  — sibling directory named dronelab-data
#               (…/dronelab and …/dronelab-data next to each other)
#
# Overrides: export ODL_ROOT and/or ODL_DATA, or the older REPO_DIR,
# DATA_DIR, and WORKSPACE_DIR names, before sourcing.

if [ -n "${ODL_ENV_LOADED:-}" ]; then
    return 0 2>/dev/null || exit 0
fi

_odl_scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Honour older variable names if ODL_* is unset.
if [ -z "${ODL_ROOT:-}" ]; then
    if [ -n "${WORKSPACE_DIR:-}" ]; then
        ODL_ROOT="${WORKSPACE_DIR}"
    elif [ -n "${REPO_DIR:-}" ]; then
        ODL_ROOT="${REPO_DIR}"
    else
        ODL_ROOT="$(cd "${_odl_scripts_dir}/.." && pwd)"
    fi
fi

if [ -z "${ODL_DATA:-}" ]; then
    if [ -n "${DATA_DIR:-}" ]; then
        ODL_DATA="${DATA_DIR}"
    else
        ODL_DATA="$(cd "${ODL_ROOT}/.." && pwd)/dronelab-data"
    fi
fi

export ODL_ROOT ODL_DATA
REPO_DIR="${REPO_DIR:-${ODL_ROOT}}"
DATA_DIR="${DATA_DIR:-${ODL_DATA}}"
WORKSPACE_DIR="${WORKSPACE_DIR:-${ODL_ROOT}}"
export REPO_DIR DATA_DIR WORKSPACE_DIR
ODL_ENV_LOADED=1
export ODL_ENV_LOADED
unset _odl_scripts_dir
