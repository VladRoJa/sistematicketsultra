#!/bin/sh

set -u

CERT_FILE="${SSL_CERT_FILE:-/etc/letsencrypt/live/suiteultragym.com/fullchain.pem}"
CHECK_INTERVAL="${NGINX_CERT_RELOAD_INTERVAL_SECONDS:-300}"

certificate_checksum() {
  cksum "$CERT_FILE" 2>/dev/null | awk '{ print $1 ":" $2 }'
}

if [ ! -r "$CERT_FILE" ]; then
  echo "Certificate watcher disabled: $CERT_FILE is not readable."
  exit 0
fi

(
  last_checksum="$(certificate_checksum)"

  while sleep "$CHECK_INTERVAL"; do
    if [ ! -r "$CERT_FILE" ]; then
      echo "Certificate watcher: $CERT_FILE is temporarily unavailable." >&2
      continue
    fi

    current_checksum="$(certificate_checksum)"

    if [ -n "$current_checksum" ] && [ "$current_checksum" != "$last_checksum" ]; then
      echo "TLS certificate change detected; validating Nginx configuration."

      if nginx -t && nginx -s reload; then
        last_checksum="$current_checksum"
        echo "Nginx reloaded with the renewed TLS certificate."
      else
        echo "Nginx reload failed; certificate watcher will retry." >&2
      fi
    fi
  done
) &

exit 0
