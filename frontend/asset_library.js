(() => {
  if (document.getElementById("assetLibraryPanel")) return;
  const shell = document.querySelector("main.shell");
  const footer = document.querySelector(".footerbar");
  if (!shell || !footer) return;

  const style = document.createElement("style");
  style.textContent = `
    .library-panel { padding:18px; }
    .library-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:14px; }
    .library-head h2 { margin:0 0 5px; }
    .library-head p { margin:0; opacity:.72; }
    .library-stats { display:grid; grid-template-columns:repeat(6,minmax(90px,1fr)); gap:8px; margin:12px 0; }
    .library-stat { border:1px solid rgba(127,127,127,.25); border-radius:9px; padding:10px; }
    .library-stat strong { display:block; font-size:20px; }
    .library-stat span { font-size:11px; opacity:.68; }
    .library-layout { display:grid; grid-template-columns:220px minmax(360px,1fr) 310px; gap:12px; min-height:430px; }
    .library-sidebar,.library-inspector { border:1px solid rgba(127,127,127,.22); border-radius:10px; padding:12px; overflow:auto; }
    .library-sidebar label,.library-inspector label { display:flex; flex-direction:column; gap:5px; margin-bottom:9px; font-size:12px; }
    .library-sidebar input,.library-sidebar select,.library-inspector input,.library-inspector select,.library-inspector textarea { width:100%; box-sizing:border-box; }
    .library-grid-wrap { min-width:0; }
    .library-grid-head { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:9px; font-size:12px; opacity:.78; }
    .library-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(130px,1fr)); gap:9px; max-height:640px; overflow:auto; padding-right:3px; }
    .library-card { text-align:left; padding:0; border:1px solid rgba(127,127,127,.2); border-radius:10px; overflow:hidden; background:transparent; cursor:pointer; }
    .library-card.selected { outline:2px solid #7cc4ff; }
    .library-thumb { aspect-ratio:1/1; background:rgba(127,127,127,.08); display:flex; align-items:center; justify-content:center; overflow:hidden; }
    .library-thumb img { width:100%; height:100%; object-fit:contain; }
    .library-card-body { padding:8px; }
    .library-card-title { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:12px; font-weight:700; }
    .library-card-meta { margin-top:4px; display:flex; justify-content:space-between; gap:5px; font-size:10px; opacity:.7; }
    .library-review { font-size:10px; margin-top:5px; opacity:.78; }
    .library-empty { padding:30px; text-align:center; opacity:.6; }
    .library-inspector-preview { min-height:150px; display:flex; align-items:center; justify-content:center; background:rgba(127,127,127,.07); border-radius:9px; margin-bottom:10px; overflow:hidden; }
    .library-inspector-preview img { width:100%; max-height:220px; object-fit:contain; }
    .library-inspector-id { font-size:10px; word-break:break-all; opacity:.58; margin-bottom:10px; }
    .library-actions { display:flex; gap:7px; flex-wrap:wrap; }
    .library-section { border-top:1px solid rgba(127,127,127,.2); margin-top:12px; padding-top:10px; }
    .library-section h4 { margin:0 0 7px; font-size:12px; }
    .library-version { font-size:11px; padding:5px 0; border-bottom:1px dashed rgba(127,127,127,.15); }
    .library-provenance { max-height:130px; overflow:auto; white-space:pre-wrap; word-break:break-word; font-size:10px; }
    .library-collection-row { display:flex; gap:5px; margin-bottom:5px; }
    .library-collection-row button { flex:1; text-align:left; }
    @media (max-width:1100px) { .library-layout { grid-template-columns:190px 1fr; } .library-inspector { grid-column:1/-1; } .library-stats { grid-template-columns:repeat(3,1fr); } }
    @media (max-width:720px) { .library-layout { grid-template-columns:1fr; } .library-inspector { grid-column:auto; } .library-stats { grid-template-columns:repeat(2,1fr); } }
  `;
  document.head.appendChild(style);

  const panel = document.createElement("section");
  panel.id = "assetLibraryPanel";
  panel.className = "card library-panel";
  panel.innerHTML = `
    <div class="library-head">
      <div>
        <h2>Asset Library · 游戏素材库</h2>
        <p>SQLite 全局索引 · 稳定 Asset ID · 标签 / Collection / 审核 / 版本 / 来源追踪</p>
      </div>
      <button id="libraryRefreshBtn">刷新素材库</button>
    </div>
    <div id="libraryStats" class="library-stats"></div>
    <div class="library-layout">
      <aside class="library-sidebar">
        <label><span>搜索</span><input id="libraryQuery" placeholder="名称 / 分类 / 备注" /></label>
        <label><span>分类</span><select id="libraryCategory"><option value="">全部分类</option></select></label>
        <label><span>审核状态</span><select id="libraryReviewState">
          <option value="">全部状态</option>
          <option value="needs_review">Needs Review</option>
          <option value="approved">Approved</option>
          <option value="production_ready">Production Ready</option>
          <option value="in_use">In Use</option>
          <option value="archived">Archived</option>
        </select></label>
        <label><span>最低 Asset Score</span><select id="libraryMinScore">
          <option value="">不限</option><option value="0.5">50+</option><option value="0.7">70+</option><option value="0.85">85+</option>
        </select></label>
        <label><span>标签（逗号分隔）</span><input id="libraryTagFilter" placeholder="forest,moss" /></label>
        <label style="flex-direction:row;align-items:center"><input id="libraryFavoriteOnly" type="checkbox" style="width:auto" /> 只看收藏</label>
        <div class="library-section">
          <h4>Collections</h4>
          <div id="libraryCollections"></div>
          <button id="libraryCreateCollectionBtn">+ 新建 Collection</button>
        </div>
      </aside>
      <div class="library-grid-wrap">
        <div class="library-grid-head"><span id="libraryCount">0 个素材</span><span>收藏优先 · Asset Score 排序</span></div>
        <div id="libraryGrid" class="library-grid"></div>
      </div>
      <aside id="libraryInspector" class="library-inspector"><div class="library-empty">选择一个素材查看详情</div></aside>
    </div>
  `;
  footer.insertAdjacentElement("beforebegin", panel);

  const $ = (id) => document.getElementById(id);
  const state = { items: [], selected: null, collections: [], activeCollection: "", timer: null };
  const REVIEW_STATES = ["needs_review", "approved", "production_ready", "in_use", "archived"];

  async function loadAll() {
    await Promise.all([loadStats(), loadCollections(), searchAssets()]);
  }

  async function loadStats() {
    try {
      const response = await fetch("/api/v1/library/stats");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "stats failed");
      $("libraryStats").innerHTML = [
        [data.total_assets, "全部素材"],
        [data.needs_review, "待审核"],
        [data.approved, "已批准"],
        [data.production_ready, "Production Ready"],
        [data.completed_by_ai, "AI 补全"],
        [data.favorites, "收藏"],
      ].map(([value,label]) => `<div class="library-stat"><strong>${value}</strong><span>${label}</span></div>`).join("");
      const category = $("libraryCategory");
      const current = category.value;
      category.innerHTML = `<option value="">全部分类</option>` + Object.entries(data.categories || {})
        .map(([name,count]) => `<option value="${escapeAttr(name)}">${escapeHtml(name)} (${count})</option>`).join("");
      category.value = current;
    } catch (error) {
      $("libraryStats").innerHTML = `<div class="library-empty">统计加载失败：${escapeHtml(error.message)}</div>`;
    }
  }

  async function loadCollections() {
    const response = await fetch("/api/v1/library/collections");
    const data = await response.json();
    if (!response.ok) return;
    state.collections = data.collections || [];
    const root = $("libraryCollections");
    root.innerHTML = "";
    const all = document.createElement("div");
    all.className = "library-collection-row";
    const allButton = document.createElement("button");
    allButton.textContent = "全部素材";
    allButton.addEventListener("click", () => { state.activeCollection = ""; searchAssets(); });
    all.appendChild(allButton);
    root.appendChild(all);
    state.collections.forEach((collection) => {
      const row = document.createElement("div");
      row.className = "library-collection-row";
      const button = document.createElement("button");
      button.textContent = `${collection.name} · ${collection.asset_count}`;
      button.title = collection.description || "";
      button.addEventListener("click", () => { state.activeCollection = collection.id; searchAssets(); });
      row.appendChild(button);
      root.appendChild(row);
    });
  }

  async function searchAssets() {
    const params = new URLSearchParams();
    const mappings = [
      ["q", $("libraryQuery").value.trim()],
      ["category", $("libraryCategory").value],
      ["review_state", $("libraryReviewState").value],
      ["min_score", $("libraryMinScore").value],
      ["tags", $("libraryTagFilter").value.trim()],
      ["collection_id", state.activeCollection],
    ];
    mappings.forEach(([key,value]) => { if (value) params.set(key,value); });
    if ($("libraryFavoriteOnly").checked) params.set("favorite", "true");
    params.set("limit", "120");

    const grid = $("libraryGrid");
    grid.innerHTML = `<div class="library-empty">加载中…</div>`;
    try {
      const response = await fetch(`/api/v1/library/assets?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "search failed");
      state.items = data.items || [];
      $("libraryCount").textContent = `${data.total} 个素材`;
      renderGrid();
      if (state.selected) {
        const latest = state.items.find((item) => item.id === state.selected.id);
        if (latest) selectAsset(latest);
      }
    } catch (error) {
      grid.innerHTML = `<div class="library-empty">素材库加载失败：${escapeHtml(error.message)}</div>`;
    }
  }

  function renderGrid() {
    const grid = $("libraryGrid");
    grid.innerHTML = "";
    if (!state.items.length) {
      grid.innerHTML = `<div class="library-empty">没有符合条件的素材</div>`;
      return;
    }
    state.items.forEach((asset) => {
      const card = document.createElement("button");
      card.className = `library-card${state.selected?.id === asset.id ? " selected" : ""}`;
      card.innerHTML = `
        <div class="library-thumb"><img loading="lazy" src="/workspace/${escapeAttr(asset.image_path)}?v=${encodeURIComponent(asset.updated_at)}" alt="${escapeAttr(asset.name)}" /></div>
        <div class="library-card-body">
          <div class="library-card-title">${asset.favorite ? "★ " : ""}${escapeHtml(asset.name)}</div>
          <div class="library-card-meta"><span>${escapeHtml(asset.category)}</span><span>S${Math.round((asset.asset_score || 0)*100)}</span></div>
          <div class="library-review">${escapeHtml(asset.review_state)}</div>
        </div>`;
      card.addEventListener("click", () => selectAsset(asset));
      grid.appendChild(card);
    });
  }

  async function selectAsset(asset) {
    state.selected = asset;
    renderGrid();
    const inspector = $("libraryInspector");
    inspector.innerHTML = `
      <div class="library-inspector-preview"><img src="/workspace/${escapeAttr(asset.image_path)}?v=${encodeURIComponent(asset.updated_at)}" alt="${escapeAttr(asset.name)}" /></div>
      <div class="library-inspector-id">${escapeHtml(asset.id)}<br/>Scene ${escapeHtml(asset.scene_id)} / ${escapeHtml(asset.scene_asset_id)}</div>
      <label><span>名称</span><input id="libraryEditName" value="${escapeAttr(asset.name)}" /></label>
      <label><span>分类</span><input id="libraryEditCategory" value="${escapeAttr(asset.category)}" /></label>
      <label><span>子分类</span><input id="libraryEditSubcategory" value="${escapeAttr(asset.subcategory || "")}" /></label>
      <label><span>审核状态</span><select id="libraryEditReview">${REVIEW_STATES.map((value) => `<option value="${value}" ${asset.review_state===value?"selected":""}>${value}</option>`).join("")}</select></label>
      <label><span>标签</span><input id="libraryEditTags" value="${escapeAttr((asset.tags || []).join(", "))}" placeholder="forest, wood, broken" /></label>
      <label><span>备注</span><textarea id="libraryEditNotes" rows="3">${escapeHtml(asset.notes || "")}</textarea></label>
      <label style="flex-direction:row;align-items:center"><input id="libraryEditFavorite" type="checkbox" style="width:auto" ${asset.favorite?"checked":""} /> 收藏</label>
      <div class="library-actions"><button id="librarySaveBtn">保存元数据</button><button id="libraryAddCollectionBtn">加入 Collection</button></div>
      <div class="library-section"><h4>版本历史</h4><div id="libraryVersions">加载中…</div></div>
      <div class="library-section"><h4>来源追踪</h4><pre class="library-provenance">${escapeHtml(JSON.stringify(asset.provenance || {}, null, 2))}</pre></div>
      <div class="library-section"><h4>关系</h4><div id="libraryRelations">加载中…</div><div class="library-actions"><input id="libraryRelationTarget" placeholder="目标 Asset ID" /><select id="libraryRelationType"><option>related_to</option><option>variant_of</option><option>derived_from</option><option>part_of</option><option>parent_of</option></select><button id="libraryAddRelationBtn">添加</button></div></div>
    `;
    $("librarySaveBtn").addEventListener("click", saveSelected);
    $("libraryAddCollectionBtn").addEventListener("click", addSelectedToCollection);
    $("libraryAddRelationBtn").addEventListener("click", addRelation);
    loadVersions(asset.id);
    loadRelations(asset.id);
  }

  async function saveSelected() {
    if (!state.selected) return;
    const tags = $("libraryEditTags").value.split(",").map((value) => value.trim()).filter(Boolean);
    const payload = {
      name: $("libraryEditName").value.trim(),
      category: $("libraryEditCategory").value.trim() || "uncategorized",
      subcategory: $("libraryEditSubcategory").value.trim(),
      review_state: $("libraryEditReview").value,
      favorite: $("libraryEditFavorite").checked,
      notes: $("libraryEditNotes").value.trim() || null,
      tags,
    };
    const response = await fetch(`/api/v1/library/assets/${state.selected.id}`, { method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) { alert(data.detail || "保存失败"); return; }
    state.selected = data;
    await Promise.all([loadStats(), searchAssets()]);
  }

  async function loadVersions(assetId) {
    const response = await fetch(`/api/v1/library/assets/${assetId}/versions`);
    const data = await response.json();
    if (!response.ok || !Array.isArray(data)) return;
    $("libraryVersions").innerHTML = data.map((version) => `<div class="library-version"><strong>v${version.version}</strong> · ${escapeHtml(version.kind)}<br/><a href="/workspace/${escapeAttr(version.image_path)}" target="_blank">${escapeHtml(version.image_path)}</a></div>`).join("") || "无版本";
  }

  async function loadRelations(assetId) {
    const response = await fetch(`/api/v1/library/assets/${assetId}/relations`);
    const data = await response.json();
    if (!response.ok) return;
    $("libraryRelations").innerHTML = (data.relations || []).map((relation) => `<div class="library-version">${escapeHtml(relation.relation_type)} · ${escapeHtml(relation.source_asset_id)} → ${escapeHtml(relation.target_asset_id)}</div>`).join("") || "暂无关系";
  }

  async function addRelation() {
    if (!state.selected) return;
    const target = $("libraryRelationTarget").value.trim();
    if (!target) return;
    const response = await fetch(`/api/v1/library/assets/${state.selected.id}/relations`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({target_asset_id:target,relation_type:$("libraryRelationType").value}) });
    const data = await response.json();
    if (!response.ok) { alert(data.detail || "添加关系失败"); return; }
    loadRelations(state.selected.id);
  }

  async function addSelectedToCollection() {
    if (!state.selected || !state.collections.length) { alert("请先创建 Collection"); return; }
    const names = state.collections.map((collection,index) => `${index+1}. ${collection.name}`).join("\n");
    const raw = prompt(`选择 Collection 序号：\n${names}`, "1");
    if (raw === null) return;
    const collection = state.collections[Number(raw)-1];
    if (!collection) return;
    const response = await fetch(`/api/v1/library/collections/${collection.id}/assets`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({asset_ids:[state.selected.id]}) });
    if (!response.ok) { const data = await response.json(); alert(data.detail || "加入失败"); return; }
    await loadCollections();
    const refreshed = await fetch(`/api/v1/library/assets/${state.selected.id}`).then((r) => r.json());
    selectAsset(refreshed);
  }

  async function createCollection() {
    const name = prompt("Collection 名称，例如：魔法森林");
    if (!name?.trim()) return;
    const description = prompt("描述（可选）", "") || "";
    const response = await fetch("/api/v1/library/collections", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name:name.trim(),description}) });
    const data = await response.json();
    if (!response.ok) { alert(data.detail || "创建失败"); return; }
    await Promise.all([loadCollections(), loadStats()]);
  }

  function scheduleSearch() {
    clearTimeout(state.timer);
    state.timer = setTimeout(searchAssets, 220);
  }

  ["libraryQuery","libraryTagFilter"].forEach((id) => $(id).addEventListener("input", scheduleSearch));
  ["libraryCategory","libraryReviewState","libraryMinScore","libraryFavoriteOnly"].forEach((id) => $(id).addEventListener("change", searchAssets));
  $("libraryRefreshBtn").addEventListener("click", loadAll);
  $("libraryCreateCollectionBtn").addEventListener("click", createCollection);

  const manifestLink = document.getElementById("manifestLink");
  if (manifestLink) {
    new MutationObserver(() => setTimeout(loadAll, 150)).observe(manifestLink, {attributes:true, attributeFilter:["href"]});
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"})[char]);
  }
  function escapeAttr(value) { return escapeHtml(value).replace(/`/g,"&#096;"); }

  loadAll();
})();
