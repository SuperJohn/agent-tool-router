const state = {
  board: null,
  traces: null,
  id: "cal-04",
  arm: "with_router",
  filter: "all",
  live: false,
  liveNote: "",
  liveDiff: false,
};

const METRICS = [
  ["first_try_valid", "First-try valid", false],
  ["valid_after_retry", "Valid after retry", false],
  ["mean_retries", "Mean retries", true],
  ["unrecoverable", "Unrecoverable", false],
  ["task_correct", "Task correct", false],
];

function readHash() {
  const raw = location.hash.replace(/^#/, "");
  if (!raw) return;
  const [id, arm] = raw.split("/");
  if (id) state.id = id;
  state.arm = arm === "without" ? "without_router" : "with_router";
}

function writeHash() {
  const arm = state.arm === "without_router" ? "without" : "with";
  const next = `#${state.id}/${arm}`;
  if (location.hash !== next) history.replaceState(null, "", next);
}

async function load() {
  readHash();
  try {
    const [boardRes, traceRes] = await Promise.all([
      fetch("data/scoreboard.json"),
      fetch("data/traces.json"),
    ]);
    if (!boardRes.ok || !traceRes.ok) throw new Error("missing replay JSON");
    state.board = await boardRes.json();
    state.traces = await traceRes.json();
    if (!state.traces.tasks.some((task) => task.id === state.id)) {
      state.id = "cal-04";
    }
    render();
    detectLive();
  } catch (error) {
    document.getElementById("run-meta").textContent =
      "Could not read site/data. Serve this folder over HTTP (make run) so the page can fetch the recorded JSON.";
    document.getElementById("stage").textContent = String(error);
  }
}

async function detectLive() {
  if (new URLSearchParams(location.search).has("static")) {
    state.live = false;
    return;
  }
  try {
    const response = await fetch("/api/health");
    state.live = response.ok;
  } catch {
    state.live = false;
  }
  renderStage();
}

function render() {
  renderMeta();
  renderScoreboard();
  renderList();
  renderStage();
  writeHash();
}

function renderMeta() {
  const board = state.board;
  document.getElementById("run-meta").textContent =
    `Recorded ${board.recorded_at} · provider ${board.provider_label} · seed ${board.seed} · ${board.task_count} tasks · max retries ${board.max_retries} · dataset ${board.dataset}`;
}

function renderScoreboard() {
  const board = state.board;
  const root = document.getElementById("scoreboard");
  root.replaceChildren();

  const legend = document.createElement("div");
  legend.className = "legend";
  legend.innerHTML =
    '<span><i class="swatch fill"></i>with router</span><span><i class="swatch tick"></i>without router</span>';
  root.append(legend);

  const head = document.createElement("div");
  head.className = "score-head";
  for (const text of ["", "With router", "Without", ""]) {
    const span = document.createElement("div");
    span.textContent = text;
    head.append(span);
  }
  root.append(head);

  for (const [key, label, isMean] of METRICS) {
    const row = document.createElement("div");
    row.className = "metric" + (key === "task_correct" ? " secondary" : "");
    row.dataset.metric = key;

    const name = document.createElement("div");
    name.className = "name";
    const strong = document.createElement("strong");
    strong.textContent = label;
    const hint = document.createElement("span");
    hint.textContent = board.definitions[key];
    name.append(strong, hint);

    const withFig = figure(board.with_router, key, isMean, false);
    const baseFig = figure(board.without_router, key, isMean, true);
    const track = document.createElement("div");
    track.className = "track";
    const scale = isMean ? board.max_retries || 1 : 100;
    const fillValue = isMean ? board.with_router.mean_retries : board.with_router[key + "_pct"];
    const tickValue = isMean ? board.without_router.mean_retries : board.without_router[key + "_pct"];
    track.style.setProperty("--fill", `${Math.max(0, Math.min(100, (fillValue / scale) * 100))}%`);
    track.style.setProperty("--tick", `${Math.max(0, Math.min(100, (tickValue / scale) * 100))}%`);
    const fill = document.createElement("span");
    fill.className = "fill";
    const tick = document.createElement("span");
    tick.className = "tick";
    track.append(fill, tick);

    row.append(name, withFig, baseFig, track);
    root.append(row);
  }
}

function figure(metrics, key, isMean, base) {
  const wrap = document.createElement("div");
  wrap.className = "figure" + (base ? " base" : "");
  const big = document.createElement("div");
  big.className = "big";
  const frac = document.createElement("div");
  frac.className = "frac";
  if (isMean) {
    big.textContent = metrics.mean_retries_display;
    frac.textContent = `${metrics.retry_total} retries`;
  } else {
    const display = metrics[key + "_display"];
    big.textContent = display.split(" ")[0];
    frac.textContent = display.split(" ")[1] || "";
  }
  wrap.append(big, frac);
  return wrap;
}

function visibleTasks() {
  return state.traces.tasks.filter((task) => {
    if (["calendar", "tracker", "lookup"].includes(state.filter)) return task.suite === state.filter;
    const outcome = task.with_router;
    if (state.filter === "recovered") return outcome.validated && outcome.retries > 0;
    if (state.filter === "unrecoverable") return !outcome.validated;
    if (state.filter === "wrong") return outcome.validated && !outcome.task_correct;
    return true;
  });
}

function pipClass(task) {
  const outcome = task.with_router;
  if (!outcome.validated) return "bad";
  if (!outcome.task_correct) return "wrong";
  if (outcome.retries > 0) return "recovered";
  return "ok";
}

function renderList() {
  const aside = document.getElementById("list");
  aside.replaceChildren();
  const filters = document.createElement("div");
  filters.className = "filters";
  for (const [id, label] of [
    ["all", "All"],
    ["calendar", "Calendar"],
    ["tracker", "Tracker"],
    ["lookup", "Lookup"],
    ["recovered", "Recovered"],
    ["unrecoverable", "Stuck"],
    ["wrong", "Wrong but valid"],
  ]) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.setAttribute("aria-pressed", String(state.filter === id));
    button.addEventListener("click", () => {
      state.filter = id;
      const visible = visibleTasks();
      if (visible.length && !visible.some((task) => task.id === state.id)) state.id = visible[0].id;
      render();
    });
    filters.append(button);
  }
  const list = document.createElement("div");
  list.className = "task-list";
  for (const task of visibleTasks()) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-current", String(task.id === state.id));
    const pip = document.createElement("span");
    pip.className = "pip " + pipClass(task);
    const tid = document.createElement("span");
    tid.className = "tid";
    tid.textContent = task.id;
    const title = document.createElement("span");
    title.className = "tt";
    title.textContent = task.title;
    button.append(pip, tid, title);
    button.addEventListener("click", () => {
      state.id = task.id;
      state.liveNote = "";
      render();
    });
    list.append(button);
  }
  aside.append(filters, list);
}

