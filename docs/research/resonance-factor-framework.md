# CEX × DEX 共振放量因子研究框架

> 创建时间：2026-06-10
> 数据来源：RustFS S3 (Binance CEX trade/book_ticker + BSC DEX onchain_swap/onchain_pair_state_block)

---

## 一、数据结构

### 1.1 CEX 数据（订单簿 + 成交）

| 序号 | 字段 | 含义 | 精度 |
|---:|---|---|---|
| 1 | `recv_timestamp_ns` | 采集服务器收到WebSocket消息的纳秒时间戳 | **纳秒** |
| 2 | `trade_timestamp_ms` | 成交真实发生时间，毫秒时间戳 | 毫秒 |
| 3 | `event_timestamp_ms` | 交易所推送时间，毫秒时间戳 | 毫秒 |
| 4 | `symbol` | 交易对符号 | - |
| 5 | `price` | 成交价格 | - |
| 6 | `quantity` | 成交数量 | - |
| 7 | `side` | 成交方向，写入 `BUY` / `SELL` | - |
| 8 | `bid_price` / `ask_price` | 最优买一价 / 卖一价（仅book_ticker有） | - |
| 9 | `bid_qty` / `ask_qty` | 最优买一量 / 卖一量（仅book_ticker有） | - |

**存储路径（RustFS S3）：**
```
crypto-alpha/raw/exchange=binance/symbol={alpha_symbol}/data_type={trade|book_ticker}/date={YYYY-MM-DD}/hour={HH}/{fileName}.csv.zst
```

**重要说明：**
- trade 数据无 bid_price/ask_price（这两个字段在trade类型中为空）
- book_ticker 数据无 price/quantity/side（L1盘口数据）
- 时间戳以 `recv_timestamp_ns` 为准，精度最高

---

### 1.2 DEX 数据（链上Swap事件）

| 序号 | 字段 | 含义 | 精度 |
|---:|---|---|---|
| 1 | `block_timestamp_sec` | BSC区块共识时间，Unix秒（实际为3秒离散） | **秒（离散）** |
| 2 | `recv_timestamp_ms` | 程序处理log时的本机毫秒时间 | 毫秒 |
| 3 | `block_number` | 区块高度（BSC约3秒一个区块） | - |
| 4 | `symbol` | Alpha安全编码后的symbol | - |
| 5 | `display_symbol` | 展示交易对名称，如 `SLX/USDT` | - |
| 6 | `trade_side` | 相对业务token方向：`buy_token` / `sell_token` / `unknown` | - |
| 7 | `stable_volume_raw` | 本条swap的stable侧成交量raw integer | - |
| 8 | `token_amount_delta` | 业务token侧净变化（正=流入池子） | - |
| 9 | `stable_amount_delta` | stable侧净变化 | - |
| 10 | `amount0_in` / `amount0_out` | token0流入/流出池子数量 | - |
| 11 | `amount1_in` / `amount1_out` | token1流入/流出池子数量 | - |
| 12 | `price_token_in_stable` | 1个业务token对应多少stable | - |
| 13 | `fee_rate` | 手续费比例，如 `0.0025` = 0.25% | - |
| 14 | `sqrt_price_x96` | V3/V4池子的价格平方根（V2为空） | - |
| 15 | `tick` | V3/V4池子当前tick（V2为空） | - |
| 16 | `liquidity` | V3/V4池子当前流动性 | - |

**存储路径（RustFS S3）：**
```
crypto-alpha/raw/exchange=binance/symbol={alpha_symbol}/data_type=onchain_swap/date={YYYY-MM-DD}/hour={HH}/{fileName}.csv.zst
```

---

### 1.3 DEX 区块级池子状态（onchain_pair_state_block）

| 序号 | 字段 | 含义 |
|---:|---|---|
| 1 | `block_stable_volume_raw` | 本区块该pair的stable侧成交量raw integer |
| 2 | `swap_count` | 本区块该pair的swap log数量 |
| 3 | `event_count` | 本区块匹配到的Swap/Sync log总数 |
| 4 | `token_reserve_raw` | token侧库存raw integer |
| 5 | `stable_reserve_raw` | stable侧库存raw integer |
| 6 | `price_token_in_stable` | 池子当前价格 |
| 7 | `stable_liquidity_usd` | stable侧流动性的USD估值 |

