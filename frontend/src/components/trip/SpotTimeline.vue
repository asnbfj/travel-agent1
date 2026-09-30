<template>
  <ol v-if="spots.length" class="timetable">
    <li v-for="(spot, index) in spots" :key="spot.id || index" class="stop">
      <div class="stop-time num">
        <span class="t-start">{{ spot.start_time || '--:--' }}</span>
        <span class="t-sep">–</span>
        <span class="t-end">{{ spot.end_time || '--:--' }}</span>
      </div>

      <div class="stop-main">
        <div class="stop-line">
          <span class="stop-name">{{ spot.name }}</span>
          <span class="stop-meta num">
            <span v-if="spot.category">{{ spot.category }}</span>
            <span>{{ spot.duration_minutes || 120 }} 分钟</span>
            <span>¥{{ spot.estimated_cost || 0 }}</span>
          </span>
        </div>

        <p v-if="spot.notes" class="stop-notes">{{ spot.notes }}</p>

        <p v-if="spot.transport_to_next" class="stop-link">
          <span class="link-label">前往下一站</span>
          {{ spot.transport_to_next }}
        </p>
      </div>
    </li>
  </ol>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import type { ItinerarySpot } from '../../types'

defineProps({
  spots: {
    type: Array as PropType<ItinerarySpot[]>,
    default: () => [],
  },
})
</script>

<style scoped>
/* 时刻表：时间成列对齐，右侧是地点与说明 */
.timetable {
  list-style: none;
  margin: 0;
  padding: 0;
}

.stop {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 18px;
  padding: 11px 0;
  border-top: 1px solid var(--rule);
}

.stop:first-child {
  border-top: none;
}

.stop-time {
  font-size: 13px;
  color: var(--ink);
  display: flex;
  gap: 4px;
  align-items: baseline;
  white-space: nowrap;
}

.t-sep,
.t-end {
  color: var(--ink-3);
}

.stop-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.stop-name {
  font-size: 15px;
  font-weight: 600;
}

.stop-meta {
  display: inline-flex;
  gap: 14px;
  font-size: 12px;
  color: var(--ink-3);
  white-space: nowrap;
}

.stop-notes {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--ink-2);
  max-width: 62ch;
}

/* 与下一站的衔接方式单独成行，说明它是移动而不是游览 */
.stop-link {
  margin: 7px 0 0;
  padding: 5px 10px;
  background: var(--plot-2);
  border-left: 2px solid var(--rule-strong);
  font-size: 12px;
  color: var(--ink-2);
}

.link-label {
  color: var(--ink-3);
  margin-right: 8px;
}

@media (max-width: 640px) {
  .stop {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }

  .stop-line {
    flex-direction: column;
    gap: 2px;
  }
}
</style>
