# Copyright (C) 2022  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import logging
from os import chdir, environ
from pathlib import Path
from shutil import copy, copytree
from uuid import uuid4

import pytest
from python_on_whales import DockerClient, DockerException

SRC_PATH = Path(__file__).resolve().parent.parent

KAFKA_USERNAME = environ["SWH_MIRROR_TEST_KAFKA_USERNAME"]
KAFKA_PASSWORD = environ["SWH_MIRROR_TEST_KAFKA_PASSWORD"]
KAFKA_BROKER = environ["SWH_MIRROR_TEST_KAFKA_BROKER"]
KAFKA_GROUPID = f"{KAFKA_USERNAME}-{uuid4()}"
OBJSTORAGE_URL = environ["SWH_MIRROR_TEST_OBJSTORAGE_URL"]
API_URL = environ.get("SWH_MIRROR_TEST_API_URL", "http://127.0.0.1:5080/api/1")
WFI_TIMEOUT = 60

LOGGER = logging.getLogger(__name__)


def pytest_addoption(parser, pluginmanager):
    parser.addoption(
        "--keep-stack", action="store_true", help="Do not teardown the docker stack"
    )


@pytest.fixture(scope="session")
def docker_client():
    return DockerClient()


# scope='session' so we use the same container for all the tests;
@pytest.fixture(scope="session")
def mirror_stack(request, docker_client, tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("mirror")
    copytree(SRC_PATH / "conf", tmp_path / "conf")
    copytree(SRC_PATH / "env", tmp_path / "env")
    copy(SRC_PATH / "mirror.yml", tmp_path)
    Path(tmp_path / "secret").write_bytes(b"not-so-secret\n")
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
    for srv in ("storage", "web", "vault", "scheduler"):
        secret_name = f"swh-mirror-{srv}-db-password"
        try:
            docker_client.secret.create(secret_name, tmp_path / "secret")
            LOGGER.info("Created secret %s", secret_name)
        except DockerException as e:
            if "code = AlreadyExists" not in e.stderr:
                raise

    LOGGER.info("Remove config objects (if any)")
    existing_configs = docker_client.config.list(
        filters={"label=com.docker.stack.namespace": stack_name}
    )
    for config in existing_configs:
        config.remove()

    image_tag = environ.get("SWH_IMAGE_TAG", None)
    assert image_tag and image_tag != "latest", (
        "SWH_IMAGE_TAG needs to be set to a build tag "
        "to avoid any incompatibilities in the stack"
    )

    LOGGER.info("Deploy docker stack %s with SWH_IMAGE_TAG %s", stack_name, image_tag)
    docker_stack = docker_client.stack.deploy(stack_name, "mirror.yml")

    yield docker_stack

    if not request.config.getoption("keep_stack"):
        LOGGER.info("Remove stack %s", stack_name)
        docker_stack.remove()
        stack_containers = docker_client.container.list(
            filters={"label=com.docker.stack.namespace": stack_name}
        )

        try:
            LOGGER.info("Waiting for all containers of %s to be down", stack_name)
            docker_client.container.wait(stack_containers)
        except DockerException as e:
            # We have a TOCTOU issue, so skip the error if some containers have already
            # been stopped by the time we wait for them.
            if "No such container" not in e.stderr:
                raise

        LOGGER.info("Remove volumes of stack %s", stack_name)
        stack_volumes = docker_client.volume.list(
            filters={"label=com.docker.stack.namespace": stack_name}
        )
        for volume in stack_volumes:
            try:
                volume.remove()
            except DockerException:
                LOGGER.exception("Failed to remove volume %s", volume)

    chdir(cwd)
