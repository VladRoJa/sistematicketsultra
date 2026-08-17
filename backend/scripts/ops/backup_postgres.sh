#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Suite Ultra - PostgreSQL base backup
# ============================================================
#
# Contrato:
# - La autenticación PostgreSQL debe existir fuera del repo
#   mediante ~/.pgpass del usuario que ejecuta este script.
# - El backup usa WAL streaming (-X stream), por lo que el
#   resultado no depende de un wal-archive externo.
# - La retención local es por cantidad, no por antigüedad.
# - Un fallo de subida remota NO impide la limpieza local.
# - Nunca se eliminan los últimos KEEP_LOCAL_BACKUPS backups.
# ============================================================

PGUSER="${PGUSER:-postgres}"
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"

BASE_DIR="${BASE_DIR:-/root/base-backups}"
KEEP_LOCAL_BACKUPS="${KEEP_LOCAL_BACKUPS:-7}"

RCLONE_CONFIG="${RCLONE_CONFIG:-/home/adminrdp/.config/rclone/rclone.conf}"
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive:sistematickets-backups/base}"

MIN_FREE_GB="${MIN_FREE_GB:-60}"

TIMESTAMP="$(date +%F_%H%M%S)"
BACKUP_NAME="base_${TIMESTAMP}"
BACKUP_DIR="${BASE_DIR}/${BACKUP_NAME}"
TAR_FILE="${BASE_DIR}/${BACKUP_NAME}.tar.gz"
TAR_PARTIAL="${TAR_FILE}.partial"

LOCK_FILE="${BASE_DIR}/.backup_postgres.lock"

PG_SERVER_MAJOR="${PG_SERVER_MAJOR:-}"
PG_VERIFY_IMAGE="${PG_VERIFY_IMAGE:-}"


log() {
    printf '%s %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" \
        "$*"
}


require_command() {
    local command_name="$1"

    if ! command -v "$command_name" >/dev/null 2>&1; then
        log "ERROR: comando requerido no disponible: ${command_name}"
        exit 1
    fi
}


resolve_pg_server_major() {
    local server_version_num

    if [[ -n "$PG_SERVER_MAJOR" ]]; then
        if ! [[ "$PG_SERVER_MAJOR" =~ ^[1-9][0-9]*$ ]]; then
            log "ERROR: PG_SERVER_MAJOR debe ser entero positivo."
            exit 1
        fi

        return 0
    fi

    server_version_num="$(
        psql \
            -h "$PGHOST" \
            -p "$PGPORT" \
            -U "$PGUSER" \
            -d postgres \
            -Atqc \
            "SHOW server_version_num;"
    )"

    if ! [[ "$server_version_num" =~ ^[0-9]+$ ]]; then
        log \
            "ERROR: no se pudo determinar server_version_num."
        exit 1
    fi

    PG_SERVER_MAJOR=$(( server_version_num / 10000 ))

    if (( PG_SERVER_MAJOR < 10 )); then
        log \
            "ERROR: versión PostgreSQL no soportada por este flujo: " \
            "${server_version_num}"
        exit 1
    fi

    log \
        "Versión mayor PostgreSQL servidor: " \
        "${PG_SERVER_MAJOR}"
}


resolve_pg_verify_image() {
    if [[ -z "$PG_VERIFY_IMAGE" ]]; then
        PG_VERIFY_IMAGE="postgres:${PG_SERVER_MAJOR}"
    fi

    if ! docker image inspect \
        "$PG_VERIFY_IMAGE" \
        >/dev/null 2>&1; then
        log \
            "ERROR: imagen PostgreSQL para verificación no disponible: " \
            "${PG_VERIFY_IMAGE}"
        exit 1
    fi

    log \
        "Imagen PostgreSQL para verificación: " \
        "${PG_VERIFY_IMAGE}"
}


