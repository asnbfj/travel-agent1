<template>
  <div class="sheet">
    <AppHeader />

    <div class="sheet-body">
      <!-- 图廓：页面左侧的标尺，刻度只表示位置，不装饰 -->
      <div class="sheet-rail" aria-hidden="true"></div>

      <main class="sheet-content">
        <router-view />
      </main>
    </div>

    <footer class="sheet-foot">
      <div class="foot-inner">
        <div class="foot-mark">
          <span class="title-song">TravelAI</span>
          <span class="foot-note">旅行智脑，本地部署实例</span>
        </div>

        <dl class="legend">
          <div class="legend-row">
            <dt>天气与路线</dt>
            <dd>高德地图 Web 服务</dd>
          </div>
          <div class="legend-row">
            <dt>景点与住宿</dt>
            <dd>博查 AI 联网检索</dd>
          </div>
          <div class="legend-row">
            <dt>行程编排</dt>
            <dd>LangGraph 工具调用循环</dd>
          </div>
        </dl>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import AppHeader from './components/common/AppHeader.vue'
</script>

<style scoped>
.sheet {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.sheet-body {
  flex: 1;
  display: grid;
  grid-template-columns: var(--rail) minmax(0, 1fr);
  max-width: calc(var(--page-max) + var(--rail) * 2);
  width: 100%;
  margin: 0 auto;
  padding: 0 24px;
}

/* 左侧标尺：每 64px 一道短刻度，每 256px 一道长刻度 */
.sheet-rail {
  border-right: 1px solid var(--rule);
  background-image: repeating-linear-gradient(
      to bottom,
      var(--rule) 0 1px,
      transparent 1px 64px
    ),
    repeating-linear-gradient(
      to bottom,
      var(--rule-strong) 0 1px,
      transparent 1px 256px
    );
  background-size: 9px 100%, 16px 100%;
  background-position: left top, left top;
  background-repeat: repeat-y, repeat-y;
}

.sheet-content {
  padding: 0 0 48px 28px;
  min-width: 0;
}

.sheet-foot {
  border-top: 1px solid var(--rule-strong);
  background: var(--paper-2);
}

.foot-inner {
  max-width: calc(var(--page-max) + var(--rail) * 2);
  margin: 0 auto;
  padding: 22px 24px 26px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.foot-mark {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.foot-mark .title-song {
  font-size: 16px;
}

.foot-note {
  font-size: 12px;
  color: var(--ink-3);
}

/* 数据来源写成图例，而不是一串用点号连起来的技术名词 */
.legend {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, auto));
  gap: 6px 34px;
}

.legend-row {
  display: flex;
  flex-direction: column;
}

.legend dt {
  font-size: 11px;
  color: var(--ink-3);
}

.legend dd {
  margin: 0;
  font-size: 13px;
  color: var(--ink-2);
}

@media (max-width: 860px) {
  .sheet-body {
    grid-template-columns: minmax(0, 1fr);
    padding: 0 16px;
  }

  .sheet-rail {
    display: none;
  }

  .sheet-content {
    padding-left: 0;
  }

  .legend {
    grid-template-columns: repeat(2, minmax(0, auto));
  }
}
</style>
