const $ = (id) => document.getElementById(id);

const imageInput = $("imageInput");
const promptInput = $("promptInput");
const analyzeBtn = $("analyzeBtn");
const scenePreview = $("scenePreview");
const viewerStage = $("viewerStage");
const selectionCanvas = $("selectionCanvas");
const selectionCtx = selectionCanvas.getContext("2d");
const assetList = $("assetList");
const assetPreview = $("assetPreview");
const message = $("message");
const health = $("health");
const fileName = $("fileName");
const viewerHint = $("viewerHint");
const manifestLink = $("manifestLink");
const archiveLink = $("archiveLink");
const selectionBar = $("selectionBar");
const selectionCount = $("selectionCount");
const mergeSelectedBtn = $("mergeSelectedBtn");
const globalSearch = $("globalSearch");
const assetCount = $("assetCount");
const queueCount = $("queueCount");
const taskName = $("taskName");
const taskDetail = $("taskDetail");
const pipelinePercent = $("pipelinePercent");
const pipelineBar = $("pipelineBar");
const pipelineState = $("pipelineState");
const librarySearch = $("librarySearch");
const libraryFootCount = $("libraryFootCount");
const importToggle = $("importToggle");
const importPopover = $("importPopover");
const importClose = $("importClose");
const miniQueueCount = $("miniQueueCount");
const miniTaskName = $("miniTaskName");
const miniTaskDetail = $("miniTaskDetail");
const miniPipelinePercent = $("miniPipelinePercent");
const appRoot = document.querySelector(".app-root");
const assetWorkspace = $("assetWorkspace");
const semanticPanel = $("semanticPanel");
const exportDock = $("exportDock");
const currentViewLabel = $("currentViewLabel");

const ASSET_CATEGORIES = [
  "uncategorized",
  "vegetation",
  "terrain",
  "structure",
  "prop",
  "building",
  "vehicle",
  "creature",
  "effect",
  "material",
];

let currentManifest = null;
let localPreviewUrl = null;
let currentSplitRect = null;
let dragStart = null;
const selectedAssetIds = new Set();
let pipelineTimer = null;
let assetSearchQuery = "";

function setPipelineProgress(percent, state) {
  const safePercent = Math.max(0, Math.min(100, Math.round(percent)));
  if (pipelinePercent) pipelinePercent.textContent = `${safePercent}%`;
  if (pipelineBar) pipelineBar.style.width = `${safePercent}%`;
  if (pipelineState) pipelineState.textContent = state;
  if (miniPipelinePercent) miniPipelinePercent.textContent = `${safePercent}%`;
}

function resetPipelineStages() {
  document.querySelectorAll("[data-pipeline-stage]").forEach((stage) => {
    stage.classList.remove("running", "done", "failed");
  });
  document.querySelectorAll("[data-mini-stage]").forEach((stage) => {
    stage.classList.remove("running", "done", "failed");
  });
}

function setStageState(stageName, state) {
  const pipelineStage = document.querySelector(`[data-pipeline-stage="${stageName}"]`);
  const miniStage = document.querySelector(`[data-mini-stage="${stageName}"]`);
  [pipelineStage, miniStage].forEach((stage) => {
    if (!stage) return;
    stage.classList.remove("running", "done", "failed");
    if (state) stage.classList.add(state);
  });
}

