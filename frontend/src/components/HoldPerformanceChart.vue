<template>
  <div ref="root" class="chart"></div>
</template>

<script setup>
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { formatNumber } from "../lib/format";

const props = defineProps({
  rows: { type: Array, default: () => [] },
});

const root = ref(null);
let chart;

function render() {
  if (!chart) {
    return;
  }
  const sorted = [...props.rows].sort((a, b) => a.hold_sec - b.hold_sec);
  chart.setOption({
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(15, 23, 42, 0.96)",
      borderColor: "rgba(148, 163, 184, 0.25)",
      textStyle: { color: "#e2e8f0" },
    },
    grid: { left: 40, right: 24, top: 24, bottom: 36 },
    xAxis: { type: "category", data: sorted.map((item) => `${item.hold_sec}s`), axisLabel: { color: "#94a3b8" } },
    yAxis: {
      type: "value",
      axisLabel: { color: "#94a3b8", formatter: (value) => formatNumber(value, 2) },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)" } },
    },
    series: [
      {
        name: "总 PnL",
        type: "bar",
        data: sorted.map((item) => item.total_pnl),
        itemStyle: {
          color(params) {
            return params.value >= 0 ? "#14b8a6" : "#f97316";
          },
        },
      },
    ],
  });
}

onMounted(() => {
  chart = echarts.init(root.value);
  render();
  window.addEventListener("resize", render);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", render);
  chart?.dispose();
});

watch(() => props.rows, render, { deep: true });
</script>