function statusPhrase(outcome) {
  const noun = outcome.retries === 1 ? "retry" : "retries";
  if (!outcome.validated) {
    if (outcome.retries === 0) return "unrecoverable on the first try";
    return `unrecoverable after ${outcome.retries} ${noun}`;
  }
  if (!outcome.task_correct) {
    return outcome.retries === 0
      ? "valid on the first try, arguments do not match"
      : `valid after ${outcome.retries} ${noun}, arguments do not match`;
  }
  if (outcome.retries === 0) return "valid on the first try";
  return `valid after ${outcome.retries} ${noun}`;
}

function renderStage() {
  const stage = document.getElementById("stage");
  stage.replaceChildren();
  const task = state.traces.tasks.find((item) => item.id === state.id);
  if (!task) {
    stage.textContent = "Task not in this recording.";
    return;
  }
  const outcome = task[state.arm];

  const compare = document.createElement("p");
  compare.className = "compare";
  compare.textContent = `With router: ${statusPhrase(task.with_router)}. Without router: ${statusPhrase(task.without_router)}.`;

  const top = document.createElement("div");
  top.className = "stage-top";
  const h2 = document.createElement("h2");
  h2.textContent = task.title;
  const chips = document.createElement("div");
  chips.className = "chips";
  for (const text of [task.id, task.suite, task.failure_class]) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = text;
    chips.append(chip);
  }
  top.append(h2, chips);

  const blurb = document.createElement("p");
  blurb.className = "blurb";
  blurb.textContent = task.blurb;

  const ask = document.createElement("div");
  ask.className = "ask";
  const askLabel = document.createElement("span");
  askLabel.className = "label";
  askLabel.textContent = "Task";
  const askBody = document.createElement("div");
  askBody.textContent = task.user;
  ask.append(askLabel, askBody);

  const arms = document.createElement("div");
  arms.className = "arms";
  for (const [id, label] of [
    ["with_router", "With router"],
    ["without_router", "Without router"],
  ]) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.setAttribute("aria-pressed", String(state.arm === id));
    button.addEventListener("click", () => {
      state.arm = id;
      state.liveNote = "";
      render();
    });
    arms.append(button);
  }

  stage.append(compare, top, blurb, ask, arms);
  if (state.liveNote) {
    const note = document.createElement("p");
    note.className = "live" + (state.liveDiff ? " diff" : "");
    note.textContent = state.liveNote;
    stage.append(note);
  }

  outcome.attempts.forEach((attempt, index) => {
    stage.append(renderAttempt(attempt, index, outcome.attempts.length, outcome));
  });

  if (!outcome.validated && outcome.failure) stage.append(renderFailure(outcome.failure));

  if (state.live) {
    const rerun = document.createElement("button");
    rerun.type = "button";
    rerun.className = "rerun";
    rerun.textContent = "Re-run this arm locally";
    rerun.addEventListener("click", () => rerunTask(task));
    stage.append(rerun);
  }
}

function schemaLabel(attempt) {
  if (attempt.schema_kind === "narrowed") return `grammar narrowed to ${attempt.narrowed_to}`;
  if (attempt.schema_kind === "catalog") return "grammar: full catalog";
  return "no grammar schema";
}

