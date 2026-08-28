(() => {
  if (document.getElementById("assetWorkflowPanel")) return;
  const footer = document.querySelector(".footerbar");
  if (!footer) return;

  const style = document.createElement("style");
  style.textContent = `
    .asset-workflow-panel{padding:18px}.asset-workflow-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.asset-workflow-head h2{margin:0 0 5px}.asset-workflow-head p{margin:0;opacity:.72}.asset-workflow-grid{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:10px}.asset-workflow-box{border:1px solid rgba(127,127,127,.22);border-radius:10px;padding:12px}.asset-workflow-box h3{margin:0 0 9px;font-size:13px}.asset-workflow-box label{display:flex;flex-direction:column;gap:4px;margin-bottom:7px;font-size:11px}.asset-workflow-box input,.asset-workflow-box select,.asset-workflow-box textarea{width:100%;box-sizing:border-box}.asset-workflow-actions{display:flex;gap:6px;flex-wrap:wrap}.asset-workflow-status{margin-top:10px;font-size:12px;white-space:pre-wrap;word-break:break-word}.asset-workflow-download{display:inline-block;margin-top:7px}@media(max-width:1100px){.asset-workflow-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.asset-workflow-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const panel = document.createElement("section");
  panel.id = "assetWorkflowPanel";
  panel.className = "card asset-workflow-panel";
  panel.innerHTML = `
    <div class="asset-workflow-head"><div><h2>Asset Library Full Workflow</h2><p>图片导入 → 拆分 → 层级 → 非破坏编辑 → 素材包 / 游戏引擎交付</p></div><span>AI NATIVE</span></div>
    <div class="asset-workflow-grid">
      <div class="asset-workflow-box">
        <h3>1 · 图片导入</h3>
        <label><span>图片</span><input id="assetFlowImportFile" type="file" accept="image/png,image/jpeg,image/webp" /></label>
        <label><span>名称</span><input id="assetFlowImportName" placeholder="wooden_barrel" /></label>
        <label><span>分类</span><input id="assetFlowImportCategory" value="uncategorized" /></label>
        <label><span>标签</span><input id="assetFlowImportTags" placeholder="forest,prop,wood" /></label>
        <button id="assetFlowImportBtn">导入素材库</button>
      </div>
      <div class="asset-workflow-box">
        <h3>2 · 拆分 / 层级</h3>
        <label><span>拆分方式</span><select id="assetFlowSplitMode"><option value="alpha_components">透明区域自动拆分</option><option value="grid">网格 / Sprite Sheet</option><option value="ai_scene">GroundingDINO + SAM2</option></select></label>
        <label><span>网格 行 × 列</span><div style="display:flex;gap:5px"><input id="assetFlowRows" type="number" min="1" value="1"/><input id="assetFlowCols" type="number" min="1" value="4"/></div></label>
        <label><span>最小透明区域面积</span><input id="assetFlowMinArea" type="number" min="1" value="64" /></label>
        <label><span>AI Scene Prompts</span><input id="assetFlowPrompts" placeholder="tree, crate, rock" /></label>
        <div class="asset-workflow-actions"><button id="assetFlowSplitBtn">拆分当前素材</button><button id="assetFlowHierarchyBtn">查看层级</button></div>
      </div>
      <div class="asset-workflow-box">
        <h3>3 · 素材编辑</h3>
        <label><span>操作</span><select id="assetFlowEditOp"><option value="trim_alpha">裁透明边</option><option value="resize">缩放</option><option value="crop">裁剪</option><option value="flip_horizontal">水平翻转</option><option value="flip_vertical">垂直翻转</option><option value="rotate_90">旋转 90°</option><option value="pad">增加透明边距</option></select></label>
        <label><span>宽 × 高（resize）</span><div style="display:flex;gap:5px"><input id="assetFlowEditW" type="number" min="1" placeholder="width"/><input id="assetFlowEditH" type="number" min="1" placeholder="height"/></div></label>
        <label><span>裁剪 x1,y1,x2,y2</span><input id="assetFlowCrop" placeholder="0,0,256,256" /></label>
        <label><span>Padding</span><input id="assetFlowPadding" type="number" min="0" value="16" /></label>
        <button id="assetFlowEditBtn">生成新版本</button>
      </div>
      <div class="asset-workflow-box">
        <h3>4 · 导出素材包</h3>
        <label><span>素材包名称</span><input id="assetFlowPackName" value="game_assets" /></label>
        <label><span>目标</span><select id="assetFlowEngine"><option value="generic">Generic</option><option value="godot4">Godot 4</option><option value="unity2d">Unity 2D</option></select></label>
        <label style="flex-direction:row;align-items:center"><input id="assetFlowMasks" type="checkbox" checked style="width:auto"/> 包含 Mask</label>
        <label style="flex-direction:row;align-items:center"><input id="assetFlowAlpha" type="checkbox" checked style="width:auto"/> 包含 Alpha</label>
        <button id="assetFlowExportBtn">导出选中素材包</button>
        <a id="assetFlowDownload" class="asset-workflow-download hidden">下载素材包</a>
      </div>
    </div>
    <div id="assetFlowStatus" class="asset-workflow-status">先在 Asset Library 选择一个素材；素材包支持批量勾选。</div>
  `;
  footer.insertAdjacentElement("beforebegin", panel);

  const $ = (id) => document.getElementById(id);
  const status = (text) => { $("assetFlowStatus").textContent = text; };

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

  function refreshLibrary() {
    document.getElementById("libraryRefreshBtn")?.click();
  }

  $("assetFlowImportBtn").addEventListener("click", async () => {
    const file = $("assetFlowImportFile").files?.[0];
    if (!file) return status("请选择要导入的图片。");
    const form = new FormData();
    form.append("image", file);
    form.append("name", $("assetFlowImportName").value.trim() || file.name.replace(/\.[^.]+$/, ""));
    form.append("category", $("assetFlowImportCategory").value.trim() || "uncategorized");
    form.append("tags", $("assetFlowImportTags").value.trim());
    status("正在导入…");
    try {
      const response = await fetch("/api/v1/library/import/image", { method:"POST", body:form });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "导入失败");
      status(`导入完成：${data.name}\n${data.id}`); refreshLibrary();
    } catch (error) { status(`导入失败：${error.message}`); }
  });

  $("assetFlowSplitBtn").addEventListener("click", async () => {
    const assetId = currentAssetId(); if (!assetId) return status("先在 Asset Library 选择一个素材。");
    const mode = $("assetFlowSplitMode").value;
    const prompts = $("assetFlowPrompts").value.split(",").map(v=>v.trim()).filter(Boolean);
    const body = { mode, rows:Number($("assetFlowRows").value||1), columns:Number($("assetFlowCols").value||1), min_area:Number($("assetFlowMinArea").value||64), prompts };
    status("正在拆分…");
    try {
      const response = await fetch(`/api/v1/library/assets/${assetId}/split`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "拆分失败");
      status(`拆分完成：${data.child_asset_ids.length} 个子素材${data.scene_id ? `\nScene ${data.scene_id}` : ""}`); refreshLibrary();
    } catch (error) { status(`拆分失败：${error.message}`); }
  });

  $("assetFlowHierarchyBtn").addEventListener("click", async () => {
    const assetId = currentAssetId(); if (!assetId) return status("先选择一个素材。");
    try {
      const response = await fetch(`/api/v1/library/assets/${assetId}/hierarchy`); const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "层级读取失败");
      status(JSON.stringify(data, null, 2));
    } catch (error) { status(`层级读取失败：${error.message}`); }
  });

  $("assetFlowEditBtn").addEventListener("click", async () => {
    const assetId = currentAssetId(); if (!assetId) return status("先选择一个素材。");
    const operation = $("assetFlowEditOp").value;
    const body = { operation, activate:true, padding:Number($("assetFlowPadding").value||0) };
    if (operation === "resize") { body.width = Number($("assetFlowEditW").value||0) || null; body.height = Number($("assetFlowEditH").value||0) || null; }
    if (operation === "crop") {
      const values = $("assetFlowCrop").value.split(",").map(Number);
      if (values.length !== 4 || values.some((value)=>!Number.isFinite(value))) return status("裁剪请输入 x1,y1,x2,y2。");
      body.rect = { x1:values[0], y1:values[1], x2:values[2], y2:values[3] };
    }
    status("正在生成编辑版本…");
    try {
      const response = await fetch(`/api/v1/library/assets/${assetId}/edit`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "编辑失败");
      status(`编辑完成：v${data.version} · ${data.width}×${data.height}\n原版本仍保留。`); refreshLibrary();
    } catch (error) { status(`编辑失败：${error.message}`); }
  });

  $("assetFlowExportBtn").addEventListener("click", async () => {
    const assetIds = selectedAssetIds(); if (!assetIds.length) return status("至少选择一个素材或批量勾选素材。");
    const body = { name:$("assetFlowPackName").value.trim() || "game_assets", asset_ids:assetIds, engine:$("assetFlowEngine").value, include_masks:$("assetFlowMasks").checked, include_alpha:$("assetFlowAlpha").checked, include_hierarchy:true };
    status("正在构建素材包…");
    try {
      const response = await fetch("/api/v1/library/packs/export", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "导出失败");
      const link = $("assetFlowDownload"); link.href=data.download_url; link.textContent=`下载 ${data.name} · ${data.engine} · ${data.asset_count} assets`; link.classList.remove("hidden");
      status(`素材包已生成：${data.pack_id}`);
    } catch (error) { status(`导出失败：${error.message}`); }
  });
})();
