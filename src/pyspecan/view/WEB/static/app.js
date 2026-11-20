"use strict";
// pyspecan web view: all logic lives in the server, this only draws and forwards input.

const $ = (id) => document.getElementById(id);
const SI = [[1e9, "G"], [1e6, "M"], [1e3, "k"]];
const MARGIN = {l: 62, r: 12, t: 8, b: 24};
const GRID = "rgba(255,255,255,0.15)", TEXT = "#bbb";

// colormaps arrive in the state as stops [[pos, [r, g, b]], ...] (channels 0..1), expanded to 256 packed ABGR entries
const LUTS = {};
function lutFor(name) {
    if (LUTS[name]) return LUTS[name];
    const stops = (state && state.colormaps && state.colormaps[name]) || [[0, [0, 0, 0]], [1, [1, 1, 1]]];
    const lut = new Uint32Array(256);
    for (let i = 0; i < 256; i++) {
        const t = i / 255;
        let k = 0;
        while (k < stops.length - 2 && t > stops[k + 1][0]) k++;
        const [p0, c0] = stops[k], [p1, c1] = stops[k + 1];
        const f = Math.min(Math.max((t - p0) / (p1 - p0 || 1), 0), 1);
        const ch = [0, 1, 2].map((c) => Math.round((c0[c] + (c1[c] - c0[c]) * f) * 255));
        lut[i] = (255 << 24) | (ch[2] << 16) | (ch[1] << 8) | ch[0];
    }
    return (LUTS[name] = lut);
}

let ws = null;
let state = null;
let layoutSig = "";
const runtime = {};      // plot id -> {frame, canvas, images: {axis index: {w, h, buf, canvas}}}
const settingsOpen = new Set();
const sectionOpen = {}; // "plot id:section" -> open, sections start open and "Advanced" folds closed

function fmtHz(v) {
    for (const [scale, suffix] of SI) {
        if (Math.abs(v) >= scale) return `${(v / scale).toFixed(3).replace(/\.?0+$/, "")}${suffix}`;
    }
    return v.toFixed(0);
}
// a frequency with enough digits to place a marker by, 12.3456 MHz
function fmtHzFull(v) {
    for (const [scale, suffix] of SI) {
        if (Math.abs(v) >= scale) return `${(v / scale).toFixed(4).replace(/\.?0+$/, "")} ${suffix}Hz`;
    }
    return `${v.toFixed(1).replace(/\.0$/, "")} Hz`;
}
const fmtLog10 = (v) => { const [m, e] = (10 ** v).toExponential(0).split("e"); return `${m}e${+e}`; }; // y holds log10 of the value
// seconds, in the unit that shows `span` (default: v itself), as plots.frame.fmt_time
function fmtTime(v, span) {
    const a = Math.abs(span ?? v);
    const [scale, name] = a >= 1 ? [1, "s"] : a >= 1e-3 ? [1e-3, "ms"] : a >= 1e-6 ? [1e-6, "µs"] : [1e-9, "ns"];
    return `${+(v / scale).toPrecision(4)} ${name}`;
}
// the x formatter of an axis over [xmin, xmax]
const fmtXOf = (axis, xmin, xmax, full) => axis.xfmt === "freq" ? (full ? fmtHzFull : fmtHz)
    : axis.xfmt === "time" ? (v) => fmtTime(v, xmax - xmin) : fmtNum;
// trace point i's x: its own, or one point per bin across the axis' x range, or i without one (see plots.frame.Trace)
const traceX = (s, i, axis) => (s.x ? s.x[i] : axis.xmin != null && axis.xmax != null ? axis.xmin + (i * (axis.xmax - axis.xmin)) / s.y.length : i);
const fmtNum = (v) => (Math.abs(v) >= 1000 || (v !== 0 && Math.abs(v) < 0.01) ? v.toExponential(1) : +v.toFixed(2) + "");

// --- connection --- //
function send(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}
const cmd = (c) => send({type: "cmd", cmd: c});
const set = (key, value) => send({type: "set", key, value});
const plotOp = (op, extra) => send({type: "plot", op, ...extra});

function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
        setConnected(false);
        setTimeout(connect, 1000);
    };
    ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "state") applyState(msg.data);
        else if (msg.type === "frame") { applyFrame(msg.data); send({type: "ack"}); } // the server waits for these
        else if (msg.type === "error") showMessage(msg.data, true);
    };
}

function setConnected(ok) {
    const el = $("connection-status");
    el.className = `status ${ok ? "connected" : "disconnected"}`;
    el.title = ok ? "connected" : "disconnected";
}

let errorUntil = 0;
function showMessage(text, isError = false) {
    if (isError) errorUntil = Date.now() + 5000;
    else if (Date.now() < errorUntil) return; // keep errors visible for a few seconds
    $("lbl-message").textContent = text;
}

// --- state -> DOM --- //
function setValue(el, value) {
    if (document.activeElement === el) return; // don't clobber what the user is typing
    if (el.type === "checkbox") el.checked = !!value;
    else el.value = value;
}

function fillSelect(el, options, label = (o) => o) {
    if (el.options.length === options.length && options.every((o, i) => el.options[i].value === o)) return;
    el.replaceChildren(...options.map((o) => new Option(label(o), o)));
}

function applyStatus(s) {
    showMessage(s.message);
    $("btn-start").disabled = s.playing;
    $("btn-stop").disabled = !s.playing;
    if (s.cur_samp !== undefined) {
        $("lbl-time").textContent = `${s.time_cur} / ${state ? state.time_tot : ""}`;
        if (!seeking) $("sld-samp").value = s.cur_samp;
    }
}

function applyState(s) {
    state = s;
    fillSelect($("sel-add-plot"), ["", ...s.plot_types], (o) => o || "+ Add plot…");
    setValue($("in-fs"), s.fs);
    setValue($("in-cf"), s.cf);
    setValue($("in-nfft"), s.nfft_exp);
    setValue($("in-sweep"), s.sweep);
    setValue($("in-overlap"), s.overlap);
    setValue($("in-show"), s.show);
    $("lbl-block").textContent = s.block_size;

    const isFile = s.max_samp !== undefined;
    document.querySelectorAll(".file-only").forEach((el) => (el.hidden = !isFile));
    if (isFile) {
        fillSelect($("sel-fmt"), s.formats);
        setValue($("sel-fmt"), s.fmt);
        $("lbl-path").textContent = s.path || "no file selected";
        $("sld-samp").max = s.max_samp;
    }
    applyRadio(s.radio);
    applyStatus(s);
    applyGlobals(s.globals);
    syncPlots(s);
}

// --- settings every plot shares (calibration), under the source settings --- //
let globalsSig = null;
function applyGlobals(g) {
    if (!g) return;
    const sig = JSON.stringify(g.fields);
    if (sig !== globalsSig) {
        globalsSig = sig;
        const groups = {};
        for (const f of g.fields) (groups[f.group] ||= []).push(f);
        $("globals").replaceChildren(...Object.entries(groups).map(([name, fields]) =>
            el("details", {className: "section", open: true}, el("summary", {textContent: name}),
                ...fields.map((f) => fieldInput(`g-${f.key}`, f, (v) => set(f.key, v))))));
    }
    for (const f of g.fields) setValue($(`g-${f.key}`), g.settings[f.key]);
}

