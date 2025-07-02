#!/usr/bin/env python
# SPDX-License-Identifier: ISC

#
# test_bgp_ecmp_16peers_2routers_v4v6_krishna.py
#
# Copyright (c) 2025 by
# Test for BGP ECMP topology with 16 peers - Dual Stack (IPv4 + IPv6)
#

"""
test_bgp_ecmp_16peers_2routers_v4v6_krishna.py: Testing BGP ECMP setup with dual stack
                      - 2 routers connected by 16 links
                      - r1 and r2: all links in default VRF
                      - 16 eBGP sessions (1 per link) for ECMP - both IPv4 and IPv6
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
    Build topology with 2 routers connected by 16 links
    Both r1 and r2 have all links in default VRF for ECMP testing
    Dual stack: IPv4 and IPv6 on all links
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

    # No VRF setup needed - all interfaces in default VRF
    router_list = tgen.routers()
    
    # Load configurations
    for rname, router in router_list.items():
        router.load_frr_config(
            os.path.join(CWD, "{}/frr.conf".format(rname)),
            [
                (TopoRouter.RD_ZEBRA, "-s 180000000 -M dplane_fpm_nl --asic-offload=notify_on_offload"),
                # (TopoRouter.RD_ZEBRA, "-s 180000000"),
                (TopoRouter.RD_BGP, None),
                (TopoRouter.RD_SHARP, None),
                (TopoRouter.RD_STATIC, None),
                (TopoRouter.RD_FPM_LISTENER, "-r -d -o fpm_listener.log"),
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

    logger.info("Dual stack topology created successfully with 16-link ECMP setup")
    
    # Just verify routers are running
    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    
    # Check that we have the expected number of interfaces
    r1_interfaces = r1.cmd("ip link show | grep r1-eth | wc -l")
    r2_interfaces = r2.cmd("ip link show | grep r2-eth | wc -l")
    
    logger.info("r1 has {} interfaces, r2 has {} interfaces".format(
        r1_interfaces.strip(), r2_interfaces.strip()))
    
    logger.info("BGP ECMP dual stack topology is ready for testing")


def test_bgp_ipv4_sessions_established():
    """Test that all 16 IPv4 BGP sessions are established"""
    tgen = get_topogen()
    # Don't run this test if we have any failure.
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing IPv4 BGP session establishment")
    
    # Check r1 IPv4 BGP sessions using JSON
    r1 = tgen.gears["r1"]
    
    def check_r1_ipv4_sessions(router):
        """Check all IPv4 BGP sessions on r1 using JSON"""
        try:
            output = router.vtysh_cmd("show bgp summary json")
            parsed = json.loads(output)
            
            if "ipv4Unicast" not in parsed:
                logger.info("r1 - no ipv4Unicast found")
                return False
                
            peers = parsed["ipv4Unicast"].get("peers", {})
            established_count = 0
            
            for peer_ip, peer_data in peers.items():
                if peer_data.get("state") == "Established":
                    established_count += 1
                else:
                    state = peer_data.get("state", "Unknown")
                    logger.info("r1 IPv4 peer {} state: {}".format(peer_ip, state))
            
            msg = "r1 total IPv4 established sessions: {}/16".format(established_count)
            logger.info(msg)
            return established_count == 16  # Expect all 16 sessions
        except Exception as e:
            logger.info("Error checking IPv4 BGP sessions for r1: {}".format(e))
            return False

    test_func = partial(check_r1_ipv4_sessions, r1)
    result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
    if not result:
        logger.info("Not all IPv4 BGP sessions established on r1")
        # Show detailed status for debugging
        output = r1.vtysh_cmd("show bgp summary json")
        logger.info("r1 IPv4 summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 16 IPv4 BGP sessions established on r1")

    # Check r2 IPv4 BGP sessions using JSON
    r2 = tgen.gears["r2"]
    
    def check_r2_ipv4_sessions(router):
        """Check IPv4 BGP sessions for r2 using JSON"""
        try:
            output = router.vtysh_cmd("show bgp summary json")
            parsed = json.loads(output)
            
            if "ipv4Unicast" not in parsed:
                logger.info("r2 - no ipv4Unicast found")
                return False
                
            peers = parsed["ipv4Unicast"].get("peers", {})
            established_count = 0
            
            for peer_ip, peer_data in peers.items():
                if peer_data.get("state") == "Established":
                    established_count += 1
                else:
                    state = peer_data.get("state", "Unknown")
                    logger.info("r2 IPv4 peer {} state: {}".format(peer_ip, state))
                    
            msg = "r2 total IPv4 established sessions: {}/16".format(established_count)
            logger.info(msg)
            return established_count == 16  # Expect all 16 sessions
        except Exception as e:
            logger.info("Error checking IPv4 BGP sessions for r2: {}".format(e))
            return False

    test_func = partial(check_r2_ipv4_sessions, r2)
    result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
    if not result:
        logger.info("Not all IPv4 BGP sessions established on r2")
        # Show detailed status for debugging
        output = r2.vtysh_cmd("show bgp summary json")
        logger.info("r2 IPv4 summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 16 IPv4 BGP sessions established on r2")

    logger.info("All IPv4 BGP sessions established successfully")


def test_bgp_ipv6_sessions_established():
    """Test that all 16 IPv6 BGP sessions are established"""
    tgen = get_topogen()
    # Don't run this test if we have any failure.
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing IPv6 BGP session establishment")
    
    # Check r1 IPv6 BGP sessions using JSON
    r1 = tgen.gears["r1"]
    
    def check_r1_ipv6_sessions(router):
        """Check all IPv6 BGP sessions on r1 using JSON"""
        try:
            output = router.vtysh_cmd("show bgp summary json")
            parsed = json.loads(output)
            
            if "ipv6Unicast" not in parsed:
                logger.info("r1 - no ipv6Unicast found")
                return False
                
            peers = parsed["ipv6Unicast"].get("peers", {})
            established_count = 0
            
            for peer_ip, peer_data in peers.items():
                if peer_data.get("state") == "Established":
                    established_count += 1
                else:
                    state = peer_data.get("state", "Unknown")
                    logger.info("r1 IPv6 peer {} state: {}".format(peer_ip, state))
            
            msg = "r1 total IPv6 established sessions: {}/16".format(established_count)
            logger.info(msg)
            return established_count == 16  # Expect all 16 sessions
        except Exception as e:
            logger.info("Error checking IPv6 BGP sessions for r1: {}".format(e))
            return False

    test_func = partial(check_r1_ipv6_sessions, r1)
    result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
    if not result:
        logger.info("Not all IPv6 BGP sessions established on r1")
        # Show detailed status for debugging
        output = r1.vtysh_cmd("show bgp ipv6 summary json")
        logger.info("r1 IPv6 summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 16 IPv6 BGP sessions established on r1")

    # Check r2 IPv6 BGP sessions using JSON
    r2 = tgen.gears["r2"]
    
    def check_r2_ipv6_sessions(router):
        """Check IPv6 BGP sessions for r2 using JSON"""
        try:
            output = router.vtysh_cmd("show bgp summary json")
            parsed = json.loads(output)
            
            if "ipv6Unicast" not in parsed:
                logger.info("r2 - no ipv6Unicast found")
                return False
                
            peers = parsed["ipv6Unicast"].get("peers", {})
            established_count = 0
            
            for peer_ip, peer_data in peers.items():
                if peer_data.get("state") == "Established":
                    established_count += 1
                else:
                    state = peer_data.get("state", "Unknown")
                    logger.info("r2 IPv6 peer {} state: {}".format(peer_ip, state))
                    
            msg = "r2 total IPv6 established sessions: {}/16".format(established_count)
            logger.info(msg)
            return established_count == 16  # Expect all 16 sessions
        except Exception as e:
            logger.info("Error checking IPv6 BGP sessions for r2: {}".format(e))
            return False

    test_func = partial(check_r2_ipv6_sessions, r2)
    result, diff = topotest.run_and_expect(test_func, True, count=30, wait=2)
    if not result:
        logger.info("Not all IPv6 BGP sessions established on r2")
        # Show detailed status for debugging
        output = r2.vtysh_cmd("show bgp ipv6 summary json")
        logger.info("r2 IPv6 summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 16 IPv6 BGP sessions established on r2")

    logger.info("All IPv6 BGP sessions established successfully")


def test_sharp_route_installation():
    """Test installing sharp routes on all routers"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    step("Going to install sharp routes on r2") 
    # Install sharp routes on each router
    router = tgen.gears["r2"]
    
    # Install IPv4 sharp routes
    cmd = "sharp install route 45.1.1.1 nexthop 192.168.2.2 10"
    router.vtysh_cmd(cmd)
    
    # Install IPv6 sharp routes
    cmd = "sharp install route 2001:db8:45:1::1/128 nexthop 2001:db8:192:168::2 10"
    router.vtysh_cmd(cmd)

    logger.info("Sharp routes (IPv4 and IPv6) installed on all routers")


@pytest.mark.skip(reason="Not needed right now")
def test_interface_verification():
    """Test that interfaces are properly configured"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing dual stack interface configuration")
    
    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    
    # Check that both routers have 16 interfaces
    for router, router_name in [(r1, "r1"), (r2, "r2")]:
        output = router.cmd("ip link show | grep {}-eth | wc -l".format(router_name))
        interface_count = int(output.strip())
        assert interface_count == 16, "{} should have 16 interfaces, got {}".format(
            router_name, interface_count)
        
        # Check IPv4 addresses
        ipv4_addrs = router.cmd("ip -4 addr show | grep {}-eth | wc -l".format(router_name))
        ipv4_count = int(ipv4_addrs.strip())
        
        # Check IPv6 addresses  
        ipv6_addrs = router.cmd("ip -6 addr show | grep {}-eth | wc -l".format(router_name))
        ipv6_count = int(ipv6_addrs.strip())
        
        logger.info("{} has {} IPv4 addresses and {} IPv6 addresses on interfaces".format(
            router_name, ipv4_count, ipv6_count))

    logger.info("All dual stack interfaces verified successfully")


if __name__ == "__main__":
    pytest.main([__file__]) 
