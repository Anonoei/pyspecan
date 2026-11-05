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

function fmtHz(v) {
    for (const [scale, suffix] of SI) {
        if (Math.abs(v) >= scale) return `${(v / scale).toFixed(3).replace(/\.?0+$/, "")}${suffix}`;
    }
    return v.toFixed(0);
}
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
        else if (msg.type === "frame") applyFrame(msg.data);
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

function fillSelect(el, options) {
    if (el.options.length === options.length && options.every((o, i) => el.options[i].value === o)) return;
    el.replaceChildren(...options.map((o) => new Option(o, o)));
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
    fillSelect($("sel-plot-type"), s.plot_types);
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
    applyStatus(s);
    syncPlots(s);
}

// --- plots --- //
function syncPlots(s) {
    const sig = JSON.stringify([s.layout, Object.entries(s.plots).map(([id, p]) => [id, p.name])]);
    if (sig !== layoutSig) {
        layoutSig = sig;
        buildPlots(s);
    }
    for (const [id, p] of Object.entries(s.plots)) updatePlotControls(id, p);
}

function el(tag, props = {}, ...children) {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...children);
    return e;
}

function buildPlots(s) {
    for (const id of Object.keys(runtime)) if (!(id in s.plots)) { delete runtime[id]; settingsOpen.delete(id); }
    const panels = $("panels");
    panels.replaceChildren(...s.layout.map((row, r) =>
        el("div", {className: "plot-row"}, ...row.map((id) => buildPlot(id, s.plots[id], r)))));
}

function buildPlot(id, p, row) {
    const rt = runtime[id] || (runtime[id] = {frame: null, images: {}});
    const typeSel = el("select", {title: "plot type"});
    typeSel.replaceChildren(...state.plot_types.map((t) => new Option(t, t)));
    typeSel.value = p.name;
    typeSel.onchange = () => { rt.frame = null; rt.images = {}; plotOp("type", {id, name: typeSel.value}); };

    const pause = el("button", {id: `pause-${id}`, onclick: () => plotOp("set", {id, key: "enabled", value: !state.plots[id].settings.enabled})});
    const gear = el("button", {textContent: "⚙", title: "settings", onclick: () => {
        settingsOpen.has(id) ? settingsOpen.delete(id) : settingsOpen.add(id);
        $(`settings-${id}`).hidden = !settingsOpen.has(id);
    }});
    const addCol = el("button", {textContent: "+", title: "add a plot to this row", onclick: () => plotOp("add", {name: $("sel-plot-type").value, row})});
    const del = el("button", {textContent: "✕", title: "remove plot", onclick: () => plotOp("del", {id})});
    const ptime = el("span", {id: `ptime-${id}`, className: "muted"});

    const settings = el("div", {id: `settings-${id}`, className: "plot-settings", hidden: !settingsOpen.has(id)},
        ...p.fields.map((f) => buildField(id, f)));
    rt.canvas = el("canvas");
    const container = el("div", {className: "plot", id: `plot-${id}`},
        el("div", {className: "plot-header"}, typeSel, ptime, el("span", {className: "right"}, pause, gear, addCol, del)),
        settings, el("div", {className: "canvas-box"}, rt.canvas));
    new ResizeObserver(() => drawPlot(id)).observe(rt.canvas.parentElement);
    return container;
}

function buildField(id, f) {
    const input = f.kind === "select"
        ? el("select", {}, ...f.options.map((o) => new Option(o, o)))
        : el("input", {type: f.kind === "check" ? "checkbox" : f.kind === "number" ? "number" : "text",
                       placeholder: f.hint || "", min: f.min ?? "", max: f.max ?? "", step: f.step ?? "any"});
    input.id = `f-${id}-${f.key}`;
    const send_ = (v) => plotOp("set", {id, key: f.key, value: v});
    if (f.kind === "check") input.onchange = () => send_(input.checked);
    else if (f.kind === "select") input.onchange = () => send_(input.value);
    else {
        input.onkeydown = (ev) => { if (ev.key === "Enter") { send_(input.value); input.blur(); } };
        input.onblur = () => { for (const [i, p] of Object.entries(state.plots)) updatePlotControls(i, p); };
    }
    return el("div", {className: "control-group"}, el("label", {htmlFor: input.id, textContent: f.label}), input);
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
        if (pt) pt.textContent = `${frame.title ? frame.title + "  " : ""}${(frame.ptime * 1000).toFixed(1)} ms`;
        frame.axes.forEach((axis, i) => { if (axis.image) applyImage(rt, i, axis.image); });
        drawPlot(id);
    }
}

