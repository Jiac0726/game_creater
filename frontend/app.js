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

function renderAssets(manifest) {
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

  manifest.assets.forEach((asset, index) => {
    const button = document.createElement("button");
    button.className = "asset-row";
    button.innerHTML = `<span>${asset.label}</span><small>${Math.round(asset.confidence * 100)}%</small>`;
    button.addEventListener("click", () => {
      document.querySelectorAll(".asset-row").forEach((el) => el.classList.remove("selected"));
      button.classList.add("selected");
      showAsset(manifest, asset);
    });
    assetList.appendChild(button);
    if (index === 0) {
      button.classList.add("selected");
      showAsset(manifest, asset);
    }
  });
}

function showAsset(manifest, asset) {
  const base = `/workspace/${manifest.scene_id}/`;
  assetPreview.innerHTML = `
    <img src="${base}${asset.image}" alt="${asset.label}" />
    <div class="meta">
      <strong>${asset.label}</strong>
      <span>${asset.id}</span>
      <span>bbox: ${asset.bbox.x1}, ${asset.bbox.y1}, ${asset.bbox.x2}, ${asset.bbox.y2}</span>
    </div>
    <div class="preview-actions">
      <a href="${base}${asset.image}" download>下载透明 PNG</a>
      <a href="${base}${asset.mask}" download>下载 Mask</a>
    </div>
  `;
}

loadHealth();
