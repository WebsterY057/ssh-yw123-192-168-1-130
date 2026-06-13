import { defineStore } from "pinia";

const API_BASE = import.meta.env.VITE_API_BASE || "";

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export const useDashboardStore = defineStore("dashboard", {
  state: () => ({
    loading: false,
    error: "",
    strategies: [],
    selectedStrategyId: "",
    selectedDate: "",
    selectedMetric: "total_pnl",
    selectedLayer: "",
    selectedHoldSec: null,
    overview: null,
    dayDetail: null,
  }),
  actions: {
    async initialize() {
      this.loading = true;
      this.error = "";
      try {
        const payload = await fetchJson("/api/strategies");
        this.strategies = payload.strategies || [];
        if (!this.selectedStrategyId && this.strategies.length) {
          this.selectedStrategyId = this.strategies[0].strategy_id;
        }
        await this.loadOverview();
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error);
      } finally {
        this.loading = false;
      }
    },
    async loadOverview() {
      if (!this.selectedStrategyId) {
        return;
      }
      this.loading = true;
      this.error = "";
      try {
        const payload = await fetchJson(`/api/overview?strategy_id=${encodeURIComponent(this.selectedStrategyId)}`);
        this.overview = payload;
        const dates = payload.meta?.available_dates || [];
        if (!dates.includes(this.selectedDate)) {
          this.selectedDate = dates[dates.length - 1] || "";
        }
        const layers = payload.meta?.available_layers || [];
        if (!layers.includes(this.selectedLayer)) {
          this.selectedLayer = "";
        }
        const holds = payload.meta?.available_holds || [];
        if (!holds.includes(this.selectedHoldSec)) {
          this.selectedHoldSec = holds[0] || null;
        }
        await this.loadDayDetail();
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error);
      } finally {
        this.loading = false;
      }
    },
    async loadDayDetail() {
      if (!this.selectedStrategyId || !this.selectedDate) {
        this.dayDetail = null;
        return;
      }
      this.loading = true;
      this.error = "";
      try {
        const payload = await fetchJson(
          `/api/day-detail?strategy_id=${encodeURIComponent(this.selectedStrategyId)}&date=${encodeURIComponent(this.selectedDate)}`
        );
        this.dayDetail = payload;
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error);
      } finally {
        this.loading = false;
      }
    },
    async refreshCache() {
      this.loading = true;
      this.error = "";
      try {
        await fetchJson("/api/cache/rebuild", { method: "POST" });
        await this.loadOverview();
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error);
      } finally {
        this.loading = false;
      }
    },
  },
});

