#!/usr/bin/env python3
import argparse
import csv
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import duckdb
import numpy as np
import pandas as pd


FLOW_WINDOW_MS = 3600
HIST_WINDOW_SEC = 3600
Z_THRESHOLD = 2.0
HOLDS = [5, 10, 20, 30, 60, 120, 300]
TRADE_SIZE = 100.0
CEX_FEE = 0.000153
BUCKET = "s3://zly/crypto-alpha/raw"
STRATEGY_NAME = "short_book_resonance_divergence"
SIGNAL_RULE = "book_resonance_raw & pre_ret_3s < 0 & obi > 0"
DEX_NOTIONAL_SCALE = 654.0

FLOW_WINDOW_NS = FLOW_WINDOW_MS * 1_000_000
HIST_WINDOW_NS = HIST_WINDOW_SEC * 1_000_000_000

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs" / "short_book_resonance_divergence_universe_backtest"
DEFAULT_SUMMARY_CACHE = ROOT_DIR / "alpha_futures_dex_universe_backtest" / "universe_backtest_summary.csv"
DEFAULT_COMPACT_SYMBOL_MAP = ROOT_DIR / "config" / "alpha_usdt_symbol_map_compact.json"


@dataclass(frozen=True)
class TokenSpec:
    token_symbol: str
    token_name: str
    alpha_symbol_path: str
    cex_pair_key: str
    display: Optional[str] = None


def duck_setup():
    key_id = os.getenv("ALPHA_S3_KEY_ID")
    secret = os.getenv("ALPHA_S3_SECRET")
    if not key_id or not secret:
        raise RuntimeError("Missing ALPHA_S3_KEY_ID or ALPHA_S3_SECRET environment variables.")
    s3_opts = {
        "KEY_ID": key_id,
        "SECRET": secret,
        "REGION": os.getenv("ALPHA_S3_REGION", "us-east-1"),
        "ENDPOINT": os.getenv("ALPHA_S3_ENDPOINT", "192.168.1.130:9000"),
        "URL_STYLE": os.getenv("ALPHA_S3_URL_STYLE", "path"),
        "USE_SSL": os.getenv("ALPHA_S3_USE_SSL", "false").lower() == "true",
    }
    con = duckdb.connect(":memory:")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        f"""
        CREATE SECRET zly (
            TYPE S3,
            KEY_ID '{s3_opts["KEY_ID"]}',
            SECRET '{s3_opts["SECRET"]}',
            REGION '{s3_opts["REGION"]}',
            ENDPOINT '{s3_opts["ENDPOINT"]}',
            URL_STYLE '{s3_opts["URL_STYLE"]}',
            USE_SSL {str(s3_opts["USE_SSL"]).lower()}
        );
        """
    )
    return con


def idx_le(arr, ts):
    i = np.searchsorted(arr, ts, side="right") - 1
    return i if i >= 0 else None


def idx_ge(arr, ts):
    i = np.searchsorted(arr, ts, side="left")
    return i if i < len(arr) else None


def fmt_ns(ts):
    if ts is None or ts <= 0:
        return None
    return pd.to_datetime(int(ts), unit="ns").strftime("%Y-%m-%d %H:%M:%S.%f")


def rolling_sum_at_queries(event_ts, event_vals, query_ts, window_ns):
    if len(event_ts) == 0:
        return np.zeros(len(query_ts), dtype=float)
    prefix = np.concatenate([[0.0], np.cumsum(event_vals, dtype=float)])
    right = np.searchsorted(event_ts, query_ts, side="right")
    left = np.searchsorted(event_ts, query_ts - window_ns, side="right")
    return prefix[right] - prefix[left]


def rolling_z_on_event_series(values, query_ts, hist_window_ns):
    values = np.asarray(values, dtype=float)
    prefix = np.concatenate([[0.0], np.cumsum(values, dtype=float)])
    prefix2 = np.concatenate([[0.0], np.cumsum(values * values, dtype=float)])
    starts = np.searchsorted(query_ts, query_ts - hist_window_ns, side="left")
    idx = np.arange(len(query_ts))
    n = idx - starts
    hist_sum = prefix[idx] - prefix[starts]
    hist_sum2 = prefix2[idx] - prefix2[starts]
    mean = np.zeros(len(values), dtype=float)
    std = np.zeros(len(values), dtype=float)
    valid = n >= 10
    mean[valid] = hist_sum[valid] / n[valid]
    var = np.zeros(len(values), dtype=float)
    var[valid] = hist_sum2[valid] / n[valid] - mean[valid] * mean[valid]
    var[var < 0] = 0
    std[valid] = np.sqrt(var[valid])
    z = np.zeros(len(values), dtype=float)
    ok = valid & (std > 0)
    z[ok] = (values[ok] - mean[ok]) / std[ok]
    return z, n


