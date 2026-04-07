// SPDX-License-Identifier: GPL-2.0-or-later
/* Zebra NHG Event Tracker implementation.
 *
 * Copyright (C) 2024 NVIDIA Corporation
 *                    Krishnasamy R
 *                    Donald Sharp
 *                    Eyal Nissim
 */

#include <zebra.h>

#include "jhash.h"
#include "memory.h"
#include "table.h"

#include "zebra/rib.h"
#include "zebra/zebra_nhg.h"
#include "zebra/zebra_nhg_tracker.h"
#include "zebra/zebra_router.h"

DEFINE_MTYPE_STATIC(ZEBRA, NHG_TRACKER, "NHG Event Tracker");
DEFINE_MTYPE(ZEBRA, NHG_TRACKER_PREFIX_MAP, "NHG Tracker Prefix Map Entry");

/* Get or create the route_table for a given VRF within a tracker table. */
static struct route_table *tracker_vrf_table_get(struct nhg_tracker_table *tt, vrf_id_t vrf_id)
{
	struct tracker_vrf_table *vt;

	for (vt = tt->vrf_tables; vt; vt = vt->next) {
		if (vt->vrf_id == vrf_id)
			return vt->table;
	}

	vt = XCALLOC(MTYPE_NHG_TRACKER, sizeof(*vt));
	vt->vrf_id = vrf_id;
	vt->table = route_table_init();
	vt->next = tt->vrf_tables;
	tt->vrf_tables = vt;
	return vt->table;
}

/* Free all per-VRF tables in a tracker table, unlocking any stored RIB RNs. */
static void tracker_vrf_tables_free(struct nhg_tracker_table *tt)
{
	struct tracker_vrf_table *vt, *next;

	for (vt = tt->vrf_tables; vt; vt = next) {
		next = vt->next;
		if (vt->table) {
			struct route_node *trn;

			for (trn = route_top(vt->table); trn; trn = route_next(trn)) {
				if (trn->info) {
					route_unlock_node(trn->info);
					trn->info = NULL;
					route_unlock_node(trn);
				}
			}
			route_table_finish(vt->table);
		}
		XFREE(MTYPE_NHG_TRACKER, vt);
	}
	tt->vrf_tables = NULL;
}

/*
 * tracker_prefix_map hash.
 * Key:   (prefix, protocol type, protocol instance, vrf_id).
 * Value: pointer to the tracker that owns this (prefix, type, instance, vrf).
 */
uint32_t tracker_prefix_map_hash_key(const struct tracker_prefix_map_entry *e)
{
	uint32_t key;

	key = prefix_hash_key(&e->p);
	key = jhash_2words((uint32_t)e->type, (uint32_t)e->instance, key);
	key = jhash_1word((uint32_t)e->vrf_id, key);
	return key;
}

int tracker_prefix_map_hash_cmp(const struct tracker_prefix_map_entry *a,
				const struct tracker_prefix_map_entry *b)
{
	if (a->type != b->type)
		return 1;
	if (a->instance != b->instance)
		return 1;
	if (a->vrf_id != b->vrf_id)
		return 1;
	return prefix_cmp(&a->p, &b->p) != 0;
}

/*
 * Hash key: parent NHG ID + nexthop hashes.
 */
uint32_t nhg_event_tracker_hash_key(const struct nhg_event_tracker *t)
{
	const struct nhg_hash_entry *snap = t->nhg_tracker_snapshot;
	uint32_t key = 0x5a351234;
	uint32_t primary;
	uint32_t backup = 0;

	primary = nexthop_group_hash(&snap->nhg);
	if (snap->backup_info)
		backup = nexthop_group_hash(&snap->backup_info->nhe->nhg);

	key = jhash_3words(snap->id, primary, backup, key);

	return key;
}

/*
 * Returns 0 on match, non-zero otherwise.
 */
int nhg_event_tracker_hash_cmp(const struct nhg_event_tracker *a, const struct nhg_event_tracker *b)
{
	const struct nhg_hash_entry *sa = a->nhg_tracker_snapshot;
	const struct nhg_hash_entry *sb = b->nhg_tracker_snapshot;
	struct nexthop *nh1, *nh2;

	if (sa->id != sb->id)
		return 1;

	/* Compare primary nexthops */
	for (nh1 = sa->nhg.nexthop, nh2 = sb->nhg.nexthop; nh1 && nh2;
	     nh1 = nexthop_next(nh1), nh2 = nexthop_next(nh2)) {
		if (!nhg_compare_nexthops(nh1, nh2))
			return 1;
	}
	if (nh1 || nh2)
		return 1;

	/* Compare backup nexthops */
	if (!sa->backup_info && !sb->backup_info)
		return 0;
	if (sa->backup_info && !sb->backup_info)
		return 1;
	if (!sa->backup_info && sb->backup_info)
		return 1;

	for (nh1 = sa->backup_info->nhe->nhg.nexthop, nh2 = sb->backup_info->nhe->nhg.nexthop;
	     nh1 && nh2; nh1 = nexthop_next(nh1), nh2 = nexthop_next(nh2)) {
		if (!nhg_compare_nexthops(nh1, nh2))
			return 1;
	}
	if (nh1 || nh2)
		return 1;

	return 0;
}

/*
 * Move all per-VRF table entries from src into dst.
 * For each VRF table in src, get-or-create the matching VRF table in dst.
 * For each prefix: if dst doesn't have it, move the RN pointer.
 * If dst already has it, release the src reference.
 */
static void tracker_vrf_tables_move(struct nhg_tracker_table *src, struct nhg_tracker_table *dst)
{
	struct tracker_vrf_table *vt, *next;

	for (vt = src->vrf_tables; vt; vt = next) {
		next = vt->next;
		if (!vt->table) {
			XFREE(MTYPE_NHG_TRACKER, vt);
			continue;
		}

		struct route_table *dst_vrf_table = tracker_vrf_table_get(dst, vt->vrf_id);
		struct route_node *old_trn;

		for (old_trn = route_top(vt->table); old_trn; old_trn = route_next(old_trn)) {
			if (!old_trn->info)
				continue;

			struct route_node *trn = route_node_get(dst_vrf_table, &old_trn->p);

			if (!trn->info) {
				trn->info = old_trn->info;
			} else {
				route_unlock_node(trn);
				route_unlock_node(old_trn->info);
			}

			old_trn->info = NULL;
			route_unlock_node(old_trn);
		}

		route_table_finish(vt->table);
		XFREE(MTYPE_NHG_TRACKER, vt);
	}
	src->vrf_tables = NULL;
}

/*
 * Collapse a stale tracker into a target tracker.
 * Moves per-VRF table entries and re-points prefix_map entries from
 * old_tracker to new_tracker (all become unmatched), transfers counts,
 * then destroys old tracker.
 */
static void zebra_nhg_tracker_collapse(struct tracker_prefix_map_head *prefix_map,
				       struct nhg_event_tracker *old_tracker,
				       struct nhg_event_tracker *new_tracker)
{
	struct tracker_prefix_map_entry *entry;

	tracker_vrf_tables_move(&old_tracker->matched_table, &new_tracker->unmatched_table);
	tracker_vrf_tables_move(&old_tracker->unmatched_table, &new_tracker->unmatched_table);

	frr_each_safe (tracker_prefix_map, prefix_map, entry) {
		if (entry->tracker == old_tracker)
			entry->tracker = new_tracker;
	}

