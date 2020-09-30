#!/bin/bash

set -e

source /srv/softwareheritage/utils/pgsql.sh

# generate the config file from the 'template'
if [ -f /etc/softwareheritage/config.yml.tmpl ]; then
	# I know... I know!
	eval "echo \"`cat /etc/softwareheritage/config.yml.tmpl`\"" > \
		 /etc/softwareheritage/config.yml
fi

# generate the pgservice file if any
if [ -f /run/secrets/postgres-password ]; then
	POSTGRES_PASSWORD_FILE=/run/secrets/postgres-password
	setup_pgsql
fi

# For debugging purpose
echo "### CONFIG FILE ###"
cat /etc/softwareheritage/config.yml
echo "###################"

echo "Arguments: $@"

while (( "$#" )); do
  case "$1" in
      "shell")
        exec bash -i
        ;;
      "graph-replayer")
        echo "Starting the SWH mirror graph replayer"
        exec sh -c "trap : TERM INT; while :; do swh --log-level ${LOG_LEVEL:-WARNING} storage replay; done"
        ;;
      "content-replayer")
        echo "Starting the SWH mirror content replayer"
        exec sh -c "trap : TERM INT; while :; do swh --log-level ${LOG_LEVEL:-WARNING} objstorage replay; done"
        ;;
      "objstorage")
        echo "Starting the SWH $1 RPC server"
        exec gunicorn3 \
             --bind 0.0.0.0:${PORT:-5000} \
             --bind unix:/var/run/gunicorn/swh/$1.sock \
             --worker-class aiohttp.worker.GunicornWebWorker \
             --threads 4 \
             --workers 2 \
             --log-level "${LOG_LEVEL:-WARNING}" \
             --timeout 3600 \
             "swh.$1.api.server:make_app_from_configfile()"
        ;;
      *)
        wait_pgsql template1

        echo Database setup
        if ! check_pgsql_db_created; then
            echo Creating database and extensions...
            swh db create --db-name ${POSTGRES_DB} storage
        fi
        echo Initializing the database...
        swh db init --db-name ${POSTGRES_DB} --flavor ${FLAVOR:-default} storage

        echo "Starting the SWH $1 RPC server"
        exec gunicorn3 \
             --bind 0.0.0.0:${PORT:-5000} \
             --bind unix:/var/run/gunicorn/swh/$1.sock \
             --threads 4 \
             --workers 2 \
             --log-level "${LOG_LEVEL:-WARNING}" \
             --timeout 3600 \
             "swh.$1.api.server:make_app_from_configfile()"
        ;;
  esac
  shift
done
