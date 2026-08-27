# Game Creater

本地优先的游戏素材 AI 生产工具。

当前主链：

```text
中文场景概念
→ 本地 Game Asset Ontology 语义联想
→ GroundingDINO 英文检测 Prompt
→ GroundingDINO 检测
→ Box 多实例去重
→ SAM2 / SAM2.1 分割
→ Mask 二次去重
→ 透明 PNG / Mask / Overlay
→ 人工删除 / 合并 / 拆分 / 重命名
→ SAM 正点 / 负点添加或精修 Mask
→ 语义增强 Asset Score
→ 场景覆盖率 / 缺失素材推荐
→ scene.json / ZIP
```

语义联想、素材管理和 Mock 测试链均可完全离线运行，不依赖 ChatGPT、OpenAI API 或在线大模型服务。真实图片拆解使用本地 GroundingDINO + SAM2/SAM2.1。

## 当前功能

### v0.1 图片 AI 拆解

- 上传 PNG / JPG / WEBP 场景图
- GroundingDINO 开放词汇目标检测
- SAM2 / SAM2.1 Mask 分割
- GroundingDINO bbox 置信度 + IoU 自动去重
- SAM Mask 高重合二次去重
- 去重统计写入 `scene.json -> inference_stats`
- Mock 后端用于无 GPU 回归测试
- 自动检查 torch / CUDA / 模型权重状态
- 导出透明 RGBA PNG 和单资产 Mask
- 自动生成 Mask + BBox Overlay
- 自动生成 `scene.json`
- 一键导出场景 ZIP

### v0.2 人工校正与素材管理

- 保留原始源图，编辑后无需重新跑 GroundingDINO
- 修改素材名称、分类、备注并持久化
- 删除错误素材
- 多选 Mask 合并成一个新资产
- 矩形拆分一个 Mask 为两个资产
- Scene Viewer 鼠标拖拽矩形并自动换算原图坐标
- SAM 正点 / 负点交互分割
- 正点表示目标、负点表示排除区域
- 可新建素材，也可用现有素材 bbox 辅助精修当前 Mask
- 编辑后自动重建透明 PNG / Mask / Overlay / JSON
- 语义增强 Asset Score：置信度 + 几何质量 + 本体语义价值
- 改名、合并、拆分、SAM 点修后保持统一资产数据结构

### v0.3 本地游戏素材语义联想

- 自建 `Game Asset Ontology`
- 中文场景概念匹配
- 场景修饰词匹配：废弃、魔法、赛博朋克、中世纪、雨天、雪地等
- 按建筑 / 结构 / 道具 / 植被 / 地形 / 载具 / 生物 / 效果 / 材质分组
- 状态 + 游戏资产组合词生成
- 自动去重、排序和数量限制
- 自动生成 GroundingDINO 适合使用的英文对象 Prompt
- Web UI 展示语义关键词树
- 一键“应用到拆图”
- 已上传图片时可“一键联想并拆图”
- 对已拆解场景计算本体素材覆盖率
- 自动列出“本体推荐但场景未检测到”的缺失素材
- 缺失素材可一键追加回 GroundingDINO Prompt
- Game Asset Ontology 参与 Asset Score 语义价值评分

首批本体覆盖：

```text
森林
地铁站
工厂
海边渔村
洞穴
城堡
酒馆
城市小巷
```

可组合：

