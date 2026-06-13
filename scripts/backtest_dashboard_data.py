#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = REPO_ROOT / "data" / "cache" / "dashboard_cache.json"
PRICE_WEB_DIR = REPO_ROOT / "clo_price_curve_web_full5"


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    strategy_name: str
    kind: str
    base_dir: Path
    direction: str
    daily_summary_json: Path | None = None
    daily_summary_csv: Path | None = None
    detail_filename: str | None = None


STRATEGY_SPECS: list[StrategySpec] = [
    StrategySpec(
        strategy_id="clo_full5",
        strategy_name="CLO Full5 Layer Compare",
        kind="layered_long",
        base_dir=REPO_ROOT / "clo_multi_day_tick3600ms_execution_compare_full5",
        direction="long_only",
        daily_summary_json=REPO_ROOT / "clo_multi_day_tick3600ms_execution_compare_full5" / "daily_summary.json",
        daily_summary_csv=REPO_ROOT / "clo_multi_day_tick3600ms_execution_compare_full5" / "daily_summary.csv",
    ),
    StrategySpec(
        strategy_id="short_book_res_div",
        strategy_name="Short Book Resonance Divergence",
        kind="single_short",
        base_dir=REPO_ROOT / "clo_directional_short_bookres_divergence",
        direction="short_only",
        daily_summary_csv=REPO_ROOT / "clo_directional_short_bookres_divergence" / "daily_summary.csv",
        detail_filename="short_book_resonance_divergence_detail.csv",
    ),
]