**存储路径（RustFS S3）：**
```
crypto-alpha/raw/exchange=binance/symbol={alpha_symbol}/data_type=onchain_pair_state_block/date={YYYY-MM-DD}/hour={HH}/{fileName}.csv.zst
```

---

### 1.4 Token名称映射（alpha_symbol_map.json）

文件：`config/alpha_symbol_map.json`

```json
{
  "ALPHA_100USDT": {
    "alpha_id": "ALPHA_100",
    "display": "Broccoli/USDT",
    "token_name": "Broccoli",
    "token_symbol": "Broccoli",
    "quote": "USDT"
  },
  ...
}
```

---

### 1.5 数据精度差异问题（核心挑战）

```
CEX: 连续事件流，recv_timestamp_ns 精度可达纳秒
DEX: 离散区块，block_timestamp_sec 为秒级（BSC约450ms一个区块）

→ 两者不能直接对齐秒级以下时间戳
→ 需统一到固定时间窗口后再对比
```

---

## 二、Token映射关系

CEX的symbol格式为 `ALPHA_XXXTUSDT`（如 `ALPHA_100USDT`），需通过 `alpha_symbol_map.json` 映射为：
- `display`: 展示名称，如 `Broccoli/USDT`
- `token_address`: 合约地址（用于匹配DEX数据）

**注意：** 同一个alpha_id可能同时存在于USDT和USDC两个交易对，需注意quote资产区分，我们只做usdt交易对。

---

## 三、共振放量研究框架

### 3.1 总体研究目标

```
研究问题：
1. 共振放量本身是否可以作为买卖信号？
2. 共振放量的前后是否有其他因子可以支撑（预热信号/出场信号）？
3. CEX和DEX的领先-滞后关系（谁先动？）
```

---

### 3.2 第一步：构造共振事件表

**时间窗口选择：**
- 推荐窗口：30秒（平衡精度与统计量）
- 备选窗口：60秒、1分钟、按BSC区块（3秒）

**步骤：**

```
1. 对CEX trade数据：
   - 按N秒窗口聚合成交量
   - 统计 buy_volume = sum(quantity where side='BUY')
   - 统计 sell_volume = sum(quantity where side='SELL')
   - 计算 z_score = (volume - mean) / std

2. 对DEX swap数据：
   - 按N秒窗口（或按区块）聚合 stable_volume_raw
   - 统计 buy_volume = sum(stable_amount_in where trade_side='buy_token')
   - 统计 sell_volume = sum(stable_amount_out where trade_side='sell_token')
   - 计算 z_score

3. 识别共振事件：
   - 条件：CEX_z_score > Z_threshold AND DEX_z_score > Z_threshold
   - 建议 Z_threshold = 2.0（可调整）
   - 记录：共振时间戳、两边z_score值、成交量、方向（buy/buy vs sell/sell vs 背离）
```

**共振类型分类：**
```
| 类型 | CEX方向 | DEX方向 | 含义 |
|---|---|---|---|
| 双边买入共振 | BUY放大 | buy_token放大 | 强烈看多信号 |
| 双边卖出共振 | SELL放大 | sell_token放大 | 强烈看空信号 |
| 背离共振 | BUY放大 | sell_token放大 | 分歧信号（谨慎） |
| 背离共振 | SELL放大 | buy_token放大 | 分歧信号（谨慎） |
```

---

### 3.3 第二步：共振本身作为信号（IC检验）

**检验方法：**

```
信号定义：
  resonance_signal = 共振事件发生（0/1）

收益定义（Futures_return）：
  未来1秒/5秒/30秒/60秒/300秒的CEX价格变动率

IC计算（面板截面IC）：
  1. 每天为一个截面
  2. 跨token计算共振信号与未来收益的spearman相关系数
  3. 汇总所有截面：IC_mean, IC_std, IR = IC_mean/IC_std, 胜率

通过标准：
  |IC_mean| > 0.03
  IR > 0.5
  胜率 > 55%
```

**持仓周期 vs IC窗口对应关系：**
```
IC窗口（信号到收益测量间隔）  →  推荐持仓周期
1秒                               1-5秒
5秒                               5-30秒
30秒                              30秒-5分钟
60秒                              1-5分钟
300秒                              5-30分钟
```

