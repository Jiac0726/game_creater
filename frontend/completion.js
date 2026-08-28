(() => {
  const edgePanel = document.querySelector(".edge-panel");
  const manifestLink = document.getElementById("manifestLink");
  if (!edgePanel || !manifestLink) return;

  const style = document.createElement("style");
  style.textContent = `
    .completion-panel { padding:18px; }
    .completion-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; }
    .completion-head h2 { margin:0 0 5px; }
    .completion-head p { margin:0; opacity:.72; }
    .completion-controls { display:grid; grid-template-columns:170px 1fr auto; gap:10px; margin-top:14px; align-items:end; }
    .completion-controls label { display:flex; flex-direction:column; gap:5px; font-size:12px; }
    .completion-result { margin-top:12px; display:flex; gap:12px; flex-wrap:wrap; font-size:13px; }
    .completion-result.hidden { display:none; }
    @media (max-width:900px) { .completion-controls { grid-template-columns:1fr; } }
  `;
  document.head.appendChild(style);

  const panel = document.createElement("section");
  panel.className = "card completion-panel";
  panel.innerHTML = `
    <div class="completion-head">
      <div>
        <h2>局部补全 / Occlusion Completion</h2>
        <p>选择一个素材，在 Scene Viewer 拖出要补全的矩形；原素材不覆盖，补全结果单独保存并可重新分割。</p>
      </div>
      <span id="completionStatus">检查中…</span>
    </div>
    <div class="completion-controls">
      <label><span>补全 Provider</span><select id="completionProvider"><option value="mock">mock</option></select></label>
      <label><span>补全提示词（可选）</span><input id="completionPrompt" placeholder="例如：complete the hidden lower half of the wooden barrel" /></label>
      <button id="completionRunBtn">使用当前矩形补全</button>
    </div>
    <div id="completionResult" class="completion-result hidden"></div>
  `;
  edgePanel.insertAdjacentElement("afterend", panel);

  const providerSelect = document.getElementById("completionProvider");
  const status = document.getElementById("completionStatus");
  const runBtn = document.getElementById("completionRunBtn");
  const resultBox = document.getElementById("completionResult");

  async function loadProviders() {
    try {
      const response = await fetch("/api/v1/completion/providers");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "completion provider check failed");
      providerSelect.innerHTML = "";
      let preferred = "mock";
      for (const provider of data.providers || []) {
        const option = document.createElement("option");
        option.value = provider.id;
        option.disabled = !provider.ready;
        const model = typeof provider.model === "string" ? provider.model : provider.model?.name;
        option.textContent = `${provider.id}${model ? ` · ${model}` : ""}${provider.ready ? "" : " · 未启动"}`;
        providerSelect.appendChild(option);
        if (provider.id === "iopaint" && provider.ready) preferred = "iopaint";
      }
      providerSelect.value = preferred;
      status.textContent = preferred === "iopaint" ? "IOPaint / LaMa 已连接" : "Mock · 可验证流程";
    } catch (error) {
      status.textContent = `Provider 检查失败：${error.message}`;
    }
  }

  runBtn.addEventListener("click", async () => {
    const sceneId = currentSceneId();
    if (!sceneId) {
      status.textContent = "请先完成场景拆解";
      return;
    }
    const rect = currentRect();
    if (!rect) {
      status.textContent = "请先选择素材，并在 Scene Viewer 拖出补全矩形";
      return;
    }

    runBtn.disabled = true;
    runBtn.textContent = "补全中…";
    resultBox.classList.add("hidden");
    try {
      const manifestResponse = await fetch(`/workspace/${sceneId}/scene.json?v=${Date.now()}`);
      const manifest = await manifestResponse.json();
      if (!manifestResponse.ok) throw new Error("scene.json 加载失败");
      const asset = selectedAsset(manifest);
      if (!asset) throw new Error("请先在 Asset Tree 选择素材");

      const response = await fetch(`/api/v1/scenes/${sceneId}/assets/${asset.id}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rect,
          provider: providerSelect.value,
          prompt: document.getElementById("completionPrompt").value.trim() || null,
          mode: "occlusion_completion",
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "补全失败");

      const base = `/workspace/${sceneId}/`;
      resultBox.innerHTML = "";
      const label = document.createElement("span");
      label.textContent = `${asset.label} · ${data.provider} · ${data.resegmented ? "已重新分割" : "Mock Mask"}`;
      resultBox.appendChild(label);
      for (const [text, path] of [
        ["查看补全素材", data.completed_asset],
        ["查看补全 Mask", data.completed_mask],
        ["查看补全场景", data.completed_scene],
      ]) {
        const link = document.createElement("a");
        link.href = base + path + `?v=${Date.now()}`;
        link.target = "_blank";
        link.textContent = text;
        resultBox.appendChild(link);
      }
      resultBox.classList.remove("hidden");
      status.textContent = "补全完成 · 原素材未覆盖";
    } catch (error) {
      status.textContent = `补全失败：${error.message}`;
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = "使用当前矩形补全";
    }
  });

  function currentSceneId() {
    const href = manifestLink.getAttribute("href") || "";
    const match = href.match(/\/workspace\/([0-9a-f]{12})\/scene\.json/);
    return match ? match[1] : null;
  }

  function currentRect() {
    const ids = ["splitX1", "splitY1", "splitX2", "splitY2"];
    if (ids.some((id) => !document.getElementById(id))) return null;
    const [x1, y1, x2, y2] = ids.map((id) => Number(document.getElementById(id).value));
    if (![x1, y1, x2, y2].every(Number.isFinite) || x2 <= x1 || y2 <= y1) return null;
    return { x1, y1, x2, y2 };
  }

  function selectedAsset(manifest) {
    const buttons = [...document.querySelectorAll(".asset-row")];
    const selectedIndex = buttons.findIndex((button) => button.classList.contains("selected"));
    if (selectedIndex < 0) return null;
    return manifest.assets?.[selectedIndex] || null;
  }

  loadProviders();
})();
