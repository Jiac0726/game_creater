# Game Creater

本地优先的游戏素材 AI 生产工具。

```text
中文场景概念
→ 本地 Game Asset Ontology
→ GroundingDINO 英文 Prompt
→ GroundingDINO 检测
→ bbox 去重
→ SAM2 / SAM2.1
→ Mask 去重
→ 透明 PNG / Mask / Overlay
→ 人工删除 / 合并 / 拆分 / 重命名
→ SAM 正点 / 负点添加或修正 Mask
→ 可选 BiRefNet 边缘 Alpha 精修
→ 语义增强 Asset Score
→ 场景覆盖率 / 缺失素材推荐
→ scene.json / ZIP
```

语义联想、素材管理和 Mock 流程均可完全离线运行，不依赖 ChatGPT、OpenAI API 或在线大模型服务。真实拆图使用本地 GroundingDINO + SAM2；BiRefNet 是独立可选 sidecar。

## 当前能力

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
→ 重写透明 PNG Alpha
```

设计约束：

- 硬 `mask` 不变
- bbox 不变
- 合并 / 拆分仍使用硬 Mask
- BiRefNet 失败不会破坏几何数据
- 默认关闭
- 独立 Python sidecar 环境
- sidecar 只收发内存 PNG(base64)，不接受任意本地文件路径

之所以独立运行，是因为 BiRefNet 官方当前依赖包含 `numpy<2`、`torch>=2.5.0`，而主后端当前使用 NumPy 2.x；分离环境可避免依赖冲突。

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
│  │     ├─ detection_filter.py
│  │     ├─ asset_editor.py
│  │     ├─ asset_scoring.py
│  │     ├─ semantic_engine.py
│  │     ├─ semantic_scoring.py
│  │     ├─ scene_recommender.py
│  │     ├─ birefnet_sidecar.py
│  │     └─ edge_refinement.py
│  ├─ tests/
│  └─ requirements*.txt
├─ birefnet_worker/
│  ├─ server.py
│  └─ requirements.txt
├─ data/game_asset_ontology.json
├─ config/grounded_sam2.env.example
├─ docs/REAL_GPU_VALIDATION.md
├─ scripts/
│  ├─ setup_grounded_sam2_wsl.sh
│  ├─ verify_grounded_sam2_env.py
│  ├─ start_grounded_sam2_wsl.sh
│  ├─ smoke_test_grounded_sam2.py
│  ├─ validate_scene_output.py
│  ├─ setup_birefnet_sidecar.sh
│  └─ start_birefnet_sidecar.sh
├─ frontend/
│  ├─ app.js
│  ├─ semantic.js
│  ├─ point_prompt.js
│  ├─ edge_refine.js
│  └─ ...
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

## 2. GroundingDINO + SAM2 真实模式

推荐：WSL2 Ubuntu / Linux + NVIDIA GPU。

Grounded-SAM-2 当前官方安装说明要求 Python 3.10、torch >= 2.3.1、torchvision >= 0.18.1，并强调 GroundingDINO 的 Deformable Attention 需要 CUDA 编译环境。因此 `torch.cuda.is_available()==True` 并不等于 GroundingDINO 一定能编译。

先安装与显卡匹配的 CUDA 版 PyTorch，然后：

```bash
bash scripts/setup_grounded_sam2_wsl.sh
```

脚本会检查：

```text
Python
PyTorch / TorchVision
nvidia-smi
CUDA_HOME
nvcc
GroundingDINO config / checkpoint
SAM2 checkpoint
```

并生成：

```text
~/.config/game_creater/grounded_sam2.env
```

环境验证：

```bash
python scripts/verify_grounded_sam2_env.py
```

启动：

```bash
bash scripts/start_grounded_sam2_wsl.sh
```

真实图片 smoke test：

```bash
python scripts/smoke_test_grounded_sam2.py \
  --image /mnt/c/path/to/scene.png \
  --keyword "废弃地铁站"
