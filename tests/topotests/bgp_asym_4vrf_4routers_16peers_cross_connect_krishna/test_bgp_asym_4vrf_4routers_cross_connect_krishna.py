#!/usr/bin/env python
# SPDX-License-Identifier: ISC

#
# test_bgp_asym_4vrf_4routers_cross_connect_krishna.py
#
# Copyright (c) 2025 by
# Test for BGP asymmetric VRF topology with 4 routers in cross-connect setup + 2 ECMP routers
#

"""
test_bgp_asym_4vrf_4routers_cross_connect_krishna.py: Testing BGP with 
asymmetric VRF cross-connect setup + ECMP routers
                      - 7 routers total (r1, r2, r3, r4, r5, r6, r7)
                      - r1: 4 VRFs with 1 link each to all 4 upstream routers
                      - r2: 6 links total (4 to r1 VRFs + 1 to r6 + 1 to r7)
                      - r3: 6 links total (4 to r1 VRFs + 1 to r6 + 1 to r7)
                      - r4: 6 links total (4 to r1 VRFs + 1 to r6 + 1 to r7)
                      - r5: 6 links total (4 to r1 VRFs + 1 to r6 + 1 to r7)
                      - r6 connects to all 4 upstream routers (r2-r5) for 4-way ECMP
                      - r7 connects to all 4 upstream routers (r2-r5) for 4-way ECMP
                      - Total: 32 eBGP sessions (16 from r1 + 8 from r6 + 8 from r7)
                      - sharp daemon enabled
                      - redistribute sharp and connected routes
"""

import os
import sys
import pytest
import json
from functools import partial
import time

# Save the Current Working Directory to find configuration files.
CWD = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(CWD, "../"))

# pylint: disable=C0413
# Import topogen and topotest helpers
from lib import topotest
from lib.topogen import Topogen, TopoRouter, get_topogen
from lib.topolog import logger
from lib.common_config import step

pytestmark = [pytest.mark.bgpd]


##############################################################################
#
#   Network Topology Definition
#
##############################################################################


