(() => {
  const byId = (id) => document.getElementById(id);
  const viewerStage = byId("viewerStage");
  const scenePreview = byId("scenePreview");
  const manifestLink = byId("manifestLink");
  const assetPreview = byId("assetPreview");
  const message = byId("message");

  const newBtn = byId("samNewBtn");
  const refineBtn = byId("samRefineBtn");
  const positiveBtn = byId("samPositiveBtn");
  const negativeBtn = byId("samNegativeBtn");
  const clearBtn = byId("samClearBtn");
  const runBtn = byId("samRunBtn");
  const cancelBtn = byId("samCancelBtn");
  const labelInput = byId("samLabelInput");
  const statusText = byId("samPointStatus");

  if (!viewerStage || !scenePreview || !newBtn) return;

  const canvas = document.createElement("canvas");
  canvas.id = "pointPromptCanvas";
  canvas.setAttribute("aria-label", "SAM2 正负点选择层");
  viewerStage.appendChild(canvas);
  const ctx = canvas.getContext("2d");

  let mode = null; // "new" | "refine"
  let positive = true;
  let targetAssetId = null;
  let points = [];

  newBtn.addEventListener("click", () => startMode("new"));
  refineBtn.addEventListener("click", () => startMode("refine"));
  positiveBtn.addEventListener("click", () => setPolarity(true));
  negativeBtn.addEventListener("click", () => setPolarity(false));
  clearBtn.addEventListener("click", clearPoints);
  cancelBtn.addEventListener("click", stopMode);
  runBtn.addEventListener("click", runSegmentation);

  canvas.addEventListener("click", (event) => addPoint(event, positive));
  canvas.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    addPoint(event, false);
  });

  scenePreview.addEventListener("load", syncCanvas);
  window.addEventListener("resize", syncCanvas);

  function startMode(nextMode) {
    const sceneId = currentSceneId();
    if (!sceneId) {
      tell("请先完成一次场景拆解，再使用 SAM 点选。", true);
      return;
    }

    targetAssetId = null;
    if (nextMode === "refine") {
      const selected = selectedAssetMeta();
      if (!selected?.id) {
        tell("请先在左侧选择一个要精修的素材。", true);
        return;
      }
      targetAssetId = selected.id;
      labelInput.value = selected.label || "asset";
    } else if (!labelInput.value.trim()) {
      labelInput.value = "new_asset";
    }

    mode = nextMode;
    points = [];
    positive = true;
    canvas.classList.add("active");
    syncCanvas();
    drawPoints();
    updateControls();
    tell(nextMode === "refine" ? `SAM 精修模式：${targetAssetId}` : "SAM 新建素材模式：点击目标内部添加绿色正点。", false);
  }

  function stopMode() {
    mode = null;
    targetAssetId = null;
    points = [];
    canvas.classList.remove("active");
    clearCanvas();
    updateControls();
    tell("已退出 SAM 点选模式。", false);
  }

  function setPolarity(value) {
    positive = value;
    updateControls();
  }

  function addPoint(event, isPositive) {
    if (!mode) return;
    const bounds = canvas.getBoundingClientRect();
    const displayX = event.clientX - bounds.left;
    const displayY = event.clientY - bounds.top;
    if (displayX < 0 || displayY < 0 || displayX > bounds.width || displayY > bounds.height) return;

    const imageWidth = scenePreview.naturalWidth || 0;
    const imageHeight = scenePreview.naturalHeight || 0;
    if (!imageWidth || !imageHeight) return;

    points.push({
      x: Math.max(0, Math.min(imageWidth - 1, Math.round(displayX * imageWidth / Math.max(1, bounds.width)))),
      y: Math.max(0, Math.min(imageHeight - 1, Math.round(displayY * imageHeight / Math.max(1, bounds.height)))),
      positive: Boolean(isPositive),
    });
    drawPoints();
    updateControls();
  }

  function clearPoints() {
    points = [];
    drawPoints();
    updateControls();
  }

  async function runSegmentation() {
    const sceneId = currentSceneId();
    if (!sceneId || !mode) return;
    if (!points.some((point) => point.positive)) {
      tell("至少需要一个绿色正点。", true);
      return;
    }

    const label = labelInput.value.trim() || selectedAssetMeta()?.label || "asset";
    const category = byId("assetCategoryInput")?.value || null;
    runBtn.disabled = true;
    runBtn.textContent = "SAM2 处理中…";
    tell(`正在用 ${points.length} 个提示点生成 Mask…`, false);

    try {
      const response = await fetch(`/api/v1/scenes/${sceneId}/assets/point-segment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          points,
          label,
          category,
          asset_id: mode === "refine" ? targetAssetId : null,
          use_asset_box: mode === "refine",
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "SAM 点选分割失败");

      const preferred = mode === "refine"
        ? targetAssetId
        : data.assets[data.assets.length - 1]?.id || null;
      if (typeof window.applyManifest === "function") {
        window.applyManifest(data, preferred);
      }
      mode = null;
      targetAssetId = null;
      points = [];
      canvas.classList.remove("active");
      clearCanvas();
      updateControls();
      tell(`SAM 点选完成：${label}`, false);
    } catch (error) {
      tell(`SAM 点选失败：${error.message}`, true);
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = "生成 / 更新 Mask";
    }
  }

  function currentSceneId() {
    const href = manifestLink?.getAttribute("href") || "";
    const match = href.match(/\/workspace\/([0-9a-f]{12})\/scene\.json/i);
    return match?.[1] || null;
  }

  function selectedAssetMeta() {
    const meta = assetPreview?.querySelector(".meta");
    if (!meta) return null;
    return {
      label: meta.querySelector("strong")?.textContent?.trim() || null,
      id: meta.querySelector("span")?.textContent?.trim() || null,
    };
  }

  function syncCanvas() {
    const width = Math.round(scenePreview.clientWidth || 0);
    const height = Math.round(scenePreview.clientHeight || 0);
    if (!width || !height) return;
    canvas.width = width;
    canvas.height = height;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    drawPoints();
  }

  function drawPoints() {
    clearCanvas();
    if (!mode || !points.length || !canvas.width || !canvas.height) return;
    const imageWidth = scenePreview.naturalWidth || 1;
    const imageHeight = scenePreview.naturalHeight || 1;
    const radius = Math.max(5, Math.min(canvas.width, canvas.height) / 90);

    points.forEach((point, index) => {
      const x = point.x * canvas.width / imageWidth;
      const y = point.y * canvas.height / imageHeight;
      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = point.positive ? "rgba(91, 235, 148, .92)" : "rgba(255, 103, 103, .92)";
      ctx.strokeStyle = "rgba(8, 13, 20, .95)";
      ctx.lineWidth = 2;
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#07101a";
      ctx.font = `bold ${Math.max(9, radius)}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(String(index + 1), x, y);
      ctx.restore();
    });
  }

  function clearCanvas() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  function updateControls() {
    const active = Boolean(mode);
    positiveBtn.disabled = !active;
    negativeBtn.disabled = !active;
    clearBtn.disabled = !active || !points.length;
    runBtn.disabled = !active || !points.some((point) => point.positive);
    cancelBtn.disabled = !active;
    positiveBtn.classList.toggle("active", active && positive);
    negativeBtn.classList.toggle("active", active && !positive);
    newBtn.classList.toggle("active", mode === "new");
    refineBtn.classList.toggle("active", mode === "refine");

    const positiveCount = points.filter((point) => point.positive).length;
    const negativeCount = points.length - positiveCount;
    statusText.textContent = active
      ? `${mode === "refine" ? "精修" : "新建"} · 正点 ${positiveCount} · 负点 ${negativeCount} · 右键也可直接加负点`
      : "未启用 · 正点用于包含目标，负点用于排除背景/邻近物体";
  }

  function tell(text, error) {
    if (message) message.textContent = text;
    if (statusText) statusText.classList.toggle("error", Boolean(error));
  }

  updateControls();
})();
