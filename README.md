# Alpha CEX x DEX 共振研究项目

这个仓库是对 CLO 共振研究工作区做过整理后的版本。目标是把可复用代码、研究文档、映射配置和生成产物分开管理，让仓库本身保持清爽，同时保留后续继续复现和扩展研究的能力。

## 目录结构

```text
.
├── config/
│   ├── alpha_symbol_map.json
│   └── alpha_usdt_symbol_map_compact.json
├── backend/
│   ├── app.py
│   └── requirements.txt
├── docs/
│   └── research/
│       ├── alpha-dex-onchain-fields.md
│       ├── cex-fields.md
│       └── resonance-factor-framework.md
├── frontend/
│   ├── src/
│   ├── index.html
│   └── vite.config.js
├── scripts/
│   ├── backtest_dashboard_data.py
│   ├── build_dashboard_cache.py
│   └── run_short_book_resonance_divergence_universe_backtest.py
├── src/
│   ├── clo_execution_compare/
│   │   ├── __init__.py
│   │   ├── backtest.py
│   │   └── build_signal_layers.py
│   └── short_book_resonance_divergence/
│       ├── __init__.py
│       └── backtest.py
└── outputs/
```

`outputs/` 目录默认不纳入 Git。回测结果、导出的 CSV、汇总 JSON、前端使用的 JS 数据文件都建议统一放在这里。

## 环境依赖

当前仓库里的 Python 脚本主要依赖：

- `duckdb`
- `numpy`
- `pandas`

安装基础依赖可以直接使用：

```bash
pip install -r requirements.txt
```

后端接口如果要启动，还需要安装：

```bash
pip install -r backend/requirements.txt
```

## 数据访问配置

脚本依赖 RustFS / S3 兼容存储中的原始数据。当前通过环境变量读取访问配置：

- `ALPHA_S3_KEY_ID`
- `ALPHA_S3_SECRET`
- `ALPHA_S3_REGION`
- `ALPHA_S3_ENDPOINT`
- `ALPHA_S3_URL_STYLE`
- `ALPHA_S3_USE_SSL`

其中以下两个是必填的：

- `ALPHA_S3_KEY_ID`
- `ALPHA_S3_SECRET`

## 使用方式

### 1. 运行 CLO 执行对比回测

```bash
python3 src/clo_execution_compare/backtest.py \
  --date 2026-06-11 \
  --cex-pair-key clousdt \
  --dex-symbol alpha_429usdt
```

默认输出目录：

```text
outputs/clo_20260611_tick3600ms_execution_compare/
```

### 2. 生成前端可用的信号层 JS 数据

```bash
python3 src/clo_execution_compare/build_signal_layers.py
```

默认输出文件：

```text
outputs/web/clo_20260611_signal_layers.js
```

### 3. 重建 dashboard 缓存

```bash
python3 scripts/build_dashboard_cache.py
```

### 4. 启动本地后端接口

```bash
uvicorn backend.app:app --reload
```

### 5. 启动前端看板

```bash
cd frontend
npm install
npm run dev
```

## 模块说明

- `src/clo_execution_compare/`：CLO 执行对比研究主模块，包含回测逻辑和前端数据构建脚本。
- `src/short_book_resonance_divergence/`：另一套 short 策略研究模块。
- `scripts/`：围绕回测结果做缓存整理、脚本入口封装等辅助工具。
- `backend/`：基于 FastAPI 的轻量接口服务，给前端提供回测看板数据。
- `frontend/`：基于 Vite + Vue 的可视化面板。
- `docs/research/`：研究框架、字段定义、数据说明文档。
- `config/`：symbol 映射、token 配置等静态映射文件。

## 备注

- 仓库主要保留源码、配置和研究说明，不保留大体量生成结果。
- 历史输出目录仍然在本地磁盘上，但已经通过 `.gitignore` 忽略。
- 后续如果要增加新策略，建议直接在 `src/` 下新增独立模块，并把输出统一写到 `outputs/<strategy-name>/`。
