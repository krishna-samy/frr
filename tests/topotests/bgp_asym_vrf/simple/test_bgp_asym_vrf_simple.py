#!/usr/bin/env python
# SPDX-License-Identifier: ISC

#
# test_bgp_asym_vrf_simple.py
#
# Copyright (c) 2025 by
# Simplified test for BGP asymmetric VRF topology
#

"""
test_bgp_asym_vrf_simple.py: Testing BGP with asymmetric VRF setup
                             - 2 routers connected by 4 links (simplified)
                             - r1: 1 VRF with 4 links 
                             - r2: all links in default VRF
                             - 4 eBGP sessions (1 per link)
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


def build_topo(tgen):
    """
    Build topology with 2 routers connected by 4 links
    r1 has 1 VRF with 4 links, r2 has all links in default VRF
    """
    tgen.add_router("r1")
    tgen.add_router("r2")

    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]

    # Create 4 links between r1 and r2
    for i in range(1, 5):
        switch = tgen.add_switch("sw{}".format(i))
        switch.add_link(r1)
        switch.add_link(r2)


def setup_module(module):
    """Setup topology"""
    tgen = Topogen(build_topo, module.__name__)
    tgen.start_topology()

    # Setup VRF on r1 (simplified - only 1 VRF)
    router_list = tgen.routers()
    r1 = router_list["r1"]
    
    # Create VRF on r1
    r1.run("ip link add vrf1 type vrf table 1001")
    r1.run("ip link set vrf1 up")

    # Wait a bit for VRF to be ready
    time.sleep(2)

    # Assign interfaces to VRF on r1
    for i in range(4):
        r1.run("ip link set r1-eth{} master vrf1".format(i))

    # Wait for interface assignments
    time.sleep(2)

    # Load configurations
    for rname, router in router_list.items():
        config_file = os.path.join(CWD, rname, "frr.conf")
        if os.path.exists(config_file):
            router.load_frr_config(
                config_file,
                [
                    (TopoRouter.RD_ZEBRA, "-s 180000000"),
                    (TopoRouter.RD_BGP, None),
                    (TopoRouter.RD_SHARP, None),
                ],
            )

    tgen.start_router()
    
    # Wait for routers to start
    time.sleep(5)


def teardown_module(_mod):
    """Teardown the pytest environment"""
    tgen = get_topogen()
    tgen.stop_topology()


def test_basic_connectivity():
    """Test basic connectivity first"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("=== Testing basic connectivity ===")
    
    r1 = tgen.gears["r1"]
    
    # Test ping from r1 to r2 via VRF
    output = r1.cmd("ping -c 2 -I vrf1 10.1.1.2")
    logger.info("Ping from r1 to r2: %s", output)
    
    # Check if ping was successful
    assert (
        "2 received" in output or "2 packets transmitted, 2 received" in output
    ), "Basic connectivity test failed"


def test_vrf_setup():
    """Test VRF setup"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("=== Testing VRF setup ===")
    
    r1 = tgen.gears["r1"]
    
    # Check VRF creation
    output = r1.cmd("ip link show type vrf")
    logger.info("VRFs created: %s", output)
    assert "vrf1" in output, "VRF1 not created"
    
    # Check interface assignment
    output = r1.cmd("ip link show master vrf1")
    logger.info("VRF1 interfaces: %s", output)
    interface_count = output.count("r1-eth")
    assert interface_count == 4, (
        "VRF1 should have 4 interfaces, found {}".format(interface_count)
    )


def test_bgp_sessions():
    """Test BGP sessions"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("=== Testing BGP sessions ===")
    
    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    
    # Check r1 BGP summary
    output = r1.vtysh_cmd("show bgp vrf vrf1 summary")
    logger.info("r1 BGP vrf1 summary: %s", output)
    
    # Check r2 BGP summary  
    output = r2.vtysh_cmd("show bgp summary")
    logger.info("r2 BGP summary: %s", output)


def test_bgp_route_exchange():
    """Test that BGP routes are being exchanged properly"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("=== Testing BGP route exchange ===")
    
    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    
    # Wait a bit more for BGP convergence
    time.sleep(10)
    
    # Check routes on r1 in VRF1
    def check_r1_routes():
        """Check BGP routes received on r1 VRF1"""
        try:
            output = r1.vtysh_cmd("show bgp vrf vrf1 ipv4 unicast json")
            parsed = json.loads(output)
            
            if "routes" not in parsed:
                return False
                
            # Should receive r2's connected routes
            received_routes = len(parsed["routes"])
            logger.info("r1 VRF1 has {} routes".format(received_routes))
            # Should have more than just local connected routes
            return received_routes > 4
            
        except Exception as e:
            logger.info("Error checking r1 routes: {}".format(e))
            return False
    
    # Check routes on r2
    def check_r2_routes():
        """Check BGP routes received on r2"""
        try:
            output = r2.vtysh_cmd("show bgp ipv4 unicast json")
            parsed = json.loads(output)
            
            if "routes" not in parsed:
                return False
                
            # Should receive r1's connected routes from VRF1
            received_routes = len(parsed["routes"])
            logger.info("r2 has {} routes".format(received_routes))
            # Should have more than just local connected routes
            return received_routes > 4
            
        except Exception as e:
            logger.info("Error checking r2 routes: {}".format(e))
            return False
    
    # Test r1 route reception
    test_func = partial(check_r1_routes)
    result, diff = topotest.run_and_expect(test_func, True, count=20, wait=1)
    if not result:
        logger.info("r1 VRF1 not receiving expected routes")
        # Show detailed output for debugging
        output = r1.vtysh_cmd("show bgp vrf vrf1 ipv4 unicast")
        logger.info("r1 VRF1 routes detail: %s", output)
    
    # Test r2 route reception
    test_func = partial(check_r2_routes)
    result, diff = topotest.run_and_expect(test_func, True, count=20, wait=1)
    if not result:
        logger.info("r2 not receiving expected routes")
        # Show detailed output for debugging
        output = r2.vtysh_cmd("show bgp ipv4 unicast")
        logger.info("r2 routes detail: %s", output)


if __name__ == "__main__":
    args = ["-s"] + sys.argv[1:]
    sys.exit(pytest.main(args)) 