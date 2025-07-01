#!/usr/bin/env python
# SPDX-License-Identifier: ISC

#
# test_bgp_asym_4vrf_4routers_krishna.py
#
# Copyright (c) 2025 by
# Test for BGP asymmetric VRF topology with 4 routers
#

"""
test_bgp_asym_4vrf_4routers_krishna.py: Testing BGP with asymmetric VRF setup
                      - 5 routers total (r1, r2, r3, r4, r5)
                      - r1: 4 VRFs with 4 links each (vrf1-4)
                      - r2: 4 links to r1's vrf1 (default VRF)
                      - r3: 4 links to r1's vrf2 (default VRF)  
                      - r4: 4 links to r1's vrf3 (default VRF)
                      - r5: 4 links to r1's vrf4 (default VRF)
                      - 16 eBGP sessions total (4 per router pair)
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
    Build topology with 5 routers:
    - r1 has 4 VRFs with 4 links each
    - r2 connects to r1's vrf1 (4 links)
    - r3 connects to r1's vrf2 (4 links)  
    - r4 connects to r1's vrf3 (4 links)
    - r5 connects to r1's vrf4 (4 links)
    """
    # Add all routers
    tgen.add_router("r1")
    tgen.add_router("r2")
    tgen.add_router("r3")
    tgen.add_router("r4") 
    tgen.add_router("r5")

    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    r3 = tgen.gears["r3"]
    r4 = tgen.gears["r4"]
    r5 = tgen.gears["r5"]

    # Create links between r1 and r2 (vrf1 to r2)
    for i in range(4):
        switch = tgen.add_switch("sw_r1_r2_{}".format(i))
        switch.add_link(r1)
        switch.add_link(r2)

    # Create links between r1 and r3 (vrf2 to r3)
    for i in range(4):
        switch = tgen.add_switch("sw_r1_r3_{}".format(i))
        switch.add_link(r1)
        switch.add_link(r3)

    # Create links between r1 and r4 (vrf3 to r4)
    for i in range(4):
        switch = tgen.add_switch("sw_r1_r4_{}".format(i))
        switch.add_link(r1)
        switch.add_link(r4)

    # Create links between r1 and r5 (vrf4 to r5)
    for i in range(4):
        switch = tgen.add_switch("sw_r1_r5_{}".format(i))
        switch.add_link(r1)
        switch.add_link(r5)


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

    # Assign interfaces to VRFs on r1
    # vrf1: r1-eth0 to r1-eth3 (interfaces 0-3, connects to r2)
    # vrf2: r1-eth4 to r1-eth7 (interfaces 4-7, connects to r3)
    # vrf3: r1-eth8 to r1-eth11 (interfaces 8-11, connects to r4)
    # vrf4: r1-eth12 to r1-eth15 (interfaces 12-15, connects to r5)
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

    logger.info("Topology created successfully with 5-router asymmetric VRF setup")
    
    # Just verify routers are running
    for router_name in ["r1", "r2", "r3", "r4", "r5"]:
        router = tgen.gears[router_name]
        cmd = "ip link show | grep {}-eth | wc -l".format(router_name)
        interfaces = router.cmd(cmd)
        logger.info("{} has {} interfaces".format(
            router_name, interfaces.strip()))
    
    # Check VRFs are created on r1
    r1 = tgen.gears["r1"]
    vrf_count = r1.cmd("ip link show type vrf | wc -l")
    logger.info("r1 has {} VRFs created".format(vrf_count.strip()))
    
    logger.info("5-router asymmetric VRF BGP topology is ready")


def test_bgp_sessions_established():
    """Test that all 16 BGP sessions are established"""
    tgen = get_topogen()
    # Don't run this test if we have any failure.
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing BGP session establishment")
    
    # Check r1 BGP sessions across all VRFs
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

    # Check each remote router has 4 established sessions
    def check_router_sessions(router, expected_count=4):
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

    # Test r1 sessions
    test_func = partial(check_r1_all_sessions, r1)
    result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
    assert result, "Not all BGP sessions established on r1"

    # Test sessions on r2, r3, r4, r5
    for router_name in ["r2", "r3", "r4", "r5"]:
        router = tgen.gears[router_name]
        test_func = partial(check_router_sessions, router, 4)
        result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
        assert result, "Not all BGP sessions established on {}".format(
            router_name)
    
    logger.info("All BGP sessions established successfully")