```

输出校验：

```bash
python scripts/validate_scene_output.py validation_output/<scene_id>
```

完整协议：`docs/REAL_GPU_VALIDATION.md`。

## 3. 多实例去重

默认：

```text
GAME_CREATER_DEDUPE_IOU=0.65
GAME_CREATER_CROSS_LABEL_DEDUPE_IOU=0.92
GAME_CREATER_MASK_DEDUPE_IOU=0.86
GAME_CREATER_CROSS_LABEL_MASK_DEDUPE_IOU=0.96
```

`scene.json` 示例：

```json
{
  "inference_stats": {
    "raw_detections": 18,
    "valid_detections": 18,
    "after_box_dedupe": 13,
    "after_mask_dedupe": 11,
    "box_duplicates_removed": 5,
    "mask_duplicates_removed": 2
  }
}
```

## 4. SAM 正点 / 负点修正

```text
绿色点：包含目标
红色点：排除背景
```

API：

```text
POST /api/v1/scenes/<scene_id>/assets/point-segment
```

可用于：

- GroundingDINO 漏检 → 新建素材
- Mask 多出背景 → 负点
- Mask 缺失部分 → 正点
- 现有素材精修 → 正点/负点 + 现有 bbox

## 5. BiRefNet 可选 sidecar

官方 BiRefNet 代码为 MIT License。当前 sidecar 默认模型：

```text
ZhengPeng7/BiRefNet_HR-matting
```

安装：

```bash
bash scripts/setup_birefnet_sidecar.sh
```

脚本会：

- 创建独立 venv
- 安装 BiRefNet 依赖
- 从 Hugging Face 解析模型具体 revision SHA
- 下载并缓存该固定 revision
- 运行时强制 `local_files_only=1`
- 生成 `~/.config/game_creater/birefnet.env`

启动 sidecar：

```bash
bash scripts/start_birefnet_sidecar.sh
```

然后重启主后端：

```bash
bash scripts/start_grounded_sam2_wsl.sh
```

主后端会自动读取可选的 `birefnet.env`。

状态：

```text
GET /api/v1/edge-refiner/status
```

精修当前素材：

```text
POST /api/v1/scenes/<scene_id>/assets/<asset_id>/refine-edge
```

请求：

```json
{ "radius": 6 }
```

前端也提供 `BiRefNet 精修当前素材` 按钮；sidecar 未启动时自动禁用。

## 6. 语义增强 Asset Score

```text
35% 检测置信度
20% 相对面积
12% Mask 填充度
13% 边界完整度
20% Game Asset Ontology 语义价值
```

未知资产保留中性语义底分，不会因为本体尚未收录就被自动删除。

## 7. 主要 API

```text
GET  /api/v1/semantic/catalog
POST /api/v1/semantic/expand
POST /api/v1/scenes/analyze
POST /api/v1/scenes/<scene_id>/recommendations
POST /api/v1/scenes/<scene_id>/assets/point-segment
POST /api/v1/scenes/<scene_id>/assets/<asset_id>/refine-edge
PATCH /api/v1/scenes/<scene_id>/assets/<asset_id>
DELETE /api/v1/scenes/<scene_id>/assets/<asset_id>
POST /api/v1/scenes/<scene_id>/assets/merge
POST /api/v1/scenes/<scene_id>/assets/<asset_id>/split
GET /api/v1/scenes/<scene_id>/export.zip
```

## 8. 测试与 CI

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Core CI 当前覆盖：

```text
语义本体 / 中文扩展 / 英文 Prompt
场景覆盖率 / 缺失素材推荐
GroundingDINO bbox 去重
SAM Mask 去重
Fake Grounded-SAM2 适配器
RGBA / Mask / Overlay / JSON / ZIP
改名 / 删除 / 合并 / 拆分
SAM 正点 / 负点 Fake-SAM API
Fake-BiRefNet 边缘 Alpha 精修
前端 app / semantic / point_prompt / edge_refine JS 语法
Grounded-SAM2 与 BiRefNet setup/start 脚本语法
BiRefNet worker Python 语法
```

## 开发路线

### 已完成代码

- [x] v0.1 图片拆解主链
- [x] v0.2 人工校正 + 双层去重 + SAM 点修
- [x] v0.3 本地语义联想 + 缺失素材推荐
- [x] v0.4 可选 BiRefNet 边缘 Alpha 精修 sidecar

### 待实机验证

- [ ] WSL2 + NVIDIA 真实 GroundingDINO/SAM2 场景图
- [ ] BiRefNet HR-matting 真实游戏素材边缘效果
- [ ] 不同去重阈值的真实场景统计

### 下一阶段

- 扩充 Game Asset Ontology
- Embedding 候选召回
- 遮挡检测与局部补全
- Depth 前景 / 中景 / 背景分层
- Unity / Godot 自动导出
- AI 生图 → 拆图 → 配置 → 场景完整流水线

## 设计原则

模型不是核心数据结构。检测器、分割器、语义模型、边缘精修模型和后续补全模型都通过独立适配层接入；素材管理核心只依赖统一的 `Detection / Mask / Asset / SceneManifest` 数据结构。
