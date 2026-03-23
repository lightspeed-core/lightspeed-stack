#!/usr/bin/env bash
# Recompute sha256 for the archive at artifacts.lock.yaml download_url and update checksum only.
#
# Maintainer flow: set download_url to the GitHub archive URL for the desired commit (and update the
# optional revision comment). Hermeto rejects extra YAML keys (name, type, source, revision) on artifacts.
# Run this script to refresh the checksum line only.
#
# Usage:
#   make konflux-artifacts-lock

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="${ROOT}/artifacts.lock.yaml"
TMP="$(mktemp)"
trap 'rm -f "${TMP}"' EXIT

URL="$(grep -m1 '^[[:space:]]*download_url:' "${LOCK}" | sed -E 's/^[[:space:]]*download_url:[[:space:]]*//' | tr -d "'\"")"
if [[ -z "${URL}" ]]; then
  echo "ERROR: could not parse download_url from ${LOCK}" >&2
  exit 1
fi

echo "Downloading ${URL}"
curl -fsSL "${URL}" -o "${TMP}"
SUM="$(sha256sum "${TMP}" | awk '{print $1}')"

sed -i "s/^\([[:space:]]*checksum: \)sha256:[a-fA-F0-9]*/\1sha256:${SUM}/" "${LOCK}"

echo "Updated checksum in ${LOCK} (sha256:${SUM})"