// --- the radio of a live sink --- //
let radioList = [];
function applyRadio(r) {
    document.querySelectorAll(".radio-only").forEach((el) => (el.hidden = !r));
    if (!r) return;
    const what = {local: "Radio on this machine", controlling: "Controlling", watching: "Watching, it is controlled elsewhere"}[r.control];
    $("lbl-radio").textContent = `${what}: ${r.device}` + (r.lag > 0.1 ? ` (${Math.round(r.lag * 1000)} ms behind)` : "");
    $("btn-claim").textContent = r.control === "controlling" ? "Release" : "Claim";
    $("btn-claim").disabled = r.control === "local";
    for (const id of ["in-fs", "in-cf"]) $(id).disabled = r.control === "watching"; // it can be looked at, not told what to do
    if (r.inverted) $("lbl-radio").textContent += " - spectrum mirrored, corrected";
    const ants = r.antennas || [];
    $("grp-antenna").hidden = !ants.length;
    const asel = $("sel-antenna");
    asel.replaceChildren(...ants.map((a) => new Option(a.label, a.port)));
    const cur = ants.find((a) => a.selected);
    asel.value = cur ? cur.port : "";
    asel.disabled = r.control === "watching";
    const sel = $("sel-radio");
    if (!radioList.length) sel.replaceChildren(new Option(r.device, ""));
}
async function loadRadios() {
    try {
        const res = await fetch("/api/radios");
        if (!res.ok) return;
        radioList = (await res.json()).filter((o) => o.target);
        const sel = $("sel-radio");
        sel.replaceChildren(new Option(state && state.radio ? state.radio.device : "", ""), ...radioList.map((o) => new Option(o.label, o.target)));
    } catch (e) { /* the list is a convenience, typing nothing works too */ }
}

// --- plots --- //
function syncPlots(s) {
    const sig = JSON.stringify([s.layout, Object.entries(s.plots).map(([id, p]) => [id, p.name, p.link, p.linkable])]);
    if (sig !== layoutSig) {
        layoutSig = sig;
        buildPlots(s);
    }
    for (const [id, p] of Object.entries(s.plots)) { updatePlotControls(id, p); updateMarkers(id, p); }
}

function el(tag, props = {}, ...children) {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...children);
    return e;
}

function buildPlots(s) {
    for (const id of Object.keys(runtime)) if (!(id in s.plots)) { delete runtime[id]; settingsOpen.delete(id); }
    const tail = el("div", {className: "drop-tail", textContent: "drop here for a new row"});
    tail.ondragenter = (ev) => { if (dragId) ev.preventDefault(); }; // only a cancelled dragenter makes it the drop target
    tail.ondragover = (ev) => { if (!dragId) return; ev.preventDefault(); clearDrop(); tail.classList.add("drop-end"); };
    tail.ondragleave = () => tail.classList.remove("drop-end");
    tail.ondrop = (ev) => { ev.preventDefault(); const id = dragId; clearDrop(); plotOp("move", {id, where: "end"}); };
    $("panels").replaceChildren(...s.layout.map((row) =>
        el("div", {className: "plot-row"}, ...row.map((id) => buildPlot(id, s.plots[id])))), tail);
}

// --- drag & drop: a plot is dropped on the half of another plot it should go to --- //
let dragId = null;
function zoneAt(box, ev) {
    const r = box.getBoundingClientRect();
    const fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
    const d = {left: fx, right: 1 - fx, above: fy, below: 1 - fy};
    return Object.keys(d).reduce((a, b) => (d[a] <= d[b] ? a : b)); // the nearest edge
}
function clearDrop() {
    document.querySelectorAll("[class*='drop-']").forEach((e) =>
        e.classList.remove("drop-left", "drop-right", "drop-above", "drop-below", "drop-end"));
}
function bindDrag(id, container, header) {
    header.draggable = true;
    header.ondragstart = (ev) => {
        dragId = id;
        ev.dataTransfer.setData("text/plain", id);
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setDragImage(container, 20, 10);
        setTimeout(() => { container.classList.add("dragging"); document.body.classList.add("dragging-any"); });
    };
    header.ondragend = () => {
        dragId = null;
        container.classList.remove("dragging");
        document.body.classList.remove("dragging-any");
        clearDrop();
    };
    container.ondragenter = (ev) => { if (dragId && dragId !== id) ev.preventDefault(); };
    container.ondragover = (ev) => {
        if (!dragId || dragId === id) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        const zone = zoneAt(container, ev);
        if (!container.classList.contains(`drop-${zone}`)) { clearDrop(); container.classList.add(`drop-${zone}`); }
    };
    container.ondragleave = (ev) => { if (!container.contains(ev.relatedTarget)) clearDrop(); };
    container.ondrop = (ev) => {
        if (!dragId || dragId === id) return;
        ev.preventDefault();
        const moving = dragId, where = zoneAt(container, ev);
        clearDrop();
        plotOp("move", {id: moving, target: id, where});
    };
}

function buildPlot(id, p) {
    const rt = runtime[id] || (runtime[id] = {frame: null, images: {}});
    if (!rt.tool) rt.tool = "channel";

    const pause = el("button", {id: `pause-${id}`, onclick: () => plotOp("set", {id, key: "enabled", value: !state.plots[id].settings.enabled})});
    const gear = el("button", {textContent: "⚙", title: "settings", onclick: () => {
        settingsOpen.has(id) ? settingsOpen.delete(id) : settingsOpen.add(id);
        $(`settings-${id}`).hidden = !settingsOpen.has(id);
    }});
    const del = el("button", {textContent: "✕", title: "remove plot", onclick: () => plotOp("del", {id})});
    const actions = (p.actions || []).map((a) => el("button", {textContent: a, title: a, className: "plot-action",
        onclick: () => plotOp("act", {id, action: a})}));
    const ptime = el("span", {id: `ptime-${id}`, className: "muted"});

    const settings = el("div", {id: `settings-${id}`, className: "plot-settings", hidden: !settingsOpen.has(id)},
        ...buildSections(id, p));
    rt.canvas = el("canvas");
    bindCanvas(id, rt.canvas);
    const header = el("div", {className: "plot-header", title: "drag to move"},
        el("span", {className: "grip", textContent: "⠿"}), el("b", {textContent: p.name}), ...linkChip(p), ptime,
        el("span", {className: "right"}, ...(p.marker_kinds ? [toolMenu(id), markerMenu(id, p)] : []), ...linkMenu(id, p), ...actions, pause, gear, del));
    rt.readout = el("div", {className: "readout", hidden: true});
    rt.table = el("div", {className: "mtable", hidden: true});
    rt.editor = el("div", {className: "marker-editor", id: `markers-${id}`, hidden: true});
    const container = el("div", {className: "plot", id: `plot-${id}`}, header,
        settings, el("div", {className: "canvas-box"}, rt.canvas), rt.readout, el("div", {className: "mk-panel"}, rt.table, rt.editor));
    bindDrag(id, container, header);
    new ResizeObserver(() => drawPlot(id)).observe(rt.canvas.parentElement);
    const tool = container.querySelector(`#tool-${id}`);
    if (tool) tool.value = rt.tool;
    return container;
}

// what dragging on empty space draws, a click draws a point. Existing markers are always draggable
const TOOLS = ["channel", "acpr", "obw", "point", "off"];
function toolMenu(id) {
    const sel = el("select", {id: `tool-${id}`, title: "what dragging over the plot draws (existing markers can always be moved and resized)"},
        ...TOOLS.map((t) => new Option(t === "off" ? "Draw: off" : `Draw: ${t}`, t)));
    sel.onchange = () => { runtime[id].tool = sel.value; };
    return sel;
}

// "+ Marker" menu: one entry per marker kind the plot offers
function markerMenu(id, p) {
    const sel = el("select", {id: `addmk-${id}`, title: "add a marker or measurement"},
        new Option("+ Marker", ""), ...Object.keys(p.marker_kinds).map((k) => new Option(k, k)));
    sel.onchange = () => { if (sel.value) plotOp("marker_add", {id, kind: sel.value}); sel.value = ""; };
    return sel;
}

const ACTION_LABELS = {prev: "▲ prev", next: "▼ next", left: "◀ left", right: "▶ right"}; // a marker's actions, see MarkerKind.ACTIONS

