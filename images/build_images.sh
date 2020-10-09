#!/usr/bin/env bash

builddate=$(date +%Y%m%d)
buildtime=$(date +%H%M%S)
builddatetime="${builddate}-${buildtime}"

username=$(docker info | grep Username | awk '{print $2}')

for img in base web replayer; do
	docker build \
		   --build-arg SWH_VER=${builddatetime} \
		   --build-arg debianversion=buster \
		   --tag softwareheritage:${img}-${builddatetime} \
		   --target swh-${img} \
		   .
	docker tag softwareheritage:${img}-${builddatetime} softwareheritage:${img}-${builddate}
	docker tag softwareheritage:${img}-${builddate} softwareheritage:${img}-latest
  if [[ -n "${username}" ]] && [[ "${PUBLISH:=no}" = "yes" ]]; then
	  echo "Publishing image softwareheritage:${img}-${builddate} on docker hub"
      docker push softwareheritage:${img}-${builddatetime}
  fi
done

#docker tag softwareheritage:base-${builddate} softwareheritage:latest

echo "Done creating images. You may want to use"
echo "export SWH_IMAGE_TAG=${builddatetime}"
