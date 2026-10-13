"""Reproduce the synthetic exception triage figures used in the day 8 review."""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


SOURCE = Path(__file__).with_name("03_模拟工单.csv")
EXCEPTION_TYPES = ("派单超时", "上门超时", "完工超时")


def is_late(actual, deadline):
    # All nonblank timestamps use YYYY-MM-DD HH:MM in the same time zone.
    return not actual or actual > deadline


with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
    orders = list(csv.DictReader(handle))

assert len(orders) == 600
assert len({row["order_id"] for row in orders}) == len(orders)

site = defaultdict(Counter)
site_service = defaultdict(Counter)
overall = Counter()
queue = {"P1": [], "P2": []}

for row in orders:
    primary = row["primary_exception"]
    assert primary in (*EXCEPTION_TYPES, "无")
    dispatch_late = is_late(row["dispatched_at"], row["appointment_deadline"])
    arrival_late = is_late(row["arrived_at"], row["appointment_deadline"])
    completion_late = is_late(row["completed_at"], row["completion_deadline"])
    expected = (
        "派单超时" if dispatch_late else
        "上门超时" if arrival_late else
        "完工超时" if completion_late else "无"
    )
    assert primary == expected, row["order_id"]

    overall["orders"] += 1
    s = site[row["site_id"]]
    ss = site_service[(row["site_id"], row["service_type"])]
    for group in (s, ss):
        group["orders"] += 1
        group["arrival_late"] += arrival_late
        group["completion_late"] += completion_late
        group[primary] += 1
    for name, flag in (("dispatch_late", dispatch_late),
                       ("arrival_late", arrival_late),
                       ("completion_late", completion_late)):
        overall[name] += flag
    overall[primary] += 1

    if primary != "无":
        overall["exceptions"] += 1
        overall["complaint_among_exceptions"] += row["complaint_flag"] == "1"
        if row["exception_closed_at"]:
            overall["closed"] += 1
        else:
            overall["open"] += 1
            overall[f"open_{primary}"] += 1
            unfinished = row["order_status"] == "未完工"
            complaint = row["complaint_flag"] == "1"
            overall["open_unfinished"] += unfinished
            overall["open_complaint"] += complaint
            priority = "P1" if unfinished or complaint else "P2"
            queue[priority].append(row)


def group_view(stats):
    return {
        "orders": stats["orders"],
        "arrival_late": stats["arrival_late"],
        "completion_late": stats["completion_late"],
        "primary_exceptions": {name: stats[name] for name in EXCEPTION_TYPES},
    }


result = {
    "scope": "600 synthetic orders; snapshot 2026-09-30 23:59 Beijing time",
    "overall": dict(overall),
    "by_site": {key: group_view(value) for key, value in sorted(site.items())},
    "by_site_and_service": {
        f"{key[0]}_{key[1]}": group_view(value)
        for key, value in sorted(site_service.items())
    },
    "open_queue": {
        priority: {
            "count": len(rows),
            "example_ids": [row["order_id"] for row in rows[:5]],
        }
        for priority, rows in queue.items()
    },
}
assert overall["exceptions"] == overall["closed"] + overall["open"]
assert overall["open"] == len(queue["P1"]) + len(queue["P2"])
print(json.dumps(result, ensure_ascii=False, indent=2))
