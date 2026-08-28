# Game Creater

本地优先的 AI 游戏素材生产、管理与交易工具。

```text
中文场景概念
→ 本地 Game Asset Ontology / Asset Plan
→ 大模型生图 Provider
→ 场景图自动回传
→ GroundingDINO 检测
→ bbox 去重
→ SAM2 / SAM2.1
→ Mask 去重
→ 透明 PNG / Mask / Overlay
→ Asset Library 全局入库
→ 人工删除 / 合并 / 拆分 / 重命名
→ SAM 正点 / 负点添加或修正 Mask
→ 可选 BiRefNet 边缘 Alpha 精修（版本化）
→ 可选 IOPaint / LaMa 局部补全（版本化、待审核）
→ Asset Store 上架 / 授权 / 下载
→ Scene Layout
→ Godot 4 / Unity 2D 导出
```

语义联想、Asset Library、Asset Store Mock 交易和 Mock 生图/拆图流程可完全离线运行。真实生图可接 OpenAI Image API；真实拆图使用本地 GroundingDINO + SAM2；BiRefNet 与 IOPaint 都作为可替换本地 sidecar。

完整 v1 流程文档：`docs/FULL_WORKFLOW.md`  
Asset Library 文档：`docs/ASSET_LIBRARY.md`  
Asset Store 文档：`docs/ASSET_STORE.md`

## 当前能力

### v1 AI 场景全流程

- 中文场景概念 → 本地 Asset Plan
- 根据 Asset Plan 自动构建“方便后续拆图”的生图 Prompt
- 可替换 ImageGenerationProvider
  - Mock：CI / 离线验证
  - OpenAI：默认 `gpt-image-2`
- 生图结果直接保存到 Project 并自动进入拆图，不需要浏览器重新上传
- Project 状态持久化：语义规划 / 生图 / 拆图 / 补全 / 导出
- `POST /api/v1/projects/run` 一次执行语义 → 生图 → 自动拆图

### Asset Library · 游戏素材库

每个拆出的素材都会自动进入全局素材库，并获得稳定的 `library_asset_id`。

Asset Library 采用：

```text
SQLite metadata/index
+
原 Scene / Project 文件系统
```

不会因为加入多个分类或 Collection 复制 PNG。

当前支持：

- Stable Global Asset ID
- 名称 / 分类 / 子分类 / 标签 / 备注
- Review State：`needs_review / approved / production_ready / in_use / archived`
- 收藏
- Asset Score 搜索与筛选
- Collection 逻辑分组
- Asset Relations：`parent_of / variant_of / derived_from / part_of / related_to`
- Provenance：Project / Scene / Source / Prompt / bbox / 推理模式 / Score components
- Asset Version 历史
- Scene 删除素材后 Library 自动归档，不抹除历史
- 历史 Scene 一键重新索引
- 批量审核 / 批量收藏 / 批量标签 / 批量加入 Collection
- Asset Library 网格 + Inspector 管理界面

版本策略：

```text
v1 segmented
v2 birefnet_refined
v3 ai_completed (默认不自动激活)
```

BiRefNet 与 AI 补全不会再直接覆盖最初的拆图历史。

### v1.1 Asset Store · 游戏素材商店

Asset Store 直接建立在 Asset Library 之上，不复制素材文件。

```text
Asset Library
→ Review / Production Ready
→ Store Listing
→ Storefront
→ Cart
→ Checkout Provider
→ Order
→ Entitlement
→ Version-locked ZIP Download
```

当前支持：

- `approved / production_ready / in_use` 素材公开上架
- `needs_review / archived` 禁止直接公开售卖，可保存 Draft
- Draft / Published / Archived 商品状态
- Personal / Commercial / Extended 三档授权
- 免费与付费定价
- 商品搜索、分类、授权类型、免费/精选筛选
- 创作者中心：从当前 Asset Library 选中素材直接上架
- 购物车
- 可替换 `StorePaymentProvider`
- Mock Checkout：只用于本地交易流程验证，不会真实收款
- Order / Order Items
- Entitlement 授权凭证
- 购买时冻结 Asset Version
- 已购素材库
- Entitlement-gated 下载
- 下载 ZIP：`asset.png / mask.png / alpha.png / metadata.json / LICENSE.txt`
- 销量 / 下载量 / 商店统计
- 商店私有状态保存到 `.game_creater_state/store.db`，不放在静态 `/workspace` 下

Mock 付费模拟可关闭：

```bash
export GAME_CREATER_ALLOW_MOCK_PAID=0
```

**当前版本是本地 Marketplace MVP，不是可直接公网运营的商城。**

## 快速启动：Mock

Windows PowerShell：

```powershell
git clone https://github.com/Jiac0726/game_creater.git
cd game_creater
git switch feat/v0.1-asset-split-mvp
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GAME_CREATER_MODE="mock"
uvicorn app.main:app --reload --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

页面包含：

```text
AI 场景全流程
Asset Editor
Asset Library
Asset Store
局部补全
Godot / Unity 导出
```

## API 总览

### 工作流

```text
POST /api/v1/projects/run
GET  /api/v1/projects/<project_id>
```

### Asset Library

```text
GET   /api/v1/library/stats
GET   /api/v1/library/assets
PATCH /api/v1/library/assets/<asset_id>
POST  /api/v1/library/assets/bulk
GET   /api/v1/library/assets/<asset_id>/versions
GET   /api/v1/library/assets/<asset_id>/relations
POST  /api/v1/library/reindex
```

### Asset Store

```text
GET    /api/v1/store/stats
GET    /api/v1/store/listings
GET    /api/v1/store/payment/providers
GET    /api/v1/store/seller/listings
POST   /api/v1/store/seller/listings
PATCH  /api/v1/store/seller/listings/<listing_id>
GET    /api/v1/store/cart
POST   /api/v1/store/cart/<listing_id>
DELETE /api/v1/store/cart/<listing_id>
POST   /api/v1/store/checkout
GET    /api/v1/store/orders
GET    /api/v1/store/library
GET    /api/v1/store/downloads/<entitlement_id>
```

## 部署边界

当前是 **localhost / local-first 开发工具**，不要直接把 FastAPI 开发服务器暴露到公网。

正式多用户商店至少还需要：

```text
身份认证 / RBAC
真正支付 Provider + Webhook
创作者分账
对象存储 / CDN / 签名下载
税务 / 发票 / 退款
授权条款
内容审核 / 投诉
多租户资源权限
```

## CI

Core CI 已覆盖：

- Semantic / Asset Plan
- Mock generation → automatic split
- GroundingDINO/SAM2 fake integration
- Asset Editor
- Asset Library 自动索引、标签、Collection、关系、版本、来源
- Library ↔ Scene 双向同步
- BiRefNet 版本化精修
- AI Completion 版本化
- Asset Store 上架规则
- Store search / cart / Mock checkout
- Order / Entitlement / version-locked download
- ZIP license / metadata
- Godot / Unity export
- Frontend JavaScript syntax
- Local AI helper scripts
