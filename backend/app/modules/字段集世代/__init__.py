状态 = "半截"


def 查世代(conn, 父哈希: str | None = None) -> dict:
    rows = []
    try:
        if 父哈希:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM 字段集世代 WHERE 父哈希=? ORDER BY 编号 DESC", (父哈希,)
            )]
        else:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM 字段集世代 ORDER BY 编号 DESC LIMIT 50"
            )]
    except Exception:
        rows = []
    return {"世代": rows, "钉死": False, "采信现行站规": True}


def 现用字段集(conn) -> list:
    row = conn.execute("SELECT 值 FROM 站规 WHERE 键=?", ("卫星哈希字段集",)).fetchone()
    if not row:
        return ["月费", "流量档", "有效期", "展示名", "备注"]
    import json
    try:
        v = json.loads(row["值"])
        return list(v) if isinstance(v, list) else ["月费", "流量档", "有效期", "展示名", "备注"]
    except Exception:
        return ["月费", "流量档", "有效期", "展示名", "备注"]
