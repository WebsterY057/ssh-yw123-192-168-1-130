# CEX 采集字段简化说明

## CEX trade 字段说明

| 序号 | 字段 | 含义 | 来源 |
|---:|---|---|---|
| 1 | `recv_timestamp_ns` | 本地采集程序收到 WebSocket 消息的纳秒时间戳。 | API 适配层接收时间戳，缺失时回退本机 `time.Now().UnixNano()` |
| 2 | `event_timestamp_ms` | 交易所成交事件时间、推送时间或消息生成时间，毫秒时间戳；交易所未提供时为 `0`。 | 交易所 WebSocket payload 经 API 适配层解析 |
| 3 | `trade_timestamp_ms` | 成交真实发生时间，毫秒时间戳；交易所未提供时为 `0`。 | 交易所成交 payload 经 API 适配层解析 |
| 4 | `exchange` | 采集来源交易所标识。 | 采集流配置 `stream.ExchangeCode` |
| 5 | `market` | 市场类型，例如 `spot` / `futures`。 | 采集流配置 `stream.Market` |
| 6 | `symbol` | 交易对符号。 | 采集流配置 `stream.Symbol` |
| 7 | `data_type` | 数据类型，当前为 `trade`。 | 采集流配置 `stream.DataType` |
| 8 | `bid_price` | `trade` 无买一价，字段为空。 | 统一 CSV schema 保留字段 |
| 9 | `bid_qty` | `trade` 无买一量，字段为空。 | 统一 CSV schema 保留字段 |
| 10 | `ask_price` | `trade` 无卖一价，字段为空。 | 统一 CSV schema 保留字段 |
| 11 | `ask_qty` | `trade` 无卖一量，字段为空。 | 统一 CSV schema 保留字段 |
| 12 | `update_id` | `trade` 无盘口更新 ID，通常为 `0`。 | 统一 CSV schema 保留字段 |
| 13 | `checksum` | `trade` 无盘口校验和，通常为 `0`。 | 统一 CSV schema 保留字段 |
| 14 | `price` | 成交价格。 | API 适配层 `Trade.Price` |
| 15 | `quantity` | 成交数量。 | API 适配层 `Trade.Quantity` |
| 16 | `side` | 成交方向，统一写入 `BUY` / `SELL`。 | API 适配层 `Trade.Side` |
| 17 | `trade_id` | 可安全转为整数的成交 ID；没有或不适合整数表示时为 `0`。 | API 适配层 `Trade.TradeID` |
| 18 | `trade_id_text` | 原始成交 ID 字符串，用于保留超大 ID 或非纯数字 ID。 | API 适配层 `Trade.TradeIDText` |
| 19 | `raw` | 原始 WebSocket 消息保留字段；多数采集路径为空。 | API 适配层 `Trade.RawMessage` |

## CEX book_ticker L1 字段说明

| 序号 | 字段 | 含义 | 来源 |
|---:|---|---|---|
| 1 | `recv_timestamp_ns` | 本地采集程序收到 WebSocket 消息的纳秒时间戳。 | API 适配层接收时间戳，缺失时回退本机 `time.Now().UnixNano()` |
| 2 | `event_timestamp_ms` | 交易所盘口事件时间或消息生成时间，毫秒时间戳；交易所未提供时为 `0`。 | 交易所 WebSocket payload 经 API 适配层解析 |
| 3 | `trade_timestamp_ms` | `book_ticker` 不是成交事件，通常固定为 `0`。 | 统一 CSV schema 保留字段 |
| 4 | `exchange` | 采集来源交易所标识。 | 采集流配置 `stream.ExchangeCode` |
| 5 | `market` | 市场类型，例如 `spot` / `futures`。 | 采集流配置 `stream.Market` |
| 6 | `symbol` | 交易对符号。 | 采集流配置 `stream.Symbol` |
| 7 | `data_type` | 数据类型，当前为 `book_ticker`。 | 采集流配置 `stream.DataType` |
| 8 | `bid_price` | 当前最优买一价。 | API 适配层 `BookTicker.BidsPrice` |
| 9 | `bid_qty` | 当前最优买一量。 | API 适配层 `BookTicker.BidsNum` |
| 10 | `ask_price` | 当前最优卖一价。 | API 适配层 `BookTicker.AsksPrice` |
| 11 | `ask_qty` | 当前最优卖一量。 | API 适配层 `BookTicker.AsksNum` |
| 12 | `update_id` | 盘口更新 ID、版本号或序列号；交易所未提供时为 `0`。 | API 适配层 `BookTicker.UpdateID` |
| 13 | `checksum` | 盘口校验和；交易所未提供时为 `0`。 | API 适配层 `BookTicker.Checksum` |
| 14 | `price` | `book_ticker` 无成交价，字段为空。 | 统一 CSV schema 保留字段 |
| 15 | `quantity` | `book_ticker` 无成交数量，字段为空。 | 统一 CSV schema 保留字段 |
| 16 | `side` | `book_ticker` 无成交方向，字段为空。 | 统一 CSV schema 保留字段 |
| 17 | `trade_id` | `book_ticker` 无成交 ID，通常为 `0`。 | 统一 CSV schema 保留字段 |
| 18 | `trade_id_text` | `book_ticker` 无原始成交 ID，字段为空。 | 统一 CSV schema 保留字段 |
| 19 | `raw` | 原始 WebSocket 消息保留字段；多数采集路径为空。 | API 适配层 `BookTicker.RawMessage` |
