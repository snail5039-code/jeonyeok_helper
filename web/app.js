// 전역도우미 웹 화면
// - 첫 화면(home)에서 질문하면 대화 화면(chat)으로 넘어간다.
// - 서버 /chat 의 SSE 이벤트(thread, step, answer, question, error, done)로 한 턴을 그린다.
// - 답변 글의 "### 혜택명 | 기관" 블록은 혜택 카드로, [n]은 근거 자료 링크로 바꾼다.
// - 서버 에이전트가 준비되지 않았거나 주소에 ?demo가 있으면 예시 응답(데모 모드)을 쓴다.

const $ = (sel, root = document) => root.querySelector(sel);
const els = {
  home: $("#home"), chat: $("#chat"), dock: $("#dock"), thread: $("#thread"),
  homeForm: $("#home-form"), homeInput: $("#home-input"),
  chatForm: $("#chat-form"), chatInput: $("#chat-input"), chatSend: $("#chat-send"),
  railSources: $("#rail-sources"), railDate: $("#rail-date"),
  history: $("#history"), historyWrap: $("#history-wrap"), crumb: $("#crumb-title"),
  sidebar: $("#sidebar"), scrim: $("#scrim"), mode: $("#mode"), theme: $("#theme"),
};

const SERVICE_TYPES = {
  conscript: "의무복무 병사", short_term_officer: "단기 간부", long_term: "중·장기 복무", merit: "보훈대상자",
};
const SOURCE_KINDS = { regulation: ["법령", "law"], benefit: ["혜택", "org"], institution: ["기관", "org"] };
const ICON_RULES = [
  [/연금|크레딧/, "pension"], [/취업|일자리|전직|구직|훈련/, "briefcase"], [/학|장학|등록금/, "grad"],
  [/예비군|병역|병무|병적/, "badge"], [/보훈|유공/, "shield"], [/서울|경기|부산|지역|시 |도 |청년/, "pin"],
];

const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* 저장 불가 환경 */ } },
};

const userId = store.get("jeonyeok.userId") || crypto.randomUUID();
store.set("jeonyeok.userId", userId);
let threadId = null;
let demo = new URLSearchParams(location.search).has("demo");
let busy = false;
let selectedType = null;
let turnCount = 0;

// ---------- 공통 ----------

const icon = (name, cls = "i") => `<svg class="${cls}"><use href="#ic-${name}"/></svg>`;
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const safeUrl = (url) => (/^https?:\/\//.test(url || "") ? url : null);
const domain = (url) => { try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; } };
const today = () => { const d = new Date(); return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")} 조회`; };
const iconFor = (text) => ICON_RULES.find(([re]) => re.test(text))?.[1] || "gift";

function inline(text, sources) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(\d+)\]/g, (m, n) => {
      const src = sources[Number(n) - 1];
      if (!src) return m;
      const href = safeUrl(src.url);
      const attrs = href ? `href="${href}" target="_blank" rel="noopener"` : "";
      return `<a class="cite" ${attrs} title="${escapeHtml(src.title)}">${n}</a>`;
    });
}

// ---------- 답변 렌더링 ----------

// 답변을 [요약 문단] [혜택 카드들] [마무리 문단]으로 나눈다.
function parseAnswer(text) {
  const lead = [], benefits = [], tail = [];
  let current = null;
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const heading = line.match(/^#{2,4}\s+(?:\d+\.\s*)?(.+)$/);
    if (heading) {
      const [title, org = ""] = heading[1].split("|").map((s) => s.trim());
      current = { title, org, fields: [], extra: [] };
      benefits.push(current);
      continue;
    }
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (current && bullet) {
      const kv = bullet[1].match(/^\*{0,2}([^:：*]{1,8})\*{0,2}\s*[:：]\s*(.+)$/);
      if (kv) current.fields.push([kv[1].trim(), kv[2].trim()]);
      else current.extra.push(bullet[1]);
      continue;
    }
    if (current) { current = null; tail.push(line); continue; }
    (benefits.length ? tail : lead).push(line);
  }
  return { lead, benefits, tail };
}

