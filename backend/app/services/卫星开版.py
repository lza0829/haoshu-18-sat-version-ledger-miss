from __future__ import annotations

import json
from typing import Any

from app.db import 连接
from app.seed import 载荷哈希

默认口径 = "全属性字段"
默认字段 = "*"
支持口径 = {默认口径}

表配置: dict[str, tuple[str, str, str]] = {
    "号卡": ("卫星_号卡属性", "号卡哈希", "枢纽_号卡"),
    "套餐": ("卫星_套餐属性", "套餐哈希", "枢纽_套餐"),
    "客户": ("卫星_客户属性", "客户哈希", "枢纽_客户"),
    "订购": ("卫星_订购属性", "链接哈希", "链接_号卡套餐"),
}


class 开版错误(RuntimeError):
    """开版写闸拒绝；调用方必须整批回滚。"""


def _读站规(conn, 键: str, 默认: str) -> str:
    r = conn.execute("SELECT 值 FROM 站规 WHERE 键=?", (键,)).fetchone()
    return r["值"] if r else 默认


def 取口径(conn) -> dict[str, Any]:
    """读取站规字段集并校验；口径不可实现时失败闭，不静默改用别的口径。"""
    口径 = _读站规(conn, "卫星载荷哈希口径", 默认口径)
    字段 = _读站规(conn, "卫星载荷哈希字段", 默认字段)
    if 口径 not in 支持口径:
        raise 开版错误(f"站规口径未实现:{口径}（本仓只贯彻「{默认口径}」）")
    if 字段 not in (默认字段, ""):
        raise 开版错误(f"站规字段集未实现:{字段}（本仓只贯彻全属性字段）")
    return {
        "口径": 默认口径,
        "字段": 默认字段,
        "规则": "属性 JSON 任一字段变化即开新版；展示名/备注变更同样开版；同哈希不空开",
        "已实现": True,
    }


def 算载荷哈希(属性: dict[str, Any], 口径: dict[str, Any] | None = None) -> str:
    """全属性字段口径下，载荷哈希 = 属性 JSON 的规范哈希。"""
    if 口径 is not None and 口径.get("口径") != 默认口径:
        raise 开版错误(f"载荷哈希口径不一致:{口径.get('口径')}")
    return 载荷哈希(属性)


def _取版本们(conn, 表: str, 父列: str, 父哈希: str):
    return conn.execute(
        f"SELECT 编号, {父列} AS 父键, 装载日, 载荷哈希, 属性, 是否当前 "
        f"FROM {表} WHERE {父列}=? ORDER BY 编号",
        (父哈希,),
    ).fetchall()


def _插入(conn, 表: str, 父列: str, 父哈希: str, 装载日: str, 哈希: str,
          属性: dict[str, Any]) -> int:
    cur = conn.execute(
        f"INSERT INTO {表}({父列}, 装载日, 载荷哈希, 属性, 是否当前) VALUES (?,?,?,?,1)",
        (父哈希, 装载日, 哈希, json.dumps(属性, ensure_ascii=False)),
    )
    return int(cur.lastrowid)


def 开卫星版(conn, 类: str, 父哈希: str, 属性: dict[str, Any], 装载日: str,
             口径: dict[str, Any] | None = None) -> dict[str, Any]:
    """单父键开版写闸，关旧与开新同事务。

    调用方已在事务内（整批装载）时用 SAVEPOINT，半截失败只回滚本次开版；
    单独调用时自开事务并自行提交/回滚。
    返回 {"动作": "首版"|"开新版"|"跳过", ...}；同哈希时绝不插入新当前。
    """
    if 类 not in 表配置:
        raise 开版错误(f"未知卫星类:{类}")
    表, 父列, _ = 表配置[类]
    口径 = 口径 or 取口径(conn)
    新哈希 = 算载荷哈希(属性, 口径)

    自管事务 = not conn.in_transaction
    if 自管事务:
        conn.execute("BEGIN IMMEDIATE")
    conn.execute("SAVEPOINT 卫星开版")
    try:
        结果 = _开版主体(conn, 类, 表, 父列, 父哈希, 属性, 装载日, 新哈希, 口径)
        conn.execute("RELEASE SAVEPOINT 卫星开版")
        if 自管事务:
            conn.commit()
        return 结果
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT 卫星开版")
        conn.execute("RELEASE SAVEPOINT 卫星开版")
        if 自管事务:
            conn.rollback()
        raise