function startPipeline(file, prompts) {
  window.clearInterval(pipelineTimer);
  resetPipelineStages();
  if (queueCount) queueCount.textContent = "1";
  if (miniQueueCount) miniQueueCount.textContent = "1";
  if (taskName) taskName.textContent = file?.name || "场景拆解任务";
  if (taskDetail) taskDetail.textContent = prompts || "自动识别游戏素材";
  if (miniTaskName) miniTaskName.textContent = file?.name || "场景拆解任务";
  if (miniTaskDetail) miniTaskDetail.textContent = prompts || "自动识别游戏素材";

  const stageNames = ["detection", "segmentation", "refine"];
  let stageIndex = 0;
  let progress = 12;
  setStageState(stageNames[0], "running");
  setPipelineProgress(progress, "PROCESSING");

  pipelineTimer = window.setInterval(() => {
    setStageState(stageNames[stageIndex], "done");
    stageIndex = Math.min(stageIndex + 1, stageNames.length - 1);
    setStageState(stageNames[stageIndex], "running");
    progress = Math.min(84, progress + 24);
    setPipelineProgress(progress, "PROCESSING");
    if (progress >= 84) window.clearInterval(pipelineTimer);
  }, 900);
}

function finishPipeline(assetTotal) {
  window.clearInterval(pipelineTimer);
  resetPipelineStages();
  document.querySelectorAll("[data-pipeline-stage]").forEach((stage) => stage.classList.add("done"));
  document.querySelectorAll("[data-mini-stage]").forEach((stage) => stage.classList.add("done"));
  if (taskDetail) taskDetail.textContent = `完成 ${assetTotal} 个素材 · 可导出至 Godot / Unity`;
  if (miniTaskDetail) miniTaskDetail.textContent = `完成 ${assetTotal} 个素材 · 可导出`;
  setPipelineProgress(100, "COMPLETE");
}

function failPipeline(detail) {
  window.clearInterval(pipelineTimer);
  const running = document.querySelector("[data-pipeline-stage].running") || document.querySelector("[data-pipeline-stage]");
  running?.classList.remove("running");
  running?.classList.add("failed");
  document.querySelector("[data-mini-stage].running")?.classList.replace("running", "failed");
  if (taskDetail) taskDetail.textContent = detail || "任务处理失败";
  if (miniTaskDetail) miniTaskDetail.textContent = detail || "任务处理失败";
  setPipelineProgress(Number.parseInt(pipelinePercent?.textContent || "0", 10), "FAILED");
}

function filterAssetRows() {
  const query = assetSearchQuery.trim().toLocaleLowerCase();
  document.querySelectorAll(".asset-row-shell").forEach((row) => {
    row.hidden = Boolean(query) && !row.textContent.toLocaleLowerCase().includes(query);
  });
}

function updateAssetSearch(value, source) {
  assetSearchQuery = value;
  if (source !== globalSearch && globalSearch) globalSearch.value = value;
  if (source !== librarySearch && librarySearch) librarySearch.value = value;
  filterAssetRows();
}

globalSearch?.addEventListener("input", () => updateAssetSearch(globalSearch.value, globalSearch));
librarySearch?.addEventListener("input", () => updateAssetSearch(librarySearch.value, librarySearch));
window.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k") {
    event.preventDefault();
    globalSearch?.focus();
    globalSearch?.select();
  }
});

const VIEW_LABELS = {
  assets: "素材库",
  scene: "场景工作台",
  semantic: "语义联想",
  workflow: "工作流",
  export: "导出与交付",
};

function activateView(viewName) {
  const nextView = VIEW_LABELS[viewName] ? viewName : "assets";
  if (appRoot) appRoot.dataset.currentView = nextView;
  document.querySelectorAll("[data-view]").forEach((panel) => {
    const supportedViews = panel.dataset.view.split(",");
    panel.classList.toggle("view-hidden", !supportedViews.includes(nextView));
  });
  document.querySelectorAll(".rail-item[data-view-name]").forEach((item) => {
    item.classList.toggle("active", item.dataset.viewName === nextView);
  });
  assetWorkspace?.classList.toggle("scene-focus", nextView === "scene");
  if (nextView === "semantic" && semanticPanel) semanticPanel.open = true;
  if (currentViewLabel) currentViewLabel.textContent = VIEW_LABELS[nextView];
  window.requestAnimationFrame(() => {
    syncSelectionCanvas();
    drawCurrentSelection();
  });
}

