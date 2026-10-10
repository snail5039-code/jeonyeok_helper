// 전역도우미 웹 채팅
// - 서버(/chat)의 SSE 이벤트를 받아 진행 단계, 답변, 출처를 그린다.
// - 서버 에이전트가 준비되지 않았거나 주소에 ?demo가 있으면 데모 모드로 예시 응답을 보여준다.

const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const inputEl = $("#input");
const sendEl = $("#send");

const SERVICE_TYPES = {
  conscript: "의무복무 병사",
  short_term_officer: "단기 간부",
  long_term: "중·장기 복무",
  merit: "보훈대상자",
};
const SOURCE_LABELS = { regulation: "법령", benefit: "혜택", institution: "기관" };
const AVATAR = '<svg viewBox="0 0 32 32"><path d="M16 6l2.6 5.6 6.1.7-4.5 4.2 1.2 6L16 19.6 10.6 22.5l1.2-6-4.5-4.2 6.1-.7z"/></svg>';

function storageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function storageSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* 저장 불가 환경은 무시 */ }
}

const userId = storageGet("jeonyeok.userId") || crypto.randomUUID();
storageSet("jeonyeok.userId", userId);
let threadId = null;
let demo = new URLSearchParams(location.search).has("demo");
let busy = false;

// ---------- 렌더링 ----------

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function safeUrl(url) {
  return /^https?:\/\//.test(url || "") ? url : null;
}

