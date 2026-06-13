# Alpha 链上 onchain 采集表字段说明

## 适用范围

本文档按当前 `alpha-onchain` 程序实际源码整理，覆盖两张 RustFS Raw 采集表：

- `onchain_swap`
- `onchain_pair_state_block`

字段顺序以程序中的 `csvHeader`、`pairStateBlockHeader` 为准。历史文件可能存在旧 schema，消费历史数据时仍应优先读取 CSV 第一行表头或 manifest `schema`。

## 通用说明

- Raw 文件格式：`csv.zst`。
- CSV 第一行为表头。
- manifest `schema` 与 CSV 表头一致。
- CSV 字段均以文本写出，消费端按语义再转为整数、小数或地址。
- 链上金额字段均为合约 raw integer，除带 `_ui` 后缀字段外，程序不按 decimals 转成展示数量。
- `block_timestamp_sec` 来自 BSC 区块头 `header.Time`，是 Unix 秒级时间戳。
- `block_timestamp_ms` 等于 `block_timestamp_sec * 1000`，只是毫秒格式，不代表链上具备毫秒级事件时间。
- `recv_timestamp_ms` 和 `state_read_timestamp_ms` 来自采集服务器本机时间 `time.Now().UnixMilli()`。

RustFS Raw object key：

```text
crypto-alpha/raw/exchange=binance/symbol={alpha_symbol}/data_type={data_type}/date={YYYY-MM-DD}/hour={HH}/{fileName}
```

## 两张表职责区分

| 表 | manifest version | 写入粒度 | 主要用途 |
|---|---:|---|---|
| `onchain_swap` | 2 | 每条匹配到的 `Swap` / `Sync` log 写 1 行 | 事件级逐笔流水、回测成交方向、成交量、链上排序审计 |
| `onchain_pair_state_block` | 2 | 每个 `symbol + token + pair + block` 最多写 1 行 | 区块级池子状态、价格、流动性、区块成交统计 |

推荐使用：

- 查链上事件明细：读 `onchain_swap`。
- 查池子状态随区块变化、区块级成交量、价格和流动性：读 `onchain_pair_state_block`。

## onchain_swap 字段说明

`onchain_swap` 是事件级流水。程序订阅新区块后，对目标 pair 拉取匹配的 V2/V3/V4 `Swap` 和 V2 `Sync` log，并对每条 log 写 1 行。

推荐链上事件排序：

```text
block_number ASC, log_index ASC
```

