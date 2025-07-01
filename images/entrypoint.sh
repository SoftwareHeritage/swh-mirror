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
                    -Ofair --loglevel=${CELERY_LOG_LEVEL:-INFO} \
                    --hostname "${SWH_WORKER_INSTANCE}@%h"
        ;;

    "rpc-server")
        shift
        if [ -v POSTGRES_DB -a ! -v DB_SKIP_INIT ]; then
            swh_setup_db $1
        fi

        # this series of service/backend specific init/setup code is not very
        # pretty, but will do for now
        if [ "$1" == "storage" ] && [ -v CASSANDRA_SEEDS ]; then
          echo Waiting for Cassandra to start
          IFS=','
          for CASSANDRA_SEED in ${CASSANDRA_SEEDS}; do
              echo "   $CASSANDRA_SEED..."
              wait-for-it ${CASSANDRA_SEED}:9042 -s --timeout=0
          done
          echo Creating keyspace
          swh storage cassandra init
        fi

        if [ "$1" == "search" ]; then
            echo Waiting for elasticsearch
            wait-for-it elasticsearch:9200 -s --timeout=0
        fi

        if [ "$1" == "objstorage" ]; then
            backend=$(yq -r .objstorage.cls $SWH_CONFIG_FILENAME)
            if [ "$backend" == "winery" ]; then
                echo Custom db initialisation for winery
                wait_pgsql
                swh db init-admin -d service=$POSTGRES_DB objstorage:winery
                swh db init -d service=$POSTGRES_DB objstorage:winery
                swh db upgrade --non-interactive -d service=$POSTGRES_DB objstorage:winery
            fi
        fi

        echo "Starting the SWH $1 RPC server"
        exec python3 -m gunicorn \
             --bind 0.0.0.0:${PORT:-5000} \
             --bind unix:/var/run/gunicorn/swh/$1.sock \
             --threads ${GUNICORN_THREADS:-4} \
             --workers ${GUNICORN_WORKERS:-16} \
             --log-level ${GUNICORN_LOG_LEVEL:-WARNING} \
             --timeout ${GUNICORN_TIMEOUT:-3600} \
             --statsd-host=prometheus-statsd-exporter:9125 \
             --statsd-prefix=service.app.$1  \
             "swh.$1.api.server:make_app_from_configfile()"
        ;;

    "scheduler")
        shift
        wait_pgsql

        wait-for-it scheduler:5008 -s --timeout=0

        echo "Register task types"
        swh scheduler task-type register

        echo "Starting the swh-scheduler $1"
        exec wait-for-it amqp:5672 -s --timeout=0 -- \
             swh scheduler -C ${SWH_CONFIG_FILENAME} $@
        ;;

    "graph-replayer")
        shift
        wait-for-it storage:5002
        echo "Starting the SWH mirror graph replayer"
        exec swh storage replay $@
        ;;

    "content-replayer")
        shift
        wait-for-it objstorage:5003
        echo "Starting the SWH mirror content replayer"
        exec swh objstorage replay $@
        ;;

    "search-indexer")
        shift
        wait-for-it search:5010
        echo "Starting the SWH search indexer"
        exec swh search -C ${SWH_CONFIG_FILENAME} \
             journal-client objects $@
        ;;

    "run-mirror-notification-watcher")
        shift
        exec swh alter run-mirror-notification-watcher "$@"
        ;;

    "winery")
        shift
        wait_pgsql
        wait-for-it objstorage:5003
        exec swh objstorage winery $@
        ;;

    "web")
        wait_pgsql

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
            swh_setup_db scrubber

            # now create the scrubber config, if needed
            swh scrubber check init --object-type ${OBJTYPE} --nb-partitions $(( 2 ** ${NBITS} )) --name ${CFGNAME} && echo "Created scrubber configuration ${CFGNAME}" || echo "Configuration ${CFGNAME} already exists (ignored)."
        fi

        echo "Starting a SWH storage scrubber ${CFGNAME}"
        exec swh scrubber check storage ${CFGNAME} $@
        ;;

    *)
        exec $@
        ;;
esac