	new_tracker->unmatched_table.re_count += old_tracker->matched_table.re_count +
						 old_tracker->unmatched_table.re_count;
	old_tracker->matched_table.re_count = 0;
	old_tracker->unmatched_table.re_count = 0;

	zlog_info("%s: collapsed tracker %u into tracker %u for NHG %u (new unmatched=%u)",
		  __func__, old_tracker->nhg_tracker_id, new_tracker->nhg_tracker_id,
		  new_tracker->parent_nhe ? new_tracker->parent_nhe->id : 0,
		  new_tracker->unmatched_table.re_count);

	zebra_nhg_tracker_free(old_tracker->parent_nhe, old_tracker);
}

/*
 * Add a RIB route_node to a tracker table (matched or unmatched)
 * and update the prefix_map.
 * If the prefix is new, sets trn->info = rn and increments re_count.
 * If the prefix already exists, releases the get-lock (no re_count change).
 * Uses prefix_map to ensure each prefix is owned by exactly one tracker.
 */
void zebra_nhg_tracker_rn_add(struct nhg_tracker_table *tt, uint32_t *re_count,
			      struct tracker_prefix_map_head *prefix_map,
			      struct nhg_event_tracker *tracker, struct route_node *rn,
			      struct route_entry *re)
{
	struct route_table *vrf_table;
	struct route_node *trn;

	vrf_table = tracker_vrf_table_get(tt, re->vrf_id);
	trn = route_node_get(vrf_table, &rn->p);
	if (!trn->info) {
		trn->info = rn;
		route_lock_node(rn);
	} else {
		route_unlock_node(trn);
	}

	if (prefix_map) {
		struct tracker_prefix_map_entry lookup_key;
		struct tracker_prefix_map_entry *entry;

		memset(&lookup_key, 0, sizeof(lookup_key));
		prefix_copy(&lookup_key.p, &rn->p);
		lookup_key.type = re->type;
		lookup_key.instance = re->instance;
		lookup_key.vrf_id = re->vrf_id;

		entry = tracker_prefix_map_find(prefix_map, &lookup_key);
		if (!entry) {
			entry = XCALLOC(MTYPE_NHG_TRACKER_PREFIX_MAP, sizeof(*entry));
			prefix_copy(&entry->p, &rn->p);
			entry->type = re->type;
			entry->instance = re->instance;
			entry->vrf_id = re->vrf_id;
			entry->tracker = tracker;
			tracker_prefix_map_add(prefix_map, entry);
			(*re_count)++;
			zlog_info("%s: added %pRN (type %s vrf %s(%u)) to tracker %u, re_count=%u",
				  __func__, rn, zebra_route_string(re->type),
				  vrf_id_to_name(re->vrf_id), re->vrf_id, tracker->nhg_tracker_id,
				  *re_count);
		}
	}
}

/*
 * Check if the RN is already tracked by a different tracker via the
 * prefix_map.  If so, evict the stale entry and collapse the old tracker.
 * Then add the RN to the given tracker's table.
 */
static void zebra_nhg_tracker_add_route(struct tracker_prefix_map_head *prefix_map,
					struct nhg_event_tracker *tracker,
					struct nhg_tracker_table *tt, struct route_node *rn,
					struct route_entry *re)
{
	zebra_nhg_tracker_rn_add(tt, &tt->re_count, prefix_map, tracker, rn, re);
}

/*
 * Evict a parked RE (same protocol/instance as the incoming RE) from a
 * tracker table (matched or unmatched).
 * We must not unlock/deref the RN while another RE on the same RN is still
 * parked for this originating NHG (orig_nhe) on this tracker—each protocol
 * RE is one prefix_map row.  Example: RN1 has RE1 (proto1, NHG1) and RE2
 * (proto2, NHG1); evicting RE1 still leaves RE2 referencing the same RN.
 */
static void zebra_nhg_tracker_evict_re(struct nhg_event_tracker *tracker,
				       struct nhg_hash_entry *orig_nhe,
				       struct tracker_prefix_map_head *prefix_map,
				       struct nhg_tracker_table *tt, struct route_node *rn,
				       struct route_entry *re)
{
	struct tracker_prefix_map_entry lk;
	struct tracker_prefix_map_entry *pm_entry;
	struct route_table *vrf_table;
	struct route_node *trn;

	memset(&lk, 0, sizeof(lk));
	prefix_copy(&lk.p, &rn->p);
	lk.type = re->type;
	lk.instance = re->instance;
	lk.vrf_id = re->vrf_id;

	pm_entry = tracker_prefix_map_find(prefix_map, &lk);
	if (!pm_entry)
		return;

	if (pm_entry->tracker != tracker)
		return;

	vrf_table = tracker_vrf_table_get(tt, re->vrf_id);
	trn = route_node_lookup(vrf_table, &rn->p);
	/* Parking for this prefix is in only one of matched vs unmatched for this
	 * tracker VRF; skip so the sibling evict_from_* removes the map row and
	 * decrements the correct re_count.  route_node_lookup yields NULL unless
	 * this node has info (locked reference).
	 */
	if (!trn)
		return;

	UNSET_FLAG(re->status, ROUTE_ENTRY_TRACKER);

	tracker_prefix_map_del(prefix_map, pm_entry);
	XFREE(MTYPE_NHG_TRACKER_PREFIX_MAP, pm_entry);
	if (tt->re_count > 0)
		tt->re_count--;

	{
		bool others_remain = false;
		struct route_node *parked_rn = trn->info;
		struct route_entry *check_re;

		RNODE_FOREACH_RE (parked_rn, check_re) {
			struct tracker_prefix_map_entry chk;

			memset(&chk, 0, sizeof(chk));
			prefix_copy(&chk.p, &rn->p);
			chk.type = check_re->type;
			chk.instance = check_re->instance;
			chk.vrf_id = check_re->vrf_id;

			if (tracker_prefix_map_find(prefix_map, &chk)) {
				others_remain = true;
				break;
			}
		}

		if (!others_remain) {
			route_unlock_node(trn->info);
			trn->info = NULL;
		}
		route_unlock_node(trn);
	}
}

static void zebra_nhg_tracker_evict_from_unmatched(struct nhg_event_tracker *tracker,
						   struct nhg_hash_entry *orig_nhe,
						   struct tracker_prefix_map_head *prefix_map,
						   struct route_node *rn, struct route_entry *re)
{
	zebra_nhg_tracker_evict_re(tracker, orig_nhe, prefix_map, &tracker->unmatched_table, rn,
				   re);
}

static void zebra_nhg_tracker_evict_from_matched(struct nhg_event_tracker *tracker,
						 struct nhg_hash_entry *orig_nhe,
						 struct tracker_prefix_map_head *prefix_map,
						 struct route_node *rn, struct route_entry *re)
{
	zebra_nhg_tracker_evict_re(tracker, orig_nhe, prefix_map, &tracker->matched_table, rn, re);
}

/*
 * No tracker matched the incoming RE's NHG.  Park the RE in the newest
 * tracker's unmatched table.  Returns the tracker used, or NULL.
 */
static struct nhg_event_tracker *
zebra_nhg_tracker_park_unmatched(struct nhg_hash_entry *orig_nhe,
				 struct tracker_prefix_map_head *prefix_map, struct route_node *rn,
				 struct route_entry *re)
{
	struct nhg_event_tracker *tracker;

	tracker = nhg_event_tracker_list_first(&orig_nhe->tracker_list);
	if (!tracker)
		return NULL;

	zebra_nhg_tracker_add_route(prefix_map, tracker, &tracker->unmatched_table, rn, re);

