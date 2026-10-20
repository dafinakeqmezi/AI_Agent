/* Optional controls for the loopback server; static exported dashboards stay read-only. */
(function () {
  "use strict";
  const config = JSON.parse(document.getElementById("live-config").textContent);
  const panel = document.createElement("section");
  panel.className = "card";
  panel.style.marginBottom = "20px";
  panel.innerHTML = `
    <style>
      #live-controls label {display:grid;gap:5px;font-size:13px}
      #live-controls {min-width:0}
      #live-controls details > summary {cursor:pointer;font-weight:600;padding:4px 0}
      #live-controls > details > summary {font-size:17px}
      #live-controls details[open] > summary {margin-bottom:12px}
      #live-controls .run-columns {display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:24px}
      #live-controls .run-columns > div {min-width:0}
      #live-controls .secondary {margin:12px 0;padding:10px 12px;border:1px solid var(--border);border-radius:8px}
      #live-controls .choices label {overflow-wrap:anywhere}
      #live-controls input:not([type=checkbox]),#live-controls select {width:100%;box-sizing:border-box}
      #live-controls .job-footer {display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:10px}
      #live-controls .job-footer .buttons {margin:0}
      #live-status {font-size:12px;color:var(--muted);overflow-wrap:anywhere}
      @media(max-width:900px) {#live-controls .run-columns {grid-template-columns:1fr;gap:4px}}
      #live-controls .fields {display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:12px 0}
      #live-controls input,#live-controls select {min-width:0;padding:8px;border:1px solid var(--border);border-radius:7px;background:var(--surface);color:var(--text)}
      #live-controls fieldset {border:1px solid var(--border);border-radius:8px;margin:14px 0;padding:12px}
      #live-controls .choices {display:grid;gap:8px;max-height:200px;overflow:auto}
      #live-controls .choices label {display:flex;align-items:center;gap:8px}
      #live-controls .buttons {display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
      #live-controls button:disabled {opacity:.45;cursor:default}
      #live-log {white-space:pre-wrap;max-height:280px;overflow:auto;background:var(--surface-2);padding:12px;border-radius:8px;font-size:12px}
      #live-error {color:var(--danger,#b42318);white-space:pre-wrap;margin:8px 0}
    </style>
    <div id="live-controls">
      <details>
      <summary>Run reviews and comparisons</summary>
      <p class="small muted">Select repositories or frozen submissions. Model runs use your chosen account allowance.</p>
      <details class="secondary"><summary>Add a repository</summary>
      <form id="live-add">
        <div class="fields">
          <label>GitHub URL or owner/repo<input id="live-repo" required placeholder="owner/repository"></label>
          <label>Student name<input id="live-student" required></label>
          <label>Assignment<select id="live-assignment"></select></label>
        </div>
        <button class="btn" type="submit">Add repository</button>
      </form>
      </details>
      <div class="run-columns"><div>
      <fieldset><legend>Saved repositories</legend><div id="live-repos" class="choices"></div></fieldset>
      <div class="fields">
        <label>Provider<select id="live-provider">
          <option value="chatgpt">ChatGPT subscription · Codex</option>
          <option value="claude-code">Claude subscription · Claude Code</option>
          <option value="openai">OpenAI API</option><option value="claude">Claude API</option>
        </select></label>
        <label>Model<input id="live-model" placeholder="CLI default or provider model setting" autocomplete="off"></label>
        <label>Maximum calls per phase<input id="live-turns" type="number" min="1" max="60" value="3"></label>
        <label>Seconds per model call<input id="live-timeout" type="number" min="10" max="1800" value="300"></label>
      </div>
      <p id="live-scope" class="small muted"></p>
      <div class="buttons"><button id="live-review" class="btn">Review selected repositories</button></div>
      <details class="secondary"><summary>Freeze repositories for grading</summary>
      <div class="fields"><label>Freeze deadline (optional, with timezone)<input id="live-deadline" placeholder="2026-11-01T23:59:00+01:00"></label></div>
      <p class="small muted">Freezing captures the current default-branch version unless a deadline or saved ref is supplied. Grading is a separate action.</p>
      <div class="buttons"><button id="live-freeze" class="btn">Freeze selected repositories</button></div>
      </details>
      </div><div>
      <fieldset><legend>Frozen submissions</legend><div id="live-submissions" class="choices"></div></fieldset>
      <div class="buttons"><button id="live-grade" class="btn">Grade selected submissions</button><button id="live-compare" class="btn">Compare selected submissions</button></div>
      <p class="small muted">Similarity uses no AI model. Select at least two submissions of the same assignment. Matches are indicators for human review, never proof of cheating or automatic grade deductions.</p>
      </div></div>
      </details>
      <div id="live-error" role="alert"></div>
      <div class="job-footer">
      <div id="live-status" role="status" aria-live="polite">Loading saved results…</div>
      <div class="buttons"><button id="live-refresh" class="btn">Refresh results</button><button id="live-stop" class="btn" disabled>Stop current job</button></div>
      </div>
      <pre id="live-log" hidden></pre>
    </div>`;
  document.querySelector(".wrap").insertBefore(panel, document.getElementById("app"));
  const el = id => document.getElementById("live-" + id);
  let state, busy = false, fetching = false, signature = "", submissionSignature = "";
  let latestJob;
  async function api(path, body) {
    const response = await fetch(path, {method: body ? "POST" : "GET", headers: {
      "X-Dashboard-Token": config.token, "Content-Type": "application/json"
    }, body: body ? JSON.stringify(body) : undefined});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Request failed");
    return result;
  }
  const selected = id => Array.from(el(id).querySelectorAll("input:checked")).map(input => input.value);
  function choices(container, items) {
    const checked = new Set(selected(container));
    el(container).replaceChildren();
    if (!items.length) { el(container).textContent = "None saved yet."; return; }
    items.forEach(item => {
      const label = document.createElement("label"), checkbox = document.createElement("input");
      checkbox.type = "checkbox"; checkbox.value = item.value; checkbox.checked = checked.has(item.value);
      checkbox.onchange = updateButtons;
      label.append(checkbox, document.createTextNode(item.label)); el(container).append(label);
    });
  }
  function updateButtons() {
    const repos = selected("repos"), subs = selected("submissions");
    el("review").disabled = busy || !repos.length;
    el("freeze").disabled = busy || !repos.length;
    el("grade").disabled = busy || !subs.length;
    el("compare").disabled = busy || subs.length < 2;
    el("stop").disabled = !busy;
    el("add").querySelector("button").disabled = busy;
    el("scope").textContent = repos.length + " repositories and " + subs.length + " frozen submissions selected. " +
      "Provider: " + el("provider").selectedOptions[0].text + "; model: " + (el("model").value.trim() || "configured default") + ".";
  }
  async function refresh() {
    if (fetching) return;
    fetching = true;
    try {
      state = await api("/api/state");
      const roster = state.roster.students;
      const nextSignature = JSON.stringify(roster);
      if (nextSignature !== signature) {
        choices("repos", roster.map(r => ({value: r.repo, label: (r.student || r.repo) + " · " + r.repo + " · " + (r.assignment || state.roster.assignment || "assignment missing")})));
        signature = nextSignature;
      }
      const subs = state.data.projects.flatMap(p => p.submissions.map(s => ({value: s.id, label: (s.student || p.student || p.name) + " · " + s.id + " · " + s.assignment})));
      const nextSubs = JSON.stringify(subs);
      if (nextSubs !== submissionSignature) { choices("submissions", subs); submissionSignature = nextSubs; }
      if (!el("assignment").options.length) Object.keys(state.data.assignments).forEach(id => {
        el("assignment").add(new Option(state.data.assignments[id].title + " (" + id + ")", id));
      });
      if (!el("assignment").dataset.initialized) {
        if (state.data.assignments.detyra1) el("assignment").value = "detyra1";
        el("assignment").dataset.initialized = "true";
      }
      latestJob = state.jobs[state.jobs.length - 1];
      busy = state.jobs.some(j => ["queued", "running", "stopping"].includes(j.status));
      if (latestJob) {
        const seconds = busy ? Math.round((Date.now() - Date.parse(latestJob.created_at)) / 1000) : latestJob.elapsed_seconds;
        const usage = latestJob.usage;
        el("status").textContent = latestJob.action + " · " + latestJob.status + " · " + seconds + "s · " + latestJob.scope.join(", ") +
          (usage ? " · " + usage.calls + " model calls · " + usage.input_tokens.toLocaleString() + " input tokens · " + usage.output_tokens.toLocaleString() + " output tokens" :
            ["freeze", "similarity"].includes(latestJob.action) ? " · No AI model used." : " · Token usage appears after a model run finishes when reported by the provider.");
        el("log").hidden = !latestJob.log;
        if (el("log").textContent !== latestJob.log) {
          el("log").textContent = latestJob.log; el("log").scrollTop = el("log").scrollHeight;
        }
      } else el("status").textContent = "Ready. No jobs started in this server session.";
      window.dispatchEvent(new CustomEvent("dashboard-data", {detail: state.data}));
      updateButtons();
    } catch (error) { el("error").textContent = error.message; }
    finally { fetching = false; }
  }
  async function start(action) {
    el("error").textContent = "";
    try {
      await api("/api/jobs", {action, repos: selected("repos"), submissions: selected("submissions"),
        provider: el("provider").value, model: el("model").value.trim(),
        max_turns: Number(el("turns").value), timeout: Number(el("timeout").value), deadline: el("deadline").value.trim()});
      busy = true; updateButtons(); await refresh();
    } catch (error) { el("error").textContent = error.message; }
  }
  el("add").onsubmit = async event => {
    event.preventDefault(); el("error").textContent = "";
    try {
      await api("/api/repos", {repo: el("repo").value.trim(), student: el("student").value.trim(), assignment: el("assignment").value});
      el("repo").value = ""; el("student").value = ""; await refresh();
    } catch (error) { el("error").textContent = error.message; }
  };
  ["review", "freeze", "grade"].forEach(action => el(action).onclick = () => start(action));
  el("compare").onclick = () => start("similarity");
  el("refresh").onclick = refresh;
  el("stop").onclick = async () => {
    try { if (latestJob) await api("/api/stop", {id: latestJob.id}); await refresh(); }
    catch (error) { el("error").textContent = error.message; }
  };
  el("provider").onchange = updateButtons; el("model").oninput = updateButtons;
  refresh();
  setInterval(refresh, 3000);
})();