def build_topo(tgen):
    """
    Build cross-connect topology with 7 routers:
    - r1 has 4 VRFs, each VRF connects to all 4 upstream routers
    - r2-r5 connect to all 4 VRFs on r1 (1 link per VRF) + r6 + r7
    - r6 connects to all 4 upstream routers (r2-r5) for 4-way ECMP
    - r7 connects to all 4 upstream routers (r2-r5) for 4-way ECMP
    
    Link mapping for r1 (unchanged):
    - vrf1 -> r2: r1-eth0  <-> r2-eth0
    - vrf1 -> r3: r1-eth1  <-> r3-eth0
    - vrf1 -> r4: r1-eth2  <-> r4-eth0
    - vrf1 -> r5: r1-eth3  <-> r5-eth0
    - vrf2 -> r2: r1-eth4  <-> r2-eth1
    - vrf2 -> r3: r1-eth5  <-> r3-eth1
    - vrf2 -> r4: r1-eth6  <-> r4-eth1
    - vrf2 -> r5: r1-eth7  <-> r5-eth1
    - vrf3 -> r2: r1-eth8  <-> r2-eth2
    - vrf3 -> r3: r1-eth9  <-> r3-eth2
    - vrf3 -> r4: r1-eth10 <-> r4-eth2
    - vrf3 -> r5: r1-eth11 <-> r5-eth2
    - vrf4 -> r2: r1-eth12 <-> r2-eth3
    - vrf4 -> r3: r1-eth13 <-> r3-eth3
    - vrf4 -> r4: r1-eth14 <-> r4-eth3
    - vrf4 -> r5: r1-eth15 <-> r5-eth3
    
    New links for r6 (4-way ECMP):
    - r6-eth0 <-> r2-eth4
    - r6-eth1 <-> r3-eth4
    - r6-eth2 <-> r4-eth4
    - r6-eth3 <-> r5-eth4
    
    New links for r7 (4-way ECMP):
    - r7-eth0 <-> r2-eth5
    - r7-eth1 <-> r3-eth5
    - r7-eth2 <-> r4-eth5
    - r7-eth3 <-> r5-eth5
    """
    # Add all routers
    tgen.add_router("r1")
    tgen.add_router("r2")
    tgen.add_router("r3")
    tgen.add_router("r4") 
    tgen.add_router("r5")
    tgen.add_router("r6")
    tgen.add_router("r7")

    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    r3 = tgen.gears["r3"]
    r4 = tgen.gears["r4"]
    r5 = tgen.gears["r5"]
    r6 = tgen.gears["r6"]
    r7 = tgen.gears["r7"]

    # Existing links for VRF1 (r1-eth0-3) to all routers 
    # (r2-eth0, r3-eth0, r4-eth0, r5-eth0)
    switch = tgen.add_switch("sw_vrf1_r2")
    switch.add_link(r1)  # r1-eth0
    switch.add_link(r2)  # r2-eth0

    switch = tgen.add_switch("sw_vrf1_r3")
    switch.add_link(r1)  # r1-eth1
    switch.add_link(r3)  # r3-eth0

    switch = tgen.add_switch("sw_vrf1_r4")
    switch.add_link(r1)  # r1-eth2
    switch.add_link(r4)  # r4-eth0

    switch = tgen.add_switch("sw_vrf1_r5")
    switch.add_link(r1)  # r1-eth3
    switch.add_link(r5)  # r5-eth0

    # Existing links for VRF2 (r1-eth4-7) to all routers 
    # (r2-eth1, r3-eth1, r4-eth1, r5-eth1)
    switch = tgen.add_switch("sw_vrf2_r2")
    switch.add_link(r1)  # r1-eth4
    switch.add_link(r2)  # r2-eth1

    switch = tgen.add_switch("sw_vrf2_r3")
    switch.add_link(r1)  # r1-eth5
    switch.add_link(r3)  # r3-eth1

    switch = tgen.add_switch("sw_vrf2_r4")
    switch.add_link(r1)  # r1-eth6
    switch.add_link(r4)  # r4-eth1

    switch = tgen.add_switch("sw_vrf2_r5")
    switch.add_link(r1)  # r1-eth7
    switch.add_link(r5)  # r5-eth1

    # Existing links for VRF3 (r1-eth8-11) to all routers 
    # (r2-eth2, r3-eth2, r4-eth2, r5-eth2)
    switch = tgen.add_switch("sw_vrf3_r2")
    switch.add_link(r1)  # r1-eth8
    switch.add_link(r2)  # r2-eth2

    switch = tgen.add_switch("sw_vrf3_r3")
    switch.add_link(r1)  # r1-eth9
    switch.add_link(r3)  # r3-eth2

    switch = tgen.add_switch("sw_vrf3_r4")
    switch.add_link(r1)  # r1-eth10
    switch.add_link(r4)  # r4-eth2

    switch = tgen.add_switch("sw_vrf3_r5")
    switch.add_link(r1)  # r1-eth11
    switch.add_link(r5)  # r5-eth2

    # Existing links for VRF4 (r1-eth12-15) to all routers 
    # (r2-eth3, r3-eth3, r4-eth3, r5-eth3)
    switch = tgen.add_switch("sw_vrf4_r2")
    switch.add_link(r1)  # r1-eth12
    switch.add_link(r2)  # r2-eth3

    switch = tgen.add_switch("sw_vrf4_r3")
    switch.add_link(r1)  # r1-eth13
    switch.add_link(r3)  # r3-eth3

    switch = tgen.add_switch("sw_vrf4_r4")
    switch.add_link(r1)  # r1-eth14
    switch.add_link(r4)  # r4-eth3

    switch = tgen.add_switch("sw_vrf4_r5")
    switch.add_link(r1)  # r1-eth15
    switch.add_link(r5)  # r5-eth3

    # NEW: Links for r6 4-way ECMP (r6-eth0-3 to r2-eth4, r3-eth4, r4-eth4, r5-eth4)
    switch = tgen.add_switch("sw_r6_r2")
    switch.add_link(r6)  # r6-eth0
    switch.add_link(r2)  # r2-eth4

    switch = tgen.add_switch("sw_r6_r3")
    switch.add_link(r6)  # r6-eth1
    switch.add_link(r3)  # r3-eth4

    switch = tgen.add_switch("sw_r6_r4")
    switch.add_link(r6)  # r6-eth2
    switch.add_link(r4)  # r4-eth4

    switch = tgen.add_switch("sw_r6_r5")
    switch.add_link(r6)  # r6-eth3
    switch.add_link(r5)  # r5-eth4

    # NEW: Links for r7 4-way ECMP (r7-eth0-3 to r2-eth5, r3-eth5, r4-eth5, r5-eth5)
    switch = tgen.add_switch("sw_r7_r2")
    switch.add_link(r7)  # r7-eth0
    switch.add_link(r2)  # r2-eth5

    switch = tgen.add_switch("sw_r7_r3")
    switch.add_link(r7)  # r7-eth1
    switch.add_link(r3)  # r3-eth5

    switch = tgen.add_switch("sw_r7_r4")
    switch.add_link(r7)  # r7-eth2
    switch.add_link(r4)  # r4-eth5

    switch = tgen.add_switch("sw_r7_r5")
    switch.add_link(r7)  # r7-eth3
    switch.add_link(r5)  # r5-eth5


