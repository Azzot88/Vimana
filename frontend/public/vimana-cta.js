/* T3.10 — статические лендинги DealVault (dealvault-v3b.html / dealvault-v4b.html).
 *
 * Зачем отдельный файл, а не inline <script>:
 * прод-CSP (nginx/default.conf, T_SEC.2) содержит `script-src 'self'` без
 * 'unsafe-inline' — любой инлайновый скрипт на этих страницах будет заблокирован
 * браузером молча. Скрипт обязан лежать отдельным same-origin файлом.
 *
 * Делает две вещи:
 *   1. CTA-кнопка: «Получить инвайт» → /register для гостя,
 *      «Зайти в аккаунт» → /dashboard для того, у кого уже есть сессия.
 *   2. Полоса прогресса чтения (#progress), если она есть на странице.
 *
 * ВАЖНО про определение аккаунта.
 * Задача была сформулирована как «проверь по кукам», но в Vimana auth-куки нет:
 * backend отдаёт JWT в теле ответа (`Token.access_token`, api/auth.py), а фронт
 * кладёт его в `localStorage['token']` (stores/auth.ts, api/client.ts) и шлёт
 * заголовком `Authorization: Bearer`. Ни один Set-Cookie в auth-потоке не
 * выставляется. Поэтому порядок такой: сначала всё же куки — на случай, если
 * cookie-сессия появится позже и чтобы этот файл не пришлось трогать; затем
 * реальный сегодняшний признак — localStorage. Обе страницы отдаются с того же
 * origin, что и SPA, так что localStorage тот же самый.
 *
 * Протухший токен не считается сессией: exp внутри JWT проверяется, иначе
 * пользователь ушёл бы по «Зайти в аккаунт» и получил редирект на /login.
 */
(function () {
  'use strict';

  var COOKIE_NAMES = ['token', 'access_token', 'vimana_token'];

  function fromCookie() {
    var jar = document.cookie ? document.cookie.split(';') : [];
    for (var i = 0; i < jar.length; i++) {
      var eq = jar[i].indexOf('=');
      if (eq < 0) continue;
      var name = jar[i].slice(0, eq).trim();
      if (COOKIE_NAMES.indexOf(name) === -1) continue;
      var value = jar[i].slice(eq + 1).trim();
      if (value) return decodeURIComponent(value);
    }
    return null;
  }

  function fromStorage() {
    // Приватный режим / отключённое хранилище кидают на доступе — не падаем.
    try {
      return window.localStorage.getItem('token');
    } catch (e) {
      return null;
    }
  }

  /** true, если это JWT с истёкшим exp. Нераспознанное считаем живым:
   *  формат мог поменяться, и лучше показать кнопку кабинета, чем сломать её. */
  function expired(token) {
    var parts = token.split('.');
    if (parts.length !== 3) return false;
    try {
      var b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      while (b64.length % 4) b64 += '=';
      var exp = JSON.parse(atob(b64)).exp;
      if (typeof exp !== 'number') return false;
      return exp * 1000 <= Date.now();
    } catch (e) {
      return false;
    }
  }

  function hasAccount() {
    var token = fromCookie() || fromStorage();
    return !!token && !expired(token);
  }

  /* Кнопок на странице может быть несколько: у пятых версий CTA продублирован
   * в шапке, в герое и в финальной секции. Переключаем все разом — иначе
   * залогиненный увидит «Зайти в аккаунт» внизу и «Получить инвайт» сверху. */
  function applyCta() {
    var nodes = document.querySelectorAll('[data-auth-label]');
    if (!nodes.length || !hasAccount()) return; // гостю оставляем разметку как есть
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var label = el.getAttribute('data-auth-label');
      var href = el.getAttribute('data-auth-href');
      if (label) el.textContent = label;
      if (href) el.setAttribute('href', href);
    }
  }

  function mountProgress() {
    var bar = document.getElementById('progress');
    if (!bar) return;
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      bar.style.display = 'none';
      return;
    }
    var ticking = false;
    function update() {
      var h = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + '%';
      ticking = false;
    }
    window.addEventListener('scroll', function () {
      if (!ticking) {
        window.requestAnimationFrame(update);
        ticking = true;
      }
    }, { passive: true });
    update();
  }

  function init() {
    applyCta();
    mountProgress();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
