from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

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
    covered_names: Tuple[str, ...]
    uncovered_names: Tuple[str, ...]
    target_count: int


def _plan_sort_key(p: FarmPlan):
    return (p.dungeon_name, p.base_pick, p.lock.kind, p.lock.value)


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
        return MultiPlanResult(plans=(), display_plans=(), covered_names=(), uncovered_names=(), target_count=0)

    candidates = build_candidate_plans_for_targets(dungeons, filtered_targets, base_universe)
    dungeon_by_name = {d.name: d for d in dungeons}
    target_set = set(target_names)
    other_counts: List[int] = []
    all_sets: List[Tuple[str, ...]] = []
    for p in candidates:
        dungeon = dungeon_by_name.get(p.dungeon_name)
        if dungeon is None:
            other_counts.append(0)
            all_sets.append(())
            continue
        all_matched = match_weapons_for_plan(dungeon, weapons, p)
        other_names = tuple(n for n in all_matched if n not in target_set)
        other_counts.append(len(other_names))
        all_sets.append(all_matched)

    selected, uncovered, display_plans = greedy_select_plans(
        candidates,
        target_names,
        other_counts,
        all_sets,
    )

    covered = [n for n in target_names if n not in uncovered]
    return MultiPlanResult(
        plans=tuple(selected),
        display_plans=tuple(display_plans),
        covered_names=tuple(covered),
        uncovered_names=tuple(sorted(uncovered)),
        target_count=len(target_names),
    )
