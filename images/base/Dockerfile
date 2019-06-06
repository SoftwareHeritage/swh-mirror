ARG debianversion=stretch
FROM debian:${debianversion:-stretch}
LABEL maintainer="Software Heritage <sysop@softwareheritage.org>"
ENV PROJECT_NAME swh-base

RUN export DEBIAN_FRONTEND=noninteractive && \
  apt-get update && apt-get upgrade -y && \
  apt-get install -y \
    apt-transport-https curl lsb-release

RUN echo deb http://deb.debian.org/debian/ $(lsb_release -sc)-backports main \
         > /etc/apt/sources.list.d/backports.list

RUN echo deb [trusted=yes] https://debian.softwareheritage.org/ $(lsb_release -sc)-swh main  \
         > /etc/apt/sources.list.d/softwareheritage.list

RUN mkdir /etc/softwareheritage
RUN mkdir -p /var/run/gunicorn/swh
RUN mkdir -p /srv/softwareheritage/objects

ENV SWH_CONFIG_FILENAME=/etc/softwareheritage/config.yml
ENV LC_ALL=C.UTF-8

RUN export DEBIAN_FRONTEND=noninteractive && \
  apt-get update && \
  apt-get install -y \
    -t $(lsb_release -sc)-backports \
	postgresql-client \
	gunicorn3 \
    python3-swh.objstorage \
    python3-swh.scheduler \
    python3-swh.storage \
    python3-swh.journal \
	&& \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*


COPY conf/logconfig.ini /etc/gunicorn/logconfig.ini
COPY conf/gunicorn.cfg /etc/gunicorn/swh.cfg

COPY base/entrypoint.sh /
ENTRYPOINT ["/entrypoint.sh"]
