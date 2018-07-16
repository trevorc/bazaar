# -*- tab-width: 4 -*-
PGDATABASE?=	bazaar
DB_OWNER?=		bazaar
PG_BINDIR!=		pg_config --bindir
WORK_DIR?=		work
ARCHIVE_DIR:=	${WORK_DIR}/archive

pg:=			${PG_BINDIR}/psql -d ${PGDATABASE}

.if empty(.TARGETS)
.BEGIN:
	@echo Error: select a valid target
	@false
.endif


###########################
# Database Initialization #
###########################

# Create the database and enable extensions on the database. Must be
# run as the database superuser.
.PHONY: create-db
create-db:
	${PG_BINDIR}/createdb -l en_US.UTF-8 -O ${DB_OWNER} ${PGDATABASE}
	${pg} -f db/boot.sql

# Load the database schema, views, and functions, as well as fixture
# data. Must be run as the owner of the database (typically `bazaar').
.PHONY: init-db
init-db:
	xz -cd db/tl_2013_us_state.sql.xz | ${pg}
	cat db/schema.sql db/views.sql db/procs.sql | ${pg}


#######################
# Development targets #
#######################

.PHONY: drop-db
drop-db:
	${PG_BINDIR}/dropdb --if-exists ${PGDATABASE}

.PHONY: reset
reset: drop-db create-db init-db load-seatgeek load-fixtures

.PHONY: reload-procs
reload-procs:
	${pg} -f db/procs.sql

${ARCHIVE_DIR}:
	ARCHIVE_DIR=${ARCHIVE_DIR} ingest/fetch-seatgeek.sh >/dev/null

.PHONY: load-seatgeek
load-seatgeek: ${ARCHIVE_DIR}
	ingest/scripts/read-archive.sh ${ARCHIVE_DIR} | \
	WORK_DIR=${WORK_DIR} PGDATABASE=${PGDATABASE} PG_BINDIR=${PG_BINDIR} \
	ingest/load-records.sh

.PHONY: load-fixtures
load-fixtures:
	${pg} -f db/development.sql
	PGDATABASE=${PGDATABASE} scripts/genfixtures.py