def _normalize_trade_frame(df):
    for c in ["recv_timestamp_ns", "price", "quantity"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["recv_timestamp_ns", "price", "quantity"]).copy()
    df = df.sort_values("recv_timestamp_ns")
    return df


def _normalize_dex_frame(df):
    for c in [
        "recv_timestamp_ms",
        "token_amount_in",
        "token_amount_out",
        "stable_amount_in",
        "stable_amount_out",
    ]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["recv_timestamp_ms"]).copy()
    df = df.sort_values("recv_timestamp_ms")
    return df


def _normalize_book_frame(df):
    for c in ["recv_timestamp_ns", "bid_price", "bid_qty", "ask_price", "ask_qty"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["recv_timestamp_ns", "bid_price", "ask_price"]).copy()
    df = df.sort_values("recv_timestamp_ns")
    return df


def load_inputs(con, token: TokenSpec, date: str):
    trade_glob = (
        f"{BUCKET}/exchange=binance-alpha-cex/market=futures/"
        f"exchange_pair_key={token.cex_pair_key}/data_type=trade/date={date}/hour=*/*.csv.zst"
    )
    trade_df = con.execute(
        f"""
        SELECT recv_timestamp_ns, price, quantity, side
        FROM read_csv('{trade_glob}', AUTO_DETECT=true, IGNORE_ERRORS=true)
        WHERE price > 0 AND quantity > 0
        """
    ).fetchdf()
    trade_df = _normalize_trade_frame(trade_df)
    if trade_df.empty:
        raise RuntimeError(f"trade data empty for {token.cex_pair_key} on {date}")
    trade_ts = trade_df["recv_timestamp_ns"].astype(np.int64).to_numpy()
    trade_vals = (trade_df["price"] * trade_df["quantity"]).astype(float).to_numpy()
    trade_side = trade_df["side"].astype(str).str.lower()
    trade_buy_vals = np.where(trade_side.str.contains("buy").to_numpy(), trade_vals, 0.0)
    trade_sell_vals = np.where(trade_side.str.contains("sell").to_numpy(), trade_vals, 0.0)

    swap_glob = (
        f"{BUCKET}/exchange=binance/symbol={token.alpha_symbol_path}/"
        f"data_type=onchain_swap/date={date}/hour=*/*.csv.zst"
    )
    dex_df = con.execute(
        f"""
        SELECT recv_timestamp_ms, event_type,
               token_amount_in, token_amount_out, stable_amount_in, stable_amount_out
        FROM read_csv('{swap_glob}', AUTO_DETECT=true, IGNORE_ERRORS=true)
        WHERE event_type LIKE '%swap%'
        """
    ).fetchdf()
    dex_df = _normalize_dex_frame(dex_df)
    if dex_df.empty:
        raise RuntimeError(f"dex data empty for {token.alpha_symbol_path} on {date}")
    dex_df["vol_dex"] = 0.0
    dex_df["dir"] = 0
    token_in_mask = dex_df["token_amount_in"].fillna(0) > 0
    stable_in_mask = dex_df["stable_amount_in"].fillna(0) > 0
    dex_df.loc[token_in_mask, "dir"] = 1
    dex_df.loc[stable_in_mask, "dir"] = -1
    dex_df.loc[token_in_mask, "vol_dex"] = (
        dex_df.loc[token_in_mask, "stable_amount_out"].fillna(0) / 1e18 * DEX_NOTIONAL_SCALE
    )
    dex_df.loc[stable_in_mask, "vol_dex"] = (
        dex_df.loc[stable_in_mask, "stable_amount_in"].fillna(0) / 1e18 * DEX_NOTIONAL_SCALE
    )
    dex_ts = dex_df["recv_timestamp_ms"].astype(np.int64).to_numpy() * 1_000_000
    dex_vals = dex_df["vol_dex"].astype(float).to_numpy()
    dex_buy_vals = np.where(dex_df["dir"].to_numpy() == 1, dex_vals, 0.0)
    dex_sell_vals = np.where(dex_df["dir"].to_numpy() == -1, dex_vals, 0.0)

    book_glob = (
        f"{BUCKET}/exchange=binance-alpha-cex/market=futures/"
        f"exchange_pair_key={token.cex_pair_key}/data_type=book_ticker/date={date}/hour=*/*.csv.zst"
    )
    book_df = con.execute(
        f"""
        SELECT recv_timestamp_ns, bid_price, bid_qty, ask_price, ask_qty
        FROM read_csv('{book_glob}', AUTO_DETECT=true, IGNORE_ERRORS=true)
        WHERE bid_price > 0 AND ask_price > 0 AND bid_qty >= 0 AND ask_qty >= 0
        """
    ).fetchdf()
    book_df = _normalize_book_frame(book_df)
    if book_df.empty:
        raise RuntimeError(f"book data empty for {token.cex_pair_key} on {date}")
    book_df["bid_notional"] = book_df["bid_price"] * book_df["bid_qty"].fillna(0)
    book_df["ask_notional"] = book_df["ask_price"] * book_df["ask_qty"].fillna(0)
    book_df["top1_notional"] = book_df["bid_notional"] + book_df["ask_notional"]
    book_df["book_delta_abs"] = book_df["top1_notional"].diff().abs().fillna(0.0)
    book_ts = book_df["recv_timestamp_ns"].astype(np.int64).to_numpy()
    book_vals = book_df["book_delta_abs"].astype(float).to_numpy()

    return {
        "trade_ts": trade_ts,
        "trade_vals": trade_vals,
        "trade_buy_vals": trade_buy_vals,
        "trade_sell_vals": trade_sell_vals,
        "dex_ts": dex_ts,
        "dex_vals": dex_vals,
        "dex_buy_vals": dex_buy_vals,
        "dex_sell_vals": dex_sell_vals,
        "book_ts": book_ts,
        "book_vals": book_vals,
        "book_df": book_df,
    }


