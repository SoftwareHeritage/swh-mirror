# Copyright (C) 2022  The Software Heritage developers
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
from python_on_whales import DockerException
import requests

from .conftest import API_URL, KAFKA_GROUPID, KAFKA_PASSWORD, KAFKA_USERNAME, LOGGER

INITIAL_SERVICES_STATUS = {
    "{}_amqp": "1/1",
    "{}_content-replayer": "0/0",
    "{}_grafana": "1/1",
    "{}_graph-replayer": "0/0",
    "{}_memcache": "1/1",
    "{}_mailhog": "1/1",
    "{}_nginx": "1/1",
    "{}_objstorage": "1/1",
    "{}_prometheus": "1/1",
    "{}_prometheus-statsd-exporter": "1/1",
    "{}_redis": "1/1",
    "{}_storage": "1/1",
    "{}_storage-db": "1/1",
    "{}_web": "1/1",
    "{}_web-db": "1/1",
    "{}_vault": "1/1",
    "{}_vault-db": "1/1",
    "{}_vault-worker": "1/1",
    "{}_scheduler": "1/1",
    "{}_scheduler-db": "1/1",
    "{}_scheduler-listener": "1/1",
    "{}_scheduler-runner": "1/1",
}
SCALE = 2


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


def wait_services_status(stack, target_status: Dict[str, int]):
    LOGGER.info("Waiting for services %s", target_status)
    last_changed_status = {}
    while True:
        services = [
            service
            for service in stack.services()
            if service.spec.name in target_status
        ]
        status = {
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
            LOGGER.info("Not yet there %s", status)
            last_changed_status = status
        time.sleep(1)
    return status == target_status


def wait_for_log_entry(docker_client, service, log_entry, occurrences=1):
    count = 0
    for stream_type, stream_content in docker_client.service.logs(
        service, follow=True, stream=True
    ):
        LOGGER.debug("%s output: %s", service.spec.name, stream_content)
        if stream_type != "stdout":
            continue
        count += len(
            re.findall(
                re.escape(log_entry.encode("us-ascii", errors="replace")),
                stream_content,
            )
        )
        if count >= occurrences:
            break


def content_get(url, done):
    content = get(url)
    swhid = f"swh:1:cnt:{content['checksums']['sha1_git']}"
    # checking the actual blob is present and valid
    # XXX: a bit sad...
    try:
        data = get(content["data_url"])
    except Exception as exc:
        LOGGER.error("Failed loading %s", content["data_url"], exc_info=exc)
        raise
    assert len(data) == content["length"]
    assert sha1(data).hexdigest() == content["checksums"]["sha1"]

    if swhid not in done:
        done.add(swhid)
        yield content


def directory_get(url, done):
    directory = get(url)
    id = url.split("/")[-2]
    swhid = f"swh:1:dir:{id}"
    if swhid not in done:
        done.add(swhid)
        for entry in directory:
            if entry["type"] == "file":
                swhid = f"swh:1:cnt:{entry['target']}"
                if swhid not in done:
                    yield from content_get(entry["target_url"], done)
            elif entry["type"] == "dir":
                swhid = f"swh:1:dir:{entry['target']}"
                if swhid not in done:
                    yield from directory_get(entry["target_url"], done)


def revision_get(url, done):
    revision = get(url)
    swhid = f"swh:1:rev:{revision['id']}"
    if swhid not in done:
        done.add(swhid)
        yield revision
        swhid = f"swh:1:dir:{revision['directory']}"
        if swhid not in done:
            yield from directory_get(revision["directory_url"], done)
        for parent in revision["parents"]:
            if f"swh:1:rev:{parent['id']}" not in done:
                yield from revision_get(parent["url"], done)


def snapshot_get(url, done):
    snapshot = get(url)
    for branchname, branch in snapshot["branches"].items():
        if branch:
            yield from resolve_target(
                branch["target_type"],
                branch["target"],
                branch["target_url"],
                done,
            )


def origin_get(url, done=None):
    if done is None:
        done = set()
    visit = get(f"{API_URL}/origin/{url}/visit/latest/?require_snapshot=true")
    if not visit.get("snapshot"):
        return
    swhid = f"swh:1:snp:{visit['snapshot']}"
    if swhid not in done:
        done.add(swhid)
        snapshot_url = visit["snapshot_url"]
        if snapshot_url:
            yield from snapshot_get(snapshot_url, done)


def resolve_target(target_type, target, target_url, done):
    if target_type == "revision":
        if f"swh:1:rev:{target}" not in done:
            yield from revision_get(target_url, done)
    elif target_type == "release":
        if f"swh:1:rel:{target}" not in done:
            yield from release_get(target_url, done)
    elif target_type == "directory":
        if f"swh:1:dir:{target}" not in done:
            yield from directory_get(target_url, done)
    elif target_type == "content":
        if f"swh:1:cnt:{target}" not in done:
            yield from content_get(target_url, done)
    elif target_type == "snapshot":
        if f"swh:1:snp:{target}" not in done:
            yield from snapshot_get(target_url, done)
    # elif target_type == "alias":
    #     if f"swh:1:snp:{target}" not in done:
    #         yield from snapshot_get(target_url, done)


def release_get(url, done):
    release = get(url)
    swhid = f"swh:1:rel:{release['id']}"
    if swhid not in done:
        done.add(swhid)
        yield release
        yield from resolve_target(
            release["target_type"], release["target"], release["target_url"], done
        )


def branch_get(url):
    branches = set()
    visits = get(f"{API_URL}/origin/{url}/visits/")
    for visit in visits:
        snapshot_url = visit.get("snapshot_url")
        while snapshot_url:
            snapshot = get(snapshot_url)
            for name, tgt in snapshot["branches"].items():
                if tgt is not None:
                    branches.add(
                        (name, tgt["target_type"], tgt["target"], tgt["target_url"])
                    )
            snapshot_url = snapshot["next_branch"]
    return len(visits), branches


timing_stats = []


def get(url):
    t0 = time.time()
    resp = requests.get(url)
    if resp.headers["content-type"].lower() == "application/json":
        result = resp.json()
    else:
        result = resp.content
    timing_stats.append(time.time() - t0)
    return result


def post(url):
    t0 = time.time()
    resp = requests.post(url)
    assert resp.status_code in (200, 201, 202)
    if resp.headers["content-type"].lower() == "application/json":
        result = resp.json()
    else:
        result = resp.content
    timing_stats.append(time.time() - t0)
    return result


def get_stats(origin):
    result = {"origin": origin}

    swhids = set()
    list(origin_get(origin, done=swhids))
    result["cnt"] = len([swhid for swhid in swhids if swhid.startswith("swh:1:cnt:")])
    result["dir"] = len([swhid for swhid in swhids if swhid.startswith("swh:1:dir:")])
    result["rev"] = len([swhid for swhid in swhids if swhid.startswith("swh:1:rev:")])

    visits, branches = branch_get(origin)
    result["visit"] = visits
    result["release"] = len([br for br in branches if br[1] == "release"])
    result["alias"] = len([br for br in branches if br[1] == "alias"])
    result["branch"] = len([br for br in branches if br[1] == "revision"])

    return result, swhids


def get_expected_stats():

    cfg = {
        "bootstrap.servers": "broker1.journal.staging.swh.network:9093",
        "sasl.username": KAFKA_USERNAME,
        "sasl.password": KAFKA_PASSWORD,
        "group.id": KAFKA_GROUPID,
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
    return stats


def test_mirror(docker_client, mirror_stack):
    initial_services_status = {
        k.format(mirror_stack.name): v for k, v in INITIAL_SERVICES_STATUS.items()
    }
    wait_services_status(mirror_stack, initial_services_status)

    # run replayer services
    for service_type in ("content", "graph"):
        service = docker_client.service.inspect(
            f"{mirror_stack}_{service_type}-replayer"
        )
        LOGGER.info("Scale %s to 1", service.spec.name)
        service.scale(1)
        wait_services_status(mirror_stack, {service.spec.name: "1/1"})
        wait_for_log_entry(
            docker_client,
            service,
            f"Starting the SWH mirror {service_type} replayer",
            1,
        )

        LOGGER.info("Scale %s to %d", service.spec.name, SCALE)
        service.scale(SCALE, detach=True)
        wait_for_log_entry(
            docker_client,
            service,
            f"Starting the SWH mirror {service_type} replayer",
            SCALE,
        )

        # wait for the replaying to be done (stop_on_oef is true)
        LOGGER.info("Wait for %s to be done", service.spec.name)
        wait_for_log_entry(docker_client, service, "Done.", SCALE)

        LOGGER.info("Scale %s to 0", service.spec.name)
        service.scale(0)
        wait_services_status(mirror_stack, {service.spec.name: "0/0"})

        # TODO: check there are no error reported in redis after the replayers are done

    origins = get(f"{API_URL}/origins/")
    if False:
        # check replicated archive is in good shape
        expected_stats = get_expected_stats()
        LOGGER.info("Check replicated archive")
        # seems the graph replayer is OK, let's check the archive can tell something
        expected_origins = sorted(expected_stats)
        assert len(origins) == len(expected_origins)
        assert sorted(o["url"] for o in origins) == expected_origins

        for origin, expected in expected_stats.items():
            timing_stats.clear()
            assert origin == expected["origin"]
            origin_stats, swhids = get_stats(origin)
            LOGGER.info("%s", origin_stats)
            LOGGER.info("%d REQS took %ss", len(timing_stats), sum(timing_stats))
            assert origin_stats == expected
            LOGGER.info("%s is OK", origin)

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
            else:
                breakpoint()

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
    # should all be in "done" status
    for origin, swhid, cook in cooks:
        assert cook["status"] == "done"
        # so we can download it
        tarfilecontent = get(cook["fetch_url"])
        assert isinstance(tarfilecontent, bytes)
        tarfileobj = tarfile.open(fileobj=BytesIO(tarfilecontent))
        filelist = tarfileobj.getnames()
        assert all(fname.startswith(swhid) for fname in filelist)
        for path in filelist[1:]:
            tarinfo = tarfileobj.getmember(path)
            url = f"{API_URL}/directory/{quote(path[10:])}"
            expected = get(url)  # remove the 'swh:1:dir:' part
            LOGGER.info("Retrieved from storage: %s → %s", url, expected)
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
            else:
                breakpoint()
                pass
