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
) -> Tuple[List[FarmPlan], Set[str]]:
    """
    贪心覆盖：每步选择“新增覆盖最多目标武器”的刷法；
    覆盖相同则优先使用已出现的副本，以减少副本数量；
    仍相同时优先选择“可覆盖更多其他武器”的刷法。
    """
    if not candidates:
        return [], set(target_names)

    uncovered: Set[str] = set(target_names)
    selected: List[FarmPlan] = []
    used_dungeons: Set[str] = set()

    coverages: List[Set[str]] = [set(p.matched_weapon_names) for p in candidates]

    while uncovered:
        best_idx: Optional[int] = None
        best_score: Optional[Tuple[int, int, int, Tuple]] = None
        best_new: Set[str] = set()

        for i, p in enumerate(candidates):
            new = coverages[i] & uncovered
            if not new:
                continue
            introduces = 0 if p.dungeon_name in used_dungeons else 1
            score = (
                len(new),
                -introduces,
                other_counts[i],
                _plan_sort_key(p),
            )
            if best_score is None or score > best_score:
                best_score = score
                best_idx = i
                best_new = new

        if best_idx is None:
            break

        chosen = candidates[best_idx]
        selected.append(chosen)
        used_dungeons.add(chosen.dungeon_name)
        uncovered -= best_new

    return selected, uncovered


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
        return MultiPlanResult(plans=(), covered_names=(), uncovered_names=(), target_count=0)

    candidates = build_candidate_plans_for_targets(dungeons, filtered_targets, base_universe)
    dungeon_by_name = {d.name: d for d in dungeons}
    target_set = set(target_names)
    other_counts: List[int] = []
    for p in candidates:
        dungeon = dungeon_by_name.get(p.dungeon_name)
        if dungeon is None:
            other_counts.append(0)
            continue
        all_matched = match_weapons_for_plan(dungeon, weapons, p)
        other_counts.append(len([n for n in all_matched if n not in target_set]))

    selected, uncovered = greedy_select_plans(candidates, target_names, other_counts)

    covered = [n for n in target_names if n not in uncovered]
    return MultiPlanResult(
        plans=tuple(selected),
        covered_names=tuple(covered),
        uncovered_names=tuple(sorted(uncovered)),
        target_count=len(target_names),
    )
