<template>
  <svg class="glyph" :class="`glyph--${kind}`" viewBox="0 0 32 32" aria-hidden="true">
    <!-- 晴 -->
    <template v-if="kind === 'sun'">
      <circle cx="16" cy="16" r="6" />
      <g class="rays">
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="16" y1="26" x2="16" y2="30" />
        <line x1="2" y1="16" x2="6" y2="16" />
        <line x1="26" y1="16" x2="30" y2="16" />
        <line x1="6.1" y1="6.1" x2="8.9" y2="8.9" />
        <line x1="23.1" y1="23.1" x2="25.9" y2="25.9" />
        <line x1="6.1" y1="25.9" x2="8.9" y2="23.1" />
        <line x1="23.1" y1="8.9" x2="25.9" y2="6.1" />
      </g>
    </template>

    <!-- 多云：日与云 -->
    <template v-else-if="kind === 'partly'">
      <circle cx="11" cy="11" r="4.6" class="accent" />
      <path class="cloud" d="M9,25 h13.5 a4.5,4.5 0 0 0 0.4,-8.98 a6.4,6.4 0 0 0 -12.1,-1.4 a4.5,4.5 0 0 0 -1.8,10.38 Z" />
    </template>

    <!-- 雨 -->
    <template v-else-if="kind === 'rain'">
      <path class="cloud" d="M8,20 h16 a4.4,4.4 0 0 0 0.3,-8.78 a6.3,6.3 0 0 0 -11.9,-1.3 a4.4,4.4 0 0 0 -4.4,10.08 Z" />
      <g class="accent-stroke">
        <line x1="11" y1="24" x2="9.5" y2="28" />
        <line x1="16" y1="24" x2="14.5" y2="28" />
        <line x1="21" y1="24" x2="19.5" y2="28" />
      </g>
    </template>

    <!-- 雪 -->
    <template v-else-if="kind === 'snow'">
      <path class="cloud" d="M8,20 h16 a4.4,4.4 0 0 0 0.3,-8.78 a6.3,6.3 0 0 0 -11.9,-1.3 a4.4,4.4 0 0 0 -4.4,10.08 Z" />
      <g class="accent-stroke">
        <line x1="11" y1="24.5" x2="11" y2="27.5" />
        <line x1="9.6" y1="26" x2="12.4" y2="26" />
        <line x1="16" y1="24.5" x2="16" y2="27.5" />
        <line x1="14.6" y1="26" x2="17.4" y2="26" />
        <line x1="21" y1="24.5" x2="21" y2="27.5" />
        <line x1="19.6" y1="26" x2="22.4" y2="26" />
      </g>
    </template>

    <!-- 雾 / 霾 -->
    <template v-else-if="kind === 'fog'">
      <g class="rays">
        <line x1="5" y1="12" x2="27" y2="12" />
        <line x1="8" y1="17" x2="24" y2="17" />
        <line x1="5" y1="22" x2="27" y2="22" />
      </g>
    </template>

    <!-- 阴 -->
    <template v-else>
      <path class="cloud" d="M7,23 h17 a4.7,4.7 0 0 0 0.3,-9.38 a6.7,6.7 0 0 0 -12.7,-1.4 a4.7,4.7 0 0 0 -4.6,10.78 Z" />
    </template>
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  /** 天气文字，如「晴」「多云」「小雨」 */
  weather?: string | null
  /** 上游给的图标字符，作为兜底判断 */
  icon?: string | null
}>()

const kind = computed(() => {
  const text = `${props.weather || ''}${props.icon || ''}`
  if (/雷|阵雨|大雨|中雨|小雨|雨/.test(text)) return 'rain'
  if (/雪|冰|冻/.test(text)) return 'snow'
  if (/雾|霾|沙|尘/.test(text)) return 'fog'
  if (/多云|少云|晴间/.test(text)) return 'partly'
  if (/晴/.test(text)) return 'sun'
  return 'cloud'
})
</script>

<style scoped>
.glyph {
  width: 26px;
  height: 26px;
  fill: none;
  stroke: var(--ink-2);
  stroke-width: 1.5;
  stroke-linecap: round;
}

.glyph path.cloud {
  fill: var(--plot-2);
  stroke: var(--ink-2);
}

.glyph .accent {
  stroke: var(--shoal);
  fill: none;
}

.glyph .accent-stroke line {
  stroke: var(--shoal);
}

.glyph .rays line {
  stroke: var(--ink-3);
}
</style>
