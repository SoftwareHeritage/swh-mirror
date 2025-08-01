# build rage (for swh-alter)
FROM rust:slim-bookworm AS build_rage
RUN cargo install rage

# build yq (stolen from https://github.com/mikefarah/yq/blob/master/Dockerfile)
FROM golang:1.24 AS build_yq
RUN CGO_ENABLED=0 go install -ldflags "-s" github.com/mikefarah/yq/v4@latest

ARG pythonversion=3.11
FROM python:${pythonversion:-3.11} AS swh-builder
LABEL maintainer="Software Heritage <sysop@softwareheritage.org>"
ENV PROJECT_NAME=swh-base

RUN export DEBIAN_FRONTEND=noninteractive && \
  apt-get update && apt-get upgrade -y && \
  apt-get install -y \
    apt-transport-https \
    curl \
    lsb-release \
    wait-for-it

ARG PGDG_REPO=http://apt.postgresql.org/pub/repos/apt
ARG PGDG_GPG_PKEY=https://www.postgresql.org/media/keys/ACCC4CF8.asc
ARG PGDG_KEYRING=/usr/share/keyrings/pgdg-archive-keyring.gpg

ARG NODE_REPO=https://deb.nodesource.com/node_14.x
ARG NODE_GPG_PKEY=https://deb.nodesource.com/gpgkey/nodesource.gpg.key
ARG NODE_KEYRING=/usr/share/keyrings/nodejs-archive-keyring.gpg

ARG YARN_REPO=https://dl.yarnpkg.com/debian/
ARG YARN_GPG_PKEY=https://dl.yarnpkg.com/debian/pubkey.gpg
ARG YARN_KEYRING=/usr/share/keyrings/yarnpkg-archive-keyring.gpg

RUN . /etc/os-release && \
  echo "deb [signed-by=${PGDG_KEYRING}] ${PGDG_REPO} ${VERSION_CODENAME}-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list && \
  curl -fsSL ${PGDG_GPG_PKEY} | gpg --dearmor > ${PGDG_KEYRING} && \
  echo "deb [signed-by=${NODE_KEYRING}] ${NODE_REPO} ${VERSION_CODENAME} main" \
  > /etc/apt/sources.list.d/nodejs.list && \
  curl -fsSL ${NODE_GPG_PKEY} | gpg --dearmor > ${NODE_KEYRING} && \
  echo "deb [signed-by=${YARN_KEYRING}] ${YARN_REPO} stable main" \
  > /etc/apt/sources.list.d/yarnpkg.list && \
  curl -fsSL ${YARN_GPG_PKEY} | gpg --dearmor > ${YARN_KEYRING}

# warning: the py:3.1x image comes with python3.9 installed from debian; do not
# add debian python packages here, they would not be usable for the python
# environment used in this image.
RUN export DEBIAN_FRONTEND=noninteractive && \
  apt-get update && apt-get upgrade -y && \
  apt-get install -y \
  libapr1-dev \
  libaprutil1-dev \
  libcmph-dev \
  libpq-dev \
  librdkafka-dev \
  libsvn-dev \
  libsystemd-dev \
  gcc \
  iputils-ping \
  pkg-config \
  pv \
  postgresql-client \
  wait-for-it \
  ngrep \
  rsync \
  nodejs \
  yarn \
  zstd

ENV SWH_CONFIG_FILENAME=/etc/softwareheritage/config.yml
ENV LC_ALL=C.UTF-8

RUN mkdir /etc/softwareheritage
RUN mkdir -p /var/run/gunicorn/swh
RUN mkdir -p /var/lib/swh
RUN useradd -md /srv/softwareheritage -s /bin/bash swh
RUN chown swh:swh /srv/softwareheritage /var/lib/swh  /var/run/gunicorn/swh /etc/softwareheritage
USER swh

RUN python3 -m venv /srv/softwareheritage/venv
ENV PATH="/srv/softwareheritage/venv/bin:${PATH}"

