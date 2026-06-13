<template>
  <div class="page-shell">
    <header class="hero">
      <div>
        <p class="eyebrow">Backtest Visual Lab</p>
        <h1>回测结果可视化平台</h1>
        <p class="hero-copy">统一查看多策略、多日期、多 hold 周期表现，并预留成交量、最大回撤、利润/成交量、手续费字段。</p>
      </div>
      <el-button type="primary" @click="store.refreshCache">重建缓存</el-button>
    </header>

    <section class="panel toolbar">
      <el-select v-model="store.selectedStrategyId" placeholder="选择策略" @change="store.loadOverview">
        <el-option v-for="item in store.strategies" :key="item.strategy_id" :label="item.strategy_name" :value="item.strategy_id" />
      </el-select>
      <el-select v-model="store.selectedDate" placeholder="选择日期" @change="store.loadDayDetail">
        <el-option v-for="date in availableDates" :key="date" :label="date" :value="date" />
      </el-select>
      <el-select v-model="store.selectedMetric" placeholder="趋势指标">
        <el-option v-for="item in metricOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="store.selectedLayer" clearable placeholder="按 layer 过滤">
        <el-option v-for="layer in availableLayers" :key="layer" :label="layer" :value="layer" />
      </el-select>
      <el-select v-model="store.selectedHoldSec" placeholder="选择 hold">
        <el-option v-for="hold in availableHolds" :key="hold" :label="`${hold}s`" :value="hold" />
      </el-select>
    </section>

    <section v-if="store.error" class="panel error-panel">{{ store.error }}</section>

    <section class="metrics-grid">
      <MetricCard label="信号数" :value="formatNumber(selectedDaySummary?.signal_count, 0)" />
      <MetricCard label="总 PnL" :value="withSign(selectedDaySummary?.best_total_pnl, 4)" />
      <MetricCard label="成交量" :value="formatNumber(selectedDaySummary?.volume, 2)" />
      <MetricCard label="最大回撤" :value="formatNumber(selectedDaySummary?.max_drawdown, 4)" />
      <MetricCard label="利润/成交量" :value="formatNumber(selectedDaySummary?.pnl_per_volume, 6)" />
      <MetricCard label="手续费" :value="formatNumber(selectedDaySummary?.total_fee, 4)" />
      <MetricCard label="最佳 Layer" :value="bestLayerLabel" />
      <MetricCard label="最佳 Hold" :value="bestHoldLabel" />
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <h2>多日趋势</h2>
          <p>按 layer 比较策略表现，支持切换收益、胜率、成交量和手续费。</p>
        </div>
      </div>
      <OverviewChart :rows="overviewRows" :metric="store.selectedMetric" />
    </section>

    <section class="split-grid">
      <div class="panel">
        <div class="section-head">
          <div>
            <h2>Layer × Hold 热力图</h2>
            <p>点击单元格即可联动下方价格图和信号明细。</p>
          </div>
        </div>
        <HeatmapChart :rows="dayHoldStats" @select="handleHeatmapSelect" />
      </div>
      <div class="panel">
        <div class="section-head">
          <div>
            <h2>Hold 收益对比</h2>
            <p>{{ selectedLayerTitle }}</p>
          </div>
        </div>
        <HoldPerformanceChart :rows="selectedLayerHoldStats" />
      </div>
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <h2>价格曲线与信号点</h2>
          <p>如果当前策略没有价格资产，这里会自动降级为空展示。</p>
        </div>
      </div>
      <PriceSignalsChart :price-series="priceSeries" :markers="signalMarkers" :selected-layer="store.selectedLayer" />
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <h2>单日汇总</h2>
          <p>包含预留字段：成交量、最大回撤、利润/成交量、手续费；缺失时显示为 `--`。</p>
        </div>
      </div>
      <el-table :data="layerSummaries" stripe>
        <el-table-column prop="layer" label="Layer" min-width="180" />
        <el-table-column prop="best_hold_sec" label="最佳 Hold">
          <template #default="{ row }">{{ row.best_hold_sec ? `${row.best_hold_sec}s` : "--" }}</template>
        </el-table-column>
        <el-table-column prop="signal_count" label="信号数" />
        <el-table-column prop="total_pnl" label="总 PnL">
          <template #default="{ row }">{{ withSign(row.total_pnl, 4) }}</template>
        </el-table-column>
        <el-table-column prop="win_ratio" label="胜率">
          <template #default="{ row }">{{ formatPercent(row.win_ratio, 2) }}</template>
        </el-table-column>
        <el-table-column prop="volume" label="成交量">
          <template #default="{ row }">{{ formatNumber(row.volume, 2) }}</template>
        </el-table-column>
        <el-table-column prop="max_drawdown" label="最大回撤">
          <template #default="{ row }">{{ formatNumber(row.max_drawdown, 4) }}</template>
        </el-table-column>
        <el-table-column prop="pnl_per_volume" label="利润/成交量">
          <template #default="{ row }">{{ formatNumber(row.pnl_per_volume, 6) }}</template>
        </el-table-column>
        <el-table-column prop="total_fee" label="手续费">
          <template #default="{ row }">{{ formatNumber(row.total_fee, 4) }}</template>
        </el-table-column>
      </el-table>
    </section>

    <section class="panel">
      <div class="section-head">
        <div>
          <h2>信号明细</h2>
          <p>{{ selectedLayerTitle }} / {{ store.selectedHoldSec ? `${store.selectedHoldSec}s` : "--" }}</p>
        </div>
      </div>
      <el-table :data="filteredSignals" stripe height="520">
        <el-table-column prop="signal_time" label="信号时间" min-width="200" />
        <el-table-column prop="layer" label="Layer" min-width="180" />
        <el-table-column prop="entry_price" label="进场价">
          <template #default="{ row }">{{ formatNumber(row.entry_price, 6) }}</template>
        </el-table-column>
        <el-table-column prop="entry_notional" label="进场额">
          <template #default="{ row }">{{ formatNumber(row.entry_notional, 4) }}</template>
        </el-table-column>
        <el-table-column prop="trade_roll_3600ms" label="成交量滚动">
          <template #default="{ row }">{{ formatNumber(row.trade_roll_3600ms, 2) }}</template>
        </el-table-column>
        <el-table-column prop="z_trade" label="Z Trade">
          <template #default="{ row }">{{ formatNumber(row.z_trade, 4) }}</template>
        </el-table-column>
        <el-table-column prop="z_dex" label="Z DEX">
          <template #default="{ row }">{{ formatNumber(row.z_dex, 4) }}</template>
        </el-table-column>
        <el-table-column prop="z_book" label="Z Book">
          <template #default="{ row }">{{ formatNumber(row.z_book, 4) }}</template>
        </el-table-column>
        <el-table-column label="收益">
          <template #default="{ row }">{{ formatNumber(selectedHoldMetric(row)?.ret, 6) }}</template>
        </el-table-column>
        <el-table-column label="PnL">
          <template #default="{ row }">{{ withSign(selectedHoldMetric(row)?.net_pnl, 4) }}</template>
        </el-table-column>
        <el-table-column label="手续费">
          <template #default="{ row }">{{ formatNumber(selectedHoldMetric(row)?.fee, 4) }}</template>
        </el-table-column>
        <el-table-column label="成交量">
          <template #default="{ row }">{{ formatNumber(selectedHoldMetric(row)?.volume, 2) }}</template>
        </el-table-column>
        <el-table-column prop="max_drawdown" label="最大回撤">
          <template #default="{ row }">{{ formatNumber(row.max_drawdown, 4) }}</template>
        </el-table-column>
        <el-table-column prop="pnl_per_volume" label="利润/成交量">
          <template #default="{ row }">{{ formatNumber(row.pnl_per_volume, 6) }}</template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted } from "vue";
