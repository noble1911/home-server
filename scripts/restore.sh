#!/bin/bash
# HomeServer Restore Script
# Restores backups created by backup.sh
#
# Usage:
#   ./scripts/restore.sh --list                              # Show available backups
#   ./scripts/restore.sh --service jellyfin-config --date 2026-02-05  # Restore one service
#   ./scripts/restore.sh --service immich-db --date 2026-02-05       # Restore PostgreSQL
#   ./scripts/restore.sh --all --date 2026-02-05                     # Restore everything
#   ./scripts/restore.sh --weekly --service ... --date ...           # Restore from weekly backup
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

BACKUP_DIR="${BACKUP_DIR:-$HOME/ServerBackups}"

# Volume → container name mapping (for stop/start during restore)
declare -A VOLUME_CONTAINER=(
    [jellyfin-config]=jellyfin
    [radarr-config]=radarr
    [sonarr-config]=sonarr
    [bazarr-config]=bazarr
    [seerr-config]=seerr
    [audiobookshelf-config]=audiobookshelf
    [audiobookshelf-metadata]=audiobookshelf
    [prowlarr-config]=prowlarr
    [qbittorrent-config]=qbittorrent
    [homeassistant-config]=homeassistant
    [nextcloud-data]=nextcloud
    [lazylibrarian-config]=lazylibrarian
)

# ─────────────────────────────────────────────
# Parse arguments
# ─────────────────────────────────────────────

ACTION=""
SERVICE=""
RESTORE_DATE=""
USE_WEEKLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --list)
            ACTION="list"
            shift
            ;;
        --service)
            SERVICE="$2"
            shift 2
            ;;
        --date)
            RESTORE_DATE="$2"
            shift 2
            ;;
        --all)
            ACTION="all"
            shift
            ;;
        --weekly)
            USE_WEEKLY=true
            shift
            ;;
        *)
            echo -e "${RED}✗${NC} Unknown option: $1"
            echo "Usage: $0 --list | --service NAME --date YYYY-MM-DD | --all --date YYYY-MM-DD"
            exit 1
            ;;
    esac
done

# ─────────────────────────────────────────────
# --list: Show available backups
# ─────────────────────────────────────────────

