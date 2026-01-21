# Copyright (C) 2022-2025  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import logging
from os import chdir, environ
from pathlib import Path
import re
from shutil import copy, copytree
from time import monotonic, sleep
from uuid import uuid4

from confluent_kafka.admin import AdminClient
import pytest
from python_on_whales import DockerClient, DockerException
import requests

SRC_PATH = Path(__file__).resolve().parent.parent

KAFKA_USERNAME = environ["SWH_MIRROR_TEST_KAFKA_USERNAME"]
KAFKA_PASSWORD = environ["SWH_MIRROR_TEST_KAFKA_PASSWORD"]
KAFKA_BROKER = environ["SWH_MIRROR_TEST_KAFKA_BROKER"]
OBJSTORAGE_URL = environ["SWH_MIRROR_TEST_OBJSTORAGE_URL"]
BASE_URL = environ.get("SWH_MIRROR_TEST_BASE_URL", "http://127.0.0.1:5081")
API_URL = environ.get("SWH_MIRROR_TEST_API_URL", f"{BASE_URL}/api/1")
WFI_TIMEOUT = 60

LOGGER = logging.getLogger(__name__)


INITIAL_SERVICES_STATUS = {
    "{}_amqp": "1/1",
    "{}_content-replayer": "0/0",
    "{}_elasticsearch": "1/1",
    "{}_grafana": "1/1",
    "{}_graph-replayer": "0/0",
    "{}_graph-replayer-content": "0/0",
    "{}_graph-replayer-directory": "0/0",
    "{}_masking-proxy-db": "1/1",
    "{}_memcache": "1/1",
    "{}_mailhog": "1/1",
    "{}_nginx": "1/1",
    "{}_notification-watcher": "0/0",
    "{}_objstorage": "1/1",
    "{}_prometheus": "1/1",
    "{}_prometheus-statsd-exporter": "1/1",
    "{}_redis": "1/1",
    "{}_scheduler": "1/1",
    "{}_scheduler-db": "1/1",
    "{}_scheduler-listener": "1/1",
    "{}_scheduler-runner": "1/1",
    "{}_search": "1/1",
    "{}_search-journal-client-origin": "1/1",
    "{}_search-journal-client-visit": "1/1",
    "{}_storage": "1/1",
    "{}_storage-public": "1/1",
    "{}_vault": "1/1",
    "{}_vault-db": "1/1",
    "{}_vault-worker": "1/1",
    "{}_web": "1/1",
    "{}_web-db": "1/1",
}


@pytest.fixture
def initial_services():
    return INITIAL_SERVICES_STATUS.copy()


@pytest.fixture
def replayer_services():
    return (
        "content-replayer",
        "graph-replayer",
        "graph-replayer-content",
        "graph-replayer-directory",
    )


def pytest_addoption(parser, pluginmanager):
    parser.addoption(
        "--keep-stack", action="store_true", help="Do not teardown the docker stack"
    )
    parser.addoption(
        "--full-check",
        action="store_true",
        help=(
            "Perform an exhaustive check that all objects have been "
            "replicated properly (slow)."
        ),
    )


def wait_for_it(url):
    LOGGER.info(f"Waiting for {url}")
    t0 = monotonic()
    while monotonic() - t0 <= WFI_TIMEOUT:
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            LOGGER.info(f"  Got it: {resp}")
            return
        except Exception:
            sleep(1)
    raise Exception("Connection error")


@pytest.fixture(scope="session")
def docker_client():
    return DockerClient()


@pytest.fixture(scope="module")
def compose_file():
    return "mirror-basic.yml"


