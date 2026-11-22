"""站规字段名单：唯一受管的改名单入口。

架构（钉死快照）下，改名单只影响**之后**的开版：
- 每次改名单追加一条不可变「站规版本」，开版时外键采信该版本；
- 已开版卫星的哈希结论钉在各自世代快照上，改名单不回溯、不重算、不覆盖；
- 绕过本入口直接 UPDATE 站规的，开版取口径时按失败闭处理（见 services/卫星开版.取口径）。
"""
from __future__ import annotations

import json
from typing import Any

from app.db import 连接
from app.seed import 此刻

默认口径 = "全属性字段"
默认名单 = ["*"]
支持口径 = {默认口径}
权威字段键 = "卫星载荷哈希字段"


class 站规错误(RuntimeError):
    """站规字段名单不可实现；调用方必须整票回滚。"""


def 规范快照(名单: list[str]) -> str:
    """字段名单的规范 JSON 文本（去空、去重、保序之外做排序以稳定落盘）。"""
    if not isinstance(名单, list) or not 名单:
        raise 站规错误("字段名单必须是非空数组")
    干净 = [str(x).strip() for x in 名单 if str(x).strip()]
    if not 干净:
        raise 站规错误("字段名单不得全为空字段")
    if "*" in 干净 and len(干净) != 1:
        raise 站规错误("「*」（全属性）只能单独使用，不得与具名字段混用")
    if len(set(干净)) != len(干净):
        raise 站规错误("字段名单不得含重复字段")
    return json.dumps(sorted(干净), ensure_ascii=False, separators=(",", ":"))


def 解析名单(原值: str) -> list[str]:
    """站规里只允许两种可实现值：'*' 或 JSON 字符串数组；其余失败闭。"""
    值 = (原值 or "").strip()
    if 值 == "*":
        return ["*"]
    try:
        名单 = json.loads(值)
    except Exception as e:
        raise 站规错误(f"站规字段集不可解析:{值!r}（{e}）；本仓只贯彻「{默认口径}」") from e
    if not isinstance(名单, list):
        raise 站规错误("站规字段集必须是数组或 '*'")
    return json.loads(规范快照(名单))


def 现行口径(conn) -> dict[str, Any]:
    口径行 = conn.execute(
        "SELECT 值 FROM 站规 WHERE 键=?", ("卫星载荷哈希口径",)
    ).fetchone()
    口径 = 口径行["值"] if 口径行 else 默认口径
    if 口径 not in 支持口径:
        raise 站规错误(f"站规口径未实现:{口径}（本仓只贯彻「{默认口径}」）")
    字段行 = conn.execute("SELECT 值 FROM 站规 WHERE 键=?", (权威字段键,)).fetchone()
    原值 = 字段行["值"] if 字段行 else "*"
    名单 = 解析名单(原值)
    快照 = 规范快照(名单)
    末版 = conn.execute(
        "SELECT 版本号, 字段集快照, 站规键值 FROM 站规版本 ORDER BY 版本号 DESC LIMIT 1"
    ).fetchone()
    # 受管改名单必须同时追加站规版本；直改站规导致二者漂移时失败闭，
    # 禁止在无世代约束下用新名单去判定旧当前。
    if 末版 is None:
        raise 站规错误("站规版本未钉，失败闭：禁止无世代约束开版")
    if 末版["字段集快照"] != 快照:
        raise 站规错误(
            f"站规字段名单（{快照}）与已钉站规版本#{末版['版本号']}"
            f"（{末版['字段集快照']}）漂移：改名单须走受管入口，失败闭"
        )
    return {
        "口径": 默认口径,
        "字段": "*" if 名单 == ["*"] else json.dumps(名单, ensure_ascii=False),
        "字段名单": 名单,
        "字段集快照": 快照,
        "站规版本": 末版["版本号"],
        "架构": "钉死快照",
        "规则": (
            "全属性字段口径：'*'=属性 JSON 全字段；具名数组=仅按名单字段子集算哈希。"
            "开版即钉死当时名单世代；再灌同载荷按当前版钉死快照比对，改名单不回溯旧结论"
        ),
        "已实现": True,
    }


def 站规版本史(conn) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT 版本号, 字段集快照, 口径, 批号, 时刻 FROM 站规版本 ORDER BY 版本号"
        )
    ]


def 改字段名单(名单: list[str], 批号: str = "", 自管: bool = True) -> dict[str, Any]:
    """受管改名单：校验 → 写站规 → 追加站规版本，同事务同成败。

    幂等：新名单与现行名单规范相等时不开新版本，原样返回当前版本。
    """
    快照 = 规范快照(名单)
    批号 = str(批号 or f"规改-{_短()}")
    conn = 连接()
    try:
        if 自管:
            conn.execute("BEGIN IMMEDIATE")
        现 = 现行口径(conn)
        if 现["字段集快照"] == 快照:
            if 自管:
                conn.commit()
            return {
                "结果": "无变化",
                "站规版本": 现["站规版本"],
                "字段集快照": 快照,
            }
        conn.execute(
            "UPDATE 站规 SET 值=? WHERE 键=?",
            ("*" if json.loads(快照) == ["*"] else 快照, 权威字段键),
        )
        cur = conn.execute(
            "INSERT INTO 站规版本(字段集快照, 口径, 站规键值, 批号, 时刻) "
            "VALUES (?,?,?,?,?)",
            (快照, 默认口径, "*" if json.loads(快照) == ["*"] else 快照, 批号, 此刻()),
        )
        版本号 = int(cur.lastrowid)
        if 自管:
            conn.commit()
        return {
            "结果": "已钉新版本",
            "站规版本": 版本号,
            "字段集快照": 快照,
            "批号": 批号,
            "影响": "仅此后新开版采信；已开版结论钉死不变",
        }
    except Exception:
        if 自管:
            conn.rollback()
        raise
    finally:
        conn.close()


def _短() -> str:
    import uuid

    return uuid.uuid4().hex[:8]
