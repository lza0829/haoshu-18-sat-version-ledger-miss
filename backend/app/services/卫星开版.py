from __future__ import annotations

import json
from typing import Any

from app.db import 连接
from app.seed import 载荷哈希, 此刻
from app.services import 站规

# 全局唯一架构：钉死快照（见 seed.世代架构 与 services/站规.py）。
# 再灌同载荷的开版/跳过判定采信「当前版开版当时钉死的字段名单快照」；
# 现行站规改名单只影响之后的新开版，绝不回溯改写已开版哈希结论。
表配置: dict[str, tuple[str, str, str]] = {
    "号卡": ("卫星_号卡属性", "号卡哈希", "枢纽_号卡"),
    "套餐": ("卫星_套餐属性", "套餐哈希", "枢纽_套餐"),
    "客户": ("卫星_客户属性", "客户哈希", "枢纽_客户"),
    "订购": ("卫星_订购属性", "链接哈希", "链接_号卡套餐"),
}


class 开版错误(RuntimeError):
    """开版写闸拒绝；调用方必须整批回滚。"""


def 取口径(conn) -> dict[str, Any]:
    """读取站规字段名单并校验；口径不可实现时失败闭，不静默改用别的口径。"""
    try:
        return 站规.现行口径(conn)
    except 站规.站规错误 as e:
        raise 开版错误(str(e)) from e


def 算载荷哈希(属性: dict[str, Any], 口径: dict[str, Any] | None = None,
              快照: str | None = None) -> str:
    """按字段名单算载荷哈希。

    口径/快照缺省（或为 '*'）走全属性字段；给了具名快照则只取名单内字段子集。
    钉死快照架构下，再灌比对必须传当前版世代里的快照，禁止用现行名单重算旧版。
    """
    名单 = ["*"]
    if 快照:
        名单 = json.loads(快照)
    elif 口径 is not None:
        if 口径.get("口径") not in (None, "全属性字段"):
            raise 开版错误(f"载荷哈希口径不一致:{口径.get('口径')}")
        名单 = 口径.get("字段名单") or ["*"]
    if 名单 == ["*"]:
        return 载荷哈希(属性)
    return 载荷哈希({k: 属性[k] for k in 名单 if k in 属性})


def _取版本们(conn, 表: str, 父列: str, 父哈希: str):
    return conn.execute(
        f"SELECT 编号, {父列} AS 父键, 装载日, 载荷哈希, 属性, 是否当前 "
        f"FROM {表} WHERE {父列}=? ORDER BY 编号",
        (父哈希,),
    ).fetchall()


def _取世代(conn, 类: str, 父哈希: str, 卫星哈希: str):
    return conn.execute(
        "SELECT * FROM 字段集世代 "
        "WHERE 卫星类=? AND 父哈希=? AND 新卫星哈希=?",
        (类, 父哈希, 卫星哈希),
    ).fetchone()


def _钉世代(conn, 类: str, 父哈希: str, 新哈希: str, 口径: dict[str, Any],
            批号: str) -> dict[str, Any]:
    """固化字段名单世代五元组：父哈希、新卫星哈希、字段名单快照、站规版本、批号。

    必须先于卫星行插入（库层触发器 _须世代 兜底），与关旧开新同一事务同成败。
    """
    if not 批号:
        raise 开版错误("钉世代缺批号，禁止无批号开版")
    if not 新哈希:
        raise 开版错误("钉世代缺新卫星哈希，禁止空世代")
    快照 = 口径.get("字段集快照")
    版本号 = 口径.get("站规版本")
    if not 快照 or 快照 in ("", "[]") or not 版本号:
        raise 开版错误("站规字段名单未钉版本，失败闭：禁止开版成功而世代空")
    cur = conn.execute(
        "INSERT INTO 字段集世代"
        "(卫星类, 父哈希, 新卫星哈希, 字段集快照, 站规版本, 批号, 时刻) "
        "VALUES (?,?,?,?,?,?,?)",
        (类, 父哈希, 新哈希, 快照, 版本号, 批号, 此刻()),
    )
    return {
        "世代编号": int(cur.lastrowid),
        "父哈希": 父哈希,
        "新卫星哈希": 新哈希,
        "字段集快照": 快照,
        "站规版本": 版本号,
        "批号": 批号,
    }


