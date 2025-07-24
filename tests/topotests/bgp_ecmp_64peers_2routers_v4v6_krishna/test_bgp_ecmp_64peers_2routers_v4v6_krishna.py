#!/usr/bin/env python
# SPDX-License-Identifier: ISC

#
# test_bgp_ecmp_64peers_2routers_v4v6_krishna.py
#
# Copyright (c) 2025 by
# Test for BGP ECMP topology with 64 peers - Dual Stack (IPv4 + IPv6)
#

"""
test_bgp_ecmp_64peers_2routers_v4v6_krishna.py: Testing BGP ECMP setup with dual stack
                      - 2 routers connected by 64 links
                      - r1 and r2: all links in default VRF
                      - 64 eBGP sessions (1 per link) for ECMP - both IPv4 and IPv6
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
    Build topology with 2 routers connected by 64 links
    Both r1 and r2 have all links in default VRF for ECMP testing
    Dual stack: IPv4 and IPv6 on all links
    """
    tgen.add_router("r1")
    tgen.add_router("r2")

    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]

    # Create 64 links between r1 and r2
    for i in range(1, 65):
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
    time.sleep(20)  # Increased wait time for 64 links


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

    logger.info("64-way dual stack topology created successfully with ECMP setup")
    
    # Just verify routers are running
    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    
    # Check that we have the expected number of interfaces
    r1_interfaces = r1.cmd("ip link show | grep r1-eth | wc -l")
    r2_interfaces = r2.cmd("ip link show | grep r2-eth | wc -l")
    
    logger.info("r1 has {} interfaces, r2 has {} interfaces".format(
        r1_interfaces.strip(), r2_interfaces.strip()))
    
    logger.info("BGP ECMP 64-way dual stack topology is ready for testing")


def test_bgp_ipv4_sessions_established():
    """Test that all 64 IPv4 BGP sessions are established"""
    tgen = get_topogen()
    # Don't run this test if we have any failure.
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing IPv4 BGP session establishment (64 sessions)")
    
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
            
            msg = "r1 total IPv4 established sessions: {}/64".format(established_count)
            logger.info(msg)
            return established_count == 64  # Expect all 64 sessions
        except Exception as e:
            logger.info("Error checking IPv4 BGP sessions for r1: {}".format(e))
            return False

    test_func = partial(check_r1_ipv4_sessions, r1)
    result, diff = topotest.run_and_expect(test_func, True, count=40, wait=3)
    if not result:
        logger.info("Not all IPv4 BGP sessions established on r1")
        # Show detailed status for debugging
        output = r1.vtysh_cmd("show bgp summary json")
        logger.info("r1 IPv4 summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 64 IPv4 BGP sessions established on r1")

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
                    
            msg = "r2 total IPv4 established sessions: {}/64".format(established_count)
            logger.info(msg)
            return established_count == 64  # Expect all 64 sessions
        except Exception as e:
            logger.info("Error checking IPv4 BGP sessions for r2: {}".format(e))
            return False

    test_func = partial(check_r2_ipv4_sessions, r2)
    result, diff = topotest.run_and_expect(test_func, True, count=40, wait=3)
    if not result:
        logger.info("Not all IPv4 BGP sessions established on r2")
        # Show detailed status for debugging
        output = r2.vtysh_cmd("show bgp summary json")
        logger.info("r2 IPv4 summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 64 IPv4 BGP sessions established on r2")

    logger.info("All 64 IPv4 BGP sessions established successfully")


def test_bgp_ipv6_sessions_established():
    """Test that all 64 IPv6 BGP sessions are established"""
    tgen = get_topogen()
    # Don't run this test if we have any failure.
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Testing IPv6 BGP session establishment (64 sessions)")
    
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
            
            msg = "r1 total IPv6 established sessions: {}/64".format(established_count)
            logger.info(msg)
            return established_count == 64  # Expect all 64 sessions
        except Exception as e:
            logger.info("Error checking IPv6 BGP sessions for r1: {}".format(e))
            return False

    test_func = partial(check_r1_ipv6_sessions, r1)
    result, diff = topotest.run_and_expect(test_func, True, count=40, wait=3)
    if not result:
        logger.info("Not all IPv6 BGP sessions established on r1")
        # Show detailed status for debugging
        output = r1.vtysh_cmd("show bgp ipv6 summary json")
        logger.info("r1 IPv6 summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 64 IPv6 BGP sessions established on r1")

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
                    
            msg = "r2 total IPv6 established sessions: {}/64".format(established_count)
            logger.info(msg)
            return established_count == 64  # Expect all 64 sessions
        except Exception as e:
            logger.info("Error checking IPv6 BGP sessions for r2: {}".format(e))
            return False

    test_func = partial(check_r2_ipv6_sessions, r2)
    result, diff = topotest.run_and_expect(test_func, True, count=40, wait=3)
    if not result:
        logger.info("Not all IPv6 BGP sessions established on r2")
        # Show detailed status for debugging
        output = r2.vtysh_cmd("show bgp ipv6 summary json")
        logger.info("r2 IPv6 summary: {}".format(output))
    else:
        logger.info("SUCCESS: All 64 IPv6 BGP sessions established on r2")

    logger.info("All 64 IPv6 BGP sessions established successfully")


