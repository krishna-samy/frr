# BGP Asymmetric VRF Cross-Connect + ECMP Test (bgp_asym_4vrf_4routers_16peers_cross_connect_krishna)

## Overview

This test verifies BGP functionality in an asymmetric VRF topology with cross-connect design plus 4-way ECMP using 7 routers total. Unlike the traditional approach where each VRF connects to a single upstream router, this topology implements a cross-connect design where each VRF on r1 connects to all 4 upstream routers, plus additional downstream routers (r6, r7) that connect to all upstream routers for 4-way ECMP.

## Topology

```
                    r2 (AS 65002)
                   /|\ |   | /|\
              vrf1 - | |   | | - vrf4     r6 (AS 65006)
             /   \  | |   | |  /   \      /||\
    r1 ---- vrf2 --\| |   | |/-- vrf3    / || \
   (AS 65001) \     | |   | |     /     /  ||  \
               vrf3 -| |   | |- vrf2    r2--+r3-r4--r5
                 \   | |   | |   /          ||   
                  vrf4| |   | |vrf1         || 
                      | |   | |             || 
                    r3 -------  r4          ||
                  (AS 65003)  (AS 65004)    ||
                       |         |          ||
                       |         |          ||
                       +---------+----------++
                               |
                           r5 (AS 65005)
                               |
                               |
                       r7 (AS 65007)
                       /||\
                      / || \
                     r2-r3-r4-r5
```

### Cross-Connect Design

Each VRF on r1 connects to ALL 4 upstream routers:
- **vrf1**: connects to r2, r3, r4, r5 (1 link each)
- **vrf2**: connects to r2, r3, r4, r5 (1 link each)  
- **vrf3**: connects to r2, r3, r4, r5 (1 link each)
- **vrf4**: connects to r2, r3, r4, r5 (1 link each)

Each upstream router connects to ALL 4 VRFs on r1 + r6 + r7:
- **r2**: connects to vrf1, vrf2, vrf3, vrf4 (1 link each) + r6 + r7 = 6 total links
- **r3**: connects to vrf1, vrf2, vrf3, vrf4 (1 link each) + r6 + r7 = 6 total links
- **r4**: connects to vrf1, vrf2, vrf3, vrf4 (1 link each) + r6 + r7 = 6 total links
- **r5**: connects to vrf1, vrf2, vrf3, vrf4 (1 link each) + r6 + r7 = 6 total links

Each ECMP router connects to ALL 4 upstream routers:
- **r6**: connects to r2, r3, r4, r5 (1 link each) for 4-way ECMP
- **r7**: connects to r2, r3, r4, r5 (1 link each) for 4-way ECMP

## Router Configuration

### r1 (AS 65001)
- **4 VRFs**: vrf1, vrf2, vrf3, vrf4
- **16 interfaces total**: 4 per VRF (cross-connect to all upstream routers)
- **VRF/Interface assignments**:
  - vrf1: r1-eth0→r2, r1-eth1→r3, r1-eth2→r4, r1-eth3→r5
  - vrf2: r1-eth4→r2, r1-eth5→r3, r1-eth6→r4, r1-eth7→r5
  - vrf3: r1-eth8→r2, r1-eth9→r3, r1-eth10→r4, r1-eth11→r5
  - vrf4: r1-eth12→r2, r1-eth13→r3, r1-eth14→r4, r1-eth15→r5
- **16 eBGP sessions**: Each VRF has 4 sessions (one to each upstream router)

### r2 (AS 65002)
- **Default VRF only**
- **6 interfaces**: r2-eth0→vrf1, r2-eth1→vrf2, r2-eth2→vrf3, r2-eth3→vrf4, r2-eth4→r6, r2-eth5→r7
- **6 eBGP sessions**: 4 to r1 VRFs + 1 to r6 + 1 to r7
- **IP ranges**: 10.1.1.0/30, 10.1.5.0/30, 10.1.9.0/30, 10.1.13.0/30, 10.1.17.0/30, 10.1.21.0/30