| 序号 | 字段 | 含义 | 来源 |
|---:|---|---|---|
| 1 | `block_timestamp_sec` | BSC 区块共识时间，Unix 秒。 | 区块头 `header.Time` |
| 2 | `block_timestamp_ms` | 毫秒格式的区块时间，实际精度仍是秒。 | `block_timestamp_sec * 1000` |
| 3 | `recv_timestamp_ms` | 程序处理该 log 时记录的本机毫秒时间。 | 采集服务器本机时间 `time.Now().UnixMilli()` |
| 4 | `block_number` | 区块高度。 | 区块头 `header.Number`，必要时用 log `BlockNumber` |
| 5 | `block_hash` | 区块哈希。 | log `BlockHash`，为空时用区块头 hash |
| 6 | `tx_hash` | 触发该 log 的交易哈希。 | log `TxHash` |
| 7 | `tx_index` | 交易在区块内的序号。 | log `TxIndex` |
| 8 | `log_index` | log 在区块内的全局序号。 | log `Index` |
| 9 | `event_topic0` | 原始事件 topic0，用于审计事件类型映射。 | log `Topics[0]` |
| 10 | `event_type` | `swap_v2` / `swap_v3` / `swap_v4` / `sync`。 | topic0 与 pair 类型映射 |
| 11 | `symbol` | 安全编码后的 Alpha symbol。 | Alpha token 元数据 `Symbol` |
| 12 | `display_symbol` | 展示交易对名称，例如 `SLX/USDT`。 | Alpha token 元数据 |
| 13 | `base_asset` | Alpha base asset。 | Alpha token 元数据 |
| 14 | `quote_asset` | Alpha quote asset。 | Alpha token 元数据 |
| 15 | `token_address` | 当前业务 token 合约地址。 | Alpha token 元数据 |
| 16 | `pair_address` | 产生事件的池子 / pair 地址。 | max pair 元数据，兜底用 log `Address` |
| 17 | `pair_type` | `v2` / `v3` / `v4`。 | max pair 元数据 |
| 18 | `platform` | DEX 平台名称。 | pair 候选元数据 |
| 19 | `swap_source` | swap 来源；V4 场景可区分 `Uniswap V4` / `CLPositionManager` 等。 | pair 候选元数据 |
| 20 | `stable_address` | stable 侧 token 地址。 | max pair 元数据 |
| 21 | `stable_name` | stable 名称，例如 `USDT` / `USDC` / `WBNB`。 | 稳定币地址映射 |
| 22 | `token0_address` | 池子 token0 地址。 | max pair 元数据与 `location` 派生 |
| 23 | `token1_address` | 池子 token1 地址。 | max pair 元数据与 `location` 派生 |
| 24 | `location` | stable 在池子中的位置：`0` 为 token0，`1` 为 token1。 | max pair 元数据 |
| 25 | `fee_multiplier_1e4` | AMM 扣费后乘数，基准为 `10000`；例如 `9975` 表示扣除 0.25% 手续费后的乘数。 | max pair 元数据 `PairInfo.PlatFee` |
| 26 | `fee_rate` | 便于阅读的手续费比例；例如 `9999 -> 0.0001`、`9975 -> 0.0025`。 | `(10000 - fee_multiplier_1e4) / 10000` |
| 27 | `amount0_delta` | 池子 token0 视角净变化；正数表示流入池子，负数表示流出池子。 | swap 事件解析 |
| 28 | `amount1_delta` | 池子 token1 视角净变化；正数表示流入池子，负数表示流出池子。 | swap 事件解析 |
| 29 | `amount0_in` | token0 流入池子的非负数量。 | V2 原始字段或 delta 派生 |
| 30 | `amount1_in` | token1 流入池子的非负数量。 | V2 原始字段或 delta 派生 |
| 31 | `amount0_out` | token0 流出池子的非负数量。 | V2 原始字段或 delta 派生 |
| 32 | `amount1_out` | token1 流出池子的非负数量。 | V2 原始字段或 delta 派生 |
| 33 | `token_amount_delta` | 业务 token 侧净变化。 | `amount0_delta` / `amount1_delta` 按 `location` 归一化 |
| 34 | `stable_amount_delta` | stable 侧净变化。 | `amount0_delta` / `amount1_delta` 按 `location` 归一化 |
| 35 | `token_amount_in` | 业务 token 流入池子的数量。 | 归一化派生 |
| 36 | `stable_amount_in` | stable 流入池子的数量。 | 归一化派生 |
| 37 | `token_amount_out` | 业务 token 流出池子的数量。 | 归一化派生 |
| 38 | `stable_amount_out` | stable 流出池子的数量。 | 归一化派生 |
| 39 | `stable_volume_raw` | 本条 swap 的 stable 侧成交量 raw integer；`sync` 写 `0`。 | `stable_amount_in + stable_amount_out` |
| 40 | `trade_side` | 相对业务 token 的方向：`buy_token` / `sell_token` / `unknown`。 | `token_amount_in` / `token_amount_out` 派生 |
| 41 | `reserve0` | V2 Sync 事件中的 reserve0；非 Sync 事件通常为空。 | V2 `Sync(uint112,uint112)` 事件 |
| 42 | `reserve1` | V2 Sync 事件中的 reserve1；非 Sync 事件通常为空。 | V2 `Sync(uint112,uint112)` 事件 |
| 43 | `token_reserve_after` | Sync 后业务 token 侧库存；非 Sync 事件通常为空。 | V2 Sync reserve 按 `location` 归一化 |
| 44 | `stable_reserve_after` | Sync 后 stable 侧库存；非 Sync 事件通常为空。 | V2 Sync reserve 按 `location` 归一化 |
| 45 | `sqrt_price_x96` | 集中流动性池 swap 后 `sqrtPriceX96`；V2 通常为空。 | V3 / V4 swap 事件 data |
| 46 | `liquidity` | 集中流动性池 swap 后 liquidity；V2 通常为空。 | V3 / V4 swap 事件 data |
| 47 | `tick` | 集中流动性池 swap 后 tick；V2 通常为空。 | V3 / V4 swap 事件 data |
| 48 | `token_decimals` | 业务 token decimals；读取失败时为空。 | token 合约 `decimals()` |
| 49 | `stable_decimals` | stable decimals；读取失败时为空。 | stable 合约 `decimals()` 或已知 stable 默认值 |

