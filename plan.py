from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from data_loader import Dungeon, Weapon
from matcher import (
    LockChoice,
    FarmPlan,
    attr_label,
    gen_base_picks,
    match_weapon_under_plan,
    sort_weapon_names_by_rarity,
)


@dataclass(frozen=True)
class MultiPlanResult:
    plans: Tuple[FarmPlan, ...]
    display_plans: Tuple[FarmPlan, ...]
    strategies: Tuple["Strategy", ...]
    covered_names: Tuple[str, ...]
    uncovered_names: Tuple[str, ...]
    target_count: int


@dataclass(frozen=True)
class StrategyGroup:
    target_names: Tuple[str, ...]
    plans: Tuple[FarmPlan, ...]


@dataclass(frozen=True)
class Strategy:
    groups: Tuple[StrategyGroup, ...]


def _plan_sort_key(p: FarmPlan):
    return (p.dungeon_name, p.base_pick, p.lock.kind, p.lock.value)


def _group_sort_key(names: Iterable[str]) -> Tuple[int, Tuple[str, ...]]:
    ordered = tuple(sorted(names))
    return (-len(ordered), ordered)


def _partition_min_groups(
    targets: Sequence[str],
    groups: Sequence[frozenset[str]],
) -> List[Tuple[frozenset[str], ...]]:
    if not targets:
        return []

    target_set = set(targets)
    group_list = [g for g in groups if g.issubset(target_set)]
    group_list.sort(key=lambda g: (-len(g), tuple(sorted(g))))

    by_target: Dict[str, List[frozenset[str]]] = {t: [] for t in target_set}
    for g in group_list:
        for t in g:
            by_target[t].append(g)

    best_len = None
    results: List[Tuple[frozenset[str], ...]] = []

    def backtrack(remaining: Set[str], current: List[frozenset[str]]):
        nonlocal best_len, results
        if not remaining:
            if best_len is None or len(current) < best_len:
                best_len = len(current)
                results = [tuple(current)]
            elif len(current) == best_len:
                results.append(tuple(current))
            return

        if best_len is not None and len(current) >= best_len:
            return

        t = next(iter(sorted(remaining)))
        for g in by_target.get(t, []):
            if not g.issubset(remaining):
                continue
            current.append(g)
            backtrack(remaining - g, current)
            current.pop()

    backtrack(set(targets), [])
    return results


def build_candidate_plans_for_targets(
    dungeons: Sequence[Dungeon],
    targets: Sequence[Weapon],
    base_universe: Sequence[str],
) -> List[FarmPlan]:
    """
    为目标武器集生成所有可行刷法候选（只保留能覆盖至少一把目标武器的刷法）。
    """
    base_picks = gen_base_picks(base_universe)
    if not base_picks:
        return []

    weapon_by_name: Dict[str, Weapon] = {w.name: w for w in targets}

    candidates: List[FarmPlan] = []
    for d in dungeons:
        locks: List[LockChoice] = (
            [LockChoice("add", a, attr_label(a)) for a in sorted(d.add_set)]
            + [LockChoice("skill", s, attr_label(s)) for s in sorted(d.skill_set)]
        )

        for bp in base_picks:
            bp_set = set(bp)
            for lk in locks:
                matched: List[str] = []
                for w in targets:
                    if match_weapon_under_plan(d, w, bp_set, lk):
                        matched.append(w.name)
                if matched:
                    matched_sorted = sort_weapon_names_by_rarity(matched, weapon_by_name)
                    candidates.append(
                        FarmPlan(
                            dungeon_name=d.name,
                            base_pick=bp,
                            lock=lk,
                            matched_weapon_names=matched_sorted,
                            matched_count=len(matched_sorted),
                        )
                    )

    candidates.sort(key=_plan_sort_key)
    return candidates


def match_weapons_for_plan(dungeon: Dungeon, weapons: Sequence[Weapon], plan: FarmPlan) -> Tuple[str, ...]:
    """
    返回该刷法在指定副本下可覆盖的全部武器名（按稀有度排序）。
    """
    weapon_by_name: Dict[str, Weapon] = {w.name: w for w in weapons}
    bp_set = set(plan.base_pick)
    matched = [
        w.name for w in weapons
        if match_weapon_under_plan(dungeon, w, bp_set, plan.lock)
    ]
    return sort_weapon_names_by_rarity(matched, weapon_by_name)


def greedy_select_plans(
    candidates: Sequence[FarmPlan],
    target_names: Sequence[str],
    other_counts: Sequence[int],
    all_sets: Sequence[Tuple[str, ...]],
) -> Tuple[List[FarmPlan], Set[str], List[FarmPlan]]:
    """
    贪心覆盖：每步选择“新增覆盖最多目标武器”的刷法；
    覆盖相同则优先选择“可覆盖更多其他武器”的刷法。
    """
    if not candidates:
        return [], set(target_names), []

    uncovered: Set[str] = set(target_names)
    selected: List[FarmPlan] = []

    coverages: List[Set[str]] = [set(p.matched_weapon_names) for p in candidates]
    display_plans: List[FarmPlan] = []
    display_keys: Set[Tuple[str, frozenset[str]]] = set()

    while uncovered:
        best_idx: Optional[int] = None
        best_score: Optional[Tuple[Tuple[int, int, int], Tuple]] = None
        best_tie_key: Optional[Tuple[int, int]] = None
        best_new: Set[str] = set()

        for i, p in enumerate(candidates):
            new = coverages[i] & uncovered
            if not new:
                continue
            score_key = (len(new), other_counts[i])
            score = (score_key, _plan_sort_key(p))
            if best_score is None or score > best_score:
                best_score = score
                best_tie_key = (len(new), other_counts[i])
                best_idx = i
                best_new = new

        if best_idx is None:
            break

        tied_indices: List[int] = []
        for i, p in enumerate(candidates):
            new = coverages[i] & uncovered
            if not new:
                continue
            tie_key = (len(new), other_counts[i])
            if tie_key == best_tie_key:
                tied_indices.append(i)

        for i in tied_indices:
            p = candidates[i]
            key = (p.dungeon_name, frozenset(all_sets[i]))
            if key in display_keys:
                continue
            display_keys.add(key)
            display_plans.append(p)

        chosen = candidates[best_idx]
        selected.append(chosen)
        uncovered -= best_new

    return selected, uncovered, display_plans


