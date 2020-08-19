#!/usr/bin/env bash

builddate=$(date +%Y%m%d-%H%M%S)

username=$(docker info | grep Username | awk '{print $2}')

for img in base web; do
  docker build --build-arg SWH_VER=${builddate} --build-arg debianversion=buster -t softwareheritage/${img}:${builddate} -f ${img}/Dockerfile .
  docker tag softwareheritage/${img}:${builddate} softwareheritage/${img}:latest
  if [[ X${username} = Xsoftwareheritage ]]; then
    docker push softwareheritage/${img}:${builddate}
    docker push softwareheritage/${img}:latest
  fi
done

