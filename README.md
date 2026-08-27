# Game Creater

本地优先的游戏素材 AI 生产工具。当前主链已经跑通：

> 场景图片 → 目标词 → GroundingDINO 检测 → SAM2/SAM2.1 分割 → 透明 PNG + Mask → 人工校正 → Asset Score → `scene.json` / ZIP

项目保留 **Mock 模式** 作为无 GPU / 无模型环境下的回归测试后端；真实本地推理通过 `grounded_sam2_local` 适配器接入。

## 当前功能

- 上传 PNG / JPG / WEBP 场景图
- 输入目标关键词，例如 `tree, rock, house, crate, grass`
- Mock 模式完整验证产品链路
- 本地 GroundingDINO + SAM2/SAM2.1 真实检测与分割适配器
- 自动检查模型依赖、权重和设备状态
- 导出透明 RGBA PNG 与单资产 Mask
- 自动生成 `scene.json`
- 自动生成 Mask + BBox 场景 Overlay
- 保留原始源图，支持后续无模型人工编辑
- 素材名称、分类、备注编辑并持久化
- 删除错误素材并自动重建 Overlay
- 多选素材合并为一个新资产
- 用矩形区域把一个 Mask 拆成两个资产
- Scene Viewer 直接鼠标拖拽矩形，自动换算原图坐标
- Asset Score v0：结合检测置信度、面积、Mask 填充度与贴边完整度评分
- 一键打包下载当前场景 ZIP
- GitHub Actions 自动测试后端主链并检查前端 JavaScript 语法

## 项目结构

```text
game_creater/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ models.py
│  │  └─ services/
│  │     ├─ pipeline.py
│  │     ├─ grounded_sam2_local.py
│  │     ├─ scene_store.py
│  │     ├─ asset_editor.py
│  │     └─ asset_scoring.py
│  ├─ tests/
│  │  ├─ test_mock_pipeline.py
│  │  ├─ test_scene_store.py
│  │  ├─ test_asset_editor.py
│  │  └─ test_asset_scoring.py
│  ├─ requirements.txt
│  └─ requirements-dev.txt
├─ config/
│  └─ grounded_sam2.env.example
├─ scripts/
│  └─ setup_grounded_sam2_wsl.sh
├─ frontend/
│  ├─ index.html
│  ├─ app.js
│  └─ style.css
├─ model_weights/      # 本地模型权重，不提交 Git
├─ workspace/          # 运行时输出，不提交 Git
└─ README.md
```

## 1. Mock 模式验证产品链

Windows / PowerShell：

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

浏览器打开：

```text
http://127.0.0.1:8000
```

Mock 不做真实 AI 识别，但会真实执行：

```text
图片读取
→ Mask 生成
→ RGBA Alpha 合成
→ 单资产裁剪
→ PNG / Mask 导出
→ Asset Score
→ Overlay 生成
→ scene.json 生成
→ 删除 / 合并 / 拆分 / 元数据编辑
→ ZIP 打包
→ Web 前端展示
```

## 2. Grounded-SAM2 本地模式

真实模式使用：

```text
GroundingDINO
    ↓ bbox
SAM2 / SAM2.1
    ↓ mask
Game Creater pipeline
    ↓
RGBA PNG / Mask / Overlay / scene.json
    ↓
Asset Editor 人工校正
```

### 推荐环境

- WSL2 Ubuntu 或 Linux
- Python 3.10+
- PyTorch 2.3.1+
- 与 PyTorch 匹配的 CUDA Toolkit
- NVIDIA GPU 推荐

Windows 原生仍可运行前端和 Mock 后端；Grounded-SAM2 重模型层推荐放在 WSL2 / Linux。

### 安装

先根据显卡/CUDA，从 PyTorch 官方安装匹配的 `torch` 和 `torchvision`，然后在仓库根目录执行：

```bash
bash scripts/setup_grounded_sam2_wsl.sh
```

### 启动真实模式