@pytest.fixture(scope="module")
def mirror_stack(request, docker_client, tmp_path_factory, compose_file):
    # copy all the stack config files in a tmp directory to be able to resolve
    # templated config files, aka. all the `conf/xxx.yml.test` are processed to
    # generate the corresponding `conf/xxx.yml` file (to inject kafka config
    # entries and the objstorage public URI which also requires basic auth).
    tmp_path = tmp_path_factory.mktemp("mirror")
    copytree(SRC_PATH / "conf", tmp_path / "conf")
    copytree(SRC_PATH / "env", tmp_path / "env")
    copy(SRC_PATH / compose_file, tmp_path)
    Path(tmp_path / "secret").write_bytes(b"not-so-secret\n")
    cwd = Path.cwd()
    chdir(tmp_path)
    # copy test-specific conf files
    uuid = str(uuid4())
    group_prefix = f"{KAFKA_USERNAME}-{uuid}"
    conftmpl = {
        "username": KAFKA_USERNAME,
        "password": KAFKA_PASSWORD,
        "group_id": group_prefix,
        "broker": KAFKA_BROKER,
        "objstorage_url": OBJSTORAGE_URL,
        "cluster_name": "test-mirror-ro",
    }

    for conffile in (tmp_path / "conf").glob("*.yml.test"):
        with open(conffile.as_posix()[:-5], "w") as outf:
            outf.write(conffile.read_text().format(**conftmpl))
    # start the whole cluster
    stack_name = f"swhtest_{uuid.split('-')[0]}"
    LOGGER.info(f"Setup test environment for stack {stack_name} in {tmp_path}")

    LOGGER.info("Create missing secrets")
    for srv in ("storage", "web", "vault", "scheduler", "winery", "masking-proxy"):
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

    default_image_tag = re.search(
        r"image: softwareheritage/mirror:\$\{SWH_IMAGE_TAG:-(?P<tag>[0-9-]+)\}",
        open(compose_file).read(),
    )
    image_tag = environ.get(
        "SWH_IMAGE_TAG",
        default_image_tag.group("tag") if default_image_tag else "unknown",
    )

    LOGGER.info(
        "Deploy docker stack %s from %s with SWH_IMAGE_TAG %s",
        stack_name,
        compose_file,
        image_tag,
    )
    docker_stack = docker_client.stack.deploy(stack_name, compose_file)
    docker_stack._test_group_prefix = group_prefix  # used by get_expected_stats()
    docker_stack._test_conf_template = conftmpl
    try:
        got_exception = False
        # for the sake of early checks...
        LOGGER.info("Sanity checks:")
        wait_for_it(BASE_URL)
        wait_for_it(f"{API_URL}/")
        wait_for_it(f"{BASE_URL}/mail/api/v2/messages")
        yield docker_stack
    except Exception:
        got_exception = True
        raise
    finally:
        if got_exception or request.node.session.testsfailed:
            # dump all logs...
            logsdir = tmp_path / "logs"
            logsdir.mkdir(exist_ok=True)

            for service in docker_stack.services():
                LOGGER.info(
                    f"Dumping logs for {service.spec.name} in {logsdir}/{service.spec.name}.log"
                )
                try:
                    (logsdir / f"{service.spec.name}.log").write_text(
                        docker_client.service.logs(service.spec.name, timestamps=True)
                    )
                except Exception as exc:
                    LOGGER.warning(
                        f"Failed to dump logs for service {service.spec.name}"
                    )
                    LOGGER.warning(exc)

        if not request.config.getoption("keep_stack"):
            LOGGER.info("Remove stack %s", stack_name)
            docker_stack.remove()

            for i in range(5):
                stack_containers = docker_client.container.list(
                    filters={"label=com.docker.stack.namespace": stack_name}
                )
                if not stack_containers:
                    LOGGER.info("No more running containers (loop %s)", i)
                    break
                try:
                    LOGGER.info(
                        "Waiting for all %s containers of %s to be down (loop %s)",
                        len(stack_containers),
                        stack_name,
                        i,
                    )
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
            retries = 0
            while stack_volumes:
                volume = stack_volumes.pop(0)
                try:
                    volume.remove()
                    LOGGER.info("Removed volume %s", volume)
                except DockerException:
                    if retries > 10:
                        LOGGER.exception(
                            "Too many failures, giving up (volume=%s)", volume
                        )
                        break
                    LOGGER.warning("Failed to remove volume %s; retrying...", volume)
                    stack_volumes.append(volume)
                    retries += 1
                    sleep(1)

            networks = docker_client.network.list(
                filters={"label=com.docker.stack.namespace": stack_name}
            )
            for network in networks:
                LOGGER.warning(
                    f"Enforce network {network.id} deletion "
                    "(it should have been deleted already)"
                )
                try:
                    docker_client.network.remove(network.id)
                except DockerException as e:
                    if f"network {network.id} not found" not in e.stderr:
                        LOGGER.error(
                            f"Could not enforce network {network.id} "
                            f"for the stack {stack_name} removal: {e.stderr}"
                        )
        # delete the tmp consumer groups
        try:
            cg_prefix = conftmpl["group_id"]
            LOGGER.info(f"Deleting consumers groups starting with {cg_prefix}")
            adm = AdminClient(
                {
                    "bootstrap.servers": conftmpl["broker"],
                    "sasl.username": conftmpl["username"],
                    "sasl.password": conftmpl["password"],
                    "security.protocol": "sasl_ssl",
                    "sasl.mechanism": "SCRAM-SHA-512",
                }
            )
            cgroups = adm.list_consumer_groups()
            while cgroups.running():
                sleep(1)
            cg_to_del = [
                cg.group_id
                for cg in cgroups.result().valid
                if cg.group_id.startswith(cg_prefix)
            ]
            if cg_to_del:
                cgdel = adm.delete_consumer_groups(cg_to_del)
                while any(x.running() for x in cgdel.values()):
                    sleep(1)
                LOGGER.info(f"Deleted consumer groups {','.join(cg_to_del)}")

        except Exception as exc:
            LOGGER.warning(f"Failed to delete kafka consumer groups {cg_prefix}:")
            LOGGER.warning(exc)

        chdir(cwd)
