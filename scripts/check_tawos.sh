#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}"

for readiness_attempt in {1..60}; do
  if docker compose -f docker/docker-compose.tawos.yaml exec -T \
      --env MYSQL_PWD="${TAWOS_MYSQL_PASSWORD:-tawos_dev_password}" \
      mysql \
      mysqladmin ping \
      --user="${TAWOS_MYSQL_USER:-tawos}" \
      --silent >/dev/null 2>&1; then
    break
  fi

  if (( readiness_attempt == 60 )); then
    echo "MySQL did not become ready within 120 seconds." >&2
    exit 1
  fi
  sleep 2
done

docker compose -f docker/docker-compose.tawos.yaml exec -T \
  --env MYSQL_PWD="${TAWOS_MYSQL_PASSWORD:-tawos_dev_password}" \
  mysql \
  mysql \
  --user="${TAWOS_MYSQL_USER:-tawos}" \
  --database="${TAWOS_MYSQL_DATABASE:-tawos}" \
  --execute="
    SELECT COUNT(*) AS issues FROM Issue;
    SELECT COUNT(*) AS projects FROM Project;
    SELECT
      COUNT(Resolution_Time_Minutes) AS issues_with_resolution_time,
      ROUND(AVG(Resolution_Time_Minutes) / 60 / 24, 2) AS mean_resolution_days,
      ROUND(MIN(Resolution_Time_Minutes) / 60 / 24, 2) AS min_resolution_days,
      ROUND(MAX(Resolution_Time_Minutes) / 60 / 24, 2) AS max_resolution_days
    FROM Issue;
  "