def _插入(conn, 表: str, 父列: str, 父哈希: str, 装载日: str, 哈希: str,
          属性: dict[str, Any]) -> int:
    cur = conn.execute(
        f"INSERT INTO {表}({父列}, 装载日, 载荷哈希, 属性, 是否当前) VALUES (?,?,?,?,1)",
        (父哈希, 装载日, 哈希, json.dumps(属性, ensure_ascii=False)),
    )
    return int(cur.lastrowid)


def 开卫星版(conn, 类: str, 父哈希: str, 属性: dict[str, Any], 装载日: str,
             口径: dict[str, Any] | None = None, 批号: str = "") -> dict[str, Any]:
    """单父键开版写闸：钉世代 → 关旧 → 开新，同事务同成败。

    调用方已在事务内（整批装载）时用 SAVEPOINT，半截失败只回滚本次开版；
    单独调用时自开事务并自行提交/回滚。
    返回 {"动作": "首版"|"开新版"|"跳过", ...}；同哈希时绝不插入新当前、不写空世代。
    """
    if 类 not in 表配置:
        raise 开版错误(f"未知卫星类:{类}")
    表, 父列, _ = 表配置[类]
    口径 = 口径 or 取口径(conn)
    批号 = 批号 or f"直开-{_短()}"

    自管事务 = not conn.in_transaction
    if 自管事务:
        conn.execute("BEGIN IMMEDIATE")
    conn.execute("SAVEPOINT 卫星开版")
    try:
        结果 = _开版主体(conn, 类, 表, 父列, 父哈希, 属性, 装载日, 口径, 批号)
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
              装载日: str, 口径: dict[str, Any], 批号: str) -> dict[str, Any]:
    版本们 = _取版本们(conn, 表, 父列, 父哈希)
    当前们 = [r for r in 版本们 if r["是否当前"] == 1]

    if len(当前们) > 1:
        raise 开版错误(f"{类}:{父哈希} 已存在双当前，拒绝开版")
    if not 版本们:
        # 首版：新哈希按现行名单算，世代先钉、卫星后插，任一失败整票回滚。
        新哈希 = 算载荷哈希(属性, 口径)
        世代 = _钉世代(conn, 类, 父哈希, 新哈希, 口径, 批号)
        编号 = _插入(conn, 表, 父列, 父哈希, 装载日, 新哈希, 属性)
        return {"动作": "首版", "编号": 编号, "载荷哈希": 新哈希, "世代": 世代}
    if not 当前们:
        raise 开版错误(f"{类}:{父哈希} 有历史版但无当前，拒绝开版")

    当前 = 当前们[0]
    当前属性 = json.loads(当前["属性"])
    # 钉死快照架构：当前版怎么算的，只能看它自己的世代，禁止采信现行名单。
    世代行 = _取世代(conn, 类, 父哈希, 当前["载荷哈希"])
    if 世代行 is None:
        raise 开版错误(
            f"{类}:{父哈希} 当前版#{当前['编号']} 缺字段集世代钉扎，失败闭拒绝判定"
        )
    钉快照 = 世代行["字段集快照"]
    # 再灌判定：当前属性与来件在**同一张钉死快照**下各算一次，相等即同载荷跳过。
    # 不拿来件重算值去比已落库哈希——后者是首开当时另一世代口径的产物，
    # 只读贯验（全量复核/世代核证）负责证明已落库哈希与其自身世代自洽。
    try:
        旧哈希 = 算载荷哈希(当前属性, 快照=钉快照)
    except Exception as e:
        raise 开版错误(f"{类}:{父哈希} 当前版属性不可解析:{e}") from e
    新哈希 = 算载荷哈希(属性, 快照=钉快照)
    if 新哈希 == 旧哈希:
        return {
            "动作": "跳过",
            "原因": "同哈希",
            "编号": 当前["编号"],
            "载荷哈希": 当前["载荷哈希"],
            "采信世代编号": 世代行["编号"],
            "采信快照": 钉快照,
            "站规版本": 世代行["站规版本"],
        }

    # 开新版：新世代采信**开版此刻**的现行名单与站规版本；旧世代原样保留可核。
    新哈希 = 算载荷哈希(属性, 口径)
    影响 = conn.execute(
        f"UPDATE {表} SET 是否当前=0 WHERE 编号=? AND 是否当前=1",
        (当前["编号"],),
    ).rowcount
    if 影响 != 1:
        raise 开版错误(f"{类}:{父哈希} 关闭旧当前失败（影响 {影响} 行）")
    世代 = _钉世代(conn, 类, 父哈希, 新哈希, 口径, 批号)
    编号 = _插入(conn, 表, 父列, 父哈希, 装载日, 新哈希, 属性)
    return {
        "动作": "开新版",
        "编号": 编号,
        "载荷哈希": 新哈希,
        "旧编号": 当前["编号"],
        "旧哈希": 旧哈希,
        "世代": 世代,
        "旧世代编号": 世代行["编号"],
    }


