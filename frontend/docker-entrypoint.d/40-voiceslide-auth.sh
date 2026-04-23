#!/bin/sh
# Runs before nginx starts (nginx base image sources *.sh files in
# /docker-entrypoint.d/ in order). Regenerates /etc/nginx/conf.d/default.conf
# from the baked-in template on every boot so BASIC_AUTH_* can be toggled
# cleanly by restarting the container.
set -e

CONF=/etc/nginx/conf.d/default.conf
TEMPLATE="${CONF}.template"
HTPASSWD=/etc/nginx/.htpasswd

if [ ! -f "$TEMPLATE" ]; then
    echo "[voiceslide] template not found at $TEMPLATE; skipping auth setup" >&2
    exit 0
fi

cp "$TEMPLATE" "$CONF"

if [ -n "$BASIC_AUTH_USERNAME" ] && [ -n "$BASIC_AUTH_PASSWORD" ]; then
    htpasswd -bc "$HTPASSWD" "$BASIC_AUTH_USERNAME" "$BASIC_AUTH_PASSWORD" >/dev/null 2>&1
    # nginx workers run as the ``nginx`` user; file must be readable by them.
    chown nginx:nginx "$HTPASSWD" 2>/dev/null || true
    chmod 644 "$HTPASSWD"
    sed -i \
        "s|#AUTH_MARKER|auth_basic \"VoiceSlide\"; auth_basic_user_file ${HTPASSWD};|g" \
        "$CONF"
    echo "[voiceslide] Basic auth enabled for user '$BASIC_AUTH_USERNAME'"
else
    rm -f "$HTPASSWD"
    echo "[voiceslide] Basic auth disabled (BASIC_AUTH_USERNAME / BASIC_AUTH_PASSWORD not set)"
fi
