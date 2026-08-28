(() => {
  if (document.getElementById("assetStorePanel")) return;
  const footer = document.querySelector(".footerbar");
  if (!footer) return;

  const style = document.createElement("style");
  style.textContent = `
    .store-panel { padding:18px; }
    .store-head { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:14px; }
    .store-head h2 { margin:0 0 5px; }
    .store-head p { margin:0; opacity:.72; max-width:780px; }
    .store-badge { padding:5px 9px; border:1px solid currentColor; border-radius:999px; font-size:11px; opacity:.8; white-space:nowrap; }
    .store-stats { display:grid; grid-template-columns:repeat(6,minmax(90px,1fr)); gap:8px; margin-bottom:14px; }
    .store-stat { border:1px solid rgba(127,127,127,.22); border-radius:9px; padding:10px; }
    .store-stat strong { display:block; font-size:19px; }
    .store-stat span { font-size:10px; opacity:.68; }
    .store-tabs { display:flex; gap:8px; margin-bottom:12px; flex-wrap:wrap; }
    .store-tab.active { outline:2px solid rgba(124,196,255,.75); }
    .store-view.hidden { display:none; }
    .store-layout { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:12px; }
    .store-toolbar { display:grid; grid-template-columns:minmax(180px,2fr) repeat(3,minmax(130px,1fr)); gap:8px; margin-bottom:10px; }
    .store-toolbar input,.store-toolbar select,.store-seller-form input,.store-seller-form select,.store-seller-form textarea { width:100%; box-sizing:border-box; }
    .store-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:10px; }
    .store-card { border:1px solid rgba(127,127,127,.22); border-radius:10px; overflow:hidden; background:rgba(127,127,127,.025); }
    .store-card.featured { box-shadow:inset 0 0 0 1px rgba(255,197,92,.45); }
    .store-thumb { aspect-ratio:1/1; display:flex; align-items:center; justify-content:center; background:rgba(127,127,127,.07); overflow:hidden; }
    .store-thumb img { width:100%; height:100%; object-fit:contain; }
    .store-card-body { padding:10px; }
    .store-title { font-weight:700; font-size:13px; min-height:34px; }
    .store-seller { font-size:10px; opacity:.58; margin:3px 0 7px; }
    .store-tags { font-size:10px; opacity:.65; min-height:30px; }
    .store-price-row { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:8px; }
    .store-price { font-weight:800; font-size:15px; }
    .store-license { font-size:10px; opacity:.65; }
    .store-cart { border:1px solid rgba(127,127,127,.22); border-radius:10px; padding:12px; align-self:start; position:sticky; top:10px; }
    .store-cart h3,.store-seller-form h3 { margin:0 0 10px; }
    .store-cart-item { display:grid; grid-template-columns:1fr auto; gap:8px; padding:7px 0; border-bottom:1px dashed rgba(127,127,127,.16); font-size:11px; }
    .store-cart-total { display:flex; justify-content:space-between; font-weight:800; margin:12px 0; }
    .store-warning { font-size:10px; opacity:.68; margin:8px 0; line-height:1.45; }
    .store-empty { padding:30px; text-align:center; opacity:.58; border:1px dashed rgba(127,127,127,.2); border-radius:10px; }
    .store-purchases { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; }
    .store-purchase { border:1px solid rgba(127,127,127,.22); border-radius:10px; padding:12px; }
    .store-purchase code { font-size:10px; word-break:break-all; }
    .store-seller-layout { display:grid; grid-template-columns:330px minmax(0,1fr); gap:12px; }
    .store-seller-form { border:1px solid rgba(127,127,127,.22); border-radius:10px; padding:12px; }
    .store-seller-form label { display:flex; flex-direction:column; gap:5px; font-size:11px; margin-bottom:8px; }
    .store-seller-list { display:grid; gap:8px; }
    .store-seller-row { display:grid; grid-template-columns:64px 1fr auto; gap:10px; align-items:center; border:1px solid rgba(127,127,127,.2); border-radius:9px; padding:8px; }
    .store-seller-row img { width:64px; height:64px; object-fit:contain; background:rgba(127,127,127,.07); border-radius:7px; }
    .store-seller-meta { font-size:10px; opacity:.65; }
    .store-actions { display:flex; gap:6px; flex-wrap:wrap; }
    @media (max-width:1000px) { .store-layout,.store-seller-layout { grid-template-columns:1fr; } .store-cart { position:static; } .store-toolbar { grid-template-columns:1fr 1fr; } .store-stats { grid-template-columns:repeat(3,1fr); } }
    @media (max-width:650px) { .store-toolbar { grid-template-columns:1fr; } .store-stats { grid-template-columns:repeat(2,1fr); } }
  `;
  document.head.appendChild(style);

  const panel = document.createElement("section");
  panel.id = "assetStorePanel";
  panel.className = "card store-panel";
  panel.innerHTML = `
    <div class="store-head">
      <div>
        <h2>Asset Store · 游戏素材商店</h2>
        <p>Asset Library 通过审核的素材可直接上架。购买会生成订单与版本冻结的授权凭证，下载 ZIP 包含素材、Mask、metadata 与 LICENSE。</p>
      </div>
      <span class="store-badge">MARKETPLACE MVP</span>
    </div>
    <div id="storeStats" class="store-stats"></div>
    <div class="store-tabs">
      <button class="store-tab active" data-store-view="market">逛商店</button>
      <button class="store-tab" data-store-view="purchased">已购素材</button>
      <button class="store-tab" data-store-view="seller">创作者中心</button>
    </div>

    <div id="storeViewMarket" class="store-view">
      <div class="store-layout">
        <div>
          <div class="store-toolbar">
            <input id="storeQuery" placeholder="搜索商品 / 分类 / 标签" />
            <select id="storeCategory"><option value="">全部分类</option></select>
            <select id="storeLicenseFilter"><option value="">全部授权</option><option value="personal">Personal</option><option value="commercial">Commercial</option><option value="extended">Extended</option></select>
            <select id="storePriceFilter"><option value="">全部价格</option><option value="free">免费</option><option value="featured">精选</option></select>
          </div>
          <div id="storeGrid" class="store-grid"></div>
        </div>
        <aside class="store-cart">
          <h3>购物车</h3>
          <div id="storeCartItems"></div>
          <div class="store-cart-total"><span>合计</span><span id="storeCartTotal">¥0.00</span></div>
          <button id="storeCheckoutBtn" style="width:100%">Mock 结算并授权</button>
          <div id="storePaymentHint" class="store-warning">Mock 结算仅用于本地开发验证，不会发生真实收款。正式商店必须接真实支付 Provider。</div>
        </aside>
      </div>
    </div>

    <div id="storeViewPurchased" class="store-view hidden">
      <div id="storePurchases" class="store-purchases"></div>
    </div>

    <div id="storeViewSeller" class="store-view hidden">
      <div class="store-seller-layout">
        <div class="store-seller-form">
          <h3>上架 Asset Library 素材</h3>
          <label><span>Library Asset ID</span><div class="store-actions"><input id="storeSellerAssetId" placeholder="asset_xxx" /><button id="storeUseSelectedAssetBtn" type="button">使用当前选中素材</button></div></label>
          <label><span>商品标题</span><input id="storeSellerTitle" placeholder="留空则使用素材名称" /></label>
          <label><span>商品描述</span><textarea id="storeSellerDescription" rows="3" placeholder="用途、风格、推荐场景…"></textarea></label>
          <label><span>价格（元）</span><input id="storeSellerPrice" type="number" min="0" step="0.01" value="0" /></label>
          <label><span>授权</span><select id="storeSellerLicense"><option value="personal">Personal</option><option value="commercial" selected>Commercial</option><option value="extended">Extended</option></select></label>
          <label><span>创作者</span><input id="storeSellerName" value="Local Creator" /></label>
          <label style="flex-direction:row;align-items:center"><input id="storeSellerPublish" type="checkbox" style="width:auto" checked /> 立即公开上架</label>
          <label style="flex-direction:row;align-items:center"><input id="storeSellerFeatured" type="checkbox" style="width:auto" /> 精选商品</label>
          <button id="storeCreateListingBtn" style="width:100%">创建商品</button>
          <div id="storeSellerMessage" class="store-warning">只有 Approved / Production Ready / In Use 的素材才能公开上架；其他素材可先保存 Draft。</div>
        </div>
        <div>
          <div class="store-actions" style="justify-content:space-between;margin-bottom:8px"><strong>我的商品</strong><button id="storeRefreshSellerBtn">刷新</button></div>
          <div id="storeSellerListings" class="store-seller-list"></div>
        </div>
      </div>
    </div>
  `;
  footer.insertAdjacentElement("beforebegin", panel);

  const $ = (id) => document.getElementById(id);
  const state = { listings: [], cart: null, purchased: [], sellerListings: [], timer: null };

  document.querySelectorAll(".store-tab").forEach((button) => {
    button.addEventListener("click", async () => {
      document.querySelectorAll(".store-tab").forEach((item) => item.classList.toggle("active", item === button));
      const view = button.dataset.storeView;
      ["Market", "Purchased", "Seller"].forEach((name) => {
        $("storeView" + name).classList.toggle("hidden", name.toLowerCase() !== view);
      });
      if (view === "purchased") await loadPurchased();
      if (view === "seller") await loadSellerListings();
    });
  });

  async function loadAll() {
    await Promise.all([loadStats(), loadListings(), loadCart(), loadPaymentProviders()]);
  }

  async function loadStats() {
    try {
      const response = await fetch("/api/v1/store/stats");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "stats failed");
      $("storeStats").innerHTML = [
        [data.published_listings, "在售商品"],
        [data.free_listings, "免费"],
        [data.paid_listings, "付费"],
        [data.paid_orders, "已结算订单"],
        [data.entitlements, "授权凭证"],
        [data.downloads, "下载次数"],
      ].map(([value,label]) => `<div class="store-stat"><strong>${value}</strong><span>${label}</span></div>`).join("");
    } catch (error) {
      $("storeStats").innerHTML = `<div class="store-empty">商店统计加载失败：${escapeHtml(error.message)}</div>`;
    }
  }

  async function loadPaymentProviders() {
    try {
      const response = await fetch("/api/v1/store/payment/providers");
      const data = await response.json();
      const mock = (data.providers || []).find((item) => item.id === "mock");
      if (mock?.simulated) {
        $("storePaymentHint").textContent = `当前结算 Provider：Mock（模拟）${mock.paid_simulation_enabled ? "，允许模拟付费" : "，仅允许免费单"}。不会发生真实收款。`;
      }
    } catch (_) {}
  }

  async function loadListings() {
    const params = new URLSearchParams();
    const query = $("storeQuery").value.trim();
    const category = $("storeCategory").value;
    const license = $("storeLicenseFilter").value;
    const price = $("storePriceFilter").value;
    if (query) params.set("q", query);
    if (category) params.set("category", category);
    if (license) params.set("license_type", license);
    if (price === "free") params.set("free_only", "true");
    if (price === "featured") params.set("featured", "true");
    params.set("limit", "120");

    const grid = $("storeGrid");
    grid.innerHTML = `<div class="store-empty">加载商品…</div>`;
    try {
      const response = await fetch(`/api/v1/store/listings?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "listing search failed");
      state.listings = data.items || [];
      syncCategories();
      renderListings();
    } catch (error) {
      grid.innerHTML = `<div class="store-empty">商品加载失败：${escapeHtml(error.message)}</div>`;
    }
  }

  function syncCategories() {
    const select = $("storeCategory");
    const current = select.value;
    const categories = [...new Set(state.listings.map((item) => item.category).filter(Boolean))].sort();
    select.innerHTML = `<option value="">全部分类</option>` + categories.map((item) => `<option value="${escapeAttr(item)}">${escapeHtml(item)}</option>`).join("");
    if (categories.includes(current)) select.value = current;
  }

  function renderListings() {
    const grid = $("storeGrid");
    grid.innerHTML = "";
    if (!state.listings.length) {
      grid.innerHTML = `<div class="store-empty">暂无符合条件的商品。先到“创作者中心”把已审核素材上架。</div>`;
      return;
    }
    state.listings.forEach((listing) => {
      const card = document.createElement("article");
      card.className = `store-card${listing.featured ? " featured" : ""}`;
      card.innerHTML = `
        <div class="store-thumb"><img loading="lazy" src="/workspace/${escapeAttr(listing.preview_path)}?v=${encodeURIComponent(listing.updated_at)}" alt="${escapeAttr(listing.title)}" /></div>
        <div class="store-card-body">
          <div class="store-title">${listing.featured ? "★ " : ""}${escapeHtml(listing.title)}</div>
          <div class="store-seller">by ${escapeHtml(listing.seller_name)} · v${listing.asset_version} · S${Math.round((listing.asset_score || 0)*100)}</div>
          <div class="store-tags">${escapeHtml([listing.category, ...(listing.tags || []).slice(0,4)].join(" · "))}</div>
          <div class="store-license">${escapeHtml(listing.license_type)} · ${listing.purchase_count} 次购买 · ${listing.download_count} 次下载</div>
          <div class="store-price-row"><span class="store-price">${formatMoney(listing.price_minor, listing.currency)}</span><button data-cart-listing="${escapeAttr(listing.id)}">加入购物车</button></div>
        </div>`;
      card.querySelector("[data-cart-listing]").addEventListener("click", () => addToCart(listing.id));
      grid.appendChild(card);
    });
  }

  async function loadCart() {
    try {
      const response = await fetch("/api/v1/store/cart");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "cart failed");
      state.cart = data;
      renderCart();
    } catch (error) {
      $("storeCartItems").innerHTML = `<div class="store-warning">购物车加载失败：${escapeHtml(error.message)}</div>`;
    }
  }

  function renderCart() {
    const root = $("storeCartItems");
    const items = state.cart?.items || [];
    root.innerHTML = "";
    if (!items.length) root.innerHTML = `<div class="store-warning">购物车为空</div>`;
    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "store-cart-item";
      row.innerHTML = `<div><strong>${escapeHtml(item.listing.title)}</strong><br>${formatMoney(item.listing.price_minor,item.listing.currency)}</div><button>×</button>`;
      row.querySelector("button").addEventListener("click", () => removeFromCart(item.listing.id));
      root.appendChild(row);
    });
    $("storeCartTotal").textContent = formatMoney(state.cart?.total_minor || 0, state.cart?.currency || "CNY");
    $("storeCheckoutBtn").disabled = !items.length;
  }

  async function addToCart(listingId) {
    const response = await fetch(`/api/v1/store/cart/${encodeURIComponent(listingId)}`, { method:"POST" });
    const data = await response.json();
    if (!response.ok) return alert(data.detail || "加入购物车失败");
    state.cart = data;
    renderCart();
  }

  async function removeFromCart(listingId) {
    const response = await fetch(`/api/v1/store/cart/${encodeURIComponent(listingId)}`, { method:"DELETE" });
    const data = await response.json();
    if (!response.ok) return alert(data.detail || "移除失败");
    state.cart = data;
    renderCart();
  }

  $("storeCheckoutBtn").addEventListener("click", async () => {
    if (!state.cart?.items?.length) return;
    if (!confirm("这是 Mock 本地结算：不会真实扣款。继续生成订单和授权凭证？")) return;
    const button = $("storeCheckoutBtn");
    button.disabled = true;
    button.textContent = "结算中…";
    try {
      const response = await fetch("/api/v1/store/checkout", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ listing_ids:[], payment_provider:"mock" }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "checkout failed");
      alert(`订单 ${data.id} 已生成，获得 ${data.entitlements.length} 个授权。`);
      await Promise.all([loadCart(), loadStats(), loadListings(), loadPurchased()]);
    } catch (error) {
      alert(`结算失败：${error.message}`);
    } finally {
      button.disabled = false;
      button.textContent = "Mock 结算并授权";
    }
  });

  async function loadPurchased() {
    const root = $("storePurchases");
    root.innerHTML = `<div class="store-empty">加载已购素材…</div>`;
    try {
      const response = await fetch("/api/v1/store/library");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "purchased library failed");
      state.purchased = data.entitlements || [];
      root.innerHTML = "";
      if (!state.purchased.length) {
        root.innerHTML = `<div class="store-empty">还没有购买/领取素材。</div>`;
        return;
      }
      state.purchased.forEach((ent) => {
        const card = document.createElement("div");
        card.className = "store-purchase";
        card.innerHTML = `
          <strong>${escapeHtml(ent.asset_id)}</strong>
          <div class="store-seller">${escapeHtml(ent.license_type)} · Asset v${ent.asset_version}</div>
          <code>${escapeHtml(ent.id)}</code>
          <div class="store-actions" style="margin-top:9px"><a href="/api/v1/store/downloads/${encodeURIComponent(ent.id)}">下载授权 ZIP</a></div>`;
        root.appendChild(card);
      });
    } catch (error) {
      root.innerHTML = `<div class="store-empty">已购素材加载失败：${escapeHtml(error.message)}</div>`;
    }
  }

  $("storeUseSelectedAssetBtn").addEventListener("click", () => {
    const text = document.querySelector(".library-inspector-id")?.textContent || "";
    const match = text.match(/asset_[a-z0-9]+/i);
    if (!match) {
      $("storeSellerMessage").textContent = "请先在 Asset Library 中选择一个素材。";
      return;
    }
    $("storeSellerAssetId").value = match[0];
    $("storeSellerMessage").textContent = `已读取当前 Asset Library 素材：${match[0]}`;
  });

  $("storeCreateListingBtn").addEventListener("click", async () => {
    const assetId = $("storeSellerAssetId").value.trim();
    if (!assetId) return;
    const price = Math.round(Math.max(0, Number($("storeSellerPrice").value) || 0) * 100);
    const payload = {
      asset_id: assetId,
      title: $("storeSellerTitle").value.trim() || null,
      description: $("storeSellerDescription").value.trim(),
      price_minor: price,
      currency: "CNY",
      license_type: $("storeSellerLicense").value,
      seller_name: $("storeSellerName").value.trim() || "Local Creator",
      publish: $("storeSellerPublish").checked,
      featured: $("storeSellerFeatured").checked,
    };
    const button = $("storeCreateListingBtn");
    button.disabled = true;
    try {
      const response = await fetch("/api/v1/store/seller/listings", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "create listing failed");
      $("storeSellerMessage").textContent = `已创建商品 ${data.id} · ${data.status}`;
      await Promise.all([loadSellerListings(), loadListings(), loadStats()]);
    } catch (error) {
      $("storeSellerMessage").textContent = `上架失败：${error.message}`;
    } finally {
      button.disabled = false;
    }
  });

  async function loadSellerListings() {
    const root = $("storeSellerListings");
    root.innerHTML = `<div class="store-empty">加载我的商品…</div>`;
    try {
      const response = await fetch("/api/v1/store/seller/listings?limit=200");
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "seller listing failed");
      state.sellerListings = data.items || [];
      root.innerHTML = "";
      if (!state.sellerListings.length) {
        root.innerHTML = `<div class="store-empty">还没有商品。</div>`;
        return;
      }
      state.sellerListings.forEach((listing) => {
        const row = document.createElement("div");
        row.className = "store-seller-row";
        row.innerHTML = `
          <img src="/workspace/${escapeAttr(listing.preview_path)}?v=${encodeURIComponent(listing.updated_at)}" alt="" />
          <div><strong>${escapeHtml(listing.title)}</strong><div class="store-seller-meta">${escapeHtml(listing.status)} · ${formatMoney(listing.price_minor, listing.currency)} · ${escapeHtml(listing.license_type)} · v${listing.asset_version}</div></div>
          <div class="store-actions"><button data-toggle>${listing.status === "published" ? "下架" : "发布"}</button></div>`;
        row.querySelector("[data-toggle]").addEventListener("click", () => toggleListing(listing));
        root.appendChild(row);
      });
    } catch (error) {
      root.innerHTML = `<div class="store-empty">我的商品加载失败：${escapeHtml(error.message)}</div>`;
    }
  }

  async function toggleListing(listing) {
    const target = listing.status === "published" ? "archived" : "published";
    const response = await fetch(`/api/v1/store/seller/listings/${encodeURIComponent(listing.id)}`, {
      method:"PATCH",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({ status:target }),
    });
    const data = await response.json();
    if (!response.ok) return alert(data.detail || "商品状态更新失败");
    await Promise.all([loadSellerListings(), loadListings(), loadStats()]);
  }

  $("storeRefreshSellerBtn").addEventListener("click", loadSellerListings);
  $("storeQuery").addEventListener("input", () => {
    clearTimeout(state.timer);
    state.timer = setTimeout(loadListings, 240);
  });
  ["storeCategory","storeLicenseFilter","storePriceFilter"].forEach((id) => $(id).addEventListener("change", loadListings));

  function formatMoney(minor, currency) {
    if (minor === 0) return "免费";
    const amount = (Number(minor || 0) / 100).toFixed(2);
    if (currency === "CNY") return `¥${amount}`;
    if (currency === "USD") return `$${amount}`;
    return `${currency} ${amount}`;
  }

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
  }
  function escapeAttr(value) { return escapeHtml(value).replace(/`/g, "&#96;"); }

  loadAll();
})();
