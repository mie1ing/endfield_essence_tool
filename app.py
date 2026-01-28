from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
import streamlit as st

from data_loader import load_dungeons, load_weapons, Dungeon, Weapon
from matcher import (
    build_weapon_index,
    can_drop_exact,
    enumerate_base_universe,
    recommend_plans_for_weapon,
    score_plans_for_dungeon,
)

st.set_page_config(page_title="副本刷取计算工具", layout="wide")


@st.cache_data(show_spinner=False)
def load_all(dungeon_path: str, weapon_path: str, encoding: str) -> Tuple[List[Dungeon], List[Weapon]]:
    dungeons = load_dungeons(dungeon_path, encoding=encoding)
    weapons = load_weapons(weapon_path, encoding=encoding)
    return dungeons, weapons


def _plans_to_df(plans) -> pd.DataFrame:
    rows = []
    for p in plans:
        lock_str = ("附加锁定=" if p.lock.kind == "add" else "技能锁定=") + p.lock.value
        rows.append(
            {
                "副本": p.dungeon_name,
                "基础三选": "".join(p.base_pick),
                "锁定": lock_str,
                "覆盖武器数": p.matched_count,
                "覆盖武器": "、".join(p.matched_weapon_names),
            }
        )
    return pd.DataFrame(rows)


def main():
    st.title("副本刷取计算工具")

    with st.sidebar:
        st.header("数据文件")
        default_dungeon = "副本.txt"
        default_weapon = "武器.txt"

        dungeon_path = st.text_input("副本文件路径", value=default_dungeon)
        weapon_path = st.text_input("武器文件路径", value=default_weapon)

        encoding = st.selectbox("文件编码", options=["utf-8", "utf-8-sig", "gbk"], index=0)

        st.header("过滤")
        rarity_text = st.text_input("只看品质（可选，逗号分隔）", value="")
        rarity_filter: Optional[Set[str]] = None
        if rarity_text.strip():
            rarity_filter = {x.strip() for x in rarity_text.split(",") if x.strip()}

        top_n = st.slider("Top-N 刷法", min_value=3, max_value=30, value=10, step=1)

    try:
        dungeons, weapons = load_all(dungeon_path, weapon_path, encoding)
    except Exception as e:
        st.error(f"读取数据失败：{e}")
        st.stop()

    weapon_index: Dict[str, Weapon] = build_weapon_index(weapons)
    base_universe = enumerate_base_universe(weapons)

    tab1, tab2 = st.tabs(["武器查询", "副本总览"])

    # -------------------
    # Tab 1: 武器查询
    # -------------------
    with tab1:
        st.subheader("指定武器 ->")

        weapon_names = sorted(weapon_index.keys())
        target_name = st.selectbox("选择武器", options=weapon_names, index=0 if weapon_names else None)

        if not target_name:
            st.info("武器列表为空。请检查武器.txt 格式。")
            st.stop()

        target = weapon_index[target_name]
        st.write(f"目标武器：{target.name}（品质：{target.rarity}，属性：{target.base}{target.add}{target.skill}）")

        # 可刷副本列表
        ok_dungeons = [d for d in dungeons if can_drop_exact(d, target)]
        if not ok_dungeons:
            st.warning("没有任何副本同时包含该武器的附加属性与技能属性，无法刷出完全匹配掉落物。")
        else:
            # st.markdown("### 可刷副本")
            # df_ok = pd.DataFrame(
            #     [{"副本": d.name, "副本附加池": "".join(sorted(d.add_set)), "副本技能池": "".join(sorted(d.skill_set))}
            #      for d in ok_dungeons]
            # )
            # st.dataframe(df_ok, use_container_width=True, hide_index=True)

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
    # Tab 2: 副本总览
    # -------------------
    with tab2:
        st.subheader("每个副本 Top-N 刷法（覆盖武器最多）")

        # 选择一个副本或全部
        dungeon_names = [d.name for d in dungeons]
        pick = st.selectbox("选择副本", options=["(全部)"] + dungeon_names, index=0)

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


if __name__ == "__main__":
    main()