document.querySelectorAll(".rail-item[data-view-name]").forEach((item) => {
  item.addEventListener("click", () => activateView(item.dataset.viewName));
});

document.querySelectorAll("[data-view-jump]").forEach((item) => {
  item.addEventListener("click", (event) => {
    event.preventDefault();
    activateView(item.dataset.viewJump);
  });
});

document.querySelectorAll(".library-tabs button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".library-tabs button").forEach((candidate) => candidate.classList.remove("active"));
    button.classList.add("active");
  });
});

importToggle?.addEventListener("click", () => importPopover?.classList.toggle("hidden"));
importClose?.addEventListener("click", () => importPopover?.classList.add("hidden"));
window.addEventListener("keydown", (event) => {
  if (event.key === "Escape") importPopover?.classList.add("hidden");
});

async function loadHealth() {
  health.classList.remove("ok", "bad");
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    const model = data.model || {};

    if (!model.ready) {
      const missing = Object.entries(model.checks || {})
        .filter(([, ready]) => !ready)
        .map(([name]) => name);
      health.textContent = `${data.mode} · 模型未就绪`;
      health.title = missing.length ? `缺少：${missing.join(", ")}` : "模型未就绪";
      health.classList.add("bad");
      analyzeBtn.disabled = true;
      message.textContent = `模型环境未就绪${missing.length ? `：${missing.join(", ")}` : ""}`;
      return;
    }

    const device = model.device ? ` · ${model.device}` : "";
    const loaded = model.loaded === false ? " · 待首次加载" : "";
    health.textContent = `${data.mode}${device}${loaded}`;
    health.title = "推理后端已就绪";
    health.classList.add("ok");
    analyzeBtn.disabled = false;
  } catch {
    health.textContent = "API 未连接";
    health.classList.add("bad");
    analyzeBtn.disabled = true;
  }
}

imageInput.addEventListener("change", () => {
  const file = imageInput.files?.[0];
  if (!file) return;

  currentManifest = null;
  currentSplitRect = null;
  selectedAssetIds.clear();
  updateSelectionBar();
  clearSelectionCanvas();
  manifestLink.classList.add("hidden");
  archiveLink.classList.add("hidden");
  $("godotLink")?.classList.add("hidden");
  $("unityLink")?.classList.add("hidden");
  exportDock?.classList.remove("ready");
  fileName.textContent = file.name;
  if (taskName) taskName.textContent = file.name;
  if (taskDetail) taskDetail.textContent = "已载入场景，等待启动 AI 拆图";
  if (miniTaskName) miniTaskName.textContent = file.name;
  if (miniTaskDetail) miniTaskDetail.textContent = "场景已载入，等待启动";

  if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
  localPreviewUrl = URL.createObjectURL(file);
  scenePreview.src = localPreviewUrl;
  scenePreview.style.display = "block";
  viewerStage.style.display = "inline-block";
  viewerHint.style.display = "none";
});

scenePreview.addEventListener("load", () => {
  syncSelectionCanvas();
  drawCurrentSelection();
});
window.addEventListener("resize", () => {
  syncSelectionCanvas();
  drawCurrentSelection();
});

selectionCanvas.addEventListener("mousedown", (event) => {
  if (!currentManifest) return;
  dragStart = canvasPoint(event);
  currentSplitRect = null;
  clearSelectionCanvas();
});

selectionCanvas.addEventListener("mousemove", (event) => {
  if (!dragStart || !currentManifest) return;
  const point = canvasPoint(event);
  drawCanvasRectangle(dragStart, point);
});