### r3 (AS 65003)
- **Default VRF only**
- **6 interfaces**: r3-eth0→vrf1, r3-eth1→vrf2, r3-eth2→vrf3, r3-eth3→vrf4, r3-eth4→r6, r3-eth5→r7
- **6 eBGP sessions**: 4 to r1 VRFs + 1 to r6 + 1 to r7
- **IP ranges**: 10.1.2.0/30, 10.1.6.0/30, 10.1.10.0/30, 10.1.14.0/30, 10.1.18.0/30, 10.1.22.0/30

### r4 (AS 65004)
- **Default VRF only**
- **6 interfaces**: r4-eth0→vrf1, r4-eth1→vrf2, r4-eth2→vrf3, r4-eth3→vrf4, r4-eth4→r6, r4-eth5→r7
- **6 eBGP sessions**: 4 to r1 VRFs + 1 to r6 + 1 to r7
- **IP ranges**: 10.1.3.0/30, 10.1.7.0/30, 10.1.11.0/30, 10.1.15.0/30, 10.1.19.0/30, 10.1.23.0/30

### r5 (AS 65005)
- **Default VRF only**
- **6 interfaces**: r5-eth0→vrf1, r5-eth1→vrf2, r5-eth2→vrf3, r5-eth3→vrf4, r5-eth4→r6, r5-eth5→r7
- **6 eBGP sessions**: 4 to r1 VRFs + 1 to r6 + 1 to r7
- **IP ranges**: 10.1.4.0/30, 10.1.8.0/30, 10.1.12.0/30, 10.1.16.0/30, 10.1.20.0/30, 10.1.24.0/30

### r6 (AS 65006)
- **Default VRF only**
- **4 interfaces**: r6-eth0→r2, r6-eth1→r3, r6-eth2→r4, r6-eth3→r5
- **4 eBGP sessions**: One to each upstream router for 4-way ECMP
- **IP ranges**: 10.1.17.0/30, 10.1.18.0/30, 10.1.19.0/30, 10.1.20.0/30

### r7 (AS 65007)
- **Default VRF only**
- **4 interfaces**: r7-eth0→r2, r7-eth1→r3, r7-eth2→r4, r7-eth3→r5
- **4 eBGP sessions**: One to each upstream router for 4-way ECMP
- **IP ranges**: 10.1.21.0/30, 10.1.22.0/30, 10.1.23.0/30, 10.1.24.0/30

## Detailed Link Mapping

| r1 VRF | r1 Interface | Remote Router | Remote Interface | IP Range     |
|--------|-------------|---------------|------------------|--------------|
| vrf1   | r1-eth0     | r2           | r2-eth0          | 10.1.1.0/30  |
| vrf1   | r1-eth1     | r3           | r3-eth0          | 10.1.2.0/30  |
| vrf1   | r1-eth2     | r4           | r4-eth0          | 10.1.3.0/30  |
| vrf1   | r1-eth3     | r5           | r5-eth0          | 10.1.4.0/30  |
| vrf2   | r1-eth4     | r2           | r2-eth1          | 10.1.5.0/30  |
| vrf2   | r1-eth5     | r3           | r3-eth1          | 10.1.6.0/30  |
| vrf2   | r1-eth6     | r4           | r4-eth1          | 10.1.7.0/30  |
| vrf2   | r1-eth7     | r5           | r5-eth1          | 10.1.8.0/30  |
| vrf3   | r1-eth8     | r2           | r2-eth2          | 10.1.9.0/30  |
| vrf3   | r1-eth9     | r3           | r3-eth2          | 10.1.10.0/30 |
| vrf3   | r1-eth10    | r4           | r4-eth2          | 10.1.11.0/30 |
| vrf3   | r1-eth11    | r5           | r5-eth2          | 10.1.12.0/30 |
| vrf4   | r1-eth12    | r2           | r2-eth3          | 10.1.13.0/30 |
| vrf4   | r1-eth13    | r3           | r3-eth3          | 10.1.14.0/30 |
| vrf4   | r1-eth14    | r4           | r4-eth3          | 10.1.15.0/30 |
| vrf4   | r1-eth15    | r5           | r5-eth3          | 10.1.16.0/30 |
| **r6** | **r6-eth0** | **r2**       | **r2-eth4**      | **10.1.17.0/30** |
| **r6** | **r6-eth1** | **r3**       | **r3-eth4**      | **10.1.18.0/30** |
| **r6** | **r6-eth2** | **r4**       | **r4-eth4**      | **10.1.19.0/30** |
| **r6** | **r6-eth3** | **r5**       | **r5-eth4**      | **10.1.20.0/30** |
| **r7** | **r7-eth0** | **r2**       | **r2-eth5**      | **10.1.21.0/30** |
| **r7** | **r7-eth1** | **r3**       | **r3-eth5**      | **10.1.22.0/30** |
| **r7** | **r7-eth2** | **r4**       | **r4-eth5**      | **10.1.23.0/30** |
| **r7** | **r7-eth3** | **r5**       | **r5-eth5**      | **10.1.24.0/30** |