// one row of editable settings per marker, rebuilt only when the markers change
function updateMarkers(id, p) {
    const rt = runtime[id];
    if (!rt || !rt.editor || !p.markers) return;
    const sig = JSON.stringify(p.markers);
    if (rt.markerSig === sig) return;
    rt.markerSig = sig;
    if (rt.drag && rt.drag.committed) { rt.drag = null; drawPlot(id); }
    rt.editor.hidden = !p.markers.length;
    rt.editor.replaceChildren(...p.markers.map((m) => {
        const fields = m.fields.map((f) => {
            const input = f.kind === "select"
                ? el("select", {}, ...f.options.map((o) => new Option(o, o)))
                : el("input", {type: f.kind === "check" ? "checkbox" : f.kind === "number" ? "number" : "text",
                               placeholder: f.hint || "", min: f.min ?? "", max: f.max ?? "", step: f.step ?? "any", size: 8});
            setValue(input, m.params[f.key]);
            const send_ = (v) => plotOp("marker_set", {id, marker: m.id, key: f.key, value: v});
            if (f.kind === "check") input.onchange = () => send_(input.checked);
            else if (f.kind === "select") input.onchange = () => send_(input.value);
            else input.onkeydown = (ev) => { if (ev.key === "Enter") { send_(input.value); input.blur(); } };
            return el("label", {className: "mk-field"}, el("span", {className: "muted", textContent: f.label + " "}), input);
        });
        const actions = (m.actions || []).map((a) => el("button", {textContent: ACTION_LABELS[a] || a, title: `${a} peak`,
            onclick: () => plotOp("marker_act", {id, marker: m.id, action: a})}));
        return el("div", {className: "mk-row"}, el("b", {textContent: m.id}), el("span", {className: "muted", textContent: m.kind}), ...fields,
            ...actions, el("button", {textContent: "✕", title: "remove marker", onclick: () => plotOp("marker_del", {id, marker: m.id})}));
    }));
}

// --- links: linked plots share level / processing settings, the auto ref level and markers --- //
function linkChip(p) {
    if (!p.link) return [];
    const others = state.links[p.link] || [];
    return [el("span", {className: "link-chip", textContent: `🔗 ${p.link}`, title: `linked with ${others.join(", ")}`})];
}

function linkMenu(id, p) {
    if (!p.linkable.length && !p.link) return [];
    const sel = el("select", {className: "link-menu", title: "link to another plot: they share ref level, scale, VBW, window, unit and markers"},
        new Option(p.link ? `Linked ${p.link}` : "Link…", ""),
        ...(p.link ? [new Option("Unlink", "-")] : []),
        ...p.linkable.filter((t) => !p.link || state.plots[t].link !== p.link)
            .map((t) => new Option(`→ ${state.plots[t].name} (${t})`, t)));
    sel.onchange = () => {
        if (sel.value === "-") plotOp("unlink", {id});
        else if (sel.value) plotOp("link", {id, target: sel.value});
        sel.value = "";
    };
    return [sel];
}

// settings grouped into collapsible sections, rarely used ones folded under "Advanced"
function buildSections(id, p) {
    const groups = {};
    for (const f of p.fields) (groups[f.group] ||= []).push(f);
    return Object.entries(groups).map(([name, fields]) => {
        const basic = fields.filter((f) => !f.advanced), adv = fields.filter((f) => f.advanced);
        const children = basic.map((f) => buildField(id, f, p));
        if (adv.length) children.push(section(`${id}:${name}:adv`, "Advanced", false, adv.map((f) => buildField(id, f, p)), "advanced"));
        return section(`${id}:${name}`, name, true, children);
    });
}

function section(key, title, dflt, children, cls = "") {
    const d = el("details", {className: `section ${cls}`, open: sectionOpen[key] ?? dflt},
        el("summary", {textContent: title}), el("div", {className: "section-body"}, ...children));
    d.ontoggle = () => { sectionOpen[key] = d.open; };
    return d;
}

function fieldInput(inputId, f, send_) {
    const input = f.kind === "select"
        ? el("select", {}, ...f.options.map((o) => new Option(o, o)))
        : el("input", {type: f.kind === "check" ? "checkbox" : f.kind === "number" ? "number" : "text",
                       placeholder: f.hint || "", min: f.min ?? "", max: f.max ?? "", step: f.step ?? "any"});
    input.id = inputId;
    if (f.kind === "check") input.onchange = () => send_(input.checked);
    else if (f.kind === "select") input.onchange = () => send_(input.value);
    else {
        input.onkeydown = (ev) => { if (ev.key === "Enter") { send_(input.value); input.blur(); } };
        input.onblur = () => { // back to what is really set
            if (!state) return;
            applyGlobals(state.globals);
            for (const [i, p] of Object.entries(state.plots)) updatePlotControls(i, p);
        };
    }
    const label = el("label", {htmlFor: input.id, textContent: f.label});
    if (f.help) label.title = f.help;
    return el("div", {className: "control-group"}, label, input);
}

function buildField(id, f, p) {
    const group = fieldInput(`f-${id}-${f.key}`, f, (v) => plotOp("set", {id, key: f.key, value: v}));
    if (p.link && f.scope === "link") {
        group.classList.add("linked");
        group.querySelector("label").title = `shared by link ${p.link}`;
    }
    return group;
}

function updatePlotControls(id, p) {
    const pause = $(`pause-${id}`);
    if (!pause) return;
    pause.textContent = p.settings.enabled ? "Pause" : "Resume";
    for (const f of p.fields) setValue($(`f-${id}-${f.key}`), p.settings[f.key]);
}

function applyFrame(data) {
    applyStatus(data.status);
    for (const [id, frame] of Object.entries(data.plots)) {
        const rt = runtime[id];
        if (!rt) continue;
        rt.frame = frame;
        const pt = $(`ptime-${id}`);
        const name = state && state.plots[id] ? state.plots[id].name : "";
        if (pt) pt.textContent = `${frame.title && frame.title !== name ? frame.title + "  " : ""}${(frame.ptime * 1000).toFixed(1)} ms`;
        frame.axes.forEach((axis, i) => {
            if (axis.image) applyImage(rt, i, axis.image);
            if (axis.surface) { // a 3d surface's heights, decoded once
                const bin = atob(axis.surface.data), b = new Uint8Array(bin.length);
                for (let k = 0; k < bin.length; k++) b[k] = bin.charCodeAt(k);
                axis.surface.bytes = b;
            }
        });
        applyReadout(rt, frame.readout || []);
        applyTable(rt, frame.table);
        drawPlot(id);
    }
}

// the marker table: results of the markers, read only (they are edited in the rows below it)
function applyTable(rt, table) {
    const key = JSON.stringify(table);
    if (rt.tableKey === key) return;
    rt.tableKey = key;
    rt.table.hidden = !table || !table.rows.length;
    if (rt.table.hidden) { rt.table.replaceChildren(); return; }
    rt.table.replaceChildren(el("table", {},
        el("thead", {}, el("tr", {}, ...table.columns.map((c) => el("th", {textContent: c})))),
        el("tbody", {}, ...table.rows.map((r) => el("tr", {className: r.id ? "" : "cont"}, ...r.cells.map((c) => el("td", {textContent: c})))))));
}

// the measurement table under the plot, rebuilt only when it changed
function applyReadout(rt, rows) {
    const key = JSON.stringify(rows);
    if (rt.readoutKey === key) return;
    rt.readoutKey = key;
    rt.readout.hidden = !rows.length;
    rt.readout.replaceChildren(...rows.map(([k, v]) =>
        el("span", {className: "ro-item"}, el("span", {className: "muted", textContent: k + " "}), el("span", {textContent: v}))));
}

// images arrive either whole, or as the newest rows of a scrolling history (newest on top)
function applyImage(rt, i, im) {
    const bin = atob(im.data), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const w = im.cols, n = im.rows_in, h = im.scroll ? im.rows : n;
    let st = rt.images[i];
    if (!st || st.w !== w || st.h !== h || (im.scroll && im.clear)) {
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        st = rt.images[i] = {w, h, buf: new Uint8Array(w * h), canvas};
    }
    const buf = st.buf;
    if (!im.scroll) buf.set(bytes);
    else if (n >= h) {
        for (let r = 0; r < h; r++) buf.set(bytes.subarray((n - 1 - r) * w, (n - r) * w), r * w);
    } else {
        buf.copyWithin(n * w, 0, (h - n) * w); // scroll down
        for (let r = 0; r < n; r++) buf.set(bytes.subarray((n - 1 - r) * w, (n - r) * w), r * w);
    }
    const lut = lutFor(im.cmap);
    const data = new ImageData(w, h);
    const px = new Uint32Array(data.data.buffer);
    for (let k = 0; k < buf.length; k++) px[k] = lut[buf[k]];
    st.canvas.getContext("2d").putImageData(data, 0, 0);
}

