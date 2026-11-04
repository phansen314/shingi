#!/usr/bin/env bash
# Runs every test file against the real koan on PATH. Each test gets a scratch
# HOME, so nothing here touches your own koan root.
set -uo pipefail

cd "$(dirname "$0")" || exit 1
status=0
for file in test_*.sh; do
	bash "$file" || status=1
done
exit "$status"
