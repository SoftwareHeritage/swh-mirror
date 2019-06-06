.. highlight:: bash

.. _objstorage_install:


Object Storage
==============

The machine that hosts the Object Storage must have access to enough storage so
the whole content of the Archive can be copied. It should be at least 300TiB
(as of today, the whole content of the archive represent around 200TiB of
compressed data).

The object storage does not require a database, however, it needs a way to
store objects (blobs).

There are several backends currently available:

- `pathslicing`: store objects in a POSIX filesystem
- `remote`: use a HTTP based RPC exposing an existing objstorage,
- `pathslicing`: store objects in a POSIX filesystem
- `azure`: use Azure's storage,
- `azure-prefixed`: Azure's storage with a prefix; typically used in
  conjunction with the `multiplexer` backend (see below) to distribute the
  storage amoung a set of Azure tokens for better performances,
- `memory`: keep everything in RAM, for testing purpose,
- `weed`: use seaweedfs as blob storage,
- `rados`: RADOS based object storage (Ceph),
- `s3`: Amazon S3 storage,
- `swift`: OpensStack Swift storage.
- `multiplexer`: assemble several objstorages as once.
- `striping`: xxx
- `filtered`: xxx


Beware that not all these backends are production ready.

Please read the documentation of each of these backends for more details on how
to configure them.

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

Configure the object storage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In this example, we use a local storage as backend located in
`/srv/softwareheritage/objects`. Write a configuration file named
`objstorage.yml`::

  objstorage:
    cls: pathslicing
    args:
      root: /srv/softwareheritage/objects
      slicing: 0:5

  client_max_size: 1073741824

Testing the configuration
~~~~~~~~~~~~~~~~~~~~~~~~~

Then start the test SWGI server for the RPC objstorage service::

  $ docker run --rm  \
      --network swh \
      -v ${PWD}/objstorage.yml:/etc/softwareheritage/config.yml \
      -v /srv/softwareheritage/objects:/srv/softwareheritage/objects \
      -p 5003:5000 \
      swh/base objstorage

You should be able to query this server (fraom another terminal since the
container is started attached to its console)::

  $ http http://127.0.0.1:5003
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

Note: in the example above, we use httpie_ as HTTP client. You can use any
other tool (curl, wget...)

.. _httpie: https://httpie.org

Since we started this container attached, just hit Ctrl+C to quit in the
terminal in which the docker container is running.

Running in production
~~~~~~~~~~~~~~~~~~~~~

This container uses gunicorn as SWGI server. However, since this later does not
handle the HTTP stack well enough for a production system, it is recommanded to
run this behind a proper HTTP server like nginx.

First, we start the objstorage container without exposing the TCP port, but
using a mounted file as socket to be able to share it with other containers.
Here, we create this socket file in `/srv/softwareheritage/objstorage.sock`::

  $ docker run -d --name objstorage \
      --network swh \
      -v ${PWD}/objstorage.yml:/etc/softwareheritage/config.yml \
      -v /srv/softwareheritage/objects:/srv/softwareheritage/objects \
      -v /srv/softwareheritage/socks/objstorage:/var/run/gunicorn/swh \
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


Which you can check for proper fucntionning also::

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


Manual installation on a Debian system
--------------------------------------

Ensure you have a Debian machine with Software Heritage apt repository
:ref:`properly configured <swh_debian_repo>`.

There are several storage scenarios supported by the :ref:`Object Storage
<swh-storage>`. We will focus on a simple scenario where local storage is used
using a regular filesystem.

Let's assume this storage capacity is available on `/srv/softwareheritage`.

- Install the Object Storage package and dependencies::

   ~$ sudo apt install python3-swh.objstorage gunicorn3 nginx-light

- Create a dedicated `swh` user::

   ~$ sudo useradd -md /srv/softwareheritage -s /bin/bash swh

- Create the required directory for objects storage::

    ~$ sudo mkdir  /srv/softwareheritage/objects
    ~$ sudo chown swh: /srv/softwareheritage/objects

- Configure the Object Storage RPC Server::

    ~$ sudo mkdir /etc/softwareheritage/
    ~$ sudo sh -c 'cat > /etc/softwareheritage/objstorage.yml' <<EOF
    > objstorage:
    >   cls: pathslicing
    >   args:
    >     root: /srv/softwareheritage/objects
    >     slicing: 0:5
    >
    > client_max_size: 1073741824
    > EOF
    ~$

