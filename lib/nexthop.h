// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Nexthop structure definition.
 * Copyright (C) 1997, 98, 99, 2001 Kunihiro Ishiguro
 * Copyright (C) 2013 Cumulus Networks, Inc.
 */

#ifndef _LIB_NEXTHOP_H
#define _LIB_NEXTHOP_H

#include "jhash.h"
#include "prefix.h"
#include "mpls.h"
#include "vxlan.h"
#include "srv6.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Maximum next hop string length - gateway + ifindex */
#define NEXTHOP_STRLEN (INET6_ADDRSTRLEN + 30)

union g_addr {
	struct in_addr ipv4;
	struct in6_addr ipv6;
};

enum nexthop_types_t {
	NEXTHOP_TYPE_IFINDEX = 1,  /* Directly connected.  */
	NEXTHOP_TYPE_IPV4,	 /* IPv4 nexthop.  */
	NEXTHOP_TYPE_IPV4_IFINDEX, /* IPv4 nexthop with ifindex.  */
	NEXTHOP_TYPE_IPV6,	 /* IPv6 nexthop.  */
	NEXTHOP_TYPE_IPV6_IFINDEX, /* IPv6 nexthop with ifindex.  */
	NEXTHOP_TYPE_BLACKHOLE,    /* Null0 nexthop.  */
};

enum blackhole_type {
	BLACKHOLE_UNSPEC = 0,
	BLACKHOLE_NULL,
	BLACKHOLE_REJECT,
	BLACKHOLE_ADMINPROHIB,
};

enum nh_encap_type {
	NET_VXLAN = 100, /* value copied from FPM_NH_ENCAP_VXLAN. */
};

/* Fixed limit on the number of backup nexthops per primary nexthop */
#define NEXTHOP_MAX_BACKUPS  8

/* Backup index value is limited */
#define NEXTHOP_BACKUP_IDX_MAX 255

/* Nexthop structure. */
struct nexthop {
	struct nexthop *next;
	struct nexthop *prev;


	/* begin of hashed data - all fields from here onwards are given to
	 * jhash() as one consecutive chunk.  DO NOT create "padding holes".
	 * DO NOT insert pointers that need to be deep-hashed.
	 *
	 * static_assert() below needs to be updated when fields are added
	 */
	char _hash_begin[0];

	/* see above */
	enum nexthop_types_t type;

	/* What vrf is this nexthop associated with? */
	vrf_id_t vrf_id;

	/* Interface index. */
	ifindex_t ifindex;

	/* Type of label(s), if any */
	enum lsp_types_t nh_label_type;

	/* padding: keep 16 byte alignment here */

	/* Nexthop address
	 * make sure all 16 bytes for IPv6 are zeroed when putting in an IPv4
	 * address since the entire thing is hashed as-is
	 */
	union {
		union g_addr gate;
		enum blackhole_type bh_type;
	};
	union g_addr src;
	union g_addr rmap_src; /* Src is set via routemap */

	/* end of hashed data - remaining fields in this struct are not
	 * directly fed into jhash().  Most of them are actually part of the
	 * hash but have special rules or handling attached.
	 */
	char _hash_end[0];

	/* Weight of the nexthop ( for unequal cost ECMP ) */
	uint8_t weight;

	uint16_t flags;
#define NEXTHOP_FLAG_ACTIVE     (1 << 0) /* This nexthop is alive. */
#define NEXTHOP_FLAG_FIB        (1 << 1) /* FIB nexthop. */
#define NEXTHOP_FLAG_RECURSIVE  (1 << 2) /* Recursive nexthop. */
#define NEXTHOP_FLAG_ONLINK     (1 << 3) /* Nexthop should be installed
					  * onlink.
					  */
#define NEXTHOP_FLAG_DUPLICATE  (1 << 4) /* nexthop duplicates another
					  * active one
					  */
#define NEXTHOP_FLAG_RNH_FILTERED  (1 << 5) /* rmap filtered, used by rnh */
#define NEXTHOP_FLAG_HAS_BACKUP (1 << 6)    /* Backup nexthop index is set */
#define NEXTHOP_FLAG_SRTE       (1 << 7) /* SR-TE color used for BGP traffic */
#define NEXTHOP_FLAG_EVPN       (1 << 8) /* nexthop is EVPN */
#define NEXTHOP_FLAG_LINKDOWN   (1 << 9) /* is not removed on link down */

