# BGP ECMP Test with 32 Peers - Dual Stack (bgp_ecmp_32peers_2routers_v4v6_krishna)

## Overview

This test verifies BGP ECMP (Equal Cost Multi-Path) functionality with 32 parallel links between two routers in a dual stack environment (IPv4 + IPv6). This provides maximum ECMP scalability testing with 64 total BGP sessions.

## Topology

```
r1 (AS 65001) ===== 32 links ===== r2 (AS 65002)
                    Dual Stack
                  (IPv4 + IPv6)
           Maximum ECMP Scale Test
```

## Router Configuration

### r1 (AS 65001)
- **Default VRF only**
- **32 interfaces**: r1-eth0 to r1-eth31
- **64 eBGP sessions**: 32 IPv4 + 32 IPv6 to r2
- **IPv4 range**: 10.1.1.1/30 to 10.1.32.1/30
- **IPv6 range**: 2001:db8:10:1:1::1/126 to 2001:db8:10:1:32::1/126
- **Router ID**: 192.168.1.1
- **Loopback**: 192.168.1.1/32, 2001:db8:192:168::1/128

### r2 (AS 65002)
- **Default VRF only**
- **32 interfaces**: r2-eth0 to r2-eth31
- **64 eBGP sessions**: 32 IPv4 + 32 IPv6 to r1
- **IPv4 range**: 10.1.1.2/30 to 10.1.32.2/30
- **IPv6 range**: 2001:db8:10:1:1::2/126 to 2001:db8:10:1:32::2/126
- **Router ID**: 192.168.2.2
- **Loopback**: 192.168.2.2/32, 2001:db8:192:168::2/128

## ECMP Features

- **32 parallel paths** between r1 and r2 for both IPv4 and IPv6
- **Maximum scale ECMP** - highest number of equal-cost paths supported
- **Equal cost routing** enables maximum ECMP load balancing for dual stack traffic
- **Sharp daemon** for route injection and testing (both IPv4 and IPv6)
- **Route redistribution** via BGP for maximum ECMP verification

## Address Planning

### IPv4 Addressing
- Link subnets: 10.1.X.0/30 where X = 1 to 32
- r1 addresses: 10.1.X.1/30
- r2 addresses: 10.1.X.2/30

### IPv6 Addressing
- Link subnets: 2001:db8:10:1:X::/126 where X = 1 to 32
- r1 addresses: 2001:db8:10:1:X::1/126
- r2 addresses: 2001:db8:10:1:X::2/126

## Test Scenarios

1. **Topology Setup**: Verifies both routers start with 32 dual stack interfaces each
2. **IPv4 BGP Session Establishment**: Confirms all 32 IPv4 BGP sessions are established
3. **IPv6 BGP Session Establishment**: Confirms all 32 IPv6 BGP sessions are established
4. **Sharp Route Installation**: Tests route injection on r2 for both IPv4 and IPv6 maximum ECMP testing
5. **Interface Verification**: Validates proper 32-way dual stack interface configuration

## Key Features

- **Maximum Dual Stack ECMP**: 32 equal-cost paths for both IPv4 and IPv6 traffic
- **BGP Multipath Scale**: 64 parallel BGP sessions (32 IPv4 + 32 IPv6) for maximum redundancy
- **Sharp Integration**: Route injection for testing maximum ECMP behavior in both address families
- **JSON Verification**: Robust BGP session state checking for both IPv4 and IPv6 at scale
- **Address Family Separation**: Independent IPv4 and IPv6 address families with maximum paths
- **Performance Testing**: Maximum scale testing for ECMP load balancing

## Running the Test

```bash
cd tests/topotests/bgp_ecmp_32peers_2routers_v4v6_krishna
sudo python3 -m pytest test_bgp_ecmp_32peers_2routers_v4v6_krishna.py -v
```

## Expected Results

- Both routers should start successfully with 32 dual stack interfaces each
- All 32 IPv4 BGP sessions should reach "Established" state
- All 32 IPv6 BGP sessions should reach "Established" state
- Sharp routes should install successfully for both IPv4 and IPv6 maximum ECMP testing
- Routes should be available via 32 equal-cost paths in both address families
- Maximum ECMP scale should be demonstrated and validated

## Use Cases

- **Maximum Scale ECMP Testing**: Verify equal-cost multipath routing behavior at maximum scale for both IPv4 and IPv6
- **High Performance Load Balancing**: Test traffic distribution across maximum number of paths for dual stack traffic
- **Enterprise Scale IPv6 Migration**: Validate ECMP behavior at enterprise scale during IPv4 to IPv6 transition scenarios
- **Maximum Redundancy**: Validate failover behavior when links go down in maximum scale dual stack environment
- **Performance Benchmarking**: Measure maximum throughput improvements with 32 parallel paths for both protocols
- **Data Center ECMP**: Test maximum scale ECMP scenarios typical in large data center environments

## Configuration Highlights

### 32-way Dual Stack Interface Example
```
interface r1-eth0
 ip address 10.1.1.1/30
 ipv6 address 2001:db8:10:1:1::1/126
 no shutdown
...
interface r1-eth31
 ip address 10.1.32.1/30
 ipv6 address 2001:db8:10:1:32::1/126
 no shutdown
```

### BGP Configuration with 64 Neighbors
```
router bgp 65001
 ! 32 IPv4 neighbors
 neighbor 10.1.1.2 remote-as 65002
 ...
 neighbor 10.1.32.2 remote-as 65002
 ! 32 IPv6 neighbors  
 neighbor 2001:db8:10:1:1::2 remote-as 65002
 ...
 neighbor 2001:db8:10:1:32::2 remote-as 65002
 !
 address-family ipv4 unicast
  ! Activate all 32 IPv4 neighbors
  neighbor 10.1.1.2 activate
  ...
  neighbor 10.1.32.2 activate
 !
 address-family ipv6 unicast
  ! Activate all 32 IPv6 neighbors
  neighbor 2001:db8:10:1:1::2 activate
  ...
  neighbor 2001:db8:10:1:32::2 activate
```

## Performance Considerations

- **BGP Convergence**: With 64 BGP sessions, convergence times may be longer
- **Memory Usage**: Maximum scale testing requires sufficient system resources
- **CPU Usage**: Processing 64 BGP sessions requires adequate CPU resources
- **Test Timing**: Test timeouts are increased to accommodate scale (40 iterations, 3-second intervals)

## Scale Benefits

- **Maximum Load Distribution**: Traffic can be distributed across 32 parallel paths
- **Ultimate Redundancy**: Up to 31 links can fail while maintaining connectivity
- **Bandwidth Aggregation**: Potential for 32x bandwidth multiplication
- **Real-world Scale**: Represents maximum ECMP scenarios in large enterprise/data center environments

This test case provides the ultimate validation of BGP ECMP functionality in dual stack environments at maximum scale, ensuring both IPv4 and IPv6 traffic can benefit from 32-way multipath load balancing across all parallel links. 