// images arrive either whole, or as the newest rows of a scrolling history (newest on top)
function applyImage(rt, i, im) {
    const bytes = Uint8Array.from(atob(im.data), (c) => c.charCodeAt(0));
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
    axes.forEach((axis, i) => drawAxis(ctx, axis, rt.images[i], 0, i * ah, cw, ah));
}

function drawAxis(ctx, axis, image, ox, oy, W, H) {
    let x0 = ox + MARGIN.l, y0 = oy + MARGIN.t, w = W - MARGIN.l - MARGIN.r, h = H - MARGIN.t - MARGIN.b;
    if (w <= 10 || h <= 10) return;
    if (axis.square) {
        const side = Math.min(w, h);
        x0 += (w - side) / 2; w = side; h = side;
    }
    const isImage = !!axis.image;
    const [xmin, xmax] = isImage ? [axis.xmin ?? 0, axis.xmax ?? 1] : extent(axis, "x");
    const [ymin, ymax] = isImage && axis.ymin == null ? [0, 1] : extent(axis, "y");
    const xOf = (v) => x0 + ((v - xmin) / (xmax - xmin)) * w;
    const yOf = (v) => y0 + (1 - (v - ymin) / (ymax - ymin)) * h;
    const fmtX = axis.xfmt === "freq" ? fmtHz : fmtNum;
    const labelY = !isImage || axis.ymin != null; // a scrolling image has no y values to label

    ctx.font = "12px sans-serif";
    ctx.lineWidth = 1;
    ctx.strokeStyle = GRID;
    ctx.fillStyle = TEXT;
    const ny = labelY ? Math.max(2, Math.min(10, Math.floor(h / 28))) : 0, nx = 4; // fewer y divisions on short plots
    for (let i = 0; i <= ny; i++) {
        const y = y0 + (i / ny) * h;
        ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + w, y); ctx.stroke();
        ctx.textAlign = "right";
        ctx.fillText(fmtNum(ymax - (i / ny) * (ymax - ymin)), x0 - 6, y + 4);
    }
    for (let i = 0; i <= nx; i++) {
        const x = x0 + (i / nx) * w;
        if (!isImage) { ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y0 + h); ctx.stroke(); }
        ctx.textAlign = i === 0 ? "left" : i === nx ? "right" : "center";
        ctx.fillText(fmtX(xmin + (i / nx) * (xmax - xmin)), x, y0 + h + 16);
    }
    ctx.strokeRect(x0, y0, w, h);

    if (isImage) {
        if (image) {
            ctx.imageSmoothingEnabled = false;
            ctx.drawImage(image.canvas, x0, y0, w, h);
        }
        drawOffscale(ctx, axis, x0, y0, w, h);
        return;
    }
    ctx.save();
    ctx.beginPath(); ctx.rect(x0, y0, w, h); ctx.clip();
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
            const x = s.x ? xOf(s.x[i]) : x0 + (i / (n - 1)) * w;
            const y = yOf(s.y[i]);
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
    }
    ctx.restore(); // also restores globalAlpha
    drawOffscale(ctx, axis, x0, y0, w, h);
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
    $("btn-add-plot").onclick = () => plotOp("add", {name: $("sel-plot-type").value});
    const sld = $("sld-samp");
    sld.addEventListener("pointerdown", () => (seeking = true));
    sld.addEventListener("change", () => { seeking = false; set("samp", sld.value); });
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