def build_signal_frame(inputs):
    trade_ts = inputs["trade_ts"]
    trade_vals = inputs["trade_vals"]
    trade_buy_vals = inputs["trade_buy_vals"]
    trade_sell_vals = inputs["trade_sell_vals"]
    dex_ts = inputs["dex_ts"]
    dex_vals = inputs["dex_vals"]
    dex_buy_vals = inputs["dex_buy_vals"]
    dex_sell_vals = inputs["dex_sell_vals"]
    book_ts = inputs["book_ts"]
    book_vals = inputs["book_vals"]
    book_df = inputs["book_df"]

    query_ts = np.unique(np.concatenate([trade_ts, dex_ts, book_ts]))
    trade_roll = rolling_sum_at_queries(trade_ts, trade_vals, query_ts, FLOW_WINDOW_NS)
    trade_buy_roll = rolling_sum_at_queries(trade_ts, trade_buy_vals, query_ts, FLOW_WINDOW_NS)
    trade_sell_roll = rolling_sum_at_queries(trade_ts, trade_sell_vals, query_ts, FLOW_WINDOW_NS)
    dex_roll = rolling_sum_at_queries(dex_ts, dex_vals, query_ts, FLOW_WINDOW_NS)
    dex_buy_roll = rolling_sum_at_queries(dex_ts, dex_buy_vals, query_ts, FLOW_WINDOW_NS)
    dex_sell_roll = rolling_sum_at_queries(dex_ts, dex_sell_vals, query_ts, FLOW_WINDOW_NS)
    book_roll = rolling_sum_at_queries(book_ts, book_vals, query_ts, FLOW_WINDOW_NS)

    z_trade, n_trade = rolling_z_on_event_series(trade_roll, query_ts, HIST_WINDOW_NS)
    z_dex, n_dex = rolling_z_on_event_series(dex_roll, query_ts, HIST_WINDOW_NS)
    z_book, n_book = rolling_z_on_event_series(book_roll, query_ts, HIST_WINDOW_NS)

    has_trade_update = np.zeros(len(query_ts), dtype=bool)
    has_dex_update = np.zeros(len(query_ts), dtype=bool)
    has_book_update = np.zeros(len(query_ts), dtype=bool)
    has_trade_update[np.searchsorted(query_ts, trade_ts)] = True
    has_dex_update[np.searchsorted(query_ts, dex_ts)] = True
    has_book_update[np.searchsorted(query_ts, book_ts)] = True

    burn_ts = query_ts[0] + HIST_WINDOW_NS
    valid = query_ts > burn_ts

    trade_state = valid & (n_trade >= 10) & (trade_roll > 0) & (z_trade > Z_THRESHOLD)
    dex_state = valid & (n_dex >= 10) & (dex_roll > 0) & (z_dex > Z_THRESHOLD)
    book_state = valid & (n_book >= 10) & (book_roll > 0) & (z_book > Z_THRESHOLD)

    def rising_edge(state, relevant):
        prev = np.r_[False, state[:-1]]
        return state & ~prev & relevant

    frame = pd.DataFrame(
        {
            "signal_ns": query_ts,
            "signal_time": pd.to_datetime(query_ts, unit="ns"),
            "trade_roll_3600ms": trade_roll,
            "trade_buy_roll_3600ms": trade_buy_roll,
            "trade_sell_roll_3600ms": trade_sell_roll,
            "dex_roll_3600ms": dex_roll,
            "dex_buy_roll_3600ms": dex_buy_roll,
            "dex_sell_roll_3600ms": dex_sell_roll,
            "book_roll_3600ms": book_roll,
            "z_trade": z_trade,
            "z_dex": z_dex,
            "z_book": z_book,
            "book_resonance_raw": rising_edge(book_state & dex_state, has_book_update | has_dex_update),
        }
    )
    trade_tot = frame["trade_buy_roll_3600ms"] + frame["trade_sell_roll_3600ms"]
    frame["obi"] = np.where(
        trade_tot > 0,
        (frame["trade_buy_roll_3600ms"] - frame["trade_sell_roll_3600ms"]) / trade_tot,
        0.0,
    )

    book_bid = book_df["bid_price"].astype(float).to_numpy()
    current_idx = np.searchsorted(book_ts, query_ts, side="right") - 1
    current_idx = np.where(current_idx >= 0, current_idx, -1)
    pre_idx = np.searchsorted(book_ts, query_ts - 3_000_000_000, side="right") - 1
    pre_idx = np.where(pre_idx >= 0, pre_idx, -1)
    current_bid = np.where(current_idx >= 0, book_bid[current_idx], np.nan)
    pre_bid = np.where(pre_idx >= 0, book_bid[pre_idx], np.nan)
    frame["pre_ret_3s"] = np.where(
        (current_idx >= 0) & (pre_idx >= 0) & (pre_bid > 0),
        current_bid / pre_bid - 1.0,
        np.nan,
    )
    frame["short_rule"] = frame["book_resonance_raw"] & (frame["pre_ret_3s"] < 0) & (frame["obi"] > 0)
    return frame


