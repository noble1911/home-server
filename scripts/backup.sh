#!/bin/bash
# HomeServer Backup Script
# Backs up PostgreSQL databases and Docker config volumes to ~/ServerBackups/
# Run manually or via launchd (installed by 14-backup.sh)
set -eo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
BACKUP_DIR="${BACKUP_DIR:-$HOME/ServerBackups}"
DATE=$(date +%Y-%m-%d)
DAY_OF_WEEK=$(date +%u)  # 1=Monday, 7=Sunday
DAILY_RETENTION=7
WEEKLY_RETENTION=4
STORAGE_WARN_MB="${STORAGE_WARN_MB:-15360}"  # 15GB default

DB_DIR="${BACKUP_DIR}/databases"
CONFIG_DIR="${BACKUP_DIR}/configs"
WEEKLY_DIR="${BACKUP_DIR}/weekly"
LOG_FILE="${BACKUP_DIR}/backup.log"

# Docker config volumes to back up
CONFIG_VOLUMES=(
    jellyfin-config
    radarr-config
    sonarr-config
    bazarr-config
    audiobookshelf-config
    audiobookshelf-metadata
    prowlarr-config
    qbittorrent-config
    homeassistant-config
    nextcloud-data
    shelfarr-data
)

# Logging helper — writes to both stdout and log file
log() {
    echo -e "$1"
    echo -e "$1" | sed 's/\x1b\[[0-9;]*m//g' >> "$LOG_FILE" 2>/dev/null
}

# ─────────────────────────────────────────────
# Prerequisites
# ─────────────────────────────────────────────

if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    log "${RED}✗${NC} Docker is not running. Cannot back up."
    exit 1
fi

mkdir -p "$DB_DIR" "$CONFIG_DIR" "$WEEKLY_DIR/databases" "$WEEKLY_DIR/configs"

log ""
log "${BLUE}==>${NC} Starting HomeServer backup (${DATE})"
log "    Target: ${BACKUP_DIR}"
log ""

ERRORS=0
SKIPPED=0
BACKED_UP=0

# ─────────────────────────────────────────────
# 1. PostgreSQL backup (Immich + Nextcloud)
# ─────────────────────────────────────────────

log "${BLUE}==>${NC} Backing up PostgreSQL databases..."

if docker ps --format '{{.Names}}' | grep -q '^immich-postgres$'; then
    DUMP_FILE="${DB_DIR}/immich-db-${DATE}.sql.gz"
    if docker exec immich-postgres pg_dumpall -U postgres 2>/dev/null | gzip > "$DUMP_FILE"; then
        SIZE=$(du -h "$DUMP_FILE" | cut -f1)
        log "  ${GREEN}✓${NC} immich-db-${DATE}.sql.gz (${SIZE})"
        BACKED_UP=$((BACKED_UP + 1))
    else
        log "  ${RED}✗${NC} PostgreSQL dump failed"
        rm -f "$DUMP_FILE"
        ERRORS=$((ERRORS + 1))
    fi
else
    log "  ${YELLOW}⚠${NC} immich-postgres not running — skipped"
    SKIPPED=$((SKIPPED + 1))
fi

# ─────────────────────────────────────────────
# 2. Docker volume backups
# ─────────────────────────────────────────────

log ""
log "${BLUE}==>${NC} Backing up Docker config volumes..."

for VOLUME in "${CONFIG_VOLUMES[@]}"; do
    # Check if volume exists
    if ! docker volume inspect "$VOLUME" &>/dev/null; then
        log "  ${YELLOW}⚠${NC} ${VOLUME} — volume not found, skipped"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    TAR_FILE="${CONFIG_DIR}/${VOLUME}-${DATE}.tar.gz"

    if docker run --rm -v "${VOLUME}:/data:ro" alpine tar czf - -C / data > "$TAR_FILE" 2>/dev/null; then
        SIZE=$(du -h "$TAR_FILE" | cut -f1)
        log "  ${GREEN}✓${NC} ${VOLUME}-${DATE}.tar.gz (${SIZE})"
        BACKED_UP=$((BACKED_UP + 1))
    else
        log "  ${RED}✗${NC} ${VOLUME} — backup failed"
        rm -f "$TAR_FILE"
        ERRORS=$((ERRORS + 1))
    fi
done

# ─────────────────────────────────────────────
# 3. Weekly promotion (Sunday)
# ─────────────────────────────────────────────

if [[ "$DAY_OF_WEEK" == "7" ]]; then
    log ""
    log "${BLUE}==>${NC} Sunday — promoting to weekly backups..."

    for f in "${DB_DIR}"/*-"${DATE}".*; do
        [[ -f "$f" ]] && cp "$f" "${WEEKLY_DIR}/databases/" && log "  ${GREEN}✓${NC} $(basename "$f") → weekly"
    done
    for f in "${CONFIG_DIR}"/*-"${DATE}".*; do
        [[ -f "$f" ]] && cp "$f" "${WEEKLY_DIR}/configs/" && log "  ${GREEN}✓${NC} $(basename "$f") → weekly"
    done
fi

# ─────────────────────────────────────────────
# 4. Retention enforcement
# ─────────────────────────────────────────────

log ""
log "${BLUE}==>${NC} Enforcing retention policy..."

CLEANED=0

# Clean daily backups older than DAILY_RETENTION days
while IFS= read -r old_file; do
    rm -f "$old_file"
    log "  ${GREEN}✓${NC} Removed old daily: $(basename "$old_file")"
    CLEANED=$((CLEANED + 1))
done < <(find "$DB_DIR" "$CONFIG_DIR" -maxdepth 1 -name "*.gz" -mtime +${DAILY_RETENTION} -type f 2>/dev/null)

# Clean weekly backups older than WEEKLY_RETENTION weeks
WEEKLY_DAYS=$((WEEKLY_RETENTION * 7))
while IFS= read -r old_file; do
    rm -f "$old_file"
    log "  ${GREEN}✓${NC} Removed old weekly: $(basename "$old_file")"
    CLEANED=$((CLEANED + 1))
done < <(find "$WEEKLY_DIR" -name "*.gz" -mtime +${WEEKLY_DAYS} -type f 2>/dev/null)

if [[ $CLEANED -eq 0 ]]; then
    log "  ${GREEN}✓${NC} Nothing to clean up"
fi

# ─────────────────────────────────────────────
# 5. Storage budget check
# ─────────────────────────────────────────────

log ""
log "${BLUE}==>${NC} Checking storage usage..."

TOTAL_KB=$(du -sk "$BACKUP_DIR" 2>/dev/null | cut -f1)
TOTAL_MB=$((TOTAL_KB / 1024))
TOTAL_HUMAN=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)

if [[ $TOTAL_MB -gt $STORAGE_WARN_MB ]]; then
    log "  ${RED}✗${NC} Backup storage: ${TOTAL_HUMAN} — exceeds ${STORAGE_WARN_MB}MB warning threshold!"
    log "    Review and clean up: ${BACKUP_DIR}"
else
    log "  ${GREEN}✓${NC} Backup storage: ${TOTAL_HUMAN} (limit: $((STORAGE_WARN_MB / 1024))GB)"
fi

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────

log ""
log "────────────────────────────────────────"
log "  Backed up: ${BACKED_UP}  Skipped: ${SKIPPED}  Errors: ${ERRORS}"
log "  Storage:   ${TOTAL_HUMAN}"
log "────────────────────────────────────────"

if [[ $ERRORS -gt 0 ]]; then
    log "${YELLOW}⚠${NC} Backup completed with ${ERRORS} error(s)"
    exit 1
else
    log "${GREEN}✓${NC} Backup complete"
fi
