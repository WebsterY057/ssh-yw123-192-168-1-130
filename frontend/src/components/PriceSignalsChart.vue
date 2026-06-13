<template>
  <div v-if="!priceSeries.length" class="empty-chart">当前策略暂无价格曲线数据</div>
  <div v-else ref="root" class="chart large"></div>
</template>

<script setup>
import * as echarts from "echarts";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { formatNumber } from "../lib/format";

const props = defineProps({
  priceSeries: { type: Array, default: () => [] },
  markers: { type: Array, default: () => [] },
  selectedLayer: { type: String, default: "" },
});

const root = ref(null);
let chart;

function render() {
  if (!chart || !props.priceSeries.length) {
    return;
  }
  const filteredMarkers = props.selectedLayer ? props.markers.filter((item) => item.layer === props.selectedLayer) : props.markers;
  chart.setOption({
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(15, 23, 42, 0.96)",
      borderColor: "rgba(148, 163, 184, 0.25)",
      textStyle: { color: "#e2e8f0" },
    },
    legend: {
      top: 8,
      textStyle: { color: "#94a3b8" },
    },
    grid: { left: 40, right: 24, top: 48, bottom: 36 },
    xAxis: { type: "category", data: props.priceSeries.map((item) => item.ts), axisLabel: { show: false } },
    yAxis: {
      type: "value",
      axisLabel: { color: "#94a3b8", formatter: (value) => formatNumber(value, 5) },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)" } },
    },
    series: [
      {
        name: "价格",
        type: "line",
        showSymbol: false,
        smooth: true,
        lineStyle: { color: "#38bdf8", width: 2 },
        data: props.priceSeries.map((item) => item.price),
      },
      {
        name: "信号点",
        type: "scatter",
        symbolSize: 8,
        itemStyle: { color: "#f97316" },
        data: filteredMarkers
          .map((marker) => {
            const index = props.priceSeries.findIndex((point) => point.ts === marker.ts);
            if (index < 0) {
              return null;
            }
            return { value: [marker.ts, marker.price], layer: marker.layer };
          })
          .filter(Boolean),
      },
    ],
  });
}

onMounted(() => {
  if (root.value) {
    chart = echarts.init(root.value);
    render();
    window.addEventListener("resize", render);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", render);
  chart?.dispose();
});

watch(() => [props.priceSeries, props.markers, props.selectedLayer], render, { deep: true });
</script>