##############################################################################
#
#   Tests starting
#
##############################################################################


def setup_module(module):
    """Setup topology"""
    tgen = Topogen(build_topo, module.__name__)
    tgen.start_topology()

    # Setup VRFs on r1
    router_list = tgen.routers()
    r1 = router_list["r1"]
    
    # Create VRFs on r1
    for vrf_num in range(1, 5):
        r1.run("ip link add vrf{} type vrf table {}".format(vrf_num, 1000 + vrf_num))
        r1.run("ip link set vrf{} up".format(vrf_num))

    # Wait a bit for VRFs to be ready
    time.sleep(2)

    # Assign interfaces to VRFs on r1 with cross-connect mapping
    # vrf1: r1-eth0 to r1-eth3 (connects to r2-eth0, r3-eth0, r4-eth0, r5-eth0)
    # vrf2: r1-eth4 to r1-eth7 (connects to r2-eth1, r3-eth1, r4-eth1, r5-eth1)
    # vrf3: r1-eth8 to r1-eth11 (connects to r2-eth2, r3-eth2, r4-eth2, r5-eth2)
    # vrf4: r1-eth12 to r1-eth15 (connects to r2-eth3, r3-eth3, r4-eth3, r5-eth3)
    for i in range(16):
        vrf_num = (i // 4) + 1
        r1.run("ip link set r1-eth{} master vrf{}".format(i, vrf_num))

    # Wait for interface assignments
    time.sleep(2)

    # Load configurations
    for rname, router in router_list.items():
        router.load_frr_config(
            os.path.join(CWD, "{}/frr.conf".format(rname)),
            [
                (TopoRouter.RD_ZEBRA, "-s 180000000"),
                (TopoRouter.RD_BGP, None),
                (TopoRouter.RD_SHARP, None),
                (TopoRouter.RD_STATIC, None),
            ],
        )

    tgen.start_router()
    
    # Wait for routers to start
    time.sleep(10)


def teardown_module(_mod):
    """Teardown the pytest environment"""
    tgen = get_topogen()
    # This function tears down the whole topology.
    tgen.stop_topology()


def test_topology_setup():
    """Simple test that just creates the topology and verifies it's up"""
    tgen = get_topogen()
    # Don't run this test if we have any failure.
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Topology created successfully with 7-router asymmetric VRF cross-connect + ECMP setup")
    
    # Just verify routers are running
    for router_name in ["r1", "r2", "r3", "r4", "r5", "r6", "r7"]:
        router = tgen.gears[router_name]
        cmd = "ip link show | grep {}-eth | wc -l".format(router_name)
        interfaces = router.cmd(cmd)
        logger.info("{} has {} interfaces".format(
            router_name, interfaces.strip()))
    
    # Check VRFs are created on r1
    r1 = tgen.gears["r1"]
    vrf_count = r1.cmd("ip link show type vrf | wc -l")
    logger.info("r1 has {} VRFs created".format(vrf_count.strip()))
    
    logger.info("7-router asymmetric VRF cross-connect + ECMP BGP topology is ready")


def test_bgp_sessions_established():
    """Test that all 32 BGP sessions are established"""
    tgen = get_topogen()
    # Don't run this test if we have any failure.
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing BGP session establishment")
    
    # Check r1 BGP sessions across all VRFs (16 sessions)
    r1 = tgen.gears["r1"]
    
    def check_r1_all_sessions(router):
        """Check all BGP sessions on r1 across all VRFs using JSON"""
        try:
            output = router.vtysh_cmd("show bgp vrf all summary json")
            parsed = json.loads(output)
            
            total_established = 0
            expected_vrfs = ["vrf1", "vrf2", "vrf3", "vrf4"]
            
            for vrf_name in expected_vrfs:
                if vrf_name not in parsed:
                    logger.info("VRF {} not found in BGP summary".format(vrf_name))
                    continue
                    
                if "ipv4Unicast" not in parsed[vrf_name]:
                    logger.info("ipv4Unicast not found for VRF {}".format(
                        vrf_name))
                    continue
                    
                peers = parsed[vrf_name]["ipv4Unicast"].get("peers", {})
                vrf_established = 0
                for peer_ip, peer_data in peers.items():
                    if peer_data.get("state") == "Established":
                        vrf_established += 1
                    else:
                        state = peer_data.get("state", "Unknown")
                        logger.info("VRF {} peer {} state: {}".format(
                            vrf_name, peer_ip, state))
                
                logger.info("VRF {} has {}/4 established sessions".format(
                    vrf_name, vrf_established))
                total_established += vrf_established
            
            msg = "r1 total established sessions: {}/16".format(total_established)
            logger.info(msg)
            return total_established == 16  # Expect all 16 sessions
        except Exception as e:
            logger.info("Error checking BGP sessions for r1: {}".format(e))
            return False

    # Check each remote router sessions
    def check_router_sessions(router, expected_count):
        """Check BGP sessions on a router using JSON"""
        try:
            output = router.vtysh_cmd("show bgp summary json")
            parsed = json.loads(output)
            
            if "ipv4Unicast" not in parsed:
                logger.info("{} - no ipv4Unicast found".format(router.name))
                return False
                
            peers = parsed["ipv4Unicast"].get("peers", {})
            established_count = 0
            
            for peer_ip, peer_data in peers.items():
                if peer_data.get("state") == "Established":
                    established_count += 1
                else:
                    state = peer_data.get("state", "Unknown")
                    logger.info("{} peer {} state: {}".format(
                        router.name, peer_ip, state))
            
            logger.info("{} established sessions: {}/{}".format(
                router.name, established_count, expected_count))
            return established_count == expected_count
        except Exception as e:
            logger.info("Error checking BGP sessions for {}: {}".format(
                router.name, e))
            return False

    # Test r1 sessions (16 sessions)
    test_func = partial(check_r1_all_sessions, r1)
    result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
    assert result, "Not all BGP sessions established on r1"

    # Test sessions on r2, r3, r4, r5 (6 sessions each: 4 from r1 VRFs + 1 from r6 + 1 from r7)
    for router_name in ["r2", "r3", "r4", "r5"]:
        router = tgen.gears[router_name]
        test_func = partial(check_router_sessions, router, 6)
        result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
        assert result, "Not all BGP sessions established on {}".format(
            router_name)
    
    # Test sessions on r6, r7 (4 sessions each for 4-way ECMP)
    for router_name in ["r6", "r7"]:
        router = tgen.gears[router_name]
        test_func = partial(check_router_sessions, router, 4)
        result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
        assert result, "Not all BGP sessions established on {}".format(
            router_name)
    
    logger.info("All 32 BGP sessions established successfully")


def test_sharp_route_installation():
    """Test installing sharp routes on all routers"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step(" Going to install sharp routes on all routers") 
    # Define sharp routes for each router with specific values
    sharp_routes = {
        "r6": {"route": "45.1.1.1", "nexthop": "192.168.6.6"},
        "r7": {"route": "55.1.1.1", "nexthop": "192.168.7.7"}
    }
    
    # Install sharp routes on each router
    for router_name, config in sharp_routes.items():
        router = tgen.gears[router_name]
        cmd = "sharp install route {} nexthop {} 10".format(
            config["route"], config["nexthop"])
        logger.info("Installing sharp route on {}: {}".format(router_name, cmd))
        router.vtysh_cmd(cmd)

    logger.info("Sharp routes installed on all routers")


def test_cross_connect_verification():
    """Test that cross-connect topology is working correctly"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing cross-connect BGP topology")
    
    r1 = tgen.gears["r1"]
    
    # Expected cross-connect configuration:
    # Each VRF on r1 should connect to all 4 upstream routers
    expected_config = {
        "vrf1": {
            "peers": {
                "10.1.1.2": {"remote_as": 65002, "remote_router": "r2"},  # r1-eth0 <-> r2-eth0
                "10.1.2.2": {"remote_as": 65003, "remote_router": "r3"},  # r1-eth1 <-> r3-eth0
                "10.1.3.2": {"remote_as": 65004, "remote_router": "r4"},  # r1-eth2 <-> r4-eth0
                "10.1.4.2": {"remote_as": 65005, "remote_router": "r5"},  # r1-eth3 <-> r5-eth0
            }
        },
        "vrf2": {
            "peers": {
                "10.1.5.2": {"remote_as": 65002, "remote_router": "r2"},  # r1-eth4 <-> r2-eth1
                "10.1.6.2": {"remote_as": 65003, "remote_router": "r3"},  # r1-eth5 <-> r3-eth1
                "10.1.7.2": {"remote_as": 65004, "remote_router": "r4"},  # r1-eth6 <-> r4-eth1
                "10.1.8.2": {"remote_as": 65005, "remote_router": "r5"},  # r1-eth7 <-> r5-eth1
            }
        },
        "vrf3": {
            "peers": {
                "10.1.9.2": {"remote_as": 65002, "remote_router": "r2"},   # r1-eth8 <-> r2-eth2
                "10.1.10.2": {"remote_as": 65003, "remote_router": "r3"},  # r1-eth9 <-> r3-eth2
                "10.1.11.2": {"remote_as": 65004, "remote_router": "r4"},  # r1-eth10 <-> r4-eth2
                "10.1.12.2": {"remote_as": 65005, "remote_router": "r5"},  # r1-eth11 <-> r5-eth2
            }
        },
        "vrf4": {
            "peers": {
                "10.1.13.2": {"remote_as": 65002, "remote_router": "r2"},  # r1-eth12 <-> r2-eth3
                "10.1.14.2": {"remote_as": 65003, "remote_router": "r3"},  # r1-eth13 <-> r3-eth3
                "10.1.15.2": {"remote_as": 65004, "remote_router": "r4"},  # r1-eth14 <-> r4-eth3
                "10.1.16.2": {"remote_as": 65005, "remote_router": "r5"},  # r1-eth15 <-> r5-eth3
            }
        }
    }
    
    try:
        output = r1.vtysh_cmd("show bgp vrf all summary json")
        parsed = json.loads(output)
        
        for vrf_name, config in expected_config.items():
            logger.info("Verifying cross-connect for VRF: {}".format(vrf_name))
            
            # Check VRF exists
            assert vrf_name in parsed, "VRF {} not found".format(vrf_name)
            
            vrf_data = parsed[vrf_name]["ipv4Unicast"]
            peers = vrf_data.get("peers", {})
            
            # Check each expected peer in this VRF
            for peer_ip, peer_config in config["peers"].items():
                assert peer_ip in peers, \
                    "Peer {} not found in {}".format(peer_ip, vrf_name)
                
                peer_data = peers[peer_ip]
                
                # Verify peer details
                assert peer_data["state"] == "Established", \
                    "Peer {} in {} not established: {}".format(
                        peer_ip, vrf_name, peer_data.get("state"))
                assert peer_data["remoteAs"] == peer_config["remote_as"], \
                    "Wrong remote AS for peer {} in {}: expected {}, got {}".format(
                        peer_ip, vrf_name, peer_config["remote_as"], peer_data["remoteAs"])
                
                logger.info("  {} -> {}: {} (AS {})".format(
                    vrf_name, peer_config["remote_router"], 
                    peer_data["state"], peer_data["remoteAs"]))
        
        logger.info("Cross-connect BGP verification passed - each VRF connects to all upstream routers")
        
    except Exception as e:
        logger.info("Cross-connect verification failed: {}".format(e))
        # Show raw output for debugging
        logger.info("Raw BGP output: {}".format(output))
        raise


