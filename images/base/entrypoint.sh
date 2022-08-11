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

# ensure root dirs used for pathslicer objstorage exist (if any)
if [ -v SWH_CONFIG_FILENAME ]; then
	python3 /srv/softwareheritage/utils/init_pathslicer_root.py
fi

# For debugging purpose
echo "### CONFIG FILE ###"
cat /etc/softwareheritage/config.yml | grep -v password || true
echo "###################"

echo "Arguments: $@"

case "$1" in
    "shell")
		exec bash -i
		;;

	"celery-worker")
		shift

		# these 2 lines below should be adapted, but we do not have easily
		# access to the rabbitmq host:port from here for now
        ## echo Waiting for RabbitMQ to start
        ## wait-for-it amqp:5672 -s --timeout=0

        echo Starting the swh Celery worker for ${SWH_WORKER_INSTANCE}
        exec python3 -m celery \
                    --app=swh.scheduler.celery_backend.config.app \
                    worker \
                    --pool=prefork --events \
                    --concurrency=${CONCURRENCY} \
                    --max-tasks-per-child=${MAX_TASKS_PER_CHILD} \
                    -Ofair --loglevel=${LOGLEVEL:-INFO} \
                    --hostname "${SWH_WORKER_INSTANCE}@%h"
		;;

    "rpc-server")
		shift
		if [ -v POSTGRES_DB ]; then
			wait_pgsql template1

			echo Database setup
			if ! check_pgsql_db_created; then
				echo Creating database and extensions...
				swh db create --db-name ${POSTGRES_DB} $1
			fi
			echo Initializing the database...
			echo " step 1: init-admin"
			swh db init-admin --db-name ${POSTGRES_DB} $1
			echo " step 2: init"
			swh db init --flavor ${FLAVOR:-default} $1
			echo " step 3: upgrade"
			swh db upgrade --non-interactive $1
		fi

		echo "Starting the SWH $1 RPC server"
		exec gunicorn3 \
			 --bind 0.0.0.0:${PORT:-5000} \
			 --bind unix:/var/run/gunicorn/swh/$1.sock \
			 --threads ${GUNICORN_THREADS:-4} \
			 --workers ${GUNICORN_WORKERS:-16} \
			 --log-level "${LOG_LEVEL:-WARNING}" \
			 --timeout ${GUNICORN_TIMEOUT:-3600} \
			 --statsd-host=prometheus-statsd-exporter:9125 \
			 --statsd-prefix=service.app.$1  \
			 "swh.$1.api.server:make_app_from_configfile()"
		;;

	"scheduler")
		shift
		wait_pgsql

        wait-for-it scheduler:5008 -s --timeout=0

        echo "Starting the swh-scheduler $1"
        exec wait-for-it amqp:5672 -s --timeout=0 -- \
			 swh --log-level ${LOGLEVEL:-INFO} scheduler -C ${SWH_CONFIG_FILENAME} $@
		;;

	*)
		exec $@
		;;
esac