// --- mouse: draw, move and resize markers --- //
const EDGE_PX = 6, MIN_DRAG_PX = 6, MAX_HZ_DIGITS = 1;
const hz_ = (v) => v.toFixed(MAX_HZ_DIGITS); // a plain number of Hz, the server parses it like "1.2M"

function pointerPos(rt, ev) {
    const r = rt.canvas.getBoundingClientRect();
    return [ev.clientX - r.left, ev.clientY - r.top];
}
function axisAt(rt, py) {
    return (rt.geom || []).findIndex((g) => g && py >= g.y0 && py <= g.y0 + g.h);
}
// data x <-> pixel x of an axis' geometry (on a log axis, see Axis.xlog, in log10 of the values)
const dataX = (g, px) => g.xlog ? 10 ** (Math.log10(g.xmin) + ((px - g.x0) / g.w) * Math.log10(g.xmax / g.xmin))
    : g.xmin + ((px - g.x0) / g.w) * (g.xmax - g.xmin);
const pixX = (g, v) => g.xlog ? g.x0 + (Math.log10(v / g.xmin) / Math.log10(g.xmax / g.xmin)) * g.w
    : g.x0 + ((v - g.xmin) / (g.xmax - g.xmin)) * g.w;
const dataY = (g, py) => g.ymax - ((py - g.y0) / g.h) * (g.ymax - g.ymin);
const pixY = (g, v) => g.y0 + (1 - (v - g.ymin) / (g.ymax - g.ymin)) * g.h;
const hasLevels = (g, axis) => !g.isImage || axis.ymin != null;
// is pixel row py inside a band's y span (always for a band without one), as plots.drag._in_y
function inBandY(g, axis, b, py) {
    if ((b.ylo == null && b.yhi == null) || !hasLevels(g, axis)) return true;
    const a = pixY(g, b.yhi ?? g.ymax), z = pixY(g, b.ylo ?? g.ymin);
    return py >= Math.min(a, z) - EDGE_PX && py <= Math.max(a, z) + EDGE_PX;
}

// the marker, level line or band edge under the pointer: {i, mode: "marker" | "level" | "left" | "right" | "move", owner, edit, lo, hi}
// (for "level" lo / hi are its y), as plots.drag.hit_test
function hitTest(rt, px, py) {
    const i = axisAt(rt, py);
    if (i < 0 || !rt.frame) return null;
    const g = rt.geom[i], axis = rt.frame.axes[i];
    if (!g || g.is3d) return null;
    for (const m of axis.markers || []) { // points first: they sit on top of the bands
        if (!m.edit || m.kind === "hline" || Math.abs(pixX(g, m.x) - px) > EDGE_PX) continue;
        const ym = Math.min(Math.max(g.y0 + (1 - (m.y - g.ymin) / (g.ymax - g.ymin)) * g.h, g.y0 + 26), g.y0 + g.h); // as drawMarkers places the triangle
        if (m.kind === "vline" || g.isImage || Math.abs(py - (ym - 7)) <= 10)
            return {i, mode: "marker", owner: m.owner, edit: m.edit, lo: m.x, hi: m.x};
    }
    if (hasLevels(g, axis)) {
        for (const m of axis.markers || []) {
            if (m.edit && m.kind === "hline" && Math.abs(pixY(g, m.y) - py) <= EDGE_PX)
                return {i, mode: "level", owner: m.owner, edit: m.edit, lo: m.y, hi: m.y};
        }
    }
    const bands = (axis.bands || []).filter((b) => b.edit && inBandY(g, axis, b, py));
    for (const b of [...bands].reverse()) {
        const a = pixX(g, b.lo), z = pixX(g, b.hi);
        const near = (v) => Math.abs(v - px) <= EDGE_PX;
        const hit = {i, owner: b.owner, edit: b.edit, lo: b.lo, hi: b.hi};
        if (near(a) && (!near(z) || Math.abs(a - px) <= Math.abs(z - px))) return {...hit, mode: "left"};
        if (near(z)) return {...hit, mode: "right"};
    }
    for (const b of [...bands].reverse()) {
        if (px > pixX(g, b.lo) && px < pixX(g, b.hi)) return {i, mode: "move", owner: b.owner, edit: b.edit, lo: b.lo, hi: b.hi};
    }
    return null;
}

// the axis with the band / marker being dragged drawn where the pointer is (the server only hears about it on release)
function dragged(rt, axis, i) {
    const d = rt.drag;
    if (!d || d.i !== i) return axis;
    const lo = Math.min(d.lo, d.hi), hi = Math.max(d.lo, d.hi);
    if (d.mode === "new") {
        return {...axis, bands: [...(axis.bands || []), {lo, hi, color: "#5cb85c", alpha: 0.15, label: "", edit: ["freq", "bw"]}]};
    }
    const same = (m) => m.edit && m.owner === d.owner && m.edit === d.edit;
    if (d.mode === "marker") {
        return {...axis, markers: (axis.markers || []).map((m) => (same(m) && m.kind !== "hline" ? {...m, x: d.lo} : m))};
    }
    if (d.mode === "level") {
        return {...axis, markers: (axis.markers || []).map((m) => (same(m) && m.kind === "hline" ? {...m, y: d.lo} : m))};
    }
    return {...axis, bands: (axis.bands || []).map((b) => (b.owner === d.owner && b.edit && b.edit[1] === d.edit[1] ? {...b, lo, hi} : b))};
}

// can new markers be drawn on axis i: a frequency axis of a plot that has markers
const canDraw = (id, rt, i) => rt.tool !== "off" && i >= 0 && !!rt.frame && rt.frame.axes[i].xfmt === "freq"
    && !!(state.plots[id] && state.plots[id].markers);