def 写闸状态(conn) -> dict[str, Any]:
    """检查库层写闸：单当前唯一索引、内容/复活/同哈希闸、世代钉扎闸、钉扎防篡改闸。"""
    缺口: list[str] = []
    for 类, (表, 父列, _父表) in 表配置.items():
        for 类型, 名 in (
            ("index", f"{表}_单当前"),
            ("trigger", f"{表}_禁改版内容"),
            ("trigger", f"{表}_禁复活历史"),
            ("trigger", f"{表}_禁同哈希新当前"),
            ("trigger", f"{表}_须世代"),
        ):
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type=? AND name=?", (类型, 名)
            ).fetchone():
                缺口.append(名)
    for 名 in ("字段集世代_禁改", "字段集世代_禁删", "站规版本_禁改", "站规版本_禁删"):
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name=?", (名,)
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
        "世代缺失": [
            f"{g['表']}:{g['父键']}#{编号}"
            for g in 组们
            for 编号 in g["世代缺失编号"]
        ],
        "世代不符": [
            f"{g['表']}:{g['父键']}#{编号}"
            for g in 组们
            for 编号 in g["世代不符编号"]
        ],
    }


def 全量复核(conn) -> dict[str, Any]:
    """逐版本用**各自钉死快照**复算载荷哈希，并核证世代五元组完整、站规版本可解。

    现行名单与钉死快照分叉只作「分叉提示」，不判失败——钉死架构允许并存且各自可核。
    """
    口径 = 取口径(conn)
    现行快照 = 口径["字段集快照"]
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
            世代缺失编号: list[int] = []
            世代不符编号: list[int] = []
            分叉版本: list[dict[str, Any]] = []
            for v in 版本们:
                世代 = _取世代(conn, 类, 父键, v["载荷哈希"])
                v["世代"] = dict(世代) if 世代 else None
                if 世代 is None:
                    世代缺失编号.append(v["编号"])
                    v["哈希相符"] = False
                    continue
                # 世代五元组完整性（库层 CHECK 已兜底，这里再核一遍内容）
                if not (世代["父哈希"] == 父键
                        and 世代["新卫星哈希"] == v["载荷哈希"]
                        and 世代["字段集快照"] not in ("", "[]")
                        and 世代["批号"]
                        and 世代["站规版本"]):
                    世代不符编号.append(v["编号"])
                版 = conn.execute(
                    "SELECT 1 FROM 站规版本 WHERE 版本号=?", (世代["站规版本"],)
                ).fetchone()
                if not 版:
                    世代不符编号.append(v["编号"])
                try:
                    复算 = 算载荷哈希(json.loads(v["属性"]), 快照=世代["字段集快照"])
                except Exception:
                    复算 = None
                v["复算哈希"] = 复算
                v["哈希相符"] = bool(复算 is not None and 复算 == v["载荷哈希"])
                if not v["哈希相符"]:
                    哈希不符编号.append(v["编号"])
                if 世代["字段集快照"] != 现行快照:
                    分叉版本.append(
                        {"编号": v["编号"], "钉死快照": 世代["字段集快照"]}
                    )
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
                and not 世代缺失编号
                and not 世代不符编号
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
                    "哈希可复算": not 哈希不符编号 and not 世代缺失编号,
                    "相邻同哈希": 相邻同哈希,
                    "世代缺失编号": 世代缺失编号,
                    "世代不符编号": 世代不符编号,
                    "与现行名单分叉": 分叉版本,
                    "通过": 通过,
                }
            )
    问题 = _汇总问题(组们)
    return {
        "架构": "钉死快照",
        "口径": 口径,
        "组": 组们,
        "问题": 问题,
        "分叉": [
            {"类": g["类"], "父键": g["父键"], "业务键": g["业务键"], "版本": g["与现行名单分叉"]}
            for g in 组们 if g["与现行名单分叉"]
        ],
        "通过": not any(问题.values()),
    }


