import React,{useEffect,useState} from "react";
import {取,递} from "../api.js";

export default function 站规(){
  const [规,设规]=useState(null);
  const [桩,设桩]=useState([]);
  const [名单输入,设名单输入]=useState("");
  const [批号,设批号]=useState("");
  const [忙,设忙]=useState(false);
  const [讯,设讯]=useState("");

  const 刷=()=>{
    取("/站规").then(设规);
    取("/空桩").then(设桩);
  };
  useEffect(()=>{刷();},[]);

  const 提交=async()=>{
    设忙(true);
    设讯("");
    try{
      const 名单 = 名单输入.split(",").map(s=>s.trim()).filter(Boolean);
      const r = await 递("/站规/字段名单", {字段名单:名单, 批号:批号||undefined});
      设讯(`${r.结果}：站规版本 #${r.站规版本}，快照 ${r.字段集快照}${r.影响?`；${r.影响}`:""}`);
      设名单输入("");设批号("");
      刷();
    }catch(e){
      设讯(`失败闭：${String(e.message||e)}`);
    }finally{ 设忙(false); }
  };

  const 条目 = 规 ? Object.entries(规.站规||{}) : [];
  const 现行 = 规?.现行口径;
  const 版本史 = 规?.版本史||[];

  return (<div>
    <h1 className="题">站规</h1>
    <p className="述">全局唯一架构「<b>钉死快照</b>」：每次卫星开版把当时字段名单钉成不可变世代；改名单只影响之后新开版，不回溯、不重算已开版哈希结论。</p>

    <div className="段题">现行口径</div>
    {!现行 ? <div className="空态">加载中…</div> : (
      <table>
        <tbody>
          <tr><th>架构</th><td>{现行.架构}</td></tr>
          <tr><th>口径</th><td>{现行.口径}</td></tr>
          <tr><th>进哈希字段名单</th><td className="哈希">{现行.字段集快照}</td></tr>
          <tr><th>已钉站规版本</th><td>#{现行.站规版本}</td></tr>
        </tbody>
      </table>
    )}
    <p className="讯">{现行?.规则}</p>

    <div className="段">
      <div className="段题">受管改字段名单（追加不可变站规版本）</div>
      <p className="述">逗号分隔，如 <code>月费,流量吉</code>；全属性用 <code>*</code>。非法名单（空/重复/星号混用）失败闭。</p>
      <div className="行">
        <input placeholder="月费,流量吉,展示名" value={名单输入}
               onChange={e=>设名单输入(e.target.value)} style={{minWidth:"18rem"}}/>
        <input placeholder="批号（可空）" value={批号} onChange={e=>设批号(e.target.value)}/>
        <button onClick={提交} disabled={忙||!名单输入.trim()}>{忙?"提交中…":"钉新版本并改名单"}</button>
      </div>
      {讯 && <p className="讯">{讯}</p>}
    </div>

    <div className="段">
      <div className="段题">站规版本史（禁改禁删）· {版本史.length}</div>
      {!版本史.length ? <div className="空态">暂无</div> : (
        <table>
          <thead><tr><th>版本号</th><th>字段集快照</th><th>口径</th><th>批号</th><th>时刻</th></tr></thead>
          <tbody>{版本史.map(r=>(
            <tr key={r.版本号}>
              <td>#{r.版本号}</td>
              <td className="哈希">{r.字段集快照}</td>
              <td>{r.口径}</td>
              <td>{r.批号}</td>
              <td>{r.时刻}</td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>

    <div className="段">
      <div className="段题">原始站规键值</div>
      <table>
        <thead><tr><th>键</th><th>值</th></tr></thead>
        <tbody>{条目.map(([k,v])=><tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody>
      </table>
    </div>

    <div className="段">
      <div className="段题">空桩 · {桩.length}</div>
      {!桩.length ? <div className="空态">暂无空桩</div> : (
        <table>
          <thead><tr><th>空桩</th><th>说明</th><th>状态</th><th>落盘</th></tr></thead>
          <tbody>{桩.map(r=>(
            <tr key={r.空桩}>
              <td>{r.空桩}</td>
              <td>{r.说明}</td>
              <td><span className={`徽章 ${r.状态==="已实现"?"通":"淡"}`}>{r.状态||"未实现"}</span></td>
              <td><span className={`徽章 ${r.已落盘?"通":"淡"}`}>{r.已落盘?"已落":"待落"}</span></td>
            </tr>
          ))}</tbody>
        </table>
      )}
    </div>
  </div>);
}
