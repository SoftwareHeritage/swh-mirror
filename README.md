# Deploy a Software Heritage stack with docker deploy

According you have a properly set up docker swarm cluster with support for the
`docker deploy` command, e.g.:

```
~/swh-docker$ docker node ls
ID                            HOSTNAME            STATUS              AVAILABILITY        MANAGER STATUS      ENGINE VERSION
py47518uzdb94y2sb5yjurj22     host2               Ready               Active                                  18.09.7
n9mfw08gys0dmvg5j2bb4j2m7 *   host1               Ready               Active              Leader              18.09.7
```

Note: this might require you activate experimental features of docker as
described in [docker deploy](https://docs.docker.com/engine/reference/commandline/deploy/)
documentation.

In the following how-to, we will assume that the service `STACK` name is `swh`
(this name is the last argument of the `docker deploy` command below).

Several preparation steps will depend on this name.

## Set up volumes

Before starting the `swh` service, you may want to specify where the data
should be stored on your docker hosts.

By default it will use docker volumes for storing databases and the content of
the objstorage (thus put them in `/var/lib/docker/volumes`.

If you want to specify a different location to put a storage in, create the
storage before starting the docker service. For example for the `objstorage`
service you will need a storage named `<STACK>_objstorage`:

```
~/swh-docker$ docker volume create -d local \
  --opt type=none \
  --opt o=bind \
  --opt device=/data/docker/swh-objstorage \
  swh_objstorage
```

If you want to deploy services like the `swh-objstorage` on several hosts, you
will a shared storage area in which blob objects will be stored. Typically a
NFS storage can be used for this. This is not covered in this doc.

Please read the documentation of docker volumes to learn how to use such a
device as volume proviver for docker.

Note that the provided `docker-compose.yaml` file have a few placement
constraints, for example the `objstorage` service is forced to be spawn on the
master node of the docker swarm cluster. Feel free to remove/amend these
constraints if needed.

## Managing secrets

Shared passwords (between services) are managed via `docker secret`. Before
being able to start services, you need to define these secrets.

Namely, you need to create a `secret` for:

- `postgres-password`

For example:
```
~/swh-docker$ echo 'strong password' | docker secret create postgres-password -
[...]
```

## Creating the swh base services

From within this repository, just type:

```
~/swh-docker$ docker deploy -c docker-compose.yml swh
Creating service swh_web
Creating service swh_objstorage
Creating service swh_storage
Creating service swh_nginx
Creating service swh_memcache
Creating service swh_db-storage
~/swh-docker$ docker service ls
ID                  NAME                MODE                REPLICAS            IMAGE                          PORTS
bkn2bmnapx7w        swh_db-storage      replicated          1/1                 postgres:11
2ujcw3dg8f9d        swh_memcache        replicated          1/1                 memcached:latest
l52hxxl61ijj        swh_nginx           replicated          1/1                 nginx:latest                   *:5080->80/tcp
3okk2njpbopx        swh_objstorage      replicated          1/1                 softwareheritage/base:latest
zais9ey62weu        swh_storage         replicated          1/1                 softwareheritage/base:latest
7sm6g5ecff19        swh_web             replicated          1/1                 softwareheritage/web:latest
```

This will start a series of containers with:

- an objstorage service,
- a storage service using a postgresql database as backend,
- a web app front end,
- a memcache for the web app,
- a prometheus monitoring app,
- a prometeus-statsd exporter,
- a grafana server,
- an nginx server serving as reverse proxy for grafana and swh-web.

using the latest published version of the docker images.


The nginx frontend will listen on the 5081 port, so you can use:

- http://localhost:5081/ to navigate your local copy of the archive,
- http://localhost:5081/grafana/ to explore the monitoring probes
  (log in with admin/admin).


Note that if the 'latest' docker images work, it is highly recommended to
explicitly specify the version of the image you want to use.
Docker images for the Software Heritage stack are tagged with their build date:

  docker images -f reference='softwareheritage/*:20*'
  REPOSITORY              TAG                 IMAGE ID            CREATED             SIZE
  softwareheritage/web    20200819-112604     32ab8340e368        About an hour ago   339MB
  softwareheritage/base   20200819-112604     19fe3d7326c5        About an hour ago   242MB
  softwareheritage/web    20200630-115021     65b1869175ab        7 weeks ago         342MB
  softwareheritage/base   20200630-115021     3694e3fcf530        7 weeks ago         245MB

To specify the tag to be used, simply set the SWH_IMAGE_TAG environment variable, like:

  export SWH_IMAGE_TAG=20200819-112604
  docker deploy -c docker-compose.yml swh

Warning: make sure to have this variable properly set for any later `docker deploy`
command you type, otherwise you running containers will be recreated using the
':latest' image (which might **not** be the latest available version, nor
consistent amond the docker nodes on you swarm cluster).

## Updating a configuration

When you modify a configuration file exposed to docker services via the `docker
config` system, you need to destroy the old config before being able to
recreate them (docker is currently not capable of updating an existing config.)
Unfortunately that also means you need to recreate every docker container using
this config.

For example, if you edit the file `conf/storage.yml`:

```
~/swh-docker$ docker service rm swh_storage
swh_storage
~/swh-docker$ docker config rm swh_storage
swh_storage
~/swh-docker$ docker deploy -c docker-compose.yml swh
Creating config swh_storage
Creating service swh_storage
Updating service swh_nginx (id: l52hxxl61ijjxnj9wg6ddpaef)
Updating service swh_memcache (id: 2ujcw3dg8f9dm4r6qmgy0sb1e)
Updating service swh_db-storage (id: bkn2bmnapx7wgvwxepume71k1)
Updating service swh_web (id: 7sm6g5ecff1979t0jd3dmsvwz)
Updating service swh_objstorage (id: 3okk2njpbopxso3n3w44ydyf9)
```

See https://docs.docker.com/engine/swarm/configs/ for more details on
how to use the config system in docker swarm.

Note that since persistent data (databases and objects) are stored in volumes,
you can safely destoy and recreate any container you want, you will not loose
any data.

## Updating a service

When a new version of the softwareheritage/base image is published, running
services must updated to use it.

In order to prevent inconsistency caveats due to dependency in deployed
versions, we recommend that you deploy the new image on all running
services at once.

This can be done as follow:

```
~/swh-docker$ export SWH_IMAGE_TAG=<new version>
~/swh-docker$ docker deploy -c docker-compose.yml swh
```

Note that this will reset the replicas config to their default values.


If you want to update only a specific service, you can also use:

```
~/swh-docker$ docker service update --image \
       softwareheritage/base:${SWH_IMAGE_TAG} ) \
       swh_graph-replayer-origin
```


# Set up a mirror

A Software Heritage mirror consists in base Software Heritage services, as
described above, without any worker related to web scraping nor source code
repository loading. Instead, filling local storage and objstorage is the
responsibility of kafka based `replayer` services:

- the `graph replayer` which is in charge of filling the storage (aka the
  graph), and

- the `content replayer` which is in charge of filling the object storage.

Examples of docker-compose files and configuration files are provided in
the `graph-replayer-remote-bytopic.yml` compose file for replayer services
using configuration from yaml files in `conf/graph-replayer/remote/`.

Copy these example files as plain yaml ones then modify them to replace
the XXX merkers with proper values (also make sure the kafka server list
is up to date.) Parameters to check/update are:

- `journal_client/brokers`: list of kafka brokers.
- `journal_client/group_id`: unique identifier for this mirroring session;
  you can choose whatever you want, but changing this value will make kafka
  start consuming messages from the beginning; kafka messages are dispatched
  among consumers with the same `group_id`, so in order to distribute the
  load among workers, they must share the same `group_id`.
- `journal_client/sasl.username`: kafka authentication username.
- `journal_client/sasl.password`: kafka authentication password.

```
~/swh-docker$ cd conf/graph-replayer/remote
~/swh-docker/conf/graph-replayer/remote$ for i in *.example; do cp $i ${i/.example//}; done
~/swh-docker/conf/graph-replayer/remote$ # edit .yml files
~/swh-docker/conf/graph-replayer/remote$ cd ../../..
~/swh-docker$

```

Once you have properly edited config files, you can start these services with:

```
~/swh-docker$ docker deploy \
   -c docker-compose.yml \
   -c graph-replayer-remote-bytopic.yml \
   swh
[...]
```

You can check everything is running with:

```
~/swh-docker$ docker service ls
ID                  NAME                             MODE                REPLICAS            IMAGE                          PORTS
88djaq3jezjm        swh_db-storage                   replicated          1/1                 postgres:11
m66q36jb00xm        swh_grafana                      replicated          1/1                 grafana/grafana:latest
qfsxngh4s2sv        swh_content-replayer             replicated          1/1                 softwareheritage/base:latest
qcl0n3ngr2uv        swh_graph-replayer-content       replicated          2/2                 softwareheritage/base:latest
f1hop14w6b9h        swh_graph-replayer-directory     replicated          4/4                 softwareheritage/base:latest
dcpvbf7h4fja        swh_graph-replayer-origin        replicated          2/2                 softwareheritage/base:latest
1njy5iuugmk2        swh_graph-replayer-release       replicated          2/2                 softwareheritage/base:latest
cbe600nl9bdb        swh_graph-replayer-revision      replicated          4/4                 softwareheritage/base:latest
5hroiithan6c        swh_graph-replayer-snapshot      replicated          2/2                 softwareheritage/base:latest
zn8dzsron3y7        swh_memcache                     replicated          1/1                 memcached:latest
wfbvf3yk6t41        swh_nginx                        replicated          1/1                 nginx:latest                   *:5081->5081/tcp
thtev7o0n6th        swh_objstorage                   replicated          1/1                 softwareheritage/base:latest
ysgdoqshgd2k        swh_prometheus                   replicated          1/1                 prom/prometheus:latest
u2mjjl91aebz        swh_prometheus-statsd-exporter   replicated          1/1                 prom/statsd-exporter:latest
xyf2xgt465ob        swh_storage                      replicated          1/1                 softwareheritage/base:latest
su8eka2b5cbf        swh_web                          replicated          1/1                 softwareheritage/web:latest
```


If everything is OK, you should have your mirror filling. Check docker logs:

```
~/swh-docker$ docker service logs swh_content-replayer
[...]
```

or:

```
~/swh-docker$ docker service logs --tail 100 --follow swh_graph-replayer-directory
[...]
```

## Scaling up services

In order to scale up a replayer service, you can use the `docker scale` command. For example:

```
~/swh-docker$ docker service scale swh_graph-replayer-directory=4
[...]
```

will start 4 copies of the directory replayer service.

Notes:

- One graph replayer service requires a steady 500MB to 1GB of RAM to run, so
  make sure you have properly sized machines for running these replayer
  containers, and to monitor these.

- The overall bandwidth of the replayer will depend heavily on the
  `swh_storage` service, thus on the `swh_db-storage`. It will require some
  network bandwidth for the ingress kafka payload (this can easily peak to
  several hundreds of Mb/s). So make sure you have a correctly tuned database
  and enough network bw.

- Biggest topics are the directory, content and revision.