	zlog_info("%s: %pRN (type %s) unmatched, parking in tracker %u for originating NHG %u (matched=%u unmatched=%u orig_re=%u)",
		  __func__, rn, zebra_route_string(re->type), tracker->nhg_tracker_id,
		  orig_nhe->id, tracker->matched_table.re_count, tracker->unmatched_table.re_count,
		  tracker->orig_re_count);

	return tracker;
}

/*
 * Collapse all trackers strictly older than keeper into keeper.
 * Their routes land in keeper's unmatched table.
 */
static void zebra_nhg_tracker_absorb_older(struct nhg_hash_entry *orig_nhe,
					   struct tracker_prefix_map_head *prefix_map,
					   struct nhg_event_tracker *keeper)
{
	struct nhg_event_tracker *t, *next_t;

	for (t = nhg_event_tracker_list_next(&orig_nhe->tracker_list, keeper); t; t = next_t) {
		next_t = nhg_event_tracker_list_next(&orig_nhe->tracker_list, t);
		zebra_nhg_tracker_collapse(prefix_map, t, keeper);
	}
}

/*
 * Insert the route into the tracker's matched table and log the event.
 * Tracker Truth Table for RE movement:
 * +---------------------+--------------------+--------------------+--------------------+----------------------+
 * | Transition          | matched->matched   | matched->unmatched | unmatched->matched | unmatched->unmatched |
 * +---------------------+--------------------+--------------------+--------------------+----------------------+
 * | within same tracker |        NA          | evict from same    | evict from same    |          NA          |
 * |                     |                    | tracker's matched, | tracker's          |                      |
 * |                     |                    | store in same      | unmatched, store   |                      |
 * |                     |                    | tracker's unmatched| in same tracker's  |                      |
 * |                     |                    |                    | matched            |                      |
 * +---------------------+--------------------+--------------------+--------------------+----------------------+
 * | old to new tracker  | collapse old       | evict from old     | collapse old       | evict from old       |
 * |                     | trackers into new, | matched, store in  | trackers into new, | unmatched, store in  |
 * |                     | evict from old     | new unmatched      | evict from old     | new unmatched        |
 * |                     | matched, store in  |                    | unmatched, store   |                      |
 * |                     | new matched        |                    | in new matched     |                      |
 * +---------------------+--------------------+--------------------+--------------------+----------------------+
 * | new to old tracker  | evict from new     |        NA          | evict from new     |          NA          |
 * |                     | matched, store in  |                    | unmatched, store   |                      |
 * |                     | old matched (new   |                    | in old matched     |                      |
 * |                     | tracker still      |                    | (new tracker still |                      |
 * |                     | alive)             |                    | alive)             |                      |
 * +---------------------+--------------------+--------------------+--------------------+----------------------+
 */
static void zebra_nhg_tracker_park_matched(struct nhg_hash_entry *orig_nhe,
					   struct tracker_prefix_map_head *prefix_map,
					   struct nhg_event_tracker *tracker,
					   struct route_node *rn, struct route_entry *re)
{
	zebra_nhg_tracker_add_route(prefix_map, tracker, &tracker->matched_table, rn, re);

	zlog_info("%s: %pRN (type %s) matched tracker %u from originating NHG %u (matched=%u unmatched=%u orig_re=%u)",
		  __func__, rn, zebra_route_string(re->type), tracker->nhg_tracker_id,
		  orig_nhe->id, tracker->matched_table.re_count, tracker->unmatched_table.re_count,
		  tracker->orig_re_count);
}

/*
 * Park an RE in the appropriate tracker instead of queuing it
 * for best-path selection.
 * orig_nhe	: the originating NHE, carries the trackers and prefix_map
 * re		: the incoming RE
 */
struct nhg_event_tracker *zebra_nhg_tracker_park_re(struct route_node *rn, struct route_entry *re,
						    struct nhg_hash_entry *orig_nhe)
{
	struct nhg_event_tracker *tracker, *keeper;
	struct nhg_event_tracker *evict_from;
	struct tracker_prefix_map_head *prefix_map = &orig_nhe->tracker_prefix_map;
	struct tracker_prefix_map_entry pm_key;
	struct tracker_prefix_map_entry *pm_re;
	struct nhg_event_tracker *newest_tracker;
	bool matched = false;

	memset(&pm_key, 0, sizeof(pm_key));
	prefix_copy(&pm_key.p, &rn->p);
	pm_key.type = re->type;
	pm_key.instance = re->instance;
	pm_key.vrf_id = re->vrf_id;
	pm_re = tracker_prefix_map_find(prefix_map, &pm_key);

	/*
	 * In general, a prefix is parked in at most one trackers matched table at any
	 * point in time.  Walk trackers (older to newest) to find one whose
	 * snapshot matches the incoming RE's NHG.
	 * Match: collapse all strictly older trackers into that keeper; their
	 * routes land in keeper's unmatched.
	 * No match for this RE's NHG: if the prefix_map still shows it parked
	 * in an older tracker (stale), zebra_nhg_tracker_add_route (below)
	 * evicts that tracker and moves the route to the newest tracker's
	 * unmatched, collapsing the stale tracker.
	 */
	frr_rev_each (nhg_event_tracker_list, &orig_nhe->tracker_list, tracker) {
		if (zebra_nhg_nexthop_compare(re->nhe->nhg.nexthop,
					      tracker->nhg_tracker_snapshot->nhg.nexthop, rn,
					      true)) {
			keeper = tracker;

			zebra_nhg_tracker_absorb_older(orig_nhe, prefix_map, keeper);

			/*
			 * Collapse has already repointed prefix_map entries from absorbed
			 * trackers to the keeper.  Get the latest owner from prefix_map
			 * and evict the RE from that tracker's unmatched/matched
			 * table (default to the keeper when no map row exists yet).
			 * This covers:
			 * - RE moved into this tracker's unmatched via collapse.
			 * - RE in a newer tracker's unmatched/matched while this older
			 *   tracker's NHG matches—evict there before parking here.
			 * - RE already in the same tracker's matched from a prior
			 *   iteration—evict so park_matched creates a fresh entry.
			 */
			evict_from = tracker;
			/* prefix_map may have changed during collapse; re-resolve owner. */
			pm_re = tracker_prefix_map_find(prefix_map, &pm_key);
			if (pm_re)
				evict_from = pm_re->tracker;

			zebra_nhg_tracker_evict_from_unmatched(evict_from, orig_nhe, prefix_map,
							       rn, re);
			zebra_nhg_tracker_evict_from_matched(evict_from, orig_nhe, prefix_map, rn,
							     re);

			zebra_nhg_tracker_park_matched(orig_nhe, prefix_map, tracker, rn, re);
			matched = true;
			break;
		}
	}

	if (!matched) {
		/*
		 * Unmatched REs are always parked in the newest tracker.  Evict the RE
		 * from the tracker that currently owns it (as per prefix_map) when that
		 * tracker's ID <= newest(covers matched->unmatched transitions from old->new
		 * and within-same-tracker).  The RE may sit in its unmatched or
		 * matched table.
		 */
		newest_tracker = nhg_event_tracker_list_first(&orig_nhe->tracker_list);
		if (pm_re && newest_tracker &&
		    pm_re->tracker->nhg_tracker_id <= newest_tracker->nhg_tracker_id) {
			zebra_nhg_tracker_evict_from_unmatched(pm_re->tracker, orig_nhe,
							       prefix_map, rn, re);
			zebra_nhg_tracker_evict_from_matched(pm_re->tracker, orig_nhe, prefix_map,
							     rn, re);
		}

		tracker = zebra_nhg_tracker_park_unmatched(orig_nhe, prefix_map, rn, re);
	}

