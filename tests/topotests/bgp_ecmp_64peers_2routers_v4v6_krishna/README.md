# BGP ECMP Test with 64 Peers - Dual Stack (bgp_ecmp_64peers_2routers_v4v6_krishna)

## Overview

This test verifies BGP ECMP (Equal Cost Multi-Path) functionality with 64 parallel links between two routers in a dual stack environment (IPv4 + IPv6). This provides ultimate ECMP scalability testing with 128 total BGP sessions.

## Topology

```
r1 (AS 65001) ===== 64 links ===== r2 (AS 65002)
                    Dual Stack
                  (IPv4 + IPv6)
           Ultimate ECMP Scale Test
```

## Router Configuration

### r1 (AS 65001)
- **Default VRF only**
- **64 interfaces**: r1-eth0 to r1-eth63
- **128 eBGP sessions**: 64 IPv4 + 64 IPv6 to r2
- **IPv4 range**: 10.1.1.1/30 to 10.1.64.1/30
- **IPv6 range**: 2001:db8:10:1:1::1/126 to 2001:db8:10:1:64::1/126
- **Router ID**: 192.168.1.1
- **Loopback**: 192.168.1.1/32, 2001:db8:192:168::1/128

### r2 (AS 65002)
- **Default VRF only**
- **64 interfaces**: r2-eth0 to r2-eth63
- **128 eBGP sessions**: 64 IPv4 + 64 IPv6 to r1
- **IPv4 range**: 10.1.1.2/30 to 10.1.64.2/30
- **IPv6 range**: 2001:db8:10:1:1::2/126 to 2001:db8:10:1:64::2/126
- **Router ID**: 192.168.2.2
- **Loopback**: 192.168.2.2/32, 2001:db8:192:168::2/128

## ECMP Features

- **64 parallel paths** between r1 and r2 for both IPv4 and IPv6
- **Ultimate scale ECMP** - maximum number of equal-cost paths supported
- **Equal cost routing** enables ultimate ECMP load balancing for dual stack traffic
- **Sharp daemon** for route injection and testing (both IPv4 and IPv6)
- **Route redistribution** via BGP for ultimate ECMP verification

## Address Planning

### IPv4 Addressing
- Link subnets: 10.1.X.0/30 where X = 1 to 64
- r1 addresses: 10.1.X.1/30
- r2 addresses: 10.1.X.2/30

### IPv6 Addressing
- Link subnets: 2001:db8:10:1:X::/126 where X = 1 to 64
- r1 addresses: 2001:db8:10:1:X::1/126
- r2 addresses: 2001:db8:10:1:X::2/126

## Test Scenarios

1. **Topology Setup**: Verifies both routers start with 64 dual stack interfaces each
2. **IPv4 BGP Session Establishment**: Confirms all 64 IPv4 BGP sessions are established
3. **IPv6 BGP Session Establishment**: Confirms all 64 IPv6 BGP sessions are established
4. **BGP Memory Stress Test**: Performs 50 iterations of route installation/removal with memory monitoring
5. **Sharp Route Installation**: Tests route injection on r2 for both IPv4 and IPv6 ultimate ECMP testing
6. **Interface Verification**: Validates proper 64-way dual stack interface configuration

## Key Features

- **Ultimate Dual Stack ECMP**: 64 equal-cost paths for both IPv4 and IPv6 traffic
- **BGP Multipath Scale**: 128 parallel BGP sessions (64 IPv4 + 64 IPv6) for ultimate redundancy
- **Sharp Integration**: Route injection for testing ultimate ECMP behavior in both address families
- **JSON Verification**: Robust BGP session state checking for both IPv4 and IPv6 at ultimate scale
- **Address Family Separation**: Independent IPv4 and IPv6 address families with maximum paths (64 each)
- **Performance Testing**: Ultimate scale testing for ECMP load balancing
- **Memory Stress Testing**: 50-iteration stress test with memory leak detection

## Running the Test

```bash
cd tests/topotests/bgp_ecmp_64peers_2routers_v4v6_krishna
sudo python3 -m pytest test_bgp_ecmp_64peers_2routers_v4v6_krishna.py -v
```

