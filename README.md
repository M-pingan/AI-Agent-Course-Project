# 企业年报结构化提取智能体

这是一个面向课程作业题目 8 的项目仓库，目标是构建一个基于大语言模型的企业年报结构化提取智能体。

当前项目包含：

- 项目设计书
- 论文提纲
- 开发清单
- React + Vite 前端
- FastAPI 后端
- GitHub Pages + Render 部署配置

## 目录结构

- `docs/`
  - `project_design.md`：项目设计书
  - `paper_outline.md`：论文提纲
  - `development_checklist.md`：开发清单与验收说明
  - `deploy_github_pages_render.md`：部署步骤
- `frontend/`
  - React 前端页面
  - GitHub Pages 兼容构建配置
- `backend/`
  - FastAPI 后端接口
  - PDF 解析、规则抽取、Qwen 接口
  - `render.yaml`：Render 部署配置
- `.github/workflows/`
  - GitHub Pages 自动部署工作流

## 本地启动

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认地址：

- `http://127.0.0.1:8000`
- `http://127.0.0.1:8000/docs`

### 前端

```powershell
cd frontend
npm install
npm run dev
```

默认地址：

- `http://127.0.0.1:5173`

如需连接本地后端：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
```

## 百炼配置

后端通过环境变量接入阿里云百炼兼容接口：

```powershell
$env:QWEN_API_KEY="your_api_key"
$env:QWEN_BASE_URL="https://ws-nitmov1zmsy9pqre.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
$env:QWEN_MODEL="qwen-plus"
```

## 部署建议

当前项目建议采用前后端分离部署：

- 前端：`GitHub Pages`
- 后端：`Render`

完整步骤见：

- `docs/deploy_github_pages_render.md`

## 当前状态

当前仓库已经具备：

- 本地前后端可运行
- PDF 上传与结果查询接口
- JSON / CSV 导出
- 百炼兼容接口连通
- GitHub Pages 自动发布工作流
- Render 部署配置

## 注意事项

- 不要把真实的 `backend/.env` 提交到 GitHub
- 扫描版 PDF 仍可能需要 OCR
- 若作为课程最终提交，还需要补论文正文、实验截图和线上 URL
