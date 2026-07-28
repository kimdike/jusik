/**
 * 주식 알림 외부 스케줄러 (Cloudflare Workers Cron)
 *
 * 왜 필요한가:
 *   GitHub Actions 의 `schedule:` 크론은 무료 러너에서 best-effort 라 조용히 버려진다.
 *   실측(2026-07-27) 결과 `*​/5` 로 걸어둔 알림이 실제로는 1~4시간에 한 번 돌았다.
 *   반면 `workflow_dispatch` 는 API 로 부르면 곧바로 실행된다.
 *   그래서 "시각을 지키는 일"만 Cloudflare 가 맡고, 실행은 그대로 Actions 가 한다.
 *
 * Cloudflare 크론은 5분마다 한 번만 걸어두고, 무엇을 돌릴지는 아래 표로 판단한다.
 * (크론 트리거를 여러 개 등록하지 않아 무료 플랜 한도를 신경 쓸 필요가 없다)
 *
 * 필요한 것: GitHub PAT (Actions: read/write) 를 GH_TOKEN 시크릿으로 등록
 */

const OWNER = "kimdike";
const REPO = "jusik";

// 모든 시각은 UTC. KST = UTC + 9.
// dow: 0=일 … 6=토 (UTC 기준 요일)
const SCHEDULE = [
  {
    file: "alerts.yml",
    label: "신호·목표가 점검",
    every: 10, // 10분마다
  },
  {
    file: "halt.yml",
    label: "사이드카/CB 감지",
    every: 5, // 5분마다
    hours: [0, 1, 2, 3, 4, 5, 6], // KST 09~15시
    dow: [1, 2, 3, 4, 5],
  },
  {
    file: "hourly.yml",
    label: "정시 점검",
    minute: 0,
    hours: [1, 2, 3, 4, 5, 6, 14, 15, 16, 17, 18, 19, 20, 21], // KST 10~15, 23~06
    dow: [1, 2, 3, 4, 5],
  },
  {
    file: "briefing.yml",
    label: "장 전 브리핑",
    minute: 30,
    hours: [23], // KST 08:30
    dow: [0, 1, 2, 3, 4], // UTC 일~목 = KST 월~금
    inputs: { kind: "pre" },
  },
  {
    file: "briefing.yml",
    label: "장 시작 30분",
    minute: 30,
    hours: [0], // KST 09:30
    dow: [1, 2, 3, 4, 5],
    inputs: { kind: "open" },
  },
  {
    file: "market_wrap.yml",
    label: "하루 정리",
    minute: 0,
    hours: [7], // KST 16:00
    dow: [1, 2, 3, 4, 5],
  },
];

function isDue(job, now) {
  const m = now.getUTCMinutes();
  const h = now.getUTCHours();
  const d = now.getUTCDay();
  if (job.dow && !job.dow.includes(d)) return false;
  if (job.hours && !job.hours.includes(h)) return false;
  if (job.every !== undefined) return m % job.every === 0;
  return m === job.minute;
}

async function dispatch(env, file, inputs) {
  const res = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${file}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "jusik-scheduler",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", ...(inputs ? { inputs } : {}) }),
    },
  );
  if (res.status !== 204) {
    // 성공은 204 No Content
    throw new Error(`${file} dispatch 실패: ${res.status} ${await res.text()}`);
  }
}

export default {
  async scheduled(event, env, ctx) {
    const now = new Date(event.scheduledTime);
    const due = SCHEDULE.filter((j) => isDue(j, now));
    if (!due.length) return;
    ctx.waitUntil(
      Promise.all(
        due.map((j) =>
          dispatch(env, j.file, j.inputs)
            .then(() => console.log(`✅ ${j.label} (${j.file}) 실행 요청`))
            .catch((e) => console.error(`❌ ${j.label}: ${e.message}`)),
        ),
      ),
    );
  },

  // 브라우저로 열면 스케줄 확인. ?run=alerts.yml 로 수동 실행.
  async fetch(req, env) {
    const url = new URL(req.url);
    const run = url.searchParams.get("run");
    if (run) {
      const job = SCHEDULE.find((j) => j.file === run);
      if (!job) return new Response(`허용되지 않은 워크플로우: ${run}`, { status: 400 });
      try {
        await dispatch(env, run, job.inputs);
        return new Response(`✅ ${run} 실행 요청됨`);
      } catch (e) {
        return new Response(`❌ ${e.message}`, { status: 502 });
      }
    }
    const now = new Date();
    const lines = SCHEDULE.map((j) => {
      const when = j.every !== undefined ? `${j.every}분마다` : `매시 ${j.minute}분`;
      const hrs = j.hours ? ` · UTC ${j.hours.join(",")}시` : " · 24시간";
      return `  ${j.file.padEnd(16)} ${when.padEnd(8)}${hrs}  (${j.label})`;
    });
    return new Response(
      `주식 알림 스케줄러\n현재 UTC ${now.toISOString()}\n\n${lines.join("\n")}\n\n` +
        `수동 실행: ?run=alerts.yml\n`,
      { headers: { "content-type": "text/plain; charset=utf-8" } },
    );
  },
};
