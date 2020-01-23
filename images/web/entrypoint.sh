#!/bin/bash

set -e

create_admin_script="
from django.contrib.auth import get_user_model;

username = 'admin';
password = 'admin';
email = 'admin@swh-web.org';

User = get_user_model();

if not User.objects.filter(username = username).exists():
    User.objects.create_superuser(username, email, password);
"

# generate the config file from the 'template'
if [ -f /etc/softwareheritage/config.yml.tmpl ]; then
    # I know... I know!
    eval "echo \"`cat /etc/softwareheritage/config.yml.tmpl`\"" > \
         /etc/softwareheritage/config.yml
fi

case "$1" in
    "shell")
      exec bash -i
      ;;

    "serve")
      echo "Migrating db using ${DJANGO_SETTINGS_MODULE}"
      django-admin migrate --settings=${DJANGO_SETTINGS_MODULE}

      echo "Creating admin user"
      echo "$create_admin_script" | python3 -m swh.web.manage shell

	  echo "starting the swh-web server"
	  mkdir -p /var/run/gunicorn/swh/web
      exec gunicorn3 \
		   --bind 0.0.0.0:5004 \
           --bind unix:/var/run/gunicorn/swh/web/sock \
           --threads 2 \
           --workers 2 \
           --timeout 3600 \
           'django.core.wsgi:get_wsgi_application()'
      ;;
esac