	SET_FLAG(re->status, ROUTE_ENTRY_TRACKER);

	return tracker;
}

/*
 * Walk all per-VRF tables in a tracker table, clear TRACKER flags,
 * optionally update NHE for non-removed REs, and queue each RN for
 * rib_process.
 *
 * update_nhe: when true (matched table), restore each RE's NHE to the
 *   tracker's parent NHE so the kernel sees the same NHG ID.
 *   When false (unmatched table), leave the RE's NHE intact so
 *   rib_process resolves the RE with its original intended NHG
 *   (e.g. a new ECMP group).
 *
 * Currently unused — kept for potential future use.
 */
static void zebra_nhg_tracker_flush_table(struct nhg_tracker_table *tt, struct nhg_hash_entry *nhe,
					  bool update_nhe, const char *label)
	__attribute__((unused));
static void zebra_nhg_tracker_flush_table(struct nhg_tracker_table *tt, struct nhg_hash_entry *nhe,
					  bool update_nhe, const char *label)
{
	struct tracker_vrf_table *vt;

	for (vt = tt->vrf_tables; vt; vt = vt->next) {
		struct route_node *trn;

		for (trn = route_top(vt->table); trn; trn = route_next(trn)) {
			if (!trn->info)
				continue;

			struct route_node *rn = trn->info;
			struct route_entry *re;

			zlog_info("%s flushing %pRN vrf %s(%u)", label, rn,
				  vrf_id_to_name(vt->vrf_id), vt->vrf_id);

			RNODE_FOREACH_RE (rn, re) {
				if (!CHECK_FLAG(re->status, ROUTE_ENTRY_TRACKER))
					continue;

				UNSET_FLAG(re->status, ROUTE_ENTRY_TRACKER);
				if (update_nhe && !CHECK_FLAG(re->status, ROUTE_ENTRY_REMOVED))
					route_entry_update_nhe(re, nhe);
			}

			rib_queue_add(rn);
		}
	}
}

/*
 * Free a batch entry and its route_node list.
 */
static void tracker_batch_entry_free(struct tracker_batch_entry *entry)
{
	struct tracker_batch_rn *brn, *next;

	for (brn = entry->rn_list; brn; brn = next) {
		next = brn->next;
		XFREE(MTYPE_NHG_TRACKER, brn);
	}
	XFREE(MTYPE_NHG_TRACKER, entry);
}

static void tracker_batch_entry_list_free(struct tracker_batch_entry *list)
{
	struct tracker_batch_entry *entry, *next;

	for (entry = list; entry; entry = next) {
		next = entry->next;
		tracker_batch_entry_free(entry);
	}
}

/*
 * Free all batch state.
 */
static void tracker_batch_state_free(struct tracker_batch_state *bs)
{
	event_cancel(&bs->safety_timer);
	tracker_batch_entry_list_free(bs->phase1_list);
	if (bs->reuse_batch)
		tracker_batch_entry_free(bs->reuse_batch);
	XFREE(MTYPE_NHG_TRACKER, bs);
}

/*
 * Send one batch entry: install NHG (if needed) + queue all routes.
 * Increments bs->routes_pending for each tracker RE found.
 */
static void tracker_batch_send_entry(struct tracker_batch_state *bs,
				     struct tracker_batch_entry *batch)
{
	struct tracker_batch_rn *brn;

	zlog_info("%s: sending NHG %u (%u routes, update_nhe=%d) for parent NHG %u phase %u",
		  __func__, batch->nhg_id, batch->route_count, batch->update_nhe,
		  bs->parent_nhe ? bs->parent_nhe->id : 0, bs->phase);

	if (batch->nhe)
		zebra_nhg_install_kernel(batch->nhe, ZEBRA_ROUTE_MAX);

	for (brn = batch->rn_list; brn; brn = brn->next) {
		struct route_node *rn = brn->rn;
		struct route_entry *re;

		RNODE_FOREACH_RE (rn, re) {
			if (!CHECK_FLAG(re->status, ROUTE_ENTRY_TRACKER))
				continue;

			/*
			 * When filter_by_nhg_id is set, only claim REs
			 * whose NHG ID matches this batch.
			 * Otherwise, claim all remaining TRACKER REs.
			 */
			if (batch->filter_by_nhg_id && re->nhe && re->nhe->id != batch->nhg_id)
				continue;

			UNSET_FLAG(re->status, ROUTE_ENTRY_TRACKER);

			if (batch->update_nhe && !CHECK_FLAG(re->status, ROUTE_ENTRY_REMOVED))
				route_entry_update_nhe(re, bs->parent_nhe);

			re->batch_nhg_id = bs->parent_nhe->id;
			bs->routes_pending++;
		}

		rib_queue_add(rn);
	}
}

/*
 * Phase 2: handle the reuse group.
 *
 * The reuse group's routes are already in the kernel pointing to the
 * preserved NHG ID.  We just need to:
 *   1. If the winning group is unmatched: update the parent NHG's
 *      nexthop set to match the winning group, then send RTM_NEWNEXTHOP.
 *   2. If the winning group is matched: the parent NHG already has the
 *      right nexthops.  Send RTM_NEWNEXTHOP to confirm state.
 *   3. Clean up internal state on reuse REs (clear flags, update re->nhe).
 *   4. No routes sent to kernel — the NHG update is sufficient.
 */
static void tracker_batch_start_phase2(struct tracker_batch_state *bs)
{
	struct tracker_batch_entry *reuse;
	struct nhg_hash_entry *parent_nhe;
	struct tracker_batch_rn *brn;

	if (!bs->reuse_batch) {
		zlog_info("%s: no reuse batch, all done for parent NHG %u", __func__,
			  bs->parent_nhe ? bs->parent_nhe->id : 0);
		if (bs->parent_nhe)
			bs->parent_nhe->batch_state = NULL;
		tracker_batch_state_free(bs);
		return;
	}

	reuse = bs->reuse_batch;
	parent_nhe = bs->parent_nhe;
	bs->phase = 2;

	zlog_info("%s: starting phase 2 (reuse NHG %u, winning group NHG %u, %u routes) for parent NHG %u",
		  __func__, parent_nhe->id, reuse->nhg_id, reuse->route_count, parent_nhe->id);

	/*
	 * If the winning group is unmatched (its nexthops differ from
	 * the current parent NHG), update the parent NHG's nexthop set
	 * to match.
	 */
	if (reuse->nhe && reuse->nhe != parent_nhe && reuse->nhg_id != parent_nhe->id) {
		zlog_info("%s: updating parent NHG %u nexthops from winning group NHG %u",
			  __func__, parent_nhe->id, reuse->nhg_id);

		/*
		 * Remove from the nexthop-keyed hash before modifying,
		 * then re-insert after.  The hash key depends on the
		 * nexthop contents; modifying in-place would corrupt
		 * the hash table.
		 */
		hash_release(zrouter.nhgs, parent_nhe);

		nexthops_free(parent_nhe->nhg.nexthop);
		parent_nhe->nhg.nexthop = NULL;
		nexthop_group_copy(&parent_nhe->nhg, &reuse->nhe->nhg);

		(void)hash_get(zrouter.nhgs, parent_nhe, hash_alloc_intern);
	}

	/* Send RTM_NEWNEXTHOP to update the kernel */
	SET_FLAG(parent_nhe->flags, NEXTHOP_GROUP_REINSTALL);
	zebra_nhg_install_kernel(parent_nhe, ZEBRA_ROUTE_MAX);

	/*
	 * Clean up internal state on reuse REs.
	 * No routes are sent to the kernel — the NHG update is sufficient
	 * because these routes already reference the preserved NHG ID.
	 *
	 * When the reuse group is an unmatched group, only claim TRACKER
	 * REs whose NHG ID matches the reuse batch's original NHG ID.
	 * Other TRACKER REs on shared RIB RNs (e.g. from the matched
	 * table) must not be touched here.
	 * When the reuse group is the matched group, claim all remaining
	 * TRACKER REs.
	 */
	for (brn = reuse->rn_list; brn; brn = brn->next) {
		struct route_node *rn = brn->rn;
		struct route_entry *re;
		bool filter_by_nhg = (reuse->nhg_id != parent_nhe->id);

		RNODE_FOREACH_RE (rn, re) {
			if (!CHECK_FLAG(re->status, ROUTE_ENTRY_TRACKER))
				continue;

			if (filter_by_nhg && re->nhe && re->nhe->id != reuse->nhg_id)
				continue;

			UNSET_FLAG(re->status, ROUTE_ENTRY_TRACKER);
			UNSET_FLAG(re->status, ROUTE_ENTRY_CHANGED);

			if (!CHECK_FLAG(re->status, ROUTE_ENTRY_REMOVED))
				route_entry_update_nhe(re, parent_nhe);
		}
	}

	zlog_info("%s: phase 2 complete for parent NHG %u, all done", __func__, parent_nhe->id);

	parent_nhe->batch_state = NULL;
	tracker_batch_state_free(bs);
}

