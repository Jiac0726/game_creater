(() => {
  if (document.getElementById("smartAssetSearchPanel")) return;
  const footer = document.querySelector(".footerbar");
  if (!footer) return;
  const style=document.createElement("style");
  style.textContent=`.smart-search{padding:18px}.smart-head{display:flex;justify-content:space-between;gap:10px}.smart-controls{display:grid;grid-template-columns:minmax(260px,1fr) auto auto;gap:8px;margin:10px 0}.smart-results{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:9px}.smart-hit{border:1px solid rgba(127,127,127,.22);border-radius:9px;padding:8px}.smart-hit img{width:100%;height:128px;object-fit:contain;background:rgba(0,0,0,.14);border-radius:6px}.smart-hit h4{margin:6px 0 3px}.smart-reason{font-size:11px;opacity:.72}.smart-score{font-size:12px;font-weight:700}.smart-status{margin-top:8px;font-size:12px}@media(max-width:720px){.smart-controls{grid-template-columns:1fr}}`;
  document.head.appendChild(style);
  const panel=document.createElement("section"); panel.id="smartAssetSearchPanel";panel.className="card smart-search";
  panel.innerHTML=`<div class="smart-head"><div><h2>Smart Asset Search</h2><p>自然语言 · Game Asset Ontology · 以图搜图</p></div><span>AI NATIVE</span></div><div class="smart-controls"><input id="smartQuery" placeholder="例如：废弃地铁站的破旧金属道具"/><button id="smartSearchBtn">智能搜索</button><button id="smartSimilarBtn">找相似素材</button></div><div id="smartProviders" class="smart-reason"></div><div id="smartResults" class="smart-results"></div><div id="smartStatus" class="smart-status">输入描述，或在 Asset Library 选中素材后查找相似图。</div>`;
  footer.insertAdjacentElement("beforebegin",panel);
  const $=id=>document.getElementById(id); const status=t=>$("smartStatus").textContent=t;
  async function json(url,opts){const r=await fetch(url,opts);const d=await r.json();if(!r.ok)throw new Error(d.detail||r.statusText);return d;}
  function currentAssetId(){return document.querySelector(".library-card.selected")?.dataset.assetId||null;}
  function render(data){$("smartResults").innerHTML=data.hits.map(h=>`<div class="smart-hit" data-asset-id="${h.asset.id}"><img src="${h.image_url}"/><h4>${h.asset.name}</h4><div class="smart-score">${Math.round(h.score*100)}% · ${h.asset.category}</div><div class="smart-reason">${h.reasons.join(" · ")}</div><div class="smart-reason">${h.asset.tags.join(", ")}</div></div>`).join("");status(`${data.hits.length} 个结果 · ${data.providers.join(" + ")}`);}
  $("smartSearchBtn").onclick=async()=>{const query=$("smartQuery").value.trim();if(!query)return status("请输入要找的素材描述。");try{status("正在进行语义检索…");render(await json("/api/v1/library/smart-search/text",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query,limit:40})}));}catch(e){status(e.message);}};
  $("smartSimilarBtn").onclick=async()=>{const asset_id=currentAssetId();if(!asset_id)return status("请先在 Asset Library 选中一个素材。");try{status("正在计算视觉相似度…");render(await json("/api/v1/library/smart-search/similar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({asset_id,limit:40})}));}catch(e){status(e.message);}};
  $("smartResults").onclick=e=>{const card=e.target.closest("[data-asset-id]");if(!card)return;const target=document.querySelector(`.library-card[data-asset-id="${card.dataset.assetId}"]`);if(target){target.click();target.scrollIntoView({behavior:"smooth",block:"center"});status(`已定位 Asset Library：${card.dataset.assetId}`);}else{navigator.clipboard?.writeText(card.dataset.assetId);status(`素材未在当前 Library 页面，已复制 Asset ID：${card.dataset.assetId}`);}};
  json("/api/v1/library/smart-search/providers").then(p=>{$("smartProviders").textContent=p.map(x=>`${x.ready?"✓":"○"} ${x.id}`).join("  ·  ");}).catch(()=>{});
})();
