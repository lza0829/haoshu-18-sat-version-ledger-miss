import json
import os
import tempfile
import unittest
from pathlib import Path

临时 = os.path.join(tempfile.gettempdir(), "haoshu-test-shared")
os.makedirs(临时, exist_ok=True)
os.environ["数据目录"] = 临时

from app import seed
from app.db import 连接
from app.services import 卫星开版, 装载, 站规, 贯验

夹具 = Path("/workspace/fixtures")


def 装(装载日, 批次, 卫星, 枢纽=None, 链接=None):
    return 装载.装一批(
        {
            "装载日": 装载日,
            "批次编号": 批次,
            "枢纽": 枢纽 or {},
            "链接": 链接 or {},
            "卫星": 卫星,
        }
    )


def 套餐父哈希(业务键):
    conn = 连接()
    try:
        return conn.execute(
            "SELECT 哈希键 FROM 枢纽_套餐 WHERE 业务键=?", (业务键,)
        ).fetchone()["哈希键"]
    finally:
        conn.close()


def 套餐版本(业务键):
    父 = 套餐父哈希(业务键)
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 卫星_套餐属性 WHERE 套餐哈希=? ORDER BY 编号", (父,)
            )
        ]
    finally:
        conn.close()


def 世代们(类=None, 父=None):
    conn = 连接()
    try:
        return 卫星开版.世代核证(conn, 类=类, 父键=父)
    finally:
        conn.close()


def 卫星明细(报):
    return [d for d in 报["报告"]["明细"] if str(d["类"]).startswith("卫星-")]