/*
 * Called when a route completes.
 * Decrements routes_pending. On reaching 0:
 *   phase 1 -> start phase 2
 *   phase 2 -> done, free batch state
 */
void tracker_batch_route_done(uint32_t parent_nhg_id)
{
	struct nhg_hash_entry *nhe;
	struct tracker_batch_state *bs;

	if (parent_nhg_id == 0)
		return;

	nhe = zebra_nhg_lookup_id(parent_nhg_id);
	if (!nhe || !nhe->batch_state)
		return;

	bs = nhe->batch_state;
	if (bs->routes_pending == 0)
		return;

	bs->routes_pending--;

	if (bs->routes_pending > 0)
		return;

	if (bs->phase == 1) {
		zlog_info("%s: phase 1 complete for parent NHG %u", __func__, nhe->id);
		tracker_batch_start_phase2(bs);
	} else {
		zlog_info("%s: phase 2 complete for parent NHG %u, all done", __func__, nhe->id);
		nhe->batch_state = NULL;
		tracker_batch_state_free(bs);
	}
}

/*
 * Called from process_subq_route after rib_process returns.
 * For batch routes not sent to dplane, decrement routes_pending.
 */
void tracker_batch_check_unsent(struct route_node *rn)
{
	rib_dest_t *dest = rib_dest_from_rnode(rn);
	struct route_entry *re;

	if (!dest)
		return;

	RNODE_FOREACH_RE (rn, re) {
		if (re->batch_nhg_id != 0 && !CHECK_FLAG(re->status, ROUTE_ENTRY_QUEUED)) {
			uint32_t nhg_id = re->batch_nhg_id;

			re->batch_nhg_id = 0;
			tracker_batch_route_done(nhg_id);
		}
	}
}

static void tracker_batch_safety_timer(struct event *event)
{
	struct tracker_batch_state *bs = EVENT_ARG(event);

	zlog_warn("%s: safety timer expired for parent NHG %u phase %u (pending=%u)", __func__,
		  bs->parent_nhe ? bs->parent_nhe->id : 0, bs->phase, bs->routes_pending);

	bs->routes_pending = 0;

	if (bs->phase == 1)
		tracker_batch_start_phase2(bs);
	else {
		if (bs->parent_nhe)
			bs->parent_nhe->batch_state = NULL;
		tracker_batch_state_free(bs);
	}
}

/*
 * Add a route_node to a batch entry if it has matching TRACKER-flagged REs.
 * filter_nhg_id: when non-zero, only count TRACKER REs whose re->nhe->id
 *   matches.  When zero, count all TRACKER REs.
 * Returns the number of matching tracker REs found on this RN.
 */
static uint32_t tracker_batch_collect_rn(struct tracker_batch_entry *entry, struct route_node *rn,
					 uint32_t filter_nhg_id)
{
	struct route_entry *re;
	uint32_t count = 0;

	RNODE_FOREACH_RE (rn, re) {
		if (!CHECK_FLAG(re->status, ROUTE_ENTRY_TRACKER))
			continue;
		if (filter_nhg_id != 0 && re->nhe && re->nhe->id != filter_nhg_id)
			continue;
		count++;
	}

	if (count > 0) {
		struct tracker_batch_rn *brn;

		brn = XCALLOC(MTYPE_NHG_TRACKER, sizeof(*brn));
		brn->rn = rn;
		brn->next = entry->rn_list;
		entry->rn_list = brn;
		entry->route_count += count;
	}

	return count;
}

/*
 * Build a single batch entry from a tracker table.
 * All TRACKER-flagged REs are collected into one batch regardless of NHG ID.
 */
static struct tracker_batch_entry *tracker_batch_build_single(struct nhg_tracker_table *tt,
							      uint32_t nhg_id,
							      struct nhg_hash_entry *nhe,
							      bool update_nhe)
{
	struct tracker_batch_entry *entry;
	struct tracker_vrf_table *vt;

	if (tt->re_count == 0)
		return NULL;

	entry = XCALLOC(MTYPE_NHG_TRACKER, sizeof(*entry));
	entry->nhg_id = nhg_id;
	entry->nhe = nhe;
	entry->update_nhe = update_nhe;

	for (vt = tt->vrf_tables; vt; vt = vt->next) {
		struct route_node *trn;

		for (trn = route_top(vt->table); trn; trn = route_next(trn)) {
			if (!trn->info)
				continue;
			tracker_batch_collect_rn(entry, trn->info, 0);
		}
	}

	if (entry->route_count == 0) {
		tracker_batch_entry_free(entry);
		return NULL;
	}

	return entry;
}

/*
 * Build batch entries from the unmatched table, grouped by re->nhe->id.
 * Returns a linked list of batch entries (one per unique NHG ID).
 * Each RN is added to the group matching its first TRACKER RE's NHG ID.
 */
static struct tracker_batch_entry *tracker_batch_build_unmatched_groups(struct nhg_tracker_table *tt)
{
	struct tracker_batch_entry *list = NULL;
	struct tracker_vrf_table *vt;

	if (tt->re_count == 0)
		return NULL;