def simulate_short_sell_first_bid_only(book_df, start_idx, target_notional):
    i = int(start_idx)
    if i >= len(book_df):
        return None
    bid = float(book_df.iloc[i]["bid_price"])
    bid_qty = float(book_df.iloc[i]["bid_qty"] or 0.0)
    if bid <= 0:
        return None
    requested_qty = float(target_notional / bid)
    take_qty = min(requested_qty, bid_qty)
    take_notional = float(take_qty * bid)
    return {
        "entry_idx": i,
        "entry_time_ns": int(book_df.iloc[i]["recv_timestamp_ns"]),
        "entry_first_bid": float(bid),
        "entry_vwap": float(bid),
        "entry_qty": float(take_qty),
        "entry_notional": float(take_notional),
        "requested_qty": float(requested_qty),
        "bid_qty_1": float(bid_qty),
        "sell_fill_ratio": float(take_qty / requested_qty) if requested_qty > 0 else 0.0,
    }


def simulate_cover_from_asks(book_df, start_idx, qty_to_cover):
    remaining_qty = float(qty_to_cover)
    cost = 0.0
    cover_qty = 0.0
    last_idx = None
    zero_ask_ticks = 0
    same_price_skips = 0
    ticks_used = 0
    last_ask = None
    i = int(start_idx)
    while i < len(book_df) and remaining_qty > 1e-12:
        ask = float(book_df.iloc[i]["ask_price"])
        ask_qty = float(book_df.iloc[i]["ask_qty"] or 0.0)
        ticks_used += 1
        if ask <= 0 or ask_qty <= 0:
            zero_ask_ticks += 1
            i += 1
            continue
        if last_ask is not None and abs(ask - last_ask) <= 1e-12:
            same_price_skips += 1
            i += 1
            continue
        take_qty = min(remaining_qty, ask_qty)
        cost += take_qty * ask
        cover_qty += take_qty
        remaining_qty -= take_qty
        last_idx = i
        last_ask = ask
        i += 1
    if last_idx is None:
        return {
            "exit_idx": None,
            "exit_time_ns": None,
            "cover_notional": float(cost),
            "cover_qty": float(cover_qty),
            "remaining_qty": float(remaining_qty),
            "zero_ask_ticks": int(zero_ask_ticks),
            "same_price_skips": int(same_price_skips),
            "ticks_used": int(ticks_used),
            "filled": False,
        }
    return {
        "exit_idx": last_idx,
        "exit_time_ns": int(book_df.iloc[last_idx]["recv_timestamp_ns"]),
        "cover_notional": float(cost),
        "cover_qty": float(cover_qty),
        "remaining_qty": float(remaining_qty),
        "zero_ask_ticks": int(zero_ask_ticks),
        "same_price_skips": int(same_price_skips),
        "ticks_used": int(ticks_used),
        "filled": bool(remaining_qty <= 1e-9),
    }


