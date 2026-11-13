/* Scriptul aplicației (fără inline: CSP strict). Alpine este varianta CSP: componentele se înregistrează aici
 * prin Alpine.data și se folosesc în șabloane doar cu nume (x-data="notificari"), nu cu expresii inline. */
(function () {
  'use strict';

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () { /* fără SW: aplicația merge oricum */ });
    });
  }

  function jetonCsrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : '';
  }

  function cheieBinara(b64url) {
    var umplut = (b64url + '==='.slice((b64url.length + 3) % 4)).replace(/-/g, '+').replace(/_/g, '/');
    var brut = atob(umplut);
    var out = new Uint8Array(brut.length);
    for (var i = 0; i < brut.length; i++) out[i] = brut.charCodeAt(i);
    return out;
  }

  function trimite(cale, corp) {
    return fetch(cale, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': jetonCsrf() },
      body: JSON.stringify(corp || {}),
    });
  }

  document.addEventListener('alpine:init', function () {
    Alpine.data('notificari', function () {
      return {
        suportat: false,
        configurat: false,
        abonat: false,
        ocupat: false,
        mesaj: '',
        cheiePublica: '',
        get blocatAbonare() { return !(this.suportat && this.configurat && !this.abonat && !this.ocupat); },
        get blocatDezabonare() { return !(this.abonat && !this.ocupat); },
        get blocatTest() { return !(this.abonat && !this.ocupat); },
        get nesuportat() { return !this.suportat; },
        async init() {
          this.cheiePublica = this.$el.dataset.vapid || '';
          this.configurat = this.cheiePublica !== '';
          this.suportat = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
          if (!this.suportat) return;
          try {
            var reg = await navigator.serviceWorker.ready;
            this.abonat = (await reg.pushManager.getSubscription()) !== null;
          } catch (e) { this.mesaj = 'Nu am putut citi starea notificărilor.'; }
        },
        async aboneaza() {
          this.ocupat = true; this.mesaj = '';
          try {
            var permisiune = await Notification.requestPermission();
            if (permisiune !== 'granted') { this.mesaj = 'Permisiunea pentru notificări nu a fost dată.'; return; }
            var reg = await navigator.serviceWorker.ready;
            var sub = await reg.pushManager.subscribe({
              userVisibleOnly: true,
              applicationServerKey: cheieBinara(this.cheiePublica),
            });
            var r = await trimite('/notificari/aboneaza', sub.toJSON());
            if (!r.ok) { await sub.unsubscribe(); this.mesaj = 'Serverul a refuzat abonarea (' + r.status + ').'; return; }
            this.abonat = true; this.mesaj = 'Notificările sunt pornite pe acest dispozitiv.';
          } catch (e) { this.mesaj = 'Abonarea nu a reușit.'; } finally { this.ocupat = false; }
        },
        async dezaboneaza() {
          this.ocupat = true; this.mesaj = '';
          try {
            var reg = await navigator.serviceWorker.ready;
            var sub = await reg.pushManager.getSubscription();
            if (sub) { await trimite('/notificari/dezaboneaza', { endpoint: sub.endpoint }); await sub.unsubscribe(); }
            this.abonat = false; this.mesaj = 'Notificările au fost oprite pe acest dispozitiv.';
          } catch (e) { this.mesaj = 'Dezabonarea nu a reușit.'; } finally { this.ocupat = false; }
        },
        async testeaza() {
          this.ocupat = true; this.mesaj = '';
          try {
            var r = await trimite('/notificari/test', {});
            var d = await r.json().catch(function () { return {}; });
            this.mesaj = r.ok ? 'Notificare de test trimisă (' + d.trimise + ').' : (d.detail || 'Trimiterea a eșuat.');
          } catch (e) { this.mesaj = 'Trimiterea a eșuat.'; } finally { this.ocupat = false; }
        },
      };
    });
  });

  // Publicarea asistată (F6.6): „Partajează” deschide meniul de partajare al telefonului cu textul pachetului; fără
  // Web Share, textul se copiază în clipboard. A doua atingere este alegerea aplicației.
  document.addEventListener('click', function (ev) {
    var b = ev.target && ev.target.closest ? ev.target.closest('[data-partajeaza]') : null;
    if (!b) return;
    var sursa = document.getElementById(b.getAttribute('data-partajeaza'));
    var stare = document.querySelector('[data-stare-partajare="' + b.getAttribute('data-partajeaza') + '"]');
    if (!sursa) return;
    var text = sursa.value || sursa.textContent || '';
    function spune(m) { if (stare) stare.textContent = m; }
    function copiaza() {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { spune('Text copiat. Deschide aplicația și lipește-l.'); },
          function () { spune('Copierea a eșuat: selectează textul și copiază-l.'); });
      } else { sursa.select && sursa.select(); spune('Selectează textul și copiază-l.'); }
    }
    if (navigator.share) {
      navigator.share({ title: b.getAttribute('data-titlu') || '', text: text }).catch(function () { copiaza(); });
    } else { copiaza(); }
  });
})();
