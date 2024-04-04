#!/bin/bash

setup_pgsql () {
  # generate the pgservice file if any
  if [[ -n $PGCFG_0 ]]; then
    : > ~/.pgpass
    : > ~/.pg_services.conf

  for i in {0..10}; do
    CFG="PGCFG_$i"
    if [[ -z ${!CFG} ]]; then
      break
    else
      echo "Configure DB access ${!CFG} (i=${i})"
      # There is probably a better way of doing this...
      NAME=${!CFG}
      PGHOST=PGHOST_$i
      PGHOST=${!PGHOST}
      PGPORT=PGPORT_$i
      PGPORT=${!PGPORT:-5432}
      PGUSER=PGUSER_$i
      PGUSER=${!PGUSER}
      POSTGRES_DB=POSTGRES_DB_$i
      POSTGRES_DB=${!POSTGRES_DB}

      PGPASSWORD=$(cat /run/secrets/postgres-password-$NAME)

      cat >> ~/.pgpass <<EOF
${PGHOST}:${PGPORT}:template1:${PGUSER}:${PGPASSWORD}
${PGHOST}:${PGPORT}:${POSTGRES_DB}:${PGUSER}:${PGPASSWORD}

EOF

      cat >> ~/.pg_service.conf <<EOF
[${NAME}]
dbname=${POSTGRES_DB}
host=${PGHOST}
port=${PGPORT}
user=${PGUSER}

EOF

    fi
  done

  chmod 0600 ~/.pgpass
  echo "DONE setup Postgresql client config file"
  echo "cat ~/.pg_service.conf"
  cat ~/.pg_service.conf
  echo "====================="
  echo "cat ~/.pgpass"
  cat ~/.pgpass
  echo "====================="
  echo "Main DB is ${NAME} (${POSTGRES_DB})"
fi

}

wait_pgsql () {
    local db_to_check
    if [ $# -ge 1 ]; then
        db_to_check="$1"
    else
        db_to_check=$POSTGRES_DB
    fi

    if [ $# -ge 2 ]; then
        host_to_check="$2"
    else
        host_to_check=$PGHOST
    fi

    if [ $# -ge 3 ]; then
        port_to_check="$3"
    else
        port_to_check=$PGPORT
    fi

    echo Waiting for postgresql to start on $host_to_check:${port_to_check} and for database $db_to_check to be available.
    wait-for-it ${host_to_check}:${port_to_check} -s --timeout=0
    until psql "dbname=${db_to_check} port=${port_to_check} host=${host_to_check} user=${PGUSER}" -c "select 'postgresql is up!' as connected"; do sleep 1; done
}

check_pgsql_db_created () {
    psql "dbname=${POSTGRES_DB} port=${PGPORT} host=${PGHOST} user=${PGUSER}" -c "select 'postgresql is up!' as connected" >/dev/null 2>/dev/null
}