def backtest_short_strategy(frame, book_df):
    book_ts = book_df["recv_timestamp_ns"].astype(np.int64).to_numpy()
    book_recv = book_df["recv_timestamp_ns"].astype(np.int64).to_numpy()
    rows = []
    subset = frame[frame["short_rule"]].copy()
    for r in subset.itertuples(index=False):
        signal_ns = int(r.signal_ns)
        entry_idx = idx_le(book_ts, signal_ns)
        if entry_idx is None:
            continue
        entry_fill = simulate_short_sell_first_bid_only(book_df, int(entry_idx), TRADE_SIZE)
        if not entry_fill:
            continue
        entry_idx = int(entry_fill["entry_idx"])
        entry_time_ns = int(entry_fill["entry_time_ns"])
        entry_first_bid = float(entry_fill["entry_first_bid"])
        entry_vwap = float(entry_fill["entry_vwap"])
        entry_qty = float(entry_fill["entry_qty"])
        entry_notional = float(entry_fill["entry_notional"])
        requested_qty = float(entry_fill["requested_qty"])
        bid_qty_1 = float(entry_fill["bid_qty_1"])
        sell_fill_ratio = float(entry_fill["sell_fill_ratio"])
        if entry_qty <= 0 or entry_notional <= 0:
            continue
        entry_fee = entry_notional * CEX_FEE
        prev_idx = entry_idx - 1 if entry_idx > 0 else None
        if prev_idx is not None:
            prev_bid = float(book_df.iloc[prev_idx]["bid_price"])
            entry_price_chg_rate = (entry_vwap / prev_bid - 1.0) if prev_bid > 0 else None
        else:
            entry_price_chg_rate = None
        row = {
            "strategy": STRATEGY_NAME,
            "signal_time": pd.Timestamp(r.signal_time).strftime("%Y-%m-%d %H:%M:%S.%f"),
            "signal_ns": signal_ns,
            "signal_book_recv_ns": fmt_ns(book_recv[entry_idx]),
            "entry_time": fmt_ns(entry_time_ns),
            "entry_first_bid": round(entry_first_bid, 6),
            "entry_vwap_bid": round(entry_vwap, 6),
            "entry_notional": round(entry_notional, 6),
            "entry_fee": round(entry_fee, 6),
            "requested_qty": round(requested_qty, 6),
            "bid_qty_1": round(bid_qty_1, 6),
            "entry_qty": round(entry_qty, 6),
            "sell_fill_ratio": round(sell_fill_ratio, 6),
            "entry_price_chg_rate": round(entry_price_chg_rate, 8) if entry_price_chg_rate is not None else None,
            "pre_ret_3s": round(float(r.pre_ret_3s), 8) if pd.notna(r.pre_ret_3s) else None,
            "trade_roll_3600ms": round(float(r.trade_roll_3600ms), 6),
            "dex_roll_3600ms": round(float(r.dex_roll_3600ms), 6),
            "book_roll_3600ms": round(float(r.book_roll_3600ms), 6),
            "z_trade": round(float(r.z_trade), 4),
            "z_dex": round(float(r.z_dex), 4),
            "z_book": round(float(r.z_book), 4),
            "obi": round(float(r.obi), 6),
            "signal_rule": SIGNAL_RULE,
        }
        for hold in HOLDS:
            exit_ns = entry_time_ns + hold * 1_000_000_000
            exit_idx = idx_ge(book_ts, exit_ns)
            if exit_idx is None:
                row[f"cover_qty_{hold}s"] = None
                row[f"cover_fill_ratio_{hold}s"] = None
                row[f"zero_ask_ticks_{hold}s"] = None
                row[f"same_price_skips_{hold}s"] = None
                row[f"cover_ticks_used_{hold}s"] = None
                row[f"exit_time_{hold}s"] = None
                row[f"exit_ask_vwap_{hold}s"] = None
                row[f"cover_notional_{hold}s"] = None
                row[f"exit_fee_{hold}s"] = None
                row[f"total_fee_{hold}s"] = None
                row[f"traded_notional_{hold}s"] = None
                row[f"net_pnl_{hold}s"] = None
                row[f"ret_{hold}s"] = None
                continue
            exit_fill = simulate_cover_from_asks(book_df, int(exit_idx), entry_qty)
            cover_qty = float(exit_fill["cover_qty"])
            cover_fill_ratio = cover_qty / entry_qty if entry_qty > 0 else 0.0
            row[f"cover_qty_{hold}s"] = round(cover_qty, 6)
            row[f"cover_fill_ratio_{hold}s"] = round(cover_fill_ratio, 6)
            row[f"zero_ask_ticks_{hold}s"] = int(exit_fill["zero_ask_ticks"])
            row[f"same_price_skips_{hold}s"] = int(exit_fill["same_price_skips"])
            row[f"cover_ticks_used_{hold}s"] = int(exit_fill["ticks_used"])
            row[f"exit_time_{hold}s"] = fmt_ns(exit_fill["exit_time_ns"]) if exit_fill["exit_time_ns"] else None
            if cover_qty <= 0 or not exit_fill["filled"]:
                row[f"exit_ask_vwap_{hold}s"] = None
                row[f"cover_notional_{hold}s"] = None
                row[f"exit_fee_{hold}s"] = None
                row[f"total_fee_{hold}s"] = None
                row[f"traded_notional_{hold}s"] = None
                row[f"net_pnl_{hold}s"] = None
                row[f"ret_{hold}s"] = None
                continue
            cover_notional = float(exit_fill["cover_notional"])
            exit_fee = cover_notional * CEX_FEE
            exit_vwap = cover_notional / cover_qty if cover_qty > 0 else None
            total_fee = entry_fee + exit_fee
            net = entry_notional - entry_fee - cover_notional - exit_fee
            traded_notional = entry_notional + cover_notional
            row[f"exit_ask_vwap_{hold}s"] = round(exit_vwap, 6) if exit_vwap is not None else None
            row[f"cover_notional_{hold}s"] = round(cover_notional, 6)
            row[f"exit_fee_{hold}s"] = round(exit_fee, 6)
            row[f"total_fee_{hold}s"] = round(total_fee, 6)
            row[f"traded_notional_{hold}s"] = round(traded_notional, 6)
            row[f"net_pnl_{hold}s"] = round(float(net), 6)
            row[f"ret_{hold}s"] = round(float(net / TRADE_SIZE), 6)
        rows.append(row)
    return rows


