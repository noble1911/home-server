#!/bin/bash
# Shared utility functions for auto-configuration of HomeServer apps.
# Source this file from stack deployment scripts:
#   source "$SCRIPT_DIR/lib/configure-helpers.sh"

# Colors (safe to re-declare — no-ops if already set)
GREEN="${GREEN:-\033[0;32m}"
BLUE="${BLUE:-\033[0;34m}"
YELLOW="${YELLOW:-\033[1;33m}"
RED="${RED:-\033[0;31m}"
NC="${NC:-\033[0m}"

CREDENTIALS_FILE="$HOME/.homeserver-credentials"

# ─────────────────────────────────────────────
# Credential management
# ─────────────────────────────────────────────

# Source the credentials file if it exists.
# Also writes DRIVE_PATH into docker/.env so 'docker compose up -d' works
# without needing the shell export.
# Returns 0 if loaded, 1 if not found.
load_credentials() {
    if [[ -f "$CREDENTIALS_FILE" ]]; then
        # shellcheck disable=SC1090
        source "$CREDENTIALS_FILE"
        # Ensure docker/.env exists for docker compose
        _sync_docker_env
        return 0
    fi
    return 1
}

# Write DRIVE_PATH to docker/.env and symlink into each stack.
# This ensures 'docker compose up -d' works without a shell export.
_sync_docker_env() {
    local repo_dir
    repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    local docker_dir="$repo_dir/docker"
    local env_file="$docker_dir/.env"

    [[ -d "$docker_dir" ]] || return 0
    [[ -n "$DRIVE_PATH" ]] || return 0

    # Only write if missing or stale
    if [[ ! -f "$env_file" ]] || ! grep -q "^DRIVE_PATH=${DRIVE_PATH}$" "$env_file" 2>/dev/null; then
        printf 'DRIVE_PATH=%s\n' "$DRIVE_PATH" > "$env_file"
    fi

    # Symlink into stacks that use bind mounts
    for stack in books-stack download-stack media-stack photos-files-stack; do
        [[ -d "$docker_dir/$stack" ]] && ln -sf ../.env "$docker_dir/$stack/.env" 2>/dev/null
    done
}

# Generate a random hex API key (16 bytes = 32 hex chars).
generate_api_key() {
    openssl rand -hex 16
}

# ─────────────────────────────────────────────
# Health check retry loop
# ─────────────────────────────────────────────

# Wait for a service to respond at a URL.
# Usage: wait_for_healthy <url> [max_retries] [interval_secs] [label]
wait_for_healthy() {
    local url="$1"
    local max_retries="${2:-30}"
    local interval="${3:-2}"
    local label="${4:-Service}"

    echo -ne "  Waiting for ${label}..."
    for i in $(seq 1 "$max_retries"); do
        if curl -sf "$url" &>/dev/null; then
            echo ""
            echo -e "  ${GREEN}✓${NC} ${label} is healthy"
            return 0
        fi
        echo -n "."
        sleep "$interval"
    done
    echo ""
    echo -e "  ${YELLOW}⚠${NC} ${label} did not respond after $((max_retries * interval))s"
    return 1
}

# ─────────────────────────────────────────────
# Docker volume seeding
# ─────────────────────────────────────────────

# Check if a Docker volume exists and contains files.
# Returns 0 if volume has data, 1 otherwise.
volume_has_data() {
    local volume_name="$1"

    if ! docker volume inspect "$volume_name" &>/dev/null; then
        return 1
    fi

    local count
    count=$(docker run --rm -v "${volume_name}:/vol:ro" alpine sh -c 'ls -A /vol 2>/dev/null | wc -l' 2>/dev/null)
    [[ "$count" -gt 0 ]]
}

# Write content into a file inside a Docker named volume.
# Creates parent directories as needed.
# Usage: seed_volume_file <volume_name> <dest_path> <content>
seed_volume_file() {
    local volume_name="$1"
    local dest_path="$2"
    local content="$3"

    # Ensure volume exists
    docker volume create "$volume_name" &>/dev/null || true

    local dir_path
    dir_path=$(dirname "$dest_path")

    echo "$content" | docker run --rm -i -v "${volume_name}:/vol" alpine sh -c \
        "mkdir -p /vol/${dir_path} && cat > /vol/${dest_path}"
}

# ─────────────────────────────────────────────
# *arr API helpers (Radarr, Sonarr, Readarr, Prowlarr)
# ─────────────────────────────────────────────

# GET request with X-Api-Key header. Prints response body.
# Usage: arr_api_get <url> <api_key>
arr_api_get() {
    local url="$1"
    local api_key="$2"
    curl -sf -H "X-Api-Key: ${api_key}" "$url" 2>/dev/null
}

# POST request with X-Api-Key header and JSON body.
# Usage: arr_api_post <url> <api_key> <json_body>
arr_api_post() {
    local url="$1"
    local api_key="$2"
    local body="$3"
    curl -sf -X POST \
        -H "X-Api-Key: ${api_key}" \
        -H "Content-Type: application/json" \
        "$url" -d "$body" 2>/dev/null
}

# ─────────────────────────────────────────────
# Cross-platform sed
# ─────────────────────────────────────────────

# In-place sed that works on both macOS (BSD) and Linux (GNU).
sed_inplace() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}