```text
废弃地铁站
魔法森林
赛博朋克城市小巷
中世纪城堡
雨天城市小巷
雪地森林
```

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
│  │     ├─ scene_store.py
│  │     ├─ asset_editor.py
│  │     ├─ asset_scoring.py
│  │     ├─ semantic_engine.py
│  │     ├─ semantic_scoring.py
│  │     └─ scene_recommender.py
│  ├─ tests/
│  └─ requirements*.txt
├─ data/
│  └─ game_asset_ontology.json
├─ config/
│  └─ grounded_sam2.env.example
├─ docs/
│  └─ REAL_GPU_VALIDATION.md
├─ scripts/
│  ├─ setup_grounded_sam2_wsl.sh
│  ├─ verify_grounded_sam2_env.py
│  ├─ start_grounded_sam2_wsl.sh
│  ├─ smoke_test_grounded_sam2.py
│  └─ validate_scene_output.py
├─ frontend/
│  ├─ index.html
│  ├─ app.js
│  ├─ semantic.js
│  ├─ point_prompt.js
│  ├─ style.css
│  ├─ semantic.css
│  └─ point_prompt.css
├─ model_weights/       # 不提交 Git
├─ workspace/           # 运行时数据，不提交 Git
├─ validation_output/   # 真实模型验证输出，不提交 Git
└─ README.md
```

## 1. 最快启动：Mock 模式

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

浏览器：

```text
http://127.0.0.1:8000
```

Mock 不做真实 AI 识别，但会真实执行：

```text
中文关键词联想
→ Prompt 生成
→ Mock Detection / Mask
→ RGBA PNG
→ 语义增强 Asset Score
→ Overlay
→ scene.json
→ 删除 / 合并 / 拆分 / 元数据编辑
→ 缺失素材推荐
→ ZIP
```

## 2. 本地语义联想

页面顶部输入：

```text
废弃地铁站
```

系统会得到类似：

```text
结构：站台 / 轨道 / 隧道 / 楼梯 / 扶梯 / 通风井
道具：闸机 / 售票机 / 长椅 / 垃圾桶 / 路障 / 电缆
效果：灰尘 / 滴水 / 电火花 / 地下薄雾
```

并生成英文检测 Prompt：

```text
subway platform,
rail track,
subway tunnel,
ticket gate,
ticket machine,
station bench,
trash can,
barrier,
cable
```

操作：

- `应用到拆图`：写入 GroundingDINO Prompt
- `联想并拆图`：已有图片时直接开始拆解
- 点击单个语义词：手动添加/移除 Prompt
- `检查缺失素材`：对比场景资产和本体候选

展开深度：

```text
1：基础本体素材
2：少量状态组合，偏检测稳定
3：更多状态组合，偏素材策划/联想
```

语义 API：

```text
GET  /api/v1/semantic/catalog
POST /api/v1/semantic/expand
POST /api/v1/scenes/<scene_id>/recommendations
```

## 3. GroundingDINO + SAM2 本地真实模式

推荐：

- WSL2 Ubuntu / Linux
- Python 3.10+
- PyTorch 2.3.1+
- TorchVision 0.18.1+
- NVIDIA GPU
- WSL/Linux 内安装 CUDA Toolkit
- `CUDA_HOME` 指向包含 `bin/nvcc` 的 CUDA 目录

官方 Grounded-SAM-2 当前说明中，GroundingDINO 的 Deformable Attention 需要 CUDA 编译环境；因此“PyTorch 能看到 GPU”并不等于 GroundingDINO 可以成功安装。

### 3.1 安装

先按显卡环境安装 CUDA 版 PyTorch，然后：

```bash
bash scripts/setup_grounded_sam2_wsl.sh
```

脚本会：

```text
检查 Python / PyTorch / CUDA
检查 nvidia-smi
检查 CUDA_HOME / nvcc
拉取 Grounded-SAM-2
安装 SAM2 + GroundingDINO
下载权重
记录实际 Grounded-SAM-2 commit
生成 ~/.config/game_creater/grounded_sam2.env
执行环境验证
```

### 3.2 单独验证环境

```bash
python scripts/verify_grounded_sam2_env.py
```

### 3.3 启动

```bash
bash scripts/start_grounded_sam2_wsl.sh
```

打开：

```text
http://127.0.0.1:8000
```

### 3.4 用一张真实图片跑完整 smoke test

通过本体生成检测词：

```bash
python scripts/smoke_test_grounded_sam2.py \
  --image /mnt/c/path/to/scene.png \
  --keyword "废弃地铁站"
```

或者：

```bash
python scripts/smoke_test_grounded_sam2.py \
  --image /mnt/c/path/to/scene.png \
  --prompts "subway platform,ticket gate,ticket machine,bench,cable"
