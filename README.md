# Game Creater

本地优先的 AI 游戏素材生产与管理工具。

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
→ Scene Layout
→ Godot 4 / Unity 2D 导出
```

语义联想、Asset Library、Mock 生图/拆图流程可完全离线运行。真实生图可接 OpenAI Image API；真实拆图使用本地 GroundingDINO + SAM2；BiRefNet 与 IOPaint 都作为可替换本地 sidecar。

完整 v1 流程文档：`docs/FULL_WORKFLOW.md`  
Asset Library 文档：`docs/ASSET_LIBRARY.md`

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
- Review State
  - `needs_review`
  - `approved`
  - `production_ready`
  - `in_use`
  - `archived`
- 收藏
- Asset Score 搜索与筛选
- Collection 逻辑分组
- Asset Relations
  - `parent_of`
  - `variant_of`
  - `derived_from`
  - `part_of`
  - `related_to`
- Provenance 来源追踪
  - Project
  - Scene
  - Source image
  - Prompt
  - bbox
  - 推理模式
  - Score components
- Asset Version 历史
- Scene 删除素材后 Library 自动归档，不抹除历史
- 历史 Scene 一键重新索引
- 批量审核 / 批量收藏 / 批量标签 / 批量加入 Collection
- Asset Library 网格 + Inspector 管理界面

版本策略：

```text
v1 segmented
v2 birefnet_refined     ← 精修后可成为 active
v3 ai_completed         ← 默认待审核，不静默替换原始素材
```

BiRefNet 现在不会覆盖原始 PNG；精修结果写入 `versions/` 并记录到 SQLite。IOPaint / LaMa 补全结果同样作为独立版本保存，原始素材保留。

Asset Library API：

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
```

详细说明：`docs/ASSET_LIBRARY.md`。

### v0.1 图片 AI 拆解

- PNG / JPG / WEBP 场景上传
- GroundingDINO 开放词汇检测
- SAM2 / SAM2.1 分割
- bbox confidence + IoU 去重
- Mask IoU 二次去重
- `scene.json -> inference_stats` 记录去重前后数量
- 透明 RGBA PNG / Mask / Overlay / ZIP
- 模型健康检查
- Mock 后端 + CI

### v0.2 人工校正

- 名称 / 分类 / 备注持久化
- 删除错误素材
- 多 Mask 合并
- 矩形拆分 Mask
- Scene Viewer 拖拽拆分区域
- SAM 正点 / 负点新建素材
- SAM 正点 / 负点精修已有素材
- 编辑后自动重建 PNG / Mask / Overlay / JSON
- 语义增强 Asset Score

### v0.3 本地语义联想

- 自建 Game Asset Ontology
- 中文场景概念与修饰词匹配
- 建筑 / 结构 / 道具 / 植被 / 地形 / 载具 / 生物 / 效果 / 材质分组
- 状态 + 资产组合词
- 中文概念 → GroundingDINO 英文对象 Prompt
- Web 关键词树
- 一键“应用到拆图” / “联想并拆图”
- 场景本体覆盖率
- 缺失素材推荐
- 本体语义价值接入 Asset Score

首批本体：

```text
森林 / 地铁站 / 工厂 / 海边渔村 / 洞穴 / 城堡 / 酒馆 / 城市小巷
```

### v0.4 BiRefNet 边缘精修

BiRefNet 不直接替换 SAM 的对象归属判断，只参与 **SAM 边界带** 的软 Alpha：

```text
SAM 二值 Mask
→ 膨胀 / 腐蚀得到边界带
→ BiRefNet 预测前景 Alpha
→ 只在边界带采用 BiRefNet
→ SAM 核心区域保持不变
→ 新建 birefnet_refined Asset Version
```

设计约束：

- 硬 `mask` 不变
- bbox 不变
- 原始 segmented PNG 不覆盖
- 合并 / 拆分仍使用硬 Mask
- 默认关闭
- 独立 Python sidecar 环境
- sidecar 只收发内存 PNG(base64)，不接受任意本地文件路径

## 项目结构

