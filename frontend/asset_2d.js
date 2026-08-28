(() => {
  if (document.getElementById("asset2dPanel")) return;
  const footer = document.querySelector(".footerbar");
  if (!footer) return;

  const style = document.createElement("style");
  style.textContent = `
    .asset2d-panel{padding:18px}.asset2d-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.asset2d-head h2{margin:0 0 5px}.asset2d-head p{margin:0;opacity:.72}.asset2d-grid{display:grid;grid-template-columns:repeat(4,minmax(190px,1fr));gap:10px}.asset2d-box{border:1px solid rgba(127,127,127,.22);border-radius:10px;padding:12px}.asset2d-box h3{margin:0 0 9px;font-size:13px}.asset2d-box label{display:flex;flex-direction:column;gap:4px;margin-bottom:7px;font-size:11px}.asset2d-box input,.asset2d-box select{width:100%;box-sizing:border-box}.asset2d-status{margin-top:10px;font-size:12px;white-space:pre-wrap;word-break:break-word}@media(max-width:1100px){.asset2d-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.asset2d-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const panel = document.createElement("section");
  panel.id = "asset2dPanel";
  panel.className = "card asset2d-panel";
  panel.innerHTML = `
    <div class="asset2d-head"><div><h2>2D Game Ready Resources</h2><p>Polygon Collision · Sprite Animation · TileSet · Game Ready Pack</p></div><span>AI NATIVE</span></div>
    <div class="asset2d-grid">
      <div class="asset2d-box">
        <h3>Polygon Collision</h3>
        <label><span>最大顶点数</span><input id="asset2dPolyPoints" type="number" min="3" max="128" value="24" /></label>
        <label style="flex-direction:row;align-items:center"><input id="asset2dPolyTrigger" type="checkbox" style="width:auto"/> Trigger / Area</label>
        <button id="asset2dPolyBtn">从 Mask 生成当前素材碰撞</button>
      </div>
      <div class="asset2d-box">
        <h3>Sprite Animation</h3>
        <label><span>动画名</span><input id="asset2dAnimName" value="idle" /></label>
        <label><span>FPS</span><input id="asset2dAnimFps" type="number" min="0.1" max="120" step="0.1" value="8" /></label>
        <label style="flex-direction:row;align-items:center"><input id="asset2dAnimLoop" type="checkbox" checked style="width:auto"/> Loop</label>
        <button id="asset2dAnimBtn">用勾选素材创建动画</button>
      </div>
      <div class="asset2d-box">
        <h3>TileSet</h3>
        <label><span>TileSet 名</span><input id="asset2dTileName" value="ground_tiles" /></label>
        <label><span>Tile 宽 × 高</span><div style="display:flex;gap:5px"><input id="asset2dTileW" type="number" min="1" value="32"/><input id="asset2dTileH" type="number" min="1" value="32"/></div></label>
        <label><span>Terrain Tags</span><input id="asset2dTerrainTags" placeholder="grass,ground" /></label>
        <button id="asset2dTileBtn">用勾选素材创建 TileSet</button>
      </div>
      <div class="asset2d-box">
        <h3>Game Ready Pack</h3>
        <label><span>包名</span><input id="asset2dPackName" value="game_ready_2d" /></label>
        <label><span>目标引擎</span><select id="asset2dEngine"><option value="godot4">Godot 4</option><option value="unity2d">Unity 2D</option><option value="generic">Generic</option></select></label>
        <label><span>Animation IDs</span><input id="asset2dAnimIds" placeholder="anim_xxx" /></label>
        <label><span>TileSet IDs</span><input id="asset2dTileIds" placeholder="tileset_xxx" /></label>
        <button id="asset2dExportBtn">导出 Game Ready Pack</button>
        <a id="asset2dDownload" class="hidden" style="display:inline-block;margin-top:7px">下载</a>
      </div>
    </div>
    <div id="asset2dStatus" class="asset2d-status">Polygon 使用当前选中素材；Animation/TileSet/Pack 使用 Asset Library 勾选素材。</div>
  `;
  footer.insertAdjacentElement("beforebegin", panel);

  const $ = (id) => document.getElementById(id);
  const status = (text) => { $("asset2dStatus").textContent = text; };

  function currentAssetId() {
    return document.querySelector(".library-card.selected")?.dataset.assetId || null;
  }

  function selectedAssetIds() {
    const ids = [...document.querySelectorAll(".library-card-select:checked")]
      .map((input) => input.closest(".library-card")?.dataset.assetId)
      .filter(Boolean);
    const current = currentAssetId();
    if (!ids.length && current) ids.push(current);
    return [...new Set(ids)];
  }

  function csvIds(value) {
    return value.split(",").map(v => v.trim()).filter(Boolean);
  }

  $("asset2dPolyBtn").addEventListener("click", async () => {
    const assetId = currentAssetId();
    if (!assetId) return status("请先选择一个素材。");
    try {
      status("正在从 Mask 生成 Polygon Collision…");
      let response = await fetch(`/api/v1/library/assets/${assetId}/collision-polygon/generate`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ alpha_threshold:1, max_points:Number($("asset2dPolyPoints").value || 24) })
      });
      let polygon = await response.json();
      if (!response.ok) throw new Error(polygon.detail || "Polygon 生成失败");
      response = await fetch(`/api/v1/library/assets/${assetId}/runtime-config`, {
        method:"PATCH", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ collision_mode:"polygon", collision_is_trigger:$("asset2dPolyTrigger").checked })
      });
      const runtime = await response.json();
      if (!response.ok) throw new Error(runtime.detail || "Runtime 配置失败");
      status(`Polygon 已生成：${polygon.points.length} 顶点 · ${runtime.collision_is_trigger ? "Trigger" : "Solid"}`);
    } catch (error) { status(`Polygon 失败：${error.message}`); }
  });

  $("asset2dAnimBtn").addEventListener("click", async () => {
    const ids = selectedAssetIds();
    if (!ids.length) return status("请按帧顺序勾选/排列要使用的素材。");
    try {
      const response = await fetch("/api/v1/library/animations", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ name:$("asset2dAnimName").value.trim() || "animation", frame_asset_ids:ids, fps:Number($("asset2dAnimFps").value || 8), loop:$("asset2dAnimLoop").checked })
      });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "动画创建失败");
      $("asset2dAnimIds").value = [...new Set([...csvIds($("asset2dAnimIds").value), data.id])].join(",");
      status(`动画已创建：${data.id}\n${data.frame_asset_ids.length} 帧 · ${data.fps} FPS`);
    } catch (error) { status(`动画失败：${error.message}`); }
  });

  $("asset2dTileBtn").addEventListener("click", async () => {
    const ids = selectedAssetIds();
    if (!ids.length) return status("请先勾选 Tile 素材。");
    try {
      const response = await fetch("/api/v1/library/tilesets", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ name:$("asset2dTileName").value.trim() || "tileset", tile_asset_ids:ids, tile_width:Number($("asset2dTileW").value || 32), tile_height:Number($("asset2dTileH").value || 32), terrain_tags:csvIds($("asset2dTerrainTags").value) })
      });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "TileSet 创建失败");
      $("asset2dTileIds").value = [...new Set([...csvIds($("asset2dTileIds").value), data.id])].join(",");
      status(`TileSet 已创建：${data.id}\n${data.tile_asset_ids.length} tiles · ${data.tile_width}×${data.tile_height}`);
    } catch (error) { status(`TileSet 失败：${error.message}`); }
  });

  $("asset2dExportBtn").addEventListener("click", async () => {
    const ids = selectedAssetIds();
    if (!ids.length) return status("请至少选择一个素材。");
    try {
      status("正在生成 Game Ready Pack…");
      const response = await fetch("/api/v1/library/packs/export-game-ready", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ name:$("asset2dPackName").value.trim() || "game_ready_2d", asset_ids:ids, engine:$("asset2dEngine").value, include_masks:true, include_alpha:true, include_hierarchy:true, include_runtime_config:true, include_collision_polygons:true, animation_ids:csvIds($("asset2dAnimIds").value), tileset_ids:csvIds($("asset2dTileIds").value) })
      });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Game Ready 导出失败");
      const link = $("asset2dDownload"); link.href=data.download_url; link.textContent=`下载 ${data.name}`; link.classList.remove("hidden");
      status(`Game Ready Pack：${data.pack_id}\nAssets ${data.asset_count} · Polygon ${data.polygon_collision_count} · Animations ${data.animation_count} · TileSets ${data.tileset_count}`);
    } catch (error) { status(`Game Ready 导出失败：${error.message}`); }
  });
})();
