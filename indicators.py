# =============================================================================
# Bitcoin Weekly Bias Dashboard — Indicator Calculations
# =============================================================================
import numpy as np
import pandas as pd

import config


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _safe_last(series: pd.Series, n: int = 1) -> float | None:
    """Return the last n-th value of a series, or None if too short."""
    s = series.dropna()
    if len(s) < n:
        return None
    return float(s.iloc[-n])


def pct_change_weekly(series: pd.Series) -> float | None:
    """Percent change last close vs previous close."""
    s = series.dropna()
    if len(s) < 2:
        return None
    return float((s.iloc[-1] / s.iloc[-2] - 1) * 100)


def yoy_change(series: pd.Series) -> float | None:
    """Year-over-year percent change using monthly FRED series."""
    s = series.dropna()
    if len(s) < 13:
        return None
    return float((s.iloc[-1] / s.iloc[-13] - 1) * 100)


# ---------------------------------------------------------------------------
# Moving Averages
# ---------------------------------------------------------------------------

def calc_moving_averages(close: pd.Series, periods: list[int] = config.WEEKLY_MA_PERIODS) -> dict:
    """
    Returns dict with MA values and price-vs-MA status.
    {period: {"ma": float, "above": bool, "pct_diff": float}}
    """
    result = {}
    price = _safe_last(close)
    if price is None:
        return result
    for p in periods:
        ma = close.rolling(p).mean()
        ma_val = _safe_last(ma)
        if ma_val is None:
            continue
        result[p] = {
            "ma": round(ma_val, 2),
            "above": price > ma_val,
            "pct_diff": round((price / ma_val - 1) * 100, 2),
        }
    return result


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

