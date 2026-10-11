// AccountDomino 계정 보안 시뮬레이션(st.components.v2).
// 기본 = 결과 비교(정적 표), 과정 보기 = 변경 전/후 각각의 인증 과정 애니메이션(자동 연속 재생 없음).
// 데이터는 textContent/이스케이프로만 화면에 쓴다(평문 비밀번호 없음). 결과·단계·해시는 서버 기록 그대로 사용한다.
export default function (component) {
  "use strict";
  const { parentElement: root, data: D, setTriggerValue } = component;
  if (!D || !D.profiles) return undefined;
  if (root.__domino && root.__domino.run === D.run_id) return root.__domino.cleanup;
  if (root.__domino) root.__domino.cleanup();

  const NS = "http://www.w3.org/2000/svg";
  const $ = (s) => root.querySelector(s);
  const dlg = $(".dlg"), stage = $("#stage"), radial = $("#radial"), wires = $("#wires");
  const results = $("#results"), foot = $("#foot");
  const hub = $("#hub"), sideL = $("#side-left"), sideR = $("#side-right");
  const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // 시간축(ms, 1× 기준) = 설정 확인 3초 → 토큰 이동 2초 → 아이디 4초 → 비밀번호 5초 → MFA 5초 = 19초.
  // 계정 수와 무관한 공통 시간축이며, 모든 카드가 같은 구간을 동시에 지난다.
  const T = { settle: 3000, move: 2000, id: 4000, password: 5000, mfa: 5000 };
  const P_MOVE = T.settle;                 // 3000
  const P_ID = P_MOVE + T.move;            // 5000
  const P_PW = P_ID + T.id;                // 9000
  const P_MFA = P_PW + T.password;         // 14000
  const END = P_MFA + T.mfa;               // 19000
  const BOUNDS = [P_MOVE, P_ID, P_PW, P_MFA, END];
  const VERDICT_AT = 0.5;                  // 구간 전반 = 확인 중, 후반 = 판정을 읽는 시간
  const ROW_START = { id: P_ID, password: P_PW, mfa: P_MFA };
  const ROWS = ["id", "password", "mfa"];
  const ROW_LABEL = { id: "아이디", password: "비밀번호", mfa: "추가 인증" };

  const ICON = {
    mail: 'M4 6h16v12H4z M4 7l8 6 8-6', shop: 'M6 8h12l-1 11H7z M9 8a3 3 0 0 1 6 0',
    community: 'M5 5h14v10H9l-4 4z', school: 'M3 9l9-4 9 4-9 4z M7 11v4c0 1 10 1 10 0v-4',
    game: 'M7 9h10a3 3 0 0 1 0 8H7a3 3 0 0 1 0-8z M10 11v4 M8 13h4 M16 12h.5 M18 14h.5',
    cloud: 'M7 17a4 4 0 0 1 .5-8 5 5 0 0 1 9.5 1 3.5 3.5 0 0 1-.5 7z',
    sns: 'M8 10a2.5 2.5 0 1 0 0-.1z M16 6a2 2 0 1 0 0-.1z M16 18a2 2 0 1 0 0-.1z M10 11l4-3 M10 13l4 3',
    video: 'M4 6h16v12H4z M10 9l5 3-5 3z', music: 'M9 18V6l9-2v12 M9 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0 M18 16a2 2 0 1 1-4 0 2 2 0 0 1 4 0',
    news: 'M5 5h14v14H5z M8 9h8 M8 12h8 M8 15h5', delivery: 'M4 8l8-3 8 3-8 3z M4 8v8l8 3 8-3V8 M12 11v8',
    travel: 'M3 13l18-6-7 12-2-5z', ticket: 'M4 8h16v3a2 2 0 0 0 0 2v3H4v-3a2 2 0 0 0 0-2z M12 8v8',
    blog: 'M5 19l1-4L16 5l3 3L9 18z', job: 'M4 8h16v11H4z M9 8V6h6v2', lecture: 'M4 5h16v10H4z M9 19h6 M12 15v4',
    photo: 'M4 6h16v12H4z M8 11a1.5 1.5 0 1 0 0-.1z M6 17l4-4 3 3 3-3 2 2', map: 'M12 3a6 6 0 0 1 6 6c0 4-6 12-6 12S6 13 6 9a6 6 0 0 1 6-6z M12 9h.01',
    ebook: 'M6 4h11a1 1 0 0 1 1 1v15H7a1 1 0 0 1-1-1z M6 17h12', fitness: 'M12 20s-7-4.5-7-9a4 4 0 0 1 7-2 4 4 0 0 1 7 2c0 4.5-7 9-7 9z',
  };
  const GENERIC = 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18';
  const svgIcon = (sid, cls) => `<span class="${cls}"><svg viewBox="0 0 24 24">${
    (ICON[sid] || GENERIC).split(" M").map((d, i) => `<path d="${i ? "M" + d : d}"/>`).join("")}</svg></span>`;
  const CRED = '<svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
  const MFA = '<svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/></svg>';
  const OPEN = '<svg viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.3-2.3"/></svg>';
  const WARN = '<svg viewBox="0 0 24 24"><path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/></svg>';
  const SHIELD_OK = '<svg viewBox="0 0 24 24"><path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/></svg>';
  const DOT = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="5" class="fill"/></svg>';
  // 결과 유형별 아이콘·색: 성공=빨강 열린 자물쇠, 차단=초록 방패, 확인 필요=노랑 경고, 진행=파랑 점.
  const OUTCOME_ICON = { success: OPEN, blocked_password: SHIELD_OK, blocked_mfa: SHIELD_OK,
                         inconsistent: WARN, error: WARN, progress: DOT };

  const st = { mode: "before", view: "before", clock: 0, playing: false, last: null, raf: 0, alive: true,
               speed: 1, doneAt: null, confirm: false, wasPlaying: false,
               panelSid: null, panelProfile: null, lanePaths: {},
               autoT: 0 };

  const setText = (n, s) => { if (n && n.textContent !== s) n.textContent = s; };
  const esc = (s) => { const d = document.createElement("div"); d.textContent = String(s == null ? "" : s); return d.innerHTML; };
  const byId = (lanes) => { const m = {}; lanes.forEach((l) => (m[l.service_id] = l)); return m; };

  const L = D.leaked;
  root.querySelectorAll('[data-f="src-name"]').forEach((n) => (n.textContent = L.service));
  root.querySelectorAll('[data-f="src-user"]').forEach((n) => (n.textContent = L.username));
  root.querySelectorAll('[data-f="src-pw"]').forEach((n) => (n.textContent = L.password_label));

  // ---- DOM: 과정 보기 카드(좌우 균형 배치) --------------------------------------
  const cardOf = {};
  // 넓은 화면에서는 좌우를 2열씩(총 4열) 쌓고, 바깥 열을 반 칸 엇갈리게 둬서
  // 바깥 열로 가는 연결선이 안쪽 카드 사이 틈으로 지나가게 한다(카드를 가로지르지 않음).
  const WIDE_MIN = 1450;
  const wideMode = () => stage.clientWidth >= WIDE_MIN && D.order.length >= 4;

  function build() {
    sideL.replaceChildren(); sideR.replaceChildren();
    for (const k in cardOf) delete cardOf[k];
    const wide = wideMode();
    radial.classList.toggle("wide", wide);
    const mkCol = (cls) => { const d = document.createElement("div"); d.className = "col " + cls; return d; };
    const colsFor = (side, isLeft) => {
      const inner = mkCol("inner");
      if (!wide) { side.appendChild(inner); return { inner, outer: inner }; }
      const outer = mkCol("outer");
      if (isLeft) { side.appendChild(outer); side.appendChild(inner); }
      else { side.appendChild(inner); side.appendChild(outer); }
      return { inner, outer };
    };
    const L = colsFor(sideL, true), R = colsFor(sideR, false);
    const order = D.order;
    const half = Math.ceil(order.length / 2);
    order.forEach((sid, i) => {
      const isLeft = i < half, cols = isLeft ? L : R, k = isLeft ? i : i - half;
      const target = (k % 2 === 0) ? cols.inner : cols.outer;
      const c = document.createElement("button");
      c.type = "button"; c.className = "svccard"; c.dataset.sid = sid;
      c.innerHTML =
        `<div class="top">${svgIcon(sid, "ico")}<span class="nm"></span><span class="chg"></span></div>` +
        `<div class="setup"><span class="su-user" data-f="user"></span>` +
        `<span class="su-meta"><span data-f="grp"></span><span class="nw" data-f="mfa"></span></span></div>` +
        `<div class="checks">` +
        ROWS.map((r) => `<div class="crow" data-r="${r}"><span class="ck">${ROW_LABEL[r]}</span>` +
          `<span class="cv"></span></div>`).join("") +
        `</div>` +
        `<div class="final"><span class="fico"></span><span class="ftx"></span></div>`;
      c.addEventListener("click", (e) => { e.stopPropagation(); togglePanel(sid, st.view); });
      target.appendChild(c);
      const crow = {};
      ROWS.forEach((r) => (crow[r] = c.querySelector(`.crow[data-r="${r}"]`)));
      cardOf[sid] = { el: c, nm: c.querySelector(".nm"), chg: c.querySelector(".chg"),
                      user: c.querySelector('[data-f="user"]'), grp: c.querySelector('[data-f="grp"]'),
                      mfa: c.querySelector('[data-f="mfa"]'),
                      crow, fico: c.querySelector(".fico"), ftx: c.querySelector(".ftx"),
                      final: c.querySelector(".final") };
    });
    setStagger();
  }
  // 2열에서는 카드 높이를 가장 큰 카드에 맞춰 통일한다(긴 아이디로 높이가 달라지면
  // 엇갈림 간격이 어긋나 연결선이 카드를 가로지르기 때문). 그 뒤 반 칸 내릴 간격을 정한다.
  function setStagger() {
    const cards = [...radial.querySelectorAll(".svccard")];
    if (!cards.length) return;
    radial.style.removeProperty("--cardh");
    const h = Math.max(...cards.map((c) => c.getBoundingClientRect().height));
    if (!h) return;
    radial.style.setProperty("--cardh", h + "px");
    radial.style.setProperty("--stagger", ((h + 16) / 2) + "px");
  }

  // ---- 배선: 허브 가장자리 → 각 카드 안쪽 가장자리(중앙 여백으로만) ------------------------
  function route() {
    wires.replaceChildren(); tokenLayer = null;
    if (getComputedStyle(wires).display === "none") { st.lanePaths = {}; return; }  // 세로 스택
    const o = wires.getBoundingClientRect();
    const localRect = (el) => {
      const a = el.getBoundingClientRect();
      return { l: a.left - o.left, r: a.right - o.left, t: a.top - o.top, b: a.bottom - o.top,
               cx: (a.left + a.right) / 2 - o.left, cy: (a.top + a.bottom) / 2 - o.top };
    };
    wires.setAttribute("viewBox", `0 0 ${o.width} ${o.height}`);
    wires.setAttribute("preserveAspectRatio", "none");
    const h = localRect(hub);
    const paths = {};
    const cards = [...radial.querySelectorAll(".svccard")].map((c) => ({ c, r: localRect(c) }));
    const sides = { left: [], right: [] };
    for (const it of cards) (it.r.cx < h.cx ? sides.left : sides.right).push(it);
    const span = (h.b - h.t) * 0.72, top = h.cy - span / 2;
    for (const side of ["left", "right"]) {
      const list = sides[side].sort((a, b) => a.r.cy - b.r.cy);
      if (!list.length) continue;
      const cardEdge = side === "left" ? Math.max(...list.map((it) => it.r.r))
                                        : Math.min(...list.map((it) => it.r.l));
      const hubEdge = side === "left" ? h.l : h.r;
      const busX = cardEdge + (hubEdge - cardEdge) * 0.5;   // 여백 가운데 공통 버스
      list.forEach((it, i) => {
        const ay = list.length > 1 ? top + (span * i) / (list.length - 1) : h.cy;
        const cy = it.r.cy, inner = side === "left" ? it.r.r : it.r.l;
        const pts = [[hubEdge, ay], [busX, ay], [busX, cy], [inner, cy]];
        const el = addWire("M " + pts.map((p) => `${p[0]} ${p[1]}`).join(" L "));
        paths[it.c.dataset.sid] = { pts, el };
      });
    }
    st.lanePaths = paths;
  }
  function addWire(d) { const p = document.createElementNS(NS, "path"); p.setAttribute("d", d); p.setAttribute("class", "wire"); wires.appendChild(p); return p; }

  // ---- 과정 보기: 카드 상태(서버가 실제 수행한 단계만 표시) ------------------------
  const warnOut = (lane) => lane.outcome === "error" || lane.outcome === "inconsistent";
  const stepOf = (lane, k) => (lane.steps || {})[k] || "skipped";

  // 결과가 정해지는 구간(그 구간의 판정이 나올 때 최종 결과 한 줄을 공개한다).
  function decideRow(lane) {
    if (warnOut(lane)) return "id";                      // 판정 못 함: 더 진행한 것처럼 보이지 않게 한다
    if (stepOf(lane, "id") === "nomatch") return "id";
    if (stepOf(lane, "password") === "nomatch") return "password";
    return "mfa";
  }
  // 각 검사 행의 최종 문구(서버 기록 그대로. 프런트가 추정하지 않는다)
  function verdictText(lane, k) {
    if (warnOut(lane)) return "확인 필요";
    const s = stepOf(lane, k);
    if (s === "skipped") return "진행하지 않음";
    if (k === "mfa") return s === "off" ? "사용 안 함" : "미완료";
    return s === "match" ? "일치" : "불일치";      // 행 라벨이 있으므로 항목명을 반복하지 않는다
  }
  // 판정 색: 막아 낸 행은 초록, 침해로 이어진 행은 빨강, 확인 필요는 노랑, 나머지 기록은 기본색.
  function verdictCls(lane) {
    return warnOut(lane) ? "v-warn" : "v-plain";   // 기록은 기본색, 강조는 진행 행·최종 결과에만
  }
  function rowView(lane, k, t) {
    const start = ROW_START[k], span = T[k], checked = stepOf(lane, k) !== "skipped" && !warnOut(lane);
    if (t < start) return { text: "대기", cls: "v-wait" };
    if (t < start + span * VERDICT_AT) {
      return checked ? { text: "확인 중", cls: "v-now", now: true } : { text: "대기", cls: "v-wait" };
    }
    return { text: verdictText(lane, k), cls: verdictCls(lane), now: false };
  }
  const decidedAt = (lane) => ROW_START[decideRow(lane)] + T[decideRow(lane)] * VERDICT_AT;

  function applyLane(sid, lane, t) {
    const c = cardOf[sid]; if (!c) return;
    setText(c.nm, lane.service);
    setText(c.user, lane.username);
    setText(c.grp, `그룹 ${lane.password_group} · `);
    setText(c.mfa, `MFA ${lane.mfa_enabled ? "켜짐" : "꺼짐"}`);
    ROWS.forEach((k) => {
      const v = rowView(lane, k, t), row = c.crow[k];
      const cls = "crow" + (v.now ? " now" : "");
      if (row.className !== cls) row.className = cls;
      const cell = row.lastElementChild;
      setText(cell, v.text);
      if (cell.className !== "cv " + v.cls) cell.className = "cv " + v.cls;
    });
    // 최종 결과 줄은 비어 있어도 자리를 지켜 카드 높이가 변하지 않게 한다(연결선 흔들림 방지).
    const shown = t >= decidedAt(lane);
    const ico = shown ? (OUTCOME_ICON[lane.outcome] || WARN) : "";
    if (c.fico.innerHTML !== ico) c.fico.innerHTML = ico;
    setText(c.ftx, shown ? lane.short : "");   // 사유는 바로 위 검사 행과 상세창에 있다
    const cls = "svccard" + (shown ? " s-" + lane.outcome : (t >= P_ID ? " s-progress" : ""));
    if (c.el.className !== cls) c.el.className = cls;
    c.chg.textContent = (st.view === "after" && lane.changes && lane.changes.length)
      ? lane.changes.map((x) => x.text).join(" · ") : "";
  }

  // ---- 타임라인(공통, 모든 카드 동시 진행) -----------------------------------------
  function phaseOf(t) {
    if (t < P_MOVE) return { stage: "settle" };
    if (t < P_ID) return { stage: "move", moving: true, p: (t - P_MOVE) / T.move };
    if (t < P_PW) return { stage: "id", p: (t - P_ID) / T.id };
    if (t < P_MFA) return { stage: "password", p: (t - P_PW) / T.password };
    if (t < END) return { stage: "mfa", p: (t - P_MFA) / T.mfa };
    return { stage: "done" };
  }
  function tokenPos(sid, t) {
    const p = st.lanePaths[sid]; if (!p) return null;
    if (t < P_MOVE) return null;
    const local = t - P_MOVE; if (local >= T.move) return null;       // 도착 후에는 카드가 표현
    const pts = p.pts, seg = [];
    let total = 0;
    for (let k = 1; k < pts.length; k++) { const l = Math.hypot(pts[k][0] - pts[k - 1][0], pts[k][1] - pts[k - 1][1]); seg.push(l); total += l; }
    let d = (local / T.move) * total;
    for (let k = 1; k < pts.length; k++) {
      if (d <= seg[k - 1] || k === pts.length - 1) {
        const r = seg[k - 1] ? d / seg[k - 1] : 1;
        return [pts[k - 1][0] + (pts[k][0] - pts[k - 1][0]) * r, pts[k - 1][1] + (pts[k][1] - pts[k - 1][1]) * r];
      }
      d -= seg[k - 1];
    }
    return pts[pts.length - 1];
  }

  let tokenLayer = null;
  // 카드 내용이 바뀌어 배선 SVG 의 렌더 박스가 viewBox 와 달라지면 좌표가 늘어나므로 다시 배선한다.
  function syncRoute() {
    const o = wires.getBoundingClientRect();
    if (!o.width || !o.height) return;
    if (wires.getAttribute("viewBox") !== `0 0 ${o.width} ${o.height}`) route();
  }
  function draw() {
    syncRoute();
    const t = st.clock, P = D.profiles[st.view], lanes = P.lanes;
    let success = 0, blocked = 0, errors = 0, done = 0;
    if (!reduced) { if (!tokenLayer && wires.getAttribute("width")) { tokenLayer = document.createElementNS(NS, "g"); wires.appendChild(tokenLayer); } }
    const active = new Set(), ph = phaseOf(t);
    lanes.forEach((lane) => {
      applyLane(lane.service_id, lane, t);
      if (t >= decidedAt(lane)) {          // 판정이 공개된 카드는 그 기록을 끝까지 유지한다
        done += 1;
        if (lane.outcome === "success") success += 1;
        else if (lane.outcome === "error" || lane.outcome === "inconsistent") errors += 1;
        else blocked += 1;
      }
      if (ph.moving && tokenLayer) {
        const pos = tokenPos(lane.service_id, t);
        if (pos) {
          let tok = tokenLayer.querySelector(`[data-sid="${lane.service_id}"]`);
          if (!tok) { tok = document.createElementNS(NS, "circle"); tok.setAttribute("r", 7); tok.setAttribute("class", "tok"); tok.dataset.sid = lane.service_id; tokenLayer.appendChild(tok); }
          tok.setAttribute("cx", pos[0]); tok.setAttribute("cy", pos[1]); active.add(lane.service_id);
        }
      }
    });
    if (tokenLayer) tokenLayer.querySelectorAll("circle").forEach((c) => { if (!active.has(c.dataset.sid)) c.remove(); });
    hub.classList.toggle("lit", t < P_MOVE && !reduced);
    setText($("#c-success"), String(success));
    setText($("#c-blocked"), String(blocked));
    $("#c-error-wrap").hidden = errors === 0;
    setText($("#c-error"), String(errors));
    highlightSelection();
    if (t >= END && st.doneAt === null) {       // 공통 시간축이 끝나야 재생 완료
      st.doneAt = st.clock;
    }
    setStateText();
  }

  const processDone = () => st.mode !== "compare" && st.doneAt !== null;
  // 전후 API 결과는 실행 때 이미 모였으므로 결과 비교는 재생 여부와 무관하게 언제나 열 수 있다.
  const PHASE_LABEL = { settle: "설정 확인", move: "유출 정보로 로그인 시도",
                        id: "아이디 확인", password: "비밀번호 검증", mfa: "추가 인증 확인", done: "결과 확인" };
  function phaseLabel() {
    if (processDone()) return "결과 확인";
    return PHASE_LABEL[phaseOf(st.clock).stage] || "결과 확인";
  }
  function setStateText() {
    if (st.mode === "compare") {
      setText($("#view-label"), "결과 비교");
      setText($("#phase"), "두 설정의 최종 결과");
      setText($("#view-state"), "같은 유출 정보 기준");
      setText($("#change-note"), "");
      $("#toggle").disabled = true; $("#step").disabled = true; $("#replay").disabled = true;
      dlg.dataset.state = "compare"; dlg.dataset.view = "compare";
      return;
    }
    $("#toggle").disabled = false; $("#replay").disabled = false;
    let s;
    if (st.confirm) s = "일시정지";
    else if (processDone()) s = "재생 완료";
    else s = st.playing ? "재생 중" : "일시정지";
    setText($("#view-state"), s);
    setText($("#view-label"), D.profiles[st.view].label + " 설정 · 인증 과정");
    setText($("#phase"), phaseLabel());
    const tg = $("#toggle"), label = st.playing ? "일시정지" : (processDone() ? "처음부터 재생" : "재생");
    if (tg.getAttribute("aria-label") !== label) { tg.setAttribute("aria-label", label); tg.title = label; }
    tg.dataset.playing = String(st.playing);
    $("#step").disabled = st.playing || processDone();
    dlg.dataset.state = st.confirm ? "confirm" : processDone() ? "done" : (st.playing ? "playing" : "paused");
    dlg.dataset.view = st.view;
    setText($("#compare"), processDone() ? D.profiles[st.view].sentence : "");
    setText($("#change-note"), "");
  }

  // ---- 결과 비교(기본, 정적 표) --------------------------------------------------
  function statusChip(lane, profile, sid) {
    if (!lane) return `<span class="rs rs-inconsistent"><span class="sico">${WARN}</span>`
      + `<span class="stxt"><b>확인 필요</b><i>결과 없음</i></span></span>`;
    const tags = (profile === "after" && lane.changes && lane.changes.length)
      ? `<span class="chgtags">${lane.changes.map((c) => `<span class="tag" title="${esc(c.detail || c.text)}">${esc(c.text)}</span>`).join("")}</span>`
      : "";
    return `<button type="button" class="rs s-${esc(lane.outcome)}" data-sid="${esc(sid)}" data-profile="${esc(profile)}" `
      + `title="상세 보기">`
      + `<span class="sico">${OUTCOME_ICON[lane.outcome] || WARN}</span>`
      + `<span class="stxt"><b>${esc(lane.short)}</b><i>${esc(lane.reason)}</i></span></button>${tags}`;
  }
  function sumLine(profile) {
    const s = D.profiles[profile].summary, L2 = D.profiles[profile].label;
    const check = s.errors + s.inconsistent;
    return `${esc(L2)} — 계정 침해 ${s.success} · 로그인 시도 차단 ${s.blocked}`
      + (check ? ` · 확인 필요 ${check}` : "");
  }
  function renderResults() {
    const bl = byId(D.profiles.before.lanes), al = byId(D.profiles.after.lanes);
    setText($("#rs-note"), "두 설정 모두 변경 전 출처 계정의 같은 유출 정보(아이디·비밀번호)로 시도했습니다. 같은 서비스는 같은 행입니다.");
    const head = `<thead><tr><th class="rs-svc">서비스</th><th>변경 전 최종 결과</th><th>변경 후 최종 결과</th></tr>`
      + `<tr class="rs-goto"><th></th>`
      + `<td><button type="button" class="linkbtn" data-goto="before">변경 전 과정 보기 →</button></td>`
      + `<td><button type="button" class="linkbtn" data-goto="after">변경 후 과정 보기 →</button></td></tr></thead>`;
    const body = D.order.map((sid) => {
      const b = bl[sid], a = al[sid], name = (b || a) ? (b || a).service : sid;
      return `<tr><th class="rs-svc">${svgIcon(sid, "ico")}<span>${esc(name)}</span></th>`
        + `<td>${statusChip(b, "before", sid)}</td>`
        + `<td>${statusChip(a, "after", sid)}</td></tr>`;
    }).join("");
    $("#rs-table").innerHTML = head + `<tbody>${body}</tbody>`;
    const anyCheck = ["before", "after"].some((p) => D.profiles[p].summary.errors + D.profiles[p].summary.inconsistent > 0);
    $("#rs-sum").innerHTML = `<span class="rs-counts">${esc(sumLine("before"))}</span>`
      + `<span class="rs-counts">${esc(sumLine("after"))}</span>`
      + `<span class="rs-cmp">${esc(D.compare_sentence)}</span>`
      + (anyCheck ? `<span class="rs-cmp warn">일부 서비스는 ‘확인 필요’ 상태입니다. 해당 결과는 성공·차단으로 세지 않았습니다.</span>` : "");
    $("#rs-table").querySelectorAll(".rs[data-sid]").forEach((btn) =>
      btn.addEventListener("click", (e) => { e.stopPropagation(); togglePanel(btn.dataset.sid, btn.dataset.profile); }));
    $("#rs-table").querySelectorAll("[data-goto]").forEach((btn) =>
      btn.addEventListener("click", () => start(btn.dataset.goto)));
  }

  function showMode() {
    const compare = st.mode === "compare";
    stage.hidden = compare; foot.hidden = compare; results.hidden = !compare;
    root.querySelectorAll(".seg.speed button").forEach((b) => (b.disabled = compare));
  }
  function render(profile) {
    st.view = profile; st.clock = 0; st.doneAt = null; st.last = null;
    if (tokenLayer) tokenLayer.replaceChildren();
    setText($("#compare"), "");
    draw(); setStagger(); route(); draw();   // 내용을 그린 뒤 높이를 맞추고 배선해야 정렬이 맞는다
  }
  function start(mode) {
    clearPanel();
    st.mode = mode;
    root.querySelectorAll(".seg [data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === mode)));
    showMode();
    if (mode === "compare") { st.playing = false; renderResults(); setStateText(); return; }
    st.playing = true;
    render(mode);
  }

  function tick(ts) {
    if (!st.alive) return;
    if (st.mode !== "compare" && st.playing) {
      if (st.last !== null) st.clock += (ts - st.last) * st.speed;   // 일시정지 시간 제외, 배속은 화면 시간에만
      st.last = ts;
      draw();
      if (st.doneAt !== null) { st.playing = false; setStateText(); }
    } else st.last = null;
    st.raf = requestAnimationFrame(tick);
  }
  function nextStep() {
    if (st.mode === "compare" || st.playing || processDone()) return;
    const next = BOUNDS.find((b) => b > st.clock + 1);
    st.clock = next === undefined ? END : next;
    st.last = null; draw();
  }

  // ---- 오른쪽 고정 상세 패널(실행 스냅샷·서버 기록만 사용) ------------------------
  const panel = $("#panel");
  let panelWasPlaying = false;

  // 비밀번호 검증 상태: 검증 대기 / 일치 / 불일치 / 미검사 / 오류 / 검증 기록 없음
  function verifyInfo(lane, reached) {
    const h = lane.hash || {}, k = (lane.steps || {}).password;
    if (lane.outcome === "error") return { s: "오류", c: "v-warn", n: "요청이 실패해 검증 기록을 받지 못했습니다." };
    if (!h.full) return { s: "검증 기록 없음", c: "v-wait", n: "이 실행에서 저장된 해시 기록이 없습니다." };
    if (!reached) return { s: "검증 대기", c: "v-wait", n: "재생이 비밀번호 검증 단계에 닿으면 결과를 표시합니다." };
    if (k === "skipped") return { s: "미검사", c: "v-plain", n: "아이디가 달라 비밀번호 검증을 수행하지 않았습니다." };
    if (k === "match") return { s: "일치", c: "v-plain", n: "저장된 해시와 비교해 일치했습니다." };
    if (k === "nomatch") return { s: "불일치", c: "v-block", n: "저장된 해시와 비교한 결과 유출 비밀번호와 다릅니다." };
    return { s: "확인 필요", c: "v-warn", n: "서버가 판정하지 못했습니다." };
  }

  function hashBlock(lane, reached) {
    const h = lane.hash || {}, v = verifyInfo(lane, reached);
    let out = `<h4 class="pn-h">비밀번호 검증</h4>`
      + `<p class="pn-state ${v.c}"><b>${esc(v.s)}</b></p><p class="pn-note">${esc(v.n)}</p>`;
    if (!h.full) return out;
    const a = h.algo || {};
    out += `<dl class="pn-dl">`
      + `<dt>알고리즘</dt><dd>${esc(a.name || "기록 없음")}`
      + (a.iterations ? ` · ${esc(String(a.iterations))}회 반복` : "") + `</dd>`
      + `<dt>저장 해시</dt><dd><span class="mono">${esc(h.short)}…</span></dd></dl>`
      + `<details class="pn-det"><summary>전체 해시 보기</summary>`
      + `<p class="mono hashfull">${esc(h.full)}</p></details>`
      + `<details class="pn-det"><summary>salt 보기</summary>`
      + `<p class="mono hashfull">${esc(h.salt)}</p>`
      + `<p class="pn-note">salt 는 계정마다 다르게 생성되어 해시와 함께 저장됩니다. 같은 비밀번호라도 저장 해시가 달라지므로, `
      + `다른 서비스의 해시와 비교해 비밀번호가 같은지 판단하지 않습니다.</p></details>`;
    return out;
  }

  function renderPanel() {
    const sid = st.panelSid, profile = st.panelProfile;
    if (!sid) return;
    const P = D.profiles[profile], lanes = P.lanes, idx = lanes.findIndex((l) => l.service_id === sid);
    if (idx < 0) return;
    const lane = lanes[idx], cmp = lane.compare || { rows: [], explain: "", mfa_step: "" };
    const all = st.mode === "compare";
    const done = all || st.clock >= decidedAt(lane);
    const pwReached = all || st.clock >= ROW_START.password + T.password * VERDICT_AT;

    const rows = cmp.rows.map((r, i) => {
      const cause = done && r.cause;
      const extra = done && i === 2 ? ` <span class="mfa-step">· ${esc(cmp.mfa_step)}</span>` : "";
      return `<tr class="${cause ? "cause" : ""}"><th>${esc(r.k)}</th>`
        + `<td>${esc(r.attempt)}</td><td>${esc(r.target)}${extra}</td></tr>`;
    }).join("");

    const reason = done
      ? `<p class="pn-result s-${esc(lane.outcome)}"><b>${esc(lane.short)}</b> · ${esc(lane.reason)}</p>`
        + `<p class="pn-note">${esc(cmp.explain)}</p>`
        + (lane.error ? `<p class="pn-note">오류: ${esc(lane.error)}</p>` : "")
      : `<p class="pn-note">아직 판정 전입니다. 재생이 해당 단계에 닿으면 표시합니다.</p>`;

    panel.innerHTML =
      `<div class="pn-head"><div><h3>${esc(lane.service)}</h3>`
      + `<p class="pn-sub">${esc(P.label)} 설정</p></div>`
      + `<button type="button" class="pn-x" id="panel-x" aria-label="상세 닫기" title="상세 닫기">`
      + `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19"/></svg></button></div>`
      + `<h4 class="pn-h">유출 정보와 대상 설정</h4>`
      + `<table class="cmp"><thead><tr><th></th><th>시도한 유출 정보</th><th>대상 계정 설정</th></tr></thead>`
      + `<tbody>${rows}</tbody></table>`
      + hashBlock(lane, pwReached)
      + `<h4 class="pn-h">최종 사유</h4>${reason}`;
    const x = $("#panel-x"); if (x) x.addEventListener("click", () => closePanel(true));
  }

  // 선택한 카드와 그 연결선만 강조한다.
  function highlightSelection() {
    const sid = st.panelSid;
    for (const k in cardOf) cardOf[k].el.classList.toggle("sel", k === sid);
    for (const k in st.lanePaths) {
      const p = st.lanePaths[k];
      if (p && p.el) p.el.classList.toggle("sel", k === sid);
    }
  }

  // 패널이 열리고 닫히면 무대 폭이 달라지므로 카드·배선을 다시 잡는다.
  function relayout() {
    if (st.mode === "compare") return;
    build(); draw(); setStagger(); route(); draw();
  }

  function togglePanel(sid, profile) {
    if (st.panelSid === sid && st.panelProfile === profile) { closePanel(true); return; }
    openPanel(sid, profile);
  }
  function openPanel(sid, profile) {
    if (!D.profiles[profile] || !D.profiles[profile].lanes.some((l) => l.service_id === sid)) return;
    if (st.panelSid === null) { panelWasPlaying = st.playing; st.playing = false; }  // 첫 열기 때만 저장
    const first = panel.hidden;
    st.panelSid = sid; st.panelProfile = profile;
    panel.hidden = false;
    if (first) relayout();              // 카드 전환일 때는 내용만 바꾼다
    renderPanel(); highlightSelection();
    const c = cardOf[sid];
    if (c) c.el.scrollIntoView({ block: "nearest", inline: "nearest" });
    const x = $("#panel-x"); if (x) x.focus();
    setStateText();
  }
  function closePanel(restore) {         // X·Esc·무대 클릭: 재생 상태 복원 + 카드로 포커스
    if (st.panelSid === null) return;
    const sid = st.panelSid;
    st.panelSid = null; st.panelProfile = null;
    panel.hidden = true; panel.replaceChildren();
    relayout(); highlightSelection();
    if (restore && st.mode !== "compare") { st.playing = panelWasPlaying; st.last = null; }
    setStateText();
    const c = restore ? cardOf[sid] : null;
    if (c) c.el.focus();
  }
  function clearPanel() {                // 프로필 전환·다시 재생·정리: 재생 상태는 복원하지 않음
    st.panelSid = null; st.panelProfile = null;
    panel.hidden = true; panel.replaceChildren();
  }

  // ---- 종료 확인 + 포커스 트랩 ---------------------------------------------------
  const confirmBox = $("#confirm");
  const focusScope = () => !confirmBox.hidden ? confirmBox : (!panel.hidden ? panel : dlg);
  const focusable = () => [...focusScope().querySelectorAll("button, summary")].filter((b) => !b.disabled && b.offsetParent !== null);
  function openConfirm() { if (st.confirm) return; st.confirm = true; st.wasPlaying = st.playing; st.playing = false; setStateText(); confirmBox.hidden = false; $("#keep").focus(); }
  function keepWatching() { if (!st.confirm) return; st.confirm = false; confirmBox.hidden = true; if (st.mode !== "compare") { st.playing = st.wasPlaying; st.last = null; } setStateText(); $("#close").focus(); }
  function quit() { cleanup(); setTriggerValue("exit", true); }
  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); if (st.confirm) keepWatching(); else if (!panel.hidden) closePanel(true); else openConfirm(); return; }
    if (e.key === "Tab") { const f = focusable(); if (!f.length) return; const cur = root.activeElement || document.activeElement; let i = f.indexOf(cur); e.preventDefault(); i = e.shiftKey ? (i <= 0 ? f.length - 1 : i - 1) : (i >= f.length - 1 ? 0 : i + 1); f[i].focus(); }
  }
  function cleanup() { if (!st.alive) return; st.alive = false; st.playing = false; clearPanel(); clearTimeout(st.autoT); cancelAnimationFrame(st.raf); document.removeEventListener("keydown", onKey, true); window.removeEventListener("resize", onResize); }
  let rz = null;
  function onResize() { clearTimeout(rz); rz = setTimeout(() => { if (!st.alive) return; if (st.mode === "compare") return;
    // 카드를 다시 그린 뒤(최종 높이 확정) 배선해야 정지 상태에서도 연결선이 맞는다.
    build(); draw(); setStagger(); route(); draw(); }, 150); }

  function setSpeed(v) { st.speed = v; root.querySelectorAll(".seg.speed button").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.speed) === v))); }

  // ---- 이벤트 ----------------------------------------------------------------
  root.querySelectorAll(".seg [data-mode]").forEach((b) => b.addEventListener("click", () => start(b.dataset.mode)));
  root.querySelectorAll(".seg.speed button").forEach((b) => b.addEventListener("click", () => setSpeed(Number(b.dataset.speed))));
  $("#toggle").addEventListener("click", () => { if (st.mode === "compare") return; if (st.playing) { st.playing = false; setStateText(); return; } if (processDone()) { start(st.view); return; } st.playing = true; setStateText(); });
  $("#step").addEventListener("click", nextStep);
  $("#replay").addEventListener("click", () => { if (st.mode !== "compare") start(st.view); });
  $("#close").addEventListener("click", openConfirm);
  $("#keep").addEventListener("click", keepWatching);
  $("#quit").addEventListener("click", quit);
  stage.addEventListener("click", () => closePanel(true));
  results.addEventListener("click", () => closePanel(true));
  document.addEventListener("keydown", onKey, true);
  window.addEventListener("resize", onResize);

  root.__domino = { run: D.run_id, cleanup };
  build(); setSpeed(1); start("before"); dlg.focus();
  requestAnimationFrame(() => { if (st.alive && st.mode !== "compare") { setStagger(); route(); draw(); } });
  st.raf = requestAnimationFrame(tick);
  return cleanup;
}
