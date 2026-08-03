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
  {
    file: "discovery.yml",
    label: "종목 발굴 스캔",
    minute: 0,
    hours: [21], // KST 06:00 (미국장 마감 후, 아침 브리핑 전)
    // 매일 — 주말도 돌려 유니버스 결과를 최신으로 유지
  },
  {
    file: "group_brief.yml",
    label: "단톡방 브리핑",
    minute: 40,
    hours: [23], // KST 08:40 — 개인 장전브리핑(08:30) 직후
    dow: [0, 1, 2, 3, 4], // UTC 일~목 = KST 월~금
  },
  {
    file: "group_summary.yml",
    label: "단톡방 시황 요약",
    minute: 35,
    hours: [0], // KST 09:35 — 시초가 반영, 텍스트 한 통
    dow: [1, 2, 3, 4, 5],
  },
  {
    file: "spike.yml",
    label: "급변동 감지",
    every: 10,
    // KST 09~16시(한국장) + KST 22~06시(미국장). 코인은 이 시간대에만 감시된다.
    hours: [0, 1, 2, 3, 4, 5, 6, 13, 14, 15, 16, 17, 18, 19, 20, 21],
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
        // trim: secret put 에 붙여넣을 때 줄바꿈/공백이 섞여 들어오는 경우가 있다
        Authorization: `Bearer ${(env.GH_TOKEN || "").trim()}`,
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
    const body = await res.text();
    throw new Error(
      `${file} dispatch 실패: ${res.status} ${res.statusText} · body=${body || "(빈 응답)"}`,
    );
  }
}

/** 토큰이 살아 있고 저장소에 권한이 있는지 확인 (진단용). */
async function diagnose(env) {
  const t = env.GH_TOKEN || "";
  console.log(
    `토큰 점검: 길이=${t.length} 접두=${t.slice(0, 11)} ` +
      `공백포함=${/\s/.test(t)} 따옴표포함=${/["']/.test(t)}`,
  );
  const res = await fetch(`https://api.github.com/repos/${OWNER}/${REPO}`, {
    headers: {
      Authorization: `Bearer ${t.trim()}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "jusik-scheduler",
    },
  });
  const j = await res.text();
  console.log(`GET /repos 응답: ${res.status} ${j.slice(0, 200)}`);
}

export default {
  async scheduled(event, env, ctx) {
    // scheduledTime 이 없으면 new Date(undefined) → Invalid Date → 모든 비교가 NaN 이 되어
    // 아무것도 발화하지 않는다. 조용히 죽는 실패라 반드시 폴백을 둔다.
    const ts = event && event.scheduledTime ? event.scheduledTime : Date.now();
    const now = new Date(ts);
    const due = SCHEDULE.filter((j) => isDue(j, now));
    console.log(
      `tick ${now.toISOString()} · 대상 ${due.length}건` +
        (due.length ? `: ${due.map((j) => j.file).join(", ")}` : "") +
        (env.GH_TOKEN ? "" : " · ⚠️ GH_TOKEN 없음"),
    );
    // DIAG 시크릿이 있으면 매 tick 토큰 상태를 찍는다 (문제 해결 후 지우면 됨)
    if (env.DIAG) ctx.waitUntil(diagnose(env).catch((e) => console.error(`진단 실패: ${e}`)));
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

  // 기본 배포는 workers_dev = false 라 이 핸들러에 닿을 주소가 없다.
  // 나중에 주소를 열더라도 수동 실행이 무인증으로 뚫리지 않게 시크릿을 요구한다.
  // (ADMIN_KEY 시크릿을 등록하지 않으면 수동 실행은 비활성)
  async fetch(req, env) {
    const url = new URL(req.url);
    if (!env.ADMIN_KEY || url.searchParams.get("key") !== env.ADMIN_KEY) {
      return new Response("not found", { status: 404 });
    }
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
