#!/usr/bin/env bash

set -e

builddate=$(date +%Y%m%d)
buildtime=$(date +%H%M%S)
builddatetime="${builddate}-${buildtime}"

username=$(docker info | grep Username | awk '{print $2}')
options=$(getopt -l "write-env-file:" -o "" -- "$@") || exit 1

docker build \
       --build-arg SWH_VER=${builddatetime} \
       --build-arg pythonversion=3.10 \
       --tag softwareheritage/mirror:${builddatetime} \
       --target swh-mirror \
       .

docker tag softwareheritage/mirror:${builddatetime} softwareheritage/mirror:latest
if [[ -n "${username}" ]] && [[ "${PUBLISH:=no}" = "yes" ]]; then
    echo "Publishing image softwareheritage/mirror:${builddatetime} on docker hub"
    docker push softwareheritage/mirror:${builddatetime}
    docker push softwareheritage/mirror:latest
fi

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
