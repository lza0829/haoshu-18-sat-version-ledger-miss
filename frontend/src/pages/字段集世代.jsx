import React, { useEffect, useState } from "react";
import { 取 } from "../api.js";

export default function 字段集世代() {
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState("");
  const [类, 设类] = useState("");
  const [父哈希, 设父哈希] = useState("");
  const [批号, 设批号] = useState("");

  const reload = () => {
    const 参 = new URLSearchParams();
    if (类) 参.set("类", 类);
    if (父哈希.trim()) 参.set("父哈希", 父哈希.trim());
    if (批号.trim()) 参.set("批号", 批号.trim());
    const q = 参.toString();
    取(`/贯验/字段集世代核证${q ? `?${q}` : ""}`)
      .then(setRows)
      .catch((e) => setErr(String(e.message || e)));
  };
  useEffect(() => { reload(); }, []);

  return (
    <div>
      <h1 className="题">字段集世代核证</h1>
      <p className="述">
        架构「<b>钉死快照</b>」只读核证：逐世代核五元组（父哈希 · 新卫星哈希 · 字段名单快照 ·
        站规版本 · 批号）完整、站规版本可解、快照与版本一致、卫星行存在。
        旧世代名单与现行站规分叉时按钉死快照采信，不回溯、不静默混用。
      </p>

      <div className="行">
        <select value={类} onChange={(e) => 设类(e.target.value)}>
          <option value="">全部类</option>
          {["号卡", "套餐", "客户", "订购"].map((x) => <option key={x} value={x}>{x}</option>)}
        </select>
        <input placeholder="父哈希（可空）" value={父哈希}
               onChange={(e) => 设父哈希(e.target.value)} style={{ minWidth: "16rem" }} />
        <input placeholder="批号（可空）" value={批号}
               onChange={(e) => 设批号(e.target.value)} style={{ minWidth: "10rem" }} />
        <button className="次" onClick={reload}>核证</button>
        {rows && (
          <span className={`徽章 ${rows.通过 ? "通" : "败"}`}>
            {rows.通过 ? "核证通过" : "核证未过"}
          </span>
        )}
      </div>

      {err && <pre className="码">{err}</pre>}

      {rows && (
        <>
          <div className="格">
            <div className="卡"><b>{rows.世代数}</b><span>世代数</span></div>
            <div className="卡"><b>{rows.分叉数}</b><span>与现行名单分叉</span></div>
            <div className="卡"><b className="哈希">{rows.现行口径?.字段集快照}</b><span>现行名单快照</span></div>
            <div className="卡"><b>#{rows.现行口径?.站规版本}</b><span>现行站规版本</span></div>
            <div className="卡"><b>{rows.站规版本史?.length}</b><span>站规版本史</span></div>
          </div>
          {rows.失败项?.length > 0 && (
            <p className="讯 败">{rows.失败项.join("；")}</p>
          )}

          <div className="段">
            <div className="段题">世代明细（禁改禁删）</div>
            {!rows.世代?.length ? <div className="空态">无匹配世代。</div> : (
              <table>
                <thead><tr>
                  <th>世代</th><th>类</th><th>业务键</th><th>父哈希</th><th>新卫星哈希</th>
                  <th>字段名单快照</th><th>站规版本</th><th>批号</th><th>核证</th><th>分叉</th>
                </tr></thead>
                <tbody>{rows.世代.map((s) => (
                  <tr key={s.世代编号}>
                    <td>#{s.世代编号}</td>
                    <td>{s.卫星类}</td>
                    <td>{s.业务键 || "—"}</td>
                    <td className="哈希">{s.父哈希}</td>
                    <td className="哈希">{s.新卫星哈希}</td>
                    <td className="哈希">{s.字段集快照}</td>
                    <td>#{s.站规版本}</td>
                    <td>{s.批号}</td>
                    <td><span className={`徽章 ${s.通过 ? "通" : "败"}`}>{s.通过 ? "齐" : "缺"}</span></td>
                    <td>
                      <span className={`徽章 ${s.与现行名单分叉 ? "淡" : "通"}`}>
                        {s.与现行名单分叉 ? "分叉(钉死采信)" : "一致"}
                      </span>
                    </td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>

          <div className="段">
            <div className="段题">站规版本史</div>
            <table>
              <thead><tr><th>版本号</th><th>字段集快照</th><th>口径</th><th>批号</th><th>时刻</th></tr></thead>
              <tbody>{(rows.站规版本史 || []).map((v) => (
                <tr key={v.版本号}>
                  <td>#{v.版本号}</td>
                  <td className="哈希">{v.字段集快照}</td>
                  <td>{v.口径}</td>
                  <td>{v.批号}</td>
                  <td>{v.时刻}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
