<template>
  <div class="home">
    <!-- 首屏：一句话进来，一条航线出去 -->
    <section class="hero">
      <div class="hero-top">
        <div class="hero-copy">
          <h1 class="title-song">用一句话，<br />排出一份走得通的行程。</h1>
          <p class="lede">
            说出目的地、日期、同行人数和预算。它会联网查逐日天气、找正在开放的景点与住宿、
            算地面交通，再把每天的时刻、门票和衔接方式排成一张能照着走的表。
          </p>
          <div class="hero-actions">
            <a-button type="primary" size="large" @click="go('/ai-chat')">
              开始智能规划
            </a-button>
            <a-button size="large" @click="go('/trip/create')">手动创建行程</a-button>
          </div>
        </div>

        <div class="hero-spine" aria-hidden="true">
          <span class="title-song">旅行智脑</span>
        </div>
      </div>

      <figure class="chart">
        <figcaption class="chart-cap">
          <span class="chart-cap-name">示例航线</span>
          <span>东京赏樱 5 日，2 人同行，预算约 ¥20,000</span>
        </figcaption>

        <div class="chart-scroll">
        <svg
          class="chart-svg"
          viewBox="0 0 720 250"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          aria-label="示例行程路线：第一天浅草与隅田川，第二天上野与千鸟渊，第三天新宿御苑与涩谷，第四天镰仓与江之岛，第五天筑地与返程。"
        >
          <!-- 经纬网 -->
          <g class="graticule">
            <line
              v-for="x in 12"
              :key="`v${x}`"
              :x1="(x - 1) * 60"
              y1="0"
              :x2="(x - 1) * 60"
              y2="250"
            />
            <line
              v-for="y in 5"
              :key="`h${y}`"
              x1="0"
              :y1="(y - 1) * 50"
              x2="720"
              :y2="(y - 1) * 50"
            />
          </g>

          <!-- 海岸线：图面上的陆地图斑 -->
          <path
            class="coast"
            d="M0,250 L0,208 C 88,198 152,224 232,216 C 322,207 366,180 452,188 C 542,196 612,176 720,184 L720,250 Z"
          />

          <!-- 航线：载入时自起点绘制到终点 -->
          <path
            class="route"
            pathLength="1"
            d="M64,186 L200,120 L340,150 L480,74 L648,104"
          />

          <!-- 途经点 -->
          <g
            v-for="(p, i) in waypoints"
            :key="p.place"
            class="wp"
            :style="{ '--d': `${0.5 + i * 0.16}s` }"
          >
            <template v-if="i === waypoints.length - 1">
              <circle :cx="p.x" :cy="p.y" r="7" class="wp-arrive-ring" />
              <circle :cx="p.x" :cy="p.y" r="3.5" class="wp-stop" />
            </template>
            <circle
              v-else
              :cx="p.x"
              :cy="p.y"
              :r="i === 0 ? 4.5 : 3.5"
              :class="i === 0 ? 'wp-origin' : 'wp-stop'"
            />
            <text :x="p.x" :y="p.y - 15" class="wp-day">{{ p.day }}</text>
            <text :x="p.x" :y="p.y + 24" class="wp-place">{{ p.place }}</text>
          </g>
        </svg>
        </div>
      </figure>
    </section>

    <!-- 它替你跑的活 -->
    <section class="block">
      <h2 class="sec-title">它替你跑的活</h2>
      <dl class="work-list">
        <div v-for="w in work" :key="w.title" class="work-item">
          <dt>{{ w.title }}</dt>
          <dd>{{ w.desc }}</dd>
        </div>
      </dl>
    </section>

    <!-- 我的行程 -->
    <section v-if="auth.isLoggedIn" class="block">
      <div class="sec-head">
        <h2 class="sec-title">我的行程</h2>
        <router-link to="/plan" class="sec-link">全部行程</router-link>
      </div>

      <div v-if="recentTrips.length" class="trip-table">
        <div class="trip-row trip-row--head">
          <span>行程</span>
          <span>目的地</span>
          <span>日期</span>
          <span>状态</span>
        </div>
        <router-link
          v-for="t in recentTrips"
          :key="t.id"
          :to="`/trip/${t.id}`"
          class="trip-row"
        >
          <span class="trip-title">{{ t.title }}</span>
          <span class="muted">{{ t.destination }}</span>
          <span class="muted num">
            {{ formatDateRange(t.start_date, t.end_date) }}
          </span>
          <span class="status" :class="`status--${tripStatusTone(t.status)}`">
            {{ tripStatusLabel(t.status) }}
          </span>
        </router-link>
      </div>

      <div v-else class="empty">
        <p>还没有行程。让 AI 先排一份，或者自己填一张表。</p>
        <a-button type="primary" @click="go('/ai-chat')">开始智能规划</a-button>
      </div>
    </section>

    <!-- 它怎么决定下一步 -->
    <section class="block loop">
      <div class="loop-copy">
        <h2 class="sec-title">它怎么决定下一步</h2>
        <p>
          没有固定的流水线。每一轮由模型自己判断：还缺什么信息，就调用哪个工具；
          信息够了，就开始写行程。
        </p>
        <p class="muted">
          四个工具挂在同一个循环上，一次规划里可以调用零次、一次或多次。
        </p>
      </div>

      <svg
        class="compass"
        viewBox="0 0 520 380"
        role="img"
        aria-label="工具调用循环：模型在天气、景点、住宿、路线四个工具之间自行选择，并把结果带回下一轮。"
      >
        <defs>
          <marker
            id="loop-arrow"
            viewBox="0 0 8 8"
            refX="6"
            refY="4"
            markerWidth="7"
            markerHeight="7"
            orient="auto"
          >
            <path d="M0,1 L7,4 L0,7 Z" class="loop-arrow-head" />
          </marker>
        </defs>

        <circle cx="260" cy="190" r="100" class="compass-ring" />
        <circle cx="260" cy="190" r="78" class="compass-guide" />

        <g class="loop-arcs">
          <path d="M350.6,232.3 A100,100 0 0 1 302.3,280.6" marker-end="url(#loop-arrow)" />
          <path d="M217.7,280.6 A100,100 0 0 1 169.4,232.3" marker-end="url(#loop-arrow)" />
          <path d="M169.4,147.7 A100,100 0 0 1 217.7,99.4" marker-end="url(#loop-arrow)" />
          <path d="M302.3,99.4 A100,100 0 0 1 350.6,147.7" marker-end="url(#loop-arrow)" />
        </g>

        <g class="compass-node">
          <circle cx="260" cy="90" r="5.5" />
          <circle cx="360" cy="190" r="5.5" />
          <circle cx="260" cy="290" r="5.5" />
          <circle cx="160" cy="190" r="5.5" />
        </g>

        <circle cx="260" cy="190" r="46" class="compass-hub" />
        <text x="260" y="182" class="hub-title">模型</text>
        <text x="260" y="198" class="hub-line">选择工具</text>
        <text x="260" y="211" class="hub-line">决定轮次</text>

        <g class="compass-labels">
          <text x="260" y="68" class="node-title" text-anchor="middle">天气</text>
          <text x="260" y="52" class="node-source" text-anchor="middle">高德地图</text>

          <text x="384" y="186" class="node-title">景点与必玩地点</text>
          <text x="384" y="202" class="node-source">博查联网检索</text>

          <text x="260" y="314" class="node-title" text-anchor="middle">路线规划</text>
          <text x="260" y="330" class="node-source" text-anchor="middle">高德地图</text>

          <text x="136" y="186" class="node-title" text-anchor="end">住宿</text>
          <text x="136" y="202" class="node-source" text-anchor="end">博查联网检索</text>
        </g>
      </svg>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useTripStore } from '../stores/trip'
