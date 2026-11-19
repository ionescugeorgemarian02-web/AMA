// Randatorul clipurilor animate (app/media/animatie.py): o pagină HTML cu animații CSS, „înghețată” cadru cu cadru
// în Chromium (Playwright) și salvată ca JPEG; FFmpeg le codează. Determinist: aceleași date -> aceleași cadre.
// Intrare: JSON pe stdin (vezi animatie.py). Ieșire: <iesire>/f00000.jpg ...
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

// ESM nu citește NODE_PATH: rezolvăm Playwright ca un `require` obișnuit (global sau local)
const { chromium } = createRequire(import.meta.url)(process.env.AMA_PLAYWRIGHT || "playwright");

const c = JSON.parse(readFileSync(0, "utf8"));
const font = (f) => `data:font/woff2;base64,${readFileSync(`${c.fonturi}/${f}`).toString("base64")}`;
const esc = (s) => s.replace(/[&<>"]/g, (x) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[x]);

// generator pseudo-aleator cu sămânță (particulele)
let st = c.samanta * 2654435761 % 4294967296 || 1;
const rnd = () => ((st = (st * 1664525 + 1013904223) % 4294967296) / 4294967296);

const k = c.culori;
const v = c.varianta % 4;
const unghi = [160, 200, 135, 225][v];
const iconStanga = v % 2 === 1;
const boabe = c.particula
  .replace(/stroke="currentColor"/, `stroke="${k.accent}"`)
  .replace(/width="24"/, 'width="100%"').replace(/height="24"/, 'height="100%"');
const icon = c.icon
  .replace(/stroke="currentColor"/, `stroke="${k.text}"`)
  .replace(/stroke-width="2"/, 'stroke-width="1.6"')
  .replace(/width="24"/, 'width="100%"').replace(/height="24"/, 'height="100%"');

let particule = "";
for (let i = 0; i < 14; i++) {
  const x = Math.round(rnd() * 100), m = Math.round(40 + rnd() * 70), d = (6 + rnd() * 6).toFixed(2);
  const del = (-rnd() * 10).toFixed(2), rot = Math.round(rnd() * 360), o = (0.10 + rnd() * 0.18).toFixed(2);
  particule += `<div class="p" style="left:${x}%;width:${m}px;height:${m}px;opacity:${o};animation-duration:${d}s;animation-delay:${del}s;--r:${rot}deg">${boabe}</div>`;
}
const cuvinte = esc(c.titlu).split(/\s+/).map((w, i) =>
  `<span class="w" style="animation-delay:${(0.35 + i * 0.09).toFixed(2)}s">${w}</span>`).join(" ");
const marime = c.titlu.length > 48 ? 92 : c.titlu.length > 28 ? 112 : 136;

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:M;font-weight:800;src:url(${font("montserrat-latin-ext-800-normal.woff2")})}
@font-face{font-family:M;font-weight:800;src:url(${font("montserrat-latin-800-normal.woff2")});unicode-range:U+0000-00FF}
@font-face{font-family:M;font-weight:600;src:url(${font("montserrat-latin-ext-600-normal.woff2")})}
@font-face{font-family:M;font-weight:600;src:url(${font("montserrat-latin-600-normal.woff2")});unicode-range:U+0000-00FF}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:${c.latime}px;height:${c.inaltime}px;overflow:hidden}
body{font-family:M,sans-serif;color:${k.text};background:linear-gradient(${unghi}deg,${k.fundal} 0%,${k.fundal2} 100%);position:relative}
.bg{position:absolute;inset:-20%;background:radial-gradient(circle at 30% 30%,${k.accent}55 0,transparent 38%),radial-gradient(circle at 75% 70%,${k.fundal2}cc 0,transparent 45%);animation:deriva ${c.durata * 1.6}s ease-in-out infinite alternate}
@keyframes deriva{from{transform:translate(-4%,-3%) scale(1)}to{transform:translate(4%,3%) scale(1.12)}}
.p{position:absolute;top:100%;animation:urca linear infinite}
@keyframes urca{from{transform:translateY(0) rotate(var(--r))}to{transform:translateY(-${c.inaltime + 300}px) rotate(calc(var(--r) + 220deg))}}
.vin{position:absolute;inset:0;background:radial-gradient(ellipse at center,transparent 45%,rgba(0,0,0,.45) 100%)}
.cont{position:absolute;left:8%;right:8%;top:${Math.round(c.inaltime * 0.12)}px;height:${Math.round(c.inaltime * 0.55)}px;display:flex;flex-direction:column;justify-content:center;align-items:${iconStanga ? "flex-start" : "center"};text-align:${iconStanga ? "left" : "center"}}
.eti{font-weight:600;font-size:34px;letter-spacing:.32em;text-transform:uppercase;color:${k.accent};opacity:0;animation:apare .6s .1s ease-out forwards}
.ins{width:300px;height:300px;border-radius:50%;background:${k.accent};display:flex;align-items:center;justify-content:center;margin:56px 0;box-shadow:0 30px 80px rgba(0,0,0,.35),inset 0 0 0 10px rgba(255,255,255,.12);transform:scale(0);animation:pop .7s .15s cubic-bezier(.2,1.6,.4,1) forwards,pluteste 3.2s .9s ease-in-out infinite alternate}
.ins div{width:56%;height:56%}
@keyframes pop{to{transform:scale(1)}}
@keyframes pluteste{from{translate:0 0}to{translate:0 -18px}}
h1{font-weight:800;font-size:${marime}px;line-height:1.08;letter-spacing:-.01em;text-shadow:0 8px 30px rgba(0,0,0,.35)}
.w{display:inline-block;opacity:0;transform:translateY(60px);animation:urcaw .55s cubic-bezier(.2,.9,.3,1.2) forwards}
@keyframes urcaw{to{opacity:1;transform:none}}
.bara{height:14px;border-radius:7px;background:${k.accent};width:0;margin-top:44px;animation:creste .8s .9s cubic-bezier(.3,.9,.3,1) forwards}
@keyframes creste{to{width:${iconStanga ? 320 : 260}px}}
@keyframes apare{to{opacity:1}}
</style></head><body><div class="bg"></div>${particule}<div class="vin"></div>
<div class="cont"><div class="eti">${esc(c.eticheta)}</div><div class="ins"><div>${icon}</div></div><h1>${cuvinte}</h1><div class="bara"></div></div>
</body></html>`;

const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: c.latime, height: c.inaltime } });
await p.setContent(html);
await p.evaluate(() => document.fonts.ready);
const n = Math.round(c.durata * c.fps);
for (let i = 0; i < n; i++) {
  const t = (i * 1000) / c.fps;
  await p.evaluate((t) => document.getAnimations().forEach((a) => { a.pause(); a.currentTime = t; }), t);
  await p.screenshot({ path: `${c.iesire}/f${String(i).padStart(5, "0")}.jpg`, type: "jpeg", quality: 90 });
}
await b.close();
