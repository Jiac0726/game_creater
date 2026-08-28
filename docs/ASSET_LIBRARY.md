# Asset Library

Game Creater 的 Asset Library 是游戏素材的全局管理层。它不是一个复制 PNG 的文件夹系统，而是：

```text
Scene / Project 文件
        ↓
稳定 Global Asset ID
        ↓
SQLite Metadata Index
        ↓
搜索 / 标签 / Collection / 审核 / 版本 / 关系 / 来源追踪
```

## 设计原则

1. **文件只保存一份**：素材 PNG、Mask、Alpha 继续位于原 Scene / Project 工作区，不因为加入多个 Collection 而复制。
2. **Scene ID 与全局 Asset ID 分离**：`asset_0001` 仍用于场景内部操作；`library_asset_id` 用于跨场景长期引用。
3. **编辑不覆盖历史**：BiRefNet 精修、AI 补全等结果作为 Asset Version 记录。
4. **删除不等于抹历史**：Scene 中移除的素材在 Library 中进入 `archived`。
5. **AI 结果需要审核**：新素材默认 `needs_review`，不会因为 Asset Score 高就自动批准。
6. **来源可追溯**：保留 Project、Scene、Source、Prompt、BBox、模型模式和评分组件等 provenance。

## SQLite Schema

当前数据库包含：

```text
assets
asset_versions
tags
asset_tags
collections
collection_assets
asset_relations
```

### assets

核心字段：

```text
id                  全局稳定 Asset ID
scene_id            来源 Scene
scene_asset_id      Scene 内局部 ID
project_id          来源 Project（如有）
name
category
subcategory
review_state
favorite
confidence
asset_score
width / height
image_path
mask_path
alpha_path
source_image_path
completed
active_version
notes
provenance_json
created_at / updated_at
```

## Global ID

拆图后：

```json
{
  "id": "asset_0001",
  "library_asset_id": "asset_a15c7fbb83a84190",
  "label": "tree"
}
```

即使将 `tree` 重命名为 `ancient mossy tree`，全局 ID 不变。

## Review State

```text
generated
needs_review
approved
production_ready
in_use
archived
```

目前新拆解素材默认进入：

```text
needs_review
```

Asset Score 只帮助排序和筛选，不自动删除或批准素材。

## Versions

初次拆解：

```text
v1 segmented
```

BiRefNet：

```text
v1 segmented
v2 birefnet_refined  ← active
```

BiRefNet 不再覆盖 v1 原 PNG。

AI 局部补全：

```text
v1 segmented        ← active
v2 ai_completed     ← 待审核
```

AI completion 默认 `activate=false`，避免生成像素未经确认就替换原始素材。

## Collections

Collection 是逻辑分组，不复制图片：

```text
asset_xxx
├─ Collection: Forest
├─ Collection: Magic Forest
├─ Collection: Vegetation
└─ Collection: Production Ready
```

## Relations

支持：

```text
parent_of
variant_of
derived_from
part_of
related_to
```

例如：

```text
wooden_crate_open --variant_of--> wooden_crate_closed
roof --part_of--> wooden_house
completed_tree --derived_from--> segmented_tree
```

## Search

API 支持组合筛选：

```text
q
category
review_state
collection_id
favorite
completed
min_score
tags
limit
offset
```

例如：

```text
GET /api/v1/library/assets?category=vegetation&min_score=0.7&tags=forest,moss
```

## API

```text
GET    /api/v1/library/stats
POST   /api/v1/library/reindex

GET    /api/v1/library/assets
GET    /api/v1/library/assets/<asset_id>
PATCH  /api/v1/library/assets/<asset_id>
POST   /api/v1/library/assets/bulk

GET    /api/v1/library/assets/<asset_id>/versions
GET    /api/v1/library/assets/<asset_id>/relations
POST   /api/v1/library/assets/<asset_id>/relations

GET    /api/v1/library/collections
POST   /api/v1/library/collections
POST   /api/v1/library/collections/<collection_id>/assets
DELETE /api/v1/library/collections/<collection_id>/assets/<asset_id>
```

## Historical Reindex

升级前已经存在的 Scene 可以直接重新索引：

```text
POST /api/v1/library/reindex
```

该过程：

- 扫描已有 `workspace/<scene_id>/scene.json`
- 给旧素材分配稳定 `library_asset_id`
- 建立 SQLite 索引
- 不复制 PNG / Mask

前端 Asset Library 中也提供 **重新索引历史 Scene** 按钮。

## Frontend Console

页面中的 `Asset Library · 游戏素材库` 提供：

```text
统计卡片
├─ 全部素材
├─ 待审核
├─ 已批准
├─ Production Ready
├─ AI 补全
└─ 收藏

搜索 / 筛选
├─ 名称
├─ 分类
├─ 审核状态
├─ Asset Score
├─ 标签
├─ 收藏
└─ Collection

Asset Grid
├─ 缩略图
├─ 名称
├─ 分类
├─ Asset Score
└─ Review State

Inspector
├─ Stable Asset ID
├─ Project / Scene 来源
├─ 名称 / 分类 / 子分类
├─ 标签 / 备注 / 收藏
├─ Review State
├─ 版本历史
├─ Provenance
└─ Asset Relations
```

## Bulk Management

素材卡支持多选，并可以：

- 批量改 Review State
- 批量收藏 / 取消收藏
- 批量添加标签
- 批量加入 Collection
- 本页全选

适合一次 AI 拆出几十到几百个素材后的集中审核。

## Scene / Library Consistency

Scene Editor 中改名、分类、删除、合并、拆分后，`SceneStore.save()` 会自动重新同步 Library。

Asset Library 中改名称 / 分类 / 备注后，也会同步回对应 `scene.json`，避免两个编辑入口互相覆盖。

## File Layout

素材文件仍位于原工作区：

```text
workspace/
├─ <scene_id>/
│  ├─ source/
│  ├─ assets/
│  ├─ masks/
│  ├─ versions/
│  ├─ completed/
│  └─ scene.json
└─ projects/
```

SQLite 是索引与元数据层，不是素材 Blob 存储。

## Deployment Note

当前 Game Creater 仍定位为本地优先工具，默认使用 `127.0.0.1` / localhost 工作流。不要把当前开发服务器直接暴露到公网。

桌面化 / 多用户部署阶段应进一步：

- 将 SQLite 迁入专用 private state 目录
- 增加用户权限与资源访问控制
- 增加数据库迁移版本（Alembic 或自定义 schema migration）
- 大规模素材库可将 metadata 后端切换至 PostgreSQL，同时保留相同 Asset Library API

## Next

Asset Library 下一阶段优先级：

1. 自动语义标签（从 Game Asset Ontology 写入 tags/category/subcategory）
2. 感知哈希 / CLIP Embedding 相似素材查重
3. 自然语言搜索
4. Approved completed version 一键提升为 Active Version
5. Unity / Godot 引用记录回写到 Library
6. Asset dependency / usage graph
