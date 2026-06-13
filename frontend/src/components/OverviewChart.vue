<template>
  <div ref="root" class="chart"></div>
</template>

<script setup>
import * as echarts from "echarts";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { formatNumber, formatPercent } from "../lib/format";

const props = defineProps({
  rows: { type: Array, default: () => [] },
  metric: { type: String, required: true },
});

const root = ref(null);
let chart;

const grouped = computed(() => {
  const byLayer = new Map();
  for (const row of props.rows) {
    const layer = row.layer || "unknown";
    if (!byLayer.has(layer)) {
      byLayer.set(layer, []);
    }
    byLayer.get(layer).push(row);
  }
  return [...byLayer.entries()].map(([layer, rows]) => ({
    layer,
    rows: rows.sort((a, b) => a.date.localeCompare(b.date)),
  }));
});

function render() {
  if (!chart) {
    return;
  }
  chart.setOption({
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(15, 23, 42, 0.96)",
      borderColor: "rgba(148, 163, 184, 0.25)",
      textStyle: { color: "#e2e8f0" },
      formatter(params) {
        const header = params[0]?.axisValue || "";
        const lines = params.map((item) => {
          const value =
            props.metric === "win_ratio"
              ? formatPercent(item.value, 2)
              : formatNumber(item.value, 4);
          return `${item.marker}${item.seriesName}: ${value}`;
        });
        return [header, ...lines].join("<br/>");
      },
    },
    legend: {
      top: 8,
      textStyle: { color: "#94a3b8" },
    },
    grid: { left: 40, right: 24, top: 48, bottom: 36 },
    xAxis: {
      type: "category",
      data: [...new Set(props.rows.map((row) => row.date))].sort(),
      axisLabel: { color: "#94a3b8" },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: "#94a3b8",
        formatter(value) {
          return props.metric === "win_ratio" ? `${(value * 100).toFixed(0)}%` : formatNumber(value, 2);
        },
      },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)" } },
    },
    series: grouped.value.map((group) => ({
      name: group.layer,
      type: "line",
      smooth: true,
      symbolSize: 8,
      data: group.rows.map((row) => row[props.metric]),
    })),
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

watch(() => [props.rows, props.metric], render, { deep: true });
</script>

