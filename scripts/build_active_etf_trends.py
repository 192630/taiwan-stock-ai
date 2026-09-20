#!/usr/bin/env python3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HISTORY_DIR = Path("data/active_etf_holdings_history")
OUTPUT_FILE = Path("data/active_etf_trends.json")
TZ = timezone(timedelta(hours=8))


def number(value):
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def holdings_map(etf):
    result = {}
    for item in etf.get("holdings") or []:
        code = str(item.get("code") or item.get("stock_code") or "").strip()
        if not code:
            continue
        result[code] = {
            "name": " ".join(str(item.get("name") or item.get("stock_name") or code).split()),
            "shares": number(item.get("shares")),
        }
    return result


def save(payload):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    now = datetime.now(TZ).isoformat()
    files = sorted(HISTORY_DIR.glob("*.json")) if HISTORY_DIR.exists() else []

    if len(files) < 2:
        save({
            "_meta": {
                "status": "waiting",
                "updated_at": now,
                "snapshot_count": len(files),
                "description": "至少需要兩個有效交易日快照才能計算連續增減趨勢",
            },
            "positive": [],
            "negative": [],
        })
        print("ETF trends waiting: fewer than two snapshots")
        return

    snapshots = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            snapshots.append((path.stem, payload.get("etfs") or {}))
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skip {path.name}: {error}")

    daily = []
    for index in range(1, len(snapshots)):
        previous_date, previous_etfs = snapshots[index - 1]
        current_date, current_etfs = snapshots[index]
        stocks = {}

        for etf_code in sorted(set(previous_etfs) & set(current_etfs)):
            previous_etf = previous_etfs.get(etf_code) or {}
            current_etf = current_etfs.get(etf_code) or {}
            if previous_etf.get("status") not in (None, "success"):
                continue
            if current_etf.get("status") not in (None, "success"):
                continue

            previous = holdings_map(previous_etf)
            current = holdings_map(current_etf)

            for code in set(previous) | set(current):
                before = previous.get(code, {}).get("shares", 0)
                after = current.get(code, {}).get("shares", 0)
                if after == before:
                    continue

                row = stocks.setdefault(code, {
                    "code": code,
                    "name": current.get(code, previous.get(code, {})).get("name", code),
                    "increased_count": 0,
                    "decreased_count": 0,
                    "new_count": 0,
                    "removed_count": 0,
                    "net_etf_count": 0,
                })

                if before <= 0 < after:
                    row["new_count"] += 1
                    row["net_etf_count"] += 1
                elif after <= 0 < before:
                    row["removed_count"] += 1
                    row["net_etf_count"] -= 1
                elif after > before:
                    row["increased_count"] += 1
                    row["net_etf_count"] += 1
                else:
                    row["decreased_count"] += 1
                    row["net_etf_count"] -= 1

        daily.append({
            "previous_date": previous_date,
            "date": current_date,
            "stocks": stocks,
        })

    if not daily:
        save({
            "_meta": {
                "status": "waiting",
                "updated_at": now,
                "snapshot_count": len(snapshots),
                "description": "目前沒有可比較的有效快照",
            },
            "positive": [],
            "negative": [],
        })
        return

    latest = daily[-1]
    positive = []
    negative = []

    for code, latest_row in latest["stocks"].items():
        latest_net = latest_row["net_etf_count"]
        if latest_net == 0:
            continue

        direction = 1 if latest_net > 0 else -1
        streak_days = 0

        for day in reversed(daily):
            row = day["stocks"].get(code)
            net = row["net_etf_count"] if row else 0
            if net * direction > 0:
                streak_days += 1
            else:
                break

        item = {
            **latest_row,
            "streak_days": streak_days,
            "latest_date": latest["date"],
        }
        (positive if direction > 0 else negative).append(item)

    positive.sort(
        key=lambda item: (
            item["streak_days"],
            item["net_etf_count"],
            item["increased_count"] + item["new_count"],
        ),
        reverse=True,
    )
    negative.sort(
        key=lambda item: (
            item["streak_days"],
            abs(item["net_etf_count"]),
            item["decreased_count"] + item["removed_count"],
        ),
        reverse=True,
    )

    save({
        "_meta": {
            "status": "success",
            "updated_at": now,
            "snapshot_count": len(snapshots),
            "comparison_days": len(daily),
            "latest_date": latest["date"],
            "description": "依每日官方投資組合快照計算跨 ETF 持股股數方向與連續交易日",
        },
        "positive": positive,
        "negative": negative,
    })

    print(f"ETF trends finished: {len(positive)} positive, {len(negative)} negative")


if __name__ == "__main__":
    main()
