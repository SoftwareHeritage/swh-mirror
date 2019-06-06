#!/bin/bash

set -e

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

    cat >~/.pg_service.conf <<EOF
[swh]
dbname=${PGDATABASE:-swh}
host=$PGHOST
user=${PGUSER:-swh}
EOF
	echo "$PGHOST:*:*:${PGUSER:-swh}:$(cat /run/secrets/postgres-password)" \
		 >~/.pgpass
	chmod 0600 ~/.pgpass
fi

# For debugging purpose
echo "### CONFIG FILE ###"
cat /etc/softwareheritage/config.yml
echo "###################"

case "$1" in
    "shell")
      exec bash -i
      ;;
	"db-init")
      echo "Initialize the SWH database"
	  exec swh db init
	  ;;
	"graph-replayer")
      echo "Starting the SWH mirror graph replayer"
	  exec sh -c "trap : TERM INT; while :; do swh journal replay; done"
	  ;;
	"content-replayer")
      echo "Starting the SWH mirror content replayer"
	  exec sh -c "trap : TERM INT; while :; do swh journal content-replay; done"
	  ;;
    "objstorage")
      echo "Starting the SWH $1 RPC server"
      exec gunicorn3 \
		   --bind 0.0.0.0:${PORT:-5000} \
		   --bind unix:/var/run/gunicorn/swh/$1.sock \
		   --worker-class aiohttp.worker.GunicornWebWorker \
           --log-level "${LOG_LEVEL:-WARNING}" \
           --timeout 3600 \
           swh.$1.api.wsgi
      ;;
    *)
      echo "Starting the SWH $1 RPC server"
	  swh db init || echo "swh db init failed, database is probably already initialized; ignored"
      exec gunicorn3 \
		   --bind 0.0.0.0:${PORT:-5000} \
		   --bind unix:/var/run/gunicorn/swh/$1.sock \
           --threads 4 \
           --workers 2 \
           --log-level "${LOG_LEVEL:-WARNING}" \
           --timeout 3600 \
           swh.$1.api.wsgi
      ;;
esac
