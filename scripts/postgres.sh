#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
export DOCKER_HOST=unix:///var/run/docker.sock
unset DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH
NAME=wain-catalog-postgres
IMAGE="${WAIN_POSTGRES_IMAGE:-postgres:17-bookworm@sha256:839fbb5a4942a7758dd93e18b42ea5649807491a0545b5eeeb8f0b8bb11857a5}"
mkdir -p .local/pgdata .local/run
chmod 700 .local/pgdata .local/run
case "${1:-start}" in
 start)
  if docker container inspect "$NAME" >/dev/null 2>&1; then
    docker start "$NAME" >/dev/null
  else
    if [ ! -f .local/pgpassword ]; then
      (umask 077; python -c 'import secrets; print(secrets.token_urlsafe(48))' > .local/pgpassword)
    fi
    docker run -d --name "$NAME" --user "$(id -u):$(id -g)" --network none \
      -e POSTGRES_USER=wain -e POSTGRES_DB=wain -e PGHOST=/run/wain \
      -e POSTGRES_PASSWORD_FILE=/run/pgpassword \
      -e 'POSTGRES_INITDB_ARGS=--auth-local=trust --auth-host=scram-sha-256' \
      --mount "type=bind,src=$ROOT/.local/pgdata,dst=/var/lib/postgresql/data" \
      --mount "type=bind,src=$ROOT/.local/run,dst=/run/wain" \
      --mount "type=bind,src=$ROOT/.local/pgpassword,dst=/run/pgpassword,readonly" \
      "$IMAGE" -c listen_addresses= -c unix_socket_directories=/run/wain >/dev/null
  fi
  for attempt in {1..30}; do
    if docker exec "$NAME" sh -c '[ "$(cat /proc/1/comm)" = postgres ] && pg_isready -h /run/wain -U wain -d postgres' >/dev/null 2>&1; then
      if [ "$(docker exec "$NAME" psql -h /run/wain -U wain -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname='wain'")" = 0 ]; then
        docker exec "$NAME" createdb -h /run/wain -U wain wain
      fi
      echo 'PostgreSQL ready (private Unix socket; no TCP port published)'
      exit 0
    fi
    sleep 1
  done
  docker logs --tail 30 "$NAME"
  exit 1
  ;;
 stop) docker stop "$NAME" ;;
 backup)
  mkdir -p .local/backups
  docker exec "$NAME" pg_dump -h /run/wain -U wain -d wain -Fc > .local/backups/wain.dump
  echo '.local/backups/wain.dump'
  ;;
 *) echo 'Usage: bash scripts/postgres.sh start|stop|backup' >&2; exit 2 ;;
esac