function renderAttempt(attempt, index, total, outcome) {
  const block = document.createElement("section");
  block.className = "attempt";
  const heading = document.createElement("h3");
  const flag = document.createElement("span");
  flag.className = attempt.valid ? "valid" : "invalid";
  flag.textContent = attempt.valid ? "valid" : "invalid";
  heading.append(
    document.createTextNode(`Attempt ${index + 1} of ${total} · `),
    flag,
    document.createTextNode(` · ${schemaLabel(attempt)}`),
  );
  block.append(heading);

  const split = document.createElement("div");
  split.className = "split";
  const rawPanel = document.createElement("div");
  rawPanel.className = "panel";
  const rawLabel = document.createElement("span");
  rawLabel.className = "label";
  rawLabel.textContent = attempt.valid && index === total - 1 ? "Corrected call" : "Raw model output";
  const raw = document.createElement("div");
  raw.className = "raw" + (attempt.valid ? " corrected" : "");
  renderRaw(raw, attempt.raw, attempt.error);
  rawPanel.append(rawLabel, raw);

  const errPanel = document.createElement("div");
  errPanel.className = "panel";
  const errLabel = document.createElement("span");
  errLabel.className = "label";
  errLabel.textContent = attempt.valid ? "Validation" : "Validation error";
  errPanel.append(errLabel);
  if (attempt.valid) {
    const ok = document.createElement("div");
    ok.className = "msg";
    ok.textContent = outcome.task_correct
      ? "Passed. The arguments match the task."
      : "Passed the schema. The arguments do not match the task, so the router does not retry.";
    errPanel.append(ok);
  } else {
    renderErrors(errPanel, attempt.error);
  }
  split.append(rawPanel, errPanel);
  block.append(split);

  if (attempt.retry_prompt) {
    const prompt = document.createElement("div");
    prompt.className = "panel prompt";
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = "Retry prompt";
    const pre = document.createElement("pre");
    pre.textContent = attempt.retry_prompt;
    prompt.append(label, pre);
    block.append(prompt);
  }

  if (attempt.valid && outcome.execution) {
    const exec = document.createElement("div");
    exec.className = "panel exec";
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = "Executed";
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(outcome.execution, null, 2);
    exec.append(label, pre);
    block.append(exec);
  }
  return block;
}

function renderRaw(container, raw, error) {
  const keys = new Set();
  for (const detail of (error && error.details) || []) {
    const loc = detail.loc || [];
    if (loc.length) keys.add(String(loc[loc.length - 1]));
  }
  for (const line of String(raw).split("\n")) {
    const div = document.createElement("div");
    const hit = [...keys].some((key) => line.includes(`"${key}"`));
    div.className = hit ? "bad-line" : "line";
    div.textContent = line.length ? line : " ";
    container.append(div);
  }
}

function renderErrors(container, error) {
  const details = (error && error.details) || [];
  if (!details.length) {
    const p = document.createElement("div");
    p.textContent = (error && error.message) || "Invalid.";
    container.append(p);
    return;
  }
  for (const detail of details) {
    const block = document.createElement("div");
    block.className = "err";
    const loc = document.createElement("div");
    loc.className = "loc";
    loc.textContent = (detail.loc || []).join(".") || "output";
    const msg = document.createElement("div");
    msg.className = "msg";
    msg.textContent = detail.msg;
    block.append(loc, msg);
    if (detail.loc && detail.loc.length && detail.input !== undefined && detail.input !== null) {
      const input = document.createElement("div");
      input.className = "input";
      const shown = typeof detail.input === "string" ? detail.input : JSON.stringify(detail.input);
      input.textContent = "input " + shown;
      block.append(input);
    }
    container.append(block);
  }
}

function renderFailure(failure) {
  const card = document.createElement("section");
  card.className = "failsafe";
  const heading = document.createElement("h3");
  heading.textContent = "Fail-safe · tool not executed";
  const list = document.createElement("dl");
  list.className = "kv";
  const last = (failure.details && failure.details[0]) || {};
  const rows = [
    ["code", failure.code],
    ["attempts", String(failure.attempts)],
    ["retries", String(failure.retries)],
    ["tool", failure.tool || "—"],
    ["executed", "false"],
    ["last error", last.msg || (failure.errors || [])[failure.errors.length - 1] || "—"],
  ];
  for (const [key, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = key;
    const dd = document.createElement("dd");
    dd.textContent = value;
    list.append(dt, dd);
  }
  card.append(heading, list);
  return card;
}

async function rerunTask(task) {
  state.liveNote = "Re-running…";
  state.liveDiff = false;
  renderStage();
  const response = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_id: task.id, arm: state.arm }),
  });
  const payload = await response.json();
  const recorded = task[state.arm];
  state.liveDiff = JSON.stringify(payload.outcome) !== JSON.stringify(recorded);
  state.liveNote = state.liveDiff
    ? "Live re-run differs from the recording."
    : "Live re-run matches the recorded trace.";
  if (!state.liveDiff) renderStage();
  else {
    task[state.arm] = payload.outcome;
    renderStage();
  }
}

window.addEventListener("hashchange", () => {
  readHash();
  state.liveNote = "";
  render();
});

load();
