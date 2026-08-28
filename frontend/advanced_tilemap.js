(() => {
  if (document.getElementById("advancedTilemapPanel")) return;
  const footer = document.querySelector(".footerbar");
  if (!footer) return;

  const style = document.createElement("style");
  style.textContent = `
    .atm-panel{padding:18px}.atm-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.atm-grid{display:grid;grid-template-columns:280px 1fr 300px;gap:12px;margin-top:12px}.atm-box{border:1px solid rgba(127,127,127,.22);border-radius:10px;padding:12px}.atm-box label{display:flex;flex-direction:column;gap:4px;margin:7px 0;font-size:11px}.atm-box input,.atm-box select,.atm-box textarea{width:100%;box-sizing:border-box}.atm-canvas{position:relative;overflow:auto;min-height:360px;max-height:640px;background-image:linear-gradient(rgba(127,127,127,.10) 1px,transparent 1px),linear-gradient(90deg,rgba(127,127,127,.10) 1px,transparent 1px);background-size:24px 24px}.atm-cell{position:absolute;width:22px;height:22px;border:1px solid rgba(127,127,127,.18);font-size:8px;display:flex;align-items:center;justify-content:center;overflow:hidden}.atm-status{white-space:pre-wrap;font-size:12px;margin-top:10px}@media(max-width:1100px){.atm-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const panel = document.createElement("section");
  panel.id = "advancedTilemapPanel";
  panel.className = "card atm-panel";
  panel.innerHTML = `
    <div class="atm-head"><div><h2 style="margin:0">Advanced Tilemap</h2><p style="margin:4px 0 0;opacity:.72">TileMapLayer · Terrain Painter · Collision / Navigation · AI Native</p></div><span>AI NATIVE</span></div>
    <div class="atm-grid">
      <div class="atm-box">
        <h3>Map</h3>
        <label>TileSet ID<input id="atmTileset" placeholder="tileset_xxx"></label>
        <label>Name<input id="atmName" value="level_01"></label>
        <div style="display:flex;gap:6px"><label style="flex:1">Width<input id="atmW" type="number" min="1" value="64"></label><label style="flex:1">Height<input id="atmH" type="number" min="1" value="64"></label></div>
        <button id="atmCreate">Create Map</button>
        <label>Existing Map<select id="atmMapSelect"><option value="">—</option></select></label>
        <button id="atmRefresh">Refresh</button>
        <hr>
        <h3>Layer</h3>
        <label>Name<input id="atmLayerName" value="Decor"></label>
        <label>Type<select id="atmLayerType"><option value="visual">Visual</option><option value="collision">Collision</option><option value="navigation">Navigation</option></select></label>
        <button id="atmAddLayer">Add Layer</button>
        <label>Active Layer<select id="atmLayerSelect"></select></label>
      </div>
      <div class="atm-box">
        <h3>Map Preview</h3>
        <div id="atmCanvas" class="atm-canvas"></div>
      </div>
      <div class="atm-box">
        <h3>Brush</h3>
        <label>Asset ID<input id="atmAsset" placeholder="asset_xxx"></label>
        <label>Terrain<input id="atmTerrain" placeholder="grass"></label>
        <label>Cells (x,y per line)<textarea id="atmCells" rows="8">0,0\n1,0\n2,0</textarea></label>
        <div style="display:flex;gap:6px"><button id="atmPaint">Paint</button><button id="atmErase">Erase</button></div>
        <p style="font-size:11px;opacity:.7">Terrain Paint 会调用 TileSet 的 cardinal4/eight8 规则重新计算邻接 Tile。</p>
        <hr>
        <h3>Export</h3>
        <label>Engine<select id="atmEngine"><option value="godot4">Godot 4</option><option value="unity2d">Unity 2D</option><option value="generic">Generic</option></select></label>
        <button id="atmExport">Export TileMap</button>
        <a id="atmDownload" class="hidden" style="display:inline-block;margin-top:8px">Download</a>
      </div>
    </div>
    <div id="atmStatus" class="atm-status">Create or select a TileMap.</div>`;
  footer.insertAdjacentElement("beforebegin", panel);

  const $ = id => document.getElementById(id);
  let current = null;
  const status = text => { $("atmStatus").textContent = text; };

  function parseCells() {
    return $("atmCells").value.split(/\n+/).map(v=>v.trim()).filter(Boolean).map(line=>{
      const [x,y] = line.split(",").map(Number);
      if (!Number.isInteger(x) || !Number.isInteger(y)) throw new Error(`Invalid cell: ${line}`);
      return {x,y};
    });
  }
  async function jsonFetch(url, options={}) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
    return data;
  }
  function render(project) {
    current = project;
    $("atmLayerSelect").innerHTML = project.layers.map(l=>`<option value="${l.id}">${l.order}: ${l.name} (${l.layer_type})</option>`).join("");
    const canvas=$("atmCanvas"); canvas.innerHTML="";
    const size=24; canvas.style.width=`${Math.max(480,Math.min(project.width,40)*size)}px`; canvas.style.height=`${Math.max(360,Math.min(project.height,25)*size)}px`;
    project.layers.filter(l=>l.visible).forEach(layer=>layer.cells.forEach(cell=>{
      if(cell.x<0||cell.y<0||cell.x>=40||cell.y>=25)return;
      const el=document.createElement("div"); el.className="atm-cell"; el.style.left=`${cell.x*size}px`; el.style.top=`${cell.y*size}px`; el.style.zIndex=String(layer.order+1);
      el.title=`${layer.name} (${cell.x},${cell.y}) ${cell.asset_id||cell.terrain||""}`; el.textContent=(cell.terrain||cell.asset_id||"?").slice(0,3); canvas.appendChild(el);
    }));
    status(`${project.name} · ${project.width}×${project.height} · ${project.layers.length} layers · ${project.layers.reduce((n,l)=>n+l.cells.length,0)} cells`);
  }
  async function refreshList(selectId=null) {
    const maps=await jsonFetch("/api/v1/library/tilemaps");
    $("atmMapSelect").innerHTML='<option value="">—</option>'+maps.map(m=>`<option value="${m.id}">${m.name}</option>`).join("");
    if(selectId){$("atmMapSelect").value=selectId; const map=await jsonFetch(`/api/v1/library/tilemaps/${selectId}`); render(map);}
  }
  $("atmRefresh").onclick=()=>refreshList().catch(e=>status(e.message));
  $("atmMapSelect").onchange=async e=>{if(e.target.value)render(await jsonFetch(`/api/v1/library/tilemaps/${e.target.value}`));};
  $("atmCreate").onclick=async()=>{try{const map=await jsonFetch("/api/v1/library/tilemaps",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:$("atmName").value,tileset_id:$("atmTileset").value,width:Number($("atmW").value),height:Number($("atmH").value)})}); await refreshList(map.id);}catch(e){status(`Create failed: ${e.message}`)}};
  $("atmAddLayer").onclick=async()=>{if(!current)return status("Select a map first.");try{render(await jsonFetch(`/api/v1/library/tilemaps/${current.id}/layers`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:$("atmLayerName").value,layer_type:$("atmLayerType").value})}));}catch(e){status(e.message)}};
  async function paint(erase=false){if(!current)return status("Select a map first.");try{const body={layer_id:$("atmLayerSelect").value,cells:parseCells()}; if(!erase){body.asset_id=$("atmAsset").value.trim()||null;body.terrain=$("atmTerrain").value.trim()||null;}render(await jsonFetch(`/api/v1/library/tilemaps/${current.id}/${erase?"erase":"paint"}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}));}catch(e){status(e.message)}}
  $("atmPaint").onclick=()=>paint(false); $("atmErase").onclick=()=>paint(true);
  $("atmExport").onclick=async()=>{if(!current)return status("Select a map first.");try{const data=await jsonFetch(`/api/v1/library/tilemaps/${current.id}/export`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({engine:$("atmEngine").value})});const link=$("atmDownload");link.href=data.download_url;link.textContent=`Download ${data.engine}`;link.classList.remove("hidden");status(`Export ready: ${data.export_id}`);}catch(e){status(e.message)}};
  refreshList().catch(()=>{});
})();
