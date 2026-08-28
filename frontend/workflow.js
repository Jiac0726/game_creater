(() => {
  const shell = document.querySelector("main.shell");
  const semanticPanel = document.querySelector(".semantic-panel");
  if (!shell || !semanticPanel) return;

  const style = document.createElement("style");
  style.textContent = `
    .workflow-panel { padding: 18px; }
    .workflow-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:14px; }
    .workflow-head h2 { margin:0 0 5px; }
    .workflow-head p { margin:0; opacity:.72; }
    .workflow-badge { white-space:nowrap; font-size:12px; padding:5px 9px; border-radius:999px; border:1px solid currentColor; opacity:.82; }
    .workflow-grid { display:grid; grid-template-columns:minmax(220px,2fr) repeat(3,minmax(120px,1fr)); gap:10px; align-items:end; }
    .workflow-grid label { display:flex; flex-direction:column; gap:5px; font-size:12px; }
    .workflow-grid input,.workflow-grid select { width:100%; box-sizing:border-box; }
    .workflow-actions { display:flex; gap:10px; margin-top:12px; align-items:center; flex-wrap:wrap; }
    .workflow-auto { display:flex !important; flex-direction:row !important; align-items:center; gap:7px !important; font-size:13px !important; }
    .workflow-auto input { width:auto; }
    .workflow-status { margin-top:14px; display:grid; grid-template-columns:minmax(260px,1fr) minmax(260px,1fr); gap:14px; }
    .workflow-status.hidden { display:none; }
    .workflow-preview { min-height:180px; border:1px dashed rgba(127,127,127,.35); border-radius:10px; display:flex; align-items:center; justify-content:center; overflow:hidden; }
    .workflow-preview img { max-width:100%; max-height:360px; object-fit:contain; }
    .workflow-details { font-size:13px; line-height:1.55; overflow:auto; }
    .workflow-details pre { white-space:pre-wrap; word-break:break-word; max-height:230px; overflow:auto; font-size:12px; }
    .workflow-stage { font-weight:700; }
    @media (max-width:900px) { .workflow-grid,.workflow-status { grid-template-columns:1fr; } }
  `;
  document.head.appendChild(style);

  const panel = document.createElement("section");
  panel.className = "card workflow-panel";
  panel.innerHTML = `
    <div class="workflow-head">
      <div>
        <h2>AI 场景全流程</h2>
        <p>场景概念 → 语义 Asset Plan → 大模型生图 → 自动回传 → GroundingDINO + SAM2 拆解</p>
      </div>
      <span class="workflow-badge">PROJECT WORKFLOW</span>
    </div>
    <div class="workflow-grid">
      <label><span>场景概念</span><input id="workflowConcept" value="废弃地铁站" placeholder="例如：中世纪魔法森林村庄" /></label>
      <label><span>生图 Provider</span><select id="workflowProvider"><option value="mock">mock</option></select></label>
      <label><span>尺寸</span><select id="workflowSize">
        <option value="1536x1024" selected>1536×1024</option>
        <option value="1024x1024">1024×1024</option>
        <option value="2048x1152">2048×1152</option>
        <option value="3840x2160">3840×2160</option>
      </select></label>
      <label><span>质量</span><select id="workflowQuality"><option>low</option><option selected>medium</option><option>high</option></select></label>
    </div>
    <div class="workflow-actions">
      <button id="workflowRunBtn">一键生成并拆解</button>
      <label class="workflow-auto"><input id="workflowAutoSplit" type="checkbox" checked /> 生图后自动拆解</label>
      <span id="workflowProviderHint"></span>
    </div>
    <div id="workflowStatus" class="workflow-status hidden">
      <div class="workflow-preview"><img id="workflowImage" alt="AI 生成场景" /></div>
      <div class="workflow-details">
        <div>Project: <code id="workflowProjectId">-</code></div>
        <div>Stage: <span id="workflowStage" class="workflow-stage">-</span></div>
        <div>Scene: <code id="workflowSceneId">-</code></div>
        <div>Planned assets: <span id="workflowPlannedCount">0</span></div>
        <div>Detection prompts: <span id="workflowPromptCount">0</span></div>
        <details><summary>生图 Prompt</summary><pre id="workflowPromptText"></pre></details>
      </div>
    </div>
  `;
  semanticPanel.insertAdjacentElement("afterend", panel);

  const byId = (id) => document.getElementById(id);
  const providerSelect = byId("workflowProvider");
  const providerHint = byId("workflowProviderHint");
  const runBtn = byId("workflowRunBtn");
  const statusPanel = byId("workflowStatus");

  async function loadProviders() {
    try {
      const response = await fetch("/api/v1/generation/providers");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "provider catalog failed");
      providerSelect.innerHTML = "";
      let preferred = "mock";
      for (const provider of data.providers || []) {
        const option = document.createElement("option");
        option.value = provider.id;
        option.textContent = `${provider.id}${provider.model ? ` · ${provider.model}` : ""}${provider.ready ? "" : " · 未配置"}`;
        option.disabled = !provider.ready;
        providerSelect.appendChild(option);
        if (provider.id === "openai" && provider.ready) preferred = "openai";
      }
      providerSelect.value = preferred;
      syncProviderHint();
    } catch (error) {
      providerHint.textContent = `Provider 检查失败：${error.message}`;
    }
  }

  function syncProviderHint() {
    if (providerSelect.value === "openai") {
      providerHint.textContent = "使用服务器环境变量 OPENAI_API_KEY；密钥不会发送到浏览器。";
    } else {
      providerHint.textContent = "Mock 用于验证完整流水线，不产生真实 AI 图像。";
    }
  }
  providerSelect.addEventListener("change", syncProviderHint);

  runBtn.addEventListener("click", async () => {
    const concept = byId("workflowConcept").value.trim();
    if (!concept) return;

    runBtn.disabled = true;
    runBtn.textContent = "全流程运行中…";
    statusPanel.classList.remove("hidden");
    byId("workflowStage").textContent = "STARTING";
    const mainMessage = document.getElementById("message");
    if (mainMessage) mainMessage.textContent = "正在执行：语义规划 → 生图 → 自动回传 → 拆解…";

    try {
      const response = await fetch("/api/v1/projects/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          concept,
          provider: providerSelect.value,
          size: byId("workflowSize").value,
          quality: byId("workflowQuality").value,
          auto_split: byId("workflowAutoSplit").checked,
          semantic_depth: 2,
          max_per_group: 12,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "全流程失败");
      const project = payload.project;
      renderProject(project);

      const semanticInput = document.getElementById("semanticInput");
      if (semanticInput) semanticInput.value = concept;
      const promptInput = document.getElementById("promptInput");
      if (promptInput && project.asset_plan?.detection_prompts) {
        promptInput.value = project.asset_plan.detection_prompts.join(", ");
      }

      if (project.scene_id) {
        const sceneResponse = await fetch(`/workspace/${project.scene_id}/scene.json?v=${Date.now()}`);
        const manifest = await sceneResponse.json();
        if (!sceneResponse.ok) throw new Error("已拆图，但 scene.json 加载失败");
        if (typeof window.applyManifest === "function") window.applyManifest(manifest);
        if (mainMessage) mainMessage.textContent = `全流程完成：Project ${project.project_id} → Scene ${project.scene_id} → ${manifest.assets.length} 个素材`;
      } else if (mainMessage) {
        mainMessage.textContent = `生图完成：Project ${project.project_id}；自动拆解已关闭。`;
      }
    } catch (error) {
      byId("workflowStage").textContent = "FAILED";
      if (mainMessage) mainMessage.textContent = `全流程失败：${error.message}`;
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = "一键生成并拆解";
    }
  });

  function renderProject(project) {
    byId("workflowProjectId").textContent = project.project_id || "-";
    byId("workflowStage").textContent = project.stage || "-";
    byId("workflowSceneId").textContent = project.scene_id || "-";
    byId("workflowPlannedCount").textContent = project.asset_plan?.assets?.length || 0;
    byId("workflowPromptCount").textContent = project.asset_plan?.detection_prompts?.length || 0;
    byId("workflowPromptText").textContent = project.generation?.prompt || "";
    const image = byId("workflowImage");
    image.src = `/workspace/projects/${project.project_id}/generation/source.png?v=${Date.now()}`;
  }

  loadProviders();
})();