## onchain_pair_state_block 字段说明

`onchain_pair_state_block` 是区块级池子状态表。当前程序会先按 `pair + token + symbol + block_number` 聚合同一区块内同一池子的事件，再读取一次该区块对应的 pair 状态并写 1 行。

推荐状态分析排序：

```text
block_number ASC, pair_address ASC
```

推荐唯一键：

```text
symbol + token_address + pair_address + block_number
```

| 序号 | 字段 | 含义 | 来源 |
|---:|---|---|---|
| 1 | `block_timestamp_sec` | BSC 区块共识时间，Unix 秒。 | 区块头 `header.Time` |
| 2 | `block_timestamp_ms` | 毫秒格式的区块时间，实际精度仍是秒。 | `block_timestamp_sec * 1000` |
| 3 | `state_read_timestamp_ms` | 程序读取并构造该区块级状态行时的本机毫秒时间。 | 采集服务器本机时间 `time.Now().UnixMilli()` |
| 4 | `first_event_recv_timestamp_ms` | 该区块该 pair 第一条触发事件的处理时间。 | 本组第一条触发 log 的事件上下文 |
| 5 | `last_event_recv_timestamp_ms` | 该区块该 pair 最后一条触发事件的处理时间。 | 本组最后一条触发 log 的事件上下文 |
| 6 | `block_number` | 区块高度。 | 区块头 `header.Number` |
| 7 | `block_hash` | 区块哈希。 | 触发事件上下文 |
| 8 | `first_trigger_tx_hash` | 第一条触发 log 的交易哈希。 | 本组最小 `tx_index/log_index` 的 log |
| 9 | `first_trigger_tx_index` | 第一条触发交易在区块内的序号。 | 第一条触发 log |
| 10 | `first_trigger_log_index` | 第一条触发 log 在区块内的全局序号。 | 第一条触发 log |
| 11 | `last_trigger_tx_hash` | 最后一条触发 log 的交易哈希。 | 本组最大 `tx_index/log_index` 的 log |
| 12 | `last_trigger_tx_index` | 最后一条触发交易在区块内的序号。 | 最后一条触发 log |
| 13 | `last_trigger_log_index` | 最后一条触发 log 在区块内的全局序号。 | 最后一条触发 log |
| 14 | `event_count` | 本区块该 pair 匹配到的 `Swap` / `Sync` log 总数。 | 本区块该 pair 事件聚合 |
| 15 | `swap_count` | 本区块该 pair 的 swap log 数量。 | 本区块该 pair 事件聚合 |
| 16 | `sync_count` | 本区块该 pair 的 sync log 数量。 | 本区块该 pair 事件聚合 |
| 17 | `symbol` | 安全编码后的 Alpha symbol。 | Alpha token 元数据 `Symbol` |
| 18 | `display_symbol` | 展示交易对名称。 | Alpha token 元数据 |
| 19 | `base_asset` | Alpha base asset。 | Alpha token 元数据 |
| 20 | `quote_asset` | Alpha quote asset。 | Alpha token 元数据 |
| 21 | `token_name` | 业务 token 名称。 | Alpha token 元数据 |
| 22 | `token_address` | 业务 token 合约地址。 | Alpha token 元数据 |
| 23 | `pair_address` | 池子 / pair 地址。 | 当前 max pair / 状态读取结果 |
| 24 | `pair_type` | `v2` / `v3` / `v4`。 | max pair 元数据 |
| 25 | `platform` | DEX 平台名称。 | pair 候选元数据 |
| 26 | `swap_source` | swap 来源；V4 场景可区分 `Uniswap V4` / `CLPositionManager` 等。 | pair 候选元数据 |
| 27 | `stable_name` | stable 名称。 | 稳定币地址映射 |
| 28 | `stable_address` | stable 侧 token 地址。 | pair 状态解析 |
| 29 | `token0_address` | 池子 token0 地址。 | max pair 元数据与 `location` 派生 |
| 30 | `token1_address` | 池子 token1 地址。 | max pair 元数据与 `location` 派生 |
| 31 | `location` | stable 在池子中的位置：`0` 为 token0，`1` 为 token1。 | max pair 元数据 |
| 32 | `fee_multiplier_1e4` | AMM 扣费后乘数，基准为 `10000`。 | pair 状态解析 `PairInfo.PlatFee` |
| 33 | `fee_rate` | 便于阅读的手续费比例。 | `(10000 - fee_multiplier_1e4) / 10000` |
| 34 | `token_reserve_raw` | token 侧库存 raw integer。 | pair 状态解析 |
| 35 | `token_balance_raw` | token 侧实际余额 raw integer。 | pair 状态解析 |
| 36 | `token_decimals` | 业务 token decimals；读取失败时为空。 | token 合约 `decimals()` |
| 37 | `token_reserve_ui` | token 侧库存展示数量。 | `token_reserve_raw / 10^token_decimals` |
| 38 | `token_balance_ui` | token 侧实际余额展示数量。 | `token_balance_raw / 10^token_decimals` |
| 39 | `stable_reserve_raw` | stable 侧库存 raw integer。 | pair 状态解析 |
| 40 | `stable_balance_raw` | stable 侧实际余额 raw integer。 | pair 状态解析 |
| 41 | `stable_decimals` | stable decimals；读取失败时为空。 | stable 合约 `decimals()` 或已知 stable 默认值 |
| 42 | `stable_reserve_ui` | stable 侧库存展示数量。 | `stable_reserve_raw / 10^stable_decimals` |
| 43 | `stable_balance_ui` | stable 侧实际余额展示数量。 | `stable_balance_raw / 10^stable_decimals` |
| 44 | `liquidity` | 集中流动性池当前 liquidity；V2 通常为空。 | V3 / V4 状态读取 |
| 45 | `sqrt_price_x96` | 集中流动性池当前 `sqrtPriceX96`；V2 通常为空。 | V3 / V4 状态读取 |
| 46 | `tick` | 集中流动性池当前 tick；V2 通常为空。 | V3 / V4 状态读取 |
| 47 | `price_token_in_stable` | 1 个业务 token 对应多少 stable；条件不足时为空。 | `stable_reserve_raw/token_reserve_raw` 按 decimals 归一化 |
| 48 | `wbnb_price` | 当前 WBNB 参考价格，保留 6 位小数；不可用时为空。 | 程序内价格缓存 |
| 49 | `stable_liquidity_usd` | stable 侧流动性的 USD 估值；无法定价时为空。 | stable 侧库存按 stable/USD 或 WBNB 等价格折算 |
| 50 | `block_stable_volume_raw` | 本区块该 pair 的 stable 侧成交量 raw integer。 | 本区块该 pair swap 聚合 |
| 51 | `block_stable_volume_ui` | 本区块该 pair 的 stable 侧成交量展示数量。 | `block_stable_volume_raw / 10^stable_decimals` |

## 关键口径说明

### 费率字段

- `fee_multiplier_1e4` 是原始扣费后乘数，基准为 `10000`。
- `fee_rate` 是派生后的真实手续费比例。
- 换算公式：

```text
fee_rate = (10000 - fee_multiplier_1e4) / 10000
```

示例：

| `fee_multiplier_1e4` | `fee_rate` | 含义 |
|---:|---:|---|
| `9999` | `0.0001` | 0.01% |
| `9975` | `0.0025` | 0.25% |
| `9970` | `0.003` | 0.3% |
| `9900` | `0.01` | 1% |