---

### 3.4 第三步：共振前因子（Pre-Resonance Signals）

**核心问题：共振前是否有预热信号？**

#### 因子1：谁先动？（领先-滞后检测）

```
方法：
  1. 找到共振事件（t=0）
  2. 检验 t-30s 到 t-1s 之间：
     - CEX成交量是否已放大？（CEX先行）
     - DEX成交量是否已放大？（DEX先行）
     - 两者是否独立同时放大？（最强共振）

判断标准：
  - 如果CEX先放大 → 信息从CEX流向DEX
  - 如果DEX先放大 → 信息从DEX流向CEX（链上先知）
  - 如果独立同时放大 → 最强共振信号
```

#### 因子2：CEX订单簿深度变化（Spread收窄）

```
计算：
  spread = ask_price - bid_price
  spread_pct = spread / mid_price

检验：
  共振前30秒，spread是否收窄？
  → 收窄 = 多空双方价差缩小，方向共识凝聚
  → 放大 = 多空分歧加大

可选字段：book_ticker 的 bid_price/ask_price
注意：trade数据中这两个字段为空，需用book_ticker数据
```

#### 因子3：CEX单边成交量比率

```
计算：
  buy_ratio = buy_volume / (buy_volume + sell_volume)

检验：
  共振前30秒，buy_ratio是否已偏离0.5？
  → buy_ratio > 0.6 → 买方力量积累
  → buy_ratio < 0.4 → 卖方力量积累
```

#### 因子4：DEX池子流动性变化

```
计算：
  liquidity_change = token_reserve_after - token_reserve_before

检验：
  共振前N个区块，池子流动性是否显著变化？
  → 流动性萎缩 + 放量 = 方向共识强
  → 流动性膨胀 + 放量 = 可能有操纵或短期情绪
```

---

### 3.5 第四步：共振后因子（Post-Resonance Signals）

**核心问题：共振后价格是否趋势延续？如何出场？**

#### 因子5：价格趋势延续性

```
计算：
  ret_t+1s = (price_t+1s - price_t) / price_t
  ret_t+5s, ret_t+30s, ret_t+60s ...

检验：
  共振后价格变动的均值方向和持续性
  → 均值持续为正 = 趋势延续，适合持有
  → 均值快速回归 = 短期反转，应快速出场
```

#### 因子6：OBI回归（Order Flow Imbalance）

```
背景：
  CLO共振v7脚本中已有OBI因子
  OBI偏态严重时（|OBI| > 0.9），出场策略失效

检验：
  共振发生后，OBI是否快速回归0附近？
  → OBI回归 → 订单流恢复平衡，出场信号
  → OBI持续偏态 → 趋势延续，继续持有
```

#### 因子7：成交量萎缩检验（放量陷阱识别）

```
方法：
  共振放量后，观察成交量变化：
  - 放量后快速萎缩 → 真实突破（趋势延续）
  - 放量后持续放量 → 可能是噪音或操纵（谨慎）

计算：
  volume_ratio = 共振后30秒平均成交量 / 共振时成交量
  → ratio < 0.5 → 放量陷阱概率低
  → ratio > 1.0 → 可能持续波动
```

---

### 3.6 第五步：领先-滞后因果检验

**核心问题：CEX和DEX之间是否存在Granger因果关系？**

```
方法：Granger因果检验

假设检验：
  H0: DEX成交量不能帮助预测CEX价格
  H1: DEX成交量能帮助预测CEX价格

  H0: CEX成交量不能帮助预测DEX价格
  H1: CEX成交量能帮助预测DEX价格

步骤：
  1. 选取共振事件前后的数据窗口
  2. 构建VAR模型
  3. 进行F检验，判断显著性

意义：
  - 如果DEX→CEX显著：链上信息领先，DEX是"先知"
  - 如果CEX→DEX显著：交易所信息领先，CEX引导链上
  - 如果双向显著：信息在两个市场快速传递，共振最强
```

---

## 四、数据获取（RustFS S3 + DuckDB）

### 4.1 推荐方案：DuckDB直读S3

