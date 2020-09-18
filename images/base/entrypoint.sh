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
    echo 'Available secrets:'
    ls -l /run/secrets/

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
      "db-init")
        wait_pgsql
        echo "Initialize the SWH database"
        exec swh db init
        ;;
  	  "fix-mirror")
  		db_init
  		echo "Fixing the database for the mirror use case (drop constraints, if any)"
  		fix_storage_for_mirror
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
  		db_init
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
