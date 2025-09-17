# Copyright (C) 2022-2025  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

from hashlib import sha1
from io import BytesIO
import re
import tarfile
import time
from typing import Dict
from urllib.parse import quote

from confluent_kafka import Consumer, KafkaException
import msgpack
import pytest
from python_on_whales import DockerException
import requests
from swh.storage import get_storage

from .conftest import (
    API_URL,
    BASE_URL,
    KAFKA_BROKER,
    KAFKA_PASSWORD,
    KAFKA_USERNAME,
    LOGGER,
)

SCALE = 2
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(
    max_retries=3,
    pool_connections=5,
    pool_maxsize=10,
)
session.mount(BASE_URL, adapter)


def get(url):
    resp = session.get(url)
    resp.raise_for_status()
    if resp.headers["content-type"].lower() in ("application/json", "text/json"):
        result = resp.json()
    else:
        result = resp.content
    return result


def post(url):
    resp = session.post(url)
    assert resp.status_code in (200, 201, 202)
    if resp.headers["content-type"].lower() == "application/json":
        result = resp.json()
    else:
        result = resp.content
    return result


def service_target_replicas(service):
    if "Replicated" in service.spec.mode:
        return service.spec.mode["Replicated"]["Replicas"]
    elif "Global" in service.spec.mode:
        return 1
    else:
        raise ValueError(f"Unknown mode {service.spec.mode}")


def is_task_running(task):
    try:
        return task.status.state == "running"
    except DockerException as e:
        # A task might already have disappeared before we can get its status.
        # In that case, we know for sure it’s not running.
        if "No such object" in e.stderr:
            return False
        else:
            raise


def wait_services_status(stack, target_status: Dict[str, str]):
    LOGGER.info("Waiting for services %s", target_status)
    last_changed_status: Dict[str, str] = {}
    while True:
        services = [
            service
            for service in stack.services()
            if service.spec.name in target_status
        ]
        status: Dict[str, str] = {
            service.spec.name: "%s/%s"
            % (
                len([True for task in service.ps() if is_task_running(task)]),
                service_target_replicas(service),
            )
            for service in services
        }
        if status == target_status:
            LOGGER.info("Got them all!")
            break
        if status != last_changed_status:
            LOGGER.info(
                "Not yet there %s",
                {k: v for k, v in status.items() if target_status.get(k) != v},
            )
            last_changed_status = status
        time.sleep(1)
    return status == target_status


def wait_for_log_entry(
    docker_client, service, log_entry, occurrences=1, with_stderr=False
):
    count = 0
    for stream_type, stream_content in docker_client.service.logs(
        service, follow=True, stream=True
    ):
        LOGGER.debug("%s output: %s", service.spec.name, stream_content)
        if not with_stderr and stream_type != "stdout":
            continue
        ncount = len(
            re.findall(
                log_entry,
                stream_content.decode(errors="replace"),
            )
        )
        if not ncount:
            if log_entry in stream_content.decode(errors="replace"):
                ncount = 1
        count += ncount
        if count >= occurrences:
            break


def get_stats_from_storage(url):

    from swh.model.model import ReleaseTargetType, SnapshotTargetType
    import swh.storage.algos.dir_iterators as algo_DI
    import swh.storage.algos.origin as algo_O
    import swh.storage.algos.revisions_walker as algo_RW
    import swh.storage.algos.snapshot as algo_SN

    storage = get_storage(
        cls="remote",
        url=f"{BASE_URL}/storage-public",
        max_retries=5,
        pool_connections=10,
        pool_maxsize=20,
    )

    stats = {"origin": url}

    visits = list(algo_O.iter_origin_visits(storage, url))
    stats["visit"] = len(visits)

    snp_ids = {
        vs.snapshot
        for v in visits
        for vs in algo_O.iter_origin_visit_statuses(storage, url, v.visit)
        if vs.snapshot
    }

    snapshots = [
        algo_SN.snapshot_get_all_branches(storage, snp_id) for snp_id in snp_ids
    ]
    branches = [br for snp in snapshots for br in snp.branches.values() if br]

    stats["release"] = len(
        {br for br in branches if br.target_type == SnapshotTargetType.RELEASE}
    )
    stats["alias"] = len(
        {br for br in branches if br.target_type == SnapshotTargetType.ALIAS}
    )
    stats["branch"] = len(
        {br for br in branches if br.target_type == SnapshotTargetType.REVISION}
    )

    # resolve aliases
    rev_ids = {
        br.target for br in branches if br.target_type == SnapshotTargetType.REVISION
    }
    rel_ids = {
        br.target for br in branches if br.target_type == SnapshotTargetType.RELEASE
    }
    dir_ids = {
        br.target for br in branches if br.target_type == SnapshotTargetType.DIRECTORY
    }
    snp_ids.update(
        {br.target for br in branches if br.target_type == SnapshotTargetType.SNAPSHOT}
    )

    state = algo_RW.State()

    all_revs = set()
    all_cnts = set()
    all_dirs = set()

    all_rels = storage.release_get(list(rel_ids))
    for rel in all_rels:
        if rel.target_type == ReleaseTargetType.REVISION:
            rev_ids.add(rel.target)
        elif rel.target_type == ReleaseTargetType.DIRECTORY:
            dir_ids.add(rel.target)
        elif rel.target_type == ReleaseTargetType.CONTENT:
            all_cnts.add(rel.target)
        elif rel.target_type == ReleaseTargetType.RELEASE:
            raise ValueError("rel: Not yet supported")
        elif rel.target_type == ReleaseTargetType.SNAPSHOT:
            raise ValueError("snp: Not yet supported")

    for rev_id in rev_ids:
        all_revs.add(rev_id)
        for rev_d in algo_RW.BFSRevisionsWalker(storage, rev_id, state=state):
            all_revs.add(rev_d["id"])
            dir_ids.add(rev_d["directory"])

    for dir_id in dir_ids:
        all_dirs.add(dir_id)
        for direntry in algo_DI.dir_iterator(storage, dir_id):
            if direntry["type"] == "dir":
                all_dirs.add(direntry["target"])
            elif direntry["type"] == "file":
                all_cnts.add(direntry["target"])
    stats["cnt"] = len(all_cnts)
    stats["dir"] = len(all_dirs)
    stats["rev"] = len(all_revs)
    return stats