def summarize_hold(rows, hold):
    pnl_values = [float(r[f"net_pnl_{hold}s"]) for r in rows if r.get(f"net_pnl_{hold}s") is not None]
    entry_values = [float(r["entry_notional"]) for r in rows if r.get(f"net_pnl_{hold}s") is not None]
    exit_values = [float(r[f"cover_notional_{hold}s"]) for r in rows if r.get(f"net_pnl_{hold}s") is not None]
    fee_values = [float(r[f"total_fee_{hold}s"]) for r in rows if r.get(f"net_pnl_{hold}s") is not None]
    if not pnl_values:
        return {
            "n": 0,
            "total_pnl": None,
            "mean_pnl": None,
            "median_pnl": None,
            "win_ratio": None,
            "total_entry_notional": None,
            "total_exit_notional": None,
            "total_traded_notional": None,
            "total_fee": None,
        }
    vals = np.asarray(pnl_values, dtype=float)
    total_entry = float(np.sum(entry_values))
    total_exit = float(np.sum(exit_values))
    total_fee = float(np.sum(fee_values))
    return {
        "n": int(len(vals)),
        "total_pnl": float(vals.sum()),
        "mean_pnl": float(vals.mean()),
        "median_pnl": float(np.median(vals)),
        "win_ratio": float((vals > 0).mean()),
        "total_entry_notional": total_entry,
        "total_exit_notional": total_exit,
        "total_traded_notional": total_entry + total_exit,
        "total_fee": total_fee,
    }


