#!/bin/bash

set -e

source /srv/softwareheritage/utils/pgsql.sh

# generate the pgservice file if any
if [ -f /run/secrets/postgres-password ]; then
    POSTGRES_PASSWORD_FILE=/run/secrets/postgres-password
    setup_pgsql
fi

if [ "$1" = 'shell' ] ; then
    shift
    if (( $# == 0)); then
        exec bash -i
    else
        "$@"
    fi
else
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
    gunicorn3 \
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
fi
