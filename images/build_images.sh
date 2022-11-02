#!/usr/bin/env bash

set -e

builddate=$(date +%Y%m%d)
buildtime=$(date +%H%M%S)
builddatetime="${builddate}-${buildtime}"

username=$(docker info | grep Username | awk '{print $2}')
options=$(getopt -l "write-env-file:" -o "" -- "$@") || exit 1

for img in base web replayer; do
    docker build \
           --build-arg SWH_VER=${builddatetime} \
           --build-arg pythonversion=3.7 \
           --tag softwareheritage/${img}:${builddatetime} \
           --target swh-${img} \
           .
    docker tag softwareheritage/${img}:${builddatetime} softwareheritage/${img}:${builddate}
    docker tag softwareheritage/${img}:${builddate} softwareheritage/${img}:latest
  if [[ -n "${username}" ]] && [[ "${PUBLISH:=no}" = "yes" ]]; then
      echo "Publishing image softwareheritage:${img}-${builddate} on docker hub"
      docker push softwareheritage/${img}:${builddatetime}
      docker push softwareheritage/${img}:${builddate}
      docker push softwareheritage/${img}:latest
  fi
done

eval set -- "$options"
while true; do
    case "$1" in
        --write-env-file)
            shift
            echo "SWH_IMAGE_TAG=${builddatetime}" > "$1"
            ;;
        --)
            shift
            break
            ;;
    esac
    shift
done

echo "Done creating images. You may want to use"
echo "export SWH_IMAGE_TAG=${builddatetime}"