def test_sharp_route_installation():
    """Test installing sharp routes on all routers"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step(" Going to install sharp routes on all routers") 
    # Define sharp routes for each router with specific values
    sharp_routes = {
        "r2": {"route": "45.1.1.1", "nexthop": "192.168.2.2"},
        "r3": {"route": "55.1.1.1", "nexthop": "192.168.3.3"},
        "r4": {"route": "65.1.1.1", "nexthop": "192.168.4.4"},
        "r5": {"route": "75.1.1.1", "nexthop": "192.168.5.5"}
    }
    
    # Install sharp routes on each router
    for router_name, config in sharp_routes.items():
        router = tgen.gears[router_name]
        cmd = "sharp install route {} nexthop {} 10".format(
            config["route"], config["nexthop"])
        logger.info("Installing sharp route on {}: {}".format(router_name, cmd))
        router.vtysh_cmd(cmd)

    logger.info("Sharp routes installed on all routers")
    

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


@pytest.mark.skip(reason="Not needed right now")
def test_bgp_detailed_json_verification():
    """Test BGP sessions with detailed JSON verification"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Running detailed BGP JSON verification")
    
    r1 = tgen.gears["r1"]
    
    # Get BGP summary for all VRFs
    try:
        output = r1.vtysh_cmd("show bgp vrf all summary json")
        parsed = json.loads(output)
        
        expected_config = {
            "vrf1": {
                "as": 65002, 
                "peers": ["10.1.1.2", "10.1.2.2", "10.1.3.2", "10.1.4.2"]
            },
            "vrf2": {
                "as": 65003, 
                "peers": ["10.1.5.2", "10.1.6.2", "10.1.7.2", "10.1.8.2"]
            },
            "vrf3": {
                "as": 65004, 
                "peers": ["10.1.9.2", "10.1.10.2", "10.1.11.2", "10.1.12.2"]
            },
            "vrf4": {
                "as": 65005, 
                "peers": ["10.1.13.2", "10.1.14.2", "10.1.15.2", "10.1.16.2"]
            }
        }
        
        for vrf_name, config in expected_config.items():
            logger.info("Verifying VRF: {}".format(vrf_name))
            
            # Check VRF exists
            assert vrf_name in parsed, "VRF {} not found".format(vrf_name)
            
            vrf_data = parsed[vrf_name]["ipv4Unicast"]
            
            # Check router ID and AS
            assert vrf_data["routerId"] == "192.168.1.1", \
                "Wrong router ID for {}".format(vrf_name)
            assert vrf_data["as"] == 65001, \
                "Wrong local AS for {}".format(vrf_name)
            
            # Check each expected peer
            peers = vrf_data.get("peers", {})
            for peer_ip in config["peers"]:
                assert peer_ip in peers, \
                    "Peer {} not found in {}".format(peer_ip, vrf_name)
                
                peer_data = peers[peer_ip]
                
                # Verify peer details
                assert peer_data["state"] == "Established", \
                    "Peer {} in {} not established: {}".format(
                        peer_ip, vrf_name, peer_data.get("state"))
                assert peer_data["remoteAs"] == config["as"], \
                    "Wrong remote AS for peer {} in {}".format(peer_ip, vrf_name)
                assert peer_data["localAs"] == 65001, \
                    "Wrong local AS for peer {} in {}".format(peer_ip, vrf_name)
                
                logger.info("  Peer {}: {} (AS {})".format(
                    peer_ip, peer_data["state"], peer_data["remoteAs"]))
        
        logger.info("All BGP JSON verification passed")
        
    except Exception as e:
        logger.info("BGP JSON verification failed: {}".format(e))
        # Show raw output for debugging
        logger.info("Raw BGP output: {}".format(output))
        raise

    # Verify individual router BGP summaries
    expected_routers = {
        "r2": {"as": 65002, "peer_count": 4},
        "r3": {"as": 65003, "peer_count": 4},
        "r4": {"as": 65004, "peer_count": 4},
        "r5": {"as": 65005, "peer_count": 4}
    }
    
    for router_name, config in expected_routers.items():
        router = tgen.gears[router_name]
        try:
            output = router.vtysh_cmd("show bgp summary json")
            parsed = json.loads(output)
            
            if "ipv4Unicast" in parsed:
                unicast_data = parsed["ipv4Unicast"]
                
                # Check AS number
                assert unicast_data["as"] == config["as"], \
                    "Wrong AS for {}: expected {}, got {}".format(
                        router_name, config["as"], unicast_data["as"])
                
                # Check peer count
                peer_count = len(unicast_data.get("peers", {}))
                assert peer_count == config["peer_count"], \
                    "Wrong peer count for {}: expected {}, got {}".format(
                        router_name, config["peer_count"], peer_count)
                
                # Check all peers are established
                for peer_ip, peer_data in unicast_data["peers"].items():
                    assert peer_data["state"] == "Established", \
                        "{} peer {} not established: {}".format(
                            router_name, peer_ip, peer_data["state"])
                
                logger.info("{}: AS {} with {} established peers".format(
                    router_name, unicast_data["as"], peer_count))
            else:
                raise AssertionError("No ipv4Unicast data for {}".format(router_name))
                
        except Exception as e:
            logger.info("JSON verification failed for {}: {}".format(router_name, e))
            raise


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args)) 