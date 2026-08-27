(() => {
  const byId = (id) => document.getElementById(id);
  const input = byId("semanticInput");
  const depth = byId("semanticDepth");
  const maxPerGroup = byId("semanticMaxPerGroup");
  const expandButton = byId("semanticExpandBtn");
  const applyButton = byId("semanticApplyBtn");
  const analyzeButton = byId("semanticAnalyzeBtn");
  const recommendButton = byId("semanticRecommendBtn");
  const result = byId("semanticResult");
  const summary = byId("semanticSummary");
  const groups = byId("semanticGroups");
  const recommendations = byId("semanticRecommendations");
  const examples = byId("semanticExamples");
  const promptInput = byId("promptInput");
  const imageInput = byId("imageInput");
  const mainAnalyzeButton = byId("analyzeBtn");
  const globalMessage = byId("message");
  const manifestLink = byId("manifestLink");

  if (!input || !expandButton || !result) return;

  let lastExpansion = null;

  expandButton.addEventListener("click", expandKeyword);
  applyButton.addEventListener("click", () => applyPrompts(false));
  analyzeButton.addEventListener("click", () => applyPrompts(true));
  recommendButton.addEventListener("click", recommendMissingAssets);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      expandKeyword();
    }
  });

  async function expandKeyword() {
    const keyword = input.value.trim();
    if (!keyword) {
      setSummary("请输入场景概念，例如：废弃地铁站。", true);
      return;
    }

    expandButton.disabled = true;
    expandButton.textContent = "联想中…";
    applyButton.disabled = true;
    analyzeButton.disabled = true;
    recommendButton.disabled = true;
    groups.innerHTML = "";
    recommendations.innerHTML = "";
    recommendations.classList.add("hidden");
    setSummary("正在使用本地 Game Asset Ontology 展开关键词…", false);
    result.classList.remove("hidden");

    try {
      const response = await fetch("/api/v1/semantic/expand", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          keyword,
          depth: Number(depth.value || 2),
          max_per_group: Number(maxPerGroup.value || 12),
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "语义联想失败");

      lastExpansion = data;
      renderExpansion(data);
      const hasPrompts = Array.isArray(data.detection_prompts) && data.detection_prompts.length > 0;
      applyButton.disabled = !hasPrompts;
      analyzeButton.disabled = !hasPrompts;
      recommendButton.disabled = !hasPrompts;
    } catch (error) {
      lastExpansion = null;
      setSummary(`联想失败：${error.message}`, true);
    } finally {
      expandButton.disabled = false;
      expandButton.textContent = "生成关键词组";
    }
  }

  function renderExpansion(data) {
    const matched = data.matched_concept_label || "未匹配本体";
    const modifiers = (data.modifiers || []).join("、") || "无";
    const promptCount = (data.detection_prompts || []).length;
    const warnings = (data.warnings || [])
      .map((item) => `<div class="semantic-warning">${escapeHtml(item)}</div>`)
      .join("");

    setSummary(
      `<strong>${escapeHtml(data.input)}</strong> → ${escapeHtml(matched)} · 修饰词：${escapeHtml(modifiers)} · 检测 Prompt ${promptCount} 个${warnings}`,
      false,
      true,
    );

    groups.innerHTML = "";
    (data.groups || []).forEach((group) => {
      const section = document.createElement("section");
      section.className = "semantic-group";
      const title = document.createElement("div");
      title.className = "semantic-group-title";
      title.innerHTML = `<strong>${escapeHtml(group.label_zh)}</strong><small>${escapeHtml(group.key)} · ${group.items.length}</small>`;

      const cloud = document.createElement("div");
      cloud.className = "semantic-cloud";
      group.items.forEach((item) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = item.source.startsWith("variant:") ? "semantic-chip variant" : "semantic-chip";
        chip.title = `${item.en} · score ${Math.round(item.score * 100)} · ${item.source}`;
        chip.innerHTML = `<span>${escapeHtml(item.zh)}</span><small>${escapeHtml(item.en)}</small>`;
        chip.addEventListener("click", () => togglePrompt(item.en, chip));
        cloud.appendChild(chip);
      });

      section.append(title, cloud);
      groups.appendChild(section);
    });
  }

  function applyPrompts(andAnalyze) {
    if (!lastExpansion?.detection_prompts?.length) return;
    promptInput.value = lastExpansion.detection_prompts.join(", ");
    if (globalMessage) {
      globalMessage.textContent = `已应用 ${lastExpansion.detection_prompts.length} 个本地语义 Prompt。`;
    }

    if (!andAnalyze) {
      promptInput.focus();
      return;
    }

    if (!imageInput.files?.[0]) {
      if (globalMessage) globalMessage.textContent = "关键词已应用；请先上传场景图片，再开始 AI 拆解。";
      return;
    }
    if (mainAnalyzeButton.disabled) {
      if (globalMessage) globalMessage.textContent = "关键词已应用，但当前推理模型未就绪。";
      return;
    }
    mainAnalyzeButton.click();
  }

  async function recommendMissingAssets() {
    if (!lastExpansion?.matched_concept) return;
    const sceneId = currentSceneId();
    if (!sceneId) {
      if (globalMessage) {
        globalMessage.textContent = "请先完成一次场景拆解，再检查本体覆盖率和缺失素材。";
      }
      return;
    }

    recommendButton.disabled = true;
    recommendButton.textContent = "检查中…";
    try {
      const response = await fetch(`/api/v1/scenes/${sceneId}/recommendations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          keyword: lastExpansion.input,
          max_results: 30,
          min_semantic_score: 0.65,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "缺失素材分析失败");
      renderRecommendations(data);
    } catch (error) {
      recommendations.classList.remove("hidden");
      recommendations.innerHTML = `<div class="recommendation-error">检查失败：${escapeHtml(error.message)}</div>`;
    } finally {
      recommendButton.disabled = false;
      recommendButton.textContent = "检查缺失素材";
    }
  }

  function renderRecommendations(data) {
    const coverage = Math.round((data.coverage_ratio || 0) * 100);
    const missing = data.missing || [];
    recommendations.classList.remove("hidden");
    recommendations.innerHTML = `
      <div class="recommendation-head">
        <div>
          <strong>场景素材覆盖率 ${coverage}%</strong>
          <span>已匹配 ${data.matched_count} / ${data.candidate_count} 个本体候选</span>
        </div>
        <small>缺失推荐 ${missing.length} 个</small>
      </div>
      <div class="coverage-track"><span style="width:${Math.max(0, Math.min(100, coverage))}%"></span></div>
      <div id="missingAssetCloud" class="missing-asset-cloud"></div>
    `;

    const cloud = byId("missingAssetCloud");
    missing.forEach((item) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "missing-asset-chip";
      chip.title = `点击加入检测 Prompt · semantic score ${Math.round(item.semantic_score * 100)}`;
      chip.innerHTML = `
        <span>+ ${escapeHtml(item.zh)}</span>
        <small>${escapeHtml(item.en)} · ${escapeHtml(item.group_label_zh)}</small>
      `;
      chip.addEventListener("click", () => {
        addPrompt(item.en);
        chip.classList.add("added");
        if (globalMessage) globalMessage.textContent = `已把缺失素材 ${item.zh} (${item.en}) 加入检测 Prompt。`;
      });
      cloud.appendChild(chip);
    });

    if (!missing.length) {
      cloud.innerHTML = '<span class="coverage-complete">当前场景已覆盖本体中的主要可检测素材。</span>';
    }
  }

  function currentSceneId() {
    const href = manifestLink?.getAttribute("href") || "";
    const match = href.match(/\/workspace\/([0-9a-f]{12})\/scene\.json/);
    return match ? match[1] : null;
  }

  function togglePrompt(term, chip) {
    const terms = promptTerms();
    const index = terms.findIndex((value) => value.toLowerCase() === term.toLowerCase());
    if (index >= 0) {
      terms.splice(index, 1);
      chip.classList.remove("active");
    } else {
      terms.push(term);
      chip.classList.add("active");
    }
    promptInput.value = terms.join(", ");
  }

  function addPrompt(term) {
    const terms = promptTerms();
    if (!terms.some((value) => value.toLowerCase() === term.toLowerCase())) {
      terms.push(term);
      promptInput.value = terms.join(", ");
    }
  }

  function promptTerms() {
    return promptInput.value
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
  }

  async function loadCatalog() {
    if (!examples) return;
    try {
      const response = await fetch("/api/v1/semantic/catalog");
      const data = await response.json();
      if (!response.ok) return;
      const concepts = (data.concepts || []).slice(0, 8);
      const modifiers = (data.modifiers || []).slice(0, 6);
      examples.innerHTML = "";

      concepts.forEach((item) => addExample(item.label_zh, false));
      modifiers.forEach((item) => addExample(item.label_zh, true));
    } catch {
      // Catalog is optional UI sugar; expansion itself remains available.
    }
  }

  function addExample(label, modifier) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = modifier ? "example-chip modifier" : "example-chip";
    button.textContent = label;
    button.addEventListener("click", () => {
      if (modifier) {
        input.value = `${label}${input.value.trim()}`;
      } else {
        input.value = label;
      }
      input.focus();
    });
    examples.appendChild(button);
  }

  function setSummary(value, isError = false, html = false) {
    summary.classList.toggle("error", isError);
    if (html) summary.innerHTML = value;
    else summary.textContent = value;
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

  loadCatalog();
})();