import { formatDateRange, tripStatusLabel, tripStatusTone } from '../utils/labels'

const router = useRouter()
const auth = useAuthStore()
const tripStore = useTripStore()

const waypoints = [
  { x: 64, y: 186, day: '第 1 天', place: '浅草、隅田川' },
  { x: 200, y: 120, day: '第 2 天', place: '上野、千鸟渊' },
  { x: 340, y: 150, day: '第 3 天', place: '新宿御苑、涩谷' },
  { x: 480, y: 74, day: '第 4 天', place: '镰仓、江之岛' },
  { x: 648, y: 104, day: '第 5 天', place: '筑地、返程' },
]

const work = [
  {
    title: '先把天看清楚',
    desc: '出行日期内的逐日预报来自高德地图，下雨的那天，户外景点会被挪到别的日子。',
  },
  {
    title: '景点和住宿现查',
    desc: '通过联网检索拿正在开放的地点、位置和大致价位，不用写死的样例数据。',
  },
  {
    title: '排成一张时刻表',
    desc: '每个景点的到达时间、游览时长、门票和到下一站的方式，逐条列出来。',
  },
  {
    title: '想改，说一句就行',
    desc: '增删景点、换住宿、压预算，说清楚要改什么，行程表跟着重排。',
  },
]

const recentTrips = computed(() => tripStore.trips.slice(0, 5))

