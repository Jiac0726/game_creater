# Game Creater

本地优先的游戏素材 AI 生产工具。当前已经形成三段式主链：

```text
中文场景概念
→ 本地 Game Asset Ontology 语义联想
→ GroundingDINO 英文检测 Prompt
→ GroundingDINO + SAM2/SAM2.1 图片拆解
→ 透明 PNG / Mask / Overlay
→ 人工删除 / 合并 / 拆分 / 重命名
→ Asset Score
→ 场景本体覆盖率 / 缺失素材推荐
→ scene.json / ZIP
```

语义联想模块与 Mock 模式均可**完全离线运行**，不依赖 ChatGPT、OpenAI API 或其他在线大模型服务。

## 当前功能

### v0.1 图片 AI 拆解

- 上传 PNG / JPG / WEBP 场景图
- GroundingDINO 开放词汇目标检测
- SAM2 / SAM2.1 Mask 分割
- Mock 后端用于无 GPU 回归测试
- 自动检查 torch / CUDA / 模型权重状态
- 导出透明 RGBA PNG 和单资产 Mask
- 自动生成 Mask + BBox Overlay
- 自动生成 `scene.json`
- 一键导出场景 ZIP

### v0.2 人工校正与素材管理

- 保留原始源图，编辑后无需重新跑 AI
- 修改素材名称、分类、备注并持久化
- 删除错误素材
- 多选 Mask 合并成一个新资产
- 矩形拆分一个 Mask 为两个资产
- Scene Viewer 鼠标拖拽矩形并自动换算原图坐标
- 编辑后自动重建透明 PNG / Mask / Overlay / JSON
- Asset Score v0：综合置信度、面积、Mask 填充度、边界完整度

### v0.3 本地游戏素材语义联想

- 自建 `Game Asset Ontology`
- 中文场景概念匹配
- 场景修饰词匹配，例如：废弃、魔法、赛博朋克、中世纪、雨天、雪地
- 按建筑 / 结构 / 道具 / 植被 / 地形 / 载具 / 生物 / 效果 / 材质分组
- 状态 + 游戏资产组合词生成
- 自动去重、排序和数量限制
- 自动生成 GroundingDINO 更适合使用的英文对象 Prompt
- Web UI 展示语义关键词树
- 一键“应用到拆图”
- 已上传图片时可“一键联想并拆图”
- 对已拆解场景计算本体素材覆盖率
- 自动列出“本体推荐但场景未检测到”的缺失素材
- 缺失素材可一键追加回 GroundingDINO Prompt
- 概念和修饰词目录 API

当前首批本体覆盖：

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

并可和修饰词组合，例如：

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
│  │     ├─ scene_store.py
│  │     ├─ asset_editor.py
│  │     ├─ asset_scoring.py
│  │     ├─ semantic_engine.py
│  │     └─ scene_recommender.py
│  ├─ tests/
│  │  ├─ test_mock_pipeline.py
│  │  ├─ test_scene_store.py
│  │  ├─ test_asset_editor.py
│  │  ├─ test_asset_scoring.py
│  │  ├─ test_semantic_engine.py
│  │  └─ test_scene_recommender.py
│  └─ requirements*.txt
├─ data/
│  └─ game_asset_ontology.json
├─ config/
│  └─ grounded_sam2.env.example
├─ scripts/
│  └─ setup_grounded_sam2_wsl.sh
├─ frontend/
│  ├─ index.html
│  ├─ app.js
│  ├─ semantic.js
│  ├─ style.css
│  └─ semantic.css
├─ model_weights/      # 不提交 Git
├─ workspace/          # 运行时数据，不提交 Git
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

浏览器打开：

```text
http://127.0.0.1:8000
```

Mock 不做真实 AI 识别，但语义联想和完整素材处理链都是真实逻辑：

```text
中文关键词联想
→ Prompt 生成
→ Mock Detection / Mask
→ RGBA PNG
→ Asset Score
→ Overlay
→ scene.json
→ 人工编辑
→ 缺失素材推荐
→ ZIP
```

## 2. 使用本地语义联想

页面顶部输入：

```text
废弃地铁站
```

点击：

```text
生成关键词组
```

系统会返回类似：

```text
结构：站台 / 轨道 / 隧道 / 楼梯 / 扶梯 / 通风井
道具：闸机 / 售票机 / 长椅 / 垃圾桶 / 路障 / 电缆
效果：灰尘 / 滴水 / 电火花 / 地下薄雾
状态变体：破损站台 / 生锈闸机 / ...
```

并自动准备英文检测 Prompt，例如：

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

- `应用到拆图`：写入下方 GroundingDINO Prompt 输入框
- `联想并拆图`：已上传图片时直接开始图片拆解
- 点击单个语义词：可手动添加/移除检测 Prompt
- `检查缺失素材`：拆图后比较当前场景资产与本体候选

展开深度：

```text
1：基础本体素材
2：少量状态组合，偏检测稳定
3：更多状态组合，偏素材策划/联想
```

### 语义 API

```text
GET  /api/v1/semantic/catalog
POST /api/v1/semantic/expand
```

请求示例：