def write_csv(path: Path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def date_dir_name(date_str: str):
    return date_str.replace("-", "")


def load_compact_symbol_map(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    specs = []
    for row in data:
        token_symbol = str(row["token_symbol"]).lower()
        specs.append(
            TokenSpec(
                token_symbol=token_symbol,
                token_name=row["token_name"],
                alpha_symbol_path=row["alpha_symbol_path"],
                cex_pair_key=f"{token_symbol}usdt",
                display=row.get("display"),
            )
        )
    return specs


def load_cached_universe(path: Path):
    if not path.exists():
        return []
    seen = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = row["token_symbol"]
            if key in seen:
                continue
            seen[key] = TokenSpec(
                token_symbol=row["token_symbol"],
                token_name=row["token_name"],
                alpha_symbol_path=row["alpha_symbol_path"],
                cex_pair_key=row["cex_pair_key"],
            )
    return sorted(seen.values(), key=lambda item: item.token_symbol)


def select_token_specs(token_whitelist=None):
    mapping_specs = {spec.token_symbol: spec for spec in load_compact_symbol_map(DEFAULT_COMPACT_SYMBOL_MAP)}
    cached_specs = {spec.token_symbol: spec for spec in load_cached_universe(DEFAULT_SUMMARY_CACHE)}
    if token_whitelist:
        resolved = []
        for raw in token_whitelist:
            key = raw.strip().lower()
            if not key:
                continue
            spec = cached_specs.get(key) or mapping_specs.get(key)
            if spec is None:
                raise ValueError(f"unknown token in whitelist: {raw}")
            resolved.append(spec)
        deduped = {spec.token_symbol: spec for spec in resolved}
        return sorted(deduped.values(), key=lambda item: item.token_symbol)
    if cached_specs:
        return sorted(cached_specs.values(), key=lambda item: item.token_symbol)
    return sorted(mapping_specs.values(), key=lambda item: item.token_symbol)


def daterange(start_date: str, end_date: str):
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    current = start
    while current <= end:
        yield current.strftime("%Y-%m-%d")
        current += pd.Timedelta(days=1)


def run_token_day(con, token: TokenSpec, date: str, output_root: Path):
    inputs = load_inputs(con, token, date)
    frame = build_signal_frame(inputs)
    detail_rows = backtest_short_strategy(frame, inputs["book_df"])

    token_dir = output_root / date_dir_name(date) / token.token_symbol
    token_dir.mkdir(parents=True, exist_ok=True)
    if int(frame["short_rule"].sum()) > 0:
        signal_cols = [
            "signal_ns",
            "signal_time",
            "trade_roll_3600ms",
            "trade_buy_roll_3600ms",
            "trade_sell_roll_3600ms",
            "dex_roll_3600ms",
            "dex_buy_roll_3600ms",
            "dex_sell_roll_3600ms",
            "book_roll_3600ms",
            "z_trade",
            "z_dex",
            "z_book",
            "book_resonance_raw",
            "obi",
            "pre_ret_3s",
            "short_rule",
        ]
        frame.loc[:, signal_cols].to_csv(
            token_dir / "signal_frame_short_book_resonance_divergence.csv",
            index=False,
        )
        write_csv(token_dir / "short_book_resonance_divergence_detail.csv", detail_rows)

    summary_rows = []
    hold_stats = {}
    signal_count = int(frame["short_rule"].sum())
    for hold in HOLDS:
        stats = summarize_hold(detail_rows, hold)
        hold_stats[f"{hold}s"] = stats
        summary_rows.append(
            {
                "date": date,
                "strategy": STRATEGY_NAME,
                "direction": "short_only",
                "signal_rule": SIGNAL_RULE,
                "token_symbol": token.token_symbol,
                "token_name": token.token_name,
                "alpha_symbol_path": token.alpha_symbol_path,
                "cex_pair_key": token.cex_pair_key,
                "signal_count": signal_count,
                "hold_sec": hold,
                **stats,
            }
        )

    write_csv(token_dir / "execution_summary.csv", summary_rows)
    (token_dir / "execution_summary.json").write_text(
        json.dumps(
            {
                "date": date,
                "strategy": STRATEGY_NAME,
                "signal_rule": SIGNAL_RULE,
                "flow_window_ms": FLOW_WINDOW_MS,
                "hist_window_sec": HIST_WINDOW_SEC,
                "z_threshold": Z_THRESHOLD,
                "holds_sec": HOLDS,
                "direction": "short_only",
                "trade_size": TRADE_SIZE,
                "cex_fee_one_way": CEX_FEE,
                "entry_rule": "at signal_time latest known bid, only consume level-1 bid on that tick",
                "exit_rule": "from first book tick >= entry_time+hold, buy back from future ask ticks until fully filled; skip repeated ask prices after a fill",
                "token_symbol": token.token_symbol,
                "token_name": token.token_name,
                "alpha_symbol_path": token.alpha_symbol_path,
                "cex_pair_key": token.cex_pair_key,
                "signal_count": signal_count,
                "hold_stats": hold_stats,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary_rows


def aggregate_300s_token_summary(summary_rows):
    grouped = {}
    for row in summary_rows:
        if int(row["hold_sec"]) != 300:
            continue
        key = row["token_symbol"]
        stats = grouped.setdefault(
            key,
            {
                "strategy": STRATEGY_NAME,
                "token_symbol": row["token_symbol"],
                "token_name": row["token_name"],
                "alpha_symbol_path": row["alpha_symbol_path"],
                "cex_pair_key": row["cex_pair_key"],
                "hold_sec": 300,
                "days": 0,
                "signal_count_sum": 0,
                "n_sum": 0,
                "total_pnl_300s_sum": 0.0,
            },
        )
        stats["days"] += 1
        stats["signal_count_sum"] += int(row["signal_count"])
        stats["n_sum"] += int(row["n"] or 0)
        stats["total_pnl_300s_sum"] += float(row["total_pnl"] or 0.0)
    rows = list(grouped.values())
    rows.sort(key=lambda item: item["total_pnl_300s_sum"], reverse=True)
    return rows


def parse_args():
    parser = argparse.ArgumentParser(description="Run the short book resonance divergence universe backtest.")
    parser.add_argument("--start-date", default="2026-05-29")
    parser.add_argument("--end-date", default="2026-06-09")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--tokens", default=None, help="Comma-separated token symbols.")
    return parser.parse_args()


def main():
    args = parse_args()
    token_whitelist = args.tokens.split(",") if args.tokens else None
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    tokens = select_token_specs(token_whitelist)
    summary_rows = []
    failures = []
    con = duck_setup()
    try:
        for token in tokens:
            for date in daterange(args.start_date, args.end_date):
                try:
                    summary_rows.extend(run_token_day(con, token, date, output_dir))
                except Exception as exc:  # noqa: BLE001
                    failures.append(
                        {
                            "date": date,
                            "strategy": STRATEGY_NAME,
                            "token_symbol": token.token_symbol,
                            "token_name": token.token_name,
                            "alpha_symbol_path": token.alpha_symbol_path,
                            "cex_pair_key": token.cex_pair_key,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )
    finally:
        con.close()

    write_csv(output_dir / "universe_backtest_summary.csv", summary_rows)
    (output_dir / "universe_backtest_summary.json").write_text(
        json.dumps(summary_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "universe_backtest_failures.json").write_text(
        json.dumps(failures, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    token_total_rows = aggregate_300s_token_summary(summary_rows)
    write_csv(output_dir / "universe_backtest_300s_token_total_summary.csv", token_total_rows)
    write_csv(
        output_dir / "universe_backtest_300s_short_book_resonance_divergence_token_summary.csv",
        token_total_rows,
    )


if __name__ == "__main__":
    main()