```python
import duckdb

conn = duckdb.connect()

# 配置S3访问
conn.execute("""
    SET s3_url_style = 'path';
    SET s3_endpoint = '192.168.1.130:9000';
    SET s3_access_key_id = 'yw123';
    SET s3_secret_access_key = 'yw123456';
    SET use_ssl = false;
""")

# 读取CEX trade数据示例
cex_trade = conn.execute("""
    SELECT 
        recv_timestamp_ns,
        trade_timestamp_ms,
        symbol,
        price,
        quantity,
        side
    FROM read_csv_auto('s3://zly/crypto-alpha/raw/exchange=binance/symbol=*/data_type=trade/date=2026-06-09/*.csv.zst')
    WHERE symbol LIKE 'ALPHA_%USDT'
""").df()

# 读取DEX swap数据示例
dex_swap = conn.execute("""
    SELECT
        block_timestamp_sec,
        recv_timestamp_ms,
        symbol,
        trade_side,
        stable_volume_raw,
        token_amount_delta,
        amount0_in, amount0_out,
        amount1_in, amount1_out
    FROM read_csv_auto('s3://zly/crypto-alpha/raw/exchange=binance/symbol=*/data_type=onchain_swap/date=2026-06-09/*.csv.zst')
""").df()
```

### 4.2 读取alpha_symbol_map.json

```python
import json

with open('config/alpha_symbol_map.json', 'r') as f:
    symbol_map = json.load(f)

# 构建 alpha_symbol → display_name 映射
alpha_to_display = {k: v['display'] for k, v in symbol_map['mapping'].items()}
alpha_to_token_address = {k: v.get('token_address', '') for k, v in symbol_map['mapping'].items()}
```

---

## 五、研究流程总览

```
阶段1：数据准备
├── 拉取目标日期的CEX trade数据（DuckDB直读S3）
├── 拉取目标日期的DEX swap数据
├── 加载alpha_symbol_map.json
└── 时间对齐到统一窗口（30秒窗口）

阶段2：共振事件识别
├── 对CEX和DEX分别计算30秒窗口成交量
├── 计算z-score，识别z > 2的放量事件
├── 找到两边同时放量的时间点 = 共振事件
└── 记录：时间戳、z_score、方向（buy/buy等）

阶段3：IC检验（共振信号本身）
├── 构造共振信号（0/1）
├── 计算未来1秒/5秒/30秒/60秒价格变动
├── 面板截面IC检验
└── 判断：共振是否可以作为有效信号

阶段4：共振前因子
├── 领先-滞后检测（谁先动？）
├── CEX订单簿spread变化
├── CEX单边成交量比率
└── DEX池子流动性变化

阶段5：共振后因子
├── 价格趋势延续性
├── OBI回归检验
└── 成交量萎缩检验（放量陷阱）

阶段6：因果检验
└── Granger因果检验（CEX↔DEX引导关系）

阶段7：整合与回测
├── 组合前因子 + 共振信号 + 后因子
├── 生成综合信号
├── 分组回测验证
└── 最优参数搜索
```

---

## 六、关键参数待确认

| 参数 | 选项 | 建议 |
|---|---|---|
| 共振窗口大小 | 10s / 30s / 60s / 1min / 按区块 | 30秒 |
| 放量判定阈值（z-score） | 1.5 / 2.0 / 2.5 | 2.0起步 |
| 研究数据范围 | 最近N天 | 待确认 |
| 收益测量窗口 | 1s / 5s / 30s / 60s / 300s | 多窗口并行 |

---

## 七、已知坑点

1. **时间精度不统一**：CEX纳秒 vs DEX秒级（BSC区块3秒），需统一到窗口
2. **symbol格式差异**：CEX用 `ALPHA_XXXTUSDT`，DEX用 `display_symbol`（如 `SLX/USDT`），需通过映射表转换
3. **trade数据无盘口**：book_ticker才有bid/ask_price，trade数据这两个字段为空
4. **V2池子无tick/sqrtPriceX96**：V2池子这些字段为空
5. **区块时间戳为秒级**：DEX数据最小时间单位是区块（3秒），不能做秒以下分析

---

## 八、参考文件

| 文件 | 内容 |
|---|---|
| `alpha DEX数据采集字段说明.md` | DEX链上数据字段完整说明 |
| `CEX采集字段说明.md` | CEX trade/book_ticker字段说明 |
| `alpha_symbol_map.json` | Token名称映射表（1321个交易对） |
