from __future__ import annotations

from typing import List, Tuple

import pandas as pd
import streamlit as st

from data_loader import load_dungeons, load_weapons, Dungeon, Weapon
from matcher import (
    attr_label,
    base_label,
    add_label,
    skill_label,
    can_drop_exact,
    enumerate_base_universe,
    recommend_plans_for_weapon,
)
from plan import plan_multi_weapons
from config import *


st.set_page_config(page_title="基质刷取计算工具", layout="wide")


@st.cache_data(show_spinner=False)
def load_all(dungeon_path: str, weapon_path: str, encoding: str) -> Tuple[List[Dungeon], List[Weapon]]:
    dungeons = load_dungeons(dungeon_path, encoding=encoding)
    weapons = load_weapons(weapon_path, encoding=encoding)
    return dungeons, weapons


def _plans_to_df(plans) -> pd.DataFrame:
    rows = []
    for p in plans:
        lock_str = ("附加属性 = " if p.lock.kind == "add" else "技能属性 = ") + p.lock.label
        rows.append(
            {
                "基础三选": "，".join(attr_label(ch) for ch in p.base_pick),
                "锁定": lock_str,
                "覆盖武器数": p.matched_count,
                "覆盖武器": "、".join(p.matched_weapon_names),
            }
        )
    return pd.DataFrame(rows)


def _multi_plans_to_df(plans) -> pd.DataFrame:
    rows = []
    for p in plans:
        lock_str = ("附加属性 = " if p.lock.kind == "add" else "技能属性 = ") + p.lock.label
        rows.append(
            {
                "副本": p.dungeon_name,
                "基础三选": "，".join(attr_label(ch) for ch in p.base_pick),
                "锁定": lock_str,
                "覆盖目标数": p.matched_count,
                "覆盖目标": "、".join(p.matched_weapon_names),
            }
        )
    return pd.DataFrame(rows)


def render_weapon_names_colored(names, weapon_index):
    # names: Iterable[str]
    parts = []
    for n in names:
        w = weapon_index.get(n)
        if not w:
            parts.append(n)
            continue
        color = RARITY_COLOR.get(w.rarity, "#111827")
        parts.append(f"<span style='color:{color};font-weight:600'>{w.name}</span>")
    return "、".join(parts)


