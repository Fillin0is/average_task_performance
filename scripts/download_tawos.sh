#!/usr/bin/env bash
set -euo pipefail

readonly TAWOS_URL="https://ndownloader.figshare.com/files/37806375"
readonly TAWOS_MD5="e9c5ecc7649d55f0cf2fb4efb5664494"
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly DATA_DIR="${PROJECT_DIR}/data/raw/tawos"
readonly ARCHIVE_PATH="${DATA_DIR}/TAWOS.sql.zip"
readonly PART_PATH="${ARCHIVE_PATH}.part"
readonly SQL_PATH="${DATA_DIR}/TAWOS.sql"

mkdir -p "${DATA_DIR}"

if [[ -f "${SQL_PATH}" ]]; then
  echo "TAWOS is already extracted: ${SQL_PATH}"
  exit 0
fi

if [[ ! -f "${ARCHIVE_PATH}" ]]; then
  echo "Downloading TAWOS v1.1 (about 608 MiB)..."
  download_attempt=1
  until curl \
      --fail \
      --location \
      --continue-at - \
      --output "${PART_PATH}" \
      "${TAWOS_URL}"; do
    if (( download_attempt >= 20 )); then
      echo "Download failed after ${download_attempt} attempts." >&2
      exit 1
    fi
    download_attempt=$((download_attempt + 1))
    echo "Connection interrupted; resuming in 3 seconds (attempt ${download_attempt}/20)..."
    sleep 3
  done
  mv "${PART_PATH}" "${ARCHIVE_PATH}"
fi

echo "Verifying archive checksum..."
printf '%s  %s\n' "${TAWOS_MD5}" "${ARCHIVE_PATH}" | md5sum --check --status

echo "Extracting TAWOS.sql..."
unzip -q -n "${ARCHIVE_PATH}" -d "${DATA_DIR}"

if [[ ! -f "${SQL_PATH}" ]]; then
  echo "Expected file was not found after extraction: ${SQL_PATH}" >&2
  exit 1
fi

echo "TAWOS is ready: ${SQL_PATH}"
du -h "${ARCHIVE_PATH}" "${SQL_PATH}"