list_backups() {
    echo -e "${BLUE}==>${NC} Available backups in ${BACKUP_DIR}"
    echo ""

    echo -e "${BLUE}Daily Backups:${NC}"
    if ls "$BACKUP_DIR"/databases/*.gz "$BACKUP_DIR"/configs/*.gz &>/dev/null 2>&1; then
        # Extract unique dates from filenames
        dates=$(ls "$BACKUP_DIR"/databases/ "$BACKUP_DIR"/configs/ 2>/dev/null \
            | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | sort -u -r)

        for d in $dates; do
            db_count=$(ls "$BACKUP_DIR"/databases/*-"${d}".* 2>/dev/null | wc -l | tr -d ' ')
            cfg_count=$(ls "$BACKUP_DIR"/configs/*-"${d}".* 2>/dev/null | wc -l | tr -d ' ')
            total_size=$(du -ch "$BACKUP_DIR"/databases/*-"${d}".* "$BACKUP_DIR"/configs/*-"${d}".* 2>/dev/null | tail -1 | cut -f1)
            echo -e "  ${GREEN}✓${NC} ${d}  —  ${db_count} database(s), ${cfg_count} config(s)  [${total_size}]"
        done
    else
        echo -e "  ${YELLOW}⚠${NC} No daily backups found"
    fi

    echo ""
    echo -e "${BLUE}Weekly Backups:${NC}"
    if ls "$BACKUP_DIR"/weekly/databases/*.gz "$BACKUP_DIR"/weekly/configs/*.gz &>/dev/null 2>&1; then
        dates=$(ls "$BACKUP_DIR"/weekly/databases/ "$BACKUP_DIR"/weekly/configs/ 2>/dev/null \
            | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' | sort -u -r)

        for d in $dates; do
            total_size=$(du -ch "$BACKUP_DIR"/weekly/databases/*-"${d}".* "$BACKUP_DIR"/weekly/configs/*-"${d}".* 2>/dev/null | tail -1 | cut -f1)
            echo -e "  ${GREEN}✓${NC} ${d}  [${total_size}]  (weekly)"
        done
    else
        echo -e "  ${YELLOW}⚠${NC} No weekly backups found"
    fi

    echo ""
    TOTAL=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)
    echo -e "  Total storage used: ${TOTAL}"
}

# ─────────────────────────────────────────────
# Restore PostgreSQL
# ─────────────────────────────────────────────

restore_postgres() {
    local dump_file="$1"

    echo -e "${BLUE}==>${NC} Restoring PostgreSQL from $(basename "$dump_file")..."

    if ! docker ps --format '{{.Names}}' | grep -q '^immich-postgres$'; then
        echo -e "${RED}✗${NC} immich-postgres is not running. Start it first."
        return 1
    fi

    echo -e "  ${YELLOW}⚠${NC} This will OVERWRITE all PostgreSQL databases (immich, nextcloud, butler)."
    echo -n "  Continue? [y/N] "
    read -r confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "  ${YELLOW}⚠${NC} Skipped PostgreSQL restore"
        return 0
    fi

    if gunzip -c "$dump_file" | docker exec -i immich-postgres psql -U postgres -q 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} PostgreSQL restored"
    else
        echo -e "  ${RED}✗${NC} PostgreSQL restore failed (some non-fatal errors are normal)"
    fi
}

# ─────────────────────────────────────────────
# Restore Docker volume
# ─────────────────────────────────────────────

restore_volume() {
    local volume="$1"
    local tar_file="$2"
    local container="${VOLUME_CONTAINER[$volume]}"

    echo -e "${BLUE}==>${NC} Restoring ${volume} from $(basename "$tar_file")..."

    if ! docker volume inspect "$volume" &>/dev/null; then
        echo -e "  ${YELLOW}⚠${NC} Volume ${volume} doesn't exist — creating it"
        docker volume create "$volume" &>/dev/null
    fi

    echo -e "  ${YELLOW}⚠${NC} This will OVERWRITE the contents of volume: ${volume}"
    echo -n "  Continue? [y/N] "
    read -r confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "  ${YELLOW}⚠${NC} Skipped ${volume}"
        return 0
    fi

    # Stop the container if it's running
    local was_running=false
    if [[ -n "$container" ]] && docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        echo -e "  Stopping ${container}..."
        docker stop "$container" &>/dev/null
        was_running=true
    fi

    # Restore: clear volume and extract tarball
    if docker run --rm -i -v "${volume}:/data" alpine sh -c "find /data -mindepth 1 -delete && tar xzf - -C /" < "$tar_file"; then
        echo -e "  ${GREEN}✓${NC} ${volume} restored"
    else
        echo -e "  ${RED}✗${NC} ${volume} restore failed"
    fi

    # Restart the container if it was running
    if $was_running; then
        echo -e "  Starting ${container}..."
        docker start "$container" &>/dev/null
        echo -e "  ${GREEN}✓${NC} ${container} restarted"
    fi
}

# ─────────────────────────────────────────────
# Resolve backup source directory
# ─────────────────────────────────────────────

get_source_dirs() {
    if $USE_WEEKLY; then
        echo "${BACKUP_DIR}/weekly/databases" "${BACKUP_DIR}/weekly/configs"
    else
        echo "${BACKUP_DIR}/databases" "${BACKUP_DIR}/configs"
    fi
}

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if [[ "$ACTION" == "list" ]]; then
    list_backups
    exit 0
fi

# Validate Docker
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}✗${NC} Docker is not running."
    exit 1
fi

# Validate date
if [[ -z "$RESTORE_DATE" ]]; then
    echo -e "${RED}✗${NC} --date YYYY-MM-DD is required"
    echo "Usage: $0 --service NAME --date YYYY-MM-DD"
    echo "       $0 --all --date YYYY-MM-DD"
    echo "       $0 --list"
    exit 1
fi

read -r SRC_DB SRC_CFG <<< "$(get_source_dirs)"

if [[ "$ACTION" == "all" ]]; then
    echo -e "${BLUE}==>${NC} Restoring ALL services from ${RESTORE_DATE}"
    echo -e "  ${YELLOW}⚠${NC} This is a full restore. Each service will ask for confirmation."
    echo ""

    # PostgreSQL
    PG_FILE="${SRC_DB}/immich-db-${RESTORE_DATE}.sql.gz"
    if [[ -f "$PG_FILE" ]]; then
        restore_postgres "$PG_FILE"
        echo ""
    fi

    # Config volumes
    for VOLUME in "${!VOLUME_CONTAINER[@]}"; do
        TAR_FILE="${SRC_CFG}/${VOLUME}-${RESTORE_DATE}.tar.gz"
        if [[ -f "$TAR_FILE" ]]; then
            restore_volume "$VOLUME" "$TAR_FILE"
            echo ""
        fi
    done

    echo -e "${GREEN}✓${NC} Full restore complete"

elif [[ -n "$SERVICE" ]]; then
    # Single service restore
    if [[ "$SERVICE" == "immich-db" ]]; then
        PG_FILE="${SRC_DB}/immich-db-${RESTORE_DATE}.sql.gz"
        if [[ ! -f "$PG_FILE" ]]; then
            echo -e "${RED}✗${NC} Backup not found: ${PG_FILE}"
            exit 1
        fi
        restore_postgres "$PG_FILE"
    else
        TAR_FILE="${SRC_CFG}/${SERVICE}-${RESTORE_DATE}.tar.gz"
        if [[ ! -f "$TAR_FILE" ]]; then
            echo -e "${RED}✗${NC} Backup not found: ${TAR_FILE}"
            exit 1
        fi
        restore_volume "$SERVICE" "$TAR_FILE"
    fi

    echo ""
    echo -e "${GREEN}✓${NC} Restore complete"
else
    echo -e "${RED}✗${NC} Specify --service NAME, --all, or --list"
    echo "Usage: $0 --service NAME --date YYYY-MM-DD"
    echo "       $0 --all --date YYYY-MM-DD"
    echo "       $0 --list"
    exit 1
fi
