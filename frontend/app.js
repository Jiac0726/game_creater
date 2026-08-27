const $ = (id) => document.getElementById(id);

const imageInput = $("imageInput");
const promptInput = $("promptInput");
const analyzeBtn = $("analyzeBtn");
const scenePreview = $("scenePreview");
const assetList = $("assetList");
const assetPreview = $("assetPreview");
const message = $("message");
const health = $("health");
const fileName = $("fileName");
const viewerHint = $("viewerHint");
const manifestLink = $("manifestLink");
const archiveLink = $("archiveLink");

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
  manifestLink.classList.add("hidden");
  archiveLink.classList.add("hidden");
  fileName.textContent = file.name;

  if (localPreviewUrl) URL.revokeObjectURL(localPreviewUrl);
  localPreviewUrl = URL.createObjectURL(file);
  scenePreview.src = localPreviewUrl;
  scenePreview.style.display = "block";
  viewerHint.style.display = "none";
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

  try {
    const response = await fetch("/api/v1/scenes/analyze", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "分析失败");

    currentManifest = data;
    renderAssets(data);

    if (data.preview_image) {
      scenePreview.src = `/workspace/${data.scene_id}/${data.preview_image}?v=${Date.now()}`;
      scenePreview.style.display = "block";
      viewerHint.style.display = "none";
    }

    manifestLink.href = `/workspace/${data.scene_id}/scene.json`;
    manifestLink.classList.remove("hidden");
    archiveLink.href = `/api/v1/scenes/${data.scene_id}/export.zip`;
    archiveLink.classList.remove("hidden");

    message.textContent = `完成：${data.assets.length} 个素材 · 已生成 Overlay · 模式 ${data.mode}`;
  } catch (error) {
    message.textContent = `失败：${error.message}`;
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "AI 拆解";
    loadHealth();
  }
});

function renderAssets(manifest, selectedAssetId = null) {
  assetList.innerHTML = "";
  assetList.classList.remove("empty");
  assetPreview.classList.remove("empty");

  if (!manifest.assets.length) {
    assetList.classList.add("empty");
    assetList.textContent = "没有检测到匹配素材，可降低阈值或调整关键词。";
    assetPreview.classList.add("empty");
    assetPreview.textContent = "暂无素材";
    return;
  }

  const preferredId = selectedAssetId || manifest.assets[0].id;

  manifest.assets.forEach((asset) => {
    const button = document.createElement("button");
    button.className = "asset-row";
    button.innerHTML = `
      <span>${escapeHtml(asset.label)}</span>
      <small>${escapeHtml(asset.category || "uncategorized")} · ${Math.round(asset.confidence * 100)}%</small>
    `;
    button.addEventListener("click", () => {
      document.querySelectorAll(".asset-row").forEach((el) => el.classList.remove("selected"));
      button.classList.add("selected");
      showAsset(manifest, asset);
    });
    assetList.appendChild(button);

    if (asset.id === preferredId) {
      button.classList.add("selected");
      showAsset(manifest, asset);
    }
  });
}

function showAsset(manifest, asset) {
  const base = `/workspace/${manifest.scene_id}/`;
  const categories = [...ASSET_CATEGORIES];
  if (asset.category && !categories.includes(asset.category)) categories.push(asset.category);

  assetPreview.innerHTML = `
    <img src="${base}${asset.image}" alt="${escapeHtml(asset.label)}" />
    <div class="meta">
      <strong>${escapeHtml(asset.label)}</strong>
      <span>${escapeHtml(asset.id)}</span>
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
    <div class="preview-actions">
      <a href="${base}${asset.image}" download>下载透明 PNG</a>
      <a href="${base}${asset.mask}" download>下载 Mask</a>
    </div>
  `;

  $("saveAssetBtn").addEventListener("click", () => saveAssetMetadata(manifest, asset));
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

loadHealth();
