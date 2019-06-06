ARG debianversion=stretch
FROM debian:${debianversion:-stretch}
LABEL maintainer="Software Heritage <sysop@softwareheritage.org>"
ENV PROJECT_NAME swh-web

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
RUN mkdir -p /var/lib/swh

ENV SWH_CONFIG_FILENAME=/etc/softwareheritage/config.yml
ENV LC_ALL=C.UTF-8
ENV DJANGO_SETTINGS_MODULE=swh.web.settings.production

RUN export DEBIAN_FRONTEND=noninteractive && \
  apt-get update && \
  apt-get install -y \
    -t $(lsb_release -sc)-backports \
	gunicorn3 \
	python3-magic \
    python3-swh.web \
	&& \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

COPY conf/logconfig.ini /etc/gunicorn/logconfig.ini
COPY conf/gunicorn.cfg /etc/gunicorn/swh.cfg

COPY web/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
