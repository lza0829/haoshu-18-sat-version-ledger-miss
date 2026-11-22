import json
from datetime import datetime, timezone

from app.db import 夹具目录, 连接

# 架构抉择（全局唯一）：钉死快照。
# 每次卫星开版把当时的字段名单快照随版本同成败固化；再灌同载荷的开版/跳过判定
# 一律采信当前版「开版当时」的钉死快照，现行站规改名单不得回溯改写已开版哈希结论。
# 另一可行架构「现行站规重算覆盖」本仓不采纳：其语义为改名单后同载荷再灌须重算开版，
# 与本文件及 services/站规.py 贯彻的口径相反，禁止两种语义混用。
世代架构 = "钉死快照"

建表 = """
CREATE TABLE IF NOT EXISTS 站规版本 (
  版本号 INTEGER PRIMARY KEY AUTOINCREMENT,
  字段集快照 TEXT NOT NULL,
  口径 TEXT NOT NULL,
  站规键值 TEXT NOT NULL DEFAULT '',
  批号 TEXT NOT NULL DEFAULT '',
  时刻 TEXT NOT NULL,
  CHECK (字段集快照 <> '' AND 字段集快照 <> '[]')
);

CREATE TABLE IF NOT EXISTS 字段集世代 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  卫星类 TEXT NOT NULL,
  父哈希 TEXT NOT NULL,
  新卫星哈希 TEXT NOT NULL,
  字段集快照 TEXT NOT NULL,
  站规版本 INTEGER NOT NULL REFERENCES 站规版本(版本号),
  批号 TEXT NOT NULL,
  时刻 TEXT NOT NULL,
  CHECK (新卫星哈希 <> ''),
  CHECK (字段集快照 <> '' AND 字段集快照 <> '[]'),
  CHECK (批号 <> '')
);
-- 不设 (卫星类,父哈希,新卫星哈希) UNIQUE：载荷回到某历史哈希时基线允许重开为当前并追加新世代；
-- 防重由应用写闸（同哈希跳过）+ 卫星表「禁同哈希新当前」触发器 + 本表禁改禁删共同保证。

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
"""

_卫星表配置 = (
    ("号卡", "卫星_号卡属性", "号卡哈希"),
    ("套餐", "卫星_套餐属性", "套餐哈希"),
    ("客户", "卫星_客户属性", "客户哈希"),
    ("订购", "卫星_订购属性", "链接哈希"),
)


def _卫星写闸() -> str:
    """卫星写闸：同父键只许一条当前；已落版本禁改内容/禁复活；同哈希禁再开当前；
    卫星行插入前必须已钉死同（卫星类, 父哈希, 载荷哈希）的字段集世代——库层禁止「开版成功而世代空」。
    字段集世代与站规版本均禁改禁删，钉扎不可被原地篡改。"""
    段 = []
    for 类, 表, 父列 in _卫星表配置:
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
        # 库层硬约束：没有先钉死字段集世代的卫星行一律插不进来。
        段.append(
            f"""CREATE TRIGGER IF NOT EXISTS {表}_须世代
BEFORE INSERT ON {表}
WHEN NOT EXISTS (
  SELECT 1 FROM 字段集世代
  WHERE 卫星类='{类}' AND 父哈希=NEW.{父列} AND 新卫星哈希=NEW.载荷哈希
)
BEGIN
  SELECT RAISE(ABORT, '{表}:开版必须先钉死字段集世代，禁止无世代开版');
END;"""
        )
    段.append(
        """CREATE TRIGGER IF NOT EXISTS 字段集世代_禁改
BEFORE UPDATE ON 字段集世代
BEGIN
  SELECT RAISE(ABORT, '字段集世代:钉扎禁改，新旧结论只许随新开版追加');
END;"""
    )
    段.append(
        """CREATE TRIGGER IF NOT EXISTS 字段集世代_禁删
BEFORE DELETE ON 字段集世代
BEGIN
  SELECT RAISE(ABORT, '字段集世代:钉扎禁删');
END;"""
    )
    段.append(
        """CREATE TRIGGER IF NOT EXISTS 站规版本_禁改
BEFORE UPDATE ON 站规版本
BEGIN
  SELECT RAISE(ABORT, '站规版本:已钉版本禁改，改名单只能追加新版本');
END;"""
    )
    段.append(
        """CREATE TRIGGER IF NOT EXISTS 站规版本_禁删
BEFORE DELETE ON 站规版本
BEGIN
  SELECT RAISE(ABORT, '站规版本:已钉版本禁删');
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


def _迁移(conn) -> None:
    """旧库（半截桩时期的字段集世代表）结构不符则弃表重建；该表历史上无任何写入路径。"""
    info = conn.execute("PRAGMA table_info(字段集世代)").fetchall()
    现有列 = {r["name"] for r in info}
    if 现有列 and not {"卫星类", "父哈希", "新卫星哈希", "字段集快照", "站规版本"} <= 现有列:
        conn.execute("DROP TABLE IF EXISTS 字段集世代")


def 初始化库() -> None:
    conn = 连接()
    try:
        _迁移(conn)
        conn.executescript(建表)
        conn.executescript(_卫星写闸())
        for k, v in {
            "站名": "号枢",
            "默认装载日": "2026-11-21",
            "卫星载荷哈希口径": "全属性字段",
            "卫星载荷哈希字段": "*",
        }.items():
            conn.execute("INSERT OR IGNORE INTO 站规(键, 值) VALUES (?, ?)", (k, v))
        # 站规版本首钉：与现行字段名单对齐，供首次开版外键采信。
        conn.execute(
            "INSERT INTO 站规版本(字段集快照, 口径, 站规键值, 批号, 时刻) "
            "SELECT '[\"*\"]', '全属性字段', '*', '站规初始化', ? "
            "WHERE NOT EXISTS (SELECT 1 FROM 站规版本)",
            (此刻(),),
        )
        conn.commit()
    finally:
        conn.close()
