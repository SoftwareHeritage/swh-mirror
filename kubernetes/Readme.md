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
# cd images
# ./build_images.sh

# docker tag softwareheritage/base:latest registry.default/softwareheritage/base:latest
# docker push registry.default/softwareheritage/base:latest

# docker tag softwareheritage/web:latest registry.default/softwareheritage/web:latest
# docker push registry.default/softwareheritage/web:latest

```

### grafana image

This image goal is to be able to configure grafana during the startup

```
# cd images/grafana
# docker build --pull -t registry.default/softwareheritage/grafana .
# docker push registry.default/softwareheritage/grafana
```

## start the objstorage

- start the service
```
# cd kubernetes

# kubectl apply -f 01-objstorage.yml
configmap/objstorage created
persistentvolume/objstorage-pv created
persistentvolumeclaim/objstorage-pvc created
deployment.apps/objstorage created
service/objstorage created
```
- test it
From a node of the cluster :
```
# kubectl get pods
NAME                                   READY   STATUS    RESTARTS   AGE
registry-deployment-7595868dc8-657ps   1/1     Running   0          46m
objstorage-8587d58b68-76jbn            1/1     Running   0          12m

# kubectl get services objstorage
NAME         TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
objstorage   ClusterIP   10.43.185.191   <none>        5003/TCP   17m

# curl http://$(kubectl get services objstorage -o jsonpath='{.spec.clusterIP}'):5003
SWH Objstorage API server%  
```
## Start the storage

- Start the db
```
# cd kubernetes

# kubectl apply -f 02-storage-db.yml
persistentvolume/storage-db-pv created
persistentvolumeclaim/storage-db-pvc created
secret/storage-db created
configmap/storage-db created
deployment.apps/storage-db created
service/storage-db created

# kubectl get pods
NAME                                   READY   STATUS    RESTARTS   AGE
registry-deployment-7595868dc8-657ps   1/1     Running   0          46m
objstorage-8587d58b68-76jbn            1/1     Running   0          15m
storage-db-64b7f8b684-48n7w            1/1     Running   0          4m52s

# kubectl get services storage-db
NAME         TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
storage-db   ClusterIP   10.43.213.178   <none>        5432/TCP   8m19s
```
- Start the storage
```
# cd kubernetes

# kubectl apply -f 03-storage.yml
configmap/storage created
deployment.apps/storage created
service/storage created
```

- Test the service
From a node of the cluster :
```
# kubectl get pods
NAME                                   READY   STATUS    RESTARTS   AGE
registry-deployment-7595868dc8-657ps   1/1     Running   0          49m
storage-db-64b7f8b684-48n7w            1/1     Running   0          7m40s
storage-6b759fb974-w9rzj               1/1     Running   0          66s

# kubectl get services storage
NAME      TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
storage   ClusterIP   10.43.212.116   <none>        5002/TCP   2m24s

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

# TODOs

- [ ] registry persistence
- [ ] storage for sqlite database for web
- [ ] prometheus exporter
- [ ] prometheus
- [ ] grafana
- [ ] graph replayer
- [ ] content replayer
- [ ] clustered configuration