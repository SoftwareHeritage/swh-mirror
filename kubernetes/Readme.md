## Current status

- basic configuration for one node cluster
- use a private registry to deploy the docker image

Services :
- objstorage
- storage-db
- storage
## Prerquisite

### Directories
```
# sudo mkdir -p /srv/softwareheritage-kube/storage-db
# sudo mkdir -p /srv/softwareheritage-kube/objects
# sudo mkdir -p /srv/softwareheritage-kube/prometheus 
# sudo chown nobody /srv/softwareheritage-kube/prometheus  # prometheus is running with user nobody
```
Must match the content of `02-storage-db.yaml`

### Registry

- Add the following line on your `/etc/hosts` file. It's needed to be able to
  push the image to it from docker
```
127.0.0.1 registry.default
```
- Start the registry in kubernetes
```
# cd kubernetes
# kubectl apply -f registry/00-registry.yml
```

## Build the images

### SWH images

```
cd images
./build_images.sh

docker tag softwareheritage/base:latest registry.default/softwareheritage/base:latest
docker push registry.default/softwareheritage/base:latest

docker tag softwareheritage/web:latest registry.default/softwareheritage/web:latest
docker push registry.default/softwareheritage/web:latest

docker tag softwareheritage/replayer:latest registry.default/softwareheritage/replayer:latest
docker push registry.default/softwareheritage/replayer:latest
 
```

### grafana image

This image goal is to be able to configure grafana during the startup

```
cd images/grafana
docker build --pull -t registry.default/softwareheritage/grafana .
docker push registry.default/softwareheritage/grafana
```

## Configuration

The configuration of the services is done on each dedicated files in the `kubernetes` directory. You can check which file is used for which service on the section `Start unitary service` later on this document.

### What needs to be configured?

#### Physical volumes
  
The physical volumes control where the data will be stored on your kubernetes cluster.
The default configuration uses local directories ubder the `/srv/softwareheritage-kube` main directory.
It can be customized for the following services :

  - prometheus
  - objstorage
  - storage-db

#### Ingress urls

The ingress urls are used to expose your services. They should be configured in the ingress configuration of the following services:
  
  - prometheus
  - grafana
  - web
  
#### Journal configuration

The journal configuration specify where to read the main data (i.e. the software heritage kafka server). If necessary the credentials should be also specified.

This configuration is declared on the config maps used by the following services:
- graph-replayer
- content-replayer

### Default configuration

| type        | service    | value                                   |
| ----------- | ---------- | --------------------------------------- |
| PV(local)   | prometheus | `/srv/softwareheritage-kube/prometheus` |
| PV(local)   | objstorage | `/srv/softwareheritage-kube/objstorage` |
| PV(local)   | storage-db | `/srv/softwareheritage-kube/storage-db` |
| ingress url | prometheus | `prometheus.default`                    |
| ingress url | grafana    | `grafana.default`                       |
| ingress url | webapp     | `web.default`                           |
|kafka url | graph-replayer / content-replayer | `broker0.journal.staging.swh.network` |
| kafka credentials |  graph-replayer / content-replayer | `swh-username` / `secretpassword` |
| Consumer group | graph-replayer | `swh-username-graph-replayer` |
| Consumer group | content-replayer | `swh-username-content-replayer` |


## Launch the mirror

### Start the complete stack

```
cd kubernetes
kubectl apply -f .
```

### Start unitary service

The configuration is split in the following files :

| File                   | Services                                                     |
| ---------------------- | ------------------------------------------------------------ |
| 01-prometheus.yaml     | <ul><li>prometheus</li><li>grafana</li></ul>                 |
| 02-objstorage.yaml     | <ul><li>object storage (swh-objstorage)</li></ul>            |
| 03-storage-db.yaml     | <ul><li>storage database (postgresql)</li></ul>              |
| 04-storage.yaml        | <ul><li>storage (swh-storage)</li></ul>                      |
| 05-web.yaml            | <ul><li>Webapp (swh-web)</li></ul>                           |
| 10-graph-replayer.yaml | <ul><li>Graph replayer (swh-storage)</li></ul>               |
| 11-graph-replayer      | <ul><li>Content replayer (swh-objstorage-replayer)</li></ul> |

To deploy one file content individually, use the following command :

```bash
kubectl apply -f <filename>
```

### Test a service

- From a node of the cluster, list the available services:
```
# kubectl get services storage
NAME      TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
storage   ClusterIP   10.43.212.116   <none>        5002/TCP   2m24s
```

- Call the service from the cluster ip:
```
# curl http://$(kubectl get services storage -o jsonpath='{.spec.clusterIP}'):5002
<html>
<head><title>Software Heritage storage server</title></head>
<body>
<p>You have reached the
<a href="https://www.softwareheritage.org/">Software Heritage</a>
storage server.<br />
See its
<a href="https://docs.softwareheritage.org/devel/swh-storage/">documentation
and API</a> for more information</p>
</body>
</html>
```

## Cleanup the environment

In the `kubernetes` directory:
```
kubectl delete -f .
```
It destroys the deployed components but keep the data intact (default on the `/srv/sofwareheritage-kube/` directory)

The services can be deployed one by one by specifying the yaml name, for example:
```bash
kubectl delete -f 04-storage.yaml
```
# TODOs

- [ ] registry persistence
- [ ] storage for sqlite database for web
- [ ] prometheus exporter
- [ ] clustered configuration
- [ ] Create a helm charts
