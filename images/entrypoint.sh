#!/bin/bash

set -e

if [[ `id -u` == "0" ]] ; then
    # init script run as root

    # ensure volumes mounted in /srv/softwareheritage belong to swh
    chown swh:swh /srv/softwareheritage/*

    # now run this script as swh
    HOME=/srv/softwareheritage exec setpriv --reuid=swh --regid=swh --init-groups $0 $@
fi

echo "Loading pgsql helper tools"
source /srv/softwareheritage/utils/pgsql.sh

if [ -v SWH_CONFIG_FILENAME ]; then
    python3 /srv/softwareheritage/utils/init_pathslicer_root.py --init
fi

# fill .pg_services.conf and .pgpass from PGCFG_n config entries
echo "Configuring DB access files (if any)"
setup_pgsql

# For debugging purpose
if [ -f /etc/softwareheritage/config.yml ]; then
    echo "### CONFIG FILE ###"
    cat /etc/softwareheritage/config.yml || true
fi

echo "###################"
echo "Arguments: $@"

case "$1" in
    "shell")
        shift
        if (( $# == 0)); then
            exec bash -i
        else
            "$@"
        fi
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
                python3 -m swh db create --dbname ${POSTGRES_DB} $1
            fi
            echo Initializing the database ${POSTGRES_DB}...
            echo " step 1: init-admin"
            python3 -m swh db init-admin --dbname postgresql:///?service=${NAME} $1
            echo " step 2: init"
            python3 -m swh db init --flavor ${FLAVOR:-default} $1
            echo " step 3: upgrade"
            python3 -m swh db upgrade --non-interactive $1
        fi

        echo "Starting the SWH $1 RPC server"
        exec python3 -m gunicorn \
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
        wait_pgsql template1

        wait-for-it scheduler:5008 -s --timeout=0

        echo "Starting the swh-scheduler $1"
        exec wait-for-it amqp:5672 -s --timeout=0 -- \
             python3 -m swh --log-level ${LOGLEVEL:-INFO} \
	     scheduler -C ${SWH_CONFIG_FILENAME} $@
        ;;

    "graph-replayer")
        shift
        wait-for-it storage:5002
        echo "Starting the SWH mirror graph replayer"
        exec python3 -m swh --log-level ${LOG_LEVEL:-WARNING} \
		storage replay $@
        ;;

    "content-replayer")
        shift
        wait-for-it objstorage:5003
        echo "Starting the SWH mirror content replayer"
        exec python3 -m swh --log-level ${LOG_LEVEL:-WARNING} \
		objstorage replay $@
        ;;

    "web")
        wait_pgsql template1

        create_admin_script="
from django.contrib.auth import get_user_model;

username = 'admin';
password = 'admin';
email = 'admin@swh-web.org';

User = get_user_model();

if not User.objects.filter(username = username).exists():
    User.objects.create_superuser(username, email, password);
"

        echo "Migrating db using ${DJANGO_SETTINGS_MODULE}"
        django-admin migrate --settings=${DJANGO_SETTINGS_MODULE}

        echo "Creating admin user"
        echo "$create_admin_script" | python3 -m swh.web.manage shell

        echo "starting the swh-web server"
        mkdir -p /var/run/gunicorn/swh/web
        python3 -m gunicorn \
                --bind 0.0.0.0:5004 \
                --bind unix:/var/run/gunicorn/swh/web/sock \
                --threads 2 \
                --workers 2 \
                --timeout 3600 \
                --access-logfile '-' \
                --config 'python:swh.web.gunicorn_config' \
                --statsd-host=prometheus-statsd-exporter:9125 \
                --statsd-prefix=service.app.web  \
                'django.core.wsgi:get_wsgi_application()'
        ;;
    "scrubber")
        shift
	# expected arguments: entity type, number of partitions (as nbits)
	OBJTYPE=$1
	shift
	NBITS=$1
	shift
	CFGNAME="${OBJTYPE}_${NBITS}"
	
        wait-for-it storage:5002
        if [ -v POSTGRES_DB ]; then
            wait_pgsql template1

            echo Database setup
            if ! check_pgsql_db_created; then
                echo Creating database and extensions...
                python3 -m swh db create --dbname ${POSTGRES_DB} scrubber
            fi
            echo Initializing the database ${POSTGRES_DB}...
            echo " step 1: init-admin"
            python3 -m swh db init-admin --dbname postgresql:///?service=${NAME} scrubber
            echo " step 2: init"
            python3 -m swh db init scrubber
            echo " step 3: upgrade"
            python3 -m swh db upgrade --non-interactive scrubber

	    # now create the scrubber config, if needed
	    python3 -m swh scrubber check init --object-type ${OBJTYPE} --nb-partitions $(( 2 ** ${NBITS} )) --name ${CFGNAME} && echo "Created scrubber configuration ${CFGNAME}" || echo "Configuration ${CFGNAME} already exists (ignored)."
        fi

        echo "Starting a SWH storage scrubber ${CFGNAME}"
        exec python3 -m swh --log-level ${LOG_LEVEL:-WARNING} \
		scrubber check storage ${CFGNAME} $@
        ;;
    *)
        exec $@
        ;;
esac
