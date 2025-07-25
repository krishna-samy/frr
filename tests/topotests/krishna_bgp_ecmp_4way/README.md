# BGP 4-way ECMP Test (bgp_ecmp_4way_krishna)

## Overview

This test verifies BGP ECMP (Equal Cost Multi-Path) functionality with 4 parallel links between two routers.

## Topology

```
r1 (AS 65001) ===== 4 links ===== r2 (AS 65002)
```

## Router Configuration

### r1 (AS 65001)
- **Default VRF only**
- **4 interfaces**: r1-eth0 to r1-eth3
- **4 eBGP sessions**: to r2
- **IP range**: 10.1.1.1/30 to 10.1.4.1/30
- **Router ID**: 192.168.1.1

### r2 (AS 65002)
- **Default VRF only**
- **4 interfaces**: r2-eth0 to r2-eth3
- **4 eBGP sessions**: to r1
- **IP range**: 10.1.1.2/30 to 10.1.4.2/30
- **Router ID**: 192.168.2.2

## ECMP Features

- **4 parallel paths** between r1 and r2
- **Equal cost routing** enables 4-way ECMP load balancing
- **Sharp daemon** for route injection and testing
- **Route redistribution** via BGP for ECMP verification

## Test Scenarios

1. **Topology Setup**: Verifies both routers start with 4 interfaces each
2. **BGP Session Establishment**: Confirms all 4 BGP sessions are established
3. **Sharp Route Installation**: Tests route injection on r2 for ECMP testing
4. **Interface Verification**: Validates proper interface configuration

## Key Features

- **4-way ECMP Load Balancing**: Multiple equal-cost paths for traffic distribution
- **BGP Multipath**: 4 parallel BGP sessions for redundancy
- **Sharp Integration**: Route injection for testing ECMP behavior
- **JSON Verification**: Robust BGP session state checking

## Running the Test

```bash
cd tests/topotests/bgp_ecmp_4way_krishna
sudo python3 -m pytest test_bgp_ecmp_4way_krishna.py -v
```

## Expected Results

- Both routers should start successfully with 4 interfaces each
- All 4 BGP sessions should reach "Established" state
- Sharp routes should install successfully for ECMP testing
- Routes should be available via 4 equal-cost paths

## Use Cases

- **Basic ECMP Testing**: Verify 4-way equal-cost multipath routing behavior
- **Load Balancing**: Test traffic distribution across 4 parallel paths
- **Redundancy**: Validate failover behavior when some links go down
- **Performance**: Measure throughput improvements with 4 parallel paths 