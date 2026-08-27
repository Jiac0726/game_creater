# Game Creater

本地优先的游戏素材 AI 生产工具。当前 `v0.1` 先跑通最重要的一条链路：

> 场景图片 → 目标词 → 检测/分割 → 透明 PNG + Mask + `scene.json`

第一版默认使用 **Mock 模式**，目的是在安装 GroundingDINO / SAM2 之前，先验证上传、资产数据结构、透明图导出、Mask 导出和前端交互是否成立。

## 当前功能

- 上传 PNG / JPG / WEBP 场景图
- 输入目标关键词，例如 `tree, rock, house, crate, grass`
- 生成资产检测结果
- 导出透明 RGBA PNG
- 导出单资产 Mask
- 自动生成 `scene.json`
- 前端查看拆解素材并单独下载
- 预留 `grounded_sam2` 生产模型适配入口

## 项目结构

```text
game_creater/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ models.py
│  │  └─ services/
│  │     └─ pipeline.py
│  └─ requirements.txt
├─ frontend/
│  ├─ index.html
│  ├─ app.js
│  └─ style.css
├─ model_weights/      # 本地模型权重，不提交 Git
├─ workspace/          # 运行时输出，不提交 Git
└─ README.md
```

## Windows 本地启动

建议使用 Python 3.10+。

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

## Mock 模式说明

Mock 模式不会做真正的 AI 识别，而是根据输入的目标词生成可预测测试区域。它仍然会真实执行：

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

因此可以先确认整个产品主流程和数据规范。

## 输出结构

一次分析会生成：

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

`scene.json` 记录素材 ID、标签、置信度、bbox、源坐标、PNG 路径和 Mask 路径，后续用于 Unity / Godot 导出和场景重建。

## 下一阶段

### v0.1
- [x] 上传场景图
- [x] Asset 数据结构
- [x] 透明 PNG / Mask / JSON 导出
- [x] 最小 Web UI
- [ ] 接入 GroundingDINO
- [ ] 接入 SAM2 / SAM2.1
- [ ] 在原图上绘制真实检测框和 Mask Overlay

### v0.2
- [ ] 点击添加 / 删除目标
- [ ] Mask 合并与拆分
- [ ] 素材重命名和分类
- [ ] 批量 ZIP 导出

### v0.3
- [ ] 本地游戏素材语义联想引擎
- [ ] Game Asset Ontology
- [ ] 关键词自动生成检测 Prompt

### 后续
- BiRefNet 边缘精修
- 遮挡检测与局部补全
- Depth 分层
- Unity / Godot 自动导出
- AI 生图 → 拆图 → 配置 → 场景完整流水线

## 模型运行架构建议

开发机如果是 Windows，前端和业务后端可以直接运行在 Windows；GroundingDINO / SAM2 推理层建议后续放到 WSL2 或 Docker + NVIDIA CUDA 环境，通过本地 HTTP 接口连接。这样模型环境与桌面应用解耦，更容易维护和替换模型。

## 设计原则

模型不是核心数据结构。所有检测器、分割器和补全模型都应通过适配层接入，核心业务只依赖统一的 `Detection / Mask / Asset / SceneManifest` 数据模型，以便未来自由替换 GroundingDINO、SAM2 或其他模型。
