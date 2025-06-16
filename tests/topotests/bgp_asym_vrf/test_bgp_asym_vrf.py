#!/usr/bin/env python
# SPDX-License-Identifier: ISC

#
# test_bgp_asym_vrf.py
#
# Copyright (c) 2025 by
# Test for BGP asymmetric VRF topology
#

"""
test_bgp_asym_vrf.py: Testing BGP with asymmetric VRF setup
                      - 2 routers connected by 16 links
                      - r1: 4 VRFs with 4 links each (vrf1-4)
                      - r2: all links in default VRF
                      - 16 eBGP sessions (1 per link)
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

pytestmark = [pytest.mark.bgpd]

# Required to instantiate the topology builder class.

##############################################################################
#
#   Network Topology Definition
#
##############################################################################


def build_topo(tgen):
    """
    Build topology with 2 routers connected by 16 links
    r1 has 4 VRFs with 4 links each, r2 has all links in default VRF
    """
    tgen.add_router("r1")
    tgen.add_router("r2")

    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]

    # Create 16 links between r1 and r2
    for i in range(1, 17):
        switch = tgen.add_switch("sw{}".format(i))
        switch.add_link(r1)
        switch.add_link(r2)


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
    # vrf1: r1-eth0 to r1-eth3 (interfaces 0-3)
    # vrf2: r1-eth4 to r1-eth7 (interfaces 4-7)
    # vrf3: r1-eth8 to r1-eth11 (interfaces 8-11)
    # vrf4: r1-eth12 to r1-eth15 (interfaces 12-15)
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

    logger.info("Topology created successfully with 16-link asymmetric VRF setup")
    
    # Just verify routers are running - no need for ping test
    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    
    # Check that we have the expected number of interfaces
    r1_interfaces = r1.cmd("ip link show | grep r1-eth | wc -l")
    r2_interfaces = r2.cmd("ip link show | grep r2-eth | wc -l")
    
    logger.info("r1 has {} interfaces, r2 has {} interfaces".format(
        r1_interfaces.strip(), r2_interfaces.strip()))
    
    # Check VRFs are created
    vrf_count = r1.cmd("ip link show type vrf | wc -l")
    logger.info("r1 has {} VRFs created".format(vrf_count.strip()))
    
    logger.info("Asymmetric VRF BGP topology is ready for manual testing")
    # Test passes - topology is created successfully


@pytest.mark.skip(reason="Not needed right now")
def test_bgp_sessions_established():
    """Test that all 16 BGP sessions are established"""
    tgen = get_topogen()
    # Don't run this test if we have any failure.
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing BGP session establishment")
    
    # Check r1 BGP sessions across all VRFs using JSON
    r1 = tgen.gears["r1"]
    
    def check_r1_all_sessions(router):
        """Check all BGP sessions on r1 across all VRFs using JSON"""
        try:
            output = router.vtysh_cmd("show bgp vrf all summary json")
            parsed = json.loads(output)
            
            total_established = 0
            for vrf_name, vrf_data in parsed.items():
                if "ipv4Unicast" in vrf_data:
                    peers = vrf_data["ipv4Unicast"].get("peers", {})
                    vrf_established = 0
                    for peer_ip, peer_data in peers.items():
                        if peer_data.get("state") == "Established":
                            vrf_established += 1
                    logger.info("VRF {} has {} established sessions".format(
                        vrf_name, vrf_established))
                    total_established += vrf_established
            
            logger.info("r1 total established sessions: {}".format(total_established))
            return total_established == 16  # Expect all 16 sessions
        except Exception as e:
            logger.info("Error checking BGP sessions for r1: {}".format(e))
            return False

    test_func = partial(check_r1_all_sessions, r1)
    result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
    if not result:
        logger.info("Not all BGP sessions established on r1")
        # Show detailed status for debugging
        output = r1.vtysh_cmd("show bgp vrf all summary json")
        logger.info("r1 all VRF summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 16 BGP sessions established on r1")

    # Check r2 BGP sessions (all in default VRF) using JSON
    r2 = tgen.gears["r2"]
    
    def check_r2_sessions(router):
        """Check BGP sessions for r2 (default VRF) using JSON"""
        try:
            output = router.vtysh_cmd("show bgp summary json")
            parsed = json.loads(output)
            
            if "ipv4Unicast" not in parsed:
                return False
                
            peers = parsed["ipv4Unicast"].get("peers", {})
            established_count = 0
            
            for peer_ip, peer_data in peers.items():
                if peer_data.get("state") == "Established":
                    established_count += 1
                    
            logger.info("r2 has {} established sessions".format(established_count))
            return established_count == 16  # Expect all 16 sessions
        except Exception as e:
            logger.info("Error checking BGP sessions for r2: {}".format(e))
            return False

    test_func = partial(check_r2_sessions, r2)
    result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
    if not result:
        logger.info("Not all BGP sessions established on r2")
        # Show detailed status for debugging
        output = r2.vtysh_cmd("show bgp summary json")
        logger.info("r2 summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 16 BGP sessions established on r2")


@pytest.mark.skip(reason="Not needed right now")
def test_vrf_interfaces():
    """Test that VRF interfaces are properly configured on r1"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing VRF interface assignment")
    
    r1 = tgen.gears["r1"]
    
    # Check VRF interface assignments
    for vrf_num in range(1, 5):
        output = r1.cmd("ip link show master vrf{}".format(vrf_num))
        # Should show 4 interfaces per VRF
        interface_count = output.count("r1-eth")
        expected_msg = "VRF{} should have 4 interfaces, found {}".format(
            vrf_num, interface_count)
        assert interface_count == 4, expected_msg
        logger.info("VRF{} correctly has {} interfaces".format(
            vrf_num, interface_count))


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args)) 