validate_pg_verify_image_tools() {
    local verify_version
    local waldump_version
    local verify_major
    local waldump_major

    if ! verify_version="$(
        docker run \
            --rm \
            --pull=never \
            --network none \
            "$PG_VERIFY_IMAGE" \
            pg_verifybackup \
            --version
    )"; then
        log \
            "ERROR: pg_verifybackup no funciona en imagen: " \
            "${PG_VERIFY_IMAGE}"
        exit 1
    fi

    if ! waldump_version="$(
        docker run \
            --rm \
            --pull=never \
            --network none \
            "$PG_VERIFY_IMAGE" \
            pg_waldump \
            --version
    )"; then
        log \
            "ERROR: pg_waldump no funciona en imagen: " \
            "${PG_VERIFY_IMAGE}"
        exit 1
    fi

    if [[ ! "$verify_version" =~ PostgreSQL\)?[[:space:]]+([0-9]+) ]]; then
        log "ERROR: no se pudo leer versión de pg_verifybackup."
        exit 1
    fi

    verify_major="${BASH_REMATCH[1]}"

    if [[ ! "$waldump_version" =~ PostgreSQL\)?[[:space:]]+([0-9]+) ]]; then
        log "ERROR: no se pudo leer versión de pg_waldump."
        exit 1
    fi

    waldump_major="${BASH_REMATCH[1]}"

    if [[ "$verify_major" != "$PG_SERVER_MAJOR" ]] \
        || [[ "$waldump_major" != "$PG_SERVER_MAJOR" ]]; then
        log \
            "ERROR: versión de herramientas no coincide con servidor. " \
            "servidor=${PG_SERVER_MAJOR} " \
            "pg_verifybackup=${verify_major} " \
            "pg_waldump=${waldump_major}"
        exit 1
    fi

    log \
        "Herramientas PostgreSQL verificadas para major: " \
        "${PG_SERVER_MAJOR}"
}


validate_configuration() {
    if ! [[ "$KEEP_LOCAL_BACKUPS" =~ ^[1-9][0-9]*$ ]]; then
        log "ERROR: KEEP_LOCAL_BACKUPS debe ser entero >= 1."
        exit 1
    fi

    if ! [[ "$MIN_FREE_GB" =~ ^[1-9][0-9]*$ ]]; then
        log "ERROR: MIN_FREE_GB debe ser entero >= 1."
        exit 1
    fi

    local pgpass_file="${PGPASSFILE:-${HOME}/.pgpass}"

    if [[ ! -f "$pgpass_file" ]]; then
        log "ERROR: no existe archivo de credenciales: ${pgpass_file}"
        exit 1
    fi

    local pgpass_mode
    pgpass_mode="$(
        stat -c '%a' "$pgpass_file"
    )"

    if [[ "$pgpass_mode" != "600" ]]; then
        log "ERROR: ${pgpass_file} debe tener permisos 600."
        exit 1
    fi

    if [[ ! -f "$RCLONE_CONFIG" ]]; then
        log "ERROR: no existe configuración rclone: ${RCLONE_CONFIG}"
        exit 1
    fi
}


validate_free_space() {
    local available_kb
    local database_bytes
    local database_kb
    local dynamic_required_kb
    local minimum_required_kb
    local required_kb

    available_kb="$(
        df -Pk "$BASE_DIR" \
        | awk 'NR == 2 {print $4}'
    )"

    database_bytes="$(
        psql \
            -h "$PGHOST" \
            -p "$PGPORT" \
            -U "$PGUSER" \
            -d postgres \
            -Atqc \
            "SELECT COALESCE(SUM(pg_database_size(datname)), 0)
             FROM pg_database;"
    )"

    if ! [[ "$database_bytes" =~ ^[0-9]+$ ]]; then
        log \
            "ERROR: no se pudo determinar tamaño de PostgreSQL."
        exit 1
    fi

    database_kb=$(( database_bytes / 1024 ))

    minimum_required_kb=$((
        MIN_FREE_GB
        * 1024
        * 1024
    ))

    dynamic_required_kb=$((
        database_kb
        * 2
        + 10
        * 1024
        * 1024
    ))

    if (( dynamic_required_kb > minimum_required_kb )); then
        required_kb="$dynamic_required_kb"
    else
        required_kb="$minimum_required_kb"
    fi

    log \
        "Tamaño lógico PostgreSQL: " \
        "$(( database_kb / 1024 / 1024 ))GB"

    log \
        "Espacio requerido para backup: " \
        "$(( required_kb / 1024 / 1024 ))GB"

    if (( available_kb < required_kb )); then
        log \
            "ERROR: espacio insuficiente. " \
            "libre=$(( available_kb / 1024 / 1024 ))GB " \
            "requerido=$(( required_kb / 1024 / 1024 ))GB"
        exit 1
    fi

    log \
        "Espacio disponible: " \
        "$(( available_kb / 1024 / 1024 ))GB"
}


