<template>
  <div class="sheet" :class="{ 'sheet--shell': isShellLayout }">
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
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/common/AppHeader.vue'

const route = useRoute()

/**
 * 聊天页用「应用外壳」布局：整页锁定在视口高度内，滚动只发生在各自的内部容器里。
 *
 * 其余页面（首页、我的行程、配置）是正常的长文档，应当由页面整体滚动。
 */
const isShellLayout = computed(() => route.path.startsWith('/ai-chat'))
</script>

<style scoped>
.sheet {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ————————————————————————— 应用外壳布局（聊天页）—————————————————————————

   聊天页需要「整页不滚动，只有侧边栏和聊天区各自滚动」。光靠子元素写
   `height: 100%` 做不到：父级高度若是「内容决定」的，百分比会退化成 auto，
   内容一长就把整页撑开 —— 两个面板于是被同一根页面滚动条带着走。

   所以这里从最外层就把高度钉死，并让中间每一层都有确定高度：
     .sheet      -> 100dvh，不滚动
     .sheet-body -> 单行 minmax(0, 1fr)，行高即容器高
     于是 .sheet-content / .chat-page 的 height:100% 才真正解析到可用高度。 */

.sheet--shell {
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
}

.sheet--shell .sheet-body {
  /* 允许收缩到可用高度，而不是被内容顶开 */
  min-height: 0;
  grid-template-rows: minmax(0, 1fr);
}

.sheet--shell .sheet-content {
  min-height: 0;
  overflow: hidden;
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
