# BGP Asymmetric VRF Topotest

## Overview

This topotest validates BGP functionality in an asymmetric VRF scenario where:
- Router 1 (r1) has 16 interfaces segregated into 4 VRFs (vrf1, vrf2, vrf3, vrf4) with 4 interfaces each
- Router 2 (r2) has all 16 interfaces in the default VRF
- 16 eBGP sessions are established (1 per link)
- Sharp daemon is enabled on both routers
- Connected routes and sharp routes are redistributed

## Topology

```
r1 (4 VRFs) --- 16 links --- r2 (default VRF)

VRF assignment on r1:
- vrf1: r1-eth0 to r1-eth3   (connects to r2-eth0 to r2-eth3)
- vrf2: r1-eth4 to r1-eth7   (connects to r2-eth4 to r2-eth7)
- vrf3: r1-eth8 to r1-eth11  (connects to r2-eth8 to r2-eth11)
- vrf4: r1-eth12 to r1-eth15 (connects to r2-eth12 to r2-eth15)
```

## Network Addressing

- Links use /30 subnets: 10.1.1.0/30, 10.1.2.0/30, ..., 10.1.16.0/30
- r1 interfaces: .1 addresses (10.1.X.1/30)
- r2 interfaces: .2 addresses (10.1.X.2/30)
- r1 loopback: 192.168.1.1/32
- r2 loopback: 192.168.2.2/32

## BGP Configuration

- r1: AS 65001 (separate BGP instance per VRF)
- r2: AS 65002 (single BGP instance in default VRF)
- eBGP sessions between r1 and r2
- Redistribution of connected and sharp routes

## Test Coverage

The test validates:
1. BGP session establishment (16 sessions total)
2. Connected route redistribution
3. Sharp daemon functionality
4. VRF interface assignment on r1

## Running the Test

```bash
cd tests/topotests/bgp_asym_vrf
sudo python3 test_bgp_asym_vrf.py
```

## Files

- `test_bgp_asym_vrf.py` - Main test script
- `r1/frr.conf` - FRR configuration for router 1
- `r2/frr.conf` - FRR configuration for router 2
- `README.md` - This documentation 