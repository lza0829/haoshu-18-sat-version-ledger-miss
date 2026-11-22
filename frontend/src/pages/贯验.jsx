import React,{useEffect,useState} from "react";
import {递,取} from "../api.js";

export default function 贯验(){
  const [末,设末]=useState(null);
  const [史,设史]=useState([]);
  const [忙,设忙]=useState(false);
  const [类,设类]=useState("");
  const [父键,设父键]=useState("");
  const [开版,设开版]=useState(null);

  const 刷=async()=>{
    const 列=await 取("/贯验");
    设史(列);
    return 列;
  };
  useEffect(()=>{
    刷().then(列=>{
      if(列[0]) 设末({
        是否通过:!!列[0].是否通过,
        枢纽数:列[0].枢纽数,
        链接数:列[0].链接数,
        卫星当前数:列[0].卫星当前数,
        说明:列[0].说明,
        检项:null,
      });
    });
  },[]);

  const 跑=async()=>{
    设忙(true);
    try{
      const r=await 递("/贯验",{});
      设末(r);
      await 刷();
    } finally { 设忙(false); }
  };

  const 查开版=async()=>{
    const 参=new URLSearchParams();
    if(类) 参.set("类",类);
    if(父键.trim()) 参.set("父键",父键.trim());
    const q=参.toString();
    设开版(await 取(`/卫星/开版贯验${q?`?${q}`:""}`));
  };
  useEffect(()=>{查开版();},[]);

  const 组=开版?.组||[];
  const 问题数=Object.values(开版?.问题||{}).reduce((a,b)=>a+b.length,0);

  return (<div>
    <h1 className="题">贯验</h1>
    <p className="述">沿枢纽 → 链接 → 卫星贯穿互证：两端可解、卫星有父、同父无双当前。</p>
    <div className="行">
      <button onClick={跑} disabled={忙}>{忙?"贯验中…":"跑贯验"}</button>
      <button className="次" onClick={刷}>刷新履历</button>
    </div>

    {!末 && <div className="空态">尚未跑过贯验，点上方按钮做一次全仓贯穿检查。</div>}

    {末 && <>
      <div className="裁决">
        <div className={`裁决旗 ${末.是否通过?"通":"败"}`}>
          <div className="标">{末.是否通过?"通过":"未过"}</div>
          <div className="辅">{末.说明}</div>
        </div>
        <div className="裁决数">
          <div className="卡"><b>{末.枢纽数}</b><span>枢纽</span></div>
          <div className="卡"><b>{末.链接数}</b><span>链接</span></div>
          <div className="卡"><b>{末.卫星当前数}</b><span>卫星当前</span></div>
        </div>
      </div>

      {末.检项?.length>0 && (
        <div className="段">
          <div className="段题">本轮检项</div>
          <div className="检列">
            {末.检项.map(x=>(
              <div className="检条" key={x.名}>
                <div className={`检点 ${x.通过?"通":"败"}`}>{x.通过?"✓":"!"}</div>
                <div className="检名">{x.名}</div>
                <div className="检说">{x.说明}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>}

    <div className="段">
      <div className="段题">卫星开版贯验（只读）</div>
      <p className="述">按站规字段集复算载荷哈希：列父键、当前/历史版、载荷哈希与是否双当前。</p>
      <div className="行">
        <select value={类} onChange={e=>设类(e.target.value)}>
          <option value="">全部类</option>
          {["号卡","套餐","客户","订购"].map(x=><option key={x} value={x}>{x}</option>)}
        </select>
        <input
          placeholder="父键哈希（可空）"
          value={父键}
          onChange={e=>设父键(e.target.value)}
          style={{minWidth:"20rem"}}
        />
        <button className="次" onClick={查开版}>查开版</button>
        {开版 && (
          <span className={`徽章 ${开版.通过?"通":"败"}`}>
            {开版.通过?"开版口径通过":"开版口径未过"}
          </span>
        )}
      </div>

      {开版 && <>
        <div className="格">
          <div className="卡"><b>{开版.口径?.口径}</b><span>字段集口径</span></div>
          <div className="卡"><b>{开版.口径?.字段}</b><span>进哈希字段</span></div>
          <div className="卡"><b>{组.length}</b><span>父键组</span></div>
          <div className="卡"><b>{问题数}</b><span>问题数</span></div>
          <div className="卡"><b>{开版.写闸?.完整?"齐备":"缺口"}</b><span>写闸</span></div>
        </div>
        <p className="讯">{开版.口径?.规则}</p>
        {开版.写闸 && !开版.写闸.完整 && (
          <p className="讯 败">写闸缺口：{开版.写闸.缺口.join("、")}</p>
        )}

        {!组.length ? <div className="空态">该口径下暂无卫星版本。</div> : (
          <table>
            <thead><tr>
              <th>类</th><th>父键</th><th>业务键</th><th>当前版</th><th>历史版数</th>
              <th>载荷哈希</th><th>哈希可复算</th><th>双当前</th>
            </tr></thead>
            <tbody>{组.map(g=>(
              <tr key={`${g.表}-${g.父键}`}>
                <td>{g.类}</td>
                <td className="哈希">{g.父键}</td>
                <td>{g.业务键||"—"}</td>
                <td>{g.当前
                  ? <span className="徽章 通">#{g.当前.编号} · {g.当前.装载日}</span>
                  : g.是否双当前
                    ? <span className="徽章 败">双当前</span>
                    : <span className="徽章 败">无当前</span>}
                </td>
                <td>{g.历史.length}</td>
                <td className="哈希">{g.载荷哈希||"—"}</td>
                <td><span className={`徽章 ${g.哈希可复算?"通":"败"}`}>{g.哈希可复算?"符":"不符"}</span></td>
                <td><span className={`徽章 ${g.是否双当前?"败":"通"}`}>{g.是否双当前?"是":"否"}</span></td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </>}
    </div>

    <div className="段">
      <div className="段题">贯验履历</div>
      {!史.length ? <div className="空态">暂无记录</div> : (
        <table>
          <thead>
            <tr>
              <th>编号</th><th>时刻</th><th>枢纽</th><th>链接</th>
              <th>卫星当前</th><th>结果</th><th>说明</th>
            </tr>
          </thead>
          <tbody>
            {史.map(r=>(
              <tr key={r.编号}>
                <td>{r.编号}</td>
                <td>{r.时刻}</td>
                <td>{r.枢纽数}</td>
                <td>{r.链接数}</td>
                <td>{r.卫星当前数}</td>
                <td><span className={`徽章 ${r.是否通过?"通":"败"}`}>{r.是否通过?"通过":"未过"}</span></td>
                <td>{r.说明}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  </div>);
}
