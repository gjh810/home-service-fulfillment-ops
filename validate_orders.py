"""独立检查第 3 天的模拟工单 CSV；只使用 Python 标准库。"""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


FILE = Path(__file__).with_name("03_模拟工单.csv")
AS_OF = datetime(2026, 9, 30, 23, 59)
FIELDS = [
    "order_id", "city", "service_type", "site_id", "created_at", "dispatched_at",
    "appointment_deadline", "arrived_at", "completion_deadline", "completed_at",
    "order_status", "primary_exception", "exception_detected_at",
    "exception_closed_at", "complaint_flag", "rating",
]
SITES = {"北京": {"BJ01", "BJ02"}, "武汉": {"WH01", "WH02"}, "重庆": {"CQ01", "CQ02"}}
SERVICES = {"安装", "维修", "拆旧"}


def parse(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M") if value else None


def main():
    with FILE.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == FIELDS, "字段顺序与字典不一致"
        rows = list(reader)
    assert len(rows) == 600, f"行数错误：{len(rows)}"
    assert len({r["order_id"] for r in rows}) == len(rows), "工单 ID 重复"

    city_count, service_count, site_count, exception_count = (Counter() for _ in range(4))
    site_exception = defaultdict(Counter)
    on_time_arrival = on_time_completion = complaints = closed = rating_missing = unfinished = 0
    for i, row in enumerate(rows, 2):
        def require(condition, message):
            assert condition, f"CSV 第 {i} 行：{message}"

        require(row["city"] in SITES, "城市无效")
        require(row["site_id"] in SITES[row["city"]], "站点与城市不匹配")
        require(row["service_type"] in SERVICES, "服务类型无效")
        require(row["complaint_flag"] in {"0", "1"}, "投诉标记无效")
        require(row["rating"] == "" or row["rating"] in {"1", "2", "3", "4", "5"}, "评分无效")

        created = parse(row["created_at"])
        dispatched = parse(row["dispatched_at"])
        appointment = parse(row["appointment_deadline"])
        arrived = parse(row["arrived_at"])
        completion_due = parse(row["completion_deadline"])
        completed = parse(row["completed_at"])
        detected = parse(row["exception_detected_at"])
        closed_at = parse(row["exception_closed_at"])
        require(created < appointment < completion_due < AS_OF, "截止时间顺序错误或未到期")
        require(dispatched is None or created <= dispatched, "派单早于创建")
        require(arrived is None or (dispatched is not None and dispatched <= arrived), "上门早于派单")
        require(completed is None or (arrived is not None and arrived <= completed), "完工早于上门")
        require(row["order_status"] == ("已完工" if completed else "未完工"), "状态与完工时间不一致")
        require(completed is not None or row["rating"] == "", "未完工工单不应有评分")

        expected = "派单超时" if dispatched is None or dispatched > appointment else (
            "上门超时" if arrived is None or arrived > appointment else (
                "完工超时" if completed is None or completed > completion_due else "无"
            )
        )
        require(row["primary_exception"] == expected, "主要异常分类错误")
        expected_detection = None if expected == "无" else completion_due if expected == "完工超时" else appointment
        require(detected == expected_detection, "异常发现时间错误")
        require(closed_at is None or (detected is not None and completed is not None and closed_at >= max(detected, completed)), "异常关闭时间错误")

        city_count[row["city"]] += 1
        service_count[row["service_type"]] += 1
        site_count[row["site_id"]] += 1
        exception_count[expected] += 1
        site_exception[row["site_id"]][expected] += 1
        on_time_arrival += int(arrived is not None and arrived <= appointment)
        on_time_completion += int(completed is not None and completed <= completion_due)
        complaints += int(row["complaint_flag"])
        closed += int(closed_at is not None)
        rating_missing += int(row["rating"] == "")
        unfinished += int(completed is None)

    exception_total = len(rows) - exception_count["无"]
    result = {
        "status": "PASS",
        "rows": len(rows),
        "unique_ids": len(rows),
        "sha256": hashlib.sha256(FILE.read_bytes()).hexdigest(),
        "city": dict(city_count),
        "service_type": dict(service_count),
        "site": dict(site_count),
        "primary_exception": dict(exception_count),
        "site_exception": {k: dict(v) for k, v in sorted(site_exception.items())},
        "unfinished": unfinished,
        "rating_missing": rating_missing,
        "on_time_arrival": on_time_arrival,
        "on_time_completion": on_time_completion,
        "complaints": complaints,
        "exception_total": exception_total,
        "exception_closed": closed,
        "rates": {
            "准时上门率": round(on_time_arrival / len(rows), 4),
            "按期完工率": round(on_time_completion / len(rows), 4),
            "投诉率": round(complaints / len(rows), 4),
            "异常闭环率": round(closed / exception_total, 4),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