def main():
    st.title("基质刷取计算工具")

    dungeon_path = "副本.txt"
    weapon_path = "武器.txt"
    encoding = "utf-8"
    rarity_filter = None
    top_n = 5

    try:
        dungeons, weapons = load_all(dungeon_path, weapon_path, encoding)
    except Exception as e:
        st.error(f"读取数据失败：{e}")
        st.stop()

    base_universe = enumerate_base_universe(weapons)

    tab1, tab2, tab3 = st.tabs(["武器查询", "属性反查", "多武器规划"])

    # -------------------
    # Tab 1: 武器查询
    # -------------------
    with tab1:
        st.subheader("指定武器 ->")

        weapons_sorted = sorted(
            weapons,
            key=lambda w: (RARITY_RANK.get(w.rarity, 999), w.name)
        )

        def weapon_label(w: Weapon) -> str:
            return f"{w.rarity} | {w.name}  ({w.base}{w.add}{w.skill})"

        target = st.selectbox("选择武器", options=weapons_sorted, format_func=weapon_label)

        color = RARITY_COLOR.get(target.rarity, "#111827")
        st.markdown(
            f"目标武器：<span style='color:{color};font-weight:800'>{target.name}</span>"
            f"（属性：{target.base}{target.add}{target.skill}）",
            unsafe_allow_html=True,
        )

        # 可刷能量淤积点列表
        ok_dungeons = [d for d in dungeons if can_drop_exact(d, target)]
        if not ok_dungeons:
            st.warning("没有任何能量淤积点同时包含该武器的附加属性与技能属性，无法刷出完全匹配基质。")
        else:
            st.markdown("### 推荐刷法")
            for d in ok_dungeons:
                st.markdown(f"#### {d.name}")
                plans = recommend_plans_for_weapon(
                    d=d,
                    target=target,
                    weapons=weapons,
                    base_universe=base_universe,
                    top_n=top_n,
                    rarity_filter=rarity_filter,
                )
                if not plans:
                    st.write("无推荐刷法（可能是基础属性全集不足3种或数据异常）。")
                    continue
                st.dataframe(_plans_to_df(plans), use_container_width=True, hide_index=True)

    # -------------------
    # Tab 2: 属性反查
    # -------------------
    with tab2:
        st.subheader("通过属性组合查找武器")
        st.markdown("选择一个基础属性、一个附加属性和一个技能属性，查找对应的武器")

        # 收集所有属性，按config.py中的顺序排列
        all_base = [k for k in BASE_FULLNAME.keys() if any(w.base == k for w in weapons)]
        all_add = [k for k in ADD_FULLNAME.keys() if any(w.add == k for w in weapons)]
        all_skill = [k for k in SKILL_FULLNAME.keys() if any(w.skill == k for w in weapons)]

        # 获取当前选择
        selected_base = st.session_state.get("selected_base")
        selected_add = st.session_state.get("selected_add")
        selected_skill = st.session_state.get("selected_skill")

        # 基础属性行
        st.markdown("**基础属性**")
        cols = st.columns(len(all_base))
        for i, b in enumerate(all_base):
            with cols[i]:
                btn_type = "primary" if selected_base == b else "secondary"
                if st.button(base_label(b), key=f"base_{b}", type=btn_type, use_container_width=True):
                    if selected_base == b:
                        st.session_state.pop("selected_base", None)
                    else:
                        st.session_state["selected_base"] = b
                    st.rerun()

        # 附加属性行
        st.markdown("**附加属性**")
        cols = st.columns(len(all_add))
        for i, a in enumerate(all_add):
            with cols[i]:
                btn_type = "primary" if selected_add == a else "secondary"
                if st.button(add_label(a), key=f"add_{a}", type=btn_type, use_container_width=True):
                    if selected_add == a:
                        st.session_state.pop("selected_add", None)
                    else:
                        st.session_state["selected_add"] = a
                    st.rerun()

        # 技能属性行
        st.markdown("**技能属性**")
        cols = st.columns(len(all_skill))
        for i, s in enumerate(all_skill):
            with cols[i]:
                btn_type = "primary" if selected_skill == s else "secondary"
                if st.button(skill_label(s), key=f"skill_{s}", type=btn_type, use_container_width=True):
                    if selected_skill == s:
                        st.session_state.pop("selected_skill", None)
                    else:
                        st.session_state["selected_skill"] = s
                    st.rerun()

        # 清除按钮
        if st.button("清除选择"):
            for key in ["selected_base", "selected_add", "selected_skill"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

        # 查找结果（允许部分匹配）
        if selected_base or selected_add or selected_skill:
            st.markdown("---")
            st.markdown("### 查找结果")

            # 过滤武器：只对已选择的属性进行匹配
            matching_weapons = [
                w for w in weapons
                if (not selected_base or w.base == selected_base)
                and (not selected_add or w.add == selected_add)
                and (not selected_skill or w.skill == selected_skill)
            ]

            if matching_weapons:
                st.success(f"找到 {len(matching_weapons)} 件武器：")
                for w in sorted(matching_weapons, key=lambda x: (RARITY_RANK.get(x.rarity, 999), x.name)):
                    color = RARITY_COLOR.get(w.rarity, "#111827")
                    st.markdown(
                        f"- <span style='color:{color};font-weight:700'>[{w.rarity}] {w.name}</span> "
                        f"({attr_label(w.base)}/{attr_label(w.add)}/{attr_label(w.skill)})",
                        unsafe_allow_html=True
                    )
            else:
                # 组装提示语，只包含已选属性
                parts = []
                if selected_base:
                    parts.append(base_label(selected_base))
                if selected_add:
                    parts.append(add_label(selected_add))
                if selected_skill:
                    parts.append(skill_label(selected_skill))
                st.warning(f"未找到匹配的武器：{' + '.join(parts)}")

    # -------------------
    # Tab 3: 多武器规划
    # -------------------
    with tab3:
        st.subheader("多武器规划（尽量少的副本与词条覆盖更多目标）")

        weapons_sorted = sorted(
            weapons,
            key=lambda w: (RARITY_RANK.get(w.rarity, 999), w.name)
        )

        def weapon_label(w: Weapon) -> str:
            return f"{w.rarity} | {w.name}  ({w.base}{w.add}{w.skill})"

        targets = st.multiselect("选择目标武器（可多选）", options=weapons_sorted, format_func=weapon_label)

        if not targets:
            st.info("请先选择至少一件目标武器。")
        else:
            result = plan_multi_weapons(
                dungeons=dungeons,
                weapons=weapons,
                targets=targets,
                base_universe=base_universe,
                rarity_filter=rarity_filter,
            )

            covered_cnt = len(result.covered_names)
            unique_dungeons = len({p.dungeon_name for p in result.plans})
            st.markdown(
                f"已覆盖 {covered_cnt}/{result.target_count} 件目标武器，"
                f"使用 {len(result.plans)} 种刷法、{unique_dungeons} 个副本。"
            )

            if result.uncovered_names:
                st.warning("未覆盖目标：" + "、".join(result.uncovered_names))

            if result.plans:
                st.dataframe(_multi_plans_to_df(result.plans), use_container_width=True, hide_index=True)
            else:
                st.error("没有任何可行刷法（可能是基础属性种类不足或数据异常）。")


if __name__ == "__main__":
    main()