	for (vt = tt->vrf_tables; vt; vt = vt->next) {
		struct route_node *trn;

		for (trn = route_top(vt->table); trn; trn = route_next(trn)) {
			struct route_node *rn;
			struct route_entry *re;
			struct tracker_batch_entry *group;
			uint32_t target_nhg_id;

			if (!trn->info)
				continue;

			rn = trn->info;

			/* Find the NHG ID from the first TRACKER RE */
			target_nhg_id = 0;
			RNODE_FOREACH_RE (rn, re) {
				if (CHECK_FLAG(re->status, ROUTE_ENTRY_TRACKER) && re->nhe) {
					target_nhg_id = re->nhe->id;
					break;
				}
			}
			if (target_nhg_id == 0)
				continue;

			/* Find or create the group for this NHG ID */
			for (group = list; group; group = group->next) {
				if (group->nhg_id == target_nhg_id)
					break;
			}
			if (!group) {
				group = XCALLOC(MTYPE_NHG_TRACKER, sizeof(*group));
				group->nhg_id = target_nhg_id;
				group->nhe = re->nhe;
				group->update_nhe = false;
				group->filter_by_nhg_id = true;
				group->next = list;
				list = group;
			}

			tracker_batch_collect_rn(group, rn, target_nhg_id);
		}
	}

	return list;
}

/* Update global tracker statistics and log the flush event. */
static void tracker_flush_update_counters(struct nhg_event_tracker *tracker,
					  struct nhg_hash_entry *nhe)
{
	struct tracker_flush_event *evt;

	zrouter.tracker_counters.tracker_full++;
	if (tracker->matched_table.re_count == tracker->orig_re_count)
		zrouter.tracker_counters.tracker_full_matched++;
	else if (tracker->unmatched_table.re_count == tracker->orig_re_count)
		zrouter.tracker_counters.tracker_full_unmatched++;
	else {
		zrouter.tracker_counters.tracker_full_combined++;
		if (tracker->matched_table.re_count > tracker->unmatched_table.re_count)
			zrouter.tracker_counters.tracker_full_combined_matched_gt++;
		else if (tracker->unmatched_table.re_count > tracker->matched_table.re_count)
			zrouter.tracker_counters.tracker_full_combined_unmatched_gt++;
	}

	evt = &zrouter.tracker_counters
		       .log[zrouter.tracker_counters.log_idx % TRACKER_FLUSH_LOG_SIZE];
	evt->nhg_id = nhe->id;
	evt->tracker_id = tracker->nhg_tracker_id;
	evt->matched = tracker->matched_table.re_count;
	evt->unmatched = tracker->unmatched_table.re_count;
	evt->orig_re_count = tracker->orig_re_count;
	zrouter.tracker_counters.log_idx++;
}

/*
 * Build matched and unmatched groups, then pick the biggest as the
 * reuse group (preserves the parent NHG ID).
 * Tie-break: matched group wins if tied.
 * On return, *reuse_out is the reuse batch (removed from its list),
 * *phase1_out is everything else, *matched_is_reuse_out indicates
 * whether the matched group won.
 */
static void tracker_flush_pick_reuse(struct nhg_event_tracker *tracker, struct nhg_hash_entry *nhe,
				     struct tracker_batch_entry **reuse_out,
				     struct tracker_batch_entry **phase1_out,
				     bool *matched_is_reuse_out)
{
	struct tracker_batch_entry *matched_batch;
	struct tracker_batch_entry *unmatched_groups;
	struct tracker_batch_entry *reuse = NULL;
	uint32_t max_count = 0;
	bool matched_is_reuse = false;

	matched_batch = tracker_batch_build_single(&tracker->matched_table, nhe->id, nhe, false);

	/*
	 * Override matched batch route_count with the accurate value
	 * maintained during parking.  tracker_batch_build_single may
	 * overcount because it sees ALL TRACKER REs on shared RIB RNs.
	 */
	if (matched_batch)
		matched_batch->route_count = tracker->matched_table.re_count;

	unmatched_groups = tracker_batch_build_unmatched_groups(&tracker->unmatched_table);

	/* Find the max route_count across all groups */
	if (matched_batch)
		max_count = matched_batch->route_count;

	{
		struct tracker_batch_entry *batch;

		for (batch = unmatched_groups; batch; batch = batch->next) {
			if (batch->route_count > max_count)
				max_count = batch->route_count;
		}
	}

	/* Pick the reuse group */
	if (matched_batch && matched_batch->route_count >= max_count) {
		reuse = matched_batch;
		reuse->update_nhe = true;
		matched_is_reuse = true;
	} else {
		struct tracker_batch_entry *batch, *prev = NULL;

		for (batch = unmatched_groups; batch; prev = batch, batch = batch->next) {
			if (batch->route_count == max_count) {
				reuse = batch;
				reuse->update_nhe = true;
				reuse->filter_by_nhg_id = false;
				if (prev)
					prev->next = batch->next;
				else
					unmatched_groups = batch->next;
				reuse->next = NULL;
				break;
			}
		}
	}

	/*
	 * Build phase 1 list: everything except the reuse group.
	 * Unmatched batches go first (they filter by NHG ID in send_entry).
	 * Matched batch goes last (it claims all remaining TRACKER REs).
	 */
	if (!matched_is_reuse && matched_batch) {
		if (unmatched_groups) {
			struct tracker_batch_entry *tail;

			for (tail = unmatched_groups; tail->next; tail = tail->next)
				;
			tail->next = matched_batch;
			matched_batch->next = NULL;
			*phase1_out = unmatched_groups;
		} else {
			*phase1_out = matched_batch;
		}
	} else {
		*phase1_out = unmatched_groups;
	}

	*reuse_out = reuse;
	*matched_is_reuse_out = matched_is_reuse;
}

/*
 * Allocate the two-phase batch state on the parent NHE and start processing.
 *
 * Phase 1: send all non-reuse groups at once (their routes go through
 *   rib_process for best-path selection and kernel install).
 *   A shared routes_pending counter tracks completion across all groups.
 * Phase 2: after phase 1 completes (routes_pending hits 0), handle the
 *   reuse group — update the preserved NHG's nexthops and clean up
 *   internal state.  No routes are sent to the kernel in phase 2.
 *
 * If phase1 is NULL, jumps directly to phase 2 (single-group case).
 */
static void tracker_flush_start_batches(struct nhg_hash_entry *nhe,
					struct tracker_batch_entry *phase1,
					struct tracker_batch_entry *reuse)
{
	struct tracker_batch_state *bs;

	/* Guard: if a batch is already in-flight, abort the old one */
	if (nhe->batch_state) {
		zlog_warn("%s: NHG %u already has batch state (phase %u, pending %u), aborting old batch",
			  __func__, nhe->id, nhe->batch_state->phase,
			  nhe->batch_state->routes_pending);
		nhe->batch_state->routes_pending = 0;
		tracker_batch_state_free(nhe->batch_state);
		nhe->batch_state = NULL;
	}

	bs = XCALLOC(MTYPE_NHG_TRACKER, sizeof(*bs));
	bs->phase1_list = phase1;
	bs->reuse_batch = reuse;
	bs->parent_nhe = nhe;
	bs->routes_pending = 0;
	nhe->batch_state = bs;

	event_add_timer(zrouter.master, tracker_batch_safety_timer, bs,
			NHG_TRACKER_DEFAULT_TIMEOUT_SEC, &bs->safety_timer);

	zlog_info("%s: NHG %u reuse group: NHG %u (%u routes), phase1 groups: %s", __func__,
		  nhe->id, reuse ? reuse->nhg_id : 0, reuse ? reuse->route_count : 0,
		  phase1 ? "yes" : "none");

	if (phase1) {
		struct tracker_batch_entry *batch;

		bs->phase = 1;
		for (batch = phase1; batch; batch = batch->next)
			tracker_batch_send_entry(bs, batch);

		if (bs->routes_pending == 0)
			tracker_batch_start_phase2(bs);
	} else {
		tracker_batch_start_phase2(bs);
	}
}

static void zebra_nhg_tracker_flush_full(struct nhg_event_tracker *tracker,
					 struct nhg_hash_entry *nhe)
{
	struct tracker_batch_entry *reuse = NULL;
	struct tracker_batch_entry *phase1 = NULL;
	bool matched_is_reuse = false;

	tracker_flush_update_counters(tracker, nhe);

	tracker_flush_pick_reuse(tracker, nhe, &reuse, &phase1, &matched_is_reuse);

	if (!phase1 && !reuse) {
		zebra_nhg_tracker_free(nhe, tracker);
		return;
	}

	/* Free the tracker (routes now owned by batch entries) */
	zebra_nhg_tracker_free(nhe, tracker);

	tracker_flush_start_batches(nhe, phase1, reuse);
}

/*
 * Check if all expected REs have been parked; if so, flush.
 */
void zebra_nhg_tracker_flush_if_full(struct nhg_event_tracker *tracker, struct nhg_hash_entry *nhe)
{
	if (!tracker)
		return;

	if ((tracker->matched_table.re_count + tracker->unmatched_table.re_count) !=
	    tracker->orig_re_count)
		return;

	zlog_info("flush_if_full tracker %u NHG %u (matched=%u unmatched=%u orig_re=%u)",
		  tracker->nhg_tracker_id, nhe->id, tracker->matched_table.re_count,
		  tracker->unmatched_table.re_count, tracker->orig_re_count);

	zebra_nhg_tracker_flush_full(tracker, nhe);
}

/* Timer callback - flush via the batch mechanism */
static void nhg_tracker_timer_expiry(struct event *event)
{
	struct nhg_event_tracker *tracker = EVENT_ARG(event);

	zrouter.tracker_counters.tracker_timer_expired++;

	struct nhg_hash_entry *nhe = tracker->parent_nhe;

	if (!nhe) {
		zlog_err("%s: tracker %u has NULL parent_nhe, freeing without flush", __func__,
			 tracker->nhg_tracker_id);
		return;
	}

	zlog_info("timer_expiry tracker %u NHG %u ifindex %u event %s (matched=%u unmatched=%u orig_re=%u)",
		  tracker->nhg_tracker_id, nhe->id, tracker->ifindex,
		  tracker->event == NHG_TRACKER_EVENT_INTF_UP ? "UP" : "DOWN",
		  tracker->matched_table.re_count, tracker->unmatched_table.re_count,
		  tracker->orig_re_count);

	zebra_nhg_tracker_flush_full(tracker, nhe);
}

/*
 * Initialise the tracker list and hash embedded in an nhg_hash_entry.
 */
void zebra_nhg_tracker_init(struct nhg_hash_entry *nhe)
{
	nhg_event_tracker_list_init(&nhe->tracker_list);
	nhg_event_tracker_hash_init(&nhe->tracker_hash);
	tracker_prefix_map_init(&nhe->tracker_prefix_map);
}

/*
 * Tear down all trackers for an NHE.
 */
void zebra_nhg_tracker_fini(struct nhg_hash_entry *nhe)
{
	struct nhg_event_tracker *t;

	while ((t = nhg_event_tracker_list_first(&nhe->tracker_list)) != NULL)
		zebra_nhg_tracker_free(nhe, t);

	nhg_event_tracker_hash_fini(&nhe->tracker_hash);

	{
		struct tracker_prefix_map_entry *entry;

		while ((entry = tracker_prefix_map_pop(&nhe->tracker_prefix_map)) != NULL)
			XFREE(MTYPE_NHG_TRACKER_PREFIX_MAP, entry);
	}
	tracker_prefix_map_fini(&nhe->tracker_prefix_map);
}

/*
 * Lookup an existing tracker whose snapshot matches the given NHG state.
 */
struct nhg_event_tracker *zebra_nhg_tracker_lookup(struct nhg_hash_entry *nhe,
						   struct nhg_hash_entry *snapshot)
{
	struct nhg_event_tracker key;

	memset(&key, 0, sizeof(key));
	key.nhg_tracker_snapshot = snapshot;

	return nhg_event_tracker_hash_find(&nhe->tracker_hash, &key);
}

/*
 * The new event produces an NHG state that matches an existing
 * tracker.  Reuse the matching tracker and collapse all other
 * trackers into it - other tracker's routes become unmatched in keeper
 */
static void zebra_nhg_tracker_loop_detection(struct nhg_hash_entry *nhe,
					     struct nhg_event_tracker *keeper)
{
	struct nhg_event_tracker *t, *next;
	struct tracker_prefix_map_head *prefix_map = &nhe->tracker_prefix_map;

	zrouter.tracker_counters.tracker_loop_detected++;

	for (t = nhg_event_tracker_list_first(&nhe->tracker_list); t; t = next) {
		next = nhg_event_tracker_list_next(&nhe->tracker_list, t);

		if (t == keeper)
			continue;

		zlog_info("%s: NHG %u loop: collapsing old tracker %u (matched=%u unmatched=%u) into keeper %u (matched=%u unmatched=%u)",
			  __func__, nhe->id, t->nhg_tracker_id, t->matched_table.re_count,
			  t->unmatched_table.re_count, keeper->nhg_tracker_id,
			  keeper->matched_table.re_count, keeper->unmatched_table.re_count);

		zebra_nhg_tracker_collapse(prefix_map, t, keeper);
	}
}

/*
 * Count unique (prefix, type, instance, vrf_id) tuples in the NHE's
 * re-tree.  Only installed unicast REs are counted, so that orig_re_count
 * matches what the tracker will actually receive during parking.
 */
static uint32_t tracker_count_unique_res(struct nhe_re_tree_head *head)
{
	struct route_entry *re;
	struct tracker_prefix_map_head tmp = {};
	uint32_t count = 0;

	tracker_prefix_map_init(&tmp);

	frr_each (nhe_re_tree, head, re) {
		struct tracker_prefix_map_entry key;

		/*
		 * Multicast REs are excluded because only unicast routes are
		 * parked (the tracker's prefix-based dedup cannot handle
		 * cross-SAFI route_nodes; e.g. connected routes on eth1 exist
		 * in both unicast and multicast tables with different RNs but
		 * the same prefix).
		 */
		if (!re->rn || rib_table_info(re->rn->table)->safi != SAFI_UNICAST)
			continue;

		/*
		 * Non-installed REs are excluded because rib_link only parks
		 * an incoming RE when old_re is INSTALLED, and non-installed
		 * REs (e.g. an ospf route losing to a connected route for
		 * the same prefix) will never arrive through the tracker
		 * path.  Counting them would inflate orig_re_count,
		 * preventing flush_if_full.
		 */
		if (!CHECK_FLAG(re->status, ROUTE_ENTRY_INSTALLED))
			continue;

		memset(&key, 0, sizeof(key));
		prefix_copy(&key.p, &re->rn->p);
		key.type = re->type;
		key.instance = re->instance;
		key.vrf_id = re->vrf_id;

		if (!tracker_prefix_map_find(&tmp, &key)) {
			struct tracker_prefix_map_entry *entry;

			entry = XCALLOC(MTYPE_NHG_TRACKER_PREFIX_MAP, sizeof(*entry));
			*entry = key;
			tracker_prefix_map_add(&tmp, entry);
			count++;
		}
	}

	while (tracker_prefix_map_count(&tmp)) {
		struct tracker_prefix_map_entry *e = tracker_prefix_map_pop(&tmp);

		XFREE(MTYPE_NHG_TRACKER_PREFIX_MAP, e);
	}
	tracker_prefix_map_fini(&tmp);

	return count;
}

/*
 * Create a new tracker upon interface event.
 */
struct nhg_event_tracker *zebra_nhg_tracker_create(struct nhg_hash_entry *nhe, ifindex_t ifindex,
						   enum nhg_tracker_event_intf event)
{
	struct nhg_event_tracker *existing;
	struct nhg_event_tracker *tracker;
	struct nhg_event_tracker *head;
	struct nhg_event_tracker *oldest;
	struct nhg_hash_entry *snapshot;
	unsigned long inherit_secs;
	uint32_t unique_re_count;

	/*
	 * Only count installed unicast REs — these are the ones that will
	 * actually arrive through the tracker path.  Skip tracker creation
	 * when the count is zero.
	 */
	unique_re_count = tracker_count_unique_res(&nhe->re_head);
	if (unique_re_count == 0)
		return NULL;

	snapshot = zebra_nhe_copy(nhe, nhe->id);

	existing = zebra_nhg_tracker_lookup(nhe, snapshot);
	if (existing) {
		zebra_nhg_free(snapshot);
		zlog_info("%s: already existing tracker found for NHG %u, reusing tracker %u",
			  __func__, nhe->id, existing->nhg_tracker_id);
		zebra_nhg_tracker_loop_detection(nhe, existing);
		return existing;
	}

	tracker = XCALLOC(MTYPE_NHG_TRACKER, sizeof(*tracker));

	head = nhg_event_tracker_list_first(&nhe->tracker_list);
	tracker->nhg_tracker_id = head ? head->nhg_tracker_id + 1 : 1;

	tracker->parent_nhe = nhe;
	tracker->nhg_tracker_snapshot = snapshot;
	tracker->ifindex = ifindex;
	tracker->event = event;
	tracker->orig_re_count = unique_re_count;

	tracker->matched_table.vrf_tables = NULL;
	tracker->matched_table.re_count = 0;

	tracker->unmatched_table.vrf_tables = NULL;
	tracker->unmatched_table.re_count = 0;

	/*
	 * Inherit the oldest existing tracker's remaining timer so that
	 * back-to-back interface events don't keep pushing the expiry out
	 * indefinitely.  Capture it before collapsing older trackers.
	 */
	inherit_secs = zrouter.nhg_tracker_timeout;
	oldest = nhg_event_tracker_list_last(&nhe->tracker_list);
	if (oldest && event_is_scheduled(oldest->timer)) {
		unsigned long remain = event_timer_remain_second(oldest->timer);

		if (remain > 0)
			inherit_secs = remain;
	}

	nhg_event_tracker_list_add_head(&nhe->tracker_list, tracker);
	nhg_event_tracker_hash_add(&nhe->tracker_hash, tracker);

	/*
	 * Collapse all older trackers into this one: their matched and
	 * unmatched routes move into new tracker's unmatched table, and
	 * prefix_map entries are repointed.
	 */
	if (nhg_event_tracker_list_count(&nhe->tracker_list) > 1) {
		zebra_nhg_tracker_absorb_older(nhe, &nhe->tracker_prefix_map, tracker);
	}

	event_add_timer(zrouter.master, nhg_tracker_timer_expiry, tracker, inherit_secs,
			&tracker->timer);

	zrouter.tracker_counters.trackers_allocated++;

	zlog_info("%s: NHG %u created tracker %u (event=%s ifindex=%u timer=%lus) total trackers=%zu",
		  __func__, nhe->id, tracker->nhg_tracker_id,
		  event == NHG_TRACKER_EVENT_INTF_UP ? "UP" : "DOWN", ifindex, inherit_secs,
		  nhg_event_tracker_list_count(&nhe->tracker_list));

	return tracker;
}

/*
 * Create or update a tracker when multiple singletons on the same
 * interface affect the same NHG.  If a tracker already exists
 * for this ifindex+event with 0 routes, update its snapshot in-place.
 */
struct nhg_event_tracker *zebra_nhg_tracker_create_or_update(struct nhg_hash_entry *nhe,
							     ifindex_t ifindex,
							     enum nhg_tracker_event_intf event)
{
	struct nhg_event_tracker *existing;
	struct nhg_hash_entry *snapshot;

	frr_each (nhg_event_tracker_list, &nhe->tracker_list, existing) {
		if (existing->ifindex == ifindex && existing->event == event &&
		    existing->matched_table.re_count == 0 &&
		    existing->unmatched_table.re_count == 0) {
			snapshot = zebra_nhe_copy(nhe, nhe->id);

			nhg_event_tracker_hash_del(&nhe->tracker_hash, existing);

			zebra_nhg_free(existing->nhg_tracker_snapshot);
			existing->nhg_tracker_snapshot = snapshot;

			nhg_event_tracker_hash_add(&nhe->tracker_hash, existing);

			zlog_info("%s: NHG %u updated tracker %u snapshot (event=%s ifindex=%u)",
				  __func__, nhe->id, existing->nhg_tracker_id,
				  event == NHG_TRACKER_EVENT_INTF_UP ? "UP" : "DOWN", ifindex);
			return existing;
		}
	}

	return zebra_nhg_tracker_create(nhe, ifindex, event);
}

/*
 * Cleanup a tracker
 */
void zebra_nhg_tracker_free(struct nhg_hash_entry *nhe, struct nhg_event_tracker *tracker)
{
	struct tracker_prefix_map_entry *entry;

	zrouter.tracker_counters.trackers_freed++;

	nhg_event_tracker_hash_del(&nhe->tracker_hash, tracker);
	nhg_event_tracker_list_del(&nhe->tracker_list, tracker);

	if (nhg_event_tracker_list_count(&nhe->tracker_list) == 0)
		zlog_info("%s: NHG %u last tracker %u freed, no active trackers remain", __func__,
			  nhe->id, tracker->nhg_tracker_id);

	event_cancel(&tracker->timer);

	/* Clean up prefix_map entries pointing to this tracker */
	frr_each_safe (tracker_prefix_map, &nhe->tracker_prefix_map, entry) {
		if (entry->tracker == tracker) {
			tracker_prefix_map_del(&nhe->tracker_prefix_map, entry);
			XFREE(MTYPE_NHG_TRACKER_PREFIX_MAP, entry);
		}
	}

	/* Free per-VRF tables (unlocks RIB RNs stored in trn->info) */
	tracker_vrf_tables_free(&tracker->matched_table);
	tracker_vrf_tables_free(&tracker->unmatched_table);

	if (tracker->nhg_tracker_snapshot) {
		zebra_nhg_free(tracker->nhg_tracker_snapshot);
		tracker->nhg_tracker_snapshot = NULL;
	}

	tracker->parent_nhe = NULL;

	XFREE(MTYPE_NHG_TRACKER, tracker);
}

static void zebra_nhg_tracker_sweep_entry(struct hash_bucket *bucket, void *arg)
{
	struct nhg_hash_entry *nhe = bucket->data;

	if (nhg_event_tracker_list_count(&nhe->tracker_list) > 0)
		zebra_nhg_tracker_fini(nhe);
}

/*
 * Release all tracker-held locks on RIB route_nodes before table teardown.
 * Called during shutdown, before any route_table_free runs, so that trackers
 * do not hold dangling references to RIB nodes whose lock has been zeroed
 * by route_table_free.
 */
void zebra_nhg_tracker_sweep_all(void)
{
	hash_iterate(zrouter.nhgs_id, zebra_nhg_tracker_sweep_entry, NULL);
}
