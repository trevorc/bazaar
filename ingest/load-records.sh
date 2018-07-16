#!/bin/sh
#
# load-records.sh - load event JSON documents into PostgreSQL
#

set -e
set -u

help() {
  cat <<EOF
$0 accepts newline-separated event JSON documents
and (idempotently) loads them into the PostgreSQL database named
on the command line.

EOF
  usage
}

usage() {
  cat <<EOF
Usage: $0 [-k] DB
  -k  keep temporary files

DB   the PostgreSQL database to load event data into

The WORK_DIR environment variable must be set. WORK_DIR governs the
prefix inside of which $0 will create and destroy
temporary files.

If PG_BINDIR is set, the PostgreSQL installation rooted in that
directory will be used. By default, the installation in
${PG_BINDIR} is used.
EOF
  exit 1
}

version() {
  cat <<EOF
$0 0.1.0

Written by Trevor Caira <trevor@bitba.se>
EOF
  exit 1
}

debug() {
  if [ -n "$DEBUG" ]; then
    echo >&2 "$@"
  fi
}

ingest_base=$(cd "$(dirname "$0")"; pwd -P)
keep=
DEBUG=${DEBUG:-}
PG_BINDIR=${PG_BINDIR:-"$(pg_config --bindir)"}

while getopts "d:kV?" flag; do
  case "$flag" in
    (d) PGDATABASE=$OPTARG ;;
    (k) keep=1 ;;
    (V) version ;;
    ([?]) help ;;
  esac
done
shift $(($OPTIND-1))
export PGDATABASE

if [ -z "${PGDATABASE:-}" ]; then
  echo >&2 "error: the PGDATABASE environment variable must be set"
  usage
fi

if [ -z "${WORK_DIR:-}" ]; then
  echo >&2 "error: the WORK_DIR environment variable must be set"
  usage
fi

WORK_DIR=$(cd "$WORK_DIR"; pwd -P)

if [ ! -d "$WORK_DIR" ]; then
  echo >&2 "error: $WORK_DIR does not exist or is not a directory"
  exit 2
fi

ingest_dir="$WORK_DIR/ingest"
psql="$PG_BINDIR/psql"

if [ ! -x "$psql" ]; then
  echo >&2 "error: $psql does not exist or is not executable"
  exit 2
fi

debug "creating $ingest_dir"
mkdir -p "$ingest_dir"

debug "populating $PGDATABASE from events on standard input"
"$ingest_base/events2records.py" |
sort -u -k 1,3 -s |
awk -f "$ingest_base/collate-records.awk"

old_pwd=$(pwd -P)
cd "$ingest_dir"
record_count=$(($(cat *.tsv | wc -l)))
debug "loading $record_count records into $PGDATABASE"
"$psql" -f "$ingest_base/tsv2db.sql"
cd "$old_pwd"

if [ -z "$keep" ]; then
  debug "removing $ingest_dir"
  rm -r "$ingest_dir"
fi
