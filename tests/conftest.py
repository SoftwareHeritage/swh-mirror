# Copyright (C) 2022  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import logging
from os import chdir, environ
from pathlib import Path
from shutil import copy, copytree
import time
from uuid import uuid4

import pytest
import testinfra

APIURL = "http://127.0.0.1:5080/api/1/"
SWH_IMAGE_TAG = environ["SWH_IMAGE_TAG"]
SRC_PATH = Path(__file__).resolve().parent.parent

KAFKA_USERNAME = environ["SWH_MIRROR_TEST_KAFKA_USERNAME"]
KAFKA_PASSWORD = environ["SWH_MIRROR_TEST_KAFKA_PASSWORD"]
KAFKA_BROKER = environ["SWH_MIRROR_TEST_KAFKA_BROKER"]
KAFKA_GROUPID = f"{KAFKA_USERNAME}-{uuid4()}"
OBJSTORAGE_URL = environ["SWH_MIRROR_TEST_OBJSTORAGE_URL"]
WFI_TIMEOUT = 60

LOGGER = logging.getLogger(__name__)


def pytest_addoption(parser, pluginmanager):
    parser.addoption(
        "--keep-stack", action="store_true", help="Do not teardown the docker stack"
    )


@pytest.fixture(scope="session")
def docker_host():
    return testinfra.get_host("local://")


# scope='session' so we use the same container for all the tests;
@pytest.fixture(scope="session")
def mirror_stack(request, docker_host, tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("mirror")
    copytree(SRC_PATH / "conf", tmp_path / "conf")
    copytree(SRC_PATH / "env", tmp_path / "env")
    copy(SRC_PATH / "mirror.yml", tmp_path)
    cwd = Path.cwd()
    chdir(tmp_path)
    # copy test-specific conf files
    conftmpl = {
        "username": KAFKA_USERNAME,
        "password": KAFKA_PASSWORD,
        "group_id": KAFKA_GROUPID,
        "broker": KAFKA_BROKER,
        "objstorage_url": OBJSTORAGE_URL,
    }

    for conffile in (tmp_path / "conf").glob("*.yml.test"):
        with open(conffile.as_posix()[:-5], "w") as outf:
            outf.write(conffile.read_text().format(**conftmpl))
    # start the whole cluster
    stack_name = f"swhtest_{tmp_path.name}"

    LOGGER.info("Create missing secrets")
    existing_secrets = [
        line.strip()
        for line in docker_host.check_output(
            "docker secret ls --format '{{.Name}}'"
        ).splitlines()
    ]
    for srv in ("storage", "web", "vault", "scheduler"):
        secret = f"swh-mirror-{srv}-db-password"
        if secret not in existing_secrets:
            LOGGER.info("Creating secret %s", secret)
            docker_host.check_output(
                f"echo not-so-secret | docker secret create {secret} -"
            )
    LOGGER.info("Remove config objects (if any)")
    existing_configs = [
        line.strip()
        for line in docker_host.check_output(
            "docker config ls --format '{{.Name}}'"
        ).splitlines()
    ]
    for cfg in existing_configs:
        if cfg.startswith(f"{stack_name}_"):
            docker_host.check_output(f"docker config rm {cfg}")

    LOGGER.info("Deploy docker stack %s", stack_name)
    docker_host.check_output(f"docker stack deploy -c mirror.yml {stack_name}")

    yield stack_name

    # breakpoint()
    if not request.config.getoption("keep_stack"):
        LOGGER.info("Remove stack %s", stack_name)
        docker_host.check_output(f"docker stack rm {stack_name}")
        # wait for services to be down
        LOGGER.info("Wait for all services of %s to be down", stack_name)
        while docker_host.check_output(
            "docker service ls --format {{.Name}} "
            f"--filter label=com.docker.stack.namespace={stack_name}"
        ):
            time.sleep(0.2)

        # give a bit of time to docker to sync the state of service<->volumes
        # relations so the next step runs ok
        time.sleep(20)
        LOGGER.info("Remove volumes of stack %s", stack_name)
        for volume in docker_host.check_output(
            "docker volume ls --format {{.Name}} "
            f"--filter label=com.docker.stack.namespace={stack_name}"
        ).splitlines():

            try:
                docker_host.check_output(f"docker volume rm {volume}")
            except AssertionError:
                LOGGER.error("Failed to remove volume %s", volume)

    chdir(cwd)