RUN --mount=type=cache,mode=0755,uid=1000,gid=1000,target=/srv/softwareheritage/.cache/pip \
   pip install --upgrade pip setuptools wheel
RUN --mount=type=cache,mode=0755,uid=1000,gid=1000,target=/srv/softwareheritage/.cache/pip \
   pip install gunicorn httpie

COPY requirements.txt /srv/softwareheritage/requirements.txt

RUN --mount=type=cache,mode=0755,uid=1000,gid=1000,target=/srv/softwareheritage/.cache/pip \
  pip install -r /srv/softwareheritage/requirements.txt

#COPY requirements-extras.txt /srv/softwareheritage/requirements-extras.txt
#RUN --mount=type=cache,mode=0755,uid=1000,gid=1000,target=/srv/softwareheritage/.cache/pip \
#  pip install -r /srv/softwareheritage/requirements-extras.txt

RUN pip freeze > /srv/softwareheritage/pip-freeze.txt

##################################
# MIRROR image
##################################

FROM python:${pythonversion:-3.11}-slim AS swh-mirror
LABEL maintainer="Software Heritage <sysop@softwareheritage.org>"

RUN export DEBIAN_FRONTEND=noninteractive && \
  apt-get update && apt-get upgrade -y && \
  apt-get install -y \
    apt-transport-https \
    curl \
	gnupg \
    lsb-release \
    wait-for-it

ARG PGDG_REPO=http://apt.postgresql.org/pub/repos/apt
ARG PGDG_GPG_PKEY=https://www.postgresql.org/media/keys/ACCC4CF8.asc
ARG PGDG_KEYRING=/usr/share/keyrings/pgdg-archive-keyring.gpg

RUN . /etc/os-release && \
  echo "deb [signed-by=${PGDG_KEYRING}] ${PGDG_REPO} ${VERSION_CODENAME}-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list && \
  curl -fsSL ${PGDG_GPG_PKEY} | gpg --dearmor > ${PGDG_KEYRING}

# warning: the py:3.1x image comes with python3.11 installed from debian; do not
# add debian python packages here, they would not be usable for the py310 based
# environment used in this image.
RUN export DEBIAN_FRONTEND=noninteractive && \
  apt-get update && apt-get upgrade -y && \
  apt-get install -y \
  gosu \
  iputils-ping \
  libmagic1 \
  #openjdk-11-jre \
  pv \
  postgresql-client \
  wait-for-it \
  ngrep \
  rsync \
  zstd && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

ENV SWH_CONFIG_FILENAME=/etc/softwareheritage/config.yml
ENV LC_ALL=C.UTF-8
ENV PATH="/srv/softwareheritage/venv/bin:${PATH}"

RUN mkdir /etc/softwareheritage
RUN mkdir -p /var/run/gunicorn/swh
RUN mkdir -p /var/lib/swh
RUN useradd -md /srv/softwareheritage -s /bin/bash swh
RUN chown swh:swh /srv/softwareheritage /var/lib/swh  /var/run/gunicorn/swh /etc/softwareheritage
USER swh
COPY --from=swh-builder /srv /srv
# Install rage (for swh-alter)
COPY --from=build_rage /usr/local/cargo/bin/rage /usr/local/cargo/bin/rage-keygen /usr/local/bin
# Install yq
COPY --from=build_yq /go/bin/yq /usr/local/bin

ARG SWH_VER
ENV SWH_VER=${SWH_VER}

COPY conf/logconfig.ini /etc/gunicorn/logconfig.ini
COPY conf/gunicorn.cfg /etc/gunicorn/swh.cfg
COPY tools/*.sh /srv/softwareheritage/utils/
COPY tools/*.sql /srv/softwareheritage/utils/
COPY tools/*.py /srv/softwareheritage/utils/

USER root
RUN chown -R swh:swh  /srv/softwareheritage/utils
RUN chmod +x /srv/softwareheritage/utils/*.sh

COPY entrypoint.sh /
ENTRYPOINT ["/entrypoint.sh"]
