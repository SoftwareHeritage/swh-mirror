ARG pythonversion=3.10
FROM python:${pythonversion:-3.10} as swh-builder
LABEL maintainer="Software Heritage <sysop@softwareheritage.org>"
ENV PROJECT_NAME swh-base

RUN export DEBIAN_FRONTEND=noninteractive && \
  apt-get update && apt-get upgrade -y && \
  apt-get install -y \
    apt-transport-https \
    curl \
    lsb-release \
    wait-for-it

ARG PGDG_REPO=http://apt.postgresql.org/pub/repos/apt
ARG PGDG_GPG_KEY=https://www.postgresql.org/media/keys/ACCC4CF8.asc
ARG PGDG_KEYRING=/usr/share/keyrings/pgdg-archive-keyring.gpg

ARG NODE_REPO=https://deb.nodesource.com/node_14.x
ARG NODE_GPG_KEY=https://deb.nodesource.com/gpgkey/nodesource.gpg.key
ARG NODE_KEYRING=/usr/share/keyrings/nodejs-archive-keyring.gpg

ARG YARN_REPO=https://dl.yarnpkg.com/debian/
ARG YARN_GPG_KEY=https://dl.yarnpkg.com/debian/pubkey.gpg
ARG YARN_KEYRING=/usr/share/keyrings/yarnpkg-archive-keyring.gpg

RUN . /etc/os-release && \
  echo "deb [signed-by=${PGDG_KEYRING}] ${PGDG_REPO} ${VERSION_CODENAME}-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list && \
  curl -fsSL ${PGDG_GPG_KEY} | gpg --dearmor > ${PGDG_KEYRING} && \
  echo "deb [signed-by=${NODE_KEYRING}] ${NODE_REPO} ${VERSION_CODENAME} main" \
  > /etc/apt/sources.list.d/nodejs.list && \
  curl -fsSL ${NODE_GPG_KEY} | gpg --dearmor > ${NODE_KEYRING} && \
  echo "deb [signed-by=${YARN_KEYRING}] ${YARN_REPO} stable main" \
  > /etc/apt/sources.list.d/yarnpkg.list && \
  curl -fsSL ${YARN_GPG_KEY} | gpg --dearmor > ${YARN_KEYRING}

# warning: the py:3.10 image comes with python3.9 installed from debian; do not
# add debian python packages here, they would not be usable for the py37 based
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

RUN pip install --upgrade pip setuptools wheel
RUN pip install gunicorn httpie

COPY requirements.txt /srv/softwareheritage/requirements.txt

RUN pip install -r /srv/softwareheritage/requirements.txt && \
  rm -rf /srv/softwareheritage/.cache/

RUN pip freeze > /srv/softwareheritage/pip-freeze.txt

##################################
# MIRROR image
##################################

FROM python:${pythonversion:-3.10}-slim as swh-mirror
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
ARG PGDG_GPG_KEY=https://www.postgresql.org/media/keys/ACCC4CF8.asc
ARG PGDG_KEYRING=/usr/share/keyrings/pgdg-archive-keyring.gpg

RUN . /etc/os-release && \
  echo "deb [signed-by=${PGDG_KEYRING}] ${PGDG_REPO} ${VERSION_CODENAME}-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list && \
  curl -fsSL ${PGDG_GPG_KEY} | gpg --dearmor > ${PGDG_KEYRING}

# warning: the py:3.10 image comes with python3.11 installed from debian; do not
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

ARG SWH_VER
ENV SWH_VER=${SWH_VER}
ENV DJANGO_SETTINGS_MODULE=swh.web.settings.production

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
