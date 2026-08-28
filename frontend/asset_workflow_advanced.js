(() => {
  if (document.getElementById("assetWorkflowAdvanced")) return;
  const base = document.getElementById("assetWorkflowPanel");
  if (!base) return;

  const style = document.createElement("style");
  style.textContent = `
    .asset-workflow-advanced{margin-top:12px;border-top:1px solid rgba(127,127,127,.22);padding-top:12px}.asset-workflow-advanced h3{margin:0 0 10px;font-size:13px}.asset-workflow-advanced-grid{display:grid;grid-template-columns:repeat(5,minmax(170px,1fr));gap:9px}.asset-workflow-advanced-box{border:1px solid rgba(127,127,127,.2);border-radius:9px;padding:10px}.asset-workflow-advanced-box h4{margin:0 0 8px;font-size:12px}.asset-workflow-advanced-box label{display:flex;flex-direction:column;gap:4px;margin-bottom:6px;font-size:11px}.asset-workflow-advanced-box input,.asset-workflow-advanced-box select{width:100%;box-sizing:border-box}.asset-workflow-preflight{margin-top:9px;font-size:11px;white-space:pre-wrap;word-break:break-word}.asset-workflow-ok{font-weight:700}.asset-workflow-errors{font-weight:700}@media(max-width:1100px){.asset-workflow-advanced-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:720px){.asset-workflow-advanced-grid{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);

  const advanced = document.createElement("div");
  advanced.id = "assetWorkflowAdvanced";
  advanced.className = "asset-workflow-advanced";
  advanced.innerHTML = `
    <h3>批量管理 / 版本回退 / 层级重挂 / 导出检查</h3>
    <div class="asset-workflow-advanced-grid">
      <div class="asset-workflow-advanced-box">
        <h4>批量图片导入</h4>
        <label><span>图片（最多 200）</span><input id="assetAdvFiles" type="file" multiple accept="image/png,image/jpeg,image/webp" /></label>
        <label><span>分类</span><input id="assetAdvCategory" value="uncategorized" /></label>
        <label><span>共享标签</span><input id="assetAdvTags" placeholder="ui,props,medieval" /></label>
        <button id="assetAdvImport">批量导入</button>
      </div>
      <div class="asset-workflow-advanced-box">
        <h4>版本回退 / 激活</h4>
        <label><span>当前素材版本</span><select id="assetAdvVersion"><option value="">先读取版本</option></select></label>
        <div class="asset-workflow-actions"><button id="assetAdvLoadVersions">读取版本</button><button id="assetAdvActivateVersion">激活所选版本</button></div>
      </div>
      <div class="asset-workflow-advanced-box">
        <h4>批量非破坏编辑</h4>
        <label><span>操作</span><select id="assetAdvBulkOp"><option value="trim_alpha">裁透明边</option><option value="flip_horizontal">水平翻转</option><option value="flip_vertical">垂直翻转</option><option value="rotate_90">旋转 90°</option><option value="pad">Padding</option><option value="resize">统一缩放</option></select></label>
        <label><span>参数：宽 × 高 / Padding</span><div style="display:flex;gap:5px"><input id="assetAdvW" type="number" min="1" placeholder="width" /><input id="assetAdvH" type="number" min="1" placeholder="height" /><input id="assetAdvPad" type="number" min="0" value="8" /></div></label>
        <button id="assetAdvBulkEdit">编辑批量勾选素材</button>
      </div>
      <div class="asset-workflow-advanced-box">
        <h4>层级重挂</h4>
        <p style="font-size:11px;opacity:.72">当前高亮素材作为父级；批量勾选素材作为子级。默认移除旧父级，并拒绝循环层级。</p>
        <label style="flex-direction:row;align-items:center"><input id="assetAdvRemoveParents" type="checkbox" checked style="width:auto" /> 移除已有父级</label>
        <button id="assetAdvReparent">重新挂载所选子素材</button>
      </div>
      <div class="asset-workflow-advanced-box">
        <h4>导出 Preflight</h4>
        <label style="flex-direction:row;align-items:center"><input id="assetAdvReviewed" type="checkbox" checked style="width:auto" /> 必须已审核</label>
        <label style="flex-direction:row;align-items:center"><input id="assetAdvRequireMask" type="checkbox" style="width:auto" /> 必须有 Mask</label>
        <label style="flex-direction:row;align-items:center"><input id="assetAdvRequireAlpha" type="checkbox" style="width:auto" /> 必须有 Alpha</label>
        <button id="assetAdvPreflight">检查批量勾选素材</button>
        <div id="assetAdvPreflightResult" class="asset-workflow-preflight"></div>
      </div>
    </div>
  `;
  base.appendChild(advanced);

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
    return [...new Set(ids)];
  }

  function refreshLibrary() {
    document.getElementById("libraryRefreshBtn")?.click();
  }

  $("assetAdvImport").addEventListener("click", async () => {
    const files = [...($("assetAdvFiles").files || [])];
    if (!files.length) return status("批量导入：请先选择图片。");
    const form = new FormData();
    files.forEach((file) => form.append("images", file));
    form.append("category", $("assetAdvCategory").value.trim() || "uncategorized");
    form.append("tags", $("assetAdvTags").value.trim());
    status(`正在批量导入 ${files.length} 张图片…`);
    try {
      const response = await fetch("/api/v1/library/import/images", { method:"POST", body:form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "批量导入失败");
      status(`批量导入完成：成功 ${data.imported}，失败 ${data.failed}`);
      refreshLibrary();
    } catch (error) { status(`批量导入失败：${error.message}`); }
  });

  $("assetAdvLoadVersions").addEventListener("click", async () => {
    const assetId = currentAssetId();
    if (!assetId) return status("版本：先高亮一个素材。");
    try {
      const response = await fetch(`/api/v1/library/assets/${assetId}/versions`);
      const versions = await response.json();
      if (!response.ok) throw new Error(versions.detail || "版本读取失败");
      $("assetAdvVersion").innerHTML = versions.map((item) => `<option value="${item.version}">v${item.version} · ${escapeHtml(item.kind)}</option>`).join("");
      status(`读取到 ${versions.length} 个版本。`);
    } catch (error) { status(`版本读取失败：${error.message}`); }
  });

  $("assetAdvActivateVersion").addEventListener("click", async () => {
    const assetId = currentAssetId();
    const version = Number($("assetAdvVersion").value);
    if (!assetId || !version) return status("请选择素材并读取版本。");
    try {
      const response = await fetch(`/api/v1/library/assets/${assetId}/versions/${version}/activate`, { method:"POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "版本激活失败");
      status(`已切换 ${assetId} → v${data.asset.active_version} · ${data.asset.width}×${data.asset.height}`);
      refreshLibrary();
    } catch (error) { status(`版本激活失败：${error.message}`); }
  });

  $("assetAdvBulkEdit").addEventListener("click", async () => {
    const assetIds = selectedAssetIds();
    if (!assetIds.length) return status("批量编辑：请勾选至少一个素材。");
    const operation = $("assetAdvBulkOp").value;
    const edit = { operation, activate:true, padding:Number($("assetAdvPad").value || 0) };
    if (operation === "resize") {
      edit.width = Number($("assetAdvW").value || 0) || null;
      edit.height = Number($("assetAdvH").value || 0) || null;
    }
    try {
      const response = await fetch("/api/v1/library/assets/bulk/edit", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({asset_ids:assetIds, edit, stop_on_error:false})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "批量编辑失败");
      status(`批量编辑完成：成功 ${data.succeeded}，失败 ${data.failed}。每个素材均创建独立版本。`);
      refreshLibrary();
    } catch (error) { status(`批量编辑失败：${error.message}`); }
  });

  $("assetAdvReparent").addEventListener("click", async () => {
    const parent = currentAssetId();
    if (!parent) return status("层级重挂：请先高亮父素材。");
    const children = selectedAssetIds().filter((id) => id !== parent);
    if (!children.length) return status("层级重挂：请批量勾选至少一个子素材。");
    try {
      const response = await fetch(`/api/v1/library/assets/${parent}/reparent`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({child_asset_ids:children, remove_existing_parents:$("assetAdvRemoveParents").checked})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "层级重挂失败");
      status(`层级更新完成：${children.length} 个子素材挂到 ${parent}；移除旧父级 ${data.removed_parent_links} 条。`);
    } catch (error) { status(`层级重挂失败：${error.message}`); }
  });

  $("assetAdvPreflight").addEventListener("click", async () => {
    const assetIds = selectedAssetIds();
    const root = $("assetAdvPreflightResult");
    if (!assetIds.length) { root.textContent = "请先批量勾选素材。"; return; }
    root.textContent = "检查中…";
    try {
      const response = await fetch("/api/v1/library/packs/preflight", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          asset_ids:assetIds,
          require_reviewed:$("assetAdvReviewed").checked,
          require_masks:$("assetAdvRequireMask").checked,
          require_alpha:$("assetAdvRequireAlpha").checked
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Preflight 失败");
      const lines = [`${data.valid ? "✓ 可导出" : "✕ 暂不建议导出"} · ${data.asset_count} assets · ${data.error_count} errors · ${data.warning_count} warnings`];
      (data.issues || []).slice(0, 20).forEach((issue) => lines.push(`${issue.level.toUpperCase()} ${issue.code}${issue.asset_id ? ` · ${issue.asset_id}` : ""}: ${issue.message}`));
      if ((data.issues || []).length > 20) lines.push(`…其余 ${(data.issues || []).length - 20} 条未显示`);
      root.textContent = lines.join("\n");
      root.className = `asset-workflow-preflight ${data.valid ? "asset-workflow-ok" : "asset-workflow-errors"}`;
    } catch (error) { root.textContent = `Preflight 失败：${error.message}`; }
  });

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
  }
})();
