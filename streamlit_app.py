"""Interactive view of the synthetic home-service fulfillment portfolio."""

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "03_模拟工单.csv"
AS_OF = pd.Timestamp("2026-09-30 23:59")
TIME_COLUMNS = (
    "created_at", "dispatched_at", "appointment_deadline", "arrived_at",
    "completion_deadline", "completed_at", "exception_detected_at",
    "exception_closed_at",
)
EXCEPTION_ORDER = ["派单超时", "上门超时", "完工超时"]


@st.cache_data
def load_orders():
    orders = pd.read_csv(SOURCE, encoding="utf-8-sig")
    for column in TIME_COLUMNS:
        orders[column] = pd.to_datetime(
            orders[column], format="%Y-%m-%d %H:%M", errors="coerce"
        )
    orders = orders.loc[
        (orders["appointment_deadline"] <= AS_OF)
        & (orders["completion_deadline"] <= AS_OF)
    ].copy()

    dispatch_late = orders["dispatched_at"].isna() | (
        orders["dispatched_at"] > orders["appointment_deadline"]
    )
    arrival_late = orders["arrived_at"].isna() | (
        orders["arrived_at"] > orders["appointment_deadline"]
    )
    completion_late = orders["completed_at"].isna() | (
        orders["completed_at"] > orders["completion_deadline"]
    )
    orders["计算异常"] = "无"
    orders.loc[completion_late, "计算异常"] = "完工超时"
    orders.loc[arrival_late, "计算异常"] = "上门超时"
    orders.loc[dispatch_late, "计算异常"] = "派单超时"
    if not orders["计算异常"].eq(orders["primary_exception"]).all():
        raise ValueError("原始异常标签与时间复算不一致，请先运行 validate_orders.py。")

    orders["准时上门"] = orders["arrived_at"].notna() & ~arrival_late
    orders["按期完工"] = orders["completed_at"].notna() & ~completion_late
    orders["投诉"] = orders["complaint_flag"].eq(1)
    orders["有异常"] = orders["计算异常"].ne("无")
    orders["已闭环"] = orders["有异常"] & orders["exception_closed_at"].notna()
    orders["待闭环"] = orders["有异常"] & ~orders["已闭环"]
    orders["建议优先级"] = "—"
    orders.loc[orders["待闭环"], "建议优先级"] = "P2"
    orders.loc[
        orders["待闭环"]
        & (orders["order_status"].eq("未完工") | orders["投诉"]),
        "建议优先级",
    ] = "P1"
    return orders


def ratio(numerator, denominator):
    return numerator / denominator if denominator else 0


def site_summary(orders):
    return (
        orders.groupby("site_id", as_index=False)
        .agg(
            工单量=("order_id", "size"),
            准时上门数=("准时上门", "sum"),
            按期完工数=("按期完工", "sum"),
            异常单数=("有异常", "sum"),
        )
        .assign(准时上门率=lambda x: x["准时上门数"] / x["工单量"])
    )


st.set_page_config(
    page_title="家电上门服务履约监控｜模拟项目",
    page_icon="📦",
    layout="wide",
)
orders = load_orders()

st.caption("个人服务运营作品集 · 2026 年 8 月模拟工单")
st.title("家电上门服务履约监控")
st.write("沿预约、派单、上门、完工四个节点查看履约质量，并追踪异常是否关闭。")
st.info("全部记录均为合成数据；站点差异是演示设定，不代表京东或任何企业的真实运营表现。")

st.sidebar.header("筛选范围")
city = st.sidebar.selectbox("城市", ["全部城市", *sorted(orders["city"].unique())])
service = st.sidebar.selectbox(
    "服务类型", ["全部服务", *sorted(orders["service_type"].unique())]
)
city_orders = orders if city == "全部城市" else orders.loc[orders["city"].eq(city)]
site = st.sidebar.selectbox(
    "站点", ["全部站点", *sorted(city_orders["site_id"].unique())]
)
st.sidebar.caption("统计截至 2026-09-30 23:59，北京时间。筛选后所有指标重新计算。")

view = orders.copy()
if city != "全部城市":
    view = view.loc[view["city"].eq(city)]
if service != "全部服务":
    view = view.loc[view["service_type"].eq(service)]
if site != "全部站点":
    view = view.loc[view["site_id"].eq(site)]

if view.empty:
    st.warning("当前筛选没有工单，请调整筛选条件。")
    st.stop()

