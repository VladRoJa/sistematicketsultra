#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Suite Ultra - Instalador idempotente de backup PostgreSQL
# ============================================================
#
# Este instalador:
# - valida el script canónico antes de instalarlo;
# - exige /root/.pgpass con permisos 600;
# - exige la configuración rclone existente;
# - instala /usr/local/bin/backup_postgres.sh;
# - conserva el resto del crontab de root;
# - asegura exactamente una entrada cron para este backup;
# - NO ejecuta el backup.
# ============================================================

TARGET_SCRIPT="/usr/local/bin/backup_postgres.sh"
PGPASS_FILE="/root/.pgpass"
RCLONE_CONFIG_FILE="/home/adminrdp/.config/rclone/rclone.conf"

CRON_SCHEDULE="15 2 * * *"
LOG_FILE="/var/log/backup_postgres.log"

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" \
    && pwd
)"

SOURCE_SCRIPT="${SCRIPT_DIR}/backup_postgres.sh"

TEMP_CURRENT_CRON=""
TEMP_NEW_CRON=""


log() {
    printf '%s %s\n' \
        "$(date '+%Y-%m-%d %H:%M:%S')" \
        "$*"
}


cleanup() {
    if [[ -n "$TEMP_CURRENT_CRON" ]]; then
        rm -f -- "$TEMP_CURRENT_CRON"
    fi

    if [[ -n "$TEMP_NEW_CRON" ]]; then
        rm -f -- "$TEMP_NEW_CRON"
    fi
}


require_root() {
    if (( EUID != 0 )); then
        log "ERROR: este instalador debe ejecutarse como root."
        exit 1
    fi
}


validate_source() {
    if [[ ! -f "$SOURCE_SCRIPT" ]]; then
        log \
            "ERROR: no existe script fuente: " \
            "${SOURCE_SCRIPT}"
        exit 1
    fi

    bash -n "$SOURCE_SCRIPT"

    log "Sintaxis del script fuente validada."

    log "Ejecutando preflight del script fuente."

    env \
        HOME=/root \
        PGPASSFILE="$PGPASS_FILE" \
        RCLONE_CONFIG="$RCLONE_CONFIG_FILE" \
        bash "$SOURCE_SCRIPT" --preflight

    log "Preflight del script fuente validado."
}


validate_credentials() {
    if [[ ! -f "$PGPASS_FILE" ]]; then
        log \
            "ERROR: no existe archivo de credenciales: " \
            "${PGPASS_FILE}"
        exit 1
    fi

    local mode
    mode="$(
        stat -c '%a' "$PGPASS_FILE"
    )"

    if [[ "$mode" != "600" ]]; then
        log \
            "ERROR: ${PGPASS_FILE} debe tener permisos 600; " \
            "actual=${mode}."
        exit 1
    fi

    if [[ ! -f "$RCLONE_CONFIG_FILE" ]]; then
        log \
            "ERROR: no existe configuración rclone: " \
            "${RCLONE_CONFIG_FILE}"
        exit 1
    fi

    log "Credenciales externas validadas."
}


install_script() {
    if [[ -f "$TARGET_SCRIPT" ]] \
        && cmp -s "$SOURCE_SCRIPT" "$TARGET_SCRIPT"; then
        log "Script ya instalado y sin cambios."
        return 0
    fi

    install \
        -o root \
        -g root \
        -m 0755 \
        "$SOURCE_SCRIPT" \
        "$TARGET_SCRIPT"

    log "Script instalado: ${TARGET_SCRIPT}"
}


install_cron() {
    local cron_line

    cron_line="$(
        printf \
            '%s %s >> %s 2>&1' \
            "$CRON_SCHEDULE" \
            "$TARGET_SCRIPT" \
            "$LOG_FILE"
    )"

    TEMP_CURRENT_CRON="$(
        mktemp
    )"

    TEMP_NEW_CRON="$(
        mktemp
    )"

    crontab -l \
        > "$TEMP_CURRENT_CRON" \
        2>/dev/null \
        || true

    awk \
        -v target="$TARGET_SCRIPT" \
        'index($0, target) == 0 { print }' \
        "$TEMP_CURRENT_CRON" \
        > "$TEMP_NEW_CRON"

    printf '%s\n' \
        "$cron_line" \
        >> "$TEMP_NEW_CRON"

    if cmp -s "$TEMP_CURRENT_CRON" "$TEMP_NEW_CRON"; then
        log "Cron ya configurado y sin cambios."
        return 0
    fi

    crontab "$TEMP_NEW_CRON"

    log "Cron instalado: ${cron_line}"
}


prepare_log() {
    touch "$LOG_FILE"

    chown root:root "$LOG_FILE"
    chmod 0640 "$LOG_FILE"

    log "Log preparado: ${LOG_FILE}"
}


main() {
    trap cleanup EXIT

    require_root
    validate_credentials
    validate_source

    install_script
    prepare_log
    install_cron

    log "Instalación completada."
    log "El backup NO fue ejecutado por este instalador."
}


main "$@"
