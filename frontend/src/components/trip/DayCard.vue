<template>
  <section class="day">
    <header class="day-head">
      <span class="day-no num">Day {{ day.day_number }}</span>
      <span class="day-date num">{{ formatDate(day.date) }}</span>
      <span v-if="day.theme" class="day-theme">{{ day.theme }}</span>
      <span v-if="day.weather_info" class="day-weather num">
        <WeatherGlyph
          :weather="day.weather_info.weather"
          :icon="day.weather_info.icon"
          class="day-glyph"
        />
        {{ day.weather_info.weather }}
        <template v-if="day.weather_info.temp_low != null">
          {{ formatTemp(day.weather_info.temp_low) }}° – {{ formatTemp(day.weather_info.temp_high) }}°
        </template>
      </span>
    </header>

    <SpotTimeline :spots="day.spots" />

    <p v-if="day.summary" class="day-summary">{{ day.summary }}</p>
  </section>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import SpotTimeline from './SpotTimeline.vue'
import WeatherGlyph from '../common/WeatherGlyph.vue'
import { formatDateCN } from '../../utils/labels'
import type { ItineraryDay } from '../../types'

defineProps({
  day: {
    type: Object as PropType<ItineraryDay>,
    required: true,
  },
})

function formatTemp(value: number | null | undefined) {
  return value === null || value === undefined ? '—' : value
}

const formatDate = (dateStr: string) => formatDateCN(dateStr)
</script>

<style scoped>
.day + .day {
  margin-top: 26px;
  padding-top: 26px;
  border-top: 1px solid var(--rule-strong);
}

.day-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--ink);
  margin-bottom: 4px;
}

/* Day N 是这一天的编号，用等宽数字对齐，不做胶囊底色 */
.day-no {
  font-size: 13px;
  font-weight: 600;
  color: var(--magenta);
}

.day-date {
  font-size: 14px;
  font-weight: 600;
}

.day-theme {
  font-size: 14px;
  color: var(--ink-2);
}

.day-weather {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--ink-2);
}

.day-glyph {
  width: 18px;
  height: 18px;
}

.day-summary {
  margin: 12px 0 0;
  padding-left: 104px;
  font-size: 13px;
  color: var(--ink-2);
  max-width: 78ch;
}

@media (max-width: 640px) {
  .day-weather {
    margin-left: 0;
  }

  .day-summary {
    padding-left: 0;
  }
}
</style>