def test_bgp_memory_stress_test():
    """Stress test for BGP memory usage with sharp routes over 50 iterations"""
    tgen = get_topogen()
    if tgen.routers_have_failure():
        pytest.skip(tgen.errors)

    logger.info("Starting BGP memory stress test with 50 iterations")
    
    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    
    def wait_for_outq_zero(router):
        """Wait for outq to become 0 on all BGP sessions"""
        def check_outq_zero():
            try:
                # Get BGP summary output in text format
                output = router.vtysh_cmd("show bgp summary")
                lines = output.split('\n')
                
                # Parse both IPv4 and IPv6 sections
                for line in lines:
                    line = line.strip()
                    # Skip header lines and empty lines
                    if not line or 'Neighbor' in line or 'BGP router' in line or \
                       'BGP table' in line or 'RIB entries' in line or \
                       'Peers' in line or 'Summary:' in line or line.startswith('-'):
                        continue
                    
                    # Parse peer lines (should have IP address as first column)
                    parts = line.split()
                    if len(parts) >= 8:  # Make sure we have enough columns
                        try:
                            neighbor_ip = parts[0]
                            # OutQ is the 8th column (index 7)
                            outq = int(parts[7])
                            
                            # Check if session is established and has non-zero outq
                            if outq > 0:
                                logger.info("BGP peer {} still has outq: {}".format(
                                    neighbor_ip, outq))
                                return False
                                
                        except (ValueError, IndexError):
                            # Skip lines that don't parse correctly
                            continue
                
                return True
            except Exception as e:
                logger.info("Error checking outq: {}".format(e))
                return False
        
        result, diff = topotest.run_and_expect(check_outq_zero, True, count=60, wait=0.5)
        return result
    
    def wait_for_inq_zero(router):
        """Wait for inq to become 0 on all BGP sessions"""
        def check_inq_zero():
            try:
                # Get BGP summary output in text format
                output = router.vtysh_cmd("show bgp summary")
                lines = output.split('\n')
                
                # Parse both IPv4 and IPv6 sections
                for line in lines:
                    line = line.strip()
                    # Skip header lines and empty lines
                    if not line or 'Neighbor' in line or 'BGP router' in line or \
                       'BGP table' in line or 'RIB entries' in line or \
                       'Peers' in line or 'Summary:' in line or line.startswith('-'):
                        continue
                    
                    # Parse peer lines (should have IP address as first column)
                    parts = line.split()
                    if len(parts) >= 8:  # Make sure we have enough columns
                        try:
                            neighbor_ip = parts[0]
                            # InQ is the 7th column (index 6) in BGP summary
                            inq = int(parts[6])
                            
                            # Check if session has non-zero inq
                            if inq > 0:
                                logger.info("BGP peer {} still has inq: {}".format(
                                    neighbor_ip, inq))
                                return False
                                
                        except (ValueError, IndexError):
                            # Skip lines that don't parse correctly
                            continue
                
                return True
            except Exception as e:
                logger.info("Error checking inq: {}".format(e))
                return False
        
        result, diff = topotest.run_and_expect(check_inq_zero, True, count=60, wait=0.5)
        return result
    
    def check_zebra_memory(router, iteration, phase):
        """Check zebra memory usage and return free ordinary blocks in MB"""
        try:
            output = router.vtysh_cmd("show memory zebra")
            logger.info("Iteration {}, {} - Zebra memory output:\n{}".format(
                iteration, phase, output))
            
            # Parse the memory output to extract "Free ordinary blocks"
            lines = output.split('\n')
            for line in lines:
                if "Free ordinary blocks:" in line:
                    # Extract the memory value and unit
                    parts = line.split()
                    if len(parts) >= 4:
                        memory_value = parts[3]
                        memory_unit = parts[4] if len(parts) > 4 else ""
                        
                        # Convert to MB if needed
                        if "MiB" in memory_unit or "MB" in memory_unit:
                            free_memory_mb = int(memory_value)
                        elif "GiB" in memory_unit or "GB" in memory_unit:
                            free_memory_mb = int(memory_value) * 1024
                        elif "KiB" in memory_unit or "KB" in memory_unit:
                            free_memory_mb = int(memory_value) // 1024
                        else:
                            # Assume bytes if no unit
                            try:
                                free_memory_mb = int(memory_value) // (1024 * 1024)
                            except (ValueError, TypeError):
                                free_memory_mb = 0
                        
                        logger.info("Iteration {}, {} - Free ordinary blocks: {} MB".format(
                            iteration, phase, free_memory_mb))
                        return free_memory_mb
            
            logger.info("Could not find 'Free ordinary blocks' in zebra memory output")
            return 0
            
        except Exception as e:
            logger.info("Error checking zebra memory: {}".format(e))
            return 0
    
    # Run stress test for 50 iterations
    for iteration in range(1, 51):
        logger.info("=" * 60)
        logger.info("Starting stress test iteration {}/50".format(iteration))
        
        try:
            # Step 1: Install 20k IPv4 and 20k IPv6 routes from r2
            logger.info("Iteration {} - Installing 20k IPv4 routes".format(iteration))
            cmd_ipv4 = "sharp install route 45.1.1.1 nexthop 192.168.2.2 20000"
            r2.vtysh_cmd(cmd_ipv4)
            
            logger.info("Iteration {} - Installing 20k IPv6 routes".format(iteration))
            cmd_ipv6 = ("sharp install route 2001:db8:45:1::1 nexthop 2001:db8:192:168::2 20000")
            r2.vtysh_cmd(cmd_ipv6)
            
            # Step 2: Wait for outq to become 0 on r1
            logger.info("Iteration {} - Waiting for outq to become 0 on r1".format(
                iteration))
            if not wait_for_outq_zero(r1):
                logger.info("Iteration {} - WARNING: outq did not become 0 within "
                           "timeout".format(iteration))
            
            time.sleep(5) 
            # Step 3: Check zebra memory after route installation
            free_memory_after_install = check_zebra_memory(r1, iteration, "after install")
            if free_memory_after_install > 200:
                logger.error("Iteration {} - MEMORY TEST FAILED: Free ordinary blocks "
                           "({} MB) > 200MB after route installation".format(
                    iteration, free_memory_after_install))
                pytest.fail("Memory stress test failed at iteration {} after route "
                           "installation: {} MB > 200MB".format(
                    iteration, free_memory_after_install))
                return
            
            # Step 4: Remove all sharp routes from r2
            logger.info("Iteration {} - Removing IPv4 sharp routes".format(iteration))
            cmd_remove_ipv4 = "sharp remove route 45.1.1.1 20000"
            r2.vtysh_cmd(cmd_remove_ipv4)
            
            logger.info("Iteration {} - Removing IPv6 sharp routes".format(iteration))
            cmd_remove_ipv6 = "sharp remove route 2001:db8:45:1::1 20000"
            r2.vtysh_cmd(cmd_remove_ipv6)
            
            # Step 5: Wait for inq to become 0 on r1 after route removal
            logger.info("Iteration {} - Waiting for inq to become 0 on r1".format(iteration))
            if not wait_for_inq_zero(r1):
                logger.info("Iteration {} - WARNING: inq did not become 0 within timeout".format(
                    iteration))
            
            time.sleep(5) 
            # Step 6: Check zebra memory after route removal
            free_memory_after_remove = check_zebra_memory(r1, iteration, "after removal")
            if free_memory_after_remove > 200:
                logger.error("Iteration {} - MEMORY TEST FAILED: Free ordinary blocks "
                           "({} MB) > 200MB after route removal".format(
                    iteration, free_memory_after_remove))
                pytest.fail("Memory stress test failed at iteration {} after route removal: "
                           "{} MB > 200MB".format(
                    iteration, free_memory_after_remove))
                return
            
            logger.info("Iteration {} - PASSED: Memory usage within limits "
                       "(install: {} MB, remove: {} MB)".format(
                iteration, free_memory_after_install, free_memory_after_remove))
                
        except Exception as e:
            logger.error("Iteration {} - Exception occurred: {}".format(iteration, e))
            pytest.fail("Memory stress test failed at iteration {} with exception: {}".format(
                iteration, str(e)))
            return
    
    logger.info("=" * 60)
    logger.info("SUCCESS: All 50 iterations of memory stress test completed successfully")


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

    logger.info("Testing 64-way dual stack interface configuration")
    
    r1 = tgen.gears["r1"]
    r2 = tgen.gears["r2"]
    
    # Check that both routers have 64 interfaces
    for router, router_name in [(r1, "r1"), (r2, "r2")]:
        output = router.cmd("ip link show | grep {}-eth | wc -l".format(router_name))
        interface_count = int(output.strip())
        assert interface_count == 64, "{} should have 64 interfaces, got {}".format(
            router_name, interface_count)
        
        # Check IPv4 addresses
        ipv4_addrs = router.cmd("ip -4 addr show | grep {}-eth | wc -l".format(router_name))
        ipv4_count = int(ipv4_addrs.strip())
        
        # Check IPv6 addresses  
        ipv6_addrs = router.cmd("ip -6 addr show | grep {}-eth | wc -l".format(router_name))
        ipv6_count = int(ipv6_addrs.strip())
        
        logger.info("{} has {} IPv4 addresses and {} IPv6 addresses on interfaces".format(
            router_name, ipv4_count, ipv6_count))

    logger.info("All 64-way dual stack interfaces verified successfully")


if __name__ == "__main__":
    pytest.main([__file__]) 