/* NewsSphere – progressive-enhancement client script.
 * Replaces the React runtime: theme, navbar, search overlay, bookmark/like buttons, load-more,
 * forms, reveal animations, carousel, share bar and the admin tools. Pages are rendered by Flask/Jinja;
 * this file only adds behaviour. No build step, no dependencies. */
(function () {
  'use strict';

  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var isAuth = document.body.getAttribute('data-auth') === 'true';

  /* ------------------------------------------------------------------ helpers */
  var ICONS = {};
  try { ICONS = JSON.parse($('#icon-data').textContent); } catch (e) { /* ignore */ }
  function svg(name, cls) {
    return '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide ' + (cls || '') + '" aria-hidden="true">' + (ICONS[name] || '') + '</svg>';
  }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function debounce(fn, ms) { var t; return function () { var a = arguments, c = this; clearTimeout(t); t = setTimeout(function () { fn.apply(c, a); }, ms); }; }
  var compact = function (n) { try { return new Intl.NumberFormat(undefined, { notation: 'compact' }).format(n || 0); } catch (e) { return String(n || 0); } };
  var fmtDate = function (d) { return new Date(d).toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }); };
  var fmtTime = function (d) { return new Date(d).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }); };

  function api(method, url, body) {
    var opts = { method: method, credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' } };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    return fetch(url, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) { var err = new Error(data.message || 'Something went wrong. Please try again.'); err.data = data; err.status = res.status; throw err; }
        return data;
      });
    }, function () { var e = new Error('Cannot reach the server.'); e.data = {}; throw e; });
  }
  function errMsg(e) { return (e && e.message) || 'Something went wrong. Please try again.'; }

  /* ------------------------------------------------------------------ toast + flash */
  var toastTimer;
  function toast(message, type) {
    var root = $('#toast-root'); if (!root) return;
    type = type || 'info';
    var icon = type === 'error' ? 'circle-alert' : type === 'info' ? 'info' : 'circle-check';
    var cls = type === 'error' ? 'bg-accent' : 'bg-ink !text-paper';
    root.innerHTML = '<div role="status" class="toast-in pointer-events-auto inline-flex items-center gap-2.5 rounded-sm px-4 py-3 text-sm font-semibold text-white shadow-xl ' + cls + '">' + svg(icon, 'h-4 w-4') + '<span>' + esc(message) + '</span></div>';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      var el = root.firstChild; if (!el) return;
      el.classList.remove('toast-in'); el.classList.add('toast-out');
      setTimeout(function () { root.innerHTML = ''; }, 180);
    }, 3200);
  }
  function flash(message, type) { try { sessionStorage.setItem('ns-flash', JSON.stringify({ message: message, type: type || 'info' })); } catch (e) { /* ignore */ } }
  try {
    var f = sessionStorage.getItem('ns-flash');
    if (f) { sessionStorage.removeItem('ns-flash'); f = JSON.parse(f); setTimeout(function () { toast(f.message, f.type); }, 250); }
  } catch (e) { /* ignore */ }

  function setBusy(btn, busy) {
    if (!btn) return;
    btn.disabled = !!busy;
    var s = $('[data-spin]', btn); if (s) s.hidden = !busy;
  }

  /* ------------------------------------------------------------------ theme */
  function setTheme(dark) {
    document.documentElement.classList.toggle('dark', dark);
    try { localStorage.setItem('ns-theme', dark ? 'dark' : 'light'); } catch (e) { /* ignore */ }
  }
  /* ------------------------------------------------------------------ overlay helpers */
  function show(el) { if (el) { el.hidden = false; } }
  function hide(el) { if (el) { el.hidden = true; } }

  /* ------------------------------------------------------------------ navbar */
  var header = $('#site-header');
  if (header) {
    var onScroll = function () { header.classList.toggle('is-scrolled', window.scrollY > 8); };
    onScroll(); window.addEventListener('scroll', onScroll, { passive: true });
  }

  var drawer = $('[data-drawer]'), drawerBackdrop = $('[data-drawer-backdrop]');
  function openDrawer() { if (!drawer) return; show(drawerBackdrop); drawer.classList.add('is-open'); drawer.setAttribute('aria-hidden', 'false'); document.body.style.overflow = 'hidden'; }
  function closeDrawer() { if (!drawer) return; drawer.classList.remove('is-open'); drawer.setAttribute('aria-hidden', 'true'); hide(drawerBackdrop); document.body.style.overflow = ''; }

  var search = $('[data-search]'), searchInput = $('[data-search-input]');
  function openSearch() { if (!search) return; show(search); setTimeout(function () { searchInput && searchInput.focus(); }, 80); }
  function closeSearch() { if (!search) return; hide(search); if (searchInput) searchInput.value = ''; renderSuggestions([], '', false); }

  function closeAccount() { var m = $('[data-account-menu]'); if (m && !m.hidden) { hide(m); $('[data-account-btn]').setAttribute('aria-expanded', 'false'); } }

  /* ------------------------------------------------------------------ search overlay suggestions */
  var suggestSeq = 0;
  function renderSuggestions(list, q, searched) {
    var box = $('[data-search-results]'), browse = $('[data-search-browse]');
    if (!box) return;
    if (list.length) {
      browse.hidden = true;
      box.innerHTML = '<ul>' + list.map(function (a) {
        return '<li><a href="/article/' + a._id + '" class="flex items-center gap-3 px-5 py-3 hover:bg-soft"><div class="min-w-0 flex-1"><div class="kicker">' + esc(catLabel(a.category)) + '</div><div class="truncate text-[15px] font-semibold">' + esc(a.title) + '</div></div>' + svg('arrow-up-right', 'h-4 w-4 shrink-0 text-muted') + '</a></li>';
      }).join('') + '<li class="border-t border-line"><a href="/search?q=' + encodeURIComponent(q) + '" class="block w-full px-5 py-3 text-left text-sm font-semibold text-accent hover:bg-soft">See all results for “' + esc(q) + '”</a></li></ul>';
    } else if (searched) {
      browse.hidden = true;
      box.innerHTML = '<p class="px-5 py-8 text-center text-sm text-muted">No quick matches. Press Enter to search everything.</p>';
    } else {
      box.innerHTML = ''; browse.hidden = false;
    }
  }
  var CAT_LABELS = {};
  try { $$('footer a[href^="/category/"]').forEach(function (a) { CAT_LABELS[a.getAttribute('href').split('/').pop()] = a.textContent.trim(); }); } catch (e) { /* ignore */ }
  function catLabel(slug) { return CAT_LABELS[slug] || (slug ? slug.charAt(0).toUpperCase() + slug.slice(1) : ''); }

  var suggest = debounce(function () {
    var q = searchInput.value.trim();
    var seq = ++suggestSeq;
    if (q.length < 2) { renderSuggestions([], q, false); setSpin(false); return; }
    setSpin(true);
    api('GET', '/api/articles/search?limit=5&q=' + encodeURIComponent(q)).then(function (d) {
      if (seq === suggestSeq) renderSuggestions(d.articles || [], q, true);
    }).catch(function () { if (seq === suggestSeq) renderSuggestions([], q, true); }).then(function () { if (seq === suggestSeq) setSpin(false); });
  }, 300);
  function setSpin(on) { var s = $('[data-search-spinner]'); if (s) s.hidden = !on; }
  if (searchInput) searchInput.addEventListener('input', suggest);

  /* ------------------------------------------------------------------ guest prompt */
  var authModal = $('[data-auth-modal]');
  function requireAuth() {
    if (isAuth) return true;
    if (authModal) {
      var next = location.pathname + location.search;
      $$('[data-auth-link]', authModal).forEach(function (a) {
        var base = a.getAttribute('href').split('?')[0];
        a.setAttribute('href', next && next !== '/' ? base + '?next=' + encodeURIComponent(next) : base);
      });
      show(authModal);
    }
    return false;
  }

  /* ------------------------------------------------------------------ bookmark / like */
  function paintBookmark(id, saved) {
    $$('[data-bookmark="' + id + '"]').forEach(function (b) {
      b.setAttribute('aria-pressed', saved ? 'true' : 'false');
      b.setAttribute('aria-label', saved ? 'Remove bookmark' : 'Save article');
      b.title = saved ? 'Remove bookmark' : 'Save for later';
      b.classList.toggle('text-accent', saved); b.classList.toggle('text-muted', !saved);
      var s = $('svg', b); if (s) s.setAttribute('fill', saved ? 'currentColor' : 'none');
      var ic = $('[data-bm-icon]', b); if (ic) { ic.classList.remove('pop'); void ic.offsetWidth; ic.classList.add('pop'); }
      var l = $('[data-bm-label]', b); if (l) l.textContent = saved ? 'Saved' : 'Save';
    });
  }
  function toggleBookmark(btn) {
    if (!requireAuth()) return;
    var id = btn.getAttribute('data-bookmark');
    var was = btn.getAttribute('aria-pressed') === 'true';
    paintBookmark(id, !was);
    api(was ? 'DELETE' : 'POST', '/api/bookmarks/' + id).then(function () {
      toast(was ? 'Removed from bookmarks' : 'Saved to bookmarks');
      var holder = btn.closest('[data-removable]');
      if (holder && was) {
        var card = btn.closest('article');
        if (card) {
          card.style.transition = 'opacity .25s, transform .25s'; card.style.opacity = '0'; card.style.transform = 'scale(.97)';
          setTimeout(function () { card.remove(); if (!$('article', holder)) location.reload(); }, 260);
        }
      }
    }).catch(function (e) { paintBookmark(id, was); toast(errMsg(e), 'error'); });
  }

  function paintLike(id, liked, count) {
    $$('[data-like="' + id + '"]').forEach(function (b) {
      b.setAttribute('aria-pressed', liked ? 'true' : 'false');
      b.setAttribute('aria-label', liked ? 'Unlike article' : 'Like article');
      ['border-accent/40', 'bg-accent/10', 'text-accent'].forEach(function (c) { b.classList.toggle(c, liked); });
      ['border-line', 'text-ink', 'hover:bg-soft'].forEach(function (c) { b.classList.toggle(c, !liked); });
      var s = $('svg', b); if (s) s.setAttribute('fill', liked ? 'currentColor' : 'none');
      var ic = $('[data-like-icon]', b); if (ic) { ic.classList.remove('pop'); void ic.offsetWidth; ic.classList.add('pop'); }
      if (count != null) { b.setAttribute('data-count', count); $('[data-like-count]', b).textContent = compact(count); }
      if (liked) { var w = ic && ic.parentNode; if (w) { var r = document.createElement('span'); r.className = 'like-burst pointer-events-none absolute inset-0 rounded-full border-2 border-accent'; w.appendChild(r); setTimeout(function () { r.remove(); }, 600); } }
    });
  }
  function toggleLike(btn) {
    if (!requireAuth()) return;
    var id = btn.getAttribute('data-like');
    var was = btn.getAttribute('aria-pressed') === 'true';
    var cnt = parseInt(btn.getAttribute('data-count'), 10) || 0;
    paintLike(id, !was, Math.max(0, cnt + (was ? -1 : 1)));
    api(was ? 'DELETE' : 'POST', '/api/articles/' + id + '/like').then(function (d) { paintLike(id, !was, d.likes); })
      .catch(function (e) { paintLike(id, was, cnt); toast(errMsg(e), 'error'); });
  }

  /* ------------------------------------------------------------------ images + reveal */
  function initImages(root) {
    $$('img[data-smart]', root).forEach(function (img) {
      if (img.__ns) return; img.__ns = true;
      var wrap = img.parentNode, shimmer = $('[data-shimmer]', wrap), fb = $('[data-fallback]', wrap);
      var ok = function () { img.classList.add('is-loaded'); if (shimmer) shimmer.remove(); };
      var bad = function () { img.remove(); if (shimmer) shimmer.remove(); if (fb) fb.classList.remove('hidden'); };
      if (img.complete) { img.naturalWidth > 0 ? ok() : bad(); } else { img.addEventListener('load', ok); img.addEventListener('error', bad); }
    });
  }
  var io = 'IntersectionObserver' in window ? new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('is-in'); io.unobserve(e.target); } });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 }) : null;
  function initReveal(root) {
    $$('.reveal', root).forEach(function (el) {
      if (el.__rv) return; el.__rv = true;
      if (io) io.observe(el); else el.classList.add('is-in');
    });
  }
  function initDates(root) {
    $$('[data-local-date]', root).forEach(function (el) { el.textContent = fmtDate(new Date()); });
    $$('[data-datetime]', root).forEach(function (el) { var v = el.getAttribute('data-datetime'); if (v) el.textContent = fmtDate(v) + ', ' + fmtTime(v); });
    $$('[data-local-time]', root).forEach(function (el) { var v = el.getAttribute('data-local-time'); if (v) el.textContent = fmtTime(v); });
    $$('[data-year]', root).forEach(function (el) { el.textContent = new Date().getFullYear(); });
  }

  /* ------------------------------------------------------------------ load more */
  function initLoadMore() {
    $$('[data-loadmore]').forEach(function (box) {
      var btn = $('[data-loadmore-btn]', box); if (!btn) return;
      btn.addEventListener('click', function () {
        var target = $(box.getAttribute('data-target')); if (!target) return;
        var url = box.getAttribute('data-url');
        btn.disabled = true; var label = btn.textContent;
        btn.innerHTML = svg('loader-circle', 'h-4 w-4 animate-spin') + ' Loading…';
        fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } }).then(function (r) { if (!r.ok) throw new Error('fail'); return r.json(); }).then(function (d) {
          var tmp = document.createElement('div'); tmp.innerHTML = d.html;
          var added = $$('article', tmp).length;
          while (tmp.firstChild) target.appendChild(tmp.firstChild);
          initImages(target); initReveal(target);
          var shown = (parseInt(box.getAttribute('data-shown'), 10) || 0) + added;
          box.setAttribute('data-shown', shown);
          if (d.hasMore) {
            var u = new URL(url, location.origin); u.searchParams.set('page', (parseInt(u.searchParams.get('page'), 10) || 1) + 1);
            box.setAttribute('data-url', u.pathname + u.search);
            btn.disabled = false; btn.textContent = label;
            var c = $('[data-loadmore-count]', box); if (c) c.textContent = 'Showing ' + shown + ' of ' + d.total;
          } else {
            var p = document.createElement('p'); p.className = 'mt-10 text-center text-sm text-muted'; p.textContent = 'You’re all caught up — ' + shown + ' stories shown.';
            box.replaceWith(p);
          }
        }).catch(function () { btn.disabled = false; btn.textContent = label; toast('Could not load more stories', 'error'); });
      });
    });
  }

  /* ------------------------------------------------------------------ carousel */
  $$('[data-carousel]').forEach(function (c) {
    var track = $('[data-carousel-track]', c);
    var go = function (d) { track.scrollBy({ left: d * 620, behavior: 'smooth' }); };
    var p = $('[data-carousel-prev]', c), n = $('[data-carousel-next]', c);
    p && p.addEventListener('click', function () { go(-1); });
    n && n.addEventListener('click', function () { go(1); });
  });

  /* ------------------------------------------------------------------ reading progress + share */
  var bar = $('[data-progress]');
  if (bar) {
    var cur = 0, target = 0, raf = null;
    var step = function () { cur += (target - cur) * 0.18; if (Math.abs(target - cur) < 0.001) cur = target; bar.style.transform = 'scaleX(' + cur + ')'; raf = cur === target ? null : requestAnimationFrame(step); };
    var upd = function () { var h = document.documentElement.scrollHeight - window.innerHeight; target = h > 0 ? Math.min(1, window.scrollY / h) : 0; if (!raf) raf = requestAnimationFrame(step); };
    window.addEventListener('scroll', upd, { passive: true }); upd();
  }
  $$('[data-share]').forEach(function (s) {
    var title = s.getAttribute('data-title'), url = location.href, enc = encodeURIComponent;
    var set = function (sel, href) { var a = $(sel, s); if (a) a.href = href; };
    set('[data-share-x]', 'https://twitter.com/intent/tweet?text=' + enc(title) + '&url=' + enc(url));
    set('[data-share-fb]', 'https://www.facebook.com/sharer/sharer.php?u=' + enc(url));
    set('[data-share-in]', 'https://www.linkedin.com/sharing/share-offsite/?url=' + enc(url));
    set('[data-share-mail]', 'mailto:?subject=' + enc(title) + '&body=' + enc(url));
    var copy = function () {
      var done = function () {
        var a = $('[data-copy-icon]', s), b = $('[data-copied-icon]', s); a.hidden = true; b.hidden = false;
        toast('Link copied to clipboard'); setTimeout(function () { a.hidden = false; b.hidden = true; }, 2000);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(done, function () { toast('Could not copy the link', 'error'); });
      else toast('Could not copy the link', 'error');
    };
    $('[data-share-copy]', s).addEventListener('click', copy);
    $('[data-share-native]', s).addEventListener('click', function () { if (navigator.share) navigator.share({ title: title, url: url }).catch(function () {}); else copy(); });
  });

  /* ------------------------------------------------------------------ newsletter */
  $$('[data-newsletter]').forEach(function (box) {
    var form = $('[data-nl-form]', box), done = $('[data-nl-done]', box), err = $('[data-nl-err]', box), btn = $('[data-nl-btn]', box);
    form.addEventListener('submit', function (e) {
      e.preventDefault(); err.hidden = true;
      var email = form.email.value.trim();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) { err.textContent = 'Please enter a valid email address.'; err.hidden = false; return; }
      setBusy(btn, true);
      api('POST', '/api/newsletter', { email: email }).then(function (d) {
        $('[data-nl-msg]', done).textContent = d.alreadySubscribed ? 'You are already on the list — thank you!' : 'You are in! Watch your inbox for the morning briefing.';
        form.hidden = true; done.hidden = false; form.reset();
      }).catch(function (x) { err.textContent = errMsg(x); err.hidden = false; }).then(function () { setBusy(btn, false); });
    });
  });

  /* ------------------------------------------------------------------ auth forms */
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  function showErrors(form, errors) {
    $$('[data-err]', form).forEach(function (p) { var m = errors[p.getAttribute('data-err')]; p.textContent = m || ''; p.classList.toggle('hidden', !m); });
  }
  function formError(form, msg) { var p = $('[data-form-error]', form); if (!p) return; p.textContent = msg || ''; p.hidden = !msg; }

  $$('[data-auth-form]').forEach(function (form) {
    var kind = form.getAttribute('data-auth-form'), btn = $('[data-submit]', form);
    if (kind === 'register') {
      var bars = $$('[data-strength] span', form);
      form.password.addEventListener('input', function () {
        var v = form.password.value;
        var s = Math.min(4, (v.length >= 8) + /[A-Z]/.test(v) + /\d/.test(v) + /[^A-Za-z0-9]/.test(v));
        bars.forEach(function (b, i) {
          b.className = 'h-1 flex-1 rounded-full transition-colors ' + (i < s ? (s < 3 ? 'bg-amber-500' : 'bg-emerald-500') : 'bg-line');
        });
      });
    }
    form.addEventListener('submit', function (e) {
      e.preventDefault(); formError(form, '');
      var body;
      if (kind === 'register') {
        var v = { name: form.name.value, email: form.email.value, password: form.password.value }, er = {};
        if (v.name.trim().length < 2) er.name = 'Please enter your name.';
        if (!EMAIL_RE.test(v.email.trim())) er.email = 'Enter a valid email address.';
        if (v.password.length < 8) er.password = 'Use at least 8 characters.';
        else if (!/[A-Za-z]/.test(v.password) || !/\d/.test(v.password)) er.password = 'Include at least one letter and one number.';
        showErrors(form, er); if (Object.keys(er).length) return;
        body = { name: v.name.trim(), email: v.email.trim(), password: v.password };
      } else {
        body = { email: form.email.value, password: form.password.value };
      }
      setBusy(btn, true);
      api('POST', '/api/auth/' + kind, body).then(function (d) {
        var next = form.getAttribute('data-next') || '/';
        location.replace(kind === 'register' ? '/onboarding' : (d.user && d.user.onboarded ? next : '/onboarding'));
      }).catch(function (x) { formError(form, errMsg(x)); setBusy(btn, false); });
    });
  });

  /* ------------------------------------------------------------------ interest picker (onboarding + profile) */
  function pickerValue(p) { return $$('[data-interest][aria-pressed="true"]', p).map(function (b) { return b.getAttribute('data-interest'); }); }
  function paintInterest(b, on) {
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    ['border-accent', 'bg-accent/10', 'text-accent'].forEach(function (c) { b.classList.toggle(c, on); });
    ['border-line', 'hover:border-ink/40'].forEach(function (c) { b.classList.toggle(c, !on); });
    var chk = $('[data-interest-check]', b);
    chk.className = 'grid h-6 w-6 place-items-center rounded-full border-2 transition ' + (on ? 'border-accent bg-accent text-white' : 'border-line');
    chk.innerHTML = on ? '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" class="h-3.5 w-3.5"><path d="M20 6 9 17l-5-5"/></svg>' : '';
  }
  $$('[data-interest-picker]').forEach(function (p) {
    p.addEventListener('click', function (e) {
      var b = e.target.closest('[data-interest]'); if (!b) return;
      paintInterest(b, b.getAttribute('aria-pressed') !== 'true');
      p.dispatchEvent(new CustomEvent('interests:change', { bubbles: true }));
    });
  });

  var onb = $('[data-onboarding]');
  if (onb) {
    var oPicker = $('[data-interest-picker]', onb), oBtn = $('[data-onb-save]', onb), oErr = $('[data-onb-error]', onb), oLabel = $('[data-onb-label]', onb);
    var oLabelUpd = function () { var n = pickerValue(oPicker).length; oLabel.textContent = 'Continue' + (n ? ' with ' + n + ' topic' + (n > 1 ? 's' : '') : ''); oErr.hidden = true; };
    oPicker.addEventListener('interests:change', oLabelUpd); oLabelUpd();
    oBtn.addEventListener('click', function () {
      var sel = pickerValue(oPicker);
      if (!sel.length) { oErr.textContent = 'Pick at least one topic to personalise your feed.'; oErr.hidden = false; return; }
      setBusy(oBtn, true);
      api('PUT', '/api/users/preferences', { interests: sel }).then(function () { flash('Your feed is ready!'); location.replace('/for-you'); })
        .catch(function (x) { oErr.textContent = errMsg(x); oErr.hidden = false; setBusy(oBtn, false); });
    });
  }

  var prof = $('[data-profile]');
  if (prof) {
    var initial = []; try { initial = JSON.parse(prof.getAttribute('data-interests')); } catch (e) { /* ignore */ }
    var pPicker = $('[data-interest-picker]', prof), pSave = $('[data-save-interests]', prof), pDirty = $('[data-dirty]', prof);
    var sameSet = function (a, b) { return a.slice().sort().join() === b.slice().sort().join(); };
    pPicker.addEventListener('interests:change', function () { var d = !sameSet(pickerValue(pPicker), initial); pSave.disabled = !d; pDirty.hidden = !d; });
    pSave.addEventListener('click', function () {
      var sel = pickerValue(pPicker);
      if (!sel.length) return toast('Pick at least one topic.', 'error');
      setBusy(pSave, true);
      api('PUT', '/api/users/preferences', { interests: sel }).then(function () { flash('Interests updated — your feed will reflect this right away.'); location.reload(); })
        .catch(function (x) { toast(errMsg(x), 'error'); setBusy(pSave, false); });
    });
    // tabs
    var tabs = $$('[data-tab]', prof);
    tabs.forEach(function (t) {
      t.addEventListener('click', function () {
        tabs.forEach(function (o) {
          var on = o === t;
          o.classList.toggle('border-accent', on); o.classList.toggle('text-accent', on);
          o.classList.toggle('border-transparent', !on); o.classList.toggle('text-muted', !on); o.classList.toggle('hover:text-ink', !on);
        });
        $$('[data-panel]', prof).forEach(function (p) { p.hidden = p.getAttribute('data-panel') !== t.getAttribute('data-tab'); });
      });
    });
    // account form
    var pf = $('[data-profile-form]', prof), pbtn = $('[data-submit]', pf);
    pf.addEventListener('submit', function (e) {
      e.preventDefault(); showErrors(pf, {}); formError(pf, '');
      var body = { name: pf.name.value, avatar: pf.avatar.value };
      if (pf.newPassword.value) { body.currentPassword = pf.currentPassword.value; body.newPassword = pf.newPassword.value; }
      setBusy(pbtn, true);
      api('PUT', '/api/users/profile', body).then(function () { flash('Profile saved'); location.reload(); })
        .catch(function (x) { var er = (x.data && x.data.errors) || null; if (er) showErrors(pf, er); else formError(pf, errMsg(x)); setBusy(pbtn, false); });
    });
  }

  /* history */
  var ch = $('[data-clear-history]');
  if (ch) ch.addEventListener('click', function () {
    if (!window.confirm('Clear your entire reading history? This also resets what the recommender has learned from your reading.')) return;
    setBusy(ch, true); $('[data-clear-icon]', ch).hidden = true;
    api('DELETE', '/api/history').then(function () { flash('Reading history cleared'); location.replace('/history'); })
      .catch(function () { toast('Could not clear history', 'error'); setBusy(ch, false); $('[data-clear-icon]', ch).hidden = false; });
  });

  /* ------------------------------------------------------------------ search page (live results) */
  var sp = $('[data-search-page]');
  if (sp) {
    var spForm = $('[data-search-page-form]', sp), spInput = $('[data-search-page-input]', sp), spClear = $('[data-clear-search]', sp);
    var sSeq = 0;
    var swap = function (url, push) {
      var seq = ++sSeq;
      var region = $('[data-search-region]', sp); region.style.opacity = '.6';
      fetch(url, { credentials: 'same-origin' }).then(function (r) { return r.text(); }).then(function (html) {
        if (seq !== sSeq) return;
        var doc = new DOMParser().parseFromString(html, 'text/html');
        var fresh = $('[data-search-region]', doc);
        if (!fresh) { location.href = url; return; }
        region.replaceWith(fresh);
        initImages(fresh); initReveal(fresh);
        history.replaceState(null, '', url);
        var q = new URL(url, location.origin).searchParams.get('q') || '';
        document.title = (q ? 'Search: ' + q : 'Search') + ' – NewsSphere';
      }).catch(function () { region.style.opacity = ''; });
    };
    var currentUrl = function (q) {
      var u = new URL(location.href); u.searchParams.delete('page');
      if (q) u.searchParams.set('q', q); else u.searchParams.delete('q');
      return u.pathname + u.search;
    };
    var live = debounce(function () {
      var q = spInput.value.trim();
      var cur = (new URL(location.href).searchParams.get('q') || '');
      spClear.classList.toggle('hidden', !spInput.value);
      if (q !== cur) swap(currentUrl(q));
    }, 400);
    spInput.addEventListener('input', live);
    spForm.addEventListener('submit', function (e) { e.preventDefault(); swap(currentUrl(spInput.value.trim())); });
    spClear.addEventListener('click', function (e) { e.preventDefault(); spInput.value = ''; spClear.classList.add('hidden'); swap(currentUrl('')); spInput.focus(); });
    sp.addEventListener('change', function (e) { var s = e.target.closest('[data-nav-select]'); if (s) swap(s.value); });
    sp.addEventListener('click', function (e) {
      var t = e.target.closest('[data-filters-toggle]');
      if (t) { var a = $('[data-filters]', sp); a.classList.toggle('hidden'); a.classList.toggle('block'); return; }
      var a2 = e.target.closest('[data-search-region] a[href^="/search"]');
      if (a2 && !e.metaKey && !e.ctrlKey && !e.shiftKey) { e.preventDefault(); swap(a2.getAttribute('href')); }
    });
    if (!spInput.value) spInput.focus(); else { spInput.focus(); spInput.setSelectionRange(spInput.value.length, spInput.value.length); }
  }

  /* ------------------------------------------------------------------ admin */
  var drawerA = $('[data-admin-drawer]');
  if (drawerA) {
    $('[data-admin-drawer-toggle]').addEventListener('click', function () { drawerA.hidden = !drawerA.hidden; });
    $('[data-admin-drawer-close]').addEventListener('click', function () { drawerA.hidden = true; });
  }
  try { var rf = sessionStorage.getItem('ns-refocus'); if (rf) { sessionStorage.removeItem('ns-refocus'); var ri = $(rf); if (ri) { ri.focus(); ri.setSelectionRange(ri.value.length, ri.value.length); } } } catch (e) { /* ignore */ }
  $$('[data-admin-search]').forEach(function (form) {
    var input = $('input[name="q"]', form);
    if (input) input.addEventListener('input', debounce(function () { try { sessionStorage.setItem('ns-refocus', 'form[data-admin-search] input[name="q"]'); } catch (e) { /* ignore */ } form.submit(); }, 350));
    $$('[data-autosubmit]', form).forEach(function (s) { s.addEventListener('change', function () { form.submit(); }); });
  });

  $$('[data-user-row]').forEach(function (row) {
    var id = row.getAttribute('data-user-row'), name = row.getAttribute('data-name');
    var tr = $('[data-toggle-role]', row), del = $('[data-delete-user]', row);
    tr && tr.addEventListener('click', function () {
      var role = tr.getAttribute('data-toggle-role');
      api('PATCH', '/api/admin/users/' + id + '/role', { role: role }).then(function () {
        flash(name + ' is now ' + (role === 'admin' ? 'an admin' : 'a regular user')); location.reload();
      }).catch(function (e) { toast(errMsg(e), 'error'); });
    });
    del && del.addEventListener('click', function () {
      if (!window.confirm('Delete ' + name + '? Their bookmarks, likes and reading history will be removed too.')) return;
      api('DELETE', '/api/admin/users/' + id).then(function () { flash('User deleted'); location.reload(); }).catch(function (e) { toast(errMsg(e), 'error'); });
    });
  });

  var adm = $('[data-admin-articles]');
  if (adm) {
    var modal = $('[data-article-modal]', adm), aform = $('[data-article-form]', adm), confirmM = $('[data-confirm-modal]', adm);
    var editing = null, delId = null;
    var fields = ['title', 'subtitle', 'description', 'content', 'category', 'source', 'author', 'popularityScore', 'image', 'tags'];
    var openModal = function (id) {
      editing = id; aform.reset(); showErrors(aform, {}); formError(aform, '');
      $('[data-modal-title]', aform).textContent = id ? 'Edit article' : 'New article';
      $('[data-submit-label]', aform).textContent = id ? 'Save changes' : 'Publish';
      aform.category.value = 'technology'; aform.popularityScore.value = 50;
      show(modal);
      if (id) {
        setBusy($('[data-submit]', aform), true);
        api('GET', '/api/admin/articles/' + id).then(function (d) {
          var a = d.article;
          fields.forEach(function (k) { if (k === 'tags') aform.tags.value = (a.tags || []).join(', '); else if (a[k] != null) aform[k].value = a[k]; });
          aform.isBreaking.checked = !!a.isBreaking; aform.isFeatured.checked = !!a.isFeatured;
        }).catch(function (e) { toast(errMsg(e), 'error'); hide(modal); }).then(function () { setBusy($('[data-submit]', aform), false); });
      }
    };
    var closeModal = function () { hide(modal); };
    $$('[data-modal-close]', adm).forEach(function (b) { b.addEventListener('click', closeModal); });
    modal.addEventListener('mousedown', function (e) { if (e.target === modal) closeModal(); });
    $('[data-new-article]', adm).addEventListener('click', function () { openModal(null); });
    $$('[data-edit-article]', adm).forEach(function (b) { b.addEventListener('click', function () { openModal(b.closest('tr').getAttribute('data-article-row')); }); });
    aform.addEventListener('submit', function (e) {
      e.preventDefault(); showErrors(aform, {}); formError(aform, '');
      var body = {}; fields.forEach(function (k) { body[k] = aform[k].value; });
      body.popularityScore = Number(body.popularityScore); body.isBreaking = aform.isBreaking.checked; body.isFeatured = aform.isFeatured.checked;
      var btn = $('[data-submit]', aform); setBusy(btn, true);
      api(editing ? 'PUT' : 'POST', '/api/admin/articles' + (editing ? '/' + editing : ''), body).then(function () {
        flash(editing ? 'Article updated' : 'Article published'); location.replace('/admin/articles');
      }).catch(function (x) { var er = x.data && x.data.errors; if (er) showErrors(aform, er); else formError(aform, errMsg(x)); setBusy(btn, false); });
    });
    $$('[data-delete-article]', adm).forEach(function (b) {
      b.addEventListener('click', function () { var tr = b.closest('tr'); delId = tr.getAttribute('data-article-row'); $('[data-confirm-title]', confirmM).textContent = tr.getAttribute('data-title'); show(confirmM); });
    });
    $('[data-confirm-cancel]', adm).addEventListener('click', function () { hide(confirmM); });
    confirmM.addEventListener('mousedown', function (e) { if (e.target === confirmM) hide(confirmM); });
    $('[data-confirm-ok]', adm).addEventListener('click', function () {
      api('DELETE', '/api/admin/articles/' + delId).then(function () { flash('Article deleted'); location.reload(); }).catch(function (e) { toast(errMsg(e), 'error'); hide(confirmM); });
    });
    var imp = $('[data-import]', adm);
    imp.addEventListener('click', function () {
      setBusy(imp, true); $('[data-import-icon]', imp).hidden = true;
      api('POST', '/api/admin/import').then(function (r) {
        if (r.inserted) { flash('Imported ' + r.inserted + ' new articles', 'success'); location.reload(); return; }
        toast((r.errors && r.errors[0]) || 'No new articles found', 'info');
      }).catch(function (e) { toast(errMsg(e), 'error'); }).then(function () { setBusy(imp, false); $('[data-import-icon]', imp).hidden = false; });
    });
    if (adm.getAttribute('data-open-new') === 'true') { openModal(null); history.replaceState(null, '', '/admin/articles'); }
  }

  /* ------------------------------------------------------------------ global delegated events */
  document.addEventListener('click', function (e) {
    var t = e.target;
    var hrefEl = t.closest('[data-href]');
    if (hrefEl) { e.preventDefault(); e.stopPropagation(); location.href = hrefEl.getAttribute('data-href'); return; }
    var bm = t.closest('[data-bookmark]'); if (bm) { e.preventDefault(); e.stopPropagation(); toggleBookmark(bm); return; }
    var lk = t.closest('[data-like]'); if (lk) { e.preventDefault(); lk && toggleLike(lk); return; }
    if (t.closest('[data-theme-toggle]')) {
      var btn = t.closest('[data-theme-toggle]'); var dark = !document.documentElement.classList.contains('dark'); setTheme(dark);
      var ic = $('.theme-icon', btn); if (ic) { ic.classList.remove('spin-in'); void ic.offsetWidth; ic.classList.add('spin-in'); }
      return;
    }
    if (t.closest('[data-drawer-open]')) return openDrawer();
    if (t.closest('[data-drawer-close]') || t.closest('[data-drawer-backdrop]')) return closeDrawer();
    if (t.closest('[data-search-open]')) return openSearch();
    if (t.closest('[data-search-close]')) return closeSearch();
    if (search && !search.hidden && t === search) return closeSearch();
    if (t.closest('[data-search] a')) closeSearch();
    var ab = t.closest('[data-account-btn]');
    if (ab) { var m = $('[data-account-menu]'); var open = m.hidden; m.hidden = !open; ab.setAttribute('aria-expanded', String(open)); return; }
    if (!t.closest('[data-account]')) closeAccount();
    if (t.closest('[data-logout]')) { api('POST', '/api/auth/logout').catch(function () {}).then(function () { flash('You have been signed out.'); location.href = '/'; }); return; }
    if (t.closest('[data-auth-close]') || (authModal && t === authModal)) hide(authModal);
  }, true);

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeSearch(); closeDrawer(); closeAccount(); hide(authModal); $$('[data-article-modal],[data-confirm-modal]').forEach(hide); }
    if (e.key === '/' && !/input|textarea|select/i.test(e.target.tagName) && !e.target.isContentEditable && !e.ctrlKey && !e.metaKey) { e.preventDefault(); openSearch(); }
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('[data-href]')) { e.preventDefault(); location.href = e.target.getAttribute('data-href'); }
  });
  if (search) search.addEventListener('submit', function (e) { var f = e.target; if (!searchInput.value.trim()) e.preventDefault(); });

  /* ------------------------------------------------------------------ init */
  initImages(document); initReveal(document); initDates(document); initLoadMore();
})();
