# BGP Asymmetric VRF Test with 4 Routers (bgp_asym_4vrf_4routers_krishna)

## Overview

This test verifies BGP functionality in an asymmetric VRF topology with 5 routers total.

## Topology

```
                                r2 (AS 65002)
                               /
                 vrf1 ---- 4 links
                /
    r1 ---- vrf2 ---- 4 links ---- r3 (AS 65003)
   (AS 65001) \
                 vrf3 ---- 4 links ---- r4 (AS 65004)
                \
                 vrf4 ---- 4 links
                               \
                                r5 (AS 65005)
```

## Router Configuration

### r1 (AS 65001)
- **4 VRFs**: vrf1, vrf2, vrf3, vrf4
- **16 interfaces total**: 4 per VRF
- **VRF assignments**:
  - vrf1: r1-eth0 to r1-eth3 (connects to r2)
  - vrf2: r1-eth4 to r1-eth7 (connects to r3)
  - vrf3: r1-eth8 to r1-eth11 (connects to r4)  
  - vrf4: r1-eth12 to r1-eth15 (connects to r5)
- **16 eBGP sessions**: 4 sessions per VRF to different routers

### r2 (AS 65002)
- **Default VRF only**
- **4 interfaces**: r2-eth0 to r2-eth3
- **4 eBGP sessions**: to r1's vrf1
- **IP range**: 10.1.1.0/30 to 10.1.4.0/30

### r3 (AS 65003)
- **Default VRF only**
- **4 interfaces**: r3-eth0 to r3-eth3
- **4 eBGP sessions**: to r1's vrf2
- **IP range**: 10.1.5.0/30 to 10.1.8.0/30

### r4 (AS 65004)
- **Default VRF only**
- **4 interfaces**: r4-eth0 to r4-eth3
- **4 eBGP sessions**: to r1's vrf3
- **IP range**: 10.1.9.0/30 to 10.1.12.0/30

### r5 (AS 65005)
- **Default VRF only**
- **4 interfaces**: r5-eth0 to r5-eth3
- **4 eBGP sessions**: to r1's vrf4
- **IP range**: 10.1.13.0/30 to 10.1.16.0/30

## Test Scenarios

1. **Topology Setup**: Verifies all 5 routers start correctly with proper interface counts
2. **BGP Session Establishment**: Confirms all 16 BGP sessions are established
   - r1: 16 total sessions across 4 VRFs
   - r2, r3, r4, r5: 4 sessions each
3. **VRF Interface Assignment**: Validates proper interface-to-VRF assignments on r1

## Key Features

- **Asymmetric VRF design**: r1 uses VRFs while r2-r5 use default VRF
- **Multi-AS setup**: Each router pair uses different AS numbers
- **Sharp daemon**: Enabled for route redistribution testing
- **Scalable design**: Demonstrates VRF segregation with multiple external peers

## Running the Test

```bash
cd tests/topotests/bgp_asym_4vrf_4routers_krishna
sudo python3 -m pytest test_bgp_asym_4vrf_4routers_krishna.py -v
```

## Expected Results

- All 5 routers should start successfully
- All 16 BGP sessions should reach "Established" state  
- All VRF interface assignments should be correct
- Sharp daemon should be running on all routers for route redistribution 