```

### 3.5 校验输出

Smoke test 会返回 `scene_dir`：

```bash
python scripts/validate_scene_output.py validation_output/<scene_id>
```

完整实机验收协议：

```text
docs/REAL_GPU_VALIDATION.md
```

## 4. 多实例 / 重复素材过滤

真实模式执行两层过滤：

```text
GroundingDINO
↓
bbox confidence + IoU 去重
↓
SAM2
↓
Mask IoU 二次去重
↓
最终资产
```

默认参数：

```text
GAME_CREATER_DEDUPE_IOU=0.65
GAME_CREATER_CROSS_LABEL_DEDUPE_IOU=0.92
GAME_CREATER_MASK_DEDUPE_IOU=0.86
GAME_CREATER_CROSS_LABEL_MASK_DEDUPE_IOU=0.96
```

统计会写入：

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

## 5. SAM 正点 / 负点人工修正

Scene Viewer 的 SAM 点提示模式：

```text
绿色点：目标 / 正点
红色点：背景 / 负点
```

用途：

- GroundingDINO 漏掉一个明显物体 → 正点创建新素材
- SAM Mask 多出背景 → 在错误区域放负点
- SAM Mask 少了一部分 → 在缺失部分放正点
- 精修已有素材时可同时使用当前素材 bbox 作为辅助提示

API：

```text
POST /api/v1/scenes/<scene_id>/assets/point-segment
```

其他人工校正 API：

```text
PATCH  /api/v1/scenes/<scene_id>/assets/<asset_id>
DELETE /api/v1/scenes/<scene_id>/assets/<asset_id>
POST   /api/v1/scenes/<scene_id>/assets/merge
POST   /api/v1/scenes/<scene_id>/assets/<asset_id>/split
GET    /api/v1/scenes/<scene_id>/export.zip
```

## 6. 语义增强 Asset Score

Asset Score 范围 `0–1`，用于排序、筛选和辅助判断，不会自动删除素材。

当前权重：

```text
35% 检测置信度
20% 相对面积
12% Mask 填充度
13% 边界完整度
20% Game Asset Ontology 语义价值
```

语义价值：

```text
本体精确资产词：1.00
已知资产的修饰/拆分形式：约 0.86
近似本体资产：0.64–0.78
当前本体未知资产：0.45（中性底分）
```

## 7. 输出结构

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

真实 CLI smoke test 默认写入：

```text
validation_output/<scene_id>/
```

## 8. 测试与 CI

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check ../frontend/app.js
node --check ../frontend/semantic.js
node --check ../frontend/point_prompt.js
```

Core CI 当前验证：

```text
语义本体加载
→ 中文概念 / 修饰词展开
→ 英文 Prompt
→ 本体语义评分
→ 场景覆盖率 / 缺失推荐
→ Detection / Mask
→ bbox 去重逻辑
→ Mask 去重逻辑
→ Grounded-SAM2 Fake adapter 集成
→ RGBA PNG
→ Asset Score
→ Overlay / scene.json
→ 删除 / 合并 / 拆分
→ SAM 正点 / 负点 Fake-SAM API
→ ZIP
→ 前端 JavaScript 语法
→ WSL/GPU helper shell/Python 脚本基本可执行性
```

## 开发路线

### v0.1

- [x] 图片上传和 Detection / Mask 主链
- [x] GroundingDINO + SAM2/SAM2.1 本地适配层
- [x] PNG / Mask / Overlay / JSON / ZIP
- [x] 模型健康检查
- [x] Mock CI
- [x] WSL2 GPU 安装 / 环境自检 / 启动 / smoke / 输出校验脚本
- [ ] 目标 WSL + NVIDIA CUDA 机器真实图片实机验证

### v0.2

- [x] 素材重命名 / 分类 / 备注
- [x] 删除素材
- [x] 多 Mask 合并
- [x] 矩形拆分 Mask
- [x] Scene Viewer 鼠标拖拽拆分
- [x] 语义增强 Asset Score
- [x] 多实例 bbox + Mask 双层去重
- [x] SAM 正点 / 负点添加和精修 Mask

### v0.3

- [x] 本地 Game Asset Ontology
- [x] 本地中文语义联想引擎
- [x] 修饰词 + 素材状态组合
- [x] 中文关键词 → GroundingDINO Prompt
- [x] Web 关键词树
- [x] 一键应用 Prompt / 联想并拆图
- [x] 场景覆盖率和缺失素材推荐
- [x] 本体语义价值接入 Asset Score
- [ ] 扩充本体词库
- [ ] Embedding 候选召回层

### 后续

- BiRefNet 边缘精修
- 遮挡检测与局部补全
- Depth 前景 / 中景 / 背景分层
- Unity / Godot 自动导出
- AI 生图 → 拆图 → 配置 → 场景完整流水线

## 设计原则

模型不是核心数据结构。检测器、分割器、语义模型和补全模型都通过独立层接入；素材管理核心只依赖统一的 `Detection / Mask / Asset / SceneManifest` 数据模型。