def calc_rsi(close: pd.Series, period: int = config.RSI_PERIOD) -> float | None:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return _safe_last(rsi)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def calc_macd(
    close: pd.Series,
    fast: int = config.MACD_FAST,
    slow: int = config.MACD_SLOW,
    signal: int = config.MACD_SIGNAL,
) -> dict:
    """
    Returns {macd_line, signal_line, histogram, bullish (bool)}.
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    m = _safe_last(macd_line)
    s = _safe_last(signal_line)
    h = _safe_last(histogram)
    h_prev = _safe_last(histogram, 2)

    if None in (m, s, h):
        return {"macd_line": None, "signal_line": None, "histogram": None, "bullish": None}

    return {
        "macd_line":   round(m, 2),
        "signal_line": round(s, 2),
        "histogram":   round(h, 2),
        "bullish":     bool(h > 0),
        "crossing_up": bool(h > 0 and h_prev is not None and h_prev < 0),
    }


# ---------------------------------------------------------------------------
# ATR (Average True Range)
# ---------------------------------------------------------------------------

def calc_atr(df: pd.DataFrame, period: int = 14) -> float | None:
    """Wilder ATR(period) from OHLCV DataFrame; returns most recent value or None."""
    needed = {"High", "Low", "Close"}
    if df.empty or not needed.issubset(df.columns) or len(df) < period + 1:
        return None
    high       = df["High"]
    low        = df["Low"]
    prev_close = df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr_series = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    result = _safe_last(atr_series)
    return round(result, 2) if result is not None else None


# ---------------------------------------------------------------------------
# COT Index (percentile) — reused for CME BTC futures
# ---------------------------------------------------------------------------

def calc_cot_index(cot_df: pd.DataFrame, window: int = config.COT_PERCENTILE_WINDOW) -> dict:
    """
    COT Index = percentile rank of current net speculator position
    over the trailing `window` weeks.
    Returns {net_pos, cot_index (0-100), extreme_long (bool), extreme_short (bool)}
    """
    if cot_df.empty or "noncomm_net" not in cot_df.columns:
        return {"net_pos": None, "cot_index": None, "extreme_long": None, "extreme_short": None}

    net = cot_df["noncomm_net"].dropna()
    if len(net) < 2:
        return {"net_pos": None, "cot_index": None, "extreme_long": None, "extreme_short": None}

    current = float(net.iloc[-1])
    window_data = net.tail(window)
    mn, mx = window_data.min(), window_data.max()
    cot_index = float((current - mn) / (mx - mn) * 100) if mx != mn else 50.0

    return {
        "net_pos":       int(current),
        "cot_index":     round(cot_index, 1),
        "extreme_long":  cot_index > 80,
        "extreme_short": cot_index < 20,
    }


# ---------------------------------------------------------------------------
# Fear & Greed Index snapshot
# ---------------------------------------------------------------------------

def calc_fear_greed_snapshot(fg_df: pd.DataFrame) -> dict:
    """
    Compute current and weekly Fear & Greed reading with percentile context.
    Returns {value, classification, weekly_chg, percentile (0-100), extreme_fear, extreme_greed}
    """
    if fg_df.empty or "value" not in fg_df.columns:
        return {
            "value": None, "classification": "", "weekly_chg": None,
            "percentile": None, "extreme_fear": None, "extreme_greed": None,
        }

    vals = fg_df["value"].dropna()
    if vals.empty:
        return {
            "value": None, "classification": "", "weekly_chg": None,
            "percentile": None, "extreme_fear": None, "extreme_greed": None,
        }

    current = float(vals.iloc[-1])
    prev    = float(vals.iloc[-8]) if len(vals) >= 8 else None   # ~1 week ago
    weekly_chg = round(current - prev, 1) if prev is not None else None

    window = vals.tail(config.FEAR_GREED_PERCENTILE_WINDOW * 7)
    mn, mx = window.min(), window.max()
    percentile = float((current - mn) / (mx - mn) * 100) if mx != mn else 50.0

    classification = ""
    if not fg_df.empty and "classification" in fg_df.columns:
        last_class = fg_df["classification"].dropna()
        if not last_class.empty:
            classification = str(last_class.iloc[-1])

    return {
        "value":          int(current),
        "classification": classification,
        "weekly_chg":     weekly_chg,
        "percentile":     round(percentile, 1),
        "extreme_fear":   current < 20,
        "extreme_greed":  current > 80,
    }


# ---------------------------------------------------------------------------
# BTC ETF Flow (shares outstanding delta)
# ---------------------------------------------------------------------------

def calc_btc_etf_flow(prices: dict, etf_shares: dict) -> dict:
    """
    For each BTC ETF, approximate weekly flow = price momentum direction.
    Returns per-ETF and combined metrics.
    """
    etf_keys = ["ibit", "fbtc", "gbtc", "arkb", "hodl", "bitb"]
    result = {}
    total_flow_proxy = 0.0
    n_valid = 0

    for key in etf_keys:
        close = prices.get(key, pd.DataFrame()).get("Close", pd.Series())
        shares = etf_shares.get(key)
        price = _safe_last(close)
        price_prev = _safe_last(close, 2)

        if price is None or price_prev is None:
            result[key] = {
                "price": None, "weekly_chg_pct": None,
                "aum_m": None, "flow_direction": "unknown"
            }
            continue

        weekly_chg_pct = round((price / price_prev - 1) * 100, 2)
        aum_m = round((shares * price / 1e6), 1) if shares else None

        flow_direction = "inflow" if weekly_chg_pct > 0 else "outflow"
        total_flow_proxy += weekly_chg_pct
        n_valid += 1

        result[key] = {
            "price":          round(price, 2),
            "weekly_chg_pct": weekly_chg_pct,
            "aum_m":          aum_m,
            "flow_direction": flow_direction,
            "shares":         shares,
        }

    # BTC/ETH ratio trend
    btc_close = prices.get("btc", pd.DataFrame()).get("Close", pd.Series())
    eth_close = prices.get("eth", pd.DataFrame()).get("Close", pd.Series())

    def _ratio_trend(a: pd.Series, b: pd.Series) -> str | None:
        av, ap = _safe_last(a), _safe_last(a, 2)
        bv, bp = _safe_last(b), _safe_last(b, 2)
        if None in (av, ap, bv, bp) or bv == 0 or bp == 0:
            return None
        return "rising" if (av / bv) > (ap / bp) else "falling"

    result["btc_eth_ratio_trend"] = _ratio_trend(btc_close, eth_close)
    result["combined_flow_avg_pct"] = round(total_flow_proxy / n_valid, 2) if n_valid else None

    return result


# ---------------------------------------------------------------------------
# Macro snapshot (same macro drivers as gold: DXY, real yields, Fed policy)
# ---------------------------------------------------------------------------

def calc_macro_snapshot(prices: dict, fred: dict) -> dict:
    """Build a single dict of current macro readings for BTC bias."""
    def last(series: pd.Series) -> float | None:
        return _safe_last(series) if not series.empty else None

    def delta(series: pd.Series) -> float | None:
        s = series.dropna()
        if len(s) < 2:
            return None
        return float(s.iloc[-1] - s.iloc[-2])

    dxy_close = prices.get("dxy", pd.DataFrame()).get("Close", pd.Series())

    def _resample_weekly(s: pd.Series) -> pd.Series:
        if s.empty or not isinstance(s.index, pd.DatetimeIndex):
            return pd.Series(dtype=float)
        return s.resample("W").last()

    t2y  = _resample_weekly(fred.get("treasury_2y",  pd.Series()))
    t10y = _resample_weekly(fred.get("treasury_10y", pd.Series()))

    t2y_val  = last(t2y)
    t10y_val = last(t10y)
    yield_curve = round(t10y_val - t2y_val, 3) if (t2y_val and t10y_val) else None
    yield_curve_prev = None
    if not t2y.empty and not t10y.empty:
        p2  = _safe_last(t2y, 2)
        p10 = _safe_last(t10y, 2)
        yield_curve_prev = round(p10 - p2, 3) if (p2 and p10) else None

    # M2 money supply (expanding M2 = more liquidity = bullish BTC)
    m2_series = fred.get("m2", pd.Series())
    m2_val = last(m2_series)
    m2_delta = delta(m2_series)
    m2_yoy = yoy_change(m2_series)

    return {
        "dxy": {
            "value":      last(dxy_close),
            "weekly_chg": pct_change_weekly(dxy_close),
        },
        "real_yield_10y": {
            "value": last(fred.get("real_yield_10y", pd.Series())),
            "delta": delta(fred.get("real_yield_10y", pd.Series())),
        },
        "breakeven_10y": {
            "value": last(fred.get("breakeven_10y", pd.Series())),
            "delta": delta(fred.get("breakeven_10y", pd.Series())),
        },
        "fed_funds": {
            "value": last(fred.get("fed_funds", pd.Series())),
            "delta": delta(fred.get("fed_funds", pd.Series())),
        },
        "cpi_yoy": {
            "value": yoy_change(fred.get("cpi_yoy", pd.Series())),
        },
        "pce_yoy": {
            "value": yoy_change(fred.get("pce_yoy", pd.Series())),
        },
        "treasury_2y": {
            "value": t2y_val,
            "delta": delta(t2y),
        },
        "treasury_10y": {
            "value": t10y_val,
            "delta": delta(t10y),
        },
        "yield_curve": {
            "value":      yield_curve,
            "prev":       yield_curve_prev,
            "steepening": (yield_curve > yield_curve_prev) if (yield_curve and yield_curve_prev) else None,
        },
        "m2": {
            "value":   m2_val,
            "delta":   m2_delta,
            "yoy_pct": m2_yoy,
        },
    }


# ---------------------------------------------------------------------------
# Cross-asset snapshot (BTC-specific: SPX positive, VIX negative)
# ---------------------------------------------------------------------------

def calc_cross_asset_snapshot(prices: dict) -> dict:
    """Build cross-asset snapshot adapted for BTC correlations."""
    def _last(key: str) -> float | None:
        s = prices.get(key, pd.DataFrame()).get("Close", pd.Series())
        return _safe_last(s)

    def _chg(key: str) -> float | None:
        s = prices.get(key, pd.DataFrame()).get("Close", pd.Series())
        return pct_change_weekly(s)

    # BTC/Gold ratio
    btc_price  = _last("btc")
    gold_price = _last("gold")
    btc_gold_ratio = round(btc_price / gold_price, 4) if (btc_price and gold_price and gold_price != 0) else None
    btc_gold_close = (
        prices.get("btc",  pd.DataFrame()).get("Close", pd.Series()) /
        prices.get("gold", pd.DataFrame()).get("Close", pd.Series())
    ).dropna() if (not prices.get("btc", pd.DataFrame()).empty and
                   not prices.get("gold", pd.DataFrame()).empty) else pd.Series()

    return {
        "vix":    {"value": _last("vix"),    "weekly_chg": _chg("vix")},
        "spx":    {"value": _last("spx"),    "weekly_chg": _chg("spx")},
        "eurusd": {"value": _last("eurusd"), "weekly_chg": _chg("eurusd")},
        "qqq":    {"value": _last("qqq"),    "weekly_chg": _chg("qqq")},
        "btc_gold_ratio": {
            "value":      btc_gold_ratio,
            "weekly_chg": pct_change_weekly(btc_gold_close) if not btc_gold_close.empty else None,
        },
    }


# ---------------------------------------------------------------------------
# Master indicator builder
# ---------------------------------------------------------------------------

def build_all_indicators(data: dict) -> dict:
    """
    Takes the raw data dict from fetch_all_data() and returns
    a fully computed indicator snapshot for BTC bias scoring.
    """
    prices     = data["prices"]
    etf_shares = data["etf_shares"]
    fred       = data["fred"]
    cot        = data["cot"]
    fear_greed = data["fear_greed"]

    btc_close = prices.get("btc", pd.DataFrame()).get("Close", pd.Series())
    eth_close = prices.get("eth", pd.DataFrame()).get("Close", pd.Series())

    # BTC/ETH ratio series
    btc_eth_ratio_series = (btc_close / eth_close).dropna() if (
        not btc_close.empty and not eth_close.empty
    ) else pd.Series()

    btc_eth_val = round(
        float(btc_close.iloc[-1]) / float(eth_close.iloc[-1]), 4
    ) if (len(btc_close) >= 1 and len(eth_close) >= 1 and float(eth_close.iloc[-1]) != 0) else None

    etf_data = calc_btc_etf_flow(prices, etf_shares)

    return {
        "btc_price":       _safe_last(btc_close),
        "btc_weekly_chg":  pct_change_weekly(btc_close),
        "macro":           calc_macro_snapshot(prices, fred),
        "technical": {
            "moving_averages": calc_moving_averages(btc_close),
            "rsi":             calc_rsi(btc_close),
            "macd":            calc_macd(btc_close),
        },
        "sentiment": {
            "fear_greed":    calc_fear_greed_snapshot(fear_greed),
            "fear_greed_df": fear_greed,
            "cot":           calc_cot_index(cot),
            "cot_df":        cot,
            "etf":           etf_data,
            "btc_eth_ratio": {
                "value":      btc_eth_val,
                "weekly_chg": pct_change_weekly(btc_eth_ratio_series),
            },
        },
        "cross_asset": calc_cross_asset_snapshot(prices),
        "prices":      prices,
    }
