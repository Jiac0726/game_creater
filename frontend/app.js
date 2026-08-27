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

let currentManifest = null;

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    health.textContent = `${data.mode} · API 正常`;
    health.classList.add("ok");
  } catch {
    health.textContent = "API 未连接";
    health.classList.add("bad");
  }
}

imageInput.addEventListener("change", () => {
  const file = imageInput.files?.[0];
  if (!file) return;
  fileName.textContent = file.name;
  const url = URL.createObjectURL(file);
  scenePreview.src = url;
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
  message.textContent = "正在生成检测结果、Mask、透明 PNG 和 scene.json…";

  try {
    const response = await fetch("/api/v1/scenes/analyze", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "分析失败");
    currentManifest = data;
    renderAssets(data);
    manifestLink.href = `/workspace/${data.scene_id}/scene.json`;
    manifestLink.classList.remove("hidden");
    message.textContent = `完成：${data.assets.length} 个素材 · 模式 ${data.mode}`;
  } catch (error) {
    message.textContent = `失败：${error.message}`;
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "AI 拆解";
  }
});

function renderAssets(manifest) {
  assetList.innerHTML = "";
  assetList.classList.remove("empty");
  assetPreview.classList.remove("empty");

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