def get_expected_stats(group_prefix):

    cfg = {
        "bootstrap.servers": KAFKA_BROKER,
        "sasl.username": KAFKA_USERNAME,
        "sasl.password": KAFKA_PASSWORD,
        "group.id": f"{group_prefix}_stats",
        "security.protocol": "sasl_ssl",
        "sasl.mechanism": "SCRAM-SHA-512",
        "session.timeout.ms": 600000,
        "max.poll.interval.ms": 3600000,
        "message.max.bytes": 1000000000,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
        "enable.partition.eof": True,
    }

    partitions = set()

    def on_assign(cons, parts):
        LOGGER.info("assignment %s", parts)
        for p in parts:
            partitions.add(p.partition)

    consumer = Consumer(cfg)
    consumer.subscribe(["swh.test.objects.stats"], on_assign=on_assign)
    stats = {}
    try:
        while True:
            msg = consumer.poll(timeout=10.0)
            if msg is None:
                if not partitions:
                    break
                continue
            if msg.error():
                if msg.error().name() == "_PARTITION_EOF":
                    partitions.discard(msg.partition())
                    if not partitions:
                        break
                else:
                    raise KafkaException(msg.error())
            else:
                # Proper message
                k = msgpack.unpackb(msg.key())
                v = msgpack.unpackb(msg.value())
                LOGGER.info(
                    "%% %s [%d] at offset %d with key %s:\n",
                    msg.topic(),
                    msg.partition(),
                    msg.offset(),
                    k,
                )
                assert k == v["origin"]
                stats[k] = v
    except KeyboardInterrupt:
        assert False, "%% Aborted by user"
    finally:
        consumer.unsubscribe()
        consumer.close()
    return stats


