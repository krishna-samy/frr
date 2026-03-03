#!/usr/bin/env python
# SPDX-License-Identifier: ISC

#
# test_zebra_tracker.py
#
# Copyright (c) 2026 by
# Nvidia Corporation
# Donald Sharp
#

"""
test_zebra_tracker.py: Testing five routers with BGP and RIP peering.

Topology:

              10.0.1.0/24
        .1 +------------+ .2
    +------+ r1-eth0     r2-eth0 [r2]
    |      +------------+
    |
    |      10.0.2.0/24
    |  .1 +------------+ .3
    + r1--+ r1-eth1     r3-eth0 [r3]
    |     +------------+
    |
    |      10.0.3.0/24
    |  .1 +------------+ .4
    +-----+ r1-eth2     r4-eth0 [r4]
    |     +------------+
    |
    |      10.0.4.0/24
    |  .1 +------------+ .5
    +-----+ r1-eth3     r5-eth0 [r5]
          +------------+
"""

import os
import re
import sys
import json
import pytest
import functools

pytestmark = [pytest.mark.bgpd, pytest.mark.ripd, pytest.mark.sharpd]

CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../"))

from lib import topotest
from lib.topogen import Topogen, TopoRouter, get_topogen
from lib.topolog import logger


def build_topo(tgen):
    for rname in ["r1", "r2", "r3", "r4", "r5"]:
        tgen.add_router(rname)

    r1 = tgen.gears["r1"]

    # r1-eth0 <-> r2-eth0 via sw1
    sw1 = tgen.add_switch("sw1")
    sw1.add_link(r1)
    sw1.add_link(tgen.gears["r2"])

    # r1-eth1 <-> r3-eth0 via sw2
    sw2 = tgen.add_switch("sw2")
    sw2.add_link(r1)
    sw2.add_link(tgen.gears["r3"])

    # r1-eth2 <-> r4-eth0 via sw3
    sw3 = tgen.add_switch("sw3")
    sw3.add_link(r1)
    sw3.add_link(tgen.gears["r4"])

    # r1-eth3 <-> r5-eth0 via sw4
    sw4 = tgen.add_switch("sw4")
    sw4.add_link(r1)
    sw4.add_link(tgen.gears["r5"])


def setup_module(module):
    tgen = Topogen(build_topo, module.__name__)
    tgen.start_topology()

    router_list = tgen.routers()
    for rname, router in router_list.items():
        router.load_frr_config(
            os.path.join(CWD, "{}/frr.conf".format(rname)),
            [
                (TopoRouter.RD_ZEBRA, None),
                (TopoRouter.RD_BGP, None),
                (TopoRouter.RD_RIP, None),
                (TopoRouter.RD_SHARP, None),
            ],
        )

    tgen.start_router()


def teardown_module(_mod):
    tgen = get_topogen()
    tgen.stop_topology()


def test_bgp_convergence():
    "Verify that all BGP sessions reach Established state"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Checking that all 4 EBGP sessions on r1 reach Established state")

    r1 = tgen.gears["r1"]

    expected_peers = {
        "10.0.1.2": {"state": "Established"},
        "10.0.2.3": {"state": "Established"},
        "10.0.3.4": {"state": "Established"},
        "10.0.4.5": {"state": "Established"},
    }

    def check_bgp_peers():
        output = json.loads(r1.vtysh_cmd("show bgp ipv4 unicast summary json"))
        peers = output.get("peers", {})
        for peer_addr, expected in expected_peers.items():
            if peer_addr not in peers:
                return "peer {} not found".format(peer_addr)
            if peers[peer_addr].get("state") != expected["state"]:
                return "peer {} state is {} expected {}".format(
                    peer_addr,
                    peers[peer_addr].get("state"),
                    expected["state"],
                )
        return None

    _, result = topotest.run_and_expect(check_bgp_peers, None, count=30, wait=1)
    assert result is None, "BGP convergence failed: {}".format(result)


def test_rip_convergence():
    "Verify that RIP routes are learned on all routers"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Checking that r2-r5 each learn remote networks via RIP")

    # r2 should learn routes to 10.0.2.0/24, 10.0.3.0/24, 10.0.4.0/24 via RIP
    # (it already knows 10.0.1.0/24 as directly connected)
    rip_expected = {
        "r2": ["10.0.2.0/24", "10.0.3.0/24", "10.0.4.0/24"],
        "r3": ["10.0.1.0/24", "10.0.3.0/24", "10.0.4.0/24"],
        "r4": ["10.0.1.0/24", "10.0.2.0/24", "10.0.4.0/24"],
        "r5": ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"],
    }

    def check_rip_routes(rname, expected_routes):
        router = tgen.gears[rname]
        output = json.loads(router.vtysh_cmd("show ip route rip json"))
        for route in expected_routes:
            if route not in output:
                return "{}: RIP route {} not found".format(rname, route)
        return None

    for rname, expected_routes in rip_expected.items():
        _, result = topotest.run_and_expect(
            functools.partial(check_rip_routes, rname, expected_routes),
            None,
            count=30,
            wait=2,
        )
        assert result is None, "RIP convergence failed: {}".format(result)


def test_nhg_tracker_show_run():
    "Verify that zebra nexthop-group tracker 20 appears in show running-config on r1"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info(
        "Verifying 'zebra nexthop-group tracker 20' is present in r1 show running-config"
    )

    r1 = tgen.gears["r1"]

    def check_tracker_present():
        output = r1.vtysh_cmd("show running-config")
        if "zebra nexthop-group tracker 20" not in output:
            return "zebra nexthop-group tracker 20 not found in show run"
        return None

    _, result = topotest.run_and_expect(check_tracker_present, None, count=20, wait=1)
    assert result is None, "NHG tracker show run failed: {}".format(result)

    logger.info(
        "Verifying 'show zebra' on r1 reports NHG Tracker Timeout as 20 seconds"
    )

    def check_show_zebra_tracker_20():
        output = r1.vtysh_cmd("show zebra")
        if not re.search(r"NHG Tracker Timeout\s+20 seconds", output):
            return "NHG Tracker Timeout 20 seconds not found in show zebra"
        return None

    _, result = topotest.run_and_expect(
        check_show_zebra_tracker_20, None, count=20, wait=1
    )
    assert result is None, "show zebra tracker timeout check failed: {}".format(result)


def test_nhg_tracker_no_form():
    "Verify that 'no zebra nexthop-group tracker' removes the config from show run"
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info(
        "Issuing 'no zebra nexthop-group tracker' and verifying it is removed from r1 show running-config"
    )

    r1 = tgen.gears["r1"]
    r1.vtysh_cmd("configure terminal\nno zebra nexthop-group tracker\nend")

    def check_tracker_absent():
        output = r1.vtysh_cmd("show running-config")
        if "zebra nexthop-group tracker" in output:
            return "zebra nexthop-group tracker still found in show run"
        return None

    _, result = topotest.run_and_expect(check_tracker_absent, None, count=20, wait=1)
    assert result is None, "NHG tracker negation failed: {}".format(result)

    logger.info(
        "Verifying 'show zebra' on r1 reports NHG Tracker Timeout back to default 60 seconds"
    )

    def check_show_zebra_tracker_default():
        output = r1.vtysh_cmd("show zebra")
        if not re.search(r"NHG Tracker Timeout\s+60 seconds", output):
            return "NHG Tracker Timeout 60 seconds not found in show zebra"
        return None

    _, result = topotest.run_and_expect(
        check_show_zebra_tracker_default, None, count=20, wait=1
    )
    assert result is None, "show zebra tracker default timeout check failed: {}".format(
        result
    )


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args))
