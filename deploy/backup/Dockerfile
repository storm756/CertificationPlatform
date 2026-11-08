# Backup / cron container: pg_dump 17 + age (encryption) + rclone (upload). Runs as non-root.
FROM postgres:17

RUN apt-get update \
    && apt-get install -y --no-install-recommends age rclone ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10002 --home-dir /home/backup --create-home backup \
    && mkdir -p /backups && chown backup /backups

COPY --chmod=0755 run.sh db-backup.sh media-backup.sh /usr/local/bin/

USER backup
ENV TZ=UTC
HEALTHCHECK --interval=10m --timeout=10s --start-period=2h \
  CMD find /backups/.last_ok_db -mmin -150 | grep -q . || exit 1

ENTRYPOINT ["/usr/local/bin/run.sh"]
