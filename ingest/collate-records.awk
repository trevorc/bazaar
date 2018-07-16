#!/usr/bin/env awk

BEGIN {
    if (!ENVIRON["WORK_DIR"]) die("error: WORK_DIR must be set")
    FS   = "\t"
    last = ""
}

NF < 3 || !$1 || !$2 {
    die("invalid record " NR " (missing fields, got " NF ")")
}

NR > 1 && last != cur() {
    close(last)
}

{
    last = cur()
    print substr($0, index($0, FS) + 1) > last
}

END {
    if (last) close(last)
}

function die(message) {
    print message > "/dev/stderr"
    exit 1
}

function cur() {
    return ENVIRON["WORK_DIR"] "/ingest/" $1 ".tsv"
}