function go(path: string) {
  router.push(path)
}

onMounted(() => {
  if (auth.isLoggedIn) {
    tripStore.fetchTrips().catch(() => {})
  }
})
</script>

<style scoped>
.home {
  padding-bottom: 20px;
}

/* ————————————————————————— 首屏 ————————————————————————— */

.hero {
  padding: 44px 0 8px;
}

.hero-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 28px;
}

.hero-copy h1 {
  font-size: 42px;
  line-height: 1.32;
  letter-spacing: 0.015em;
}

.lede {
  margin: 16px 0 0;
  max-width: 54ch;
  color: var(--ink-2);
  font-size: 15px;
}

.hero-actions {
  display: flex;
  gap: 12px;
  margin-top: 26px;
}

/* 竖排的中文名，像图上贴的签条 */
.hero-spine {
  flex: none;
  writing-mode: vertical-rl;
  padding: 2px 0 2px 10px;
  border-left: 1px solid var(--rule);
  color: var(--ink-3);
}

.hero-spine span {
  font-size: 15px;
  letter-spacing: 0.42em;
}

/* ————————————————————————— 航线图 ————————————————————————— */

.chart {
  margin: 34px 0 0;
  background: var(--plot);
  border: 1px solid var(--rule);
  border-radius: 2px;
}

.chart-cap {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--rule);
  font-size: 12px;
  color: var(--ink-3);
}

.chart-cap-name {
  font-weight: 600;
  color: var(--ink);
  font-size: 13px;
}

.chart-scroll {
  overflow-x: auto;
}

.chart-svg {
  display: block;
  width: 100%;
  height: auto;
}

.graticule line {
  stroke: var(--rule);
  stroke-width: 1;
  opacity: 0.55;
}

.coast {
  fill: var(--sand);
  opacity: 0.4;
}

.route {
  fill: none;
  stroke: var(--magenta);
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  animation: draw-route 1.5s 0.15s cubic-bezier(0.35, 0, 0.2, 1) forwards;
}

@keyframes draw-route {
  to {
    stroke-dashoffset: 0;
  }
}

.wp {
  opacity: 0;
  animation: plot-point 0.45s ease-out forwards;
  animation-delay: var(--d);
}