def _开版主体(conn, 类: str, 表: str, 父列: str, 父哈希: str, 属性: dict[str, Any],
              装载日: str, 新哈希: str, 口径: dict[str, Any]) -> dict[str, Any]:
    版本们 = _取版本们(conn, 表, 父列, 父哈希)
    当前们 = [r for r in 版本们 if r["是否当前"] == 1]

    if len(当前们) > 1:
        raise 开版错误(f"{类}:{父哈希} 已存在双当前，拒绝开版")
    if not 版本们:
        编号 = _插入(conn, 表, 父列, 父哈希, 装载日, 新哈希, 属性)
        return {"动作": "首版", "编号": 编号, "载荷哈希": 新哈希}
    if not 当前们:
        raise 开版错误(f"{类}:{父哈希} 有历史版但无当前，拒绝开版")

    当前 = 当前们[0]
    try:
        旧哈希 = 算载荷哈希(json.loads(当前["属性"]), 口径)
    except Exception as e:
        raise 开版错误(f"{类}:{父哈希} 当前版属性不可解析:{e}") from e
    if 旧哈希 != 当前["载荷哈希"]:
        raise 开版错误(f"{类}:{父哈希} 当前版载荷哈希与属性不符，拒绝开版")
    if 旧哈希 == 新哈希:
        return {
            "动作": "跳过",
            "原因": "同哈希",
            "编号": 当前["编号"],
            "载荷哈希": 新哈希,
        }

    影响 = conn.execute(
        f"UPDATE {表} SET 是否当前=0 WHERE 编号=? AND 是否当前=1",
        (当前["编号"],),
    ).rowcount
    if 影响 != 1:
        raise 开版错误(f"{类}:{父哈希} 关闭旧当前失败（影响 {影响} 行）")
    编号 = _插入(conn, 表, 父列, 父哈希, 装载日, 新哈希, 属性)
    return {
        "动作": "开新版",
        "编号": 编号,
        "载荷哈希": 新哈希,
        "旧编号": 当前["编号"],
        "旧哈希": 旧哈希,
    }


def 写闸状态(conn) -> dict[str, Any]:
    """检查库层写闸（单当前唯一索引 + 属性不可覆盖 + 同哈希禁开）是否齐备。"""
    缺口: list[str] = []
    for 表, _父列, _父表 in 表配置.values():
        for 类型, 名 in (
            ("index", f"{表}_单当前"),
            ("trigger", f"{表}_禁改版内容"),
            ("trigger", f"{表}_禁复活历史"),
            ("trigger", f"{表}_禁同哈希新当前"),
        ):
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type=? AND name=?", (类型, 名)
            ).fetchone():
                缺口.append(名)
    return {"完整": not 缺口, "缺口": 缺口}


def _父键标签(conn, 类: str, 父哈希: str) -> str | None:
    try:
        if 类 == "订购":
            r = conn.execute(
                "SELECT a.业务键 AS 号, b.业务键 AS 套 "
                "FROM 链接_号卡套餐 l "
                "JOIN 枢纽_号卡 a ON a.哈希键=l.号卡哈希 "
                "JOIN 枢纽_套餐 b ON b.哈希键=l.套餐哈希 "
                "WHERE l.哈希键=?",
                (父哈希,),
            ).fetchone()
            return f"{r['号']} / {r['套']}" if r else None
        表 = {"号卡": "枢纽_号卡", "套餐": "枢纽_套餐", "客户": "枢纽_客户"}[类]
        r = conn.execute(f"SELECT 业务键 FROM {表} WHERE 哈希键=?", (父哈希,)).fetchone()
        return r["业务键"] if r else None
    except Exception:
        return None