function bindCanvas(id, canvas) {
    canvas.style.touchAction = "none";
    canvas.addEventListener("pointerleave", () => { const rt = runtime[id]; rt.hover = null; if (!rt.drag) drawPlot(id); });
    canvas.addEventListener("pointermove", (ev) => {
        const rt = runtime[id];
        [rt.hover_x, rt.hover_y] = pointerPos(rt, ev);
        rt.hover = true;
        if (rt.turn) { // turning a 3d axis
            const t = rt.turn, v = view3d(rt, t.i);
            v.az = t.az - (rt.hover_x - t.px) * 0.5;
            v.el = Math.min(90, Math.max(-90, t.el + (rt.hover_y - t.py) * 0.5));
            drawPlot(id);
            return;
        }
        if (!rt.drag) {
            drawPlot(id);
            const [px, py] = pointerPos(rt, ev), hit = hitTest(rt, px, py);
            const i = axisAt(rt, py);
            if (i >= 0 && rt.geom[i] && rt.geom[i].is3d) { canvas.style.cursor = "grab"; return; }
            canvas.style.cursor = hit ? (hit.mode === "move" ? "grab" : hit.mode === "level" ? "ns-resize" : "ew-resize")
                : (canDraw(id, rt, i) ? "crosshair" : "");
            return;
        }
        const [qx, qy] = pointerPos(rt, ev), d = rt.drag, g = rt.geom[d.i];
        const x = dataX(g, Math.min(Math.max(qx, g.x0), g.x0 + g.w));
        if (d.mode === "level") {
            const y = dataY(g, Math.min(Math.max(qy, g.y0), g.y0 + g.h));
            d.lo = d.hi = y;
            d.moved = d.moved || Math.abs(pixY(g, y) - pixY(g, d.startY)) > 2;
            drawPlot(id);
            return;
        }
        if (d.mode === "left") d.lo = Math.min(x, d.hi);
        else if (d.mode === "right") d.hi = Math.max(x, d.lo);
        else if (d.mode === "move") { const dx = x - d.startX; d.lo = d.lo0 + dx; d.hi = d.hi0 + dx; }
        else if (d.mode === "marker") d.lo = d.hi = x;
        else d.hi = x; // new: lo is where it started
        d.moved = d.moved || Math.abs(pixX(g, x) - pixX(g, d.startX)) > 2;
        drawPlot(id);
    });
    canvas.addEventListener("pointerdown", (ev) => {
        const rt = runtime[id];
        if (ev.button !== 0 || !rt.frame) return;
        const [px, py] = pointerPos(rt, ev);
        const at = axisAt(rt, py);
        if (at >= 0 && rt.geom[at] && rt.geom[at].is3d) { // turn the view
            const v = view3d(rt, at);
            rt.turn = {i: at, px, py, az: v.az, el: v.el};
            canvas.setPointerCapture(ev.pointerId);
            canvas.style.cursor = "grabbing";
            ev.preventDefault();
            return;
        }
        let d = hitTest(rt, px, py);
        if (!d) {
            const i = axisAt(rt, py);
            if (!canDraw(id, rt, i)) return;
            const g = rt.geom[i], x = dataX(g, px);
            d = {i, mode: "new", lo: x, hi: x};
        }
        const g = rt.geom[d.i], x = dataX(g, px);
        rt.drag = {...d, startX: x, startY: d.mode === "level" ? d.lo : dataY(g, py), lo0: d.lo, hi0: d.hi, startPx: px, moved: false};
        canvas.setPointerCapture(ev.pointerId);
        canvas.style.cursor = d.mode === "move" ? "grabbing" : canvas.style.cursor;
        ev.preventDefault();
    });
    const finish = (ev, cancel) => {
        const rt = runtime[id];
        if (rt.turn) { rt.turn = null; canvas.style.cursor = "grab"; return; }
        const d = rt.drag;
        if (!d) return;
        // a plain click on a marker does nothing, on a box of the plot's (a found signal) it applies the box
        if (cancel || !(d.moved || d.mode === "new" || (["move", "left", "right"].includes(d.mode) && !d.owner && Array.isArray(d.edit)))) rt.drag = null;
        else commitDrag(id, rt, d, rt.geom[d.i]);
        drawPlot(id);
    };
    canvas.addEventListener("pointerup", (ev) => finish(ev, false));
    canvas.addEventListener("dblclick", (ev) => { // a 3d axis back to its first view
        const rt = runtime[id], i = axisAt(rt, pointerPos(rt, ev)[1]);
        if (i >= 0 && rt.geom[i] && rt.geom[i].is3d) { rt.view3d[i] = {...VIEW3D}; drawPlot(id); }
    });
    canvas.addEventListener("pointercancel", (ev) => finish(ev, true));
}

// send what a finished drag means: move / resize an existing marker, or add a new one
function commitDrag(id, rt, d, g) {
    const lo = Math.min(d.lo, d.hi), hi = Math.max(d.lo, d.hi);
    const wide = (pixX(g, hi) - pixX(g, lo)) >= MIN_DRAG_PX;
    let sent = true;
    if (d.mode === "new") {
        if (rt.tool === "point" && !wide) plotOp("marker_add", {id, kind: "point", params: {freq: hz_(d.hi)}});
        else if (rt.tool !== "point" && wide) {
            const params = rt.tool === "obw" ? {freq: hz_((lo + hi) / 2), span: hz_(hi - lo)} : {freq: hz_((lo + hi) / 2), bw: hz_(hi - lo)};
            plotOp("marker_add", {id, kind: rt.tool, params});
        } else sent = false;
    } else {
        const params = d.mode === "level" ? {[d.edit]: +d.lo.toPrecision(6) + ""}
            : d.mode === "marker" ? {[d.edit]: hz_(d.lo)}
            : {[d.edit[0]]: hz_((lo + hi) / 2), [d.edit[1]]: hz_(Math.max(hi - lo, 1))};
        if (d.owner) plotOp("marker_set", {id, marker: d.owner, params});
        else for (const [key, value] of Object.entries(params)) plotOp("set", {id, key, value}); // a mark of the plot itself
    }
    if (!sent) { rt.drag = null; return; }
    // keep showing the dropped position until the server's state arrives (or a moment passes)
    const mine = rt.drag = {...d, committed: true};
    setTimeout(() => { if (rt.drag === mine) { rt.drag = null; drawPlot(id); } }, 1500);
}

// --- drawing --- //
function extent(axis, key) {
    const lo = axis[key + "min"], hi = axis[key + "max"];
    if (lo != null && hi != null) return [lo, hi];
    let mn = Infinity, mx = -Infinity;
    for (const s of axis.traces || []) {
        const arr = s[key] || (key === "x" ? s.y.map((_, i) => i) : s.y);
        for (const v of arr) { if (v < mn) mn = v; if (v > mx) mx = v; }
    }
    if (!isFinite(mn)) return [0, 1];
    if (mn === mx) { mn -= 0.5; mx += 0.5; }
    const pad = (mx - mn) * 0.05;
    return [lo ?? mn - pad, hi ?? mx + pad];
}

function drawPlot(id) {
    const rt = runtime[id];
    if (!rt || !rt.canvas) return;
    const canvas = rt.canvas, dpr = window.devicePixelRatio || 1;
    const cw = canvas.parentElement.clientWidth, ch = canvas.parentElement.clientHeight;
    if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) {
        canvas.width = Math.round(cw * dpr);
        canvas.height = Math.round(ch * dpr);
        canvas.style.width = cw + "px";
        canvas.style.height = ch + "px";
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    if (!rt.frame) return;
    const axes = rt.frame.axes, ah = ch / axes.length;
    rt.geom = [];
    axes.forEach((axis, i) => {
        const out = {view: view3d(rt, i)};
        drawAxis(ctx, dragged(rt, axis, i), rt.images[i], 0, i * ah, cw, ah, out);
        rt.geom[i] = out.geom;
    });
    drawHover(ctx, id, rt);
}

// crosshair with the frequency / level under the pointer, and the edges of a band being dragged
function drawHover(ctx, id, rt) {
    if (!rt.hover && !rt.drag) return;
    const i = rt.drag ? rt.drag.i : axisAt(rt, rt.hover_y);
    const g = rt.geom[i], axis = i >= 0 && rt.frame.axes[i];
    if (!g || !axis || g.is3d) return;
    const px = Math.min(Math.max(rt.hover_x, g.x0), g.x0 + g.w), py = Math.min(Math.max(rt.hover_y, g.y0), g.y0 + g.h);
    const inside = rt.hover_x >= g.x0 && rt.hover_x <= g.x0 + g.w && rt.hover_y >= g.y0 && rt.hover_y <= g.y0 + g.h;
    if (!inside && !rt.drag) return;
    const fx = fmtXOf(axis, g.xmin, g.xmax, true), x = dataX(g, px);
    const xname = axis.xfmt === "freq" ? "f" : axis.xfmt === "time" ? "t" : "x";
    const lines = [];
    const unit = (state.plots[id] && state.plots[id].settings.unit) || "";
    if (rt.drag && rt.drag.mode !== "marker" && rt.drag.mode !== "level") {
        const lo = Math.min(rt.drag.lo, rt.drag.hi), hi = Math.max(rt.drag.lo, rt.drag.hi);
        lines.push(`${fx(lo)} – ${fx(hi)}`, `width ${fx(hi - lo)}   center ${fx((lo + hi) / 2)}`);
    } else {
        lines.push(`${xname} ${fx(x)}`);
    }
    if (!g.isImage) {
        const y = g.ymax - ((py - g.y0) / g.h) * (g.ymax - g.ymin);
        const fy = axis.yfmt === "log10" ? fmtLog10 : axis.yfmt === "freq" ? fmtHzFull : axis.yfmt === "logfreq" ? (v) => fmtHzFull(10 ** v)
            : (v) => v.toFixed(2);
        lines.push(`cursor ${fy(y)} ${unit}`.trim());
        const t = (axis.traces || [])[axis.traces.length - 1]; // the plot's own trace is the last one
        if (t && t.y.length && !rt.drag) {
            const k = t.x ? t.x.reduce((b, v, n) => (Math.abs(v - x) < Math.abs(t.x[b] - x) ? n : b), 0)
                          : Math.round(((x - g.xmin) / (g.xmax - g.xmin)) * t.y.length);
            lines.push(`trace  ${fy(t.y[Math.min(Math.max(k, 0), t.y.length - 1)])} ${unit}`.trim());
        }
    }
    ctx.save();
    ctx.beginPath(); ctx.rect(g.x0, g.y0, g.w, g.h); ctx.clip();
    ctx.strokeStyle = "rgba(255,255,255,0.35)"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(px, g.y0); ctx.lineTo(px, g.y0 + g.h);
    if (!g.isImage) { ctx.moveTo(g.x0, py); ctx.lineTo(g.x0 + g.w, py); }
    ctx.stroke(); ctx.setLineDash([]);
    ctx.font = "12px sans-serif"; ctx.textAlign = "right";
    const wText = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 12, hText = lines.length * 15 + 6;
    const bx = g.x0 + g.w - wText - 4, by = g.y0 + 4;
    ctx.fillStyle = "rgba(10,10,10,0.8)"; ctx.fillRect(bx, by, wText, hText);
    ctx.strokeStyle = "rgba(255,255,255,0.25)"; ctx.strokeRect(bx, by, wText, hText);
    ctx.fillStyle = "#eee";
    lines.forEach((l, n) => ctx.fillText(l, bx + wText - 6, by + 16 + n * 15));
    ctx.restore();
}

