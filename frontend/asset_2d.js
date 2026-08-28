(() => {
  if (document.getElementById("asset2dPanel")) return;
  const footer = document.querySelector(".footerbar");
  if (!footer) return;

  const style = document.createElement("style");
  style.textContent = `
    .asset2d-panel{padding:18px}.asset2d-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.asset2d-head h2{margin:0 0 5px}.asset2d-head p{margin:0;opacity:.72}.asset2d-grid{display:grid;grid-template-columns:repeat(4,minmax(210px,1fr));gap:10px}.asset2d-box{border:1px solid rgba(127,127,127,.22);border-radius:10px;padding:12px}.asset2d-box h3{margin:0 0 9px;font-size:13px}.asset2d-box label{display:flex;flex-direction:column;gap:4px;margin-bottom:7px;font-size:11px}.asset2d-box input,.asset2d-box select,.asset2d-box textarea{width:100%;box-sizing:border-box}.asset2d-status{margin-top:10px;font-size:12px;white-space:pre-wrap;word-break:break-word}.asset2d-frame-list{display:flex;flex-direction:column;gap:4px;max-height:220px;overflow:auto;margin:7px 0}.asset2d-frame{display:grid;grid-template-columns:24px 1fr auto;gap:5px;align-items:center;border:1px solid rgba(127,127,127,.22);border-radius:7px;padding:5px;cursor:grab;font-size:11px}.asset2d-frame.dragging{opacity:.45}.asset2d-frame-actions{display:flex;gap:3px}.asset2d-frame-actions button{padding:2px 5px;font-size:10px}.asset2d-rules{min-height:120px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px}.asset2d-help{font-size:10px;opacity:.68;line-height:1.45;margin:5px 0}@media(max-width:1200px){.asset2d-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.asset2d-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const panel = document.createElement("section");
  panel.id = "asset2dPanel";
  panel.className = "card asset2d-panel";
  panel.innerHTML = `
    <div class="asset2d-head"><div><h2>2D Game Ready Resources</h2><p>Polygon Collision · Sprite Animation · Terrain/Autotile · Game Ready Pack</p></div><span>AI NATIVE</span></div>
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
        <hr/>
        <label><span>帧排序工作台</span><select id="asset2dAnimSelect"><option value="">选择动画…</option></select></label>
        <div id="asset2dFrameList" class="asset2d-frame-list"></div>
        <button id="asset2dFramesSaveBtn">保存帧顺序</button>
        <div class="asset2d-help">拖拽帧可排序；↑↓移动；×移除；+复制。发生增删后保存会允许修改帧集合。</div>
      </div>
      <div class="asset2d-box">
        <h3>TileSet / Terrain / Autotile</h3>
        <label><span>TileSet 名</span><input id="asset2dTileName" value="ground_tiles" /></label>
        <label><span>Tile 宽 × 高</span><div style="display:flex;gap:5px"><input id="asset2dTileW" type="number" min="1" value="32"/><input id="asset2dTileH" type="number" min="1" value="32"/></div></label>
        <label><span>Terrain Tags</span><input id="asset2dTerrainTags" placeholder="grass,ground" /></label>
        <label><span>Autotile</span><select id="asset2dAutoMode"><option value="none">关闭</option><option value="cardinal4">4方向 N/E/S/W</option><option value="eight8">8方向</option></select></label>
        <button id="asset2dRuleTemplateBtn" type="button">用勾选素材生成规则模板</button>
        <label><span>Terrain Rules</span><textarea id="asset2dTerrainRules" class="asset2d-rules" placeholder="asset_id|grass|0|0\nasset_id|grass|85|10"></textarea></label>
        <div class="asset2d-help">格式：Asset ID | Terrain | Neighbor Mask | Priority。bit：N=1 NE=2 E=4 SE=8 S=16 SW=32 W=64 NW=128。cardinal4 常用全连接=85。</div>
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
  let activeClip = null;
  let frameIds = [];
  let frameCompositionChanged = false;
  let draggedIndex = null;

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

  function parseTerrainRules() {
    return $("asset2dTerrainRules").value.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map((line, index) => {
      const [asset_id, terrain, maskText = "0", priorityText = "0"] = line.split("|").map(v => v.trim());
      if (!asset_id || !terrain) throw new Error(`Terrain Rule 第 ${index + 1} 行缺少 Asset ID 或 Terrain`);
      const neighbor_mask = Number(maskText);
      const priority = Number(priorityText);
      if (!Number.isInteger(neighbor_mask) || neighbor_mask < 0 || neighbor_mask > 255) throw new Error(`Terrain Rule 第 ${index + 1} 行 mask 必须是 0-255`);
      if (!Number.isInteger(priority)) throw new Error(`Terrain Rule 第 ${index + 1} 行 priority 必须是整数`);
      return { asset_id, terrain, neighbor_mask, priority };
    });
  }

  async function loadAnimations(preferId = null) {
    try {
      const response = await fetch("/api/v1/library/animations");
      const clips = await response.json();
      if (!response.ok) throw new Error(clips.detail || "动画列表加载失败");
      const select = $("asset2dAnimSelect");
      const current = preferId || select.value;
      select.innerHTML = '<option value="">选择动画…</option>';
      for (const clip of clips) {
        const option = document.createElement("option");
        option.value = clip.id;
        option.textContent = `${clip.name} · ${clip.frame_asset_ids.length}帧 · ${clip.id}`;
        select.appendChild(option);
      }
      if (current && clips.some(c => c.id === current)) {
        select.value = current;
        await loadClip(current);
      }
    } catch (error) {
      status(`动画列表失败：${error.message}`);
    }
  }

  async function loadClip(id) {
    if (!id) {
      activeClip = null; frameIds = []; frameCompositionChanged = false; renderFrames(); return;
    }
    const response = await fetch(`/api/v1/library/animations/${id}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "动画加载失败");
    activeClip = data;
    frameIds = [...data.frame_asset_ids];
    frameCompositionChanged = false;
    $("asset2dAnimName").value = data.name;
    $("asset2dAnimFps").value = data.fps;
    $("asset2dAnimLoop").checked = data.loop;
    renderFrames();
  }

  function moveFrame(from, to) {
    if (from < 0 || from >= frameIds.length || to < 0 || to >= frameIds.length || from === to) return;
    const [item] = frameIds.splice(from, 1);
    frameIds.splice(to, 0, item);
    renderFrames();
  }

  function renderFrames() {
    const list = $("asset2dFrameList");
    list.innerHTML = "";
    frameIds.forEach((assetId, index) => {
      const row = document.createElement("div");
      row.className = "asset2d-frame";
      row.draggable = true;
      row.dataset.index = String(index);
      row.innerHTML = `<span>${index + 1}</span><code>${assetId}</code><span class="asset2d-frame-actions"><button data-act="up">↑</button><button data-act="down">↓</button><button data-act="dup">+</button><button data-act="remove">×</button></span>`;
      row.addEventListener("dragstart", () => { draggedIndex = index; row.classList.add("dragging"); });
      row.addEventListener("dragend", () => { draggedIndex = null; row.classList.remove("dragging"); });
      row.addEventListener("dragover", event => event.preventDefault());
      row.addEventListener("drop", event => { event.preventDefault(); if (draggedIndex !== null) moveFrame(draggedIndex, index); });
      row.querySelector('[data-act="up"]').addEventListener("click", () => moveFrame(index, index - 1));
      row.querySelector('[data-act="down"]').addEventListener("click", () => moveFrame(index, index + 1));
      row.querySelector('[data-act="dup"]').addEventListener("click", () => { frameIds.splice(index + 1, 0, assetId); frameCompositionChanged = true; renderFrames(); });
      row.querySelector('[data-act="remove"]').addEventListener("click", () => { if (frameIds.length <= 1) return; frameIds.splice(index, 1); frameCompositionChanged = true; renderFrames(); });
      list.appendChild(row);
    });
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
    if (!ids.length) return status("请按帧顺序勾选要使用的素材。");
    try {
      const response = await fetch("/api/v1/library/animations", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ name:$("asset2dAnimName").value.trim() || "animation", frame_asset_ids:ids, fps:Number($("asset2dAnimFps").value || 8), loop:$("asset2dAnimLoop").checked })
      });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "动画创建失败");
      $("asset2dAnimIds").value = [...new Set([...csvIds($("asset2dAnimIds").value), data.id])].join(",");
      await loadAnimations(data.id);
      status(`动画已创建：${data.id}\n${data.frame_asset_ids.length} 帧 · ${data.fps} FPS`);
    } catch (error) { status(`动画失败：${error.message}`); }
  });

  $("asset2dAnimSelect").addEventListener("change", async event => {
    try { await loadClip(event.target.value); }
    catch (error) { status(`动画加载失败：${error.message}`); }
  });

  $("asset2dFramesSaveBtn").addEventListener("click", async () => {
    if (!activeClip || !frameIds.length) return status("请先在帧排序工作台选择动画。");
    try {
      const response = await fetch(`/api/v1/library/animations/${activeClip.id}/frames`, {
        method:"PUT", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ frame_asset_ids:frameIds, require_same_frames:!frameCompositionChanged })
      });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "帧序列保存失败");
      activeClip = data; frameIds = [...data.frame_asset_ids]; frameCompositionChanged = false; renderFrames();
      status(`帧序列已保存：${data.id} · ${data.frame_asset_ids.length} 帧`);
    } catch (error) { status(`帧序列保存失败：${error.message}`); }
  });

  $("asset2dRuleTemplateBtn").addEventListener("click", () => {
    const ids = selectedAssetIds();
    if (!ids.length) return status("请先勾选 Tile 素材。");
    const terrain = csvIds($("asset2dTerrainTags").value)[0] || "terrain";
    $("asset2dTerrainRules").value = ids.map((id, index) => `${id}|${terrain}|${index === 0 ? 0 : 85}|${index}`).join("\n");
    if ($("asset2dAutoMode").value === "none") $("asset2dAutoMode").value = "cardinal4";
  });

  $("asset2dTileBtn").addEventListener("click", async () => {
    const ids = selectedAssetIds();
    if (!ids.length) return status("请先勾选 Tile 素材。");
    try {
      const rules = parseTerrainRules();
      const response = await fetch("/api/v1/library/tilesets", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ name:$("asset2dTileName").value.trim() || "tileset", tile_asset_ids:ids, tile_width:Number($("asset2dTileW").value || 32), tile_height:Number($("asset2dTileH").value || 32), terrain_tags:csvIds($("asset2dTerrainTags").value), autotile_mode:$("asset2dAutoMode").value, terrain_rules:rules })
      });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "TileSet 创建失败");
      $("asset2dTileIds").value = [...new Set([...csvIds($("asset2dTileIds").value), data.id])].join(",");
      status(`TileSet 已创建：${data.id}\n${data.tile_asset_ids.length} tiles · ${data.autotile_mode} · ${data.terrain_rules.length} rules`);
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

  loadAnimations();
})();
