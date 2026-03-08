# =============================================================================
# Bitcoin Weekly Bias Dashboard — Streamlit App
# =============================================================================
import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _get_fred_key() -> str:
    """Read FRED key from .env (local) or Streamlit secrets (cloud)."""
    key = os.getenv("FRED_API_KEY", "")
    if not key:
        try:
            key = str(st.secrets["FRED_API_KEY"])
        except Exception:
            key = ""
    return key


st.set_page_config(
    page_title="Bitcoin Weekly Bias Dashboard",
    page_icon="₿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom CSS — Bitcoin orange theme
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    .main { background-color: #0E1117; }
    .block-container { padding: 1rem 2rem; }
    .metric-card {
        background: #1E2129; border-radius: 10px;
        padding: 14px 18px; margin-bottom: 8px;
    }
    .metric-label  { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
    .metric-value  { font-size: 22px; font-weight: 700; color: #FAFAFA; }
    .metric-change { font-size: 13px; margin-top: 2px; }
    .bull-text  { color: #00C853; }
    .bear-text  { color: #D50000; }
    .neut-text  { color: #FFD740; }
    .score-pill {
        display: inline-block; padding: 6px 20px;
        border-radius: 50px; font-weight: 700;
        font-size: 18px; letter-spacing: 1px;
    }
    h2, h3 { color: #F7931A !important; }
    section[data-testid="stSidebar"] { background-color: #1E2129; }
    .stButton > button {
        background: #F7931A; color: #000; font-weight: 700;
        border: none; border-radius: 8px; padding: 10px 28px;
        font-size: 15px; cursor: pointer;
    }
    .stButton > button:hover { background: #E07B0E; }
    .divider { border-top: 1px solid #2A2D35; margin: 16px 0; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Imports (after page config)
# ---------------------------------------------------------------------------
import pandas as pd

import charts
import data_fetcher
import ict_analysis
import indicators
import scoring
import config


# ---------------------------------------------------------------------------
# Data fetching with caching
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner="Fetching market data...")
def load_data(fred_key: str = ""):
    return data_fetcher.fetch_all_data(fred_key=fred_key)


def get_data(force_refresh: bool = False):
    fred_key = _get_fred_key()
    if force_refresh:
        st.cache_data.clear()
    return load_data(fred_key=fred_key)


# ---------------------------------------------------------------------------
# Helper: coloured metric card
# ---------------------------------------------------------------------------

def metric_card(label: str, value: str, change: str = "", change_positive: bool | None = None):
    if change_positive is True:
        chg_class = "bull-text"
    elif change_positive is False:
        chg_class = "bear-text"
    else:
        chg_class = "neut-text"

    chg_html = f'<div class="metric-change {chg_class}">{change}</div>' if change else ""
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value">{value}</div>
        {chg_html}
    </div>
    """, unsafe_allow_html=True)


def score_badge(score: float, label: str, color: str):
    st.markdown(f"""
    <div style="text-align:center; margin: 10px 0;">
        <span class="score-pill" style="background:{color}33; color:{color}; border: 2px solid {color};">
            {label}
        </span>
        <div style="color:#888; font-size:13px; margin-top:6px;">
            Score: <strong style="color:{color};">{score:+.2f}</strong>
        </div>
    </div>
    """, unsafe_allow_html=True)


def _fmt(val, decimals: int = 2, suffix: str = "", prefix: str = "") -> str:
    if val is None:
        return "N/A"
    return f"{prefix}{val:,.{decimals}f}{suffix}"


def _fmt_btc(val) -> str:
    """Format BTC price with commas and no decimal places."""
    if val is None:
        return "N/A"
    return f"${val:,.0f}"


def _arrow(chg) -> tuple[str, bool | None]:
    if chg is None:
        return "", None
    arrow = "▲" if chg >= 0 else "▼"
    return f"{arrow} {abs(chg):.2f}%", chg >= 0


# ---------------------------------------------------------------------------
# ── MAIN APP ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def main():
    # ── Header ──────────────────────────────────────────────────────────
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.markdown("## ₿ Bitcoin Weekly Bias Dashboard")
        st.markdown(
            "<div style='color:#888; font-size:13px; margin-top:-12px;'>"
            "Free sources: Yahoo Finance · FRED · CFTC · Alternative.me Fear & Greed · All indicators weekly"
            "</div>",
            unsafe_allow_html=True,
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("Refresh Data", key="refresh_btn", use_container_width=True)

    # ── FRED key warning ─────────────────────────────────────────────────
    if not os.getenv("FRED_API_KEY"):
        st.warning(
            "**FRED API key not set** — macro indicators (Real Yield, Breakeven, CPI, PCE, Yield Curve) "
            "will show N/A. Add `FRED_API_KEY=your_key` to the `.env` file. "
            "Get a free key at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html).",
            icon="⚠️",
        )

    # ── Load data ────────────────────────────────────────────────────────
    data = get_data(force_refresh=refresh)

    with st.spinner("Computing indicators..."):
        ind  = indicators.build_all_indicators(data)
        bias = scoring.score_all(ind)

    fetched_at = data.get("fetched_at")
    if fetched_at:
        st.caption(f"Last updated: {fetched_at.strftime('%Y-%m-%d %H:%M:%S')}")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 1: BIAS SCORECARD
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### Bias Scorecard")

    gauge_col, breakdown_col, detail_col = st.columns([1.2, 1, 1.8])

    with gauge_col:
        fig_gauge = charts.chart_bias_gauge(bias["score"], bias["label"], bias["color"])
        st.plotly_chart(fig_gauge, use_container_width=True, config={"displayModeBar": False})

    with breakdown_col:
        fig_breakdown = charts.chart_score_breakdown(bias["group_scores"], bias["breakdown"])
        st.plotly_chart(fig_breakdown, use_container_width=True, config={"displayModeBar": False})

    with detail_col:
        st.markdown("**Indicator Signals**")
        all_bd = bias["breakdown"]

        def signal_row(name: str, score: int):
            icon  = "🟢" if score > 0 else ("🔴" if score < 0 else "⚪")
            label = "Bullish" if score > 0 else ("Bearish" if score < 0 else "Neutral")
            st.markdown(f"{icon} **{name}** — {label}")

        with st.expander("Macro", expanded=True):
            for k, v in all_bd["macro"].items():
                signal_row(k.replace("_", " ").title(), v)

        with st.expander("Sentiment"):
            for k, v in all_bd["sentiment"].items():
                signal_row(k.replace("_", " ").title(), v)

        with st.expander("Technical"):
            for k, v in all_bd["technical"].items():
                signal_row(k.replace("_", " ").title(), v)

        with st.expander("Cross-Asset"):
            for k, v in all_bd["cross_asset"].items():
                signal_row(k.replace("_", " ").title(), v)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # BTC headline
    btc_price = ind.get("btc_price")
    btc_chg   = ind.get("btc_weekly_chg")
    arrow, is_pos = _arrow(btc_chg)
    chg_class = "bull-text" if is_pos else "bear-text"
    st.markdown(
        f"<h3 style='margin:0;'>Bitcoin (BTC/USD) &nbsp; "
        f"<span style='color:#F7931A;'>{_fmt_btc(btc_price)}</span> &nbsp;"
        f"<span class='{chg_class}' style='font-size:16px;'>{arrow} wk</span></h3>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 2: MACRO PANEL
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### Macro Indicators")

    macro = ind.get("macro", {})

    mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
    with mc1:
        dxy = macro.get("dxy", {})
        arrow, pos = _arrow(dxy.get("weekly_chg"))
        metric_card("DXY", _fmt(dxy.get("value"), 2),
                    f"{arrow} wk",
                    change_positive=not pos if pos is not None else None)

    with mc2:
        ry = macro.get("real_yield_10y", {})
        delta = ry.get("delta")
        metric_card("10Y Real Yield", _fmt(ry.get("value"), 3, "%"),
                    f"{'▲' if delta and delta > 0 else '▼'} {abs(delta):.3f}%" if delta else "",
                    change_positive=delta < 0 if delta else None)

    with mc3:
        be = macro.get("breakeven_10y", {})
        delta = be.get("delta")
        metric_card("10Y Breakeven", _fmt(be.get("value"), 2, "%"),
                    f"{'▲' if delta and delta > 0 else '▼'} {abs(delta):.3f}%" if delta else "",
                    change_positive=delta > 0 if delta else None)

    with mc4:
        ff = macro.get("fed_funds", {})
        metric_card("Fed Funds Rate", _fmt(ff.get("value"), 2, "%"), "")

    with mc5:
        metric_card("CPI YoY", _fmt(macro.get("cpi_yoy", {}).get("value"), 2, "%"), "")

    with mc6:
        m2 = macro.get("m2", {})
        m2_yoy = m2.get("yoy_pct")
        metric_card("M2 Supply YoY",
                    _fmt(m2_yoy, 2, "%") if m2_yoy else "N/A",
                    "Expanding M2 = Bullish BTC" if m2_yoy and m2_yoy > 0 else "",
                    change_positive=m2_yoy > 0 if m2_yoy else None)

    # 2Y / 10Y yields + yield curve
    mc_a, mc_b, mc_c = st.columns(3)
    with mc_a:
        t2 = macro.get("treasury_2y", {})
        delta = t2.get("delta")
        metric_card("2Y Treasury Yield", _fmt(t2.get("value"), 3, "%"),
                    f"{'▲' if delta and delta > 0 else '▼'} {abs(delta):.3f}%" if delta else "",
                    change_positive=delta < 0 if delta else None)
    with mc_b:
        t10 = macro.get("treasury_10y", {})
        delta = t10.get("delta")
        metric_card("10Y Treasury Yield", _fmt(t10.get("value"), 3, "%"),
                    f"{'▲' if delta and delta > 0 else '▼'} {abs(delta):.3f}%" if delta else "",
                    change_positive=delta < 0 if delta else None)
    with mc_c:
        yc = macro.get("yield_curve", {})
        val = yc.get("value")
        steep = yc.get("steepening")
        trend = "Steepening" if steep else ("Flattening" if steep is False else "")
        metric_card("Yield Curve 10Y-2Y", _fmt(val, 3, "%"), trend, change_positive=steep)

    # Macro charts
    ch1, ch2 = st.columns(2)
    with ch1:
        fig = charts.chart_real_yield(data["fred"])
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with ch2:
        fig = charts.chart_yield_curve(data["fred"])
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    fig_dxy = charts.chart_dxy(data["prices"])
    st.plotly_chart(fig_dxy, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 3: SENTIMENT — FEAR & GREED + COT
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### Sentiment — Fear & Greed · COT · ETF Flows")

    fg_data  = ind.get("sentiment", {}).get("fear_greed", {})
    cot_data = ind.get("sentiment", {}).get("cot", {})

    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        fg_val   = fg_data.get("value")
        fg_class = fg_data.get("classification", "")
        fg_chg   = fg_data.get("weekly_chg")
        extreme  = ""
        if fg_data.get("extreme_fear"):
            extreme = "Extreme Fear → Contrarian BULLISH"
        elif fg_data.get("extreme_greed"):
            extreme = "Extreme Greed → Contrarian BEARISH"
        chg_str = f"{'▲' if fg_chg and fg_chg > 0 else '▼'} {abs(fg_chg):.1f} wk" if fg_chg else ""
        metric_card(
            "Fear & Greed Index",
            f"{fg_val} — {fg_class}" if fg_val else "N/A",
            extreme or chg_str,
            change_positive=(fg_val < 40) if fg_val else None,   # fear = contrarian bullish
        )

    with sc2:
        net = cot_data.get("net_pos")
        ci  = cot_data.get("cot_index")
        extreme_cot = "Extreme Long (Contrarian Bearish)" if cot_data.get("extreme_long") else \
                      ("Extreme Short (Contrarian Bullish)" if cot_data.get("extreme_short") else "")
        metric_card("CME BTC COT %ile", _fmt(ci, 1) if ci is not None else "N/A",
                    extreme_cot, change_positive=(ci < 20) if ci is not None else None)

    with sc3:
        btc_eth = ind.get("sentiment", {}).get("btc_eth_ratio", {})
        metric_card("BTC / ETH Ratio", _fmt(btc_eth.get("value"), 2),
                    (_arrow(btc_eth.get("weekly_chg"))[0]) + " wk")

    with sc4:
        avg_flow = ind.get("sentiment", {}).get("etf", {}).get("combined_flow_avg_pct")
        metric_card("ETF Avg Flow (wk)", _fmt(avg_flow, 2, "%"),
                    change_positive=avg_flow >= 0 if avg_flow is not None else None)

    # Fear & Greed chart
    fig_fg = charts.chart_fear_greed(data.get("fear_greed", pd.DataFrame()))
    st.plotly_chart(fig_fg, use_container_width=True, config={"displayModeBar": False})

    # COT chart
    fig_cot = charts.chart_cot(data["cot"])
    st.plotly_chart(fig_cot, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 4: BITCOIN ETF PANEL
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### Bitcoin Spot ETFs")

    etf_data   = ind.get("sentiment", {}).get("etf", {})
    etf_keys   = ["ibit", "fbtc", "gbtc", "arkb", "hodl", "bitb"]
    etf_labels = ["IBIT", "FBTC", "GBTC", "ARKB", "HODL", "BITB"]
    etf_desc   = [
        "BlackRock iShares BTC",
        "Fidelity Wise Origin BTC",
        "Grayscale Bitcoin Trust",
        "ARK 21Shares Bitcoin",
        "VanEck Bitcoin ETF",
        "Bitwise Bitcoin ETF",
    ]

    cols = st.columns(6)
    for i, (key, label, desc) in enumerate(zip(etf_keys, etf_labels, etf_desc)):
        d = etf_data.get(key, {})
        price = d.get("price")
        chg   = d.get("weekly_chg_pct")
        aum   = d.get("aum_m")
        arrow_str, is_pos = _arrow(chg)
        with cols[i]:
            aum_str = f"AUM ~${aum:,.0f}M" if aum else ""
            metric_card(f"{label} — {desc}", _fmt(price), f"{arrow_str} wk | {aum_str}", change_positive=is_pos)

    # BTC/ETH ratio trend
    mr1, mr2 = st.columns(2)
    with mr1:
        ratio_trend = etf_data.get("btc_eth_ratio_trend")
        icon = "▲" if ratio_trend == "rising" else ("▼" if ratio_trend == "falling" else "")
        metric_card("BTC / ETH Ratio Trend", f"{icon} {ratio_trend or 'N/A'}".strip(),
                    "Rising = BTC outperforming ETH = BTC Dominance",
                    change_positive=ratio_trend == "rising" if ratio_trend else None)
    with mr2:
        metric_card("Avg ETF Flow (wk)",
                    _fmt(etf_data.get("combined_flow_avg_pct"), 2, "%"),
                    "Positive = net inflows across BTC ETFs",
                    change_positive=(etf_data.get("combined_flow_avg_pct") or 0) >= 0)

    fig_etf = charts.chart_etf_flows(etf_data)
    st.plotly_chart(fig_etf, use_container_width=True, config={"displayModeBar": False})

    # BTC/ETH ratio chart
    fig_ratio = charts.chart_btc_eth_ratio(data["prices"])
    st.plotly_chart(fig_ratio, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 5: TECHNICAL PANEL
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### Technical — Weekly")

    tech = ind.get("technical", {})
    mas  = tech.get("moving_averages", {})
    rsi  = tech.get("rsi")
    macd = tech.get("macd", {})

    tc1, tc2, tc3, tc4, tc5 = st.columns(5)
    for col, period in zip([tc1, tc2, tc3], config.WEEKLY_MA_PERIODS):
        ma_d  = mas.get(period, {})
        above = ma_d.get("above")
        diff  = ma_d.get("pct_diff")
        with col:
            metric_card(
                f"{period}W MA",
                _fmt_btc(ma_d.get("ma")),
                f"{'Above' if above else 'Below'} ({diff:+.2f}%)" if diff is not None else "",
                change_positive=above,
            )
    with tc4:
        rsi_zone = "Momentum (50-70)" if (rsi and 50 <= rsi <= 70) else \
                   ("Overbought >75" if (rsi and rsi > 75) else \
                   ("Weak <40" if (rsi and rsi < 40) else "Neutral"))
        metric_card("RSI (14W)", _fmt(rsi, 1), rsi_zone,
                    change_positive=(rsi and 50 <= rsi <= 70))
    with tc5:
        macd_bull  = macd.get("bullish")
        macd_cross = macd.get("crossing_up")
        macd_label = "Bullish Cross!" if macd_cross else ("Above 0" if macd_bull else "Below 0")
        metric_card("MACD Weekly", _fmt(macd.get("histogram"), 0), macd_label, change_positive=macd_bull)

    # Price + MA chart
    fig_btc = charts.chart_btc_price_ma(data["prices"], mas)
    st.plotly_chart(fig_btc, use_container_width=True, config={"displayModeBar": False})

    rsi_col, macd_col = st.columns(2)
    with rsi_col:
        fig_rsi = charts.chart_rsi(data["prices"])
        st.plotly_chart(fig_rsi, use_container_width=True, config={"displayModeBar": False})
    with macd_col:
        fig_macd = charts.chart_macd(data["prices"])
        st.plotly_chart(fig_macd, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 6: CROSS-ASSET PANEL
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### Cross-Asset")
    st.caption(
        "BTC is a risk-on asset. Rising SPX/QQQ = Bullish BTC. Rising VIX = Bearish BTC. "
        "Falling DXY = Bullish BTC."
    )

    cross = ind.get("cross_asset", {})

    xc1, xc2, xc3, xc4, xc5 = st.columns(5)
    cross_items = [
        (xc1, "VIX",       cross.get("vix",           {}), True),   # rising VIX = bearish BTC
        (xc2, "S&P 500",   cross.get("spx",           {}), False),  # rising SPX = bullish BTC
        (xc3, "QQQ",       cross.get("qqq",           {}), False),  # rising QQQ = bullish BTC
        (xc4, "EUR/USD",   cross.get("eurusd",        {}), False),  # rising EURUSD = bullish BTC (weak USD)
        (xc5, "BTC/Gold",  cross.get("btc_gold_ratio",{}), False),  # rising = BTC outperforming gold
    ]

    for col, label, d, invert_pos in cross_items:
        val = d.get("value")
        chg = d.get("weekly_chg")
        arrow_str, is_pos = _arrow(chg)
        # BTC-bullish direction
        if is_pos is None:
            btc_pos = None
        elif label == "VIX":
            btc_pos = not is_pos    # rising VIX = bearish BTC
        else:
            btc_pos = is_pos        # all others: rising = bullish BTC
        with col:
            metric_card(label, _fmt(val, 4 if "USD" in label else 2),
                        f"{arrow_str} wk", change_positive=btc_pos)

    fig_cross = charts.chart_cross_asset(data["prices"])
    st.plotly_chart(fig_cross, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # SECTION 7: ICT TRADE IDEAS
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### ICT Trade Ideas (Daily)")
    st.caption(
        "Educational ICT analysis only — not financial advice. "
        "Concepts applied: Market Structure · Order Blocks · Fair Value Gaps · Fibonacci OTE (0.618–0.705) · Key Levels"
    )

    monthly_df_ict = data.get("monthly_btc", pd.DataFrame())
    weekly_df_ict  = data.get("weekly_btc",  pd.DataFrame())
    daily_df_ict   = data.get("daily_btc",   pd.DataFrame())

    if monthly_df_ict.empty or weekly_df_ict.empty or daily_df_ict.empty:
        st.warning("ICT data unavailable — price DataFrames not loaded. Click Refresh Data.")
    else:
        with st.spinner("Running ICT analysis..."):
            ict_trades     = ict_analysis.generate_ict_trades(
                monthly_df_ict, weekly_df_ict, daily_df_ict, bias["score"])
            ict_key_levels = ict_analysis.get_key_levels(monthly_df_ict, weekly_df_ict)
            sh, sl, _      = ict_analysis._find_major_swing(daily_df_ict, lookback_bars=30)
            if sh - sl < float(daily_df_ict["Close"].iloc[-1]) * 0.01:
                sh, sl, _ = ict_analysis._find_major_swing(daily_df_ict, lookback_bars=60)
            ict_fib        = ict_analysis.calc_fibonacci_levels(sh, sl)
            all_fvgs       = (
                [f for f in ict_analysis.find_fvgs(weekly_df_ict) if not f["filled"]] +
                [f for f in ict_analysis.find_fvgs(daily_df_ict)  if not f["filled"]]
            )
            all_obs        = (
                [o for o in ict_analysis.find_order_blocks(weekly_df_ict) if o["valid"]] +
                [o for o in ict_analysis.find_order_blocks(daily_df_ict)  if o["valid"]]
            )

        # ── Key levels summary row ─────────────────────────────────────
        kl = ict_key_levels
        kl1, kl2, kl3, kl4 = st.columns(4)
        with kl1:
            metric_card("Prev Month High (PMH)", _fmt_btc(kl.get("PMH")))
        with kl2:
            metric_card("Prev Month Low (PML)",  _fmt_btc(kl.get("PML")))
        with kl3:
            metric_card("Prev Week High (PWH)",  _fmt_btc(kl.get("PWH")))
        with kl4:
            metric_card("Prev Week Low (PWL)",   _fmt_btc(kl.get("PWL")))

        # Fibonacci summary
        if ict_fib:
            fifty = ict_fib.get(0.5)
            ote_l = ict_fib.get(0.618)
            ote_h = ict_fib.get(0.705)
            current_btc = ind.get("btc_price")
            zone_label = ""
            if current_btc and fifty:
                zone_label = "🔵 Discount Zone" if current_btc < fifty else "🔴 Premium Zone"
            st.markdown(
                f"<div style='font-size:12px; color:#888; margin: 4px 0 12px 0;'>"
                f"Swing: ${_fmt(ict_fib.get('swing_low'), 0)} → ${_fmt(ict_fib.get('swing_high'), 0)} &nbsp;|&nbsp; "
                f"50% (mid): <strong style='color:#FFD740;'>${_fmt(fifty, 0)}</strong> &nbsp;|&nbsp; "
                f"OTE Zone: ${_fmt(ote_h, 0)} – ${_fmt(ote_l, 0)} &nbsp;|&nbsp; {zone_label}"
                f"</div>",
                unsafe_allow_html=True,
            )

        # ── 3 Trade Cards ─────────────────────────────────────────────
        tc1, tc2, tc3 = st.columns(3)
        trade_titles = [
            "Trade 1 — Primary Trend",
            "Trade 2 — OTE Retracement",
            "Trade 3 — Liquidity Hunt",
        ]

        for col, trade, title in zip([tc1, tc2, tc3], ict_trades, trade_titles):
            d    = trade["direction"]
            conf = trade["confidence"]
            is_low = (conf == "LOW")

            badge_color = "#00C853" if d == "LONG" else ("#D50000" if d == "SHORT" else "#FFD740")
            conf_color  = (
                "#00C853" if conf == "HIGH"
                else ("#FFD740" if conf == "MEDIUM"
                      else "#888888")
            )
            card_opacity = "0.55" if is_low else "1.0"
            card_border  = "1px solid #444" if is_low else ""
            card_style   = (f"opacity:{card_opacity}; border:{card_border};" if is_low else "")

            low_banner = (
                f'<div style="background:#FF6D0022; border:1px solid #FF6D00; '
                f'border-radius:4px; padding:4px 8px; margin-bottom:8px; '
                f'font-size:10px; color:#FF6D00; text-align:center;">'
                f'LOW SIGNAL — avoid or use minimal size</div>'
            ) if is_low else ""

            with col:
                st.markdown(f"""
                <div class="metric-card" style="{card_style}">
                    {low_banner}
                    <div style="font-size:11px; color:#888; margin-bottom:6px;">{title}</div>
                    <div style="text-align:center; margin-bottom:10px;">
                        <span class="score-pill"
                              style="background:{badge_color}33; color:{badge_color};
                                     border:2px solid {badge_color}; font-size:14px; padding:4px 16px;">
                            {d}
                        </span>
                    </div>
                    <div class="metric-label" style="margin-bottom:6px;">{trade['setup_name']}</div>
                    <div style="font-size:12px; color:#FAFAFA; line-height:1.8;">
                        <b>Entry:</b> &nbsp;${_fmt(trade['entry'], 0)}<br>
                        <b>Stop: </b> &nbsp;${_fmt(trade['stop'],  0)}<br>
                        <b>TP1:  </b> &nbsp;${_fmt(trade['target1'], 0)}
                            <span style="color:#888; font-size:11px;">&nbsp;(R:R {_fmt(trade['rr1'], 2)})</span><br>
                        <b>TP2:  </b> &nbsp;${_fmt(trade['target2'], 0)}
                            <span style="color:#888; font-size:11px;">&nbsp;(R:R {_fmt(trade['rr2'], 2)})</span>
                    </div>
                    <div style="margin:8px 0 4px; font-size:11px;">
                        Confidence: <span style="color:{conf_color}; font-weight:700;">{conf}</span>
                        &nbsp;|&nbsp; TF: <span style="color:#888;">{trade['timeframe']}</span>
                    </div>
                    <div style="font-size:11px; color:#aaa; line-height:1.5; border-top:1px solid #2A2D35; padding-top:6px;">
                        {trade['rationale']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if trade.get("key_levels_used"):
                    st.caption("📌 " + " · ".join(trade["key_levels_used"]))

        # ── ICT Chart ─────────────────────────────────────────────────
        fig_ict = charts.chart_ict_levels(
            daily_df=daily_df_ict,
            weekly_df=weekly_df_ict,
            trades=ict_trades,
            key_levels=ict_key_levels,
            fvgs=all_fvgs,
            obs=all_obs,
            fib=ict_fib,
        )
        st.plotly_chart(fig_ict, use_container_width=True, config={"displayModeBar": False})

    # ════════════════════════════════════════════════════════════════════
    # FOOTER
    # ════════════════════════════════════════════════════════════════════
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.caption(
        "Data: Yahoo Finance (prices, ETFs) · FRED API (macro) · CFTC (CME BTC COT) · "
        "Alternative.me (Fear & Greed) — all free sources. "
        "This dashboard is for informational purposes only. Not financial advice."
    )


if __name__ == "__main__":
    main()
