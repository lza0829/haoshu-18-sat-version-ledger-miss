import json
from datetime import datetime, timezone

from app.db import 夹具目录, 连接

建表 = """
CREATE TABLE IF NOT EXISTS 字段集世代 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  父哈希 TEXT NOT NULL,
  新卫星哈希 TEXT NOT NULL DEFAULT '',
  字段集口径 TEXT NOT NULL DEFAULT '[]',
  站规版本 TEXT NOT NULL DEFAULT '',
  批号 TEXT NOT NULL DEFAULT '',
  时刻 TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS 站规 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 装载批次 (
  编号 TEXT PRIMARY KEY,
  装载日 TEXT NOT NULL,
  时刻 TEXT NOT NULL,
  报告 TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS 枢纽_号卡 (
  哈希键 TEXT PRIMARY KEY,
  业务键 TEXT NOT NULL UNIQUE,
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 枢纽_套餐 (
  哈希键 TEXT PRIMARY KEY,
  业务键 TEXT NOT NULL UNIQUE,
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 枢纽_客户 (
  哈希键 TEXT PRIMARY KEY,
  业务键 TEXT NOT NULL UNIQUE,
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 链接_号卡套餐 (
  哈希键 TEXT PRIMARY KEY,
  号卡哈希 TEXT NOT NULL REFERENCES 枢纽_号卡(哈希键),
  套餐哈希 TEXT NOT NULL REFERENCES 枢纽_套餐(哈希键),
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 链接_号卡客户 (
  哈希键 TEXT PRIMARY KEY,
  号卡哈希 TEXT NOT NULL REFERENCES 枢纽_号卡(哈希键),
  客户哈希 TEXT NOT NULL REFERENCES 枢纽_客户(哈希键),
  装载日 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 卫星_号卡属性 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  号卡哈希 TEXT NOT NULL REFERENCES 枢纽_号卡(哈希键),
  装载日 TEXT NOT NULL,
  载荷哈希 TEXT NOT NULL,
  属性 TEXT NOT NULL,
  是否当前 INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS 卫星_套餐属性 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  套餐哈希 TEXT NOT NULL REFERENCES 枢纽_套餐(哈希键),
  装载日 TEXT NOT NULL,
  载荷哈希 TEXT NOT NULL,
  属性 TEXT NOT NULL,
  是否当前 INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS 卫星_客户属性 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  客户哈希 TEXT NOT NULL REFERENCES 枢纽_客户(哈希键),
  装载日 TEXT NOT NULL,
  载荷哈希 TEXT NOT NULL,
  属性 TEXT NOT NULL,
  是否当前 INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS 卫星_订购属性 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  链接哈希 TEXT NOT NULL REFERENCES 链接_号卡套餐(哈希键),
  装载日 TEXT NOT NULL,
  载荷哈希 TEXT NOT NULL,
  属性 TEXT NOT NULL,
  是否当前 INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS 隔离匣 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  原因 TEXT NOT NULL,
  载荷 TEXT NOT NULL,
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 金库贯验 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  枢纽数 INTEGER NOT NULL,
  链接数 INTEGER NOT NULL,
  卫星当前数 INTEGER NOT NULL,
  是否通过 INTEGER NOT NULL,
  说明 TEXT NOT NULL
);
卫星写闸：同父键只许一条当前；已落版本禁改内容/禁复活；同哈希禁再开当前。"""
    段 = []
    for 表, 父列 in _卫星表配置:
        段.append(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {表}_单当前 "
            f"ON {表}({父列}) WHERE 是否当前=1;"
        )
        段.append(
            f"""CREATE TRIGGER IF NOT EXISTS {表}_禁改版内容
BEFORE UPDATE ON {表}
WHEN OLD.{父列}<>NEW.{父列}
  OR OLD.装载日<>NEW.装载日
  OR OLD.载荷哈希<>NEW.载荷哈希
  OR OLD.属性<>NEW.属性
BEGIN
  SELECT RAISE(ABORT, '{表}:禁止原地改写已落版本，须关旧开新');
END;"""
        )
        段.append(
            f"""CREATE TRIGGER IF NOT EXISTS {表}_禁复活历史
BEFORE UPDATE ON {表}
WHEN OLD.是否当前=0 AND NEW.是否当前=1
BEGIN
  SELECT RAISE(ABORT, '{表}:禁止把历史版复活为当前');
END;"""
        )
        段.append(
            f"""CREATE TRIGGER IF NOT EXISTS {表}_禁同哈希新当前
BEFORE INSERT ON {表}
WHEN NEW.是否当前=1 AND EXISTS (
  SELECT 1 FROM {表}
  WHERE {父列}=NEW.{父列} AND 是否当前=1 AND 载荷哈希=NEW.载荷哈希
)
BEGIN
  SELECT RAISE(ABORT, '{表}:同载荷哈希禁止再开当前');
END;"""
        )
    return "\n".join(段)


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def 哈希键(*parts: str) -> str:
    import hashlib

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def 载荷哈希(obj) -> str:
    import hashlib

    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def 初始化库() -> None:
    conn = 连接()
    conn.executescript(建表)
    conn.executescript(_卫星写闸())
    for k, v in {
        "站名": "号枢",
        "默认装载日": "2026-11-21",
        "卫星载荷哈希口径": "全属性字段",
        "卫星载荷哈希字段": "*",
    }.items():
        conn.execute("INSERT OR IGNORE INTO 站规(键, 值) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()
