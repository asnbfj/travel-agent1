<template>
  <div v-if="weather" class="forecast">
    <div class="forecast-head">
      <span class="forecast-city">{{ weather.city }} 逐日预报</span>
      <span class="forecast-source">
        <span>来源 {{ weather.source || '高德地图' }}</span>
        <span v-if="weather.report_time">发布 {{ weather.report_time }}</span>
      </span>
    </div>

    <div class="forecast-days">
      <div
        v-for="day in (weather.forecasts || []).slice(0, 5)"
        :key="day.date"
        class="forecast-day"
      >
        <div class="fd-weekday">{{ day.weekday }}</div>
        <WeatherGlyph :weather="day.weather" :icon="day.icon" />
        <div class="fd-weather">{{ day.weather }}</div>
        <div class="fd-temp num">
          {{ formatTemp(day.temp_low) }}° – {{ formatTemp(day.temp_high) }}°
        </div>
      </div>
    </div>

    <p v-if="weather.tips" class="forecast-tips">{{ weather.tips }}</p>
  </div>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import WeatherGlyph from './WeatherGlyph.vue'
import type { WeatherInfo } from '../../types'

defineProps({
  weather: {
    type: Object as PropType<WeatherInfo | undefined>,
    default: undefined,
  },
})

/** 上游可能不提供温度，避免渲染成 "null°" */
const formatTemp = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : value
</script>

<style scoped>
.forecast {
  border: 1px solid var(--rule);
  background: var(--plot);
}

.forecast-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 14px;
  border-bottom: 1px solid var(--rule);
  background: var(--plot-2);
  font-size: 12px;
  color: var(--ink-3);
}

.forecast-city {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}

.forecast-source {
  display: inline-flex;
  gap: 12px;
}

.forecast-days {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.forecast-day {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 14px 6px;
  border-left: 1px solid var(--rule);
}

.forecast-day:first-child {
  border-left: none;
}

.fd-weekday {
  font-size: 12px;
  color: var(--ink-2);
}

.fd-weather {
  font-size: 12px;
  color: var(--ink-2);
}

.fd-temp {
  font-size: 12px;
  color: var(--shoal);
}

.forecast-tips {
  margin: 0;
  padding: 10px 14px;
  border-top: 1px solid var(--rule);
  font-size: 13px;
  color: var(--ink-2);
}

/* 窄屏：五天并排会让温度折行，改成三列两行 */
@media (max-width: 640px) {
  .forecast-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }

  .forecast-days {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .forecast-day {
    border-left: 1px solid var(--rule);
  }

  .forecast-day:nth-child(3n + 1) {
    border-left: none;
  }

  .forecast-day:nth-child(n + 4) {
    border-top: 1px solid var(--rule);
  }

  .fd-temp {
    white-space: nowrap;
  }
}
</style>