```text
game_creater/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ models.py
│  │  ├─ workflow_models.py
│  │  ├─ workflow_api.py
│  │  ├─ asset_library_models.py
│  │  ├─ asset_library_api.py
│  │  └─ services/
│  │     ├─ pipeline.py
│  │     ├─ grounded_sam2_local.py
│  │     ├─ detection_filter.py
│  │     ├─ asset_editor.py
│  │     ├─ asset_library.py
│  │     ├─ asset_library_sync.py
│  │     ├─ asset_scoring.py
│  │     ├─ semantic_engine.py
│  │     ├─ prompt_builder.py
│  │     ├─ generation_providers.py
│  │     ├─ completion_service.py
│  │     ├─ completion_providers.py
│  │     ├─ birefnet_sidecar.py
│  │     ├─ edge_refinement.py
│  │     ├─ godot_exporter.py
│  │     └─ unity_exporter.py
│  ├─ tests/
│  └─ requirements*.txt
├─ birefnet_worker/
├─ data/game_asset_ontology.json
├─ docs/
│  ├─ FULL_WORKFLOW.md
│  ├─ ASSET_LIBRARY.md
│  └─ REAL_GPU_VALIDATION.md
├─ scripts/
├─ frontend/
│  ├─ app.js
│  ├─ semantic.js
│  ├─ workflow.js
│  ├─ asset_library.js
│  ├─ completion.js
│  ├─ point_prompt.js
│  ├─ edge_refine.js
│  └─ engine_export.js
├─ workspace/
└─ validation_output/
```

## 1. 最快启动：Mock

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

可直接用 Mock 模式验证：

```text
语义联想
→ Mock 生图
→ 自动拆图
→ Asset Library 自动入库
→ 编辑 / 版本 / Collection / 批量管理
→ Godot / Unity 导出
```

## 2. 真实生图 + GroundingDINO + SAM2

OpenAI 生图 Provider：

```bash
export OPENAI_API_KEY="..."
export GAME_CREATER_OPENAI_IMAGE_MODEL="gpt-image-2"
```

推荐 WSL2 Ubuntu / Linux + NVIDIA GPU 运行真实拆图。

```bash
bash scripts/setup_grounded_sam2_wsl.sh
python scripts/verify_grounded_sam2_env.py
bash scripts/start_grounded_sam2_wsl.sh
```

真实图片 smoke test：

```bash
python scripts/smoke_test_grounded_sam2.py \
  --image /mnt/c/path/to/scene.png \
  --keyword "废弃地铁站"
```

完整协议：`docs/REAL_GPU_VALIDATION.md`。

## 3. IOPaint / LaMa 局部补全

```bash
bash scripts/setup_iopaint_sidecar.sh
bash scripts/start_iopaint_sidecar.sh
```

原始素材不会被补全结果覆盖；补全输出进入 Asset Version 历史并等待审核。

## 4. 多实例去重

```text
GAME_CREATER_DEDUPE_IOU=0.65
GAME_CREATER_CROSS_LABEL_DEDUPE_IOU=0.92
GAME_CREATER_MASK_DEDUPE_IOU=0.86
GAME_CREATER_CROSS_LABEL_MASK_DEDUPE_IOU=0.96
```

## 5. SAM 正点 / 负点修正

```text
绿色点：包含目标
红色点：排除背景
```

API：

```text
POST /api/v1/scenes/<scene_id>/assets/point-segment
```

## 部署说明

当前版本定位为 localhost / 本地优先开发工具。不要直接将开发服务器暴露到公网。

桌面化 / 多用户阶段将进一步处理：

- SQLite 迁至专用 private state 目录
- 用户权限 / 资源访问控制
- Schema migration
- 大规模库可切换 PostgreSQL

## 当前验证

Core CI 覆盖：

- Game Asset Ontology / Semantic Engine / Prompt Builder
- Mock 生图 → 自动回传 → 自动拆图
- GroundingDINO / SAM2 Mock 与 Fake integration
- bbox / Mask 去重
- Asset Score
- Scene / Project persistence
- Asset Library 自动入库和稳定 Global ID
- Library ↔ Scene 元数据同步
- 标签 / 搜索 / Review State / Collection / Relations
- Asset Versions / Archive
- Project provenance
- AI Completion version（不自动覆盖 Active Version）
- BiRefNet version（原 segmented PNG 保留）
- Godot / Unity 导出
- 前端 JavaScript syntax
- 本地 AI helper scripts

真实 NVIDIA / WSL2 / OpenAI API / BiRefNet / IOPaint 的生产质量仍需在目标机器与代表性 AI 游戏场景上实测。
