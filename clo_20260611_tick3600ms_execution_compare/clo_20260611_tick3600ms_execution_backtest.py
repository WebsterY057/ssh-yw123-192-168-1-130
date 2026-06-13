#!/usr/bin/env python3
import csv
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


DATE = "2026-06-11"
FLOW_WINDOW_MS = 3600
HIST_WINDOW_SEC = 3600
Z_THRESHOLD = 2.0
HOLDS = [5, 10, 20, 30, 60, 120, 300]
TRADE_SIZE = 100.0
CEX_FEE = 0.0001530
BUCKET = "s3://zly/crypto-alpha/raw"
OUT_DIR = Path("/home/yw123/clo_20260611_tick3600ms_execution_compare")

FLOW_WINDOW_NS = FLOW_WINDOW_MS * 1_000_000
HIST_WINDOW_NS = HIST_WINDOW_SEC * 1_000_000_000

S3_OPTS = dict(
    KEY_ID="yw123",
    SECRET="yw123456",
    REGION="us-east-1",
    ENDPOINT="192.168.1.130:9000",
    URL_STYLE="path",
    USE_SSL=False,
)

LAYER_ORDER = ["book_only", "book_resonance", "trade_resonance"]


def duck_setup():
    con = duckdb.connect(":memory:")
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(
        f"""
        CREATE SECRET zly (
            TYPE S3,
            KEY_ID '{S3_OPTS["KEY_ID"]}',
            SECRET '{S3_OPTS["SECRET"]}',
            REGION '{S3_OPTS["REGION"]}',
            ENDPOINT '{S3_OPTS["ENDPOINT"]}',
            URL_STYLE '{S3_OPTS["URL_STYLE"]}',
            USE_SSL {str(S3_OPTS["USE_SSL"]).lower()}
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


def load_inputs():
    con = duck_setup()

    trade_glob = (
        f"{BUCKET}/exchange=binance-alpha-cex/market=futures/"
        f"exchange_pair_key=clousdt/data_type=trade/date={DATE}/hour=*/*.csv.zst"
    )
    trade_df = con.execute(
        f"""
        SELECT recv_timestamp_ns, price, quantity, side
        FROM read_csv('{trade_glob}', AUTO_DETECT=true, IGNORE_ERRORS=true)
        WHERE price > 0 AND quantity > 0
        """
    ).fetchdf()
    for c in ["recv_timestamp_ns", "price", "quantity"]:
        trade_df[c] = pd.to_numeric(trade_df[c], errors="coerce")
    trade_df = trade_df.dropna(subset=["recv_timestamp_ns", "price", "quantity"]).copy()
    trade_df = trade_df.sort_values("recv_timestamp_ns")
    trade_ts = trade_df["recv_timestamp_ns"].astype(np.int64).to_numpy()
    trade_vals = (trade_df["price"] * trade_df["quantity"]).astype(float).to_numpy()
    trade_side = trade_df["side"].astype(str).str.lower()
    trade_buy_vals = np.where(trade_side.str.contains("buy").to_numpy(), trade_vals, 0.0)
    trade_sell_vals = np.where(trade_side.str.contains("sell").to_numpy(), trade_vals, 0.0)

    swap_glob = (
        f"{BUCKET}/exchange=binance/symbol=alpha_429usdt/"
        f"data_type=onchain_swap/date={DATE}/hour=*/*.csv.zst"
    )
    dex_df = con.execute(
        f"""
        SELECT recv_timestamp_ms, event_type,
               token_amount_in, token_amount_out, stable_amount_in, stable_amount_out
        FROM read_csv('{swap_glob}', AUTO_DETECT=true, IGNORE_ERRORS=true)
        WHERE event_type LIKE '%swap%'
        """
    ).fetchdf()
    for c in ["recv_timestamp_ms", "token_amount_in", "token_amount_out", "stable_amount_in", "stable_amount_out"]:
        dex_df[c] = pd.to_numeric(dex_df[c], errors="coerce")
    dex_df = dex_df.dropna(subset=["recv_timestamp_ms"]).copy()
    dex_df["vol_dex"] = 0.0
    dex_df["dir"] = 0
    mb = dex_df["token_amount_in"].fillna(0) > 0
    ms = dex_df["stable_amount_in"].fillna(0) > 0
    dex_df.loc[mb, "dir"] = 1
    dex_df.loc[ms, "dir"] = -1
    dex_df.loc[mb, "vol_dex"] = dex_df.loc[mb, "stable_amount_out"].fillna(0) / 1e18 * 654
    dex_df.loc[ms, "vol_dex"] = dex_df.loc[ms, "stable_amount_in"].fillna(0) / 1e18 * 654
    dex_df = dex_df.sort_values("recv_timestamp_ms")
    dex_ts = (dex_df["recv_timestamp_ms"].astype(np.int64).to_numpy() * 1_000_000)
    dex_vals = dex_df["vol_dex"].astype(float).to_numpy()
    dex_buy_vals = np.where(dex_df["dir"].to_numpy() == 1, dex_vals, 0.0)
    dex_sell_vals = np.where(dex_df["dir"].to_numpy() == -1, dex_vals, 0.0)

    book_glob = (
        f"{BUCKET}/exchange=binance-alpha-cex/market=futures/"
        f"exchange_pair_key=clousdt/data_type=book_ticker/date={DATE}/hour=*/*.csv.zst"
    )
    book_df = con.execute(
        f"""
        SELECT recv_timestamp_ns, bid_price, bid_qty, ask_price, ask_qty
        FROM read_csv('{book_glob}', AUTO_DETECT=true, IGNORE_ERRORS=true)
        WHERE bid_price > 0 AND ask_price > 0 AND bid_qty >= 0 AND ask_qty >= 0
        """
    ).fetchdf()
    for c in ["recv_timestamp_ns", "bid_price", "bid_qty", "ask_price", "ask_qty"]:
        book_df[c] = pd.to_numeric(book_df[c], errors="coerce")
    book_df = book_df.dropna(subset=["recv_timestamp_ns", "bid_price", "ask_price"]).copy()
    book_df = book_df.sort_values("recv_timestamp_ns")
    book_df["bid_notional"] = book_df["bid_price"] * book_df["bid_qty"].fillna(0)
    book_df["ask_notional"] = book_df["ask_price"] * book_df["ask_qty"].fillna(0)
    book_df["top1_notional"] = book_df["bid_notional"] + book_df["ask_notional"]
    book_df["book_delta_abs"] = book_df["top1_notional"].diff().abs().fillna(0.0)
    book_ts = book_df["recv_timestamp_ns"].astype(np.int64).to_numpy()
    book_vals = book_df["book_delta_abs"].astype(float).to_numpy()

    con.close()
    return (
        trade_ts, trade_vals, trade_buy_vals, trade_sell_vals,
        dex_ts, dex_vals, dex_buy_vals, dex_sell_vals,
        book_ts, book_vals, book_df
    )


def build_signal_frame(
    trade_ts, trade_vals, trade_buy_vals, trade_sell_vals,
    dex_ts, dex_vals, dex_buy_vals, dex_sell_vals,
    book_ts, book_vals
):
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

    trade_res_state = trade_state & dex_state
    book_res_state = book_state & dex_state
    cex_only_state = trade_state & ~dex_state
    dex_only_state = dex_state & ~trade_state

    def rising_edge(state, relevant):
        prev = np.r_[False, state[:-1]]
        return state & ~prev & relevant

    frame = pd.DataFrame({
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
        "has_trade_update": has_trade_update,
        "has_dex_update": has_dex_update,
        "has_book_update": has_book_update,
        "trade_state": trade_state,
        "dex_state": dex_state,
        "book_state": book_state,
        "book_only": rising_edge(book_state & ~dex_state, has_book_update),
        "trade_resonance": rising_edge(trade_res_state, has_trade_update | has_dex_update),
        "book_resonance": rising_edge(book_res_state, has_book_update | has_dex_update),
    })
    trade_tot = frame["trade_buy_roll_3600ms"] + frame["trade_sell_roll_3600ms"]
    frame["obi"] = np.where(
        trade_tot > 0,
        (frame["trade_buy_roll_3600ms"] - frame["trade_sell_roll_3600ms"]) / trade_tot,
        0.0,
    )
    dex_tot = frame["dex_buy_roll_3600ms"] + frame["dex_sell_roll_3600ms"]
    dex_buy_pct = np.where(dex_tot > 0, frame["dex_buy_roll_3600ms"] / dex_tot * 100.0, 50.0)
    frame["dir_dex"] = np.select(
        [dex_buy_pct > 55.0, dex_buy_pct < 45.0],
        ["buy", "sell"],
        default="neutral",
    )
    return frame


def simulate_buy_first_ask_only(book_df, start_idx, target_notional):
    i = int(start_idx)
    if i >= len(book_df):
        return None
    ask = float(book_df.iloc[i]["ask_price"])
    ask_qty = float(book_df.iloc[i]["ask_qty"] or 0.0)
    if ask <= 0:
        return None
    requested_qty = float(target_notional / ask)
    take_qty = min(requested_qty, ask_qty)
    take_notional = float(take_qty * ask)
    return {
        "entry_idx": i,
        "entry_time_ns": int(book_df.iloc[i]["recv_timestamp_ns"]),
        "entry_first_ask": float(ask),
        "entry_vwap": float(ask),
        "entry_qty": float(take_qty),
        "entry_notional": float(take_notional),
        "requested_qty": float(requested_qty),
        "ask_qty_1": float(ask_qty),
        "buy_fill_ratio": float(take_qty / requested_qty) if requested_qty > 0 else 0.0,
    }


def simulate_sell_to_bids(book_df, start_idx, qty_to_sell):
    remaining_qty = float(qty_to_sell)
    proceeds = 0.0
    sold_qty = 0.0
    last_idx = None
    zero_bid_ticks = 0
    same_price_skips = 0
    ticks_used = 0
    last_sell_bid = None
    i = int(start_idx)
    while i < len(book_df) and remaining_qty > 1e-12:
        bid = float(book_df.iloc[i]["bid_price"])
        bid_qty = float(book_df.iloc[i]["bid_qty"] or 0.0)
        ticks_used += 1
        if bid <= 0 or bid_qty <= 0:
            zero_bid_ticks += 1
            i += 1
            continue
        if last_sell_bid is not None and abs(bid - last_sell_bid) <= 1e-12:
            same_price_skips += 1
            i += 1
            continue
        take_qty = min(remaining_qty, bid_qty)
        proceeds += take_qty * bid
        sold_qty += take_qty
        remaining_qty -= take_qty
        last_idx = i
        last_sell_bid = bid
        i += 1
    if last_idx is None:
        return {
            "exit_idx": None,
            "exit_time_ns": None,
            "gross_proceeds": float(proceeds),
            "sold_qty": float(sold_qty),
            "remaining_qty": float(remaining_qty),
            "zero_bid_ticks": int(zero_bid_ticks),
            "same_price_skips": int(same_price_skips),
            "ticks_used": int(ticks_used),
            "filled": False,
        }
    return {
        "exit_idx": last_idx,
        "exit_time_ns": int(book_df.iloc[last_idx]["recv_timestamp_ns"]),
        "gross_proceeds": float(proceeds),
        "sold_qty": float(sold_qty),
        "remaining_qty": float(remaining_qty),
        "zero_bid_ticks": int(zero_bid_ticks),
        "same_price_skips": int(same_price_skips),
        "ticks_used": int(ticks_used),
        "filled": bool(remaining_qty <= 1e-9),
    }


def backtest_layer(frame, book_df, layer_name):
    book_ts = pd.to_datetime(book_df["recv_timestamp_ns"], unit="ns").values
    book_recv = book_df["recv_timestamp_ns"].astype(np.int64).to_numpy()

    rows = []
    subset = frame[frame[layer_name]].copy()
    for r in subset.itertuples(index=False):
        signal_ns = int(r.signal_ns)
        entry_idx = idx_le(book_ts, np.datetime64(signal_ns, "ns"))
        if entry_idx is None:
            continue
        entry_fill = simulate_buy_first_ask_only(book_df, int(entry_idx), TRADE_SIZE)
        if not entry_fill:
            continue
        entry_idx = int(entry_fill["entry_idx"])
        entry_time_ns = int(entry_fill["entry_time_ns"])
        entry_first_ask = float(entry_fill["entry_first_ask"])
        entry_vwap = float(entry_fill["entry_vwap"])
        entry_qty = float(entry_fill["entry_qty"])
        entry_notional = float(entry_fill["entry_notional"])
        requested_qty = float(entry_fill["requested_qty"])
        ask_qty_1 = float(entry_fill["ask_qty_1"])
        buy_fill_ratio = float(entry_fill["buy_fill_ratio"])
        if entry_qty <= 0 or entry_notional <= 0:
            continue
        entry_cost = entry_notional * (1 + CEX_FEE)
        prev_idx = entry_idx - 1 if entry_idx > 0 else None
        if prev_idx is not None:
            prev_ask = float(book_df.iloc[prev_idx]["ask_price"])
            entry_price_chg_rate = (entry_vwap / prev_ask - 1.0) if prev_ask > 0 else None
        else:
            entry_price_chg_rate = None
        row = {
            "layer": layer_name,
            "signal_time": pd.Timestamp(r.signal_time).strftime("%Y-%m-%d %H:%M:%S.%f"),
            "signal_ns": signal_ns,
            "signal_book_recv_ns": fmt_ns(book_recv[entry_idx]),
            "entry_time": fmt_ns(entry_time_ns),
            "entry_first_ask": round(entry_first_ask, 6),
            "entry_vwap_ask": round(entry_vwap, 6),
            "entry_notional": round(entry_notional, 6),
            "requested_qty": round(requested_qty, 6),
            "ask_qty_1": round(ask_qty_1, 6),
            "entry_qty": round(entry_qty, 6),
            "buy_fill_ratio": round(buy_fill_ratio, 6),
            "entry_price_chg_rate": round(entry_price_chg_rate, 8) if entry_price_chg_rate is not None else None,
            "trade_roll_3600ms": round(float(r.trade_roll_3600ms), 6),
            "dex_roll_3600ms": round(float(r.dex_roll_3600ms), 6),
            "book_roll_3600ms": round(float(r.book_roll_3600ms), 6),
            "z_trade": round(float(r.z_trade), 4),
            "z_dex": round(float(r.z_dex), 4),
            "z_book": round(float(r.z_book), 4),
            "obi": round(float(r.obi), 6),
            "dir_dex": str(r.dir_dex),
        }
        for hold in HOLDS:
            exit_ns = entry_time_ns + hold * 1_000_000_000
            exit_idx = idx_ge(book_ts, np.datetime64(exit_ns, "ns"))
            if exit_idx is None:
                row[f"exit_bid_vwap_{hold}s"] = None
                row[f"net_pnl_{hold}s"] = None
                row[f"ret_{hold}s"] = None
                row[f"exit_time_{hold}s"] = None
                row[f"sell_qty_{hold}s"] = None
                row[f"sell_fill_ratio_{hold}s"] = None
                row[f"zero_bid_ticks_{hold}s"] = None
                row[f"sell_ticks_used_{hold}s"] = None
                continue
            exit_fill = simulate_sell_to_bids(book_df, int(exit_idx), entry_qty)
            sold_qty = float(exit_fill["sold_qty"])
            sell_fill_ratio = sold_qty / entry_qty if entry_qty > 0 else 0.0
            row[f"sell_qty_{hold}s"] = round(sold_qty, 6)
            row[f"sell_fill_ratio_{hold}s"] = round(sell_fill_ratio, 6)
            row[f"zero_bid_ticks_{hold}s"] = int(exit_fill["zero_bid_ticks"])
            row[f"same_price_skips_{hold}s"] = int(exit_fill["same_price_skips"])
            row[f"sell_ticks_used_{hold}s"] = int(exit_fill["ticks_used"])
            row[f"exit_time_{hold}s"] = fmt_ns(exit_fill["exit_time_ns"]) if exit_fill["exit_time_ns"] else None
            if sold_qty <= 0 or not exit_fill["filled"]:
                row[f"exit_bid_vwap_{hold}s"] = None
                row[f"net_pnl_{hold}s"] = None
                row[f"ret_{hold}s"] = None
                continue
            gross_proceeds = float(exit_fill["gross_proceeds"])
            exit_time_ns = int(exit_fill["exit_time_ns"])
            exit_vwap = gross_proceeds / sold_qty if sold_qty > 0 else None
            proceeds = gross_proceeds
            net = proceeds - entry_cost - proceeds * CEX_FEE
            row[f"exit_bid_vwap_{hold}s"] = round(exit_vwap, 6) if exit_vwap is not None else None
            row[f"net_pnl_{hold}s"] = round(float(net), 6)
            row[f"ret_{hold}s"] = round(float(net / TRADE_SIZE), 6)
            row[f"exit_time_{hold}s"] = fmt_ns(exit_time_ns)
        rows.append(row)
    return rows


def summarize_layer(rows, hold):
    vals = [r[f"net_pnl_{hold}s"] for r in rows if r.get(f"net_pnl_{hold}s") is not None]
    if not vals:
        return {"n": 0}
    vals = np.asarray(vals, dtype=float)
    return {
        "n": int(len(vals)),
        "total_pnl": float(vals.sum()),
        "mean_pnl": float(vals.mean()),
        "median_pnl": float(np.median(vals)),
        "win_ratio": float((vals > 0).mean()),
    }


def write_csv(path, rows):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    (
        trade_ts, trade_vals, trade_buy_vals, trade_sell_vals,
        dex_ts, dex_vals, dex_buy_vals, dex_sell_vals,
        book_ts, book_vals, book_df
    ) = load_inputs()
    frame = build_signal_frame(
        trade_ts, trade_vals, trade_buy_vals, trade_sell_vals,
        dex_ts, dex_vals, dex_buy_vals, dex_sell_vals,
        book_ts, book_vals
    )

    summary_rows = []
    summary_json = {
        "date": DATE,
        "flow_window_ms": FLOW_WINDOW_MS,
        "hist_window_sec": HIST_WINDOW_SEC,
        "z_threshold": Z_THRESHOLD,
        "holds_sec": HOLDS,
        "direction": "long_only",
        "trade_size": TRADE_SIZE,
        "cex_fee_one_way": CEX_FEE,
        "entry_rule": "at signal_time latest known ask, only consume level-1 ask on that tick",
        "exit_rule": "from first book tick >= entry_time+hold, keep selling into future bid ticks until fully filled",
        "layers": {},
    }

    for layer in LAYER_ORDER:
        detail_rows = backtest_layer(frame, book_df, layer)
        write_csv(OUT_DIR / f"{layer}_detail.csv", detail_rows)
        layer_summary = {}
        for hold in HOLDS:
            stats = summarize_layer(detail_rows, hold)
            layer_summary[f"{hold}s"] = stats
            summary_rows.append({"layer": layer, "hold_sec": hold, **stats})
        summary_json["layers"][layer] = {
            "signal_count": int(frame[layer].sum()),
            "hold_stats": layer_summary,
        }

    frame.to_csv(OUT_DIR / "signal_frame_tick3600ms.csv", index=False)
    write_csv(OUT_DIR / "execution_summary.csv", summary_rows)
    (OUT_DIR / "execution_summary.json").write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary_json, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