function renderLines(lines, sources) {
  let html = "", list = false;
  for (const line of lines) {
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (bullet) { if (!list) { html += "<ul>"; list = true; } html += `<li>${inline(bullet[1], sources)}</li>`; continue; }
    if (list) { html += "</ul>"; list = false; }
    html += `<p>${inline(line.replace(/^#+\s*/, ""), sources)}</p>`;
  }
  return html + (list ? "</ul>" : "");
}

function renderBenefit(b, sources) {
  const tags = [], meta = [];
  for (const [key, value] of b.fields) {
    if (/대상/.test(key)) tags.push(`<span class="tag ok">${icon("check", "i sm")}${inline(value, sources)}</span>`);
    else if (/근거|법령/.test(key)) tags.push(`<span class="tag law">${inline(value, sources)}</span>`);
    else meta.push(`<span><b>${escapeHtml(key)}</b>${inline(value, sources)}</span>`);
  }
  for (const extra of b.extra) meta.push(`<span>${inline(extra, sources)}</span>`);
  // 같은 이름의 혜택 출처가 있으면 신청 링크로 쓴다.
  const match = sources.find((s) => s.type !== "regulation" && safeUrl(s.url) && (s.title.includes(b.title) || b.title.includes(s.title)));
  const action = match ? `<a class="btn" href="${match.url}" target="_blank" rel="noopener">자세히${icon("external", "i sm")}</a>` : "";
  return `<div class="benefit">
    <span class="b-icon">${icon(iconFor(b.title + b.org))}</span>
    <div>
      <div class="b-title"><b>${inline(b.title, sources)}</b>${b.org ? `<small>${escapeHtml(b.org)}</small>` : ""}</div>
      ${meta.length ? `<div class="b-meta">${meta.join("")}</div>` : ""}
      ${tags.length ? `<div class="tags">${tags.join("")}</div>` : ""}
    </div>
    ${action}
  </div>`;
}

function renderSourceList(sources) {
  return sources.map((s, i) => {
    const [label, kind] = SOURCE_KINDS[s.type] || ["출처", "org"];
    const href = safeUrl(s.url);
    const tag = href ? `a class="source" href="${href}" target="_blank" rel="noopener"` : `div class="source"`;
    return `<${tag}><span class="n">${i + 1}</span><span><b>${escapeHtml(s.title)}</b><small><span class="kind ${kind}">${label}</span>${escapeHtml(domain(s.url))}</small></span></${href ? "a" : "div"}>`;
  }).join("");
}

function processSummary(sources, stepCount) {
  const count = (t) => sources.filter((s) => s.type === t).length;
  const parts = [["법령", count("regulation")], ["혜택", count("benefit")], ["기관", count("institution")]]
    .filter(([, n]) => n).map(([name, n]) => `${name} <b>${n}건</b>`);
  return parts.length ? `${parts.join(", ")}을 근거로 답했어요` : `${stepCount}단계를 거쳐 답했어요`;
}

function appliedChips(profile = {}) {
  const chips = [];
  if (profile.service_type && SERVICE_TYPES[profile.service_type]) chips.push(`<span class="chip on">${SERVICE_TYPES[profile.service_type]}</span>`);
  if (profile.service_years) chips.push(`<span class="chip">${profile.service_years}년 복무</span>`);
  if (profile.discharge_date) chips.push(`<span class="chip">${escapeHtml(profile.discharge_date)} 전역</span>`);
  if (profile.region) chips.push(`<span class="chip">${escapeHtml(profile.region)}</span>`);
  return chips.length ? `이 조건으로 찾았어요 ${chips.join("")}` : "";
}

// ---------- 한 턴 ----------

