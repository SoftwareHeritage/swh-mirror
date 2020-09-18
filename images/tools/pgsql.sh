#!/bin/bash

setup_pgsql () {
    echo "${PGHOST}:5432:${PGDATABASE:-swh}:${PGUSER:-swh}:$(cat /run/secrets/postgres-password)" \
		 > ~/.pgpass
    cat > ~/.pg_service.conf <<EOF
[swh]
dbname=${PGDATABASE:-swh}
host=${PGHOST}
port=5432
user=${PGUSER:-swh}
EOF
    chmod 0600 ~/.pgpass
}

wait_pgsql () {
    echo Waiting for postgresql to start
    wait-for-it ${PGHOST}:5432 -s --timeout=0
    until psql postgresql:///?service=swh -c "select 1" > /dev/null 2> /dev/null; do sleep 1; done
}

db_init () {
	wait_pgsql
	if version=$(psql postgresql:///?service=swh -qtA \
					  -c "select version from dbversion order by version desc limit 1" 2>/dev/null) ; then
		echo "Database seems already initialized at version $version"
	else
		echo "Database seems not initialized yet; initialize it"
		swh db init
	fi
}

fix_storage_for_mirror () {
	psql postgresql:///?service=swh -f /srv/softwareheritage/utils/fix-storage.sql
}
