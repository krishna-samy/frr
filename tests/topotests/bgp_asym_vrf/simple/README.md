# BGP Asymmetric VRF - Simple Test Version

This directory contains a simplified version of the BGP asymmetric VRF test for development and debugging purposes.

## Test Configuration

- **Topology**: 2 routers connected by 4 links (instead of 16)
- **VRFs**: 1 VRF on r1 (instead of 4)
- **BGP Sessions**: 4 eBGP sessions (AS 65001 ↔ AS 65002)

## Directory Structure

```
simple/
├── test_bgp_asym_vrf_simple.py    # Simplified test script
├── r1/
│   └── frr.conf                   # r1 FRR configuration
├── r2/
│   └── frr.conf                   # r2 FRR configuration
└── README.md                      # This file
```

## Running the Test

```bash
cd simple/
sudo -E python3 -m pytest test_bgp_asym_vrf_simple.py -s -vv
```

## Purpose

This simplified version is useful for:
- Quick testing and debugging
- Development of new features
- Understanding the test logic before scaling to the full 16-link version 