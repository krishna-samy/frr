## Problem Analysis

The following flamegraph shows the CPU hotspot during route convergence:
We are trying to avoid the repeated processing of same NH resolution for the whole bunch of routes pointing to the same ECMP
rib_process() -> nexthop_active_update() is the function that becomes a hotspot
The CPU consumption by this function is between 15% to 20% for the routes 100k with 16way/32way ECMP and trying to optimize it.

## Data Structure Changes

### On the received/unresolved NHE:

```c
struct nhg_hash_entry {
    ...
    struct list *resolved_via_rns;  // List of route_node* used for resolution
    uint32_t installed_nhe_id;       // Cached resolved NHE
    uint32_t activation_epoch;     // will be compared against global value for each rib_process()
};
```

### On each route_node that was resolved for nexthop:

```c
struct route_node {
    ...
    struct list *dependent_received_nhes;    // List of NHEs that resolved via this RN
};
```

## Overall Solution

```
                                                               +------------------------------------+
                                                               |          BGP Route Arrives         |
                                                               |        (e.g., 192.168.X.0/24)      |
                                                               +-------------------+----------------+
                                                                                   |
                                                                                   v
                                                               +------------------------------------+
                                                               |       Early Route Processing       |
                                                               | - create/find re_bgp_X             |
                                                               | - create/find received_nhe (NHE-100)|
                                                               | - attach re_bgp_X.received_nhe     |
                                                               +-------------------+----------------+
                                                                                   |
                                                                                   v
                                                               +--------------------------------------------+
                                                               | rib_process                                |
                                                               |  - nexthop_active_update(re, received_nhe) |
                                                               +-------------------+------------------------+
                                                                                   |
                                                                                   v
                                        +-----------------------------------------------------------------------------------------+
                                        |   Cache Valid? (NHE-100.activation_epoch == global_epoch)                               |
                                        +-----------------------------------------------------------------------------------------+
                                                     |                                                          |
                                                   YES                                                          NO
                                                     |                                                          |
                                                     v                                                          |
                                         +----------------------------+                                         |
                                         | Route-map Check            |                                         |
                                         | zebra_route_map_check()    |                                         |
                                         |                            |                                         |
                                         +-----------+----------------+                                         |
                                                     |                                                          |
                                         +-----------+-----------+                                              |
                                         |                       |                                              |
                                   No route-map            Route-map                                            |
                                   configured              configured                                           |
                                         |                       |                                              |
                                         |                       v                                              |
                                         |           +-------------------------+                                |
                                         |           | Route-map permits?      |                                |
                                         |           | (any NH modifications?) |                                |
                                         |           +-----------+-------------+                                |
                                         |                       |                                              |
                                         |                       v                                              |                                         
                                         |           +-----------+----------------------+                       |
                                         |           |                                  |                       |
                                         |         PERMIT                             DENY/                     |
                                         |       (no mods)                          modifies                    |
                                         |           |                                  |                       |
                                         +---------->+                                  |                       |
                                                     |                                  |                       |
                                                     v                                  v                       v
                                         +-----------+------------+                +-------+----------------------------------+ 
                                         | Installed NHE present? |                |   Slow Path: Resolve & track nhe <-> rn  |
                                         | in cache?              |      NO        |   Do per nexthop_active()                |                                        
                                         | (NHE-100.installed_    |--------------->| - resolve NHs (route_node_match          |
                                         |  nhe_id != 0)          |                |   A,B,C,D)                               |
                                         +-----------+------------+                | - add bidirectional tracking             |
                                               |                                   |   (received_nhe <-> rn_ospf_*)           |
                                               |                                   | - create installed_nhe (e.g.,            |
                                               |                                   |   NHE-200) point re->nhe = 200           |
                                             YES                                   +------------------------------------------+
                                               |                                                            |
                                               v                                                            |
                                      +--------+--------+                                                   v
                                      |   Fast Path     |                                       +-----------+------------+
                                      | - lookup installed_nhe by id                            |      Cache Update      |
                                      | - use this nhe and skip costly nexthop_active()         | - NHE-100.installed_   |
                                      |                                                         |   nhe_id = 200         |
                                      +--------+--------+                                       | - NHE-100.activation_  |
                                               |                                                |   epoch = global_epoch |
                                               |                                                +-----------+------------+
                                               |                                                            |
                                               +------------------------------------------------------------+
                                                                             |
                                                                             v
                                                                +------------+---------------+
                                                                |       Route Installed      |
                                                                +----------------------------+
```

## Cache Invalidation on OSPF Route Update

For the above example where BGP nexthop is recursively resolved by OSPF - And OSPF route update comes to the metaQ when BGP routes are still being processed, we need to invalidate the cache. So that the sub-sequent BGP routes take the slow/regular path.

### When the nexthops are resolved recursively:
Let's say we have 100 BGP routes that point to NH A&B(these NHs are resolved by OSPF).
And we receive a OSPF route update in metaQ while we are still processing the 100 BGP routes.

**Example:** BGP sending routes with
- nh A, nh B

And Nexthops resolves via ospf:
- A --> C
- B --> D

And then OSPF changes A --> E

```
                                               +----------------------------------+
                                               |         OSPF Route Update        |
                                               |       (e.g., 10.0.0.1/32)        |
                                               +------------------+---------------+
                                                                  |
                                                                  v
                                               +------------------+----------------------------------------+
                                               | zebra_nhg_invalidate_via_rn(rn_ospf_A):                   |
                                               |  for each received_nhe in rn_ospf_A.dependent_received_nhe|
                                               |   - NHE-100.installed_nhe_id = 0                          |
                                               |   - NHE-100.activation_epoch = 0                          |
                                               |   - remove tracking links                                 |
                                               +------------------+----------------------------------------+
                                                                  |
                                                                  v
                                                        +---------+-------------------------+
                                                        |   All the Cache/Track Invalidated |
                                                        +---------+-------------------------+
                                                                  |
                                                                  v
                                                        +---------+----------+
                                                        | Next BGP Route     |
                                                        | Arrives (from queue)
                                                        +---------+----------+
                                                                  |
                                                                  v
                                                        [Back to Early Route Processing]  >>> this will take the slow path again.
```

## Cleanup Process

### When the received_nhe is deleted: clean-up the mapping

```c
for each received_nhe.resolved_via_rns
  rn.dependent_received_nhes = 0;
```

## Global Epoch Value

**Variable:** `global_nh_epoch`

Incremented when any system event that can affect nexthop.
So, when any route comes to rib_process will see the existing cache invalidated and go through the new learning.
Example:
- Interface up/down
- Route-map changes

