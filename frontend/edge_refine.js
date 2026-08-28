(() => {
  const byId = (id) => document.getElementById(id);
  const runButton = byId("edgeRefineBtn");
  const radiusInput = byId("edgeRadius");
  const status = byId("edgeRefineStatus");
  const manifestLink = byId("manifestLink");
  const assetPreview = byId("assetPreview");
  const globalMessage = byId("message");

  if (!runButton || !radiusInput || !status) return;

  let ready = false;

  async function loadStatus() {
    ready = false;
    runButton.disabled = true;
    try {
      const response = await fetch("/api/v1/edge-refiner/status");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "状态读取失败");
      if (!data.enabled) {
        status.textContent = "未启用";
        status.title = "设置 GAME_CREATER_EDGE_REFINER=birefnet_sidecar 后启用";
        return;
      }
      if (!data.ready) {
        status.textContent = "Sidecar 未连接";
        status.title = data.error || "请先启动 BiRefNet sidecar";
        return;
      }
      ready = true;
      runButton.disabled = false;
      const model = data.model_id ? data.model_id.split("/").pop() : "BiRefNet";
      status.textContent = `${model} · ${data.loaded ? "已加载" : "待首次加载"}`;
      status.title = data.revision || "BiRefNet sidecar ready";
    } catch (error) {
      status.textContent = "状态不可用";
      status.title = error.message;
    }
  }

  function currentSceneId() {
    const href = manifestLink?.getAttribute("href") || "";
    const match = href.match(/\/workspace\/([0-9a-f]{12})\/scene\.json/);
    return match?.[1] || null;
  }

  function currentAssetId() {
    return assetPreview?.querySelector(".meta span")?.textContent?.trim() || null;
  }

  runButton.addEventListener("click", async () => {
    if (!ready) {
      if (globalMessage) globalMessage.textContent = "BiRefNet sidecar 尚未就绪。";
      return;
    }
    const sceneId = currentSceneId();
    const assetId = currentAssetId();
    if (!sceneId || !assetId) {
      if (globalMessage) globalMessage.textContent = "请先完成场景拆解，并在左侧选择一个素材。";
      return;
    }

    const radius = Math.max(1, Math.min(24, Number(radiusInput.value || 6)));
    radiusInput.value = String(radius);
    runButton.disabled = true;
    runButton.textContent = "精修中…";
    if (globalMessage) globalMessage.textContent = `正在用 BiRefNet 精修 ${assetId} 的边缘 Alpha…`;

    try {
      const response = await fetch(`/api/v1/scenes/${sceneId}/assets/${assetId}/refine-edge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ radius }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "边缘精修失败");

      const previewImage = assetPreview?.querySelector("img");
      if (previewImage && data.image) {
        previewImage.src = `/workspace/${sceneId}/${data.image}?v=${Date.now()}`;
      }
      if (globalMessage) globalMessage.textContent = `边缘精修完成：${data.label} · radius ${radius}`;
      await loadStatus();
    } catch (error) {
      if (globalMessage) globalMessage.textContent = `边缘精修失败：${error.message}`;
      runButton.disabled = !ready;
    } finally {
      runButton.textContent = "BiRefNet 精修当前素材";
      if (ready) runButton.disabled = false;
    }
  });

  loadStatus();
})();
