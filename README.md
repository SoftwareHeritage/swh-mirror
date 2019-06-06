# Deploy a Software Heritage stack with docker deploy

According you have a properly set up docker swarm cluster, e.g.:

```
~/swh-docker$ docker node ls
ID                            HOSTNAME            STATUS              AVAILABILITY        MANAGER STATUS      ENGINE VERSION
py47518uzdb94y2sb5yjurj22     host2               Ready               Active                                  18.09.7
n9mfw08gys0dmvg5j2bb4j2m7 *   host1               Ready               Active              Leader              18.09.7
```

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
  --opt device=/data/docker/swh-objstorage \
  --opt o=bind \
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
contraints if needed.

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

## Creating the swh service

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
- an nginx server serving as reverse proxy for the swh-web instances.


## Updating a configuration

When you modify a configuration file exposed to docker services via the `docker
config` system, you need to destroy the old config before being able to
recreate them (docker is currenlty not capable of updating an existing config.
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


# Set up a mirror

A Software Heritage mirror consists in base Software Heritage services, as
descibed above without any worker related to web scraping nor source code
repository loading. Instead, filling local storage and objstorage is the
responsibility of kafka based `replayer` services:

- the `graph replayer` which is in charge of filling the storage (aka the
  graph), and

- the `content replayer` which is in charge of filling the object storage.

Ensure configuration files are properly set in `conf/graph-replayer.yml` and
`conf/content-replayer.yml`, then you can start these services with:

```
~/swh-docker$ docker deploy -c docker-compose.yml,docker-compose-mirror.yml swh
[...]
```

If everything is OK, you should have your mirror filling. Check docker logs:

```
~/swh-docker$ docker service logs swh_content-replayer
[...]
```

and:

```
~/swh-docker$ docker service logs swh_graph-replayer
[...]
```