## Expected Results

- Both routers should start successfully with 64 dual stack interfaces each
- All 64 IPv4 BGP sessions should reach "Established" state
- All 64 IPv6 BGP sessions should reach "Established" state
- Memory stress test should complete all 50 iterations without exceeding 200MB free memory
- Sharp routes should install successfully for both IPv4 and IPv6 ultimate ECMP testing
- Routes should be available via 64 equal-cost paths in both address families
- Ultimate ECMP scale should be demonstrated and validated

## Use Cases

- **Ultimate Scale ECMP Testing**: Verify equal-cost multipath routing behavior at ultimate scale for both IPv4 and IPv6
- **High Performance Load Balancing**: Test traffic distribution across maximum number of paths for dual stack traffic
- **Enterprise Scale IPv6 Migration**: Validate ECMP behavior at enterprise scale during IPv4 to IPv6 transition scenarios
- **Ultimate Redundancy**: Validate failover behavior when links go down in ultimate scale dual stack environment
- **Performance Benchmarking**: Measure ultimate throughput improvements with 64 parallel paths for both protocols
- **Data Center ECMP**: Test ultimate scale ECMP scenarios typical in massive data center environments
- **Memory Leak Detection**: Validate BGP memory management under high-scale route churn

## Configuration Highlights

### 64-way Dual Stack Interface Example
```
interface r1-eth0
 ip address 10.1.1.1/30
 ipv6 address 2001:db8:10:1:1::1/126
 no shutdown
...
interface r1-eth63
 ip address 10.1.64.1/30
 ipv6 address 2001:db8:10:1:64::1/126
 no shutdown
```

### BGP Configuration with 128 Neighbors
```
router bgp 65001
 maximum-paths 64
 maximum-paths ibgp 64
 ! 64 IPv4 neighbors
 neighbor 10.1.1.2 remote-as 65002
 ...
 neighbor 10.1.64.2 remote-as 65002
 ! 64 IPv6 neighbors  
 neighbor 2001:db8:10:1:1::2 remote-as 65002
 ...
 neighbor 2001:db8:10:1:64::2 remote-as 65002
 !
 address-family ipv4 unicast
  ! Activate all 64 IPv4 neighbors
  neighbor 10.1.1.2 activate
  ...
  neighbor 10.1.64.2 activate
 !
 address-family ipv6 unicast
  ! Activate all 64 IPv6 neighbors
  neighbor 2001:db8:10:1:1::2 activate
  ...
  neighbor 2001:db8:10:1:64::2 activate
```

## Memory Stress Test Details

The test includes a comprehensive memory stress test that:
- Runs 50 iterations of route installation and removal
- Installs 20,000 IPv4 routes and 20,000 IPv6 routes per iteration
- Waits for BGP OutQ and InQ to become zero
- Monitors zebra memory usage for "Free ordinary blocks"
- Fails if free memory exceeds 200MB at any point
- Tests memory leak detection and cleanup

## Performance Considerations

- **BGP Convergence**: With 128 BGP sessions, convergence times may be significantly longer
- **Memory Usage**: Ultimate scale testing requires substantial system resources
- **CPU Usage**: Processing 128 BGP sessions requires significant CPU resources
- **Test Timing**: Test timeouts are increased to accommodate ultimate scale (40 iterations, 3-second intervals)
- **System Requirements**: Requires high-memory systems for 64-peer testing

## Scale Benefits

- **Ultimate Load Distribution**: Traffic can be distributed across 64 parallel paths
- **Maximum Redundancy**: Up to 63 links can fail while maintaining connectivity
- **Bandwidth Aggregation**: Potential for 64x bandwidth multiplication
- **Real-world Ultimate Scale**: Represents ultimate ECMP scenarios in massive enterprise/hyperscale data center environments

This test case provides the ultimate validation of BGP ECMP functionality in dual stack environments at the highest scale, ensuring both IPv4 and IPv6 traffic can benefit from 64-way multipath load balancing across all parallel links. The included memory stress testing ensures BGP implementations can handle high-scale route churn without memory leaks. 