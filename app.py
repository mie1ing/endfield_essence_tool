from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st

from data_loader import load_dungeons, load_weapons, Dungeon, Weapon
from matcher import (
    attr_label,
    can_drop_exact,
    enumerate_base_universe,
    recommend_plans_for_weapon,
    score_plans_for_dungeon,
)
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

    with st.sidebar:
        st.header("数据文件")
        default_dungeon = "副本.txt"
        default_weapon = "武器.txt"

        dungeon_path = st.text_input("副本文件路径", value=default_dungeon)
        weapon_path = st.text_input("武器文件路径", value=default_weapon)

        encoding = st.selectbox("文件编码", options=["utf-8", "utf-8-sig", "gbk"], index=0)

        st.header("过滤")
        rarity_text = st.text_input("只看品质", value="")
        rarity_filter: Optional[Set[str]] = None
        if rarity_text.strip():
            rarity_filter = {x.strip() for x in rarity_text.split(",") if x.strip()}

        top_n = st.slider("Top-N 刷法", min_value=3, max_value=30, value=10, step=1)

    try:
        dungeons, weapons = load_all(dungeon_path, weapon_path, encoding)
    except Exception as e:
        st.error(f"读取数据失败：{e}")
        st.stop()

    # weapon_index: Dict[str, Weapon] = build_weapon_index(weapons)
    base_universe = enumerate_base_universe(weapons)
    weapon_index: Dict[str, Weapon] = {w.name: w for w in weapons}

    tab1, tab2, tab3 = st.tabs(["武器查询", "总览", "属性反查"])

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
    # Tab 2: 能量淤积点总览
    # -------------------
    with tab2:
        st.subheader("每个能量淤积点 Top-N 刷法（覆盖武器最多）")

        # 选择一个副本或全部
        dungeon_names = [d.name for d in dungeons]
        pick = st.selectbox("选择能量淤积点", options=["(全部)"] + dungeon_names, index=0)

        if pick == "(全部)":
            for d in dungeons:
                st.markdown(f"### {d.name}")
                plans = score_plans_for_dungeon(
                    d=d,
                    weapons=weapons,
                    base_universe=base_universe,
                    top_n=top_n,
                    rarity_filter=rarity_filter,
                )
                if not plans:
                    st.write("无可覆盖武器的刷法（或基础属性全集不足3种）。")
                    continue
                st.dataframe(_plans_to_df(plans), use_container_width=True, hide_index=True)
        else:
            d = next(x for x in dungeons if x.name == pick)
            plans = score_plans_for_dungeon(
                d=d,
                weapons=weapons,
                base_universe=base_universe,
                top_n=top_n,
                rarity_filter=rarity_filter,
            )
            if not plans:
                st.write("无可覆盖武器的刷法（或基础属性全集不足3种）。")
            else:
                st.dataframe(_plans_to_df(plans), use_container_width=True, hide_index=True)

    # -------------------
    # Tab 3: 属性反查
    # -------------------
    with tab3:
        st.subheader("通过属性组合查找武器")
        st.markdown("选择一个基础属性、一个附加属性和一个技能属性，查找对应的武器")

        # 收集所有属性
        all_base = sorted(set(w.base for w in weapons))
        all_add = sorted(set(w.add for w in weapons))
        all_skill = sorted(set(w.skill for w in weapons))

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
                if st.button(attr_label(b), key=f"base_{b}", type=btn_type, use_container_width=True):
                    st.session_state["selected_base"] = b
                    st.rerun()

        # 附加属性行
        st.markdown("**附加属性**")
        cols = st.columns(len(all_add))
        for i, a in enumerate(all_add):
            with cols[i]:
                btn_type = "primary" if selected_add == a else "secondary"
                if st.button(attr_label(a), key=f"add_{a}", type=btn_type, use_container_width=True):
                    st.session_state["selected_add"] = a
                    st.rerun()

        # 技能属性行
        st.markdown("**技能属性**")
        cols = st.columns(len(all_skill))
        for i, s in enumerate(all_skill):
            with cols[i]:
                btn_type = "primary" if selected_skill == s else "secondary"
                if st.button(attr_label(s), key=f"skill_{s}", type=btn_type, use_container_width=True):
                    st.session_state["selected_skill"] = s
                    st.rerun()

        # 查找结果
        if selected_base and selected_add and selected_skill:
            st.markdown("---")
            st.markdown("### 查找结果")

            # 过滤武器
            matching_weapons = [
                w for w in weapons
                if w.base == selected_base and w.add == selected_add and w.skill == selected_skill
            ]

            if matching_weapons:
                st.success(f"找到 {len(matching_weapons)} 件武器：")
                for w in sorted(matching_weapons, key=lambda x: (RARITY_RANK.get(x.rarity, 999), x.name)):
                    color = RARITY_COLOR.get(w.rarity, "#111827")
                    st.markdown(
                        f"- <span style='color:{color};font-weight:700'>[{w.rarity}] {w.name}</span> "
                        f"({attr_label(w.base)}{attr_label(w.add)}{attr_label(w.skill)})",
                        unsafe_allow_html=True
                    )
            else:
                st.warning(
                    f"未找到匹配的武器：{attr_label(selected_base)} + {attr_label(selected_add)} + {attr_label(selected_skill)}"
                )

        # 清除按钮
        if st.button("清除选择"):
            for key in ["selected_base", "selected_add", "selected_skill"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()


if __name__ == "__main__":
    main()