def test_mirror(
    request, docker_client, mirror_stack, initial_services, replayer_services
):
    initial_services_status = {
        k.format(mirror_stack.name): v for k, v in initial_services.items()
    }
    wait_services_status(mirror_stack, initial_services_status)

    ########################
    # run replayer services
    for service_name in replayer_services:
        service = docker_client.service.inspect(f"{mirror_stack}_{service_name}")
        LOGGER.info("Scale %s to %d", service.spec.name, SCALE)
        service.scale(SCALE)
        wait_for_log_entry(
            docker_client,
            service,
            "Starting the SWH mirror (graph|content) replayer",
            SCALE,
        )

    for service_name in replayer_services:
        service = docker_client.service.inspect(f"{mirror_stack}_{service_name}")
        # wait for the replaying to be done (stop_on_oef is true)
        LOGGER.info("Wait for %s to be done", service.spec.name)
        wait_for_log_entry(docker_client, service, "Done.", SCALE)

        LOGGER.info("Scale %s to 0", service.spec.name)
        service.scale(0)
        wait_services_status(mirror_stack, {service.spec.name: "0/0"})

        # TODO: check there are no error reported in redis after the replayers are done

    origins = get(f"{API_URL}/origins/")
    expected_stats = get_expected_stats(group_prefix=mirror_stack._test_group_prefix)
    # only check the complete replication when asked for (this is slow)
    if request.config.getoption("full_check"):
        # check replicated archive is in good shape
        LOGGER.info("Check replicated archive")
        # seems the graph replayer is OK, let's check the archive can tell something
        expected_origins = sorted(expected_stats)
        assert len(origins) == len(expected_origins)
        assert sorted(o["url"] for o in origins) == expected_origins

        for origin, expected in expected_stats.items():
            assert origin == expected["origin"]
            t0 = time.monotonic()
            origin_stats = get_stats_from_storage(origin)
            LOGGER.info("%s", origin_stats)
            LOGGER.info("took %.2fs", time.monotonic() - t0)
            assert origin_stats == expected
            LOGGER.info("%s is OK", origin)

    ########################
    # test the vault service
    cooks = []
    # first start all the cookings
    for origin in origins:
        LOGGER.info("Cook HEAD for %s", origin["url"])
        visit = get(
            f"{API_URL}/origin/{origin['url']}/visit/latest/?require_snapshot=true"
        )
        assert visit
        snp = get(visit["snapshot_url"])
        assert snp
        branches = snp.get("branches", {})
        head = branches.get("HEAD")
        assert head

        while True:
            if head["target_type"] == "alias":
                head = branches[head["target"]]
            elif head["target_type"] == "release":
                head = get(head["target_url"])
            elif head["target_type"] == "directory":
                swhid = f"swh:1:dir:{head['target']}"
                break
            elif head["target_type"] == "revision":
                rev = get(head["target_url"])
                swhid = f"swh:1:dir:{rev['directory']}"
                break

        LOGGER.info("Directory is %s", swhid)
        cook = post(f"{API_URL}/vault/flat/{swhid}/")
        assert cook
        assert cook["status"] in ("new", "pending")
        cooks.append((origin["url"], swhid, cook))

    # then wait for successful cooks
    while not all(cook["status"] == "done" for _, _, cook in cooks):
        origin, swhid, cook = cooks.pop(0)
        cook = get(f"{API_URL}/vault/flat/{swhid}")
        cooks.append((origin, swhid, cook))
    LOGGER.info("All origins have been cooked")

    # should all be in "done" status
    for origin, swhid, cook in cooks:
        LOGGER.info(f"Validating cooked directory for {origin} ({swhid})")
        assert cook["status"] == "done"
        # so we can download it
        tarfilecontent = get(cook["fetch_url"])
        assert isinstance(tarfilecontent, bytes)
        tarfileobj = tarfile.open(fileobj=BytesIO(tarfilecontent))
        filelist = tarfileobj.getnames()
        assert all(fname.startswith(swhid) for fname in filelist)
        for path in filelist[1:]:
            tarinfo = tarfileobj.getmember(path)
            url = f"{API_URL}/directory/{quote(path[10:])}/"
            expected = get(url)  # remove the 'swh:1:dir:' part
            LOGGER.debug("Retrieved from storage: %s → %s", url, expected)
            if expected["type"] == "dir":
                assert tarinfo.isdir()
            elif expected["type"] == "file":
                if expected["perms"] == 0o120000:
                    assert tarinfo.issym()
                    tgt = get(expected["target_url"])
                    symlnk = get(tgt["data_url"])
                    assert symlnk == tarinfo.linkpath.encode()
                else:
                    assert tarinfo.isfile()
                    assert expected["length"] == tarinfo.size
                    assert (
                        sha1(tarfileobj.extractfile(tarinfo).read()).hexdigest()
                        == expected["checksums"]["sha1"]
                    )
    LOGGER.info("All cooked origins have been validated")

    ########################
    # test the TDN handling
    service = docker_client.service.inspect(f"{mirror_stack}_notification-watcher")
    LOGGER.info("Scale %s to %d", service.spec.name, 1)
    service.scale(1)

    removal_id = "test_removal_swh_core"
    LOGGER.info("Scaled %s to %d", service.spec.name, 1)
    subject = f"[Action needed] Removal from the main Software Heritage archive ({removal_id})"
    # beware these are not "basic" quotes...
    logentries = [
        "Watching notifications for mirrors",
        f"Received a removal notification “{removal_id}”",
        f"Sending email “{subject}”",
    ]
    for logentry in logentries:
        LOGGER.info("Waiting for log entry %s", logentry)
        wait_for_log_entry(docker_client, service, logentry, with_stderr=True)

    # check the notification email has been sent
    LOGGER.info("Checking expected email message has been sent")
    for i in range(10):
        messages = get(f"{BASE_URL}/mail/api/v2/messages")
        if messages["count"] >= 1:
            break
        time.sleep(1)

    assert messages["count"] >= 1
    for msg in messages["items"]:
        if msg["Content"]["Headers"]["Subject"][0] == subject:
            break
    else:
        assert False, "Expected email message missing"

    # check the objects under the origin are masked
    origin = "https://github.com/SoftwareHeritage/swh-core"
    LOGGER.info(f"Checking swh-core github origin has been masked ({origin})")
    with pytest.raises(requests.HTTPError) as exc:
        get(f"{API_URL}/origin/{origin}/visit/latest/")
    assert exc.value.response.status_code == 403

    # check that the swh.core pypi package remains OK
    origin = "https://pypi.org/project/swh.core/"
    LOGGER.info(f"Checking swh-core pypi origin is still available ({origin})")
    origin_stats = get_stats_from_storage(origin)
    assert origin_stats == expected_stats[origin]

    # TODO: respawn a pair of vault cooking to check both origins are handled
    # properly, aka the masked one should not be cookable while the pypi
    # package should work the same as before...
    #
    # NOTE: this is currently not a valid test because there is no vault cache
    # invalidation mechanism related to TDN/masking so far. So the already
    # cooked export for this now-masked origin will still be present (which is
    # an issue but not a mirror specific one).