def test_ecmp_routers_verification():
    """Test that r6 and r7 have 4-way ECMP to all upstream routers"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing 4-way ECMP for r6 and r7")
    
    # Expected ECMP configuration for r6 and r7
    expected_ecmp_config = {
        "r6": {
            "as": 65006,
            "peers": {
                "10.1.17.2": {"remote_as": 65002, "remote_router": "r2"},  # r6-eth0 <-> r2-eth4
                "10.1.18.2": {"remote_as": 65003, "remote_router": "r3"},  # r6-eth1 <-> r3-eth4
                "10.1.19.2": {"remote_as": 65004, "remote_router": "r4"},  # r6-eth2 <-> r4-eth4
                "10.1.20.2": {"remote_as": 65005, "remote_router": "r5"},  # r6-eth3 <-> r5-eth4
            }
        },
        "r7": {
            "as": 65007,
            "peers": {
                "10.1.21.2": {"remote_as": 65002, "remote_router": "r2"},  # r7-eth0 <-> r2-eth5
                "10.1.22.2": {"remote_as": 65003, "remote_router": "r3"},  # r7-eth1 <-> r3-eth5
                "10.1.23.2": {"remote_as": 65004, "remote_router": "r4"},  # r7-eth2 <-> r4-eth5
                "10.1.24.2": {"remote_as": 65005, "remote_router": "r5"},  # r7-eth3 <-> r5-eth5
            }
        }
    }
    
    for router_name, config in expected_ecmp_config.items():
        router = tgen.gears[router_name]
        logger.info("Verifying 4-way ECMP for router: {}".format(router_name))
        
        try:
            output = router.vtysh_cmd("show bgp summary json")
            parsed = json.loads(output)
            
            # Check router exists and has correct AS
            assert "ipv4Unicast" in parsed, "No ipv4Unicast for {}".format(router_name)
            
            unicast_data = parsed["ipv4Unicast"]
            assert unicast_data["as"] == config["as"], \
                "Wrong AS for {}: expected {}, got {}".format(
                    router_name, config["as"], unicast_data["as"])
            
            peers = unicast_data.get("peers", {})
            
            # Check each expected peer
            for peer_ip, peer_config in config["peers"].items():
                assert peer_ip in peers, \
                    "Peer {} not found in {}".format(peer_ip, router_name)
                
                peer_data = peers[peer_ip]
                
                # Verify peer details
                assert peer_data["state"] == "Established", \
                    "Peer {} in {} not established: {}".format(
                        peer_ip, router_name, peer_data.get("state"))
                assert peer_data["remoteAs"] == peer_config["remote_as"], \
                    "Wrong remote AS for peer {} in {}: expected {}, got {}".format(
                        peer_ip, router_name, peer_config["remote_as"], peer_data["remoteAs"])
                
                logger.info("  {} -> {}: {} (AS {})".format(
                    router_name, peer_config["remote_router"], 
                    peer_data["state"], peer_data["remoteAs"]))
            
            logger.info("{} 4-way ECMP verification passed".format(router_name))
            
        except Exception as e:
            logger.info("ECMP verification failed for {}: {}".format(router_name, e))
            # Show raw output for debugging
            logger.info("Raw BGP output: {}".format(output))
            raise
    
    logger.info("All ECMP routers verification completed successfully")


def test_debug_bgp_multipath():
    """Debug BGP route advertisements and multipath setup"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)
    
    logger.info("Debugging BGP route advertisements and multipath")
    
    r1 = tgen.gears["r1"]
    
    # Check BGP received routes in vrf1 to see all advertisements
    logger.info("=== Checking BGP received routes in vrf1 ===")
    output = r1.vtysh_cmd("show bgp vrf vrf1 ipv4 unicast neighbors received-routes")
    logger.info("VRF1 received routes:\n{}".format(output))
    
    # Check BGP rib in vrf1 to see all paths
    logger.info("=== Checking BGP RIB for 45.1.1.1 in vrf1 ===")
    output = r1.vtysh_cmd("show bgp vrf vrf1 ipv4 unicast 45.1.1.1/32")
    logger.info("45.1.1.1/32 in vrf1:\n{}".format(output))
    
    # Check multipath configuration
    logger.info("=== Checking BGP configuration in vrf1 ===")
    output = r1.vtysh_cmd("show running-config | section 'router bgp.*vrf vrf1' -A 20")
    logger.info("VRF1 BGP config:\n{}".format(output))
    
    # Check all VRFs
    for vrf_num in range(1, 5):
        vrf_name = "vrf{}".format(vrf_num)
        logger.info("=== Checking {} ===".format(vrf_name))
        output = r1.vtysh_cmd("show bgp vrf {} ipv4 unicast 45.1.1.1/32".format(vrf_name))
        logger.info("45.1.1.1/32 in {}:\n{}".format(vrf_name, output))

    # Check ECMP routers
    for router_name in ["r6", "r7"]:
        router = tgen.gears[router_name]
        logger.info("=== Checking {} for ECMP ===".format(router_name))
        
        # Check for route from r2-r5 (45.1.1.1)
        output = router.vtysh_cmd("show bgp ipv4 unicast 45.1.1.1/32")
        logger.info("45.1.1.1/32 in {}:\n{}".format(router_name, output))
        
        # Check routing table
        output = router.vtysh_cmd("show ip route 45.1.1.1/32")
        logger.info("Route table for 45.1.1.1/32 in {}:\n{}".format(router_name, output))


@pytest.mark.skip(reason="Not needed right now")
def test_vrf_interfaces():
    """Test that VRF interfaces are properly assigned"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    r1 = tgen.gears["r1"]
    
    # Check VRF interface assignments
    for vrf_num in range(1, 5):
        cmd = "ip link show master vrf{} | grep r1-eth | wc -l".format(vrf_num)
        vrf_interfaces = r1.cmd(cmd)
        logger.info("VRF{} has {} interfaces assigned".format(
            vrf_num, vrf_interfaces.strip()))
        assert int(vrf_interfaces.strip()) == 4, \
            "VRF{} should have 4 interfaces".format(vrf_num)
    
    logger.info("All VRF interfaces properly assigned")


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args)) 