class 字段集世代测试(unittest.TestCase):
    def setUp(self):
        库 = Path(os.environ["数据目录"]) / "号枢.db"
        if 库.exists():
            库.unlink()
        seed.初始化库()

    # ---- 基础：开版必钉世代五元组 --------------------------------------
    def test_首版即钉死世代五元组(self):
        r = 装(
            "2026-11-21", "批-首",
            {"套餐": [{"业务键": "套-A", "属性": {"月费": 59, "展示名": "畅"}}]},
            {"套餐": [{"业务键": "套-A"}]},
        )
        self.assertEqual(r["结果"], "成功", r)
        明细 = 卫星明细(r)[0]
        self.assertEqual(明细["站规版本"], 1)
        self.assertEqual(明细["字段集快照"], '["*"]')
        self.assertEqual(明细["批号"], "批-首")
        证 = 世代们(类="套餐")
        self.assertTrue(证["通过"], 证["失败项"])
        self.assertEqual(证["世代数"], 1)
        世 = 证["世代"][0]
        self.assertTrue(世["五元组完整"])
        self.assertTrue(世["站规版本可解"])
        self.assertTrue(世["快照与版本一致"])
        self.assertTrue(世["卫星行存在"])
        self.assertEqual(世["批号"], "批-首")
        self.assertEqual(世["字段集快照"], '["*"]')

    def test_跳过不开版不写世代(self):
        体 = {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]}
        装("2026-11-21", "批-1", 体, {"套餐": [{"业务键": "套-A"}]})
        r = 装("2026-11-22", "批-2", 体, {"套餐": [{"业务键": "套-A"}]})
        self.assertEqual(卫星明细(r)[0]["结果"], "同哈希跳过")
        self.assertEqual(世代们()["世代数"], 1)
        self.assertEqual(len(套餐版本("套-A")), 1)

    def test_载荷回到历史哈希可重开为当前_追加新世代且无双当前(self):
        # 基线语义：同哈希只禁止与「当前」撞；回到历史版本的载荷允许重开为新当前。
        装("2026-11-21", "批-1",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
           {"套餐": [{"业务键": "套-A"}]})
        装("2026-11-22", "批-2",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 79}}]},
           {"套餐": [{"业务键": "套-A"}]})
        # 回到批-1 的历史载荷（月费59）→ 与当前（79）不同 → 重开新版
        r = 装("2026-11-23", "批-3",
               {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
               {"套餐": [{"业务键": "套-A"}]})
        self.assertEqual(卫星明细(r)[0]["结果"], "开新版")
        行 = 套餐版本("套-A")
        self.assertEqual(len(行), 3)
        self.assertEqual(sum(v["是否当前"] for v in 行), 1)
        self.assertEqual(行[-1]["载荷哈希"], 行[0]["载荷哈希"])  # 与首版同哈希
        # 同哈希各有独立世代行（首版、重开版），均五元组可核
        证 = 世代们(类="套餐")
        self.assertEqual(证["世代数"], 3)
        self.assertTrue(证["通过"], 证["失败项"])
        self.assertTrue(贯验.跑贯验()["是否通过"])
        # 再灌当前载荷仍跳过（同哈希不撞当前空开）
        r2 = 装("2026-11-24", "批-4",
                {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
                {"套餐": [{"业务键": "套-A"}]})
        self.assertEqual(卫星明细(r2)[0]["结果"], "同哈希跳过")
        self.assertEqual(世代们(类="套餐")["世代数"], 3)

    # ---- 架构甲判别场景：移出/移进展示名 -------------------------------
    def test_展示名移出名单后同载荷再灌跳过不开版(self):
        属性 = {"月费": 59, "流量吉": 30, "展示名": "畅享焕新"}
        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": 属性}]},
           {"套餐": [{"业务键": "套-A"}]})
        # 站规改名单：展示名移出哈希字段，追加站规版本 2
        改 = 站规.改字段名单(["月费", "流量吉", "备注"], 批号="规-移出示名")
        self.assertEqual(改["结果"], "已钉新版本")
        self.assertEqual(改["站规版本"], 2)
        # 同载荷再灌：钉死快照架构下必须采信旧快照 → 同哈希 → 跳过
        r = 装("2026-11-22", "批-再灌",
               {"套餐": [{"业务键": "套-A", "属性": 属性}]},
               {"套餐": [{"业务键": "套-A"}]})
        self.assertEqual(卫星明细(r)[0]["结果"], "同哈希跳过", r)
        self.assertEqual(len(套餐版本("套-A")), 1)
        self.assertEqual(世代们()["世代数"], 1)

    def test_改名单后只改被移出字段仍跳过_改留名字段才开新版且钉新名单(self):
        # 先在全属性口径下开首版，再缩名单，并在新名单下开一个当前版（钉子集快照）
        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59, "展示名": "甲", "备注": "无"}}]},
           {"套餐": [{"业务键": "套-A"}]})
        站规.改字段名单(["月费"], 批号="规-只留月费")
        装("2026-11-22", "批-子集开版",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 60, "展示名": "甲", "备注": "无"}}]},
           {"套餐": [{"业务键": "套-A"}]})
        # 当前版钉的是子集快照 ["月费"]：只改已移出名单的展示名/备注，月费不变 → 同哈希跳过
        r1 = 装("2026-11-23", "批-改名",
                {"套餐": [{"业务键": "套-A", "属性": {"月费": 60, "展示名": "乙", "备注": "有"}}]},
                {"套餐": [{"业务键": "套-A"}]})
        self.assertEqual(卫星明细(r1)[0]["结果"], "同哈希跳过")
        # 改留名字段月费 → 开新版；新世代钉现行名单（版本2），旧世代保留
        r2 = 装("2026-11-24", "批-改费",
                {"套餐": [{"业务键": "套-A", "属性": {"月费": 69, "展示名": "乙", "备注": "有"}}]},
                {"套餐": [{"业务键": "套-A"}]})
        self.assertEqual(卫星明细(r2)[0]["结果"], "开新版")
        self.assertEqual(卫星明细(r2)[0]["站规版本"], 2)
        self.assertEqual(卫星明细(r2)[0]["字段集快照"], '["月费"]')
        证 = 世代们(类="套餐")
        self.assertEqual(证["世代数"], 3)
        self.assertEqual(证["分叉数"], 1)  # 仅首世代 ["*"] 与现行 ["月费"] 分叉
        首, 二, 三 = 证["世代"]
        self.assertEqual(首["字段集快照"], '["*"]')
        self.assertTrue(首["与现行名单分叉"])
        self.assertEqual(二["字段集快照"], '["月费"]')
        self.assertEqual(三["字段集快照"], '["月费"]')
        self.assertFalse(三["与现行名单分叉"])

    def test_展示名移回名单后旧世代仍可核_分叉不失败不混用(self):
        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59, "展示名": "甲"}}]},
           {"套餐": [{"业务键": "套-A"}]})
        站规.改字段名单(["月费"], 批号="规-缩")
        装("2026-11-22", "批-开二",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 69, "展示名": "甲"}}]},
           {"套餐": [{"业务键": "套-A"}]})
        站规.改字段名单(["*"], 批号="规-恢复")
        证 = 世代们(类="套餐")
        self.assertTrue(证["通过"])  # 分叉只提示，不判失败
        # 现行恢复为 ["*"]：世代1 也是 ["*"] 不分叉，仅世代2（["月费"]）分叉
        self.assertEqual(证["分叉数"], 1)
        # 全量复核：两版各自按自身钉死快照复算相符
        报 = 卫星开版.开版贯验(类="套餐")
        self.assertTrue(报["通过"], 报["问题"])
        self.assertEqual(len(报["分叉"]), 1)

    # ---- 硬约束：禁止开版成功而世代空（库层触发器） --------------------
    def test_库层拒绝无世代卫星插入(self):
        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
           {"套餐": [{"业务键": "套-A"}]})
        父 = 套餐父哈希("套-A")
        conn = 连接()
        try:
            with self.assertRaises(Exception) as ctx:
                conn.execute(
                    "INSERT INTO 卫星_套餐属性(套餐哈希, 装载日, 载荷哈希, 属性, 是否当前) "
                    "VALUES (?,?,?,?,1)",
                    (父, "2026-11-30", "deadbeefdeadbeef", '{"月费": 1}'),
                )
            self.assertIn("禁止无世代开版", str(ctx.exception))
        finally:
            conn.close()

    def test_钉世代失败整票回滚_不留空世代不双当前(self):
        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
           {"套餐": [{"业务键": "套-A"}]})
        父 = 套餐父哈希("套-A")
        conn = 连接()
        try:
            conn.execute("BEGIN IMMEDIATE")
            原钉 = 卫星开版._钉世代
            卫星开版._钉世代 = lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("模拟世代写入失败")
            )
            try:
                with self.assertRaises(RuntimeError):
                    卫星开版.开卫星版(
                        conn, "套餐", 父, {"月费": 88}, "2026-11-24", 批号="批-半截"
                    )
            finally:
                卫星开版._钉世代 = 原钉
            # 事务内：旧当前仍在，无新行
            行 = conn.execute(
                "SELECT 编号, 是否当前 FROM 卫星_套餐属性 WHERE 套餐哈希=? ORDER BY 编号",
                (父,),
            ).fetchall()
            self.assertEqual([(r["编号"], r["是否当前"]) for r in 行], [(1, 1)])
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM 字段集世代").fetchone()["c"], 1
            )
            conn.rollback()
        finally:
            conn.close()
        # 提交后状态不变，贯验通过，无双当前
        self.assertEqual(len(套餐版本("套-A")), 1)
        self.assertTrue(贯验.跑贯验()["是否通过"])

    def test_关旧后开新失败_保存点回滚不留双当前(self):
        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
           {"套餐": [{"业务键": "套-A"}]})
        父 = 套餐父哈希("套-A")
        conn = 连接()
        try:
            conn.execute("BEGIN IMMEDIATE")
            原插 = 卫星开版._插入
            卫星开版._插入 = lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("模拟卫星插入失败")
            )
            try:
                with self.assertRaises(RuntimeError):
                    卫星开版.开卫星版(
                        conn, "套餐", 父, {"月费": 88}, "2026-11-24", 批号="批-半截2"
                    )
            finally:
                卫星开版._插入 = 原插
            行 = conn.execute(
                "SELECT 是否当前 FROM 卫星_套餐属性 WHERE 套餐哈希=? ORDER BY 编号",
                (父,),
            ).fetchall()
            self.assertEqual([r["是否当前"] for r in 行], [1])  # 关旧被回滚
            conn.rollback()
        finally:
            conn.close()
        self.assertEqual(sum(v["是否当前"] for v in 套餐版本("套-A")), 1)

    # ---- 硬约束：钉扎与站规版本禁改禁删 -------------------------------
    def test_世代钉扎禁改禁删_站规版本禁改禁删(self):
        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
           {"套餐": [{"业务键": "套-A"}]})
        conn = 连接()
        try:
            with self.assertRaises(Exception) as ctx:
                conn.execute("UPDATE 字段集世代 SET 批号='篡改' WHERE 编号=1")
            self.assertIn("钉扎禁改", str(ctx.exception))
            with self.assertRaises(Exception) as ctx:
                conn.execute("DELETE FROM 字段集世代 WHERE 编号=1")
            self.assertIn("钉扎禁删", str(ctx.exception))
            with self.assertRaises(Exception) as ctx:
                conn.execute("UPDATE 站规版本 SET 字段集快照='[]' WHERE 版本号=1")
            self.assertIn("已钉版本禁改", str(ctx.exception))
            with self.assertRaises(Exception) as ctx:
                conn.execute("DELETE FROM 站规版本 WHERE 版本号=1")
            self.assertIn("已钉版本禁删", str(ctx.exception))
        finally:
            conn.close()

    # ---- 失败闭：绕过受管入口改站规 / 非法名单 ------------------------
    def test_绕过入口直改站规_开版失败闭且整票回滚(self):
        conn = 连接()
        try:
            conn.execute(
                "UPDATE 站规 SET 值='[\"月费\"]' WHERE 键='卫星载荷哈希字段'"
            )
            conn.commit()
        finally:
            conn.close()
        r = 装("2026-11-21", "批-坏",
               {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
               {"套餐": [{"业务键": "套-A"}]})
        # 直改站规未钉站规版本 → 世代无法采信 → 失败闭
        self.assertEqual(r["结果"], "失败")
        conn = 连接()
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM 枢纽_套餐").fetchone()["c"], 0
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM 卫星_套餐属性").fetchone()["c"], 0
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM 字段集世代").fetchone()["c"], 0
            )
        finally:
            conn.close()

    def test_非法名单失败闭_空名单重复字段星号混用(self):
        for 坏 in ([], ["", "  "], ["月费", "月费"], ["*", "月费"]):
            with self.subTest(坏=坏):
                with self.assertRaises(站规.站规错误):
                    站规.改字段名单(坏)
        # 非数组站规值在取口径解析时同样失败闭
        conn = 连接()
        try:
            conn.execute(
                "UPDATE 站规 SET 值='not-a-list' WHERE 键='卫星载荷哈希字段'"
            )
            conn.commit()
        finally:
            conn.close()
        with self.assertRaises(站规.站规错误):
            c = 连接()
            try:
                站规.现行口径(c)
            finally:
                c.close()

    def test_改名单幂等不开新版本(self):
        r1 = 站规.改字段名单(["月费", "流量吉"], 批号="规-1")
        r2 = 站规.改字段名单(["流量吉", "月费"], 批号="规-2")  # 排序后规范相等
        self.assertEqual(r1["站规版本"], 2)
        self.assertEqual(r2["结果"], "无变化")
        self.assertEqual(r2["站规版本"], 2)

    # ---- 并发：开版与改名单/开版交错不得双当前 -------------------------
    def test_并发开版写锁串行_正式无双当前(self):
        import threading

        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
           {"套餐": [{"业务键": "套-A"}]})
        父 = 套餐父哈希("套-A")
        闸 = threading.Barrier(2)
        错 = []

        def 开(月费):
            c = 连接()
            try:
                闸.wait()
                卫星开版.开卫星版(
                    c, "套餐", 父, {"月费": 月费}, f"2026-11-{月费}", 批号=f"批-并{月费}"
                )
                c.commit()
            except Exception as e:
                错.append(str(e))
                c.rollback()
            finally:
                c.close()

        t1 = threading.Thread(target=开, args=(70,))
        t2 = threading.Thread(target=开, args=(80,))
        t1.start(); t2.start(); t1.join(); t2.join()
        # busy_timeout 下写锁串行：两笔不同载荷都应落库，任一笔都不许产生双当前
        self.assertEqual(错, [], 错)
        行 = 套餐版本("套-A")
        self.assertEqual(len(行), 3)  # 首版 + 两次开版
        self.assertEqual(sum(v["是否当前"] for v in 行), 1)
        self.assertEqual(世代们(类="套餐", 父=父)["世代数"], 3)
        self.assertTrue(贯验.跑贯验()["是否通过"])

    def test_并发改名单与开版_世代只采信一个站规版本且可核(self):
        import threading

        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59, "展示名": "甲"}}]},
           {"套餐": [{"业务键": "套-A"}]})
        父 = 套餐父哈希("套-A")
        闸 = threading.Barrier(2)
        错 = []

        def 改名():
            try:
                闸.wait()
                站规.改字段名单(["月费"], 批号="规-并发")
            except Exception as e:
                错.append(str(e))

        def 开版():
            c = 连接()
            try:
                闸.wait()
                卫星开版.开卫星版(
                    c, "套餐", 父, {"月费": 99, "展示名": "甲"},
                    "2026-11-26", 批号="批-并发开"
                )
                c.commit()
            except Exception as e:
                错.append(str(e))
                c.rollback()
            finally:
                c.close()

        t1 = threading.Thread(target=改名)
        t2 = threading.Thread(target=开版)
        t1.start(); t2.start(); t1.join(); t2.join()
        # 写锁串行：可能一方先得锁，二者都不应产生损坏状态
        self.assertLessEqual(len(错), 1)
        证 = 世代们(类="套餐", 父=父)
        self.assertTrue(证["通过"], 证["失败项"])
        for 世 in 证["世代"]:
            self.assertTrue(世["快照与版本一致"])  # 不允许世代与站规版本静默混用
        self.assertEqual(sum(v["是否当前"] for v in 套餐版本("套-A")), 1)

    # ---- 只读核证接口 --------------------------------------------------
    def test_世代核证只读接口_按类父批号筛选(self):
        装("2026-11-21", "批-首",
           {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
           {"套餐": [{"业务键": "套-A"}]})
        全 = 卫星开版.世代核证()
        self.assertIn("站规版本史", 全)
        self.assertEqual(全["架构"], "钉死快照")
        self.assertEqual(len(全["站规版本史"]), 1)
        父 = 套餐父哈希("套-A")
        self.assertEqual(len(卫星开版.世代核证(类="套餐", 父键=父)["世代"]), 1)
        self.assertEqual(len(卫星开版.世代核证(批号="批-首")["世代"]), 1)
        self.assertEqual(卫星开版.世代核证(批号="不存在")["世代数"], 0)
        self.assertEqual(卫星开版.世代核证(类="号卡")["世代数"], 0)

    # ---- 夹具升档链路：升档开版后改名单再灌 ----------------------------
    def test_夹具链路_升档开版后改名单同载荷再灌跳过(self):
        for 名 in ("号卡套餐样例", "套餐升档样例"):
            self.assertTrue((夹具 / f"{名}.json").exists(), 名)
        装载.装一批(json.loads((夹具 / "号卡套餐样例.json").read_text(encoding="utf-8")))
        装载.装一批(json.loads((夹具 / "套餐升档样例.json").read_text(encoding="utf-8")))
        行前 = 套餐版本("套-畅享59")
        self.assertEqual(len(行前), 2)
        # 改名单：移出展示名（本批样例属性不含展示名，验证名单变更本身）
        站规.改字段名单(["月费", "流量吉"], 批号="规-夹具")
        # 同当前载荷再灌（沿用升档样例载荷，换新批号模拟再灌）
        升档体 = json.loads((夹具 / "套餐升档样例.json").read_text(encoding="utf-8"))
        升档体["批次编号"] = "批-改名单后再灌"
        r = 装载.装一批(升档体)
        self.assertEqual(r["结果"], "成功")
        self.assertEqual(卫星明细(r)[0]["结果"], "同哈希跳过")
        self.assertEqual(len(套餐版本("套-畅享59")), 2)  # 不开新版
        父 = 套餐父哈希("套-畅享59")
        证 = 世代们(类="套餐", 父=父)
        self.assertTrue(证["通过"])
        # 该父键旧两版世代均钉在版本1，现行版本2 → 两条分叉提示
        self.assertEqual(证["分叉数"], 2)
        self.assertTrue(贯验.跑贯验()["是否通过"])

    def test_夹具四连灌_世代随开版钉死_同哈希不增世代(self):
        for 名 in ("号卡套餐样例", "套餐升档样例", "卫星展示名改样例", "卫星同哈希重灌样例"):
            self.assertTrue((夹具 / f"{名}.json").exists(), 名)
        for 名 in ("号卡套餐样例", "套餐升档样例", "卫星展示名改样例", "卫星同哈希重灌样例"):
            装载.装一批(json.loads((夹具 / f"{名}.json").read_text(encoding="utf-8")))
        父 = 套餐父哈希("套-畅享59")
        证 = 世代们(类="套餐", 父=父)
        self.assertTrue(证["通过"])
        self.assertEqual(证["世代数"], 3)  # 三次开版各一世代，同哈希跳过不增
        self.assertEqual(len(套餐版本("套-畅享59")), 3)
        self.assertEqual(sum(v["是否当前"] for v in 套餐版本("套-畅享59")), 1)
        报 = 卫星开版.开版贯验(类="套餐", 父键=父)
        self.assertTrue(报["通过"], 报["问题"])
        self.assertTrue(贯验.跑贯验()["是否通过"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
