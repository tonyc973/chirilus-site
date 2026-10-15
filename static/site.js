/* roglia.ro — progressive enhancements. The site works fully without this file. */
(function () {
  'use strict';

  // Each feature is isolated so one failure can't take the others down.
  function run(feature) { try { feature(); } catch (e) { /* enhancement only */ } }

  // ───── Theme toggle (the initial theme is set inline in <head> to avoid a flash) ─────
  run(function () {
    var root = document.documentElement;
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    function sync() {
      var dark = root.getAttribute('data-theme') !== 'light';
      btn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
      btn.setAttribute('aria-pressed', dark ? 'true' : 'false');
    }
    sync();
    btn.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) {}
      sync();
    });
    // Follow the OS setting until the visitor picks a theme themselves.
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    if (mq.addEventListener) {
      mq.addEventListener('change', function (e) {
        var stored = null;
        try { stored = localStorage.getItem('theme'); } catch (err) {}
        if (!stored) { root.setAttribute('data-theme', e.matches ? 'dark' : 'light'); sync(); }
      });
    }
  });

  // ───── Nav: on-dark glass while it floats over the cinematic hero ─────
  run(function () {
    var nav = document.querySelector('.nav-pill');
    var hero = document.querySelector('.cinema-hero');
    if (!nav || !hero) return;
    function upd() { nav.classList.toggle('over-hero', window.scrollY < hero.offsetHeight - 72); }
    upd();
    window.addEventListener('scroll', upd, { passive: true });
    window.addEventListener('resize', upd);
  });

  // ───── Reading progress (post pages) ─────
  run(function () {
    var bar = document.querySelector('.read-progress');
    var article = document.querySelector('article.post-body');
    if (!bar || !article) return;
    var ticking = false;
    function update() {
      ticking = false;
      var rect = article.getBoundingClientRect();
      var total = article.offsetHeight - window.innerHeight;
      var pct = total > 0 ? Math.min(Math.max(-rect.top / total, 0), 1) : 1;
      bar.style.transform = 'scaleX(' + pct.toFixed(4) + ')';
    }
    function onScroll() { if (!ticking) { ticking = true; requestAnimationFrame(update); } }
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
  });

  // ───── Copy buttons on code blocks ─────
  run(function () {
    if (!navigator.clipboard) return;
    document.querySelectorAll('.prose .highlight').forEach(function (block) {
      var pre = block.querySelector('pre');
      if (!pre) return;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'code-copy';
      b.textContent = 'Copy';
      b.setAttribute('aria-label', 'Copy code to clipboard');
      b.addEventListener('click', function () {
        navigator.clipboard.writeText(pre.textContent.replace(/\n$/, '')).then(function () {
          b.textContent = 'Copied';
          b.classList.add('is-done');
          setTimeout(function () { b.textContent = 'Copy'; b.classList.remove('is-done'); }, 1600);
        }, function () { b.textContent = 'Select + copy'; });
      });
      block.appendChild(b);
    });
  });

  // ───── "Copy email" button (mailto: does nothing on machines without a mail app) ─────
  run(function () {
    document.querySelectorAll('[data-copy]').forEach(function (b) {
      if (!navigator.clipboard) { b.hidden = true; return; }
      var label = b.textContent;
      b.addEventListener('click', function () {
        navigator.clipboard.writeText(b.getAttribute('data-copy')).then(function () {
          b.textContent = 'Copied ✓';
          b.classList.add('is-done');
          setTimeout(function () { b.textContent = label; b.classList.remove('is-done'); }, 1800);
        });
      });
    });
  });

  // ───── Local time in Bucharest (footer) ─────
  run(function () {
    var el = document.getElementById('local-time');
    if (!el || !window.Intl) return;
    var fmt = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Bucharest' });
    function tick() { el.textContent = ' · ' + fmt.format(new Date()) + ' local'; }
    tick();
    setInterval(tick, 30000);
  });

  // ───── Cinematic hero — prismatic slit dispersion ("the spectrometer"), Canvas 2D ─────
  run(function () {
    var canvas = document.getElementById('hero-rays');
    if (!canvas) return;
    var hero = canvas.closest('.cinema-hero');
    var ctx = canvas.getContext('2d');
    if (!ctx || !hero) return;
    hero.classList.add('js-rays');

    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var coarse = window.matchMedia('(pointer: coarse)').matches;

    var SPECTRUM = [
      [155,123,255],[107,138,255],[95,212,255],[124,240,176],
      [190,235,150],[255,176,112],[255,138,95],[255,107,61]
    ];
    function hueAt(t) {
      t = t < 0 ? 0 : (t > 1 ? 1 : t);
      var x = t * (SPECTRUM.length - 1);
      var i = Math.min(SPECTRUM.length - 2, Math.floor(x));
      var f = x - i, a = SPECTRUM[i], b = SPECTRUM[i + 1];
      return [a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f, a[2]+(b[2]-a[2])*f];
    }
    function rnd(i, s) { var x = Math.sin(i*127.1 + s*311.7) * 43758.5453; return x - Math.floor(x); }

    var P = { slitX:0.91, slitTop:0.16, slitBot:0.86, n:24, spread:0.85, lenMin:0.26, lenMax:0.66 };
    var W = 0, H = 0, dpr = 1, mobileDim = 1;

    var PARTICLES = [];
    var dust = !reduceMotion;  // no motes in the still frame: frozen, they read as dirt on the lens
    function smoothstep(a, b, x) { var t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); }
    function initParticles() {
      PARTICLES = [];
      var count = coarse ? 8 : 18;
      for (var i = 0; i < count; i++) {
        PARTICLES.push({ x: rnd(i,3), y: rnd(i,4), z: 0.25 + rnd(i,5)*0.75, ph: rnd(i,6)*6.2832, sp: 0.25 + rnd(i,7)*0.7 });
      }
    }

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, coarse ? 1.5 : 2);
      W = canvas.clientWidth; H = canvas.clientHeight;
      canvas.width = Math.max(1, Math.round(W * dpr));
      canvas.height = Math.max(1, Math.round(H * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // On narrow screens lift the fan into the upper-right and dim it so it
      // arcs above the headline rather than washing across the type.
      var narrow = W < 768;
      // Keep the slit near the 1120px content column on very wide screens.
      P.slitX   = narrow ? 0.94 : Math.min(0.91, ((W + 1120) / 2 + 100) / W);
      P.slitTop = narrow ? 0.05 : 0.16;
      P.slitBot = narrow ? 0.44 : 0.86;
      P.lenMax  = narrow ? 0.52 : 0.66;
      P.spread  = narrow ? 1.0  : 0.85;
      mobileDim = narrow ? 0.62 : 1.0;
    }

    function streak(cx, cy, angle, len, rgb, alpha) {
      ctx.save(); ctx.translate(cx, cy); ctx.rotate(angle);
      var passes = [[1,1.0],[3.0,0.42],[7.5,0.18]], baseW = 2.2;
      var c = 'rgba(' + (rgb[0]|0) + ',' + (rgb[1]|0) + ',' + (rgb[2]|0) + ',';
      for (var k = 0; k < passes.length; k++) {
        var w = baseW * passes[k][0], am = passes[k][1];
        var g = ctx.createLinearGradient(0, 0, len, 0);
        g.addColorStop(0, c + (alpha*am) + ')');
        g.addColorStop(0.10, c + (alpha*am) + ')');
        g.addColorStop(0.55, c + (alpha*am*0.45) + ')');
        g.addColorStop(1, c + '0)');
        ctx.fillStyle = g;
        ctx.beginPath(); ctx.moveTo(0, -w/2); ctx.lineTo(0, w/2); ctx.lineTo(len, 0); ctx.closePath(); ctx.fill();
      }
      ctx.restore();
    }

    function draw(time, reveal, intensity, shear, drift, hueHover) {
      ctx.clearRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'lighter';
      var sx = P.slitX*W + drift, sTop = P.slitTop*H, sBot = P.slitBot*H, sMid = (sTop+sBot)/2, N = P.n;
      for (var i = 0; i < N; i++) {
        var u = i/(N-1);
        var t = 0.5 + 0.5*Math.sign(u-0.5)*Math.pow(Math.abs(2*u-1), 1.7);
        var oy = sMid + (t-0.5)*(sBot-sTop);
        var ang = Math.PI - (t-0.5)*P.spread + (rnd(i,1)-0.5)*0.05 + shear;
        var cd = Math.abs(t-0.5)/0.5, lf = 1 - Math.pow(cd, 1.7);
        var len = (P.lenMin + (P.lenMax-P.lenMin)*lf) * W * (0.86 + rnd(i,2)*0.28) * reveal;
        var rgb = hueAt(t + hueHover*0.04);
        var alpha = (0.20 + 0.16*lf);
        alpha *= (0.80 + 0.20*Math.sin(time*0.6 + i*1.7));
        alpha *= intensity * reveal * mobileDim;
        var a2 = ang + Math.sin(time*0.18 + i*0.9)*0.026;
        if (alpha > 0) streak(sx, oy, a2, len, rgb, alpha);
      }
      // Volumetric dust — fine motes drifting through the beam, fading out before the text column.
      for (var pi = 0; dust && pi < PARTICLES.length; pi++) {
        var pt = PARTICLES[pi];
        var dx = pt.x*W - time*pt.sp*9;
        var pxp = ((dx % W) + W) % W;
        var pyp = pt.y*H + Math.sin(time*0.25 + pt.ph)*12;
        var tw = 0.45 + 0.55*Math.sin(time*0.9 + pt.ph*1.3);
        var pa = (0.16 + 0.46*pt.z) * tw * intensity * reveal * mobileDim * smoothstep(0.5*W, 0.72*W, pxp);
        if (pa <= 0.012) continue;
        var pr = 0.5 + pt.z*0.8;
        ctx.fillStyle = 'rgba(255,250,243,' + pa + ')';
        ctx.beginPath(); ctx.arc(pxp, pyp, pr, 0, 6.2832); ctx.fill();
        ctx.fillStyle = 'rgba(255,247,237,' + (pa*0.2) + ')';
        ctx.beginPath(); ctx.arc(pxp, pyp, pr*2, 0, 6.2832); ctx.fill();
      }

      // The slit — a crisp emitter line with a tight inner bloom and a wide soft halo.
      var breathe = 1 + 0.06*Math.sin(time*0.5);
      var kg = ctx.createLinearGradient(sx, sTop, sx, sBot);
      kg.addColorStop(0, 'rgba(255,255,255,0)');
      kg.addColorStop(0.5, 'rgba(255,252,248,' + (0.62*reveal*intensity*mobileDim*breathe*(1 + 0.15*hueHover)) + ')');
      kg.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = kg; ctx.fillRect(sx-1, sTop, 2, sBot-sTop);
      // Glows are tall ellipses hugging the slit, so no grey panel spreads to its right.
      ctx.save(); ctx.translate(sx, sMid); ctx.scale(0.4, 1);
      var rg1 = ctx.createRadialGradient(0, 0, 0, 0, 0, (sBot-sTop)*0.32);
      rg1.addColorStop(0, 'rgba(255,248,238,' + (0.14*reveal*intensity*mobileDim*breathe) + ')');
      rg1.addColorStop(1, 'rgba(255,248,238,0)');
      ctx.fillStyle = rg1; ctx.fillRect(-W*2.5, -H, W*5, H*2);
      var rg2 = ctx.createRadialGradient(0, 0, 0, 0, 0, (sBot-sTop)*0.72);
      rg2.addColorStop(0, 'rgba(255,245,235,' + (0.05*reveal*intensity*mobileDim) + ')');
      rg2.addColorStop(1, 'rgba(255,245,235,0)');
      ctx.fillStyle = rg2; ctx.fillRect(-W*2.5, -H, W*5, H*2);
      ctx.restore();

      ctx.globalCompositeOperation = 'destination-in';
      var lm = ctx.createLinearGradient(0, 0, W, 0);
      lm.addColorStop(0, 'rgba(0,0,0,0)'); lm.addColorStop(0.12, 'rgba(0,0,0,0)');
      lm.addColorStop(0.42, 'rgba(0,0,0,0.7)'); lm.addColorStop(1, 'rgba(0,0,0,1)');
      ctx.fillStyle = lm; ctx.fillRect(0, 0, W, H);
      var vm = ctx.createLinearGradient(0, 0, 0, H);
      vm.addColorStop(0, 'rgba(0,0,0,0)'); vm.addColorStop(0.10, 'rgba(0,0,0,1)');
      vm.addColorStop(0.82, 'rgba(0,0,0,1)'); vm.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = vm; ctx.fillRect(0, 0, W, H);
      var rm = ctx.createRadialGradient(sx, sMid, 0, sx, sMid, W*0.95);
      rm.addColorStop(0, 'rgba(0,0,0,1)'); rm.addColorStop(0.7, 'rgba(0,0,0,0.95)'); rm.addColorStop(1, 'rgba(0,0,0,0.35)');
      ctx.fillStyle = rm; ctx.fillRect(0, 0, W, H);
      var rf = ctx.createLinearGradient(0, 0, W, 0);  // fade whatever light lands right of the slit
      rf.addColorStop(0, 'rgba(0,0,0,1)'); rf.addColorStop(Math.min(1, sx / W), 'rgba(0,0,0,1)'); rf.addColorStop(1, 'rgba(0,0,0,0.25)');
      ctx.fillStyle = rf; ctx.fillRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'source-over';
    }

    var startT = null, raf = null, visible = true;
    var pTX = 0, pTY = 0, pX = 0, pY = 0, hueTarget = 0, hueCur = 0;

    function scrollIntensity() {
      var rect = hero.getBoundingClientRect();
      var p = -rect.top / (hero.offsetHeight || 1);
      p = p < 0 ? 0 : (p > 1 ? 1 : p);
      return 1 - p;
    }
    function frame(now) {
      if (startT === null) startT = now;
      var time = (now - startT) / 1000;
      var rv = reduceMotion ? 1 : Math.min(1, time/1.1);
      rv = rv < 1 ? (1 - Math.pow(1-rv, 3)) : 1;
      pX += (pTX - pX)*0.06; pY += (pTY - pY)*0.06;
      hueCur += (hueTarget - hueCur)*0.08;
      var shear = pX*0.045, drift = pX*6;
      var intensity = scrollIntensity();
      if (pX < 0) intensity *= (1 + pX*0.08);
      draw(time, rv, intensity, shear, drift, hueCur);
      if (!reduceMotion && visible && intensity > 0.01) { raf = requestAnimationFrame(frame); }
      else { raf = null; }
    }
    function startLoop() { if (raf === null && !reduceMotion) raf = requestAnimationFrame(frame); }
    function renderStatic() { resize(); draw(8.0, 1, scrollIntensity(), 0, 0, 0); }

    resize();
    initParticles();
    if (reduceMotion) {
      renderStatic();
    } else {
      if (!coarse) {
        window.addEventListener('pointermove', function (e) {
          var r = hero.getBoundingClientRect();
          pTX = ((e.clientX - r.left)/r.width - 0.5)*2;
          pTY = ((e.clientY - r.top)/r.height - 0.5)*2;
        }, { passive: true });
        window.addEventListener('blur', function () { pTX = 0; pTY = 0; });
      }
      var lit = document.querySelector('.lit-word');
      if (lit) {
        lit.addEventListener('pointerenter', function () { hueTarget = 1; });
        lit.addEventListener('pointerleave', function () { hueTarget = 0; });
      }
      if ('IntersectionObserver' in window) {
        new IntersectionObserver(function (es) {
          visible = es[0].isIntersecting;
          if (visible) startLoop();
        }).observe(hero);
      }
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) { if (raf) { cancelAnimationFrame(raf); raf = null; } }
        else { startLoop(); }
      });
      window.addEventListener('scroll', function () { if (visible) startLoop(); }, { passive: true });
      startLoop();
    }
    var rt;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () { resize(); if (reduceMotion) renderStatic(); else startLoop(); }, 150);
    });
  });
})();