	/* which flags are part of nexthop_hash().  Should probably be split
	 * off into a separate field...
	 */
#define NEXTHOP_FLAGS_HASHED NEXTHOP_FLAG_ONLINK

#define NEXTHOP_IS_ACTIVE(flags)                                               \
	(CHECK_FLAG(flags, NEXTHOP_FLAG_ACTIVE)                                \
	 && !CHECK_FLAG(flags, NEXTHOP_FLAG_DUPLICATE))

	/* Nexthops obtained by recursive resolution.
	 *
	 * If the nexthop struct needs to be resolved recursively,
	 * NEXTHOP_FLAG_RECURSIVE will be set in flags and the nexthops
	 * obtained by recursive resolution will be added to `resolved'.
	 */
	struct nexthop *resolved;
	/* Recursive parent */
	struct nexthop *rparent;

	/* Label(s) associated with this nexthop. */
	struct mpls_label_stack *nh_label;

	/* Count and index of corresponding backup nexthop(s) in a backup list;
	 * only meaningful if the HAS_BACKUP flag is set.
	 */
	uint8_t backup_num;
	uint8_t backup_idx[NEXTHOP_MAX_BACKUPS];

	/* Encapsulation information. */
	enum nh_encap_type nh_encap_type;
	union {
		vni_t vni;
	} nh_encap;

	/* EVPN router's MAC.
	 * Don't support multiple RMAC from the same VTEP yet, so it's not
	 * included in hash key.
	 */
	struct ethaddr rmac;

	/* SR-TE color used for matching SR-TE policies */
	uint32_t srte_color;

	/* SRv6 information */
	struct nexthop_srv6 *nh_srv6;
};

/* all hashed fields (including padding, if it is necessary to add) need to
 * be listed in the static_assert below
 */

#define S(field) sizeof(((struct nexthop *)NULL)->field)

static_assert(
	offsetof(struct nexthop, _hash_end) - offsetof(struct nexthop, _hash_begin) ==
		S(type) + S(vrf_id) + S(ifindex) + S(nh_label_type) + S(gate) + S(src) + S(rmap_src),
	"struct nexthop contains padding, this can break things. insert _pad fields at appropriate places");

#undef S

/* this is here to show exactly what is meant by the comments above about
 * the hashing
 */
static inline uint32_t _nexthop_hash_bytes(const struct nexthop *nh, uint32_t seed)
{
	return jhash(&nh->_hash_begin,
		     offsetof(struct nexthop, _hash_end) - offsetof(struct nexthop, _hash_begin),
		     seed);
}

/* Utility to append one nexthop to another. */
#define NEXTHOP_APPEND(to, new)           \
	do {                              \
		(to)->next = (new);       \
		(new)->prev = (to);       \
		(new)->next = NULL;       \
	} while (0)

struct nexthop *nexthop_new(void);

void nexthop_free(struct nexthop *nexthop);
void nexthops_free(struct nexthop *nexthop);

void nexthop_add_labels(struct nexthop *nexthop, enum lsp_types_t ltype,
			uint8_t num_labels, const mpls_label_t *labels);
void nexthop_del_labels(struct nexthop *);
void nexthop_change_labels(struct nexthop *nexthop, struct mpls_label_stack *new_stack);

void nexthop_add_srv6_seg6local(struct nexthop *nexthop, uint32_t action,
				const struct seg6local_context *ctx);
void nexthop_del_srv6_seg6local(struct nexthop *nexthop);
void nexthop_add_srv6_seg6(struct nexthop *nexthop, const struct in6_addr *seg, int num_segs,
			   enum srv6_headend_behavior encap_behavior);
void nexthop_del_srv6_seg6(struct nexthop *nexthop);

/*
 * Allocate a new nexthop object and initialize it from various args.
 */
struct nexthop *nexthop_from_ifindex(ifindex_t ifindex, vrf_id_t vrf_id);
struct nexthop *nexthop_from_ipv4(const struct in_addr *ipv4,
				  const struct in_addr *src,
				  vrf_id_t vrf_id);
struct nexthop *nexthop_from_ipv4_ifindex(const struct in_addr *ipv4,
					  const struct in_addr *src,
					  ifindex_t ifindex, vrf_id_t vrf_id);