def _汇总问题(组们: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "双当前": [f"{g['表']}:{g['父键']}" for g in 组们 if g["是否双当前"]],
        "有历史无当前": [
            f"{g['表']}:{g['父键']}" for g in 组们 if g["当前数"] == 0 and g["版本"]
        ],
        "哈希不符": [
            f"{g['表']}:{g['父键']}#{编号}"
            for g in 组们
            for 编号 in g["哈希不符编号"]
        ],
        "同哈希空开": [
            f"{g['表']}:{g['父键']}" for g in 组们 if g["相邻同哈希"]
        ],
    }


def 全量复核(conn) -> dict[str, Any]:
    """按站规字段集重算全部卫星版本的载荷哈希，并核对当前版约束。"""
    口径 = 取口径(conn)
    组们: list[dict[str, Any]] = []
    for 类, (表, 父列, _父表) in 表配置.items():
        行们 = conn.execute(
            f"SELECT 编号, {父列} AS 父键, 装载日, 载荷哈希, 属性, 是否当前 "
            f"FROM {表} ORDER BY {父列}, 编号"
        ).fetchall()
        按父: dict[str, list[dict[str, Any]]] = {}
        for r in 行们:
            按父.setdefault(r["父键"], []).append(dict(r))
        for 父键, 版本们 in 按父.items():
            哈希不符编号: list[int] = []
            for v in 版本们:
                try:
                    复算 = 算载荷哈希(json.loads(v["属性"]), 口径)
                except Exception:
                    复算 = None
                v["复算哈希"] = 复算
                v["哈希相符"] = bool(复算 is not None and 复算 == v["载荷哈希"])
                if not v["哈希相符"]:
                    哈希不符编号.append(v["编号"])
            当前们 = [v for v in 版本们 if v["是否当前"] == 1]
            历史 = [v for v in 版本们 if v["是否当前"] != 1]
            相邻同哈希 = any(
                版本们[i]["载荷哈希"] == 版本们[i - 1]["载荷哈希"]
                for i in range(1, len(版本们))
            )
            通过 = (
                len(当前们) == 1
                and not 相邻同哈希
                and not 哈希不符编号
            )
            组们.append(
                {
                    "类": 类,
                    "表": 表,
                    "父键": 父键,
                    "业务键": _父键标签(conn, 类, 父键),
                    "当前": 当前们[0] if len(当前们) == 1 else None,
                    "当前们": 当前们,
                    "历史": 历史,
                    "版本": 版本们,
                    "当前数": len(当前们),
                    "是否双当前": len(当前们) > 1,
                    "载荷哈希": 当前们[0]["载荷哈希"] if len(当前们) == 1 else None,
                    "哈希不符编号": 哈希不符编号,
                    "哈希可复算": not 哈希不符编号,
                    "相邻同哈希": 相邻同哈希,
                    "通过": 通过,
                }
            )
    问题 = _汇总问题(组们)
    return {
        "口径": 口径,
        "组": 组们,
        "问题": 问题,
        "通过": not any(问题.values()),
    }


def 开版贯验(conn=None, 类: str | None = None, 父键: str | None = None) -> dict[str, Any]:
    """只读核对接口：父键、字段集口径、当前/历史版、载荷哈希、是否双当前。"""
    自开 = conn is None
    conn = conn or 连接()
    try:
        报 = 全量复核(conn)
        写闸 = 写闸状态(conn)
    finally:
        if 自开:
            conn.close()
    组们 = 报["组"]
    if 类:
        组们 = [g for g in 组们 if g["类"] == 类]
    if 父键:
        组们 = [g for g in 组们 if g["父键"] == 父键]
    问题 = _汇总问题(组们)
    return {
        "接口": "卫星开版贯验",
        "口径": 报["口径"],
        "写闸": 写闸,
        "类": 类,
        "父键": 父键,
        "组": 组们,
        "双当前": 问题["双当前"],
        "问题": 问题,
        "通过": not any(问题.values()) and 写闸["完整"],
    }