cleanup_partial_backup() {
    if [[ -d "$BACKUP_DIR" ]]; then
        log "Limpiando backup parcial: ${BACKUP_DIR}"
        rm -rf -- "$BACKUP_DIR"
    fi

    if [[ -f "$TAR_PARTIAL" ]]; then
        log "Limpiando archivo comprimido parcial: ${TAR_PARTIAL}"
        rm -f -- "$TAR_PARTIAL"
    fi
}


create_base_backup() {
    log "Iniciando pg_basebackup: ${BACKUP_NAME}"

    pg_basebackup \
        -h "$PGHOST" \
        -p "$PGPORT" \
        -U "$PGUSER" \
        -D "$BACKUP_DIR" \
        -Fp \
        -P \
        -X stream

    log "pg_basebackup completado."
}


verify_base_backup() {
    log "Verificando integridad del backup base."

    docker run \
        --rm \
        --pull=never \
        --network none \
        --mount \
        "type=bind,src=${BACKUP_DIR},dst=/backup,readonly" \
        "$PG_VERIFY_IMAGE" \
        pg_verifybackup \
        /backup

    log "Verificación del backup completada."
}

compress_backup() {
    log "Comprimiendo backup."

    tar \
        -C "$BASE_DIR" \
        -czf "$TAR_PARTIAL" \
        "$BACKUP_NAME"

    mv -- "$TAR_PARTIAL" "$TAR_FILE"
    rm -rf -- "$BACKUP_DIR"

    log "Backup comprimido: ${TAR_FILE}"
}


upload_backup() {
    log "Subiendo backup a remoto: ${RCLONE_REMOTE}"

    if env RCLONE_CONFIG="$RCLONE_CONFIG" \
        rclone copy \
            "$TAR_FILE" \
            "$RCLONE_REMOTE"; then
        log "Upload remoto completado."
        return 0
    fi

    log "ERROR: falló upload remoto de ${TAR_FILE}"
    return 1
}


prune_local_backups() {
    local -a backups=()
    local delete_count
    local index

    mapfile -t backups < <(
        find "$BASE_DIR" \
            -maxdepth 1 \
            -type f \
            -name 'base_*.tar.gz' \
            -printf '%f\n' \
        | sort
    )

    if (( ${#backups[@]} <= KEEP_LOCAL_BACKUPS )); then
        log \
            "Retención local: " \
            "${#backups[@]} backups; no hay nada que eliminar."
        return 0
    fi

    delete_count=$((
        ${#backups[@]}
        - KEEP_LOCAL_BACKUPS
    ))

    log \
        "Retención local: eliminando ${delete_count}; " \
        "conservando ${KEEP_LOCAL_BACKUPS}."

    for ((index = 0; index < delete_count; index++)); do
        rm -- "${BASE_DIR}/${backups[$index]}"
    done
}


main() {
    require_command pg_basebackup
    require_command psql
    require_command tar
    require_command rclone
    require_command flock
    require_command docker

    mkdir -p "$BASE_DIR"

    validate_configuration
    resolve_pg_server_major
    resolve_pg_verify_image
    validate_pg_verify_image_tools

    if [[ "${1:-}" == "--preflight" ]]; then
        if (( $# != 1 )); then
            log "ERROR: uso inválido de --preflight."
            exit 2
        fi

        validate_free_space

        log "Preflight PostgreSQL backup: OK"
        return 0
    fi

    if (( $# != 0 )); then
        log "ERROR: argumento no reconocido: ${1}"
        log "Uso: backup_postgres.sh [--preflight]"
        exit 2
    fi

    exec 9>"$LOCK_FILE"

    if ! flock -n 9; then
        log "ERROR: ya existe otro backup PostgreSQL en ejecución."
        exit 1
    fi

    validate_free_space

    trap cleanup_partial_backup EXIT

    create_base_backup
    verify_base_backup
    compress_backup

    trap - EXIT

    local upload_status=0

    if ! upload_backup; then
        upload_status=1
    fi

    prune_local_backups

    if (( upload_status != 0 )); then
        log \
            "Backup local completado, pero upload remoto falló."
        exit 1
    fi

    log "Backup PostgreSQL completado correctamente."
}


main "$@"