window.addEventListener("mouseup", (event) => {
  if (!dragStart || !currentManifest) return;
  const end = canvasPoint(event);
  const minX = Math.max(0, Math.min(dragStart.x, end.x));
  const minY = Math.max(0, Math.min(dragStart.y, end.y));
  const maxX = Math.min(selectionCanvas.width, Math.max(dragStart.x, end.x));
  const maxY = Math.min(selectionCanvas.height, Math.max(dragStart.y, end.y));
  dragStart = null;

  if (maxX - minX < 3 || maxY - minY < 3) {
    currentSplitRect = null;
    clearSelectionCanvas();
    return;
  }

  const scaleX = currentManifest.width / Math.max(1, selectionCanvas.width);
  const scaleY = currentManifest.height / Math.max(1, selectionCanvas.height);
  currentSplitRect = {
    x1: Math.max(0, Math.floor(minX * scaleX)),
    y1: Math.max(0, Math.floor(minY * scaleY)),
    x2: Math.min(currentManifest.width, Math.ceil(maxX * scaleX)),
    y2: Math.min(currentManifest.height, Math.ceil(maxY * scaleY)),
  };

  drawCurrentSelection();
  fillSplitInputs(currentSplitRect);
  message.textContent = `已选择拆分矩形：(${currentSplitRect.x1}, ${currentSplitRect.y1}) → (${currentSplitRect.x2}, ${currentSplitRect.y2})`;
});

analyzeBtn.addEventListener("click", async () => {
  const file = imageInput.files?.[0];
  if (!file) {
    message.textContent = "请先选择一张场景图片。";
    return;
  }

  const form = new FormData();
  form.append("image", file);
  form.append("prompts", promptInput.value);

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "拆解中…";
  message.textContent = "正在生成检测结果、Mask、透明 PNG、Overlay 和 scene.json…";
  startPipeline(file, promptInput.value);
  importPopover?.classList.add("hidden");

  try {
    const response = await fetch("/api/v1/scenes/analyze", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "分析失败");

    selectedAssetIds.clear();
    currentSplitRect = null;
    applyManifest(data);
    message.textContent = `完成：${data.assets.length} 个素材 · 已生成 Overlay · 模式 ${data.mode}`;
    finishPipeline(data.assets.length);
  } catch (error) {
    message.textContent = `失败：${error.message}`;
    failPipeline(error.message);
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "✦ 开始 AI 拆图";
    loadHealth();
  }
});