// 답변에 쓰는 아주 작은 마크다운: ### 제목, - 목록, **굵게**, [n] 출처 번호
function renderAnswer(text, sources) {
  const inline = (s) =>
    escapeHtml(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[(\d+)\]/g, (m, n) => {
        const src = sources[Number(n) - 1];
        const href = src && safeUrl(src.url);
        return src ? `<sup><a ${href ? `href="${href}" target="_blank" rel="noopener"` : ""} title="${escapeHtml(src.title)}">${n}</a></sup>` : m;
      });

  let html = "";
  let inList = false;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const item = line.match(/^[-*•]\s+(.*)/);
    if (item) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(item[1])}</li>`;
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    if (!line) continue;
    const heading = line.match(/^#{1,4}\s+(.*)/);
    if (heading) html += `<h3>${inline(heading[1])}</h3>`;
    else if (line.startsWith("※") || line.includes("소관 기관에 꼭 확인")) html += `<p class="note">${inline(line)}</p>`;
    else html += `<p>${inline(line)}</p>`;
  }
  if (inList) html += "</ul>";
  return html;
}

function renderSources(sources) {
  if (!sources.length) return "";
  return `<div class="sources">${sources
    .map((s, i) => {
      const href = safeUrl(s.url);
      const tag = href ? `a href="${href}" target="_blank" rel="noopener"` : "div";
      return `<${tag} class="source">
        <span class="num">${i + 1}</span>
        <span class="badge ${s.type}">${SOURCE_LABELS[s.type] || "출처"}</span>
        <span class="title">${escapeHtml(s.title)}</span>
      </${href ? "a" : "div"}>`;
    })
    .join("")}</div>`;
}

function updateProfile(profile = {}) {
  for (const dd of document.querySelectorAll("#profile dd")) {
    const key = dd.dataset.key;
    let value = profile[key];
    if (value === undefined || value === null || value === "") continue;
    if (key === "service_type") value = SERVICE_TYPES[value] || value;
    if (key === "service_years") value = `${value}년`;
    if (key === "age") value = `${value}세`;
    if (dd.textContent !== String(value)) {
      dd.textContent = value;
      dd.classList.add("filled", "flash");
      setTimeout(() => dd.classList.remove("flash"), 1200);
    }
  }
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addUserMessage(text) {
  $("#welcome")?.remove();
  const el = document.createElement("div");
  el.className = "msg user";
  el.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  messagesEl.append(el);
  scrollToBottom();
}

function addBotMessage() {
  const el = document.createElement("div");
  el.className = "msg bot";
  el.innerHTML = `<div class="avatar">${AVATAR}</div><div class="body"><ul class="steps"></ul><div class="answer"></div></div>`;
  messagesEl.append(el);
  scrollToBottom();

  const steps = el.querySelector(".steps");
  const answer = el.querySelector(".answer");
  return {
    step(label) {
      steps.querySelector("li:not(.done)")?.classList.add("done");
      const li = document.createElement("li");
      li.textContent = label;
      steps.append(li);
      scrollToBottom();
    },
    finish(text, sources = []) {
      steps.querySelectorAll("li").forEach((li) => li.classList.add("done"));
      const count = steps.children.length;
      steps.classList.add("collapsed");
      if (count > 1) {
        // 끝난 진행 단계는 한 줄 요약으로 접고, 누르면 펼친다.
        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "steps-toggle";
        toggle.textContent = `${count}단계를 거쳐 답변했어요`;
        toggle.setAttribute("aria-expanded", "false");
        toggle.addEventListener("click", () => {
          const open = steps.classList.toggle("collapsed") === false;
          toggle.setAttribute("aria-expanded", String(open));
        });
        steps.before(toggle);
      }
      answer.innerHTML = renderAnswer(text, sources) + renderSources(sources);
      scrollToBottom();
    },
    fail(message) {
      steps.classList.add("collapsed");
      answer.innerHTML = `<p class="error">${escapeHtml(message)}</p>`;
    },
  };
}

// ---------- 서버 통신 ----------

function parseSse(chunk) {
  const event = chunk.match(/^event: (.*)$/m)?.[1];
  const data = chunk.match(/^data: (.*)$/m)?.[1];
  return event ? { event, data: data ? JSON.parse(data) : {} } : null;
}

async function* streamChat(message) {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId, user_id: userId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `서버 오류 (${res.status})`);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const parsed = parseSse(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
      if (parsed) yield parsed;
    }
  }
}

// ---------- 데모 ----------

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const DEMO_ANSWER = {
  profile: { service_type: "conscript", discharge_date: "2025-12", region: "서울" },
  sources: [
    { type: "regulation", title: "국민연금법 제18조(군 복무기간에 대한 노령연금 가입기간 추가 산입)", url: "https://www.law.go.kr/법령/국민연금법/제18조" },
    { type: "institution", title: "국민연금공단", url: "https://www.nps.or.kr" },
    { type: "institution", title: "온통청년", url: "https://www.youthcenter.go.kr" },
    { type: "institution", title: "고용24", url: "https://www.work24.go.kr" },
  ],
  text: [
    "※ 데모 화면이에요. 실제 답변은 법령과 공공서비스 조회 결과로 만들어져요.",
    "의무복무를 마치고 서울에 사신다면 이런 혜택을 확인해 보세요.",
    "### 1. 군복무 크레딧",
    "- **대상**: 병역 의무를 이행한 사람",
    "- **내용**: 군 복무기간 일부를 국민연금 가입기간으로 추가 인정 [1]",
    "- **신청**: 노령연금 청구 시 반영, 자세한 내용은 국민연금공단 [2]",
    "### 2. 서울시 청년 정책",
    "- 지역 청년 정책은 온통청년에서 '서울'로 걸러 보면 한눈에 볼 수 있어요 [3]",
    "### 3. 취업 지원",
    "- 국민취업지원제도, 국민내일배움카드는 고용24에서 신청해요 [4]",
    "정확한 자격은 소관 기관에 꼭 확인하세요.",
  ].join("\n"),
};

async function* demoChat(message) {
  const needsProfile = !/병장|병사|하사|중사|상사|소위|중위|대위|소령|간부|복무|유공자|보훈/.test(message);
  yield { event: "step", data: { label: "복무 정보를 정리하고 있어요" } };
  await sleep(600);
  if (needsProfile && !document.querySelector("#profile dd.filled")) {
    yield {
      event: "question",
      data: { text: "혜택이 복무 형태에 따라 많이 달라요. 병사로 전역하셨나요, 간부로 전역하셨나요? 사시는 지역도 알려주시면 더 정확해요." },
    };
    return;
  }
  for (const label of ["관련 법령을 찾고 있어요", "받을 수 있는 혜택을 조회하고 있어요", "신청 기관을 찾고 있어요", "답변을 정리하고 있어요", "근거를 확인하고 있어요"]) {
    yield { event: "step", data: { label } };
    await sleep(650);
  }
  yield { event: "answer", data: DEMO_ANSWER };
}

// ---------- 전송 ----------

async function send(text) {
  text = text.trim();
  if (!text || busy) return;
  busy = true;
  sendEl.disabled = true;
  inputEl.value = "";
  autoGrow();
  addUserMessage(text);
  const bot = addBotMessage();

  try {
    for await (const { event, data } of (demo ? demoChat : streamChat)(text)) {
      if (event === "thread") threadId = data.thread_id;
      else if (event === "step") bot.step(data.label);
      else if (event === "answer") { bot.finish(data.text, data.sources || []); updateProfile(data.profile); }
      else if (event === "question") { bot.finish(data.text); updateProfile(data.profile); }
      else if (event === "error") bot.fail(data.message);
    }
  } catch (e) {
    bot.fail(e.message || "연결에 실패했어요.");
  } finally {
    busy = false;
    sendEl.disabled = false;
    inputEl.focus();
  }
}

function autoGrow() {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 160)}px`;
}

$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  send(inputEl.value);
});
inputEl.addEventListener("input", autoGrow);
inputEl.addEventListener("keydown", (e) => {
  // 한글 조합 중 Enter는 무시해야 마지막 글자가 두 번 들어가지 않는다.
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send(inputEl.value);
  }
});
document.querySelectorAll(".suggestions button").forEach((btn) =>
  btn.addEventListener("click", () => send(btn.textContent)),
);

// ---------- 시작 ----------

(async function init() {
  try {
    const health = await (await fetch("/health")).json();
    if (!health.agent_ready) demo = true;
    if (!demo) {
      const { profile } = await (await fetch(`/profile/${encodeURIComponent(userId)}`)).json();
      updateProfile(profile);
    }
  } catch {
    demo = true; // 서버 없이 파일로 열었을 때
  }
  $("#mode").hidden = !demo;
})();
