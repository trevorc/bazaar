#!/bin/sh

if [ $# -ne 1 ]; then
  echo >&2 "error: must supply exactly one positional argument"
  cat <<EOF
Usage: $0 ARCHIVE_DIR
EOF
  exit 1
fi

ARCHIVE_DIR="$(cd "$1"; pwd -P)"

cd "$(dirname "$0")/.."

cat "$ARCHIVE_DIR"/* |
./explodejson.py