function drawTraces(ctx, axis, xOf, yOf) {
    for (const s of axis.traces) {
        const n = s.y.length;
        ctx.strokeStyle = ctx.fillStyle = s.color;
        ctx.globalAlpha = s.alpha ?? 1;
        ctx.lineWidth = s.width ?? 1.5;
        if (s.kind === "scatter") {
            for (let i = 0; i < n; i++) ctx.fillRect(xOf(s.x[i]) - 1, yOf(s.y[i]) - 1, 2, 2);
            continue;
        }
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
            const x = xOf(traceX(s, i, axis));
            const y = yOf(s.y[i]);
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }
}

function drawAxis(ctx, axis, image, ox, oy, W, H, out = {}) {
    if (axis.projection === "3d") return drawAxis3d(ctx, axis, ox, oy, W, H, out);
    let x0 = ox + MARGIN.l, y0 = oy + MARGIN.t, w = W - MARGIN.l - MARGIN.r, h = H - MARGIN.t - MARGIN.b;
    if (w <= 10 || h <= 10) return;
    const isImage = !!axis.image;
    const bar = isImage && axis.ymin != null && w > 160; // a level axis image gets a color bar (relative hits)
    if (bar) w -= 44;
    if (axis.square) {
        const side = Math.min(w, h);
        x0 += (w - side) / 2; w = side; h = side;
    }
    const [xmin, xmax] = isImage ? [axis.xmin ?? 0, axis.xmax ?? 1] : extent(axis, "x");
    const [ymin, ymax] = isImage && axis.ymin == null ? [0, 1] : extent(axis, "y");
    const xlog = !!axis.xlog && xmin > 0 && xmax > xmin;
    const lx0 = xlog ? Math.log10(xmin) : 0, lspan = xlog ? Math.log10(xmax) - lx0 : 1;
    const xOf = xlog ? (v) => x0 + ((Math.log10(v) - lx0) / lspan) * w : (v) => x0 + ((v - xmin) / (xmax - xmin)) * w;
    const yOf = (v) => y0 + (1 - (v - ymin) / (ymax - ymin)) * h;
    const fmtX = fmtXOf(axis, xmin, xmax, false);
    const fmtY = axis.yfmt === "log10" ? fmtLog10 : axis.yfmt === "freq" ? fmtHz : axis.yfmt === "logfreq" ? (v) => fmtHz(10 ** v) : fmtNum;
    const labelY = !isImage || axis.ymin != null; // a scrolling image has no y values to label
    out.geom = {x0, y0, w, h, xmin, xmax, ymin, ymax, isImage, xlog};

    ctx.font = "12px sans-serif";
    ctx.lineWidth = 1;
    ctx.strokeStyle = GRID;
    ctx.fillStyle = TEXT;
    const ny = labelY ? Math.max(2, Math.min(10, Math.floor(h / 28))) : 0, nx = 4; // fewer y divisions on short plots
    for (let i = 0; i <= ny; i++) {
        const y = y0 + (i / ny) * h;
        ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
        ctx.textAlign = "right";
        ctx.fillText(fmtY(ymax - (i / ny) * (ymax - ymin)), x0 - 6, y + 4);
    }
    if (xlog) { // a line at every decade (labeled) and its 2..9 (faint)
        for (let d = Math.floor(lx0); d <= Math.ceil(lx0 + lspan); d++) {
            for (let m = 1; m < 10; m++) {
                const v = m * 10 ** d;
                if (v < xmin || v > xmax) continue;
                const x = xOf(v);
                ctx.globalAlpha = m === 1 ? 1 : 0.35;
                ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y0 + h); ctx.stroke();
                ctx.globalAlpha = 1;
                if (m === 1) { ctx.textAlign = "center"; ctx.fillText(fmtX(v), x, y0 + h + 16); }
            }
        }
    } else {
        for (let i = 0; i <= nx; i++) {
            const x = x0 + (i / nx) * w;
            if (!isImage) { ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y0 + h); ctx.stroke(); }
            ctx.textAlign = i === 0 ? "left" : i === nx ? "right" : "center";
            ctx.fillText(fmtX(xmin + (i / nx) * (xmax - xmin)), x, y0 + h + 16);
        }
    }
    ctx.strokeRect(x0, y0, w, h);

    if (isImage) {
        if (image) {
            ctx.imageSmoothingEnabled = false;
            ctx.drawImage(image.canvas, x0, y0, w, h);
        }
        if (bar) drawColorbar(ctx, axis.image.cmap, x0 + w + 8, y0, 10, h);
        drawBands(ctx, axis, xOf, isImage && axis.ymin == null ? null : yOf, x0, y0, w, h);
        if (axis.ymin != null && axis.traces.length) { // traces over a level axis image (persistence)
            ctx.save();
            ctx.beginPath(); ctx.rect(x0, y0, w, h); ctx.clip();
            drawTraces(ctx, axis, xOf, yOf);
            ctx.restore();
        }
        drawMarkers(ctx, axis, xOf, yOf, x0, y0, w, h);
        drawOffscale(ctx, axis, x0, y0, w, h);
        return;
    }
    ctx.save();
    ctx.beginPath(); ctx.rect(x0, y0, w, h); ctx.clip();
    drawBands(ctx, axis, xOf, isImage && axis.ymin == null ? null : yOf, x0, y0, w, h);
    drawTraces(ctx, axis, xOf, yOf);
    ctx.restore(); // also restores globalAlpha
    drawMarkers(ctx, axis, xOf, yOf, x0, y0, w, h);
    drawOffscale(ctx, axis, x0, y0, w, h);
}

// the color map of a level image, 0 (bottom) to 1 (top): the share of the brightest pixel's hits, as tk's color bar
function drawColorbar(ctx, cmap, x, y, w, h) {
    const lut = lutFor(cmap);
    for (let r = 0; r < h; r++) {
        const c = lut[Math.round((1 - r / Math.max(h - 1, 1)) * 255)];
        ctx.fillStyle = `rgb(${c & 255},${(c >> 8) & 255},${(c >> 16) & 255})`;
        ctx.fillRect(x, y + r, w, 1);
    }
    ctx.strokeStyle = GRID; ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = TEXT; ctx.textAlign = "left"; ctx.font = "11px sans-serif";
    for (const v of [0, 0.5, 1]) ctx.fillText(v.toFixed(1), x + w + 3, y + (1 - v) * (h - 8) + 8);
}

// --- 3d axes: an orthographic view of the data box, turned by dragging, a double click resets it --- //
const VIEW3D = {az: -60, el: 28};
function view3d(rt, i) {
    rt.view3d = rt.view3d || {};
    return rt.view3d[i] || (rt.view3d[i] = {...VIEW3D});
}