mergeSelectedBtn.addEventListener("click", async () => {
  if (!currentManifest || selectedAssetIds.size < 2) return;

  const ids = [...selectedAssetIds];
  const selected = currentManifest.assets.filter((asset) => selectedAssetIds.has(asset.id));
  const defaultLabel = `${selected[0]?.label || "asset"}_merged`;
  const label = window.prompt("合并后的素材名称", defaultLabel);
  if (label === null) return;
  if (!label.trim()) {
    message.textContent = "合并后的名称不能为空。";
    return;
  }

  mergeSelectedBtn.disabled = true;
  message.textContent = `正在合并 ${ids.length} 个素材…`;
  try {
    const response = await fetch(`/api/v1/scenes/${currentManifest.scene_id}/assets/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_ids: ids, label: label.trim(), keep_sources: false }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "合并失败");

    selectedAssetIds.clear();
    currentSplitRect = null;
    const preferred = data.assets[data.assets.length - 1]?.id || null;
    applyManifest(data, preferred);
    message.textContent = `已合并为：${label.trim()}`;
  } catch (error) {
    message.textContent = `合并失败：${error.message}`;
  } finally {
    updateSelectionBar();
  }
});

function renderAssets(manifest, selectedAssetId = null) {
  assetList.innerHTML = "";
  assetList.classList.remove("empty");
  assetPreview.classList.remove("empty");
  updateSelectionBar();
  if (assetCount) assetCount.textContent = `${manifest.assets.length} 项`;
  if (libraryFootCount) libraryFootCount.textContent = String(manifest.assets.length);

  if (!manifest.assets.length) {
    assetList.classList.add("empty");
    assetList.textContent = "当前场景没有素材。";
    assetPreview.classList.add("empty");
    assetPreview.textContent = "暂无素材";
    return;
  }

  const preferredId = selectedAssetId || manifest.assets[0].id;
  const base = `/workspace/${manifest.scene_id}/`;

  manifest.assets.forEach((asset) => {
    const row = document.createElement("div");
    row.className = "asset-row-shell";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "asset-select";
    checkbox.checked = selectedAssetIds.has(asset.id);
    checkbox.title = "选择后可批量合并";
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selectedAssetIds.add(asset.id);
      else selectedAssetIds.delete(asset.id);
      updateSelectionBar();
    });

    const button = document.createElement("button");
    button.className = "asset-row";
    const score = Math.round((asset.asset_score || 0) * 100);
    button.innerHTML = `
      <img class="asset-thumb" src="${base}${asset.image}?v=${Date.now()}" alt="" />
      <span>${escapeHtml(asset.label)}</span>
      <small>S${score}</small>
    `;
    button.addEventListener("click", () => {
      document.querySelectorAll(".asset-row").forEach((el) => el.classList.remove("selected"));
      button.classList.add("selected");
      showAsset(manifest, asset);
    });

    row.append(checkbox, button);
    assetList.appendChild(row);

    if (asset.id === preferredId) {
      button.classList.add("selected");
      showAsset(manifest, asset);
    }
  });
  filterAssetRows();
}

function showAsset(manifest, asset) {
  const base = `/workspace/${manifest.scene_id}/`;
  const categories = [...ASSET_CATEGORIES];
  if (asset.category && !categories.includes(asset.category)) categories.push(asset.category);
  const midY = Math.max(asset.bbox.y1 + 1, Math.floor((asset.bbox.y1 + asset.bbox.y2) / 2));
  const splitRect = currentSplitRect || {
    x1: asset.bbox.x1,
    y1: asset.bbox.y1,
    x2: asset.bbox.x2,
    y2: midY,
  };

  assetPreview.innerHTML = `
    <img src="${base}${asset.image}?v=${Date.now()}" alt="${escapeHtml(asset.label)}" />
    <div class="meta">
      <strong>${escapeHtml(asset.label)}</strong>
      <span>${escapeHtml(asset.id)}</span>
      <span>Asset Score: ${Math.round((asset.asset_score || 0) * 100)} / 100</span>
      <span>检测置信度: ${Math.round((asset.confidence || 0) * 100)}%</span>
      <span>bbox: ${asset.bbox.x1}, ${asset.bbox.y1}, ${asset.bbox.x2}, ${asset.bbox.y2}</span>
    </div>
    <div class="asset-editor">
      <label>
        <span>名称</span>
        <input id="assetLabelInput" value="${escapeAttribute(asset.label)}" />
      </label>
      <label>
        <span>分类</span>
        <select id="assetCategoryInput">
          ${categories.map((category) => `<option value="${escapeAttribute(category)}" ${category === asset.category ? "selected" : ""}>${escapeHtml(category)}</option>`).join("")}
        </select>
      </label>
      <label>
        <span>备注</span>
        <textarea id="assetNotesInput" rows="3" placeholder="例如：主场景大树、可交互道具…">${escapeHtml(asset.notes || "")}</textarea>
      </label>
      <button id="saveAssetBtn" class="save-asset-btn">保存素材信息</button>
    </div>

    <div class="tool-section">
      <strong>矩形拆分 Mask</strong>
      <small>可直接在中间 Scene Viewer 上拖拽；矩形内作为 Part A，其余 Mask 作为 Part B。</small>
      <div class="rect-grid">
        <label>X1<input id="splitX1" type="number" value="${splitRect.x1}" /></label>
        <label>Y1<input id="splitY1" type="number" value="${splitRect.y1}" /></label>
        <label>X2<input id="splitX2" type="number" value="${splitRect.x2}" /></label>
        <label>Y2<input id="splitY2" type="number" value="${splitRect.y2}" /></label>
      </div>
      <div class="split-labels">
        <input id="insideLabel" placeholder="Part A 名称（可选）" />
        <input id="outsideLabel" placeholder="Part B 名称（可选）" />
      </div>
      <button id="splitAssetBtn" class="secondary-btn">按矩形拆分</button>
    </div>

    <div class="preview-actions">
      <a href="${base}${asset.image}" download>下载透明 PNG</a>
      <a href="${base}${asset.mask}" download>下载 Mask</a>
    </div>
    <button id="deleteAssetBtn" class="danger-btn">删除这个素材</button>
  `;

  $("saveAssetBtn").addEventListener("click", () => saveAssetMetadata(manifest, asset));
  $("deleteAssetBtn").addEventListener("click", () => deleteAsset(manifest, asset));
  $("splitAssetBtn").addEventListener("click", () => splitAsset(manifest, asset));
}

async function saveAssetMetadata(manifest, asset) {
  const saveButton = $("saveAssetBtn");
  const payload = {
    label: $("assetLabelInput").value.trim(),
    category: $("assetCategoryInput").value,
    notes: $("assetNotesInput").value.trim() || null,
  };

  if (!payload.label) {
    message.textContent = "素材名称不能为空。";
    return;
  }

  saveButton.disabled = true;
  saveButton.textContent = "保存中…";

  try {
    const response = await fetch(`/api/v1/scenes/${manifest.scene_id}/assets/${asset.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const updated = await response.json();
    if (!response.ok) throw new Error(updated.detail || "保存失败");

    const index = manifest.assets.findIndex((item) => item.id === asset.id);
    if (index >= 0) manifest.assets[index] = updated;
    currentManifest = manifest;
    renderAssets(manifest, updated.id);
    message.textContent = `已保存：${updated.label} · ${updated.category}`;
  } catch (error) {
    message.textContent = `保存失败：${error.message}`;
    saveButton.disabled = false;
    saveButton.textContent = "保存素材信息";
  }
}

async function deleteAsset(manifest, asset) {
  if (!window.confirm(`确定删除素材“${asset.label}”吗？`)) return;
  message.textContent = `正在删除：${asset.label}…`;

  try {
    const response = await fetch(`/api/v1/scenes/${manifest.scene_id}/assets/${asset.id}`, {
      method: "DELETE",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "删除失败");

    selectedAssetIds.delete(asset.id);
    currentSplitRect = null;
    applyManifest(data);
    message.textContent = `已删除：${asset.label}`;
  } catch (error) {
    message.textContent = `删除失败：${error.message}`;
  }
}

async function splitAsset(manifest, asset) {
  const rect = {
    x1: Number($("splitX1").value),
    y1: Number($("splitY1").value),
    x2: Number($("splitX2").value),
    y2: Number($("splitY2").value),
  };
  const payload = {
    rect,
    inside_label: $("insideLabel").value.trim() || null,
    outside_label: $("outsideLabel").value.trim() || null,
  };

  if (Object.values(rect).some((value) => !Number.isFinite(value))) {
    message.textContent = "拆分坐标必须是有效数字。";
    return;
  }

  const button = $("splitAssetBtn");
  button.disabled = true;
  button.textContent = "拆分中…";
  message.textContent = `正在拆分：${asset.label}…`;

  try {
    const response = await fetch(`/api/v1/scenes/${manifest.scene_id}/assets/${asset.id}/split`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "拆分失败");

    selectedAssetIds.delete(asset.id);
    currentSplitRect = null;
    const preferred = data.assets[data.assets.length - 2]?.id || null;
    applyManifest(data, preferred);
    message.textContent = `已拆分：${asset.label} → 2 个素材`;
  } catch (error) {
    message.textContent = `拆分失败：${error.message}`;
    button.disabled = false;
    button.textContent = "按矩形拆分";
  }
}

function applyManifest(manifest, selectedAssetId = null) {
  currentManifest = manifest;
  const validIds = new Set(manifest.assets.map((asset) => asset.id));
  [...selectedAssetIds].forEach((id) => {
    if (!validIds.has(id)) selectedAssetIds.delete(id);
  });

  renderAssets(manifest, selectedAssetId);
  refreshOverlay(manifest);

  manifestLink.href = `/workspace/${manifest.scene_id}/scene.json?v=${Date.now()}`;
  manifestLink.classList.remove("hidden");
  archiveLink.href = `/api/v1/scenes/${manifest.scene_id}/export.zip`;
  archiveLink.classList.remove("hidden");
  exportDock?.classList.add("ready");
}

function refreshOverlay(manifest) {
  if (!manifest?.preview_image) return;
  scenePreview.src = `/workspace/${manifest.scene_id}/${manifest.preview_image}?v=${Date.now()}`;
  scenePreview.style.display = "block";
  viewerStage.style.display = "inline-block";
  viewerHint.style.display = "none";
}

function updateSelectionBar() {
  const hasScene = Boolean(currentManifest && currentManifest.assets.length);
  selectionBar.classList.toggle("hidden", !hasScene);
  selectionCount.textContent = `已选 ${selectedAssetIds.size}`;
  mergeSelectedBtn.disabled = selectedAssetIds.size < 2;
}

function syncSelectionCanvas() {
  const width = Math.round(scenePreview.clientWidth || 0);
  const height = Math.round(scenePreview.clientHeight || 0);
  if (!width || !height) return;
  selectionCanvas.width = width;
  selectionCanvas.height = height;
  selectionCanvas.style.width = `${width}px`;
  selectionCanvas.style.height = `${height}px`;
}

function canvasPoint(event) {
  const bounds = selectionCanvas.getBoundingClientRect();
  const scaleX = selectionCanvas.width / Math.max(1, bounds.width);
  const scaleY = selectionCanvas.height / Math.max(1, bounds.height);
  return {
    x: Math.max(0, Math.min(selectionCanvas.width, (event.clientX - bounds.left) * scaleX)),
    y: Math.max(0, Math.min(selectionCanvas.height, (event.clientY - bounds.top) * scaleY)),
  };
}

function drawCanvasRectangle(start, end) {
  clearSelectionCanvas();
  selectionCtx.save();
  selectionCtx.strokeStyle = "#7cc4ff";
  selectionCtx.fillStyle = "rgba(124, 196, 255, 0.12)";
  selectionCtx.lineWidth = 2;
  selectionCtx.setLineDash([6, 4]);
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  const width = Math.abs(end.x - start.x);
  const height = Math.abs(end.y - start.y);
  selectionCtx.fillRect(x, y, width, height);
  selectionCtx.strokeRect(x, y, width, height);
  selectionCtx.restore();
}

function drawCurrentSelection() {
  clearSelectionCanvas();
  if (!currentSplitRect || !currentManifest || !selectionCanvas.width || !selectionCanvas.height) return;
  const scaleX = selectionCanvas.width / currentManifest.width;
  const scaleY = selectionCanvas.height / currentManifest.height;
  drawCanvasRectangle(
    { x: currentSplitRect.x1 * scaleX, y: currentSplitRect.y1 * scaleY },
    { x: currentSplitRect.x2 * scaleX, y: currentSplitRect.y2 * scaleY },
  );
}

function clearSelectionCanvas() {
  selectionCtx.clearRect(0, 0, selectionCanvas.width, selectionCanvas.height);
}

function fillSplitInputs(rect) {
  if (!rect || !$("splitX1")) return;
  $("splitX1").value = rect.x1;
  $("splitY1").value = rect.y1;
  $("splitX2").value = rect.x2;
  $("splitY2").value = rect.y2;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[char]);
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, "&#096;");
}

activateView(appRoot?.dataset.currentView || "assets");
loadHealth();
