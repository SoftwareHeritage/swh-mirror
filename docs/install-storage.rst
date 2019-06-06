.. highlight:: bash

.. _storage_install:


Graph Storage
=============

The machine that hosts the (graph) Storage must have access to a Postgresql
database. It must also have access to a running objstorage instance. Setting up
these services will not be covered here.

In this guide, we assume that:

- Postgresql is running on machine `pghost` and the database `swh-storage`
  exists and is owned by the postgresql user `swhuser`,
- objstorage is running on machine `objstorage` listening on port 5003.


Docker based deployment
-----------------------

In a docker based deployment, all machine names must be resolvable from within
a docker container and accessible from there.

When testing this guide on a single docker host, the simplest solution is to
start your docker containers linked to a common bridge::

  $ docker network create swh
  e0d85947d4f53f8b2f0393517f373ab4f5b06d02e1efa07114761f610b1f7afa
  $

In the examples below we will use such a network config.

Build the image
~~~~~~~~~~~~~~~

```
$ docker build -t swh/base https://forge.softwareheritage.org/source/swh-docker.git
```

Configure the storage
~~~~~~~~~~~~~~~~~~~~~

Write a configuration file named `storage.yml`::

  storage:
    cls: local
    args:
      db: postgresql://swhuser:p4ssw0rd@pghost/swh-storage

      objstorage:
        cls: remote
        args:
          url: http://objstorage:5003

  client_max_size: 1073741824


Testing the configuration
~~~~~~~~~~~~~~~~~~~~~~~~~

Then start the test SWGI server for the RPC storage service::

  $ docker run --rm  \
      --network swh \
      -v ${PWD}/storage.yml:/etc/softwareheritage/config.yml \
      -p 5002:5000 \
      swh/base storage

You should be able to query this server (fraom another terminal since the
container is started attached to its console)::

  $ http http://127.0.0.1:5002
  HTTP/1.1 200 OK
  Content-Length: 25
  Content-Type: text/plain; charset=utf-8
  Date: Thu, 20 Jun 2019 08:02:32 GMT
  Server: Python/3.5 aiohttp/3.5.1

  SWH Objstorage API server

  $ http http://127.0.0.1:5003/check_config check_write=True
  HTTP/1.1 200 OK
  Content-Length: 4
  Content-Type: application/json
  Date: Thu, 20 Jun 2019 08:06:58 GMT
  Server: Python/3.5 aiohttp/3.5.4

  true
  $

Note: in the example above, we use httpie_ as HTTP client. You can use any
other tool (curl, wget...)

.. _httpie: https://httpie.org

Since we started this container attached, just hit Ctrl+C to quit in the
terminal in which the docker container is running.

Running in production
~~~~~~~~~~~~~~~~~~~~~

This container uses gunicorn as SWGI server. However, since this later does not
handle the HTTP stack well enough for a production system, it is recommended to
run this behind a proper HTTP server like nginx.

First, we start the objstorage container without exposing the TCP port, but
using a mounted file as socket to ba able to share it with other containers.
Here, we create this socket file in `/srv/softwareheritage/objstorage.sock`::

  $ docker run -d --name swh-objstorage \
      --network swh \
      -v ${PWD}/objstorage.yml:/etc/softwareheritage/config.yml \
      -v /srv/softwareheritage/objects:/srv/softwareheritage/objects \
      -v /srv/softwareheritage/socks:/var/run/gunicorn/swh \
      swh/base objstorage

And start an HTTP server that will proxy the UNIX socket
`/srv/softwareheritage/socks/objstorage.sock`. Using Nginx, you can use the
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
      server unix:/tmp/gunicorn/gunicorn.sock fail_timeout=0;
      }

    server {
      listen             80 default_server;

      # Add a trailing slash to top level requests
      rewrite ^/([^/]+)$ /$1/ permanent;

      location / {
        set $upstream "http://app_server";
        proxy_pass $upstream;
      }
    }
  }


And run nginx in a docker container with::

  $ docker run \
      --network swh \
      -v ${PWD}/conf/nginx.conf:/etc/nginx/nginx.conf:ro \
      -v /tmp/objstorage/objstorage.sock:/tmp/gunicorn.sock \
      -p 5003:80 \
      nginx


Which you can check it is properly functionning::

  $ http :5003/check_config check_write=True
  HTTP/1.1 200 OK
  Connection: keep-alive
  Content-Length: 1
  Content-Type: application/x-msgpack
  Date: Thu, 20 Jun 2019 10:13:39 GMT
  Server: nginx/1.17.0

  true


If you want your docker conotainers to start automatically, add the
`--restart=always` option to docker commands above. This should prevent you
from having to write custom service unit files.
