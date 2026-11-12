# Biblioteci JS vendorizate

Fără CDN și fără lanț de build. Fișierele sunt luate din pachetul npm indicat (`npm pack <pachet>@<versiune>`),
copiate neschimbate din `dist/`. Sumele SHA-256 sunt verificate de `tests/unit/test_panou_static.py`.

| Fișier | Pachet npm | Versiune | Licență | SHA-256 |
| --- | --- | --- | --- | --- |
| `htmx-2.0.4.min.js` | `htmx.org` (`dist/htmx.min.js`) | 2.0.4 | 0BSD | `e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447` |
| `alpine-csp-3.14.9.min.js` | `@alpinejs/csp` (`dist/cdn.min.js`) | 3.14.9 | MIT | `820bc9503874024057da244dc30c21301548329eb9a00e7937e91c4d3908b273` |

Note: htmx se folosește cu `allowEval=false` și fără stiluri injectate (vezi `<meta name="htmx-config">` din `base.html`);
Alpine este varianta CSP (fără `eval`), deci componentele se înregistrează în `static/js/app.js` prin `Alpine.data`.
Actualizare: `npm pack`, copiere, schimbarea numelui, a versiunii și a sumei aici și în test, în același commit.
