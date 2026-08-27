# Game Creater

本地优先的游戏素材 AI 生产工具。当前目标是先稳定跑通：

> 场景图片 → 目标词 → GroundingDINO 检测 → SAM2/SAM2.1 分割 → 透明 PNG + Mask + `scene.json`

项目保留 **Mock 模式** 作为无 GPU / 无模型环境下的回归测试后端；真实本地推理已经接入 `grounded_sam2_local` 适配器。

## 当前功能

- 上传 PNG / JPG / WEBP 场景图
- 输入目标关键词，例如 `tree, rock, house, crate, grass`
- Mock 模式完整验证产品链路
- 本地 GroundingDINO + SAM2/SAM2.1 真实检测与分割适配器
- 自动检查模型依赖、权重和设备状态
- 导出透明 RGBA PNG
- 导出单资产 Mask
- 自动生成 `scene.json`
- 前端查看拆解素材并单独下载
- GitHub Actions 自动回归测试 Mock 主链

## 项目结构

```text
game_creater/
├─ backend/
│  ├─ app/
│  │  ├─ __init__.py
│  │  ├─ main.py
│  │  ├─ models.py
│  │  └─ services/
│  │     ├─ __init__.py
│  │     ├─ pipeline.py
│  │     └─ grounded_sam2_local.py
│  ├─ tests/
│  │  └─ test_mock_pipeline.py
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

## 1. 先用 Mock 模式验证产品链

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
→ PNG 导出
→ Mask 导出
→ scene.json 生成
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
RGBA PNG / Mask / scene.json
```

### 推荐环境

重模型部分建议：

- WSL2 Ubuntu 或 Linux
- Python 3.10+
- PyTorch 2.3.1+
- 与 PyTorch 匹配的 CUDA Toolkit
- NVIDIA GPU 推荐

Windows 原生仍可运行前端和 Mock 后端，但 Grounded-SAM2 官方对 Windows 更推荐 WSL。

### 安装

先根据你的显卡/CUDA，从 PyTorch 官方安装匹配的 `torch` 和 `torchvision`。

然后在仓库根目录执行：

```bash
bash scripts/setup_grounded_sam2_wsl.sh
```

脚本会：

1. 检查 PyTorch / TorchVision
2. Clone / 更新 `IDEA-Research/Grounded-SAM-2`
3. 安装 SAM2
4. 安装 GroundingDINO
5. 下载 SAM2 checkpoints
6. 下载 GroundingDINO checkpoint
7. 输出需要设置的环境变量

### 启动真实模式

假设脚本使用默认安装目录：

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

也可以参考：

```text
config/grounded_sam2.env.example
```

## 3. 模型健康检查

浏览器或 API 请求：

```text
GET /api/health
GET /api/v1/models/status
```

真实模式会检查：

- `torch`
- `sam2`
- `grounding_dino`
- GroundingDINO config
- GroundingDINO checkpoint
- SAM2 checkpoint
- SAM2 config
- CPU / CUDA 状态

模型未就绪时，前端会直接显示缺失项，并禁止启动拆解，避免进入推理后才报错。

## 4. 输入 Prompt

GroundingDINO 更适合英文对象词，例如：

```text
tree, rock, house, crate, grass, barrel, fence
```

后端会自动整理成 GroundingDINO 所需的点号分隔文本形式。

后续语义联想模块会负责把中文素材概念自动映射成检测 Prompt。

## 5. 输出结构

一次分析生成：

```text
workspace/<scene_id>/
├─ assets/
│  ├─ tree_001.png
│  └─ rock_001.png
├─ masks/
│  ├─ tree_001.png
│  └─ rock_001.png
└─ scene.json
```

`scene.json` 保存：

- asset ID
- label
- confidence
- bbox
- source position
- transparent PNG path
- mask path

这些数据后续用于 Unity / Godot 导出和场景重建。

## 6. 测试

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

当前测试不下载 AI 权重，只测试 Mock 主链，因此 GitHub Actions 可以稳定验证：

```text
输入图片
→ Detection
→ Mask
→ RGBA PNG
→ scene.json
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
- [ ] Scene Viewer 显示真实 bbox / Mask Overlay
- [ ] 一键 ZIP 导出

### v0.2

- [ ] 点击添加 / 删除目标
- [ ] Mask 合并与拆分
- [ ] 素材重命名和分类
- [ ] 多实例过滤与去重
- [ ] Asset Score

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

模型不是核心数据结构。检测器、分割器和补全模型都通过适配层接入，核心业务只依赖统一的 `Detection / Mask / Asset / SceneManifest` 数据模型。

这样未来可以替换 GroundingDINO、SAM2、BiRefNet 或其他模型，而不重写素材管理和导出逻辑。
