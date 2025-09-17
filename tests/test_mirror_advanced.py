# Copyright (C) 2025  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

import pytest

from .test_mirror_basic import test_mirror  # noqa


@pytest.fixture
def replayer_services(replayer_services):
    return replayer_services + ("graph-replayer-content", "graph-replayer-directory")


@pytest.fixture
def initial_services(initial_services):
    initial_services.update(
        {
            "{}_graph-replayer-content": "0/0",
            "{}_graph-replayer-directory": "0/0",
        }
    )
    return initial_services


@pytest.fixture(scope="module")
def compose_file():
    return "mirror-advanced.yml"