def safe_float(value: Any) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def safe_bool(value: Any) -> bool | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def parse_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_csv_file(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_js_assignment(path: Path) -> Any:
    content = path.read_text(encoding="utf-8").strip()
    _, rhs = content.split("=", 1)
    return json.loads(rhs.strip().rstrip(";"))


def normalize_hold_key(hold_key: str) -> int:
    text = str(hold_key).strip().lower()
    return int(text[:-1]) if text.endswith("s") else int(text)


def derive_volume(raw_stats: dict[str, Any]) -> float | None:
    for key in ("volume", "traded_volume", "total_volume"):
        value = safe_float(raw_stats.get(key))
        if value is not None:
            return value
    return safe_float(raw_stats.get("total_traded_notional"))


def derive_fee(raw_stats: dict[str, Any]) -> float | None:
    return safe_float(raw_stats.get("total_fee"))


def derive_pnl_per_volume(raw_stats: dict[str, Any], total_pnl: float | None, volume: float | None) -> float | None:
    explicit = safe_float(raw_stats.get("pnl_per_volume"))
    if explicit is not None:
        return explicit
    if total_pnl is None or volume in (None, 0):
        return None
    return total_pnl / volume


def normalize_hold_stat(layer: str, hold_sec: int, raw_stats: dict[str, Any]) -> dict[str, Any]:
    total_pnl = safe_float(raw_stats.get("total_pnl"))
    volume = derive_volume(raw_stats)
    return {
        "layer": layer,
        "hold_sec": hold_sec,
        "n": safe_int(raw_stats.get("n")) or 0,
        "signal_count": safe_int(raw_stats.get("signal_count")) or safe_int(raw_stats.get("n")) or 0,
        "total_pnl": total_pnl,
        "mean_pnl": safe_float(raw_stats.get("mean_pnl")),
        "median_pnl": safe_float(raw_stats.get("median_pnl")),
        "win_ratio": safe_float(raw_stats.get("win_ratio")),
        "volume": volume,
        "max_drawdown": safe_float(raw_stats.get("max_drawdown")),
        "pnl_per_volume": derive_pnl_per_volume(raw_stats, total_pnl, volume),
        "total_fee": derive_fee(raw_stats),
        "total_entry_notional": safe_float(raw_stats.get("total_entry_notional")),
        "total_exit_notional": safe_float(raw_stats.get("total_exit_notional")),
        "total_traded_notional": safe_float(raw_stats.get("total_traded_notional")),
    }


def choose_best_hold(hold_stats: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [item for item in hold_stats if item.get("total_pnl") is not None]
    if not valid:
        return None
    return max(valid, key=lambda item: (item["total_pnl"], item["hold_sec"]))


def summarize_day(strategy_id: str, date: str, direction: str, holds_sec: list[int], hold_stats: list[dict[str, Any]]) -> dict[str, Any]:
    best = choose_best_hold(hold_stats)
    signal_count = max((item.get("signal_count") or 0 for item in hold_stats), default=0)
    total_fee = best.get("total_fee") if best else None
    volume = best.get("volume") if best else None
    return {
        "strategy_id": strategy_id,
        "date": date,
        "direction": direction,
        "holds_sec": holds_sec,
        "signal_count": signal_count,
        "best_hold_sec": best.get("hold_sec") if best else None,
        "best_total_pnl": best.get("total_pnl") if best else None,
        "best_win_ratio": best.get("win_ratio") if best else None,
        "volume": volume,
        "max_drawdown": best.get("max_drawdown") if best else None,
        "pnl_per_volume": best.get("pnl_per_volume") if best else None,
        "total_fee": total_fee,
    }


def list_date_dirs(base_dir: Path) -> list[str]:
    dates: list[str] = []
    if not base_dir.exists():
        return dates
    for child in sorted(base_dir.iterdir()):
        if child.is_dir() and child.name.isdigit() and len(child.name) == 8:
            dates.append(child.name)
    return dates


def lookup_price_js(date: str) -> Path | None:
    path = PRICE_WEB_DIR / f"clo_{date.replace('-', '')}_adjusted_trade_price_1s.js"
    return path if path.exists() else None


def lookup_layer_js(date: str) -> Path | None:
    path = PRICE_WEB_DIR / f"clo_{date.replace('-', '')}_full5_layers.js"
    return path if path.exists() else None


def parse_price_series(date: str) -> list[dict[str, Any]]:
    price_path = lookup_price_js(date)
    if not price_path:
        return []
    raw_points = parse_js_assignment(price_path)
    points: list[dict[str, Any]] = []
    for item in raw_points:
        ts = item[0] if len(item) > 0 else None
        price = safe_float(item[1] if len(item) > 1 else None)
        normalized_price = safe_float(item[2] if len(item) > 2 else None)
        points.append(
            {
                "ts": ts,
                "price": price,
                "normalized_price": normalized_price,
            }
        )
    return points


def parse_layer_markers(date: str) -> dict[str, list[dict[str, Any]]]:
    layer_path = lookup_layer_js(date)
    if not layer_path:
        return {}
    payload = parse_js_assignment(layer_path)
    raw_layers = payload.get("layers", {})
    parsed: dict[str, list[dict[str, Any]]] = {}
    for layer, rows in raw_layers.items():
        parsed[layer] = []
        for row in rows:
            hold_metrics = {}
            for key, value in row.items():
                if key.startswith("ret_") and key.endswith("s"):
                    hold_metrics[key] = safe_float(value)
            parsed[layer].append(
                {
                    "ts": row.get("signal_time"),
                    "layer": layer,
                    "price": safe_float(row.get("price") or row.get("entry_vwap_ask") or row.get("entry_vwap_bid")),
                    "signal_time": row.get("signal_time"),
                    "hold_metrics": hold_metrics,
                }
            )
    return parsed


def normalize_signal_row(row: dict[str, Any], layer: str, direction: str, holds_sec: list[int]) -> dict[str, Any]:
    signal_time = row.get("signal_time")
    entry_price = safe_float(row.get("entry_vwap_ask") or row.get("entry_vwap_bid"))
    hold_metrics = []
    for hold_sec in holds_sec:
        suffix = f"{hold_sec}s"
        hold_metrics.append(
            {
                "hold_sec": hold_sec,
                "ret": safe_float(row.get(f"ret_{suffix}")),
                "net_pnl": safe_float(row.get(f"net_pnl_{suffix}")),
                "fee": safe_float(row.get(f"total_fee_{suffix}") or row.get(f"exit_fee_{suffix}")),
                "fill_ratio": safe_float(
                    row.get(f"sell_fill_ratio_{suffix}") or row.get(f"cover_fill_ratio_{suffix}")
                ),
                "volume": safe_float(
                    row.get(f"traded_notional_{suffix}")
                    or row.get(f"sell_qty_{suffix}")
                    or row.get(f"cover_qty_{suffix}")
                ),
            }
        )
    return {
        "signal_time": signal_time,
        "signal_ns": row.get("signal_ns"),
        "layer": layer,
        "direction": direction,
        "entry_time": row.get("entry_time"),
        "entry_price": entry_price,
        "entry_notional": safe_float(row.get("entry_notional")),
        "entry_fee": safe_float(row.get("entry_fee")),
        "requested_qty": safe_float(row.get("requested_qty")),
        "entry_qty": safe_float(row.get("entry_qty")),
        "fill_ratio": safe_float(row.get("buy_fill_ratio") or row.get("sell_fill_ratio")),
        "entry_price_change_rate": safe_float(row.get("entry_price_chg_rate")),
        "trade_roll_3600ms": safe_float(row.get("trade_roll_3600ms")),
        "dex_roll_3600ms": safe_float(row.get("dex_roll_3600ms")),
        "book_roll_3600ms": safe_float(row.get("book_roll_3600ms")),
        "z_trade": safe_float(row.get("z_trade")),
        "z_dex": safe_float(row.get("z_dex")),
        "z_book": safe_float(row.get("z_book")),
        "obi": safe_float(row.get("obi")),
        "dir_dex": row.get("dir_dex"),
        "signal_rule": row.get("signal_rule"),
        "vwap_long_filter": safe_bool(row.get("vwap_long_filter")),
        "pre_ret_3s": safe_float(row.get("pre_ret_3s")),
        "volume": safe_float(row.get("traded_notional_30s")),
        "max_drawdown": safe_float(row.get("max_drawdown")),
        "pnl_per_volume": safe_float(row.get("pnl_per_volume")),
        "total_fee": safe_float(row.get("total_fee_30s")),
        "hold_metrics": hold_metrics,
    }


def build_layer_summary(hold_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_layer: dict[str, list[dict[str, Any]]] = {}
    for item in hold_stats:
        by_layer.setdefault(item["layer"], []).append(item)

    summaries: list[dict[str, Any]] = []
    for layer, items in by_layer.items():
        best = choose_best_hold(items)
        summaries.append(
            {
                "layer": layer,
                "best_hold_sec": best.get("hold_sec") if best else None,
                "signal_count": max((item.get("signal_count") or 0 for item in items), default=0),
                "total_pnl": best.get("total_pnl") if best else None,
                "win_ratio": best.get("win_ratio") if best else None,
                "volume": best.get("volume") if best else None,
                "max_drawdown": best.get("max_drawdown") if best else None,
                "pnl_per_volume": best.get("pnl_per_volume") if best else None,
                "total_fee": best.get("total_fee") if best else None,
            }
        )
    return sorted(summaries, key=lambda item: item["layer"])


def load_full5_daily_summary(spec: StrategySpec) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    assert spec.daily_summary_json is not None
    daily_rows = parse_json_file(spec.daily_summary_json)
    day_summaries: list[dict[str, Any]] = []
    hold_stat_rows: list[dict[str, Any]] = []
    available_layers: set[str] = set()
    available_holds: set[int] = set()

    for row in daily_rows:
        date = row["date"]
        holds_sec = [int(value) for value in row.get("holds_sec", [])]
        available_holds.update(holds_sec)
        day_hold_stats: list[dict[str, Any]] = []
        for layer, layer_payload in row.get("layers", {}).items():
            available_layers.add(layer)
            hold_stats = layer_payload.get("hold_stats", {})
            for hold_key, raw_stats in hold_stats.items():
                hold_sec = normalize_hold_key(hold_key)
                normalized = normalize_hold_stat(layer, hold_sec, raw_stats)
                normalized["date"] = date
                normalized["strategy_id"] = spec.strategy_id
                normalized["raw_signal_count"] = safe_int(layer_payload.get("raw_signal_count"))
                hold_stat_rows.append(normalized)
                day_hold_stats.append(normalized)
        day_summaries.append(summarize_day(spec.strategy_id, date, spec.direction, holds_sec, day_hold_stats))

    meta = {
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.strategy_name,
        "direction": spec.direction,
        "available_dates": sorted(item["date"] for item in day_summaries),
        "available_layers": sorted(available_layers),
        "available_holds": sorted(available_holds),
        "supports_price_series": True,
    }
    return day_summaries, {"meta": meta, "hold_stat_rows": hold_stat_rows}


def load_single_short_daily_summary(spec: StrategySpec) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    assert spec.daily_summary_csv is not None
    rows = parse_csv_file(spec.daily_summary_csv)
    hold_stat_rows: list[dict[str, Any]] = []
    day_map: dict[str, list[dict[str, Any]]] = {}
    holds: set[int] = set()
    layer_name = "short_book_resonance_divergence"

    for row in rows:
        date = row["date"]
        hold_sec = safe_int(row.get("hold_sec")) or 0
        holds.add(hold_sec)
        normalized = normalize_hold_stat(layer_name, hold_sec, row)
        normalized["date"] = date
        normalized["strategy_id"] = spec.strategy_id
        hold_stat_rows.append(normalized)
        day_map.setdefault(date, []).append(normalized)

    day_summaries = [
        summarize_day(spec.strategy_id, date, spec.direction, sorted(holds), stats)
        for date, stats in sorted(day_map.items())
    ]

    meta = {
        "strategy_id": spec.strategy_id,
        "strategy_name": spec.strategy_name,
        "direction": spec.direction,
        "available_dates": sorted(day_map.keys()),
        "available_layers": [layer_name],
        "available_holds": sorted(holds),
        "supports_price_series": False,
    }
    return day_summaries, {"meta": meta, "hold_stat_rows": hold_stat_rows}


def load_strategy_index(spec: StrategySpec) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if spec.kind == "layered_long":
        return load_full5_daily_summary(spec)
    return load_single_short_daily_summary(spec)


def detail_csv_files_for_full5(day_dir: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for path in sorted(day_dir.glob("*_detail.csv")):
        layer = path.name.replace("_detail.csv", "")
        out.append((layer, path))
    return out


def load_day_detail(spec: StrategySpec, date: str, meta: dict[str, Any], index_hold_rows: list[dict[str, Any]]) -> dict[str, Any]:
    day_token = date.replace("-", "")
    day_dir = spec.base_dir / day_token
    execution_summary_path = day_dir / "execution_summary.json"
    execution_summary = parse_json_file(execution_summary_path) if execution_summary_path.exists() else {}
    holds_sec = [int(value) for value in execution_summary.get("holds_sec", meta.get("available_holds", []))]

    if spec.kind == "layered_long":
        detail_files = detail_csv_files_for_full5(day_dir)
    else:
        detail_path = day_dir / (spec.detail_filename or "")
        detail_files = [("short_book_resonance_divergence", detail_path)] if detail_path.exists() else []

    signals: list[dict[str, Any]] = []
    for layer, detail_path in detail_files:
        for row in parse_csv_file(detail_path):
            signals.append(normalize_signal_row(row, layer, spec.direction, holds_sec))

    hold_stats = [row for row in index_hold_rows if row["date"] == date]
    layer_summaries = build_layer_summary(hold_stats)

    price_series = parse_price_series(date) if meta.get("supports_price_series") else []
    raw_markers = parse_layer_markers(date) if meta.get("supports_price_series") else {}
    if raw_markers:
        signal_markers = [marker for markers in raw_markers.values() for marker in markers]
    else:
        signal_markers = [
            {
                "ts": signal["signal_time"],
                "layer": signal["layer"],
                "price": signal["entry_price"],
                "signal_time": signal["signal_time"],
                "hold_metrics": {
                    f"ret_{item['hold_sec']}s": item["ret"]
                    for item in signal["hold_metrics"]
                    if item["ret"] is not None
                },
            }
            for signal in signals
        ]

    return {
        "strategy_id": spec.strategy_id,
        "date": date,
        "summary": execution_summary,
        "holds_sec": holds_sec,
        "layer_summaries": layer_summaries,
        "hold_stats": hold_stats,
        "signals": signals,
        "price_series": price_series,
        "signal_markers": signal_markers,
    }


def build_dashboard_payload() -> dict[str, Any]:
    strategies: list[dict[str, Any]] = []
    by_id: dict[str, Any] = {}

    for spec in STRATEGY_SPECS:
        day_summaries, strategy_index = load_strategy_index(spec)
        meta = strategy_index["meta"]
        hold_rows = strategy_index["hold_stat_rows"]
        day_details: dict[str, Any] = {}
        for date in meta["available_dates"]:
            day_details[date] = load_day_detail(spec, date, meta, hold_rows)
        strategies.append(
            {
                "meta": meta,
                "day_summaries": day_summaries,
                "hold_stat_rows": hold_rows,
                "days": day_details,
            }
        )
        by_id[spec.strategy_id] = strategies[-1]

    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "strategies": strategies,
        "strategy_ids": [item["meta"]["strategy_id"] for item in strategies],
        "by_id": by_id,
    }


def write_dashboard_cache(cache_path: Path = CACHE_PATH) -> dict[str, Any]:
    payload = build_dashboard_payload()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def load_dashboard_cache(cache_path: Path = CACHE_PATH) -> dict[str, Any]:
    return parse_json_file(cache_path)


def get_dashboard_payload(mode: str = "live", cache_path: Path = CACHE_PATH) -> dict[str, Any]:
    if mode == "cache":
        if not cache_path.exists():
            return write_dashboard_cache(cache_path)
        return load_dashboard_cache(cache_path)
    return build_dashboard_payload()

