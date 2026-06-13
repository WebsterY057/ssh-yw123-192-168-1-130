<template>
  <div ref="root" class="chart"></div>
</template>

<script setup>
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { formatNumber, formatPercent } from "../lib/format";

const emit = defineEmits(["select"]);
const props = defineProps({
  rows: { type: Array, default: () => [] },
});

const root = ref(null);
let chart;

function render() {
  if (!chart) {
    return;
  }
  const layers = [...new Set(props.rows.map((row) => row.layer))];
  const holds = [...new Set(props.rows.map((row) => row.hold_sec))].sort((a, b) => a - b);
  const data = props.rows.map((row) => [holds.indexOf(row.hold_sec), layers.indexOf(row.layer), row.total_pnl]);
  chart.setOption({
    tooltip: {
      position: "top",
      backgroundColor: "rgba(15, 23, 42, 0.96)",
      borderColor: "rgba(148, 163, 184, 0.25)",
      textStyle: { color: "#e2e8f0" },
      formatter(params) {
        const layer = layers[params.data[1]];
        const holdSec = holds[params.data[0]];
        const row = props.rows.find((item) => item.layer === layer && item.hold_sec === holdSec);
        if (!row) {
          return "";
        }
        return [
          `${layer} / ${holdSec}s`,
          `总 PnL: ${formatNumber(row.total_pnl, 4)}`,
          `胜率: ${formatPercent(row.win_ratio, 2)}`,
          `成交量: ${formatNumber(row.volume, 2)}`,
          `手续费: ${formatNumber(row.total_fee, 4)}`,
        ].join("<br/>");
      },
    },
    grid: { left: 80, right: 24, top: 24, bottom: 40 },
    xAxis: { type: "category", data: holds.map((item) => `${item}s`), axisLabel: { color: "#94a3b8" } },
    yAxis: { type: "category", data: layers, axisLabel: { color: "#94a3b8" } },
    visualMap: {
      min: Math.min(...props.rows.map((row) => row.total_pnl ?? 0), 0),
      max: Math.max(...props.rows.map((row) => row.total_pnl ?? 0), 0),
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      textStyle: { color: "#94a3b8" },
      inRange: { color: ["#7f1d1d", "#1e293b", "#14532d"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: {
          show: true,
          color: "#e2e8f0",
          formatter(params) {
            return formatNumber(params.data[2], 2);
          },
        },
      },
    ],
  });
}

onMounted(() => {
  chart = echarts.init(root.value);
  chart.on("click", (params) => {
    if (!params.value) {
      return;
    }
    const [holdIndex, layerIndex] = params.value;
    emit("select", {
      layer: chart.getOption().yAxis[0].data[layerIndex],
      holdSec: Number(chart.getOption().xAxis[0].data[holdIndex].replace("s", "")),
    });
  });
  render();
  window.addEventListener("resize", render);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", render);
  chart?.dispose();
});

watch(() => props.rows, render, { deep: true });
</script>