// data (x, y, z) -> pixel [px, py] in the box (x0, y0, w, h), for the axis' ranges, box aspect and the view
function projector(axis, view, x0, y0, w, h) {
    const r = {x: extent(axis, "x"), y: extent(axis, "y"), z: extent(axis, "z")};
    const asp = axis.aspect || [1, 1, 1], am = Math.max(...asp);
    const a = asp.map((v) => v / am);
    const az = view.az * Math.PI / 180, el = view.el * Math.PI / 180;
    const ca = Math.cos(az), sa = Math.sin(az), ce = Math.cos(el), se = Math.sin(el);
    const unit = (x, y, z) => [((x - r.x[0]) / (r.x[1] - r.x[0]) - 0.5) * a[0], ((y - r.y[0]) / (r.y[1] - r.y[0]) - 0.5) * a[1],
                                ((z - r.z[0]) / (r.z[1] - r.z[0]) - 0.5) * a[2]];
    const raw = (x, y, z) => { // screen x, screen y (up), depth (away from the viewer)
        const [X, Y, Z] = unit(x, y, z);
        const depth = X * sa + Y * ca;
        return [X * ca - Y * sa, Z * ce + depth * se, depth * ce - Z * se];
    };
    const corners = [];
    for (const x of r.x) for (const y of r.y) for (const z of r.z) corners.push([x, y, z]);
    const pr = corners.map((c) => raw(...c));
    const sx = pr.map((p) => p[0]), sy = pr.map((p) => p[1]);
    const lo = [Math.min(...sx), Math.min(...sy)], hi = [Math.max(...sx), Math.max(...sy)];
    const s = 0.86 * Math.min(w / (hi[0] - lo[0] || 1), h / (hi[1] - lo[1] || 1));
    const cx = x0 + w / 2 - s * (lo[0] + hi[0]) / 2, cy = y0 + h / 2 + s * (lo[1] + hi[1]) / 2;
    const P = (x, y, z) => { const p = raw(x, y, z); return [cx + s * p[0], cy - s * p[1]]; };
    P.depth = (x, y, z) => raw(x, y, z)[2];
    P.r = r;
    return P;
}