- Ensure the Object Storage service can be started by hand::

    ~$ sudo -u swh swh-objstorage -C  /etc/softwareheritage/objstorage.yml serve
    ======== Running on http://0.0.0.0:5003 ========
    (Press CTRL+C to quit)

  In another terminal, check the HTTP server responds properly::

    ~$ curl 127.0.0.1:5003
    SWH Objstorage API server
    ~$

  Quit the test server by hitting Ctrl+C in the terminal it is running in.

- Ensure reauired directories for gunicorn exists::

    ~$ sudo mkdir -p /etc/gunicorn/instances
    ~$ sudo mkdir -p /var/run/gunicorn/swh-objstorage/
    ~$ sudo chown swh: /var/run/gunicorn/swh-objstorage/

- Copy the gunicorn config file below to `/etc/gunicorn/instances/objstorage.cfg`::

    import traceback
    import gunicorn.glogging

    class Logger(gunicorn.glogging.Logger):
        log_only_errors = True

        def access(self, resp, req, environ, request_time):
            """ See http://httpd.apache.org/docs/2.0/logs.html#combined
            for format details
            """

            if not (self.cfg.accesslog or self.cfg.logconfig or self.cfg.syslog):
                return

            # wrap atoms:
            # - make sure atoms will be test case insensitively
            # - if atom doesn't exist replace it by '-'
            atoms = self.atoms(resp, req, environ, request_time)
            safe_atoms = self.atoms_wrapper_class(atoms)

            try:
                if self.log_only_errors and str(atoms['s']) == '200':
                    return
                self.access_log.info(self.cfg.access_log_format % safe_atoms, extra={'swh_atoms': atoms})
            except:
                self.exception('Failed processing access log entry')

    logger_class = Logger
    logconfig = '/etc/gunicorn/logconfig.ini'

    # custom settings
    bind = "unix:/run/gunicorn/swh-objstorage/gunicorn.sock"
    workers = 16
    worker_class = "aiohttp.worker.GunicornWebWorker"
    timeout = 3600
    graceful_timeout = 3600
    keepalive = 5
    max_requests = 0
    max_requests_jitter = 0
    # Uncomment the following lines if you want statsd monitoring
    # statsd_host = "127.0.0.1:8125"
    # statsd_prefix = "swh-objstorage"

- Copy the logging config file to `/etc/gunicorn/logconfig.ini`::

    [loggers]
    keys=root, gunicorn.error, gunicorn.access

    [handlers]
    keys=console, journal

    [formatters]
    keys=generic

    [logger_root]
    level=INFO
    handlers=console,journal

    [logger_gunicorn.error]
    level=INFO
    propagate=0
    handlers=journal
    qualname=gunicorn.error

    [logger_gunicorn.access]
    level=INFO
    propagate=0
    handlers=journal
    qualname=gunicorn.access

    [handler_console]
    class=StreamHandler
    formatter=generic
    args=(sys.stdout, )

    [handler_journal]
    class=swh.core.logger.JournalHandler
    formatter=generic
    args=()

    [formatter_generic]
    format=%(asctime)s [%(process)d] [%(levelname)s] %(message)s
    datefmt=%Y-%m-%d %H:%M:%S
    class=logging.Formatter


- Ensure the Object Storage server can be started via gunicorn::

    ~$ SWH_CONFIG_FILENAME=/etc/softwareheritage/objstorage.yml \
       gunicorn3 -c /etc/gunicorn/instances/objstorage.cfg swh.objstorage.api.wsgi
    [...]
    ^C
    ~$

- Add a `systemd` Service Unit file for this gunicorn WSGI server; copy the
  file below to `/etc/systemd/system/gunicorn-swh-objstorage.service`::

    [Unit]
    Description=Gunicorn instance swh-objstorage
    ConditionPathExists=/etc/gunicorn/instances/swh-objstorage.cfg
    PartOf=gunicorn.service
    ReloadPropagatedFrom=gunicorn.service
    Before=gunicorn.service

    [Service]
    User=swhstorage
    Group=swhstorage
    PIDFile=/run/gunicorn/swh-objstorage/pidfile
    RuntimeDirectory=/run/gunicorn/swh-objstorage
    WorkingDirectory=/run/gunicorn/swh-objstorage
    Environment=SWH_CONFIG_FILENAME=/etc/softwareheritage/objstorage.yml
    Environment=SWH_LOG_TARGET=journal
    ExecStart=/usr/bin/gunicorn3 -p /run/gunicorn/swh-objstorage/pidfile -c /etc/gunicorn/instances/objstorage.cfg swh.objstorage.api.wsgi
    ExecStop=/bin/kill -TERM $MAINPID
    ExecReload=/bin/kill -HUP $MAINPID

    [Install]
    WantedBy=multi-user.target

  And the file below to `/etc/systemd/system/gunicorn.service`::

    [Unit]
    Description=All gunicorn services

    [Service]
    Type=oneshot
    ExecStart=/bin/true
    ExecReload=/bin/true
    RemainAfterExit=on

    [Install]
    WantedBy=multi-user.target

