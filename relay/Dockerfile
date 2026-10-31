FROM debian:bookworm-slim
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      postfix libsasl2-modules ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 25
VOLUME ["/var/spool/postfix"]
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD postfix status >/dev/null 2>&1 || exit 1
ENTRYPOINT ["/entrypoint.sh"]
