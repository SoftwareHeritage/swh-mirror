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
