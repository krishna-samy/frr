# BGP ECMP Test with 16 Peers - Dual Stack (bgp_ecmp_16peers_2routers_v4v6_krishna)

## Overview

This test verifies BGP ECMP (Equal Cost Multi-Path) functionality with 16 parallel links between two routers in a dual stack environment (IPv4 + IPv6).

## Topology

```
r1 (AS 65001) ===== 16 links ===== r2 (AS 65002)
                    Dual Stack
                  (IPv4 + IPv6)
```

## Router Configuration

### r1 (AS 65001)
- **Default VRF only**
- **16 interfaces**: r1-eth0 to r1-eth15
- **32 eBGP sessions**: 16 IPv4 + 16 IPv6 to r2
- **IPv4 range**: 10.1.1.1/30 to 10.1.16.1/30
- **IPv6 range**: 2001:db8:10:1:1::1/126 to 2001:db8:10:1:16::1/126
- **Router ID**: 192.168.1.1
- **Loopback**: 192.168.1.1/32, 2001:db8:192:168::1/128

### r2 (AS 65002)
- **Default VRF only**
- **16 interfaces**: r2-eth0 to r2-eth15
- **32 eBGP sessions**: 16 IPv4 + 16 IPv6 to r1
- **IPv4 range**: 10.1.1.2/30 to 10.1.16.2/30
- **IPv6 range**: 2001:db8:10:1:1::2/126 to 2001:db8:10:1:16::2/126
- **Router ID**: 192.168.2.2
- **Loopback**: 192.168.2.2/32, 2001:db8:192:168::2/128

## ECMP Features

- **16 parallel paths** between r1 and r2 for both IPv4 and IPv6
- **Equal cost routing** enables ECMP load balancing for dual stack traffic
- **Sharp daemon** for route injection and testing (both IPv4 and IPv6)
- **Route redistribution** via BGP for ECMP verification

## Address Planning

### IPv4 Addressing
- Link subnets: 10.1.X.0/30 where X = 1 to 16
- r1 addresses: 10.1.X.1/30
- r2 addresses: 10.1.X.2/30

### IPv6 Addressing
- Link subnets: 2001:db8:10:1:X::/126 where X = 1 to 16
- r1 addresses: 2001:db8:10:1:X::1/126
- r2 addresses: 2001:db8:10:1:X::2/126

## Test Scenarios

1. **Topology Setup**: Verifies both routers start with 16 dual stack interfaces each
2. **IPv4 BGP Session Establishment**: Confirms all 16 IPv4 BGP sessions are established
3. **IPv6 BGP Session Establishment**: Confirms all 16 IPv6 BGP sessions are established
4. **Sharp Route Installation**: Tests route injection on r2 for both IPv4 and IPv6 ECMP testing
5. **Interface Verification**: Validates proper dual stack interface configuration

## Key Features

- **Dual Stack ECMP**: Multiple equal-cost paths for both IPv4 and IPv6 traffic
- **BGP Multipath**: 32 parallel BGP sessions (16 IPv4 + 16 IPv6) for redundancy
- **Sharp Integration**: Route injection for testing ECMP behavior in both address families
- **JSON Verification**: Robust BGP session state checking for both IPv4 and IPv6
- **Address Family Separation**: Independent IPv4 and IPv6 address families

## Running the Test

```bash
cd tests/topotests/bgp_ecmp_16peers_2routers_v4v6_krishna
sudo python3 -m pytest test_bgp_ecmp_16peers_2routers_v4v6_krishna.py -v
```

## Expected Results

- Both routers should start successfully with 16 dual stack interfaces each
- All 16 IPv4 BGP sessions should reach "Established" state
- All 16 IPv6 BGP sessions should reach "Established" state
- Sharp routes should install successfully for both IPv4 and IPv6 ECMP testing
- Routes should be available via multiple equal-cost paths in both address families

## Use Cases

- **Dual Stack ECMP Testing**: Verify equal-cost multipath routing behavior for both IPv4 and IPv6
- **Load Balancing**: Test traffic distribution across multiple paths for dual stack traffic
- **IPv6 Migration**: Validate ECMP behavior during IPv4 to IPv6 transition scenarios
- **Redundancy**: Validate failover behavior when links go down in dual stack environment
- **Performance**: Measure throughput improvements with multiple paths for both protocols

## Configuration Highlights

### Dual Stack Interface Example
```
interface r1-eth0
 ip address 10.1.1.1/30
 ipv6 address 2001:db8:10:1:1::1/126
 no shutdown
```

### BGP Configuration
```
router bgp 65001
 ! IPv4 neighbors
 neighbor 10.1.1.2 remote-as 65002
 ! IPv6 neighbors  
 neighbor 2001:db8:10:1:1::2 remote-as 65002
 !
 address-family ipv4 unicast
  neighbor 10.1.1.2 activate
 !
 address-family ipv6 unicast
  neighbor 2001:db8:10:1:1::2 activate
```

This test case provides comprehensive validation of BGP ECMP functionality in dual stack environments, ensuring both IPv4 and IPv6 traffic can benefit from multipath load balancing. 