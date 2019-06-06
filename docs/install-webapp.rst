.. highlight:: bash

.. _webapp_install:


Web Application
===============

The machine that hosts the front end web application must have access to all
the Software Heritage service RPC endpoints. Some of them may be optional, in
which case parts of the web UI won't work as expected.

In this guide, we assume that:

- storage RPC server is running on machine `storage` listening on port 5002,
- objstorage RPC server is running on machine `objstorage` listening on
  port 5003.

For the metadata/indexer part to work, il will also require:

- indexer storage RPC server is running on machine `indexerstorage` listening
  on port 5007.

For the Vault part to work, it will also require:

- vault RPC server is running on machine `vault` listening on port 5005,
- scheduler RPC server is running on machine `scheduler` listening on
  port 5008.

For the Deposit part to work, it will also require:

- deposit RPC server is running on machine `vault` listening on port 5006,
- scheduler RPC server is running on machine `scheduler` listening on
  port 5008.


Docker based deployment
-----------------------

In a docker based deployment, obviously, all machine names listed above must be
resolvable from within a docker container and accessible from there.

When testing this guide on a single docker host, the simplest solution is to
start your docker containers linked to a common bridge::

  $ docker network create swh
  e0d85947d4f53f8b2f0393517f373ab4f5b06d02e1efa07114761f610b1f7afa
  $

In the examples below we will use such a network config.


Build the image
~~~~~~~~~~~~~~~

::

  $ docker build -t swh/web -f Dockerfile.web \
     https://forge.softwareheritage.org/source/swh-docker.git
  [...]
  Successfully tagged swh/web:latest


Configure the web app
~~~~~~~~~~~~~~~~~~~~~

Write a configuration file named `web.yml` like::

  storage:
    cls: remote
    args:
      url: http://storage:5002/
      timeout: 1

  objstorage:
    cls: remote
    args:
      url: http://objstorage:5003/

  indexer_storage:
    cls: remote
    args:
      url: http://indexer-storage:5007/

  scheduler:
    cls: remote
    args:
      url: http://scheduler:5008/

  vault:
    cls: remote
    args:
      url: http://vault:5005/

  deposit:
    private_api_url: https://deposit:5006/1/private/
    private_api_user: swhworker
    private_api_password: ''

  allowed_hosts:
	- app_server

  debug: no

  serve_assets: yes

  throttling:
    cache_uri: null
    scopes:
      swh_api:
        limiter_rate:
          default: 120/h
        exempted_networks:
          - 0.0.0.0/0
      swh_vault_cooking:
        limiter_rate:
          default: 120/h
        exempted_networks:
          - 0.0.0.0/0
      swh_save_origin:
        limiter_rate:
          default: 120/h
        exempted_networks:
          - 0.0.0.0/0


Testing the configuration
~~~~~~~~~~~~~~~~~~~~~~~~~

Then initialize the web app::

  $ docker run --rm \
      --network swh \
      -v ${PWD}/web.yml:/etc/softwareheritage/config.yml \
      swh/web migrate
  Migrating db using swh.web.settings.production
  Operations to perform:
    Apply all migrations: admin, auth, contenttypes, sessions, swh.web.common
  Running migrations:
    No migrations to apply.
  Creating admin user
  $

and start the web app::

  $ docker run --rm  \
      --network swh \
      -v ${PWD}/web.yml:/etc/softwareheritage/config.yml \
      -p 5004:5000 \
      swh/web serve
  starting the swh-web server
  [...]

You should be able to navigate the web application using your browser on
http://localhost:5004 .

If everything works fine, hit Ctrl+C in the terminal in which the docker
container is running.

Using memcache
~~~~~~~~~~~~~~

It is strongly advised to use a memcache for the web app. Considering such a
service is listening on `memcache:11211`, you should adapt the
`throttling.cache_uri` parameter of your `web.yml` file accordingly::

  [...]

  throttling:
    cache_uri: memcache:11211

  [...]

You can easily start such a memcached server using::

  $ docker run --name memcache --network swh -d memcached


Running in production
~~~~~~~~~~~~~~~~~~~~~

This container uses gunicorn as WSGI server. However, since this later does not
handle the HTTP stack well enough for a production system, it is recommended to
run this behind a proper HTTP server like nginx via a unix socket.

First, we start the webapp container without exposing the TCP port, but
using a mounted file as socket to be able to share it with other containers.
Here, we create this socket file in `/srv/softwareheritage/socks/web.sock`::

  $ docker run -d --name webapp \
      --network swh \
      -v ${PWD}/web.yml:/etc/softwareheritage/config.yml \
      -v /srv/softwareheritage/socks:/var/run/gunicorn/swh \
      swh/web serve

And start an HTTP server that will proxy the UNIX socket
`/srv/softwareheritage/socks/web/sock`. Using Nginx, you can use the
following `nginx.conf` file::

  worker_processes  4;

  # Show startup logs on stderr; switch to debug to print, well, debug logs when
  # running nginx-debug
  error_log /dev/stderr info;

  events {
    worker_connections 1024;
  }

  http {
    include            mime.types;
    default_type       application/octet-stream;
    sendfile           on;
    keepalive_timeout  65;

    # Built-in Docker resolver. Needed to allow on-demand resolution of proxy
    # upstreams.
    resolver           127.0.0.11 valid=30s;

    upstream app_server {
      # fail_timeout=0 means we always retry an upstream even if it failed
      # to return a good HTTP response

      # for UNIX domain socket setups
      server unix:/tmp/gunicorn/sock fail_timeout=0;
      }

    server {
      listen             80 default_server;

      location / {
        set $upstream "http://app_server";
        proxy_pass $upstream;
      }
    }
  }


Note that the `app_server` name in this file above must be listed in the
`allowed_hosts` config option in the `web.yml` file.

And run nginx in a docker container with::

  $ docker run -d \
    --network swh \
    -v ${PWD}/conf/nginx.conf:/etc/nginx/nginx.conf:ro \
    -v /srv/softwareheritage/socks/web:/tmp/gunicorn \
    -p 5004:80 \
    nginx


Which you can check it is properly functionning navigating on http://localhost:5004

If you want your docker conotainers to start automatically, add the
`--restart=always` option to docker commands above. This should prevent you
from having to write custom service unit files.