```json
{
  "keyword": "魔法森林",
  "depth": 2,
  "max_per_group": 12
}
```

## 3. 场景覆盖率与缺失素材推荐

完成一次场景拆解后，可以调用：

```text
POST /api/v1/scenes/<scene_id>/recommendations
```

请求：

```json
{
  "keyword": "森林",
  "max_results": 20,
  "min_semantic_score": 0.65
}
```

响应包含：

```json
{
  "candidate_count": 23,
  "matched_count": 8,
  "coverage_ratio": 0.3478,
  "missing": [
    {
      "zh": "灌木",
      "en": "bush",
      "group": "vegetation",
      "semantic_score": 0.922
    }
  ]
}
```

推荐器只比较可独立检测/制作的实体组，并排除状态变体；会同时尝试匹配英文标签和用户改名后的中文标签。

缺失项在前端可直接点击加入 GroundingDINO Prompt，用于第二轮补充检测。

## 4. GroundingDINO + SAM2 本地真实模式

推荐环境：

- WSL2 Ubuntu / Linux
- Python 3.10+
- PyTorch 2.3.1+
- 匹配的 CUDA 环境
- NVIDIA GPU

先按显卡环境安装 PyTorch，然后执行：

```bash
bash scripts/setup_grounded_sam2_wsl.sh
```

启动示例：

```bash
export GAME_CREATER_MODE=grounded_sam2_local
export GAME_CREATER_DEVICE=auto
export GROUNDING_DINO_CONFIG="$HOME/.local/share/game_creater/Grounded-SAM-2/grounding_dino/groundingdino/config/GroundingDINO_SwinT_OGC.py"
export GROUNDING_DINO_CHECKPOINT="$HOME/.local/share/game_creater/Grounded-SAM-2/gdino_checkpoints/groundingdino_swint_ogc.pth"
export SAM2_MODEL_CONFIG="configs/sam2.1/sam2.1_hiera_l.yaml"
export SAM2_CHECKPOINT="$HOME/.local/share/game_creater/Grounded-SAM-2/checkpoints/sam2.1_hiera_large.pt"

cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

环境变量参考 `config/grounded_sam2.env.example`。

健康检查：

```text
GET /api/health
GET /api/v1/models/status
```

## 5. 人工校正 API

```text
PATCH  /api/v1/scenes/<scene_id>/assets/<asset_id>
DELETE /api/v1/scenes/<scene_id>/assets/<asset_id>
POST   /api/v1/scenes/<scene_id>/assets/merge
POST   /api/v1/scenes/<scene_id>/assets/<asset_id>/split
GET    /api/v1/scenes/<scene_id>/export.zip
```

## 6. Asset Score v0

当前只作为排序/过滤基础，不会自动删除素材。

```text
45% 检测置信度
25% 相对面积
15% Mask 填充度
15% 边界完整度
```

未来会加入：

```text
Game Asset Ontology 语义价值分
重复度
遮挡率
素材独立性
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

## 8. 测试与 CI

本地：

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check ../frontend/app.js
node --check ../frontend/semantic.js
```

GitHub Actions 当前验证：

```text
语义本体加载
→ 中文概念匹配
→ 修饰词与状态变体
→ 英文 Prompt 生成
→ 场景本体覆盖率 / 缺失素材推荐
→ Detection / Mask
→ RGBA PNG
→ Asset Score
→ Overlay
→ scene.json
→ 元数据持久化
→ 删除 / 合并 / 拆分
→ ZIP
→ 前端 JavaScript 语法
```

## 开发路线

### v0.1

- [x] 图片上传和 Detection / Mask 主链
- [x] GroundingDINO + SAM2/SAM2.1 本地适配层
- [x] PNG / Mask / Overlay / JSON / ZIP
- [x] 模型健康检查
- [x] Mock CI
- [ ] 目标 WSL + NVIDIA CUDA 实机真实图片验证

### v0.2

- [x] 素材重命名 / 分类 / 备注
- [x] 删除素材
- [x] 多 Mask 合并
- [x] 矩形拆分 Mask
- [x] Scene Viewer 鼠标拖拽拆分
- [x] Asset Score v0
- [ ] SAM 点击添加 / 修正 Mask
- [ ] 多实例过滤和去重

### v0.3

- [x] 本地 Game Asset Ontology
- [x] 本地中文语义联想引擎
- [x] 修饰词 + 素材状态组合
- [x] 中文关键词 → GroundingDINO Prompt
- [x] Web 关键词树
- [x] 一键应用 Prompt / 联想并拆图
- [x] 场景覆盖率和缺失素材推荐
- [ ] 扩充本体词库
- [ ] Embedding 候选召回层
- [ ] 把语义价值加入 Asset Score

### 后续

- BiRefNet 边缘精修
- 遮挡检测与局部补全
- Depth 前景 / 中景 / 背景分层
- Unity / Godot 自动导出
- AI 生图 → 拆图 → 配置 → 场景完整流水线

## 设计原则

模型不是核心数据结构。检测器、分割器、语义模型和补全模型都通过独立层接入；素材管理核心只依赖统一的 `Detection / Mask / Asset / SceneManifest` 数据模型。
