(() => {
  if (document.getElementById("sceneComposerPanel")) return;
  const footer = document.querySelector(".footerbar");
  if (!footer) return;

  const style = document.createElement("style");
  style.textContent = `
    .composer-panel{padding:18px}.composer-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;margin-bottom:12px}
    .composer-layout{display:grid;grid-template-columns:240px minmax(420px,1fr) 260px;gap:12px}.composer-side{border:1px solid rgba(127,127,127,.22);border-radius:10px;padding:10px}
    .composer-side h3{margin:0 0 8px;font-size:13px}.composer-side input,.composer-side select{width:100%;box-sizing:border-box;margin-bottom:6px}.composer-row{display:flex;gap:6px;margin-bottom:6px}.composer-row>*{min-width:0;flex:1}
    .composer-stage-wrap{overflow:auto;border:1px solid rgba(127,127,127,.22);border-radius:10px;background:#14171c;min-height:440px;position:relative}.composer-stage{position:relative;transform-origin:top left;background-size:32px 32px;background-image:linear-gradient(to right,rgba(255,255,255,.04) 1px,transparent 1px),linear-gradient(to bottom,rgba(255,255,255,.04) 1px,transparent 1px)}
    .composer-item{position:absolute;transform-origin:center center;cursor:move;user-select:none}.composer-item img{display:block;max-width:none;pointer-events:none}.composer-item.selected{outline:2px solid #6aa9ff;outline-offset:2px}.composer-layer{display:flex;gap:5px;align-items:center;padding:5px;border-radius:6px}.composer-layer.active{background:rgba(100,160,255,.14)}
    .composer-status{margin-top:8px;font-size:12px;white-space:pre-wrap}@media(max-width:1050px){.composer-layout{grid-template-columns:1fr}.composer-stage-wrap{min-height:360px}}
  `;
  document.head.appendChild(style);

  const panel = document.createElement("section");
  panel.id = "sceneComposerPanel";
  panel.className = "card composer-panel";
  panel.innerHTML = `
    <div class="composer-head"><div><h2>Scene Composer</h2><p>Asset Library → Layer → Transform → Godot / Unity Scene</p></div><span>AI NATIVE</span></div>
    <div class="composer-layout">
      <div class="composer-side">
        <h3>场景 / 图层</h3>
        <div class="composer-row"><input id="cmpSceneName" value="new_scene"/><button id="cmpCreateScene">新建</button></div>
        <select id="cmpSceneSelect"><option value="">选择场景</option></select>
        <div class="composer-row"><input id="cmpLayerName" placeholder="Layer 名"/><button id="cmpAddLayer">加层</button></div>
        <div id="cmpLayers"></div>
        <hr/>
        <button id="cmpAddAsset">加入当前 Asset Library 素材</button>
        <div class="composer-row" style="margin-top:6px"><select id="cmpExportTarget"><option value="godot4">Godot 4</option><option value="unity2d">Unity 2D</option><option value="generic">Generic</option></select><button id="cmpExport">导出</button></div>
        <a id="cmpDownload" class="hidden">下载场景包</a>
      </div>
      <div class="composer-stage-wrap"><div id="cmpStage" class="composer-stage"></div></div>
      <div class="composer-side">
        <h3>选中对象</h3>
        <div id="cmpItemEmpty">点击画布素材进行编辑。</div>
        <div id="cmpItemEditor" class="hidden">
          <label>X<input id="cmpX" type="number" step="1"/></label><label>Y<input id="cmpY" type="number" step="1"/></label>
          <label>Rotation<input id="cmpRot" type="number" step="1"/></label>
          <div class="composer-row"><label>Scale X<input id="cmpScaleX" type="number" step="0.05"/></label><label>Scale Y<input id="cmpScaleY" type="number" step="0.05"/></label></div>
          <label>Z Index<input id="cmpZ" type="number" step="1"/></label>
          <select id="cmpItemLayer"></select>
          <div class="composer-row"><button id="cmpSaveItem">保存</button><button id="cmpDeleteItem">删除</button></div>
        </div>
      </div>
    </div>
    <div id="cmpStatus" class="composer-status">先新建/选择场景，然后从 Asset Library 选择素材加入画布。</div>`;
  footer.insertAdjacentElement("beforebegin", panel);

  const $ = id => document.getElementById(id);
  let scene = null;
  let activeLayerId = null;
  let selectedItemId = null;
  let drag = null;

  function status(text){ $("cmpStatus").textContent = text; }
  function currentLibraryAssetId(){ return document.querySelector(".library-card.selected")?.dataset.assetId || null; }
  async function json(url, options){ const r=await fetch(url,options); const d=await r.json(); if(!r.ok) throw new Error(d.detail || r.statusText); return d; }

  async function refreshScenes(selectId){
    const scenes = await json("/api/v1/library/composer/scenes");
    $("cmpSceneSelect").innerHTML='<option value="">选择场景</option>'+scenes.map(s=>`<option value="${s.id}">${s.name}</option>`).join("");
    if(selectId){ $("cmpSceneSelect").value=selectId; await loadScene(selectId); }
  }

  async function loadScene(id){ scene = await json(`/api/v1/library/composer/scenes/${id}`); activeLayerId = activeLayerId && scene.layers.some(l=>l.id===activeLayerId) ? activeLayerId : scene.layers[0]?.id; selectedItemId=null; render(); }

  function render(){
    if(!scene){ $("cmpStage").innerHTML=""; return; }
    const stage=$("cmpStage"); stage.style.width=`${scene.width}px`; stage.style.height=`${scene.height}px`; stage.style.backgroundColor=scene.background; stage.style.backgroundSize=`${scene.grid_size}px ${scene.grid_size}px`;
    const layerById=Object.fromEntries(scene.layers.map(l=>[l.id,l]));
    stage.innerHTML=scene.items.filter(i=>i.visible && layerById[i.layer_id]?.visible!==false).map(i=>{
      const t=i.transform; const selected=i.id===selectedItemId?" selected":""; const z=(layerById[i.layer_id]?.order||0)*10000+i.z_index;
      return `<div class="composer-item${selected}" data-item-id="${i.id}" style="left:${t.x}px;top:${t.y}px;z-index:${z};transform:translate(-50%,-50%) rotate(${t.rotation_deg}deg) scale(${t.scale_x},${t.scale_y})"><img src="${i.image_url}" width="${Math.max(1,i.width)}" height="${Math.max(1,i.height)}"/></div>`;
    }).join("");
    $("cmpLayers").innerHTML=scene.layers.map(l=>`<div class="composer-layer ${l.id===activeLayerId?'active':''}" data-layer-id="${l.id}"><button class="cmpLayerPick">${l.name}</button><span>${l.y_sort?'Y-Sort':''}</span></div>`).join("");
    $("cmpItemLayer").innerHTML=scene.layers.map(l=>`<option value="${l.id}">${l.name}</option>`).join("");
    renderEditor();
  }

  function renderEditor(){
    const item=scene?.items.find(i=>i.id===selectedItemId); $("cmpItemEmpty").classList.toggle("hidden",!!item); $("cmpItemEditor").classList.toggle("hidden",!item); if(!item)return;
    $("cmpX").value=item.transform.x; $("cmpY").value=item.transform.y; $("cmpRot").value=item.transform.rotation_deg; $("cmpScaleX").value=item.transform.scale_x; $("cmpScaleY").value=item.transform.scale_y; $("cmpZ").value=item.z_index; $("cmpItemLayer").value=item.layer_id;
  }

  $("cmpCreateScene").onclick=async()=>{ try{ const name=$("cmpSceneName").value.trim()||"scene"; const created=await json("/api/v1/library/composer/scenes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name})}); await refreshScenes(created.id); status(`已创建 ${created.name}`);}catch(e){status(e.message);} };
  $("cmpSceneSelect").onchange=()=>$("cmpSceneSelect").value&&loadScene($("cmpSceneSelect").value).catch(e=>status(e.message));
  $("cmpAddLayer").onclick=async()=>{ if(!scene)return status("先选择场景"); try{ scene=await json(`/api/v1/library/composer/scenes/${scene.id}/layers`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:$("cmpLayerName").value.trim()||"Layer"})}); activeLayerId=scene.layers.at(-1).id; render(); }catch(e){status(e.message);} };
  $("cmpLayers").onclick=e=>{ const row=e.target.closest("[data-layer-id]"); if(row){activeLayerId=row.dataset.layerId;render();} };
  $("cmpAddAsset").onclick=async()=>{ if(!scene)return status("先选择场景"); const assetId=currentLibraryAssetId(); if(!assetId)return status("先在 Asset Library 选中一个素材"); try{ scene=await json(`/api/v1/library/composer/scenes/${scene.id}/items`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({asset_id:assetId,layer_id:activeLayerId,transform:{x:scene.width/2,y:scene.height/2,rotation_deg:0,scale_x:1,scale_y:1}})}); selectedItemId=scene.items.at(-1).id; render(); }catch(e){status(e.message);} };

  $("cmpStage").addEventListener("pointerdown",e=>{ const el=e.target.closest(".composer-item"); if(!el||!scene)return; selectedItemId=el.dataset.itemId; const item=scene.items.find(i=>i.id===selectedItemId); if(!item||item.locked)return; render(); drag={id:item.id,startX:e.clientX,startY:e.clientY,x:item.transform.x,y:item.transform.y}; el.setPointerCapture?.(e.pointerId); });
  $("cmpStage").addEventListener("pointermove",e=>{ if(!drag||!scene)return; const item=scene.items.find(i=>i.id===drag.id); if(!item)return; item.transform.x=drag.x+(e.clientX-drag.startX); item.transform.y=drag.y+(e.clientY-drag.startY); const el=$("cmpStage").querySelector(`[data-item-id="${item.id}"]`); if(el){el.style.left=`${item.transform.x}px`;el.style.top=`${item.transform.y}px`;} $("cmpX").value=item.transform.x.toFixed(1);$("cmpY").value=item.transform.y.toFixed(1); });
  window.addEventListener("pointerup",async()=>{ if(!drag||!scene)return; const item=scene.items.find(i=>i.id===drag.id); const id=drag.id; drag=null; try{ scene=await json(`/api/v1/library/composer/scenes/${scene.id}/items/${id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({transform:item.transform})}); render(); }catch(e){status(e.message);} });

  $("cmpSaveItem").onclick=async()=>{ if(!scene||!selectedItemId)return; try{ scene=await json(`/api/v1/library/composer/scenes/${scene.id}/items/${selectedItemId}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({layer_id:$("cmpItemLayer").value,z_index:Number($("cmpZ").value||0),transform:{x:Number($("cmpX").value||0),y:Number($("cmpY").value||0),rotation_deg:Number($("cmpRot").value||0),scale_x:Number($("cmpScaleX").value||1),scale_y:Number($("cmpScaleY").value||1)}})}); render(); }catch(e){status(e.message);} };
  $("cmpDeleteItem").onclick=async()=>{ if(!scene||!selectedItemId)return; try{ scene=await json(`/api/v1/library/composer/scenes/${scene.id}/items/${selectedItemId}`,{method:"DELETE"}); selectedItemId=null; render(); }catch(e){status(e.message);} };
  $("cmpExport").onclick=async()=>{ if(!scene)return status("先选择场景"); try{ const target=$("cmpExportTarget").value; const out=await json(`/api/v1/library/composer/scenes/${scene.id}/export/${target}`,{method:"POST"}); const a=$("cmpDownload");a.href=out.download_url;a.classList.remove("hidden");a.textContent=`下载 ${target} 场景包`;status(`导出完成：${out.scene_id} → ${target}`);}catch(e){status(e.message);} };

  refreshScenes().catch(e=>status(e.message));
  window.GameCreaterSceneComposer={refresh:refreshScenes,load:loadScene};
})();