function addTurn(question) {
  turnCount += 1;
  const id = `turn-${turnCount}`;
  const el = document.createElement("article");
  el.className = "turn";
  el.id = id;
  el.innerHTML = `
    <h1 class="question">${escapeHtml(question)}</h1>
    <div class="applied" hidden></div>
    <div class="process live">
      ${icon("shield")}<span class="ptext">질문을 살펴보고 있어요</span>
      <button class="more" type="button" hidden>과정 보기${icon("chevron", "i sm")}</button>
      <ol class="steps"></ol>
    </div>
    <div class="body"><div class="skeleton"><i></i><i></i><i></i></div></div>`;
  els.thread.append(el);
  el.scrollIntoView({ block: "start" });

  // 사이드바 '이번 대화'
  const link = document.createElement("a");
  link.textContent = question;
  link.addEventListener("click", () => { $(`#${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); closeMenu(); });
  els.history.querySelectorAll("a").forEach((a) => a.classList.remove("on"));
  link.classList.add("on");
  els.history.prepend(link);
  els.historyWrap.hidden = false;
  if (turnCount === 1) { els.crumb.textContent = question; els.crumb.hidden = false; }

  const process = $(".process", el), steps = $(".steps", el), body = $(".body", el), applied = $(".applied", el);
  const finishSteps = () => steps.querySelectorAll("li").forEach((li) => li.classList.add("done"));

  return {
    step(label) {
      steps.querySelector("li:not(.done)")?.classList.add("done");
      const li = document.createElement("li");
      li.textContent = label;
      steps.append(li);
      $(".ptext", process).textContent = label;
    },
    answer({ text, sources = [], profile }) {
      finishSteps();
      process.classList.remove("live");
      $(".ptext", process).innerHTML = processSummary(sources, steps.children.length);
      const more = $(".more", process);
      more.hidden = !steps.children.length;
      more.addEventListener("click", () => process.classList.toggle("open"));
      applied.innerHTML = appliedChips(profile);
      applied.hidden = !applied.innerHTML;

      const { lead, benefits, tail } = parseAnswer(text);
      body.innerHTML = `
        ${lead.length ? `<div class="prose">${renderLines(lead, sources)}</div>` : ""}
        ${benefits.length ? `<section><div class="list-head"><h2>받을 수 있는 혜택</h2><span>${benefits.length}</span></div>
          <div class="benefits">${benefits.map((b) => renderBenefit(b, sources)).join("")}</div></section>` : ""}
        ${tail.length ? `<div class="prose answer-note">${renderLines(tail, sources)}</div>` : ""}
        ${sources.length ? `<div class="inline-sources"><h3>근거 자료</h3><div class="sources">${renderSourceList(sources)}</div></div>` : ""}
        <div class="feedback">
          <button class="btn ghost" type="button" data-act="like">${icon("thumb", "i sm")}도움이 됐어요</button>
          <button class="btn ghost" type="button" data-act="copy">${icon("copy", "i sm")}복사</button>
        </div>`;
      bindFeedback(body, text);
      updateRail(sources);
      updateProfile(profile);
    },
    ask({ text, profile }) {
      process.hidden = true;
      body.innerHTML = `<div class="prose"><p>${inline(text, [])}</p></div>
        <div class="types" role="group" aria-label="복무 형태 고르기">
          ${["병사로 전역했어요", "부사관으로 전역했어요", "장교로 전역했어요", "보훈대상자예요"].map((t) => `<button class="chip" type="button">${t}</button>`).join("")}
        </div>`;
      body.querySelectorAll(".chip").forEach((chip) => chip.addEventListener("click", () => send(chip.textContent)));
      updateProfile(profile);
    },
    fail(message) {
      process.hidden = true;
      body.innerHTML = `<div class="answer-error">${icon("question")}<span>${escapeHtml(message)}</span></div>`;
    },
  };
}

function bindFeedback(root, text) {
  root.querySelector('[data-act="like"]').addEventListener("click", (e) => e.currentTarget.classList.toggle("on"));
  root.querySelector('[data-act="copy"]').addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    try { await navigator.clipboard.writeText(text); btn.lastChild.textContent = "복사했어요"; }
    catch { btn.lastChild.textContent = "복사하지 못했어요"; }
    setTimeout(() => { btn.lastChild.textContent = "복사"; }, 1600);
  });
}

function updateRail(sources) {
  els.railDate.textContent = sources.length ? today() : "";
  els.railSources.innerHTML = sources.length ? renderSourceList(sources) : `<p class="rail-empty">이번 답변에는 연결된 근거 자료가 없어요.</p>`;
}

function updateProfile(profile = {}) {
  for (const dd of document.querySelectorAll("#profile dd")) {
    let value = profile[dd.dataset.key];
    if (value === undefined || value === null || value === "") continue;
    if (dd.dataset.key === "service_type") value = SERVICE_TYPES[value] || value;
    if (dd.dataset.key === "service_years") value = `${value}년`;
    dd.textContent = value;
    dd.classList.remove("empty");
  }
}

// ---------- 서버 통신 ----------

async function* streamChat(message) {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId, user_id: userId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `서버가 응답하지 않아요 (${res.status}). 잠시 후 다시 시도해 주세요.`);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let idx;
    while ((idx = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      const event = chunk.match(/^event: (.*)$/m)?.[1];
      const data = chunk.match(/^data: (.*)$/m)?.[1];
      if (event) yield { event, data: data ? JSON.parse(data) : {} };
    }
  }
}

// ---------- 데모 ----------

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const DEMO = {
  profile: { service_type: "conscript", discharge_date: "2025-12", region: "서울" },
  sources: [
    { type: "regulation", title: "국민연금법 제18조(군 복무기간에 대한 노령연금 가입기간 추가 산입)", url: "https://www.law.go.kr/법령/국민연금법/제18조" },
    { type: "institution", title: "국민연금공단", url: "https://www.nps.or.kr" },
    { type: "institution", title: "고용24", url: "https://www.work24.go.kr" },
    { type: "institution", title: "온통청년", url: "https://www.youthcenter.go.kr" },
    { type: "institution", title: "병무청", url: "https://www.mma.go.kr" },
  ],
  text: [
    "의무복무를 마친 서울 거주자라면 지금 챙길 수 있는 혜택이 4가지 있어요. 연금처럼 나중에 반영되는 것도 있고 [1], 취업 지원처럼 지금 신청해야 하는 것도 있어요 [3].",
    "### 군복무 크레딧 | 국민연금공단",
    "- 대상: 병역 이행자",
    "- 내용: 군 복무기간 일부를 국민연금 가입기간으로 추가 인정 [1]",
    "- 신청: 노령연금 청구 시 반영, 자세한 내용은 국민연금공단 [2]",
    "- 근거: 국민연금법 제18조",
    "### 국민취업지원제도 | 고용노동부",
    "- 대상: 구직 중인 청년",
    "- 내용: 취업 상담, 직업훈련, 구직 활동 지원",
    "- 신청: 고용24에서 온라인 신청 [3]",
    "### 서울시 청년 정책 | 서울특별시",
    "- 대상: 서울 거주 청년",
    "- 내용: 주거, 자산형성, 마음건강 정책 모음",
    "- 신청: 온통청년에서 지역을 서울로 골라 확인 [4]",
    "### 예비군 편성 확인 | 병무청",
    "- 대상: 전역자",
    "- 내용: 전역 후 예비군 편성과 훈련 일정 확인 [5]",
    "※ 데모 화면이에요. 실제 답변은 법령과 공공서비스 조회 결과로 만들어져요. 정확한 자격과 기한은 소관 기관에 꼭 확인하세요.",
  ].join("\n"),
};

async function* demoChat(message) {
  yield { event: "step", data: { label: "복무 정보를 정리하고 있어요" } };
  await sleep(500);
  const known = !document.querySelector('#profile dd[data-key="service_type"].empty');
  if (!known && !/병장|병사|하사|중사|상사|소위|중위|대위|소령|간부|부사관|장교|복무|유공|보훈/.test(message)) {
    yield { event: "question", data: { text: "혜택이 복무 형태에 따라 많이 달라요. 어떻게 전역하셨나요? 사는 지역도 알려주시면 더 정확해요." } };
    return;
  }
  for (const label of ["관련 법령을 찾고 있어요", "받을 수 있는 혜택을 조회하고 있어요", "신청 기관을 찾고 있어요", "답변을 정리하고 있어요", "근거를 확인하고 있어요"]) {
    yield { event: "step", data: { label } };
    await sleep(550);
  }
  yield { event: "answer", data: DEMO };
}

// ---------- 보내기 ----------

function showChat() {
  els.home.hidden = true;
  els.chat.hidden = false;
  els.dock.hidden = false;
  $("#nav-home").classList.remove("on");
}

function withType(text) {
  if (!selectedType || text.includes(selectedType)) return text;
  return `${text} (복무 형태: ${selectedType})`;
}

async function send(raw) {
  const text = raw.trim();
  if (!text || busy) return;
  busy = true;
  els.chatSend.disabled = true;
  showChat();
  els.homeInput.value = ""; els.chatInput.value = ""; grow(els.chatInput);
  const turn = addTurn(text);

  try {
    for await (const { event, data } of (demo ? demoChat : streamChat)(withType(text))) {
      if (event === "thread") threadId = data.thread_id;
      else if (event === "step") turn.step(data.label);
      else if (event === "answer") turn.answer(data);
      else if (event === "question") turn.ask(data);
      else if (event === "error") turn.fail(data.message);
    }
  } catch (e) {
    turn.fail(e.message || "연결이 끊겼어요. 잠시 후 다시 시도해 주세요.");
  } finally {
    busy = false;
    els.chatSend.disabled = false;
    els.chatInput.focus();
  }
}

function resetChat() {
  threadId = null;
  turnCount = 0;
  els.thread.innerHTML = "";
  els.history.innerHTML = "";
  els.historyWrap.hidden = true;
  els.crumb.hidden = true;
  updateRail([]);
  els.railSources.innerHTML = `<p class="rail-empty">답변이 나오면 근거로 쓴 법령과 기관이 여기에 모여요.</p>`;
  els.home.hidden = false; els.chat.hidden = true; els.dock.hidden = true;
  $("#nav-home").classList.add("on");
  closeMenu();
  els.homeInput.focus();
}

// ---------- 입력, 메뉴, 테마 ----------

function grow(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
}

function bindComposer(form, textarea) {
  form.addEventListener("submit", (e) => { e.preventDefault(); send(textarea.value); });
  textarea.addEventListener("input", () => grow(textarea));
  textarea.addEventListener("keydown", (e) => {
    // 한글 조합 중 Enter는 무시해야 마지막 글자가 두 번 들어가지 않는다.
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(textarea.value); }
  });
}
bindComposer(els.homeForm, els.homeInput);
bindComposer(els.chatForm, els.chatInput);

document.querySelectorAll("#types .chip").forEach((chip) => chip.addEventListener("click", () => {
  const on = selectedType !== chip.dataset.type;
  selectedType = on ? chip.dataset.type : null;
  document.querySelectorAll("#types .chip").forEach((c) => {
    const active = c === chip && on;
    c.classList.toggle("on", active);
    c.setAttribute("aria-pressed", String(active));
  });
}));
document.querySelectorAll(".q-card").forEach((card) => card.addEventListener("click", () => send($("b", card).textContent)));
document.querySelectorAll("[data-ask]").forEach((link) => link.addEventListener("click", (e) => {
  e.preventDefault(); closeMenu(); send(link.dataset.ask);
}));
$("#new-chat").addEventListener("click", resetChat);
$("#nav-home").addEventListener("click", (e) => { e.preventDefault(); resetChat(); });

function openMenu() { els.sidebar.classList.add("open"); els.scrim.hidden = false; }
function closeMenu() { els.sidebar.classList.remove("open"); els.scrim.hidden = true; }
$("#menu").addEventListener("click", openMenu);
$("#close-menu").addEventListener("click", closeMenu);
els.scrim.addEventListener("click", closeMenu);

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  const dark = theme ? theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  els.theme.innerHTML = icon(dark ? "sun" : "moon", "i sm");
}
els.theme.addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  const next = dark ? "light" : "dark";
  store.set("jeonyeok.theme", next);
  applyTheme(next);
});
applyTheme(store.get("jeonyeok.theme"));

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
  els.mode.hidden = !demo;
  // 공유 링크: ?q=질문 으로 들어오면 바로 물어본다.
  const q = new URLSearchParams(location.search).get("q");
  if (q) send(q);
})();