function drawAxis3d(ctx, axis, ox, oy, W, H, out) {
    const x0 = ox + 8, y0 = oy + 8, w = W - 16, h = H - 16;
    if (w <= 20 || h <= 20) return;
    const P = projector(axis, out.view || VIEW3D, x0, y0, w, h), r = P.r;
    out.geom = {x0: ox, y0: oy, w: W, h: H, is3d: true};
    const line = (a, b) => { const p = P(...a), q = P(...b); ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(q[0], q[1]); ctx.stroke(); };
    ctx.lineWidth = 1; ctx.strokeStyle = GRID; ctx.font = "11px sans-serif"; ctx.fillStyle = TEXT;
    // the floor's grid and the box: the edges at the back are drawn, the ones in front would hide the data
    const [xa, xb] = r.x, [ya, yb] = r.y, [za, zb] = r.z;
    for (let k = 0; k <= 4; k++) {
        const x = xa + (k / 4) * (xb - xa), y = ya + (k / 4) * (yb - ya);
        line([x, ya, za], [x, yb, za]); line([xa, y, za], [xb, y, za]);
    }
    const backX = P.depth(xa, 0, 0) > P.depth(xb, 0, 0) ? xa : xb, backY = P.depth(0, ya, 0) > P.depth(0, yb, 0) ? ya : yb;
    for (let k = 0; k <= 4; k++) { // the two back walls
        const z = za + (k / 4) * (zb - za);
        line([backX, ya, z], [backX, yb, z]); line([xa, backY, z], [xb, backY, z]);
    }
    line([backX, backY, za], [backX, backY, zb]);
    // labels on the front edges of the floor, z up the back corner
    const frontY = backY === ya ? yb : ya, frontX = backX === xa ? xb : xa;
    const fx = fmtXOf(axis, xa, xb, false), fy = axis.yfmt === "freq" ? fmtHz : fmtNum;
    ctx.textAlign = "center";
    for (let k = 0; k <= 4; k += 2) {
        const x = xa + (k / 4) * (xb - xa), p = P(x, frontY, za);
        ctx.fillText(fx(x), p[0], p[1] + 14);
        const y = ya + (k / 4) * (yb - ya), q = P(frontX, y, za);
        ctx.fillText(fy(y), q[0] + (q[0] > x0 + w / 2 ? 18 : -18), q[1] + 12);
        const z = za + (k / 4) * (zb - za), t = P(backX, backY, z);
        ctx.fillText(fmtNum(z), t[0] + (t[0] > x0 + w / 2 ? 22 : -22), t[1] + 4);
    }
    if (axis.ylabel) { const q = P(frontX, (ya + yb) / 2, za); ctx.fillText(axis.ylabel, q[0] + (q[0] > x0 + w / 2 ? 40 : -40), q[1] + 26); }
    if (axis.surface) drawSurface(ctx, axis.surface, P);
    // bands lie on the floor
    for (const b of axis.bands || []) {
        const lo = Math.max(b.lo, xa), hi = Math.min(b.hi, xb), yl = b.ylo ?? ya, yh = b.yhi ?? yb;
        if (hi <= lo) continue;
        const pts = [[lo, yl], [hi, yl], [hi, yh], [lo, yh]].map(([x, y]) => P(x, y, za));
        ctx.globalAlpha = b.alpha ?? 0.15; ctx.fillStyle = b.color;
        ctx.beginPath(); pts.forEach((p, k) => (k ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath(); ctx.fill();
        ctx.globalAlpha = 1;
    }
    for (const s of axis.traces || []) {
        const n = s.y.length;
        ctx.strokeStyle = ctx.fillStyle = s.color; ctx.globalAlpha = s.alpha ?? 1; ctx.lineWidth = s.width ?? 1.5;
        const z = (k) => (s.z ? s.z[k] : za);
        if (s.kind === "scatter") {
            for (let k = 0; k < n; k++) { const p = P(traceX(s, k, axis), s.y[k], z(k)); ctx.fillRect(p[0] - 1, p[1] - 1, 2, 2); }
        } else {
            ctx.beginPath();
            for (let k = 0; k < n; k++) { const p = P(traceX(s, k, axis), s.y[k], z(k)); if (k) ctx.lineTo(p[0], p[1]); else ctx.moveTo(p[0], p[1]); }
            ctx.stroke();
        }
        ctx.globalAlpha = 1;
    }
    ctx.fillStyle = TEXT; ctx.textAlign = "left";
    ctx.fillText("drag to turn", ox + 6, oy + H - 6);
}

// a height field as a surface of quads colored by height, drawn back to front so the near ones cover the far ones
function drawSurface(ctx, sf, P) {
    const rows = sf.rows, cols = sf.cols, b = sf.bytes;
    if (!b || rows < 2 || cols < 2) return;
    const [xa, xb] = P.r.x, [ya, yb] = P.r.y, [za, zb] = P.r.z;
    const pts = new Float32Array(rows * cols * 2);
    for (let r = 0; r < rows; r++) {
        const y = ya + (r / (rows - 1)) * (yb - ya);
        for (let c = 0; c < cols; c++) {
            const p = P(xa + (c / (cols - 1)) * (xb - xa), y, za + (b[r * cols + c] / 255) * (zb - za));
            pts[(r * cols + c) * 2] = p[0]; pts[(r * cols + c) * 2 + 1] = p[1];
        }
    }
    const lut = lutFor(sf.cmap), css = new Array(256);
    for (let v = 0; v < 256; v++) { const c = lut[v]; css[v] = `rgb(${c & 255},${(c >> 8) & 255},${(c >> 16) & 255})`; }
    const rowsBack = P.depth(0, yb, 0) > P.depth(0, ya, 0), colsBack = P.depth(xb, 0, 0) > P.depth(xa, 0, 0);
    const order = (n, back) => (back ? [...Array(n - 1).keys()].reverse() : [...Array(n - 1).keys()]);
    const rOrder = order(rows, rowsBack), cOrder = order(cols, colsBack);
    ctx.lineWidth = 0.6;
    for (const r of rOrder) {
        for (const c of cOrder) {
            const k = [r * cols + c, r * cols + c + 1, (r + 1) * cols + c + 1, (r + 1) * cols + c];
            const v = Math.max(b[k[0]], b[k[1]], b[k[2]], b[k[3]]);
            ctx.fillStyle = ctx.strokeStyle = css[v]; // the edge in the same color hides the seams between quads
            ctx.beginPath();
            ctx.moveTo(pts[k[0] * 2], pts[k[0] * 2 + 1]);
            for (let q = 1; q < 4; q++) ctx.lineTo(pts[k[q] * 2], pts[k[q] * 2 + 1]);
            ctx.closePath(); ctx.fill(); ctx.stroke();
        }
    }
}

// shaded x spans (channels), or boxes when they have a y span (`yOf` null: no levels, y spans are ignored), under the traces
function drawBands(ctx, axis, xOf, yOf, x0, y0, w, h) {
    ctx.save();
    ctx.beginPath(); ctx.rect(x0, y0, w, h); ctx.clip();
    ctx.textAlign = "left";
    for (const b of axis.bands || []) {
        const a = Math.max(xOf(b.lo), x0), z = Math.min(xOf(b.hi), x0 + w);
        const boxed = yOf && (b.ylo != null || b.yhi != null);
        const top = boxed && b.yhi != null ? Math.max(yOf(b.yhi), y0) : y0;
        const btm = boxed && b.ylo != null ? Math.min(yOf(b.ylo), y0 + h) : y0 + h;
        if (z <= a || btm <= top) continue;
        ctx.globalAlpha = b.alpha ?? 0.15;
        ctx.fillStyle = b.color;
        ctx.fillRect(a, top, z - a, btm - top);
        ctx.globalAlpha = 1;
        if (b.edit || boxed) { // a band the mouse can move / resize, or a box: show its edges
            ctx.strokeStyle = b.color; ctx.globalAlpha = 0.7; ctx.lineWidth = 1;
            if (boxed) ctx.strokeRect(a, top, z - a, btm - top);
            else { ctx.beginPath(); ctx.moveTo(a, top); ctx.lineTo(a, btm); ctx.moveTo(z, top); ctx.lineTo(z, btm); ctx.stroke(); }
            ctx.globalAlpha = 1;
        }
        if (b.label) { ctx.fillStyle = b.color; ctx.fillText(b.label, a + 3, btm - 5); }
    }
    ctx.restore();
}

// markers: a triangle on the point with its label, a vertical line, or a dashed level line (not on an image without levels)
function drawMarkers(ctx, axis, xOf, yOf, x0, y0, w, h) {
    ctx.save();
    ctx.beginPath(); ctx.rect(x0, y0, w, h); ctx.clip();
    ctx.lineWidth = 1;
    ctx.textAlign = "left";
    for (const m of axis.markers || []) {
        ctx.strokeStyle = ctx.fillStyle = m.color;
        if (m.kind === "hline") {
            const y = yOf(m.y);
            if ((axis.image && axis.ymin == null) || y < y0 || y > y0 + h) continue;
            ctx.setLineDash([6, 3]);
            ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
            ctx.setLineDash([]);
            if (m.label) { ctx.textAlign = "right"; ctx.fillText(m.label, x0 + w - 3, y - 3); ctx.textAlign = "left"; }
            continue;
        }
        const x = xOf(m.x);
        if (x < x0 || x > x0 + w) continue;
        if (m.kind === "vline") {
            ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y0 + h); ctx.stroke();
            if (m.label) ctx.fillText(m.label, x + 3, y0 + 12);
            continue;
        }
        const y = Math.min(Math.max(yOf(m.y), y0 + 26), y0 + h);
        ctx.beginPath(); ctx.moveTo(x, y - 2); ctx.lineTo(x - 5, y - 11); ctx.lineTo(x + 5, y - 11); ctx.closePath(); ctx.fill();
        if (m.label) ctx.fillText(m.label, Math.min(x + 6, x0 + w - 24), y - 13);
    }
    ctx.restore();
}

// the data is entirely above / below the y range
function drawOffscale(ctx, axis, x0, y0, w, h) {
    if (!axis.offscale) return;
    ctx.fillStyle = "#e6d84a";
    ctx.textAlign = "left";
    ctx.fillText(axis.offscale === "above" ? "▲ above range" : "▼ below range", x0 + 8, axis.offscale === "above" ? y0 + 16 : y0 + h - 8);
}

// --- inputs --- //
let seeking = false;
function bindInputs() {
    document.querySelectorAll("[data-set]").forEach((e) => {
        const key = e.dataset.set;
        if (e.tagName === "SELECT") e.addEventListener("change", () => set(key, e.value));
        else {
            e.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { set(key, e.value); e.blur(); } });
            e.addEventListener("blur", () => state && applyState(state));
        }
    });
    $("btn-start").onclick = () => cmd("start");
    $("btn-stop").onclick = () => cmd("stop");
    $("btn-reset").onclick = () => cmd("reset");
    $("btn-prev").onclick = () => cmd("prev");
    $("btn-next").onclick = () => cmd("next");
    const add = $("sel-add-plot");
    add.onchange = () => { if (add.value) plotOp("add", {name: add.value}); add.value = ""; };
    const layoutFile = $("in-layout");
    $("btn-layout-load").onclick = () => layoutFile.click();
    layoutFile.onchange = async () => {
        const file = layoutFile.files[0];
        layoutFile.value = ""; // picking the same file again still loads it
        if (file) plotOp("layout_load", {text: await file.text()});
    };
    const sld = $("sld-samp");
    sld.addEventListener("pointerdown", () => (seeking = true));
    sld.addEventListener("change", () => { seeking = false; set("samp", sld.value); });
    $("btn-claim").onclick = () => cmd(state.radio.control === "controlling" ? "release" : "claim");
    $("btn-reconnect").onclick = () => cmd("reconnect");
    $("sel-antenna").addEventListener("change", (e) => set("antenna", e.target.value));
    $("sel-radio").addEventListener("focus", loadRadios); // fresh when it is about to be used
    $("sel-radio").addEventListener("change", (e) => { if (e.target.value) set("device", e.target.value); });
    $("btn-open").onclick = () => openDialog(null);
    $("btn-dir-go").onclick = () => browse($("in-dir").value);
    $("in-dir").onkeydown = (ev) => { if (ev.key === "Enter") { ev.preventDefault(); browse($("in-dir").value); } };
}

// --- file picker --- //
async function browse(path) {
    const err = $("lbl-dir-error");
    err.textContent = "";
    const res = await fetch("/api/fs" + (path ? `?path=${encodeURIComponent(path)}` : ""));
    if (!res.ok) { err.textContent = (await res.json()).detail; return; }
    const d = await res.json();
    $("in-dir").value = d.path;
    const item = (label, cls, onclick) => el("li", {className: cls, textContent: label, onclick});
    const sep = d.path.includes("\\") ? "\\" : "/";
    const join = (n) => d.path.replace(/[\\/]$/, "") + sep + n;
    $("lst-files").replaceChildren(
        ...(d.parent ? [item("📁 ..", "dir", () => browse(d.parent))] : []),
        ...d.entries.map((e) => e.dir
            ? item(`📁 ${e.name}`, "dir", () => browse(join(e.name)))
            : item(`${e.name}  (${fmtSize(e.size)})`, "file", () => { set("path", join(e.name)); $("dlg-file").close(); })));
}

function fmtSize(n) {
    for (const [u, s] of [[1e9, "GB"], [1e6, "MB"], [1e3, "kB"]]) if (n >= u) return `${(n / u).toFixed(1)} ${s}`;
    return `${n} B`;
}

function openDialog(path) {
    $("dlg-file").showModal();
    browse(path);
}

document.addEventListener("DOMContentLoaded", () => {
    bindInputs();
    connect();
});