- Load these Service Unit files and activate them::

    ~$ sudo systemctl daemon-reload
    ~$ sudo systemctl enable --now gunicorn-swh-objstorage.service


- Configure the nginx HTTP server as a reverse proxy for the gunicorn SWGI
  server; here is an example of the file `/etc/nginx/nginx.conf`::

    user www-data;
    worker_processes 16;
    worker_rlimit_nofile 1024;

    pid        /var/run/nginx.pid;
    error_log  /var/log/nginx/error.log error;

    events {
      accept_mutex off;
      accept_mutex_delay 500ms;
      worker_connections 1024;
    }

    http {

      include       /etc/nginx/mime.types;
      default_type  application/octet-stream;

      access_log  /var/log/nginx/access.log;

      sendfile    on;
      server_tokens on;

      types_hash_max_size 1024;
      types_hash_bucket_size 512;

      server_names_hash_bucket_size 128;
      server_names_hash_max_size 1024;

      keepalive_timeout   65s;
      keepalive_requests  100;
      client_body_timeout 60s;
      send_timeout        60s;
      lingering_timeout   5s;
      tcp_nodelay         on;

      gzip              on;
      gzip_comp_level   1;
      gzip_disable      msie6;
      gzip_min_length   20;
      gzip_http_version 1.1;
      gzip_proxied      off;
      gzip_vary         off;

      client_body_temp_path   /var/nginx/client_body_temp;
      client_max_body_size    10m;
      client_body_buffer_size 128k;
      proxy_temp_path         /var/nginx/proxy_temp;
      proxy_connect_timeout   90s;
      proxy_send_timeout      90s;
      proxy_read_timeout      90s;
      proxy_buffers           32 4k;
      proxy_buffer_size       8k;
      proxy_set_header        Host $host;
      proxy_set_header        X-Real-IP $remote_addr;
      proxy_set_header        X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header        Proxy "";
      proxy_headers_hash_bucket_size 64;


      include /etc/nginx/conf.d/*.conf;
      include /etc/nginx/sites-enabled/*;
    }


  `/etc/nginx/conf.d/swh-objstorage-gunicorn-upstream.conf`::

    upstream swh-objstorage-gunicorn {
      server     unix:/run/gunicorn/swh-objstorage/gunicorn.sock  fail_timeout=0;
    }

  `/etc/nginx/sites-enabled/swh-objstorage.conf`::

    server {
      listen 0.0.0.0:5003 deferred;

      server_name           <hostname> 127.0.0.1 localhost ::1;
      client_max_body_size 4G;

      index  index.html index.htm index.php;
      access_log            /var/log/nginx/nginx-swh-objstorage.access.log combined if=$error_status;
      error_log             /var/log/nginx/nginx-swh-objstorage.error.log;

      location / {
        proxy_pass            http://swh-objstorage-gunicorn;
        proxy_read_timeout    3600s;
        proxy_connect_timeout 90s;
        proxy_send_timeout    90s;
        proxy_buffering       off;
        proxy_set_header      Host $host;
        proxy_set_header      X-Real-IP $remote_addr;
        proxy_set_header      X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header      Proxy "";
      }
    }

  Note the `<hostname>` in the example file above to adapt to your server name.

  `/etc/nginx/conf.d/swh-objstorage-default.conf`::

    server {
      listen 0.0.0.0:5003 default_server;

      server_name           nginx-swh-objstorage-default;

      return 444;
      index  index.html index.htm index.php;
      access_log            /var/log/nginx/nginx-swh-objstorage-default.access.log combined;
      error_log             /var/log/nginx/nginx-swh-objstorage-default.error.log;

      location / {
        index     index.html index.htm index.php;
      }
    }


- Restart the `nginx` service::

    ~$ sudo systemctl restart nginx.service

- Check the whole stack is responding::

    ~$ curl http://127.0.0.1:5003/
    SWH Objstorage API serverd
    ~$
