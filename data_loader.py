from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Set


@dataclass(frozen=True)
class Dungeon:
    name: str
    add_set: Set[str]     # 8 chars
    skill_set: Set[str]   # 8 chars


@dataclass(frozen=True)
class Weapon:
    name: str
    rarity: str
    base: str
    add: str
    skill: str


def _split_chars(s: str) -> Set[str]:
    s = s.strip()
    return set(list(s))


def load_dungeons(path: str | Path, encoding: str = "utf-8") -> List[Dungeon]:
    """
    副本.txt: 每行至少3列：副本名称 附加属性串 技能属性串
    允许空格或制表符分隔。
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"副本文件不存在: {path}")

    dungeons: List[Dungeon] = []
    for i, raw in enumerate(path.read_text(encoding=encoding).splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            raise ValueError(f"副本文件第{i}行列数不足(需>=3): {raw}")

        name = parts[0]
        add_str = parts[1]
        skill_str = parts[2]

        add_set = _split_chars(add_str)
        skill_set = _split_chars(skill_str)

        if len(add_set) != len(add_str):
            # 有重复字符也算一种输入错误，提示即可
            raise ValueError(f"副本 {name} 的附加属性串存在重复字符: {add_str}")
        if len(skill_set) != len(skill_str):
            raise ValueError(f"副本 {name} 的技能属性串存在重复字符: {skill_str}")

        dungeons.append(Dungeon(name=name, add_set=add_set, skill_set=skill_set))

    return dungeons


def load_weapons(path: str | Path, encoding: str = "utf-8") -> List[Weapon]:
    """
    武器.txt: 每行至少3列：武器名称 武器品质 三字属性(基础+附加+技能)
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"武器文件不存在: {path}")

    weapons: List[Weapon] = []
    for i, raw in enumerate(path.read_text(encoding=encoding).splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            raise ValueError(f"武器文件第{i}行列数不足(需>=3): {raw}")

        name = parts[0]
        rarity = parts[1]
        attr = parts[2].strip()
        if len(attr) != 3:
            raise ValueError(f"武器 {name} 的属性不是3个字: {attr}")

        base, add, skill = attr[0], attr[1], attr[2]
        weapons.append(Weapon(name=name, rarity=rarity, base=base, add=add, skill=skill))

    return weapons
