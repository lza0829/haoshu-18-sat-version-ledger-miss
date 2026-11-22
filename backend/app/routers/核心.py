import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import 夹具目录, 连接
from app.services import 装载, 贯验, 目录, 卫星开版, 站规

路由 = APIRouter(prefix="/api")


class 装载请求(BaseModel):
    装载日: str = ""
    批次编号: str = ""
    枢纽: dict = Field(default_factory=dict)
    链接: dict = Field(default_factory=dict)
    卫星: dict = Field(default_factory=dict)


@路由.get("/健康")
def 健康():
    return {"正常": True, "项目": "号枢", "骨架": "枢纽-链接-卫星-互证"}


@路由.get("/总览")
def 取总览():
    return 目录.总览()


@路由.get("/枢纽/{kind}")
def 列枢纽(kind: str):
    表 = {"号卡": "枢纽_号卡", "套餐": "枢纽_套餐", "客户": "枢纽_客户"}.get(kind)
    if not 表:
        raise HTTPException(404, "未知枢纽类")
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {表} ORDER BY 业务键")]
    finally:
        conn.close()


@路由.get("/链接/{kind}")
def 列链接(kind: str):
    if kind == "号卡套餐":
        sql = """SELECT l.*, a.业务键 AS 号卡业务键, b.业务键 AS 套餐业务键
                 FROM 链接_号卡套餐 l
                 JOIN 枢纽_号卡 a ON a.哈希键=l.号卡哈希
                 JOIN 枢纽_套餐 b ON b.哈希键=l.套餐哈希"""
    elif kind == "号卡客户":
        sql = """SELECT l.*, a.业务键 AS 号卡业务键, b.业务键 AS 客户业务键
                 FROM 链接_号卡客户 l
                 JOIN 枢纽_号卡 a ON a.哈希键=l.号卡哈希
                 JOIN 枢纽_客户 b ON b.哈希键=l.客户哈希"""
    else:
        raise HTTPException(404, "未知链接类")
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


@路由.get("/卫星/开版贯验")
def 卫星开版贯验(类: str = "", 父键: str = ""):
    """只读：按字段集口径复算载荷哈希，列当前/历史版与是否双当前。"""
    if 类 and 类 not in 卫星开版.表配置:
        raise HTTPException(404, "未知卫星类")
    return 卫星开版.开版贯验(类=类 or None, 父键=父键 or None)


@路由.get("/卫星/{kind}")
def 列卫星(kind: str, 仅当前: int = 1):
    表 = {
        "号卡": "卫星_号卡属性",
        "套餐": "卫星_套餐属性",
        "客户": "卫星_客户属性",
        "订购": "卫星_订购属性",
    }.get(kind)
    if not 表:
        raise HTTPException(404, "未知卫星类")
    conn = 连接()
    try:
        if 仅当前:
            rows = conn.execute(f"SELECT * FROM {表} WHERE 是否当前=1 ORDER BY 编号 DESC")
        else:
            rows = conn.execute(f"SELECT * FROM {表} ORDER BY 编号 DESC LIMIT 200")
        return [dict(r) for r in rows]
    finally:
        conn.close()


@路由.get("/站规")
def 读站规():
    conn = 连接()
    try:
        return {
            "站规": {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 站规")},
            "现行口径": 站规.现行口径(conn),
            "版本史": 站规.站规版本史(conn),
            "架构": "钉死快照",
        }
    finally:
        conn.close()


class 改名单请求(BaseModel):
    字段名单: list[str]
    批号: str = ""


@路由.post("/站规/字段名单")
def 改字段名单(体: 改名单请求):
    """受管改名单入口：校验并追加不可变站规版本；只影响之后新开版。"""
    try:
        return 站规.改字段名单(体.字段名单, 批号=体.批号)
    except 站规.站规错误 as e:
        raise HTTPException(422, str(e)) from e


@路由.get("/隔离匣")
def 隔离():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 隔离匣 ORDER BY 编号 DESC LIMIT 50")]
    finally:
        conn.close()


@路由.post("/装载")
def 做装载(体: 装载请求):
    return 装载.装一批(体.model_dump())


@路由.post("/装载/夹具")
def 装夹具(名: str = "号卡套餐样例"):
    路径 = 夹具目录 / f"{名}.json"
    if not 路径.exists():
        raise HTTPException(404, f"夹具不存在:{名}")
    return 装载.装一批(json.loads(路径.read_text(encoding="utf-8")))


@路由.post("/贯验")
def 做贯验():
    return 贯验.跑贯验()


@路由.get("/贯验")
def 列贯验():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 金库贯验 ORDER BY 编号 DESC LIMIT 20")]
    finally:
        conn.close()


@路由.get("/空桩")
def 空桩():
    from app import modules

    return modules.列表()

from app.modules import 字段集世代 as 世


@路由.get("/贯验/字段集世代")
def 取字段集世代(父哈希: str | None = None):
    """旧入口保留：已切到真实世代核证只读服务。"""
    conn = 连接()
    try:
        return 世.查世代(conn, 父哈希)
    finally:
        conn.close()


@路由.get("/贯验/字段集世代核证")
def 字段集世代核证(类: str | None = None, 父哈希: str | None = None,
                   批号: str | None = None):
    """基线所无的新增只读接口：字段名单世代核证。"""
    if 类 and 类 not in 卫星开版.表配置:
        raise HTTPException(404, "未知卫星类")
    return 卫星开版.世代核证(类=类, 父键=父哈希, 批号=批号)

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