n = len(view)
exceptions = int(view["有异常"].sum())
closed = int(view["已闭环"].sum())
st.caption(f"当前范围：{n} 单 · 异常 {exceptions} 单 · 待闭环 {int(view['待闭环'].sum())} 单")
metrics = st.columns(5)
metrics[0].metric("有效工单", f"{n:,}")
metrics[1].metric("准时上门率", f"{ratio(int(view['准时上门'].sum()), n):.1%}")
metrics[2].metric("按期完工率", f"{ratio(int(view['按期完工'].sum()), n):.1%}")
metrics[3].metric("投诉率", f"{ratio(int(view['投诉'].sum()), n):.1%}")
metrics[4].metric("异常闭环率", f"{ratio(closed, exceptions):.1%}" if exceptions else "不适用")
st.caption("前三项比率与投诉率以当前有效工单为分母；异常闭环率仅以当前有异常的工单为分母。")

overview_tab, exception_tab, method_tab = st.tabs(["履约概览", "异常待办", "口径与局限"])

with overview_tab:
    left, right = st.columns([1.2, 1])
    by_site = site_summary(view)
    with left:
        st.subheader("站点准时上门")
        chart = alt.Chart(by_site).mark_bar(color="#176B67", cornerRadiusEnd=3).encode(
            x=alt.X("准时上门率:Q", title="准时上门率", scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(format=".0%")),
            y=alt.Y("site_id:N", title="站点", sort="-x"),
            tooltip=["site_id:N", "工单量:Q", "准时上门数:Q", alt.Tooltip("准时上门率:Q", format=".1%")],
        ).properties(height=max(260, len(by_site) * 48))
        st.altair_chart(chart, width="stretch")
    with right:
        st.subheader("主要异常构成")
        counts = (
            view.loc[view["有异常"], "计算异常"]
            .value_counts()
            .reindex(EXCEPTION_ORDER, fill_value=0)
            .rename_axis("异常环节")
            .reset_index(name="工单量")
        )
        exception_chart = alt.Chart(counts).mark_bar(color="#B56A22", cornerRadiusEnd=3).encode(
            x=alt.X("工单量:Q", title="工单量"),
            y=alt.Y("异常环节:N", title="", sort=EXCEPTION_ORDER),
            tooltip=["异常环节:N", "工单量:Q"],
        ).properties(height=260)
        st.altair_chart(exception_chart, width="stretch")
        st.caption("主要异常只记录最早失约环节；一单可能在后续环节再次超时。")

    st.subheader("站点明细")
    display_site = by_site.copy()
    display_site["准时上门率"] = display_site["准时上门率"].map(lambda value: f"{value:.1%}")
    st.dataframe(display_site, hide_index=True, width="stretch")

with exception_tab:
    priority = view["建议优先级"].value_counts()
    p1, p2 = st.columns(2)
    p1.metric("P1 · 未完工或有投诉", int(priority.get("P1", 0)))
    p2.metric("P2 · 已完工且无投诉", int(priority.get("P2", 0)))
    st.caption("P1/P2 是本项目提出的待办规则，尚未用于真实业务处置。")
    queue = view.loc[view["待闭环"], [
        "order_id", "city", "service_type", "site_id", "计算异常",
        "order_status", "投诉", "exception_detected_at", "建议优先级",
    ]].copy()
    queue["排序"] = queue["建议优先级"].map({"P1": 0, "P2": 1})
    queue = queue.sort_values(["排序", "exception_detected_at", "order_id"]).drop(columns="排序")
    queue.columns = ["工单 ID", "城市", "服务", "站点", "主要异常", "状态", "投诉", "发现时间", "建议优先级"]
    st.dataframe(queue, hide_index=True, width="stretch", height=390)
    st.markdown("[查看异常定位与原因假设](https://github.com/gjh810/home-service-fulfillment-ops/blob/main/08_%E5%BC%82%E5%B8%B8%E5%AE%9A%E4%BD%8D%E4%B8%8E%E5%8E%9F%E5%9B%A0%E5%81%87%E8%AE%BE.md) · [查看处理 SOP](https://github.com/gjh810/home-service-fulfillment-ops/blob/main/09_%E5%BC%82%E5%B8%B8%E5%A4%84%E7%90%86SOP.md)")

with method_tab:
    st.subheader("数据与指标口径")
    st.markdown(
        """
        - **有效工单：**预约上门与承诺完工截止时间均早于或等于统计时点。
        - **准时上门：**实际上门时间非空，且不晚于预约截止。
        - **按期完工：**实际完工时间非空，且不晚于承诺完工截止。
        - **主要异常：**派单 → 上门 → 完工，取最早失约环节；投诉另计。
        - **异常闭环：**有主要异常且存在关闭时间；关闭时间不能证明处理质量。
        """
    )
    st.write(f"源数据 {len(orders)} 单；主要异常标签与时间复算一致 {len(orders)}/{len(orders)} 单。")
    st.caption("数据由固定随机种子生成。没有人员、路程、配件或沟通记录，站点差异不能推断真实根因。")
    st.markdown("[GitHub 项目与复现说明](https://github.com/gjh810/home-service-fulfillment-ops)")