struct nexthop *nexthop_from_ipv6(const struct in6_addr *ipv6,
				  vrf_id_t vrf_id);
struct nexthop *nexthop_from_ipv6_ifindex(const struct in6_addr *ipv6,
					  ifindex_t ifindex, vrf_id_t vrf_id);
struct nexthop *nexthop_from_blackhole(enum blackhole_type bh_type,
				       vrf_id_t nh_vrf_id);

/*
 * Hash a nexthop. Suitable for use with hash tables.
 *
 * Please double check the code on what is included in the hash, there was
 * documentation here but it got outdated and the only thing worse than no
 * doc is incorrect doc.
 */
uint32_t nexthop_hash(const struct nexthop *nexthop);

extern bool nexthop_same(const struct nexthop *nh1, const struct nexthop *nh2);
extern bool nexthop_same_no_ifindex(const struct nexthop *nh1, const struct nexthop *nh2);
extern bool nexthop_same_no_labels(const struct nexthop *nh1,
				   const struct nexthop *nh2);
extern bool nexthop_same_no_weight(const struct nexthop *nh1, const struct nexthop *nh2);
extern int nexthop_cmp(const struct nexthop *nh1, const struct nexthop *nh2);
extern int nexthop_cmp_no_weight(const struct nexthop *nh1,
				 const struct nexthop *nh2);
extern int nexthop_g_addr_cmp(enum nexthop_types_t type,
			      const union g_addr *addr1,
			      const union g_addr *addr2);

/* More-limited comparison function used to detect duplicate nexthops.
 * Returns -1, 0, 1
 */
int nexthop_cmp_basic(const struct nexthop *nh1, const struct nexthop *nh2);

extern const char *nexthop_type_to_str(enum nexthop_types_t nh_type);
extern bool nexthop_labels_match(const struct nexthop *nh1,
				 const struct nexthop *nh2);

extern const char *nexthop2str(const struct nexthop *nexthop,
			       char *str, int size);
extern struct nexthop *nexthop_next(const struct nexthop *nexthop);
extern struct nexthop *nexthop_next_resolution(const struct nexthop *nexthop,
					       bool nexthop_resolution);
extern struct nexthop *
nexthop_next_active_resolved(const struct nexthop *nexthop);
extern unsigned int nexthop_level(const struct nexthop *nexthop);
/* Copies to an already allocated nexthop struct */
extern void nexthop_copy(struct nexthop *copy, const struct nexthop *nexthop,
			 struct nexthop *rparent);
/* Copies to an already allocated nexthop struct, not including recurse info */
extern void nexthop_copy_no_recurse(struct nexthop *copy,
				    const struct nexthop *nexthop,
				    struct nexthop *rparent);
/* Duplicates a nexthop and returns the newly allocated nexthop */
extern struct nexthop *nexthop_dup(const struct nexthop *nexthop,
				   struct nexthop *rparent);
/* Duplicates a nexthop and returns the newly allocated nexthop */
extern struct nexthop *nexthop_dup_no_recurse(const struct nexthop *nexthop,
					      struct nexthop *rparent);

/* Is this nexthop a blackhole? */
extern bool nexthop_is_blackhole(const struct nexthop *nh);

/*
 * Parse one or more backup index values, as comma-separated numbers,
 * into caller's array of uint8_ts. The array must be NEXTHOP_MAX_BACKUPS
 * in size. Mails back the number of values converted, and returns 0 on
 * success, <0 if an error in parsing.
 */
int nexthop_str2backups(const char *str, int *num_backups,
			uint8_t *backups);

void nexthop_json_helper(json_object *json_nexthop,
			 const struct nexthop *nexthop, bool display_vrfid,
			 uint8_t rn_family);
void nexthop_vty_helper(struct vty *vty, const struct nexthop *nexthop,
			bool display_vrfid, uint8_t rn_family);

#ifdef _FRR_ATTRIBUTE_PRINTFRR
#pragma FRR printfrr_ext "%pNH"  (struct nexthop *)
#endif

ssize_t printfrr_nhs(struct fbuf *buf, const struct nexthop *nh);
#ifdef __cplusplus
}
#endif

#endif /*_LIB_NEXTHOP_H */