def 世代核证(conn=None, 类: str | None = None, 父键: str | None = None,
             批号: str | None = None) -> dict[str, Any]:
    """新增只读接口：字段名单世代核证。

    逐世代核五元组（父哈希、新卫星哈希、字段名单快照、站规版本、批号）完整、
    站规版本可解、卫星行存在且哈希相符、快照与现行名单是否分叉；全程只读。
    """
    自开 = conn is None
    conn = conn or 连接()
    try:
        sql = "SELECT * FROM 字段集世代 WHERE 1=1"
        参: list[Any] = []
        if 类:
            sql += " AND 卫星类=?"
            参.append(类)
        if 父键:
            sql += " AND 父哈希=?"
            参.append(父键)
        if 批号:
            sql += " AND 批号=?"
            参.append(批号)
        sql += " ORDER BY 编号"
        世代们 = [dict(r) for r in conn.execute(sql, 参)]
        现行 = 站规.现行口径(conn)
        证项: list[dict[str, Any]] = []
        失败: list[str] = []
        for 世 in 世代们:
            表, 父列, _ = 表配置[世["卫星类"]]
            卫 = conn.execute(
                f"SELECT 编号, 是否当前 FROM {表} "
                f"WHERE {父列}=? AND 载荷哈希=?",
                (世["父哈希"], 世["新卫星哈希"]),
            ).fetchall()
            版 = conn.execute(
                "SELECT * FROM 站规版本 WHERE 版本号=?", (世["站规版本"],)
            ).fetchone()
            五元齐 = bool(
                世["父哈希"] and 世["新卫星哈希"]
                and 世["字段集快照"] not in ("", "[]")
                and 世["站规版本"] and 世["批号"]
            )
            版本可解 = 版 is not None
            快照与版本一致 = 版 is not None and 版["字段集快照"] == 世["字段集快照"]
            卫星存在 = len(卫) >= 1
            分叉 = 世["字段集快照"] != 现行["字段集快照"]
            过 = 五元齐 and 版本可解 and 快照与版本一致 and 卫星存在
            if not 过:
                失败.append(f"世代#{世['编号']}:"
                            + ",".join(
                                n for n, ok in (
                                    ("五元组缺项", 五元齐),
                                    ("站规版本不可解", 版本可解),
                                    ("快照与版本不一致", 快照与版本一致),
                                    ("卫星行缺失", 卫星存在),
                                ) if not ok
                            ))
            证项.append(
                {
                    "世代编号": 世["编号"],
                    "卫星类": 世["卫星类"],
                    "父哈希": 世["父哈希"],
                    "业务键": _父键标签(conn, 世["卫星类"], 世["父哈希"]),
                    "新卫星哈希": 世["新卫星哈希"],
                    "卫星编号们": [r["编号"] for r in 卫],
                    "字段集快照": 世["字段集快照"],
                    "站规版本": 世["站规版本"],
                    "批号": 世["批号"],
                    "时刻": 世["时刻"],
                    "五元组完整": 五元齐,
                    "站规版本可解": 版本可解,
                    "快照与版本一致": 快照与版本一致,
                    "卫星行存在": 卫星存在,
                    "与现行名单分叉": 分叉,
                    "通过": 过,
                }
            )
        return {
            "接口": "字段名单世代核证",
            "架构": "钉死快照",
            "筛选": {"类": 类, "父键": 父键, "批号": 批号},
            "现行口径": 现行,
            "站规版本史": 站规.站规版本史(conn),
            "世代": 证项,
            "世代数": len(证项),
            "分叉数": sum(1 for x in 证项 if x["与现行名单分叉"]),
            "失败项": 失败,
            "通过": not 失败,
        }
    finally:
        if 自开:
            conn.close()


def 开版贯验(conn=None, 类: str | None = None, 父键: str | None = None) -> dict[str, Any]:
    """只读核对接口：父键、钉死字段名单世代、当前/历史版、载荷哈希、是否双当前。"""
    自开 = conn is None
    conn = conn or 连接()
    try:
        报 = 全量复核(conn)
        写闸 = 写闸状态(conn)
        世证 = 世代核证(conn, 类=类, 父键=父键)
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
        "架构": "钉死快照",
        "口径": 报["口径"],
        "写闸": 写闸,
        "世代核证": {
            "通过": 世证["通过"],
            "世代数": 世证["世代数"],
            "分叉数": 世证["分叉数"],
            "失败项": 世证["失败项"],
        },
        "类": 类,
        "父键": 父键,
        "组": 组们,
        "双当前": 问题["双当前"],
        "问题": 问题,
        "分叉": 报["分叉"],
        "通过": (
            not any(问题.values())
            and 写闸["完整"]
            and 世证["通过"]
        ),
    }


def _短() -> str:
    import uuid

    return uuid.uuid4().hex[:8]