import MetricCard from "./components/MetricCard.vue";
import OverviewChart from "./components/OverviewChart.vue";
import HeatmapChart from "./components/HeatmapChart.vue";
import HoldPerformanceChart from "./components/HoldPerformanceChart.vue";
import PriceSignalsChart from "./components/PriceSignalsChart.vue";
import { formatNumber, formatPercent, withSign } from "./lib/format";
import { useDashboardStore } from "./stores/dashboard";

const store = useDashboardStore();

const metricOptions = [
  { label: "总 PnL", value: "total_pnl" },
  { label: "信号数", value: "signal_count" },
  { label: "胜率", value: "win_ratio" },
  { label: "成交量", value: "volume" },
  { label: "最大回撤", value: "max_drawdown" },
  { label: "利润/成交量", value: "pnl_per_volume" },
  { label: "手续费", value: "total_fee" },
];

const availableDates = computed(() => store.overview?.meta?.available_dates || []);
const availableLayers = computed(() => store.overview?.meta?.available_layers || []);
const availableHolds = computed(() => store.overview?.meta?.available_holds || []);
const overviewRows = computed(() => store.overview?.hold_stat_rows || []);
const selectedDaySummary = computed(() => (store.overview?.day_summaries || []).find((item) => item.date === store.selectedDate));
const layerSummaries = computed(() => store.dayDetail?.detail?.layer_summaries || []);
const dayHoldStats = computed(() => store.dayDetail?.detail?.hold_stats || []);
const activeLayer = computed(() => store.selectedLayer || bestLayer.value?.layer || availableLayers.value[0] || "");
const selectedLayerHoldStats = computed(() => {
  if (!activeLayer.value) {
    return [];
  }
  return dayHoldStats.value.filter((row) => row.layer === activeLayer.value);
});
const priceSeries = computed(() => store.dayDetail?.detail?.price_series || []);
const signalMarkers = computed(() => store.dayDetail?.detail?.signal_markers || []);
const filteredSignals = computed(() => {
  const rows = store.dayDetail?.detail?.signals || [];
  if (!store.selectedLayer) {
    return rows;
  }
  return rows.filter((row) => row.layer === store.selectedLayer);
});

const bestLayer = computed(() => {
  const rows = layerSummaries.value.filter((row) => row.total_pnl !== null && row.total_pnl !== undefined);
  if (!rows.length) {
    return null;
  }
  return [...rows].sort((a, b) => b.total_pnl - a.total_pnl)[0];
});

const bestLayerLabel = computed(() => bestLayer.value?.layer || "--");
const bestHoldLabel = computed(() => {
  if (bestLayer.value?.best_hold_sec) {
    return `${bestLayer.value.best_hold_sec}s`;
  }
  if (selectedDaySummary.value?.best_hold_sec) {
    return `${selectedDaySummary.value.best_hold_sec}s`;
  }
  return "--";
});
const selectedLayerTitle = computed(() => (activeLayer.value ? `当前 Layer: ${activeLayer.value}` : "全部 Layer"));

function selectedHoldMetric(row) {
  return row.hold_metrics.find((item) => item.hold_sec === store.selectedHoldSec) || {};
}

function handleHeatmapSelect({ layer, holdSec }) {
  store.selectedLayer = layer;
  store.selectedHoldSec = holdSec;
}

onMounted(() => {
  store.initialize();
});
</script>