## Test Scenarios

1. **Topology Setup**: Verifies all 7 routers start correctly with proper interface counts
2. **BGP Session Establishment**: Confirms all 32 BGP sessions are established
   - r1: 16 total sessions across 4 VRFs (4 sessions per VRF)
   - r2, r3, r4, r5: 6 sessions each (4 to r1 VRFs + 1 to r6 + 1 to r7)
   - r6, r7: 4 sessions each (one to each upstream router for 4-way ECMP)
3. **Cross-Connect Verification**: Validates that each VRF connects to all upstream routers
4. **ECMP Verification**: Validates that r6 and r7 have 4-way ECMP to all upstream routers
5. **Sharp Route Installation**: Tests route redistribution across the extended topology

## Key Features

- **Cross-Connect Design**: Each VRF connects to ALL upstream routers for full redundancy
- **4-Way ECMP**: r6 and r7 demonstrate traditional ECMP across multiple upstream paths
- **Asymmetric VRF**: r1 uses VRFs while other routers use default VRF
- **Multi-AS setup**: Each router uses different AS numbers (65001-65007)
- **Sharp daemon**: Enabled for route redistribution testing
- **Full mesh from VRF perspective**: Each VRF has connectivity to all external ASes
- **Hybrid topology**: Combines VRF cross-connect with traditional ECMP

## Advantages of Cross-Connect + ECMP Design

1. **VRF Redundancy**: Each VRF has multiple paths to all external ASes
2. **ECMP Load Balancing**: r6 and r7 demonstrate 4-way load balancing across upstream routers
3. **Fault Tolerance**: Failure of any single upstream router doesn't isolate any VRF or ECMP router
4. **Flexible Routing**: More granular control over routing policies per VRF
5. **Scalable Design**: Shows how VRF and ECMP approaches can coexist in the same topology
6. **Redundant Upstream**: Upstream routers (r2-r5) handle both VRF and ECMP traffic

## Running the Test

```bash
cd tests/topotests/bgp_asym_4vrf_4routers_16peers_cross_connect_krishna
sudo python3 -m pytest test_bgp_asym_4vrf_4routers_cross_connect_krishna.py -v
```

## Expected Results

- All 7 routers should start successfully  
- All 32 BGP sessions should reach "Established" state:
  - 16 sessions from r1 (4 sessions per VRF)
  - 24 sessions to upstream routers (6 sessions each on r2, r3, r4, r5)
  - 8 sessions from ECMP routers (4 sessions each on r6, r7)
- Cross-connect verification should pass (each VRF connects to all upstream routers)
- ECMP verification should pass (r6 and r7 connect to all upstream routers)
- All VRF interface assignments should be correct
- Sharp daemon should be running on all routers for route redistribution
- r6 and r7 should demonstrate 4-way ECMP when receiving routes from upstream routers 