def plan_multi_weapons(
    dungeons: Sequence[Dungeon],
    weapons: Sequence[Weapon],
    targets: Sequence[Weapon],
    base_universe: Sequence[str],
    rarity_filter: Optional[Set[str]] = None,
) -> MultiPlanResult:
    """
    多武器规划：在全副本范围内，使用尽可能少的刷法覆盖尽量多的目标武器。
    """
    if rarity_filter is None:
        filtered_targets = list(targets)
    else:
        filtered_targets = [w for w in targets if w.rarity in rarity_filter]

    target_names = [w.name for w in filtered_targets]
    if not target_names:
        return MultiPlanResult(
            plans=(),
            display_plans=(),
            strategies=(),
            covered_names=(),
            uncovered_names=(),
            target_count=0,
        )

    candidates = build_candidate_plans_for_targets(dungeons, filtered_targets, base_universe)
    target_set = set(target_names)
    dungeon_by_name = {d.name: d for d in dungeons}
    plan_meta: Dict[Tuple[str, Tuple[str, str, str], str, str], Tuple[Tuple[str, ...], int]] = {}
    for p in candidates:
        dungeon = dungeon_by_name.get(p.dungeon_name)
        if dungeon is None:
            continue
        all_matched = match_weapons_for_plan(dungeon, weapons, p)
        other_count = len([n for n in all_matched if n not in target_set])
        plan_meta[(p.dungeon_name, p.base_pick, p.lock.kind, p.lock.value)] = (all_matched, other_count)

    plans_by_group: Dict[frozenset[str], List[FarmPlan]] = {}
    for p in candidates:
        group = frozenset(p.matched_weapon_names)
        if not group:
            continue
        plans_by_group.setdefault(group, []).append(p)

    coverable_targets = set().union(*plans_by_group.keys()) if plans_by_group else set()
    uncovered = sorted(set(target_names) - coverable_targets)
    covered = [n for n in target_names if n in coverable_targets]

    strategies: List[Strategy] = []
    if coverable_targets:
        partitions = _partition_min_groups(covered, list(plans_by_group.keys()))
        for part in partitions:
            groups: List[StrategyGroup] = []
            for group in sorted(part, key=lambda g: _group_sort_key(g)):
                plans = plans_by_group.get(group, [])
                # Dedupe: same dungeon + same full coverage result -> keep one plan
                deduped: Dict[Tuple[str, frozenset[str]], FarmPlan] = {}
                for p in plans:
                    meta = plan_meta.get((p.dungeon_name, p.base_pick, p.lock.kind, p.lock.value))
                    if meta is None:
                        continue
                    all_matched, _ = meta
                    key = (p.dungeon_name, frozenset(all_matched))
                    if key not in deduped:
                        deduped[key] = p
                    else:
                        if _plan_sort_key(p) < _plan_sort_key(deduped[key]):
                            deduped[key] = p
                plans = list(deduped.values())

                # Dedupe: remove plans whose "other weapons" is a strict subset of another plan
                plan_other_sets: List[Tuple[FarmPlan, frozenset[str]]] = []
                for p in plans:
                    meta = plan_meta.get((p.dungeon_name, p.base_pick, p.lock.kind, p.lock.value))
                    if meta is None:
                        continue
                    all_matched, _ = meta
                    other_set = frozenset(set(all_matched) - target_set)
                    plan_other_sets.append((p, other_set))

                keep: List[FarmPlan] = []
                for i, (p, other_set) in enumerate(plan_other_sets):
                    is_subset = False
                    for j, (_, other_other) in enumerate(plan_other_sets):
                        if i == j:
                            continue
                        if other_set < other_other:
                            is_subset = True
                            break
                    if not is_subset:
                        keep.append(p)
                plans = keep
                plans_sorted = sorted(
                    plans,
                    key=lambda p: (
                        -plan_meta.get((p.dungeon_name, p.base_pick, p.lock.kind, p.lock.value), ((), 0))[1],
                        _plan_sort_key(p),
                    ),
                )
                groups.append(
                    StrategyGroup(
                        target_names=tuple(sorted(group)),
                        plans=tuple(plans_sorted),
                    )
                )
            strategies.append(Strategy(groups=tuple(groups)))

    return MultiPlanResult(
        plans=(),
        display_plans=(),
        strategies=tuple(strategies),
        covered_names=tuple(covered),
        uncovered_names=tuple(uncovered),
        target_count=len(target_names),
    )
