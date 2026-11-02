"use strict";
// pyspecan web view: all logic lives in the server, this only draws and forwards input.

const $ = (id) => document.getElementById(id);
const COLORS = {psd: "#e6d84a", max: "#d9534f", min: "#5b9bd5", grid: "rgba(255,255,255,0.15)", text: "#bbb"};
const SI = [[1e9, "G"], [1e6, "M"], [1e3, "k"]];

let ws = null;
let state = null;
let frame = null;
let seeking = false;

function fmtHz(v) {
    for (const [scale, suffix] of SI) {
        if (Math.abs(v) >= scale) return `${(v / scale).toFixed(3).replace(/\.?0+$/, "")}${suffix}`;
    }
    return `${v.toFixed(0)}`;
}

// --- connection --- //
function send(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}
const cmd = (c) => send({type: "cmd", cmd: c});
const set = (key, value) => send({type: "set", key, value});

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
        else if (msg.type === "frame") {
            frame = msg.data;
            $("lbl-ptime").textContent = `${(frame.ptime * 1000).toFixed(1)} ms`;
            draw();
        } else if (msg.type === "error") $("lbl-message").textContent = msg.data;
    };
}

function setConnected(ok) {
    const el = $("connection-status");
    el.className = `status ${ok ? "connected" : "disconnected"}`;
    el.title = ok ? "connected" : "disconnected";
}

// --- state -> DOM --- //
function setValue(el, value) {
    if (document.activeElement === el) return; // don't clobber what the user is typing
    if (el.type === "checkbox") el.checked = !!value;
    else el.value = value;
}

function fillSelect(el, options) {
    if (el.options.length === options.length) return;
    el.replaceChildren(...options.map((o) => new Option(o, o)));
}

function applyState(s) {
    state = s;
    fillSelect($("sel-window"), s.windows);
    setValue($("sel-window"), s.plot.window);
    setValue($("in-fs"), s.fs);
    setValue($("in-cf"), s.cf);
    setValue($("in-nfft"), s.nfft_exp);
    setValue($("in-show"), s.show);
    setValue($("in-ref"), s.plot.ref_level);
    setValue($("in-scale"), s.plot.scale_div);
    setValue($("in-vbw"), s.plot.vbw);
    setValue($("chk-max"), s.plot.show_max);
    setValue($("chk-min"), s.plot.show_min);
    setValue($("chk-enabled"), s.plot.enabled);
    $("lbl-block").textContent = s.block_size;
    $("lbl-message").textContent = s.message;
    $("btn-start").disabled = s.playing;
    $("btn-stop").disabled = !s.playing;

    const isFile = s.max_samp !== undefined;
    document.querySelectorAll(".file-only").forEach((el) => (el.hidden = !isFile));
    if (isFile) {
        fillSelect($("sel-fmt"), s.formats);
        setValue($("sel-fmt"), s.fmt);
        setValue($("in-path"), s.path === "None" ? "" : s.path);
        $("lbl-time").textContent = `${s.time_cur} / ${s.time_tot}`;
        const sld = $("sld-samp");
        sld.max = s.max_samp;
        if (!seeking) sld.value = s.cur_samp;
    }
    draw();
}

function bindInputs() {
    document.querySelectorAll("[data-set]").forEach((el) => {
        const key = el.dataset.set;
        const isSelect = el.tagName === "SELECT";
        if (el.type === "checkbox") el.addEventListener("change", () => set(key, el.checked));
        else if (isSelect) el.addEventListener("change", () => set(key, el.value));
        else el.addEventListener("keydown", (ev) => {
            if (ev.key === "Enter") { set(key, el.value); el.blur(); }
        });
        if (!isSelect && el.type !== "checkbox") el.addEventListener("blur", () => state && applyState(state));
    });
    $("btn-start").onclick = () => cmd("start");
    $("btn-stop").onclick = () => cmd("stop");
    $("btn-reset").onclick = () => cmd("reset");
    $("btn-prev").onclick = () => cmd("prev");
    $("btn-next").onclick = () => cmd("next");
    const sld = $("sld-samp");
    sld.addEventListener("pointerdown", () => (seeking = true));
    sld.addEventListener("pointerup", () => (seeking = false));
    sld.addEventListener("change", () => set("samp", sld.value));
}

// --- drawing --- //
function drawLine(ctx, data, color, x0, w, yOf) {
    if (!data || data.length < 2) return;
    ctx.strokeStyle = color;
    ctx.beginPath();
    for (let i = 0; i < data.length; i++) {
        const x = x0 + (i / (data.length - 1)) * w;
        const y = yOf(data[i]);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
}

function draw() {
    const canvas = $("psd");
    const dpr = window.devicePixelRatio || 1;
    const cw = canvas.clientWidth, ch = canvas.clientHeight;
    if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) {
        canvas.width = Math.round(cw * dpr);
        canvas.height = Math.round(ch * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    if (!frame) return;

    const m = {l: 55, r: 15, t: 10, b: 28};
    const w = cw - m.l - m.r, h = ch - m.t - m.b;
    if (w <= 0 || h <= 0) return;
    const {y_top, y_btm} = frame;
    const yOf = (v) => m.t + ((y_top - Math.max(Math.min(v, y_top + 1e3), y_btm - 1e3)) / (y_top - y_btm)) * h;

    ctx.font = "12px sans-serif";
    ctx.fillStyle = COLORS.text;
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 10; i++) { // y grid
        const y = m.t + (i / 10) * h;
        ctx.beginPath(); ctx.moveTo(m.l, y); ctx.lineTo(m.l + w, y); ctx.stroke();
        ctx.textAlign = "right";
        ctx.fillText((y_top - (i / 10) * (y_top - y_btm)).toFixed(0), m.l - 6, y + 4);
    }
    const fmin = frame.cf - frame.fs / 2, fmax = frame.cf + frame.fs / 2;
    for (let i = 0; i <= 4; i++) { // x grid
        const x = m.l + (i / 4) * w;
        ctx.beginPath(); ctx.moveTo(x, m.t); ctx.lineTo(x, m.t + h); ctx.stroke();
        ctx.textAlign = i === 0 ? "left" : i === 4 ? "right" : "center";
        ctx.fillText(fmtHz(fmin + (i / 4) * (fmax - fmin)), x, ch - 8);
    }

    ctx.save();
    ctx.beginPath(); ctx.rect(m.l, m.t, w, h); ctx.clip();
    ctx.lineWidth = 1.5;
    drawLine(ctx, frame.max, COLORS.max, m.l, w, yOf);
    drawLine(ctx, frame.min, COLORS.min, m.l, w, yOf);
    drawLine(ctx, frame.psd, COLORS.psd, m.l, w, yOf);
    ctx.restore();
}

document.addEventListener("DOMContentLoaded", () => {
    bindInputs();
    window.addEventListener("resize", draw);
    connect();
});
