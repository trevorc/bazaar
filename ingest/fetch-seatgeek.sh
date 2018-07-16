#!/bin/sh
#
# fetch-seatgeek.sh - download Seatgeek API

set -e
set -u

if [ -n "${BASH:-}" ]; then
  set -o pipefail
fi

help() {
  cat <<EOF
$0 downloads the latest seatgeek snapshot from the API and
emits it on standard output, as well as writing it to the given
archive directory.

EOF
  usage
}

usage() {
  cat <<EOF
Usage: $0

The ARCHIVE_DIR environment variable must be set. ARCHIVE_DIR governs the
prefix inside of which $0 will archive downloaded info.
EOF
  exit 1
}

version() {
  cat <<EOF
$0 0.1.0

Written by Trevor Caira <trevor@bitba.se>
EOF
}

debug() {
  if [ -n "$DEBUG" ]; then
    echo >&2 "$@"
  fi
}

if [ -z "${ARCHIVE_DIR:-}" ]; then
  echo >&2 "error: ARCHIVE_DIR is unset"
  usage
fi

### Options controlling execution
ingest_base=$(cd "$(dirname "$0")"; pwd -P)
DEBUG=${DEBUG:-}

while getopts "V?" flag; do
  case "$flag" in
    (V) version ;;
    ([?]) help ;;
  esac
done
shift $(($OPTIND-1))

if [ $# -gt 0 ]; then
  echo >&2 "extra positional arguments"
  usage
fi

if [ ! -d "$ARCHIVE_DIR" ]; then
  debug "creating $ARCHIVE_DIR"
  mkdir -p "$ARCHIVE_DIR"
fi

debug "fetching locations seatgeek API"
cat "$ingest_base/locations.tsv" |
while read -r location_name latitude longitude; do
  debug "downloading location $location_name"
  "$ingest_base/downloadlocation.py" -a "$ARCHIVE_DIR" "$latitude" "$longitude" |
  "$ingest_base/explodejson.py"
done
