#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = REPO_ROOT / "outputs" / "clo_20260611_tick3600ms_execution_compare"
DEFAULT_OUTPUT_FILE = REPO_ROOT / "outputs" / "web" / "clo_20260611_signal_layers.js"
DETAIL_FILES = {
    "book_only": "book_only_detail.csv",
    "book_resonance": "book_resonance_detail.csv",
    "trade_resonance": "trade_resonance_detail.csv",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Build a browser-friendly JS payload from backtest outputs.")
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing execution_summary.json and layer detail CSV files.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="JS file to generate.",
    )
    return parser.parse_args()


def load_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        out.append({
            "sec": row["signal_time"].split(".")[0],
            "price": float(row["entry_vwap_ask"]) if row.get("entry_vwap_ask") else None,
            "signal_time": row.get("signal_time"),
            "entry_time": row.get("entry_time"),
            "entry_first_ask": float(row["entry_first_ask"]) if row.get("entry_first_ask") else None,
            "entry_vwap_ask": float(row["entry_vwap_ask"]) if row.get("entry_vwap_ask") else None,
            "entry_notional": float(row["entry_notional"]) if row.get("entry_notional") else None,
            "requested_qty": float(row["requested_qty"]) if row.get("requested_qty") else None,
            "ask_qty_1": float(row["ask_qty_1"]) if row.get("ask_qty_1") else None,
            "entry_qty": float(row["entry_qty"]) if row.get("entry_qty") else None,
            "buy_fill_ratio": float(row["buy_fill_ratio"]) if row.get("buy_fill_ratio") else None,
            "entry_price_chg_rate": float(row["entry_price_chg_rate"]) if row.get("entry_price_chg_rate") else None,
            "signal_book_recv_ns": row.get("signal_book_recv_ns"),
            "trade_roll_3600ms": float(row["trade_roll_3600ms"]) if row.get("trade_roll_3600ms") else None,
            "dex_roll_3600ms": float(row["dex_roll_3600ms"]) if row.get("dex_roll_3600ms") else None,
            "book_roll_3600ms": float(row["book_roll_3600ms"]) if row.get("book_roll_3600ms") else None,
            "z_trade": float(row["z_trade"]) if row.get("z_trade") else None,
            "z_dex": float(row["z_dex"]) if row.get("z_dex") else None,
            "z_book": float(row["z_book"]) if row.get("z_book") else None,
            "obi": float(row["obi"]) if row.get("obi") else None,
            "dir_dex": row.get("dir_dex"),
            "ret_5s": float(row["ret_5s"]) if row.get("ret_5s") else None,
            "ret_10s": float(row["ret_10s"]) if row.get("ret_10s") else None,
            "ret_20s": float(row["ret_20s"]) if row.get("ret_20s") else None,
            "ret_30s": float(row["ret_30s"]) if row.get("ret_30s") else None,
            "ret_60s": float(row["ret_60s"]) if row.get("ret_60s") else None,
            "ret_120s": float(row["ret_120s"]) if row.get("ret_120s") else None,
            "ret_300s": float(row["ret_300s"]) if row.get("ret_300s") else None,
            "sell_qty_30s": float(row["sell_qty_30s"]) if row.get("sell_qty_30s") else None,
            "sell_fill_ratio_30s": float(row["sell_fill_ratio_30s"]) if row.get("sell_fill_ratio_30s") else None,
            "zero_bid_ticks_30s": int(row["zero_bid_ticks_30s"]) if row.get("zero_bid_ticks_30s") else 0,
            "sell_ticks_used_30s": int(row["sell_ticks_used_30s"]) if row.get("sell_ticks_used_30s") else 0,
            "sell_qty_60s": float(row["sell_qty_60s"]) if row.get("sell_qty_60s") else None,
            "sell_fill_ratio_60s": float(row["sell_fill_ratio_60s"]) if row.get("sell_fill_ratio_60s") else None,
            "zero_bid_ticks_60s": int(row["zero_bid_ticks_60s"]) if row.get("zero_bid_ticks_60s") else 0,
            "sell_ticks_used_60s": int(row["sell_ticks_used_60s"]) if row.get("sell_ticks_used_60s") else 0,
            "sell_qty_120s": float(row["sell_qty_120s"]) if row.get("sell_qty_120s") else None,
            "sell_fill_ratio_120s": float(row["sell_fill_ratio_120s"]) if row.get("sell_fill_ratio_120s") else None,
            "zero_bid_ticks_120s": int(row["zero_bid_ticks_120s"]) if row.get("zero_bid_ticks_120s") else 0,
            "sell_ticks_used_120s": int(row["sell_ticks_used_120s"]) if row.get("sell_ticks_used_120s") else 0,
            "sell_qty_300s": float(row["sell_qty_300s"]) if row.get("sell_qty_300s") else None,
            "sell_fill_ratio_300s": float(row["sell_fill_ratio_300s"]) if row.get("sell_fill_ratio_300s") else None,
            "zero_bid_ticks_300s": int(row["zero_bid_ticks_300s"]) if row.get("zero_bid_ticks_300s") else 0,
            "sell_ticks_used_300s": int(row["sell_ticks_used_300s"]) if row.get("sell_ticks_used_300s") else 0,
        })
    return out


def main():
    args = parse_args()
    summary = json.loads((args.source_dir / "execution_summary.json").read_text(encoding="utf-8"))
    layers = {key: load_rows(args.source_dir / filename) for key, filename in DETAIL_FILES.items()}
    payload = {"summary": summary, "layers": layers}
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(
        "window.CLO_SIGNAL_LAYER_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output_file}")


if __name__ == "__main__":
    main()
