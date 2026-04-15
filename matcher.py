from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from data_loader import Dungeon, Weapon
from config import *


def attr_label(ch: str) -> str:
    return ATTR_FULLNAME.get(ch, ch)  # 没有映射就退回单字


def base_label(ch: str) -> str:
    return BASE_FULLNAME.get(ch, ch)


def add_label(ch: str) -> str:
    return ADD_FULLNAME.get(ch, ch)


def skill_label(ch: str) -> str:
    return SKILL_FULLNAME.get(ch, ch)


def sort_weapon_names_by_rarity(
    names: Iterable[str],
    weapon_by_name: Dict[str, Weapon],
) -> Tuple[str, ...]:
    """
    将武器名列表按 (品质, 名称) 排序；未知品质排最后；未知武器名排最后。
    """
    def key(n: str):
        w = weapon_by_name.get(n)
        if w is None:
            return (999, n)
        return (RARITY_RANK.get(w.rarity, 999), w.name)

    # 去重并排序
    unique = set(names)
    return tuple(sorted(unique, key=key))


@dataclass(frozen=True)
class LockChoice:
    kind: str   # "add" or "skill"
    value: str  # single char （e.g. “攻”
    label: str  # full name (e.g. "攻击提升")


@dataclass(frozen=True)
class FarmPlan:
    dungeon_name: str
    base_pick: Tuple[str, str, str]   # 3 chars sorted
    lock: LockChoice
    matched_weapon_names: Tuple[str, ...]  # matched weapons (names)
    matched_count: int


def can_drop_exact(d: Dungeon, w: Weapon) -> bool:
    """是否存在某种选择，使该副本可能掉落完全匹配 w(base,add,skill)。"""
    return (w.add in d.add_set) and (w.skill in d.skill_set)


def match_weapon_under_plan(d: Dungeon, w: Weapon, base_pick: Set[str], lock: LockChoice) -> bool:
    """在指定刷法(base_pick + lock)下，该武器是否可能被完全匹配掉落。"""
    if w.base not in base_pick:
        return False

    if lock.kind == "add":
        # 附加锁定为 lock.value，技能从 d.skill_set 等概率抽
        if w.add != lock.value:
            return False
        return w.skill in d.skill_set

    if lock.kind == "skill":
        # 技能锁定为 lock.value，附加从 d.add_set 等概率抽
        if w.skill != lock.value:
            return False
        return w.add in d.add_set

    raise ValueError(f"未知 lock.kind: {lock.kind}")


def enumerate_base_universe(weapons: Sequence[Weapon]) -> List[str]:
    """基础属性全集（从武器表提取）。"""
    bases = sorted({w.base for w in weapons})
    return bases


def gen_base_picks(base_universe: Sequence[str]) -> List[Tuple[str, str, str]]:
    """所有3选基础组合（排序后元组）。"""
    if len(base_universe) < 3:
        # 允许少于3种：此时只能用已有种类补齐会不符合规则，这里直接返回空
        return []
    return [tuple(sorted(c)) for c in combinations(base_universe, 3)]


def score_plans_for_dungeon(
    d: Dungeon,
    weapons: Sequence[Weapon],
    base_universe: Sequence[str],
    top_n: int = 10,
    rarity_filter: Optional[Set[str]] = None,
) -> List[FarmPlan]:
    """枚举该副本所有(basePick, lock)并按覆盖武器数排序，返回Top-N。"""
    base_picks = gen_base_picks(base_universe)

    # 枚举锁定项：副本自带8种附加/技能
    locks: List[LockChoice] = (
        [LockChoice("add", a, attr_label(a)) for a in sorted(d.add_set)]
        + [LockChoice("skill", s, attr_label(s)) for s in sorted(d.skill_set)]
    )

    plans: List[FarmPlan] = []
    weapon_by_name: Dict[str, Weapon] = {w.name: w for w in weapons}
    for bp in base_picks:
        bp_set = set(bp)
        for lk in locks:
            matched: List[str] = []
            for w in weapons:
                if rarity_filter is not None and w.rarity not in rarity_filter:
                    continue
                if match_weapon_under_plan(d, w, bp_set, lk):
                    matched.append(w.name)
            if matched:
                matched_sorted = sort_weapon_names_by_rarity(matched, weapon_by_name)
                plans.append(
                    FarmPlan(
                        dungeon_name=d.name,
                        base_pick=bp,
                        lock=lk,
                        matched_weapon_names=matched_sorted,
                        matched_count=len(matched_sorted),
                    )
                )

    # 按覆盖数降序，再按 dungeon/base/lock 稳定排序
    plans.sort(key=lambda p: (-p.matched_count, p.dungeon_name, p.base_pick, p.lock.kind, p.lock.value))

    return dedupe_by_coverage(plans, top_n)


def dedupe_by_coverage(plans: Sequence[FarmPlan], top_n: int) -> List[FarmPlan]:
    """按“覆盖集合”去重，并移除严格子集覆盖。"""
    unique_plans: List[FarmPlan] = []
    coverages: List[frozenset[str]] = []
    seen: Set[frozenset[str]] = set()
    for p in plans:
        coverage = frozenset(p.matched_weapon_names)
        if coverage in seen:
            continue
        seen.add(coverage)
        unique_plans.append(p)
        coverages.append(coverage)

    keep: List[bool] = [True] * len(coverages)
    for i, cov in enumerate(coverages):
        for j, other in enumerate(coverages):
            if i == j:
                continue
            if cov < other:
                keep[i] = False
                break

    result = [p for p, k in zip(unique_plans, keep) if k]
    return result[:top_n]


def recommend_plans_for_weapon(
    d: Dungeon,
    target: Weapon,
    weapons: Sequence[Weapon],
    base_universe: Sequence[str],
    top_n: int = 10,
    rarity_filter: Optional[Set[str]] = None,
    excluded_weapon_names: Optional[Set[str]] = None,
) -> List[FarmPlan]:
    """
    在副本 d 中，筛选“包含目标武器”的高覆盖刷法 Top-N。
    约束：base_pick 必须包含 target.base；lock必须能让目标武器匹配。
    """
    if not can_drop_exact(d, target):
        return []

    base_picks = gen_base_picks(base_universe)
    locks = [
        LockChoice("add", target.add, attr_label(target.add)),     # 锁附加=目标附加
        LockChoice("skill", target.skill, attr_label(target.skill)), # 锁技能=目标技能
    ]

    plans: List[FarmPlan] = []
    weapon_by_name: Dict[str, Weapon] = {w.name: w for w in weapons}
    excluded = set(excluded_weapon_names or ())
    excluded.discard(target.name)
    for bp in base_picks:
        if target.base not in bp:
            continue
        bp_set = set(bp)
        for lk in locks:
            matched: List[str] = []
            for w in weapons:
                if w.name in excluded:
                    continue
                if rarity_filter is not None and w.rarity not in rarity_filter:
                    continue
                if match_weapon_under_plan(d, w, bp_set, lk):
                    matched.append(w.name)
            # 保证目标武器在匹配列表中
            if target.name in matched:
                matched_sorted = sort_weapon_names_by_rarity(matched, weapon_by_name)
                plans.append(
                    FarmPlan(
                        dungeon_name=d.name,
                        base_pick=bp,
                        lock=lk,
                        matched_weapon_names=matched_sorted,
                        matched_count=len(matched_sorted),
                    )
                )

    plans.sort(key=lambda p: (-p.matched_count, p.base_pick, p.lock.kind, p.lock.value))
    return dedupe_by_coverage(plans, top_n)
