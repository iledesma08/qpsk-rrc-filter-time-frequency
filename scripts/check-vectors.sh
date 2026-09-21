#!/usr/bin/env bash
# Verify generated vector files have an unchanged SHA-256 sidecar.
set -euo pipefail

vector_dir="${1:-sim/vectors}"
status=0

for vector in "$vector_dir"/*; do
  [[ -f "$vector" ]] || continue

  case "$vector" in
    */README.md|*.sha256)
      continue
      ;;
  esac

  checksum_file="$vector.sha256"
  if [[ ! -f "$checksum_file" ]]; then
    printf 'Missing checksum for generated vector: %s\n' "$vector" >&2
    status=1
    continue
  fi

  read -r expected_hash _ < "$checksum_file"
  actual_hash=$(sha256sum "$vector")
  actual_hash=${actual_hash%% *}
  if [[ "$actual_hash" != "$expected_hash" ]]; then
    printf 'Checksum mismatch for generated vector: %s\n' "$vector" >&2
    status=1
  fi
done

exit "$status"
