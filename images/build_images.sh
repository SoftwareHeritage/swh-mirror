#!/usr/bin/env bash

builddate=$(date +%Y%m%d-%H%M%S)

username=$(docker info | grep Username | awk '{print $2}')

for img in base web; do
  docker build --build-arg SWH_VER=${builddate} --build-arg debianversion=buster -t softwareheritage/${img}:${builddate} -f ${img}/Dockerfile .
  docker tag softwareheritage/${img}:${builddate} softwareheritage/${img}:latest
  if [[ "${username}" = "softwareheritage" ]] && [[ "${PUBLISH:=no}" = "yes" ]]; then
	  echo "Publishing image softwareheritage/${img}:${builddate} on docker hub"
      docker push softwareheritage/${img}:${builddate}
      docker push softwareheritage/${img}:latest
  fi
done

echo "Done creating images. You may want to use"
echo "export SWH_IMAGE_TAG=${builddate}"
