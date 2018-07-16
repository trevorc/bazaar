#!/bin/sh
#
# ingest.sh - imports the seatgeek event database into PostgreSQL
#
# This script is the entry point into the ingest component.
#
# Setup:
#
# - the login user must be able to connect to the given PostgreSQL
#   database either using PGHOST/PGPORT/PGUSER/.pgpass or with UNIX
#   authentication
# - the database user must have SELECT/UPDATE/INSERT credentials on
#   all of the seatgeek tables
# - the login user must be able to write to the directory supplied on
#   the command line as the prefix

set -e
set -u

if [ -n "${BASH:-}" ]; then
  set -o pipefail
fi

help() {
  cat <<EOF
$0 is the entrance point into the seatgeek ingest pipeline.
It downloads the current event data for the supplied locations and
refreshes their corresponding values in the database.

EOF
  usage
}

usage() {
  cat <<EOF
Usage: $0 [-a DIR] [-d DB] [-p DIR] [-v]
  -a DIR  archive responses to DIR [default $ARCHIVE_DIR]
  -d DB   load records into database DB [default $PGDATABASE]
  -p DIR  operate inside of DIR as prefix [default $WORK_DIR]
  -q DIR  override the directory of the PostgreSQL binaries
          [default $PG_BINDIR]
  -v      verbose debugging output
  -V      print version information
  -?      print this help message
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

### Options controlling execution
ingest_base=$(cd "$(dirname "$0")"; pwd -P)
PGDATABASE=${PGDATABASE:-bazaar}
DEBUG=${DEBUG:-}
WORK_DIR=${WORK_DIR:-work}
ARCHIVE_DIR=${ARCHIVE_DIR:-"$WORK_DIR"/archive}
PG_BINDIR=${PG_BINDIR:-"$(pg_config --bindir)"}

### Parse command line arguments
while getopts "a:d:p:vV?" flag; do
  case "$flag" in
    (a) ARCHIVE_DIR=$OPTARG ;;
    (d) PGDATABASE=$OPTARG ;;
    (p) WORK_DIR=$OPTARG ;;
    (q) PG_BINDIR=$OPTARG ;;
    (v) DEBUG=1 ;;
    (V) version ;;
    ([?]) help ;;
  esac
done
shift $(($OPTIND-1))
export ARCHIVE_DIR
export DEBUG
export PGDATABASE
export PG_BINDIR
export WORK_DIR

if ! psql -c ""; then
  echo >&2 "could not connect to $PGDATABASE"
  exit 2
fi

debug "starting ingest into database $PGDATABASE"

if [ ! -d "$WORK_DIR" ]; then
  echo "creating $WORK_DIR"
  mkdir -p "$WORK_DIR"
fi

# Begin operation
"$ingest_base/fetch-seatgeek.sh" |
"$ingest_base/load-records.sh"

debug "ingest complete"
