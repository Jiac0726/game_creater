(() => {
  if (document.getElementById("assetRuntimePanel")) return;
  const base = document.getElementById("assetWorkflowPanel");
  if (!base) return;

  const style = document.createElement("style");
  style.textContent = `
    .asset-runtime-panel{margin-top:12px;border-top:1px solid rgba(127,127,127,.22);padding-top:12px}.asset-runtime-panel h3{margin:0 0 5px;font-size:13px}.asset-runtime-panel p{margin:0 0 10px;font-size:11px;opacity:.72}.asset-runtime-grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:9px}.asset-runtime-box{border:1px solid rgba(127,127,127,.2);border-radius:9px;padding:10px}.asset-runtime-box label{display:flex;flex-direction:column;gap:4px;margin-bottom:6px;font-size:11px}.asset-runtime-box input,.asset-runtime-box select{width:100%;box-sizing:border-box}.asset-runtime-actions{display:flex;gap:6px;flex-wrap:wrap}@media(max-width:900px){.asset-runtime-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:640px){.asset-runtime-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const root = document.createElement("div");
  root.id = "assetRuntimePanel";
  root.className = "asset-runtime-panel";
  root.innerHTML = `
    <h3>2D Game Runtime Config</h3>
    <p>Pivot / PPU / Render Layer / Sorting / Collision / Gameplay Tags 会进入引擎包；Unity 生成 Prefab，Godot 生成可实例化 .tscn。</p>
    <div class="asset-runtime-grid">
      <div class="asset-runtime-box">
        <label><span>Pivot X / Y</span><div style="display:flex;gap:5px"><input id="assetRuntimePivotX" type="number" min="0" max="1" step="0.05" value="0.5"/><input id="assetRuntimePivotY" type="number" min="0" max="1" step="0.05" value="1"/></div></label>
        <label><span>Pixels Per Unit</span><input id="assetRuntimePPU" type="number" min="1" value="100" /></label>
      </div>
      <div class="asset-runtime-box">
        <label><span>Render Layer</span><input id="assetRuntimeLayer" value="default" placeholder="foreground_props" /></label>
        <label><span>Sorting Order</span><input id="assetRuntimeSort" type="number" min="-32768" max="32767" value="0" /></label>
      </div>
      <div class="asset-runtime-box">
        <label><span>Collision</span><select id="assetRuntimeCollision"><option value="none">None</option><option value="box">Box</option></select></label>
        <label style="flex-direction:row;align-items:center"><input id="assetRuntimeTrigger" type="checkbox" style="width:auto" /> Trigger / Area</label>
        <label><span>Gameplay Tags</span><input id="assetRuntimeTags" placeholder="obstacle,interactable,loot" /></label>
      </div>
      <div class="asset-runtime-box">
        <div class="asset-runtime-actions"><button id="assetRuntimeLoad">读取当前配置</button><button id="assetRuntimeSave">保存当前素材</button><button id="assetRuntimeBulk">应用到批量勾选</button></div>
        <button id="assetRuntimeExport" style="margin-top:8px">导出带 Runtime Config 的素材包</button>
      </div>
    </div>
  `;
  base.appendChild(root);

  const $ = (id) => document.getElementById(id);
  const statusRoot = document.getElementById("assetFlowStatus");
  const status = (text) => { if (statusRoot) statusRoot.textContent = text; };

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

  function body() {
    return {
      pivot_x:Number($("assetRuntimePivotX").value),
      pivot_y:Number($("assetRuntimePivotY").value),
      pixels_per_unit:Number($("assetRuntimePPU").value),
      render_layer:$("assetRuntimeLayer").value.trim() || "default",
      sorting_order:Number($("assetRuntimeSort").value || 0),
      collision_mode:$("assetRuntimeCollision").value,
      collision_is_trigger:$("assetRuntimeTrigger").checked,
      gameplay_tags:$("assetRuntimeTags").value.split(",").map((value)=>value.trim()).filter(Boolean)
    };
  }

  function fill(data) {
    $("assetRuntimePivotX").value = data.pivot_x;
    $("assetRuntimePivotY").value = data.pivot_y;
    $("assetRuntimePPU").value = data.pixels_per_unit;
    $("assetRuntimeLayer").value = data.render_layer;
    $("assetRuntimeSort").value = data.sorting_order;
    $("assetRuntimeCollision").value = data.collision_mode;
    $("assetRuntimeTrigger").checked = !!data.collision_is_trigger;
    $("assetRuntimeTags").value = (data.gameplay_tags || []).join(",");
  }

  $("assetRuntimeLoad").addEventListener("click", async () => {
    const assetId = currentAssetId();
    if (!assetId) return status("Runtime Config：请先高亮素材。");
    try {
      const response = await fetch(`/api/v1/library/assets/${assetId}/runtime-config`);
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "读取失败");
      fill(data); status(`已读取 ${assetId} 的 Runtime Config。`);
    } catch (error) { status(`Runtime Config 读取失败：${error.message}`); }
  });

  $("assetRuntimeSave").addEventListener("click", async () => {
    const assetId = currentAssetId();
    if (!assetId) return status("Runtime Config：请先高亮素材。");
    try {
      const response = await fetch(`/api/v1/library/assets/${assetId}/runtime-config`, {method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(body())});
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "保存失败");
      fill(data); status(`Runtime Config 已保存：${assetId}`);
    } catch (error) { status(`Runtime Config 保存失败：${error.message}`); }
  });

  $("assetRuntimeBulk").addEventListener("click", async () => {
    const assetIds = selectedAssetIds();
    if (!assetIds.length) return status("Runtime Config：请批量勾选素材。");
    try {
      const response = await fetch("/api/v1/library/assets/bulk/runtime-config", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({asset_ids:assetIds,patch:body()})});
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "批量保存失败");
      status(`Runtime Config 已应用到 ${data.length} 个素材。`);
    } catch (error) { status(`Runtime Config 批量保存失败：${error.message}`); }
  });

  $("assetRuntimeExport").addEventListener("click", async () => {
    const assetIds = selectedAssetIds();
    if (!assetIds.length) return status("Runtime Pack：至少选择一个素材。");
    const name = document.getElementById("assetFlowPackName")?.value.trim() || "game_assets";
    const engine = document.getElementById("assetFlowEngine")?.value || "generic";
    const includeMasks = document.getElementById("assetFlowMasks")?.checked ?? true;
    const includeAlpha = document.getElementById("assetFlowAlpha")?.checked ?? true;
    status("正在构建带 Runtime Config 的素材包…");
    try {
      const response = await fetch("/api/v1/library/packs/export-runtime", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,asset_ids:assetIds,engine,include_masks:includeMasks,include_alpha:includeAlpha,include_hierarchy:true,include_runtime_config:true})});
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "导出失败");
      const link = document.getElementById("assetFlowDownload");
      if (link) { link.href=data.download_url; link.textContent=`下载 Runtime Pack · ${data.engine} · ${data.runtime_config_count} configs`; link.classList.remove("hidden"); }
      status(`Runtime Pack 已生成：${data.pack_id} · ${data.runtime_config_count} 个游戏配置`);
    } catch (error) { status(`Runtime Pack 导出失败：${error.message}`); }
  });
})();
