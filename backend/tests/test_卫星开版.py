import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

临时 = os.path.join(tempfile.gettempdir(), "haoshu-test-shared")
os.makedirs(临时, exist_ok=True)
os.environ["数据目录"] = 临时

from app import seed
from app.db import 连接
from app.services import 卫星开版, 装载, 贯验


def 读(类, 业务键):
    seed.初始化库()
    conn = 连接()
    try:
        表, 父列, 父表 = 卫星开版.表配置[类]
        父 = conn.execute(
            f"SELECT 哈希键 FROM {父表} WHERE 业务键=?", (业务键,)
        ).fetchone()["哈希键"]
        return [
            dict(r)
            for r in conn.execute(
                f"SELECT * FROM {表} WHERE {父列}=? ORDER BY 编号", (父,)
            )
        ]
    finally:
        conn.close()


def 批量(装载日, 批次, 卫星, 枢纽=None, 链接=None):
    return 装载.装一批(
        {
            "装载日": 装载日,
            "批次编号": 批次,
            "枢纽": 枢纽 or {},
            "链接": 链接 or {},
            "卫星": 卫星,
        }
    )


class 卫星哈希开版测试(unittest.TestCase):
    def setUp(self):
        库 = Path(os.environ["数据目录"]) / "号枢.db"
        if 库.exists():
            库.unlink()
        seed.初始化库()

    def test_首版后再灌同载荷不空开(self):
        for i in (1, 2):
            r = 批量(
                "2026-11-21",
                f"批-首-{i}",
                {
                    "套餐": [
                        {"业务键": "套-A", "属性": {"月费": 59, "流量吉": 30}}
                    ]
                },
                {"套餐": [{"业务键": "套-A"}]},
            )
            self.assertEqual(r["结果"], "成功", r)
        同哈希 = [
            d for d in r["报告"]["明细"] if d.get("结果") == "同哈希跳过"
        ]
        self.assertEqual(len(同哈希), 1)
        行 = 读("套餐", "套-A")
        self.assertEqual(len(行), 1)
        self.assertEqual(行[0]["是否当前"], 1)

    def test_只改展示名开新版_全属性字段口径(self):
        for i, 属性 in enumerate(
            (
                {"月费": 59, "流量吉": 30},
                {"月费": 59, "流量吉": 30, "展示名": "畅享焕新"},
            )
        ):
            r = 批量(
                f"2026-11-2{i}",
                f"批-展示-{i}",
                {"套餐": [{"业务键": "套-A", "属性": 属性}]},
                {"套餐": [{"业务键": "套-A"}]},
            )
            self.assertEqual(r["结果"], "成功", r)
        行 = 读("套餐", "套-A")
        self.assertEqual(len(行), 2)
        self.assertEqual(sum(x["是否当前"] for x in 行), 1)
        self.assertNotEqual(行[0]["载荷哈希"], 行[1]["载荷哈希"])
        self.assertEqual(行[1]["是否当前"], 1)

    def test_改月费开新版且旧版非当前(self):
        for i, 月费 in enumerate((59, 69)):
            r = 批量(
                f"2026-11-2{i}",
                f"批-月费-{i}",
                {"套餐": [{"业务键": "套-A", "属性": {"月费": 月费}}]},
                {"套餐": [{"业务键": "套-A"}]},
            )
            self.assertEqual(r["结果"], "成功", r)
        行 = 读("套餐", "套-A")
        self.assertEqual(len(行), 2)
        self.assertEqual([x["是否当前"] for x in 行], [0, 1])

    def test_同哈希重灌不产生双当前且旧版可查(self):
        体 = {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]}
        批量("2026-11-21", "批-1", 体, {"套餐": [{"业务键": "套-A"}]})
        批量("2026-11-22", "批-2", {"套餐": [{"业务键": "套-A", "属性": {"月费": 69}}]})
        r = 批量("2026-11-23", "批-3", {"套餐": [{"业务键": "套-A", "属性": {"月费": 69}}]})
        self.assertEqual(r["结果"], "成功", r)
        self.assertEqual(r["报告"]["跳过"], 1)
        行 = 读("套餐", "套-A")
        self.assertEqual(len(行), 2)
        self.assertEqual([x["是否当前"] for x in 行], [0, 1])

    def test_原样重灌同批次后历史版仍可查(self):
        体 = {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]}
        批量("2026-11-21", "批-1", 体, {"套餐": [{"业务键": "套-A"}]})
        批量("2026-11-22", "批-2", {"套餐": [{"业务键": "套-A", "属性": {"月费": 79}}]})
        报 = 卫星开版.开版贯验(类="套餐")
        self.assertTrue(报["通过"], 报["问题"])
        组 = [g for g in 报["组"] if g["父键"]][0]
        self.assertEqual(len(组["历史"]), 1)
        self.assertEqual(len(组["当前们"]), 1)
        self.assertFalse(组["是否双当前"])
        self.assertEqual(组["历史"][0]["是否当前"], 0)

    def test_库层写闸拒绝原地覆盖当前属性(self):
        feed = "/workspace/fixtures/号卡套餐样例.json"
        if not Path(feed).exists():
            self.skipTest("缺夹具")
        装载.装一批(json.loads(Path(feed).read_text(encoding="utf-8")))
        conn = 连接()
        try:
            with self.assertRaises(Exception) as ctx:
                conn.execute(
                    "UPDATE 卫星_套餐属性 SET 属性='{}' WHERE 是否当前=1"
                )
            self.assertIn("禁止原地改写", str(ctx.exception))
        finally:
            conn.close()

    def test_库层写闸拒绝改历史版本(self):
        feed = "/workspace/fixtures/号卡套餐样例.json"
        if not Path(feed).exists():
            self.skipTest("缺夹具")
        装载.装一批(json.loads(Path(feed).read_text(encoding="utf-8")))
        装载.装一批(json.loads(Path("/workspace/fixtures/套餐升档样例.json").read_text(encoding="utf-8")))
        conn = 连接()
        try:
            旧 = conn.execute(
                "SELECT * FROM 卫星_套餐属性 WHERE 是否当前=0 LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(旧)
            with self.assertRaises(Exception) as ctx:
                conn.execute(
                    "UPDATE 卫星_套餐属性 SET 属性='{}' WHERE 编号=?", (旧["编号"],)
                )
            self.assertIn("禁止原地改写", str(ctx.exception))
        finally:
            conn.close()

    def test_库层写闸拒绝复活历史版(self):
        feed = "/workspace/fixtures/号卡套餐样例.json"
        if not Path(feed).exists():
            self.skipTest("缺夹具")
        装载.装一批(json.loads(Path(feed).read_text(encoding="utf-8")))
        装载.装一批(json.loads(Path("/workspace/fixtures/套餐升档样例.json").read_text(encoding="utf-8")))
        conn = 连接()
        try:
            旧 = conn.execute(
                "SELECT * FROM 卫星_套餐属性 WHERE 是否当前=0 LIMIT 1"
            ).fetchone()
            with self.assertRaises(Exception):
                conn.execute(
                    "UPDATE 卫星_套餐属性 SET 是否当前=1 WHERE 编号=?", (旧["编号"],)
                )
        finally:
            conn.close()

    def test_库层写闸拒绝同哈希新当前(self):
        feed = "/workspace/fixtures/号卡套餐样例.json"
        if not Path(feed).exists():
            self.skipTest("缺夹具")
        装载.装一批(json.loads(Path(feed).read_text(encoding="utf-8")))
        conn = 连接()
        try:
            r = conn.execute(
                "SELECT * FROM 卫星_套餐属性 WHERE 是否当前=1 LIMIT 1"
            ).fetchone()
            with self.assertRaises(Exception) as ctx:
                conn.execute(
                    "INSERT INTO 卫星_套餐属性(套餐哈希, 装载日, 载荷哈希, 属性, 是否当前) "
                    "VALUES (?,?,?,?,1)",
                    (r["套餐哈希"], "2026-11-30", r["载荷哈希"], r["属性"]),
                )
            self.assertIn("同载荷哈希禁止再开当前", str(ctx.exception))
        finally:
            conn.close()

    def test_半截开版失败闭_不留双当前(self):
        feed = "/workspace/fixtures/号卡套餐样例.json"
        if not Path(feed).exists():
            self.skipTest("缺夹具")
        装载.装一批(json.loads(Path(feed).read_text(encoding="utf-8")))
        conn = 连接()
        try:
            父 = conn.execute(
                "SELECT 哈希键 FROM 枢纽_套餐 WHERE 业务键='套-畅享59'"
            ).fetchone()["哈希键"]
            conn.execute("BEGIN IMMEDIATE")
            原插入 = 卫星开版._插入
            卫星开版._插入 = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("模拟插入失败"))
            try:
                with self.assertRaises(RuntimeError):
                    卫星开版.开卫星版(
                        conn, "套餐", 父, {"月费": 59, "流量吉": 41}, "2026-11-24"
                    )
            finally:
                卫星开版._插入 = 原插入
            行内 = conn.execute(
                "SELECT 是否当前 FROM 卫星_套餐属性 WHERE 套餐哈希=? ORDER BY 编号",
                (父,),
            ).fetchall()
            self.assertEqual([r["是否当前"] for r in 行内], [1])
            conn.rollback()
        finally:
            conn.close()
        行 = 读("套餐", "套-畅享59")
        self.assertEqual(sum(x["是否当前"] for x in 行), 1)
        self.assertTrue(贯验.跑贯验()["是否通过"])

    def test_贯验按同一字段集判定(self):
        feed = "/workspace/fixtures/号卡套餐样例.json"
        if not Path(feed).exists():
            self.skipTest("缺夹具")
        装载.装一批(json.loads(Path(feed).read_text(encoding="utf-8")))
        报 = 贯验.跑贯验()
        self.assertTrue(报["是否通过"], 报)
        self.assertEqual(报["口径"]["口径"], "全属性字段")

    def test_夹具链路_展示名开版_同哈希不空开_再改月费开版(self):
        """只改展示名 → 开新版；同哈希重灌 → 不空开且仍唯一当前；再改月费 → 开版且旧非当前。"""
        夹 = Path("/workspace/fixtures")
        for 名 in ("号卡套餐样例", "套餐升档样例", "卫星展示名改样例", "卫星同哈希重灌样例"):
            if not (夹 / f"{名}.json").exists():
                self.skipTest(f"缺夹具:{名}")

        装载.装一批(json.loads((夹 / "号卡套餐样例.json").read_text(encoding="utf-8")))
        装载.装一批(json.loads((夹 / "套餐升档样例.json").read_text(encoding="utf-8")))
        改展示 = 装载.装一批(
            json.loads((夹 / "卫星展示名改样例.json").read_text(encoding="utf-8"))
        )
        self.assertEqual(改展示["结果"], "成功", 改展示)
        明细 = 改展示["报告"]["明细"]
        self.assertEqual([d["结果"] for d in 明细], ["开新版"], 明细)
        组 = 卫星开版.开版贯验(类="套餐")["组"]
        组 = [g for g in 组 if g["业务键"] == "套-畅享59"][0]
        self.assertEqual(len(组["当前们"]), 1)
        self.assertEqual(len(组["历史"]), 2)
        乙 = [g for g in 卫星开版.开版贯验(类="套餐")["组"] if g["业务键"] == "套-极速99"][0]
        self.assertEqual(len(乙["当前们"]), 1)
        self.assertEqual(len(乙["历史"]), 0)

        同哈希 = 装载.装一批(
            json.loads((夹 / "卫星同哈希重灌样例.json").read_text(encoding="utf-8"))
        )
        self.assertEqual(同哈希["结果"], "成功", 同哈希)
        self.assertEqual([d["结果"] for d in 同哈希["报告"]["明细"]], ["同哈希跳过"])
        组 = [g for g in 卫星开版.开版贯验(类="套餐")["组"] if g["业务键"] == "套-畅享59"][0]
        self.assertEqual(len(组["版本"]), 3)
        self.assertEqual(len(组["当前们"]), 1)
        self.assertFalse(组["是否双当前"])

        旧当前 = 组["当前"]
        改月费 = 装载.装一批(
            {
                "装载日": "2026-11-25",
                "批次编号": "批-再改月费",
                "卫星": {
                    "套餐": [
                        {
                            "业务键": "套-畅享59",
                            "属性": {"月费": 69, "流量吉": 40, "展示名": "畅享59·焕新"},
                        }
                    ]
                },
            }
        )
        self.assertEqual(改月费["结果"], "成功", 改月费)
        self.assertEqual([d["结果"] for d in 改月费["报告"]["明细"]], ["开新版"])
        组 = [g for g in 卫星开版.开版贯验(类="套餐")["组"] if g["业务键"] == "套-畅享59"][0]
        旧版 = [v for v in 组["版本"] if v["编号"] == 旧当前["编号"]][0]
        self.assertEqual(旧版["是否当前"], 0)
        self.assertNotEqual(组["当前"]["编号"], 旧当前["编号"])
        self.assertEqual(组["当前"]["装载日"], "2026-11-25")
        self.assertTrue(贯验.跑贯验()["是否通过"])

    def test_站规口径改成子集须失败闭而非静默换口径(self):
        conn = 连接()
        try:
            conn.execute(
                "UPDATE 站规 SET 值='计价字段子集' WHERE 键='卫星载荷哈希口径'"
            )
            conn.commit()
        finally:
            conn.close()
        r = 批量(
            "2026-11-21",
            "批-坏口径",
            {"套餐": [{"业务键": "套-A", "属性": {"月费": 59}}]},
            {"套餐": [{"业务键": "套-A"}]},
        )
        self.assertEqual(r["结果"], "失败", r)
        self.assertIn("未实现", r["说明"])
        conn = 连接()
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM 枢纽_套餐").fetchone()["c"], 0
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM 卫星_套餐属性").fetchone()["c"], 0
            )
        finally:
            conn.close()

    def test_只读接口透出父键_当前历史_哈希_双当前(self):
        feed = "/workspace/fixtures/号卡套餐样例.json"
        if not Path(feed).exists():
            self.skipTest("缺夹具")
        装载.装一批(json.loads(Path(feed).read_text(encoding="utf-8")))
        套 = 读("套餐", "套-畅享59")[0]["套餐哈希"]
        报 = 卫星开版.开版贯验(类="套餐", 父键=套)
        self.assertTrue(报["通过"], 报)
        self.assertEqual(报["口径"]["口径"], "全属性字段")
        self.assertEqual(报["双当前"], [])
        self.assertEqual(len(报["组"]), 1)
        组 = 报["组"][0]
        self.assertEqual(组["业务键"], "套-畅享59")
        self.assertEqual(组["父键"], 套)
        self.assertEqual(len(组["当前们"]), 1)
        self.assertEqual(len(组["历史"]), 0)
        self.assertTrue(组["哈希可复算"])
        self.assertEqual(组["载荷哈希"], 组["当前"]["载荷哈希"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