@keyframes plot-point {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.wp-origin {
  fill: var(--magenta);
}

.wp-stop {
  fill: var(--plot);
  stroke: var(--ink);
  stroke-width: 1.6;
}

.wp-arrive-ring {
  fill: none;
  stroke: var(--magenta);
  stroke-width: 1.4;
}

.wp-day {
  font-family: var(--font-ui);
  font-size: 10px;
  fill: var(--ink-3);
  text-anchor: middle;
}

/* 图上的地名按制图惯例用宋体 */
.wp-place {
  font-family: var(--font-song);
  font-size: 13px;
  fill: var(--ink);
  text-anchor: middle;
}

/* ————————————————————————— 通用区块 ————————————————————————— */

.block {
  margin-top: 52px;
}

.sec-title {
  font-family: var(--font-song);
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.sec-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.sec-link {
  font-size: 13px;
  color: var(--ink-2);
  border-bottom: 1px solid var(--rule-strong);
}

.sec-link:hover {
  color: var(--magenta);
  border-bottom-color: var(--magenta);
}

.muted {
  color: var(--ink-2);
}

/* ————————————————————————— 能力清单 ————————————————————————— */

.work-list {
  margin: 18px 0 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 40px;
}

.work-item {
  padding: 14px 0;
  border-top: 1px solid var(--rule);
}

.work-item dt {
  font-weight: 600;
  font-size: 15px;
}

.work-item dd {
  margin: 4px 0 0;
  color: var(--ink-2);
  font-size: 14px;
  max-width: 44ch;
}

/* ————————————————————————— 行程表 ————————————————————————— */

.trip-table {
  border: 1px solid var(--rule);
  background: var(--plot);
  border-radius: 2px;
}

.trip-row {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 1fr) 88px;
  gap: 16px;
  align-items: center;
  padding: 11px 16px;
  border-top: 1px solid var(--rule);
  font-size: 14px;
  transition: background 0.15s ease;
}

.trip-row:first-child {
  border-top: none;
}

.trip-row--head {
  font-size: 12px;
  color: var(--ink-3);
  background: var(--plot-2);
}

a.trip-row:hover {
  background: var(--paper-2);
}

.trip-title {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty {
  border: 1px solid var(--rule);
  background: var(--plot);
  padding: 30px 20px;
  text-align: center;
}

.empty p {
  margin: 0 0 14px;
  color: var(--ink-2);
}

/* ————————————————————————— 工具调用循环 ————————————————————————— */

.loop {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 460px;
  gap: 40px;
  align-items: center;
}

.loop-copy p {
  margin: 14px 0 0;
  max-width: 46ch;
  color: var(--ink-2);
}

.compass {
  width: 100%;
  max-width: 460px;
  height: auto;
  justify-self: end;
}

.compass-ring {
  fill: none;
  stroke: var(--rule);
  stroke-width: 1;
}

.compass-guide {
  fill: none;
  stroke: var(--rule);
  stroke-width: 1;
  stroke-dasharray: 2 5;
  opacity: 0.8;
}

.loop-arcs path {
  fill: none;
  stroke: var(--magenta);
  stroke-width: 1.4;
}

.loop-arrow-head {
  fill: var(--magenta);
}

.compass-node circle {
  fill: var(--plot);
  stroke: var(--ink);
  stroke-width: 1.6;
}

.compass-hub {
  fill: var(--plot);
  stroke: var(--ink);
  stroke-width: 1.2;
}

.hub-title {
  font-family: var(--font-song);
  font-size: 16px;
  font-weight: 700;
  fill: var(--ink);
  text-anchor: middle;
}

.hub-line {
  font-size: 10px;
  fill: var(--ink-3);
  text-anchor: middle;
}

.node-title {
  font-size: 13px;
  font-weight: 600;
  fill: var(--ink);
}

.node-source {
  font-size: 11px;
  fill: var(--ink-3);
}

/* ————————————————————————— 窄屏 ————————————————————————— */

@media (max-width: 1040px) {
  .loop {
    grid-template-columns: minmax(0, 1fr);
    gap: 24px;
  }

  .compass {
    justify-self: center;
  }
}

@media (max-width: 860px) {
  .hero {
    padding-top: 28px;
  }

  /* 图上地名缩到 6px 就没法读了：宁可让图横向滑动，也不缩小字 */
  .chart-svg {
    min-width: 640px;
  }

  .hero-copy h1 {
    font-size: 30px;
  }

  .hero-spine {
    display: none;
  }

  .work-list {
    grid-template-columns: minmax(0, 1fr);
  }

  .trip-row {
    grid-template-columns: minmax(0, 1fr) auto;
    row-gap: 4px;
  }

  .trip-row--head span:nth-child(2),
  .trip-row--head span:nth-child(3) {
    display: none;
  }

  .trip-row .muted {
    grid-column: 1 / -1;
  }
}
</style>