```bash
export GAME_CREATER_MODE=grounded_sam2_local
export GAME_CREATER_DEVICE=auto
export GROUNDING_DINO_CONFIG="$HOME/.local/share/game_creater/Grounded-SAM-2/grounding_dino/groundingdino/config/GroundingDINO_SwinT_OGC.py"
export GROUNDING_DINO_CHECKPOINT="$HOME/.local/share/game_creater/Grounded-SAM-2/gdino_checkpoints/groundingdino_swint_ogc.pth"
export SAM2_MODEL_CONFIG="configs/sam2.1/sam2.1_hiera_l.yaml"
export SAM2_CHECKPOINT="$HOME/.local/share/game_creater/Grounded-SAM-2/checkpoints/sam2.1_hiera_large.pt"
export GAME_CREATER_BOX_THRESHOLD=0.35
export GAME_CREATER_TEXT_THRESHOLD=0.25

cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

环境变量示例见 `config/grounded_sam2.env.example`。

## 3. 人工校正

修改素材元数据：

```text
PATCH /api/v1/scenes/<scene_id>/assets/<asset_id>
```

删除错误素材：

```text
DELETE /api/v1/scenes/<scene_id>/assets/<asset_id>
```

合并多个素材：

```text
POST /api/v1/scenes/<scene_id>/assets/merge
```

矩形拆分一个 Mask：

```text
POST /api/v1/scenes/<scene_id>/assets/<asset_id>/split
```

前端支持直接在 Scene Viewer 拖拽矩形；显示坐标会自动映射回原图坐标并填入拆分参数。

## 4. Asset Score v0

当前评分范围为 `0–1`，暂时只做排序与筛选基础，不会自动删除素材。

组成：

```text
45% 检测置信度
25% 相对面积
15% Mask 填充度
15% 边界完整度
```

`scene.json` 中保存：

```json
{
  "asset_score": 0.78,
  "score_components": {
    "confidence": 0.80,
    "size": 1.0,
    "fill": 0.92,
    "completeness": 1.0,
    "area_ratio": 0.0512
  }
}
```

后续 Game Asset Ontology 会再加入“是否具有游戏素材语义价值”的评分维度。

## 5. 输出结构

```text
workspace/<scene_id>/
├─ source/
│  └─ source.png
├─ assets/
├─ masks/
├─ preview/
│  └─ overlay.png
└─ scene.json
```

完整场景：

```text
GET /api/v1/scenes/<scene_id>/export.zip
```

## 6. 输入 Prompt

GroundingDINO 更适合英文对象词，例如：

```text
tree, rock, house, crate, grass, barrel, fence
```

后续语义联想模块负责把中文素材概念自动映射成检测 Prompt。

## 7. 测试

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check ../frontend/app.js
```

CI 当前验证：

```text
输入图片
→ Detection
→ Mask
→ RGBA PNG
→ Asset Score
→ Overlay
→ scene.json
→ 元数据持久化
→ 删除素材
→ 合并 Mask
→ 矩形拆分 Mask
→ ZIP
→ 前端 JavaScript 语法
```

## 开发路线

### v0.1

- [x] 上传场景图
- [x] Asset 数据结构
- [x] 透明 PNG / Mask / JSON 导出
- [x] 最小 Web UI
- [x] GroundingDINO + SAM2/SAM2.1 本地适配层
- [x] 模型健康检查
- [x] Mock 回归测试 + CI
- [x] Scene Viewer 显示 bbox / Mask Overlay
- [x] 一键 ZIP 导出
- [ ] 目标 WSL + NVIDIA CUDA 环境真实图片实机验证

### v0.2

- [x] 素材重命名、分类、备注
- [x] 删除错误素材
- [x] 多素材 Mask 合并
- [x] 矩形拆分 Mask
- [x] Scene Viewer 鼠标拖拽框选拆分区域
- [x] 编辑后自动重建透明 PNG / Mask / Overlay / JSON
- [x] Asset Score v0
- [ ] SAM 点击添加 / 修正 Mask
- [ ] 多实例过滤与去重

### v0.3

- [ ] 本地游戏素材语义联想引擎
- [ ] Game Asset Ontology
- [ ] 中文关键词 → 检测 Prompt
- [ ] 图片反向推荐缺失素材

### 后续

- BiRefNet 边缘精修
- 遮挡检测与局部补全
- Depth 前景 / 中景 / 背景分层
- Unity / Godot 自动导出
- AI 生图 → 拆图 → 配置 → 场景完整流水线

## 设计原则

模型不是核心数据结构。检测器、分割器和补全模型通过适配层接入，核心业务只依赖统一的 `Detection / Mask / Asset / SceneManifest` 数据模型；人工校正与评分层也完全独立于推理模型。
