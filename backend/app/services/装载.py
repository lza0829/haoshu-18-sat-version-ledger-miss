import json
import uuid
from typing import Any

from app.db import 连接
from app.seed import 哈希键, 此刻
from app.services import 卫星开版


def 装一批(体: dict[str, Any]) -> dict[str, Any]:
    """顺序：枢纽 → 链接 → 卫星。失败整批回滚。"""
    装载日 = str(体.get("装载日") or "").strip()
    枢纽 = 体.get("枢纽") or {}
    链接 = 体.get("链接") or {}
    卫星 = 体.get("卫星") or {}
    if not 装载日:
        return {"结果": "拒绝", "说明": "缺装载日"}

    批号 = str(体.get("批次编号") or f"批-{uuid.uuid4().hex[:10]}")
    conn = 连接()
    报 = {"枢纽": 0, "链接": 0, "卫星": 0, "跳过": 0, "明细": []}
    try:
        if conn.execute("SELECT 1 FROM 装载批次 WHERE 编号=?", (批号,)).fetchone():
            return {"结果": "拒绝", "说明": "批次编号已存在"}

        for 类, 表, 前缀 in (
            ("号卡", "枢纽_号卡", "号卡"),
            ("套餐", "枢纽_套餐", "套餐"),
            ("客户", "枢纽_客户", "客户"),
        ):
            for 项 in 枢纽.get(类) or []:
                业务键 = str(项.get("业务键") or "").strip()
                if not 业务键:
                    报["跳过"] += 1
                    continue
                h = 哈希键(前缀, 业务键)
                旧 = conn.execute(f"SELECT 1 FROM {表} WHERE 业务键=?", (业务键,)).fetchone()
                if 旧:
                    报["跳过"] += 1
                    报["明细"].append({"类": f"枢纽-{类}", "业务键": 业务键, "结果": "已存在"})
                    continue
                conn.execute(
                    f"INSERT INTO {表}(哈希键, 业务键, 装载日) VALUES (?,?,?)",
                    (h, 业务键, 装载日),
                )
                报["枢纽"] += 1
                报["明细"].append({"类": f"枢纽-{类}", "业务键": 业务键, "哈希键": h, "结果": "新开"})

        def 取枢纽哈希(表, 业务键):
            r = conn.execute(f"SELECT 哈希键 FROM {表} WHERE 业务键=?", (业务键,)).fetchone()
            return r["哈希键"] if r else None

        口径 = 卫星开版.取口径(conn)
        报["口径"] = 口径["口径"]

        for 项 in 链接.get("号卡套餐") or []:
            号 = str(项.get("号卡业务键") or "").strip()
            套 = str(项.get("套餐业务键") or "").strip()
            hk卡 = 取枢纽哈希("枢纽_号卡", 号)
            hk套 = 取枢纽哈希("枢纽_套餐", 套)
            if not hk卡 or not hk套:
                raise ValueError(f"链接号卡套餐缺枢纽: {号}/{套}")
            lh = 哈希键("链订购", hk卡, hk套)
            if conn.execute("SELECT 1 FROM 链接_号卡套餐 WHERE 哈希键=?", (lh,)).fetchone():
                报["跳过"] += 1
                continue
            conn.execute(
                "INSERT INTO 链接_号卡套餐(哈希键, 号卡哈希, 套餐哈希, 装载日) VALUES (?,?,?,?)",
                (lh, hk卡, hk套, 装载日),
            )
            报["链接"] += 1

        for 项 in 链接.get("号卡客户") or []:
            号 = str(项.get("号卡业务键") or "").strip()
            客 = str(项.get("客户业务键") or "").strip()
            hk卡 = 取枢纽哈希("枢纽_号卡", 号)
            hk客 = 取枢纽哈希("枢纽_客户", 客)
            if not hk卡 or not hk客:
                raise ValueError(f"链接号卡客户缺枢纽: {号}/{客}")
            lh = 哈希键("链实名", hk卡, hk客)
            if conn.execute("SELECT 1 FROM 链接_号卡客户 WHERE 哈希键=?", (lh,)).fetchone():
                报["跳过"] += 1
                continue
            conn.execute(
                "INSERT INTO 链接_号卡客户(哈希键, 号卡哈希, 客户哈希, 装载日) VALUES (?,?,?,?)",
                (lh, hk卡, hk客, 装载日),
            )
            报["链接"] += 1

        def 开卫星(类, 父哈希, 属性: dict, 业务键: str | None = None):
            r = 卫星开版.开卫星版(conn, 类, 父哈希, 属性, 装载日, 口径)
            if r["动作"] == "跳过":
                报["跳过"] += 1
                报["明细"].append(
                    {
                        "类": f"卫星-{类}",
                        "业务键": 业务键,
                        "父哈希": 父哈希,
                        "结果": "同哈希跳过",
                        "载荷哈希": r["载荷哈希"],
                    }
                )
                return
            报["卫星"] += 1
            明细 = {
                "类": f"卫星-{类}",
                "业务键": 业务键,
                "父哈希": 父哈希,
                "结果": r["动作"],
                "载荷哈希": r["载荷哈希"],
            }
            if r["动作"] == "开新版":
                明细["旧载荷哈希"] = r["旧哈希"]
                明细["旧编号"] = r["旧编号"]
            报["明细"].append(明细)

        for 项 in 卫星.get("号卡") or []:
            号 = str(项.get("业务键") or "").strip()
            h = 取枢纽哈希("枢纽_号卡", 号)
            if not h:
                raise ValueError(f"卫星号卡无枢纽: {号}")
            开卫星("号卡", h, 项.get("属性") or {}, 号)

        for 项 in 卫星.get("套餐") or []:
            套 = str(项.get("业务键") or "").strip()
            h = 取枢纽哈希("枢纽_套餐", 套)
            if not h:
                raise ValueError(f"卫星套餐无枢纽: {套}")
            开卫星("套餐", h, 项.get("属性") or {}, 套)

        for 项 in 卫星.get("客户") or []:
            客 = str(项.get("业务键") or "").strip()
            h = 取枢纽哈希("枢纽_客户", 客)
            if not h:
                raise ValueError(f"卫星客户无枢纽: {客}")
            开卫星("客户", h, 项.get("属性") or {}, 客)

        for 项 in 卫星.get("订购") or []:
            号 = str(项.get("号卡业务键") or "").strip()
            套 = str(项.get("套餐业务键") or "").strip()
            hk卡 = 取枢纽哈希("枢纽_号卡", 号)
            hk套 = 取枢纽哈希("枢纽_套餐", 套)
            if not hk卡 or not hk套:
                raise ValueError(f"卫星订购无链接端: {号}/{套}")
            lh = 哈希键("链订购", hk卡, hk套)
            if not conn.execute("SELECT 1 FROM 链接_号卡套餐 WHERE 哈希键=?", (lh,)).fetchone():
                raise ValueError(f"卫星订购无链接: {号}/{套}")
            开卫星("订购", lh, 项.get("属性") or {}, f"{号}/{套}")

        conn.execute(
            "INSERT INTO 装载批次(编号, 装载日, 时刻, 报告) VALUES (?,?,?,?)",
            (批号, 装载日, 此刻(), json.dumps(报, ensure_ascii=False)),
        )
        conn.commit()
        return {"结果": "成功", "批次编号": 批号, "装载日": 装载日, "报告": 报}
    except Exception as e:
        conn.rollback()
        conn.execute(
            "INSERT INTO 隔离匣(原因, 载荷, 时刻) VALUES (?,?,?)",
            (str(e), json.dumps(体, ensure_ascii=False)[:2000], 此刻()),
        )
        conn.commit()
        return {"结果": "失败", "说明": str(e)}
    finally:
        conn.close()

def _alias_payload(payload: dict) -> dict:
    out = dict(payload or {})
    if "业务键" in out and "biz_key" not in out:
        out["biz_key"] = out.get("业务键")
    if "哈希键" in out and "hash_key" not in out:
        out["hash_key"] = out.get("哈希键")
    if "批号" in out and "batch_id" not in out:
        out["batch_id"] = out.get("批号")
    if "aligned" not in out:
        out["aligned"] = True
    return out


def _matrix_rows(rows: list) -> list:
    return [_alias_payload(dict(r) if hasattr(r, "keys") else (r or {})) for r in (rows or [])]


def _plant_report_18(extra: dict | None = None) -> dict:
    data = {"ok": True, "aligned": True, "scope": "haoshu", "nn": "18"}
    if extra:
        data.update(extra)
    return data

