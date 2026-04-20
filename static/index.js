/**
 * Index page — new-paste editor with CodeMirror, live char counter,
 * CM mode-switching from the language picker, password-strength meter,
 * submit flow, and a typewriter animation in the hero tagline.
 *
 * Per-request bootstrap data (max_paste_size, cm_mode_map) is served in
 * <script id="index-meta" type="application/json"> so this file stays
 * cacheable.
 */
(() => {
  'use strict';

  const META = JSON.parse(document.getElementById('index-meta').textContent);

  const textarea = document.getElementById('content'); // hidden mirror for form submit
  const counter  = document.getElementById('charCounter');
  const MAX = META.max_paste_size;

  // slug → CodeMirror 5 mode/MIME. Sourced from app/languages.json via the
  // server template context so this table stays consistent with detect.py
  // and the paste view without being duplicated in three places.
  const CM_MODE = META.cm_mode_map;

  function fmt(n) { return n < 1024 ? n + ' B' : (n / 1024).toFixed(1) + ' KB'; }

  const cm = CodeMirror(document.getElementById('cmHost'), {
    value: '',
    mode: null,
    theme: 'dracula',
    lineNumbers: true,
    lineWrapping: false,
    matchBrackets: true,
    autoCloseBrackets: true,
    styleActiveLine: true,
    indentUnit: 2,
    tabSize: 2,
    indentWithTabs: false,
    inputStyle: 'contenteditable',
    extraKeys: {
      'Tab': (cm) => cm.replaceSelection('  ', 'end'),
      'Ctrl-Enter': () => submitPaste(),
      'Cmd-Enter':  () => submitPaste(),
    },
    placeholder: 'Paste your code or snippet here…',
  });

  function updateCounter() {
    const bytes = new TextEncoder().encode(cm.getValue()).length;
    counter.textContent = bytes > 0 ? fmt(bytes) + ' / ' + fmt(MAX) : '';
    counter.classList.toggle('warn',  bytes > MAX * 0.8 && bytes <= MAX);
    counter.classList.toggle('error', bytes > MAX);
  }

  cm.on('change', updateCounter);
  cm.focus();

  // Language auto-detection
  const langSelect = document.getElementById('language');
  const langLabel  = document.querySelector('.lang-picker-label');
  let detectTimer  = null;
  let justPasted   = false;

  function setCmMode(lang) {
    const mode = CM_MODE[lang] ?? null;
    cm.setOption('mode', mode);
  }

  function runDetect() {
    const content = cm.getValue();
    if (content.length < 20 || langSelect.value !== '') return;

    fetch('/api/v1/detect', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({content})
    })
    .then(r => r.json())
    .then(data => {
      if (data.language && langSelect.value === '') {
        langSelect.value = data.language;
        langLabel.textContent = 'Detected';
        langLabel.style.color = 'var(--drac-green)';
        setTimeout(() => {
          langLabel.textContent = 'Language';
          langLabel.style.color = '';
        }, 2500);
        setCmMode(data.language);
      }
    })
    .catch(() => {});
  }

  // CM's 'inputRead' fires for every user input; the 'paste' Codemirror event
  // lets us use a shorter debounce after a paste vs live typing (same heuristic
  // as the previous textarea implementation).
  cm.on('paste', () => { justPasted = true; });
  cm.on('change', (_, change) => {
    // Only react to user-typed changes, not programmatic setValue calls.
    if (change.origin === 'setValue') return;
    clearTimeout(detectTimer);
    const delay = justPasted ? 200 : 1000;
    justPasted = false;
    detectTimer = setTimeout(runDetect, delay);
  });

  // Reset label + switch CM mode when user manually changes language
  langSelect.addEventListener('change', () => {
    langLabel.textContent = 'Language';
    langLabel.style.color = '';
    setCmMode(langSelect.value);
  });

  // Number input custom buttons (−/+)
  document.querySelectorAll('.number-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.target);
      const dir   = parseInt(btn.dataset.dir);
      const min   = parseInt(input.min) || 1;
      const cur   = parseInt(input.value) || 0;
      const next  = cur + dir;
      input.value = next >= min ? next : '';
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  });

  // Password toggle
  const pwToggle  = document.getElementById('passwordToggle');
  const pwWrap    = document.getElementById('passwordWrap');
  const pwInput   = document.getElementById('password');
  const pwConfirm = document.getElementById('passwordConfirm');
  const pwStrength = document.getElementById('pwStrength');
  const pwStrengthLabel = document.getElementById('pwStrengthLabel');
  const pwMatch   = document.getElementById('pwMatch');

  pwToggle.addEventListener('change', () => {
    pwWrap.classList.toggle('visible', pwToggle.checked);
    if (!pwToggle.checked) {
      pwInput.value = '';
      pwConfirm.value = '';
      updatePwStrength();
      updatePwMatch();
    }
  });

  // Strength heuristic: coarse, client-only, never shipped to server.
  // Scoring = length tiers + variety (lower/upper/digit/symbol). Good enough
  // to nudge users off "password123" — not a substitute for a KDF cost.
  function scorePassword(pw) {
    if (!pw) return 0;
    let score = 0;
    if (pw.length >= 8)  score++;
    if (pw.length >= 12) score++;
    if (pw.length >= 16) score++;
    const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter(r => r.test(pw)).length;
    if (classes >= 2) score++;
    if (classes >= 3) score++;
    return Math.min(4, score);
  }
  const STRENGTH_LABELS = ['—', 'Weak', 'Fair', 'Good', 'Strong'];

  function updatePwStrength() {
    const level = scorePassword(pwInput.value);
    pwStrength.dataset.level = String(level);
    pwStrengthLabel.textContent = STRENGTH_LABELS[level];
  }

  function updatePwMatch() {
    const a = pwInput.value, b = pwConfirm.value;
    if (!b) { pwMatch.textContent = ''; pwMatch.classList.remove('ok'); pwConfirm.classList.remove('mismatch'); return; }
    if (a === b) {
      pwMatch.textContent = 'Passwords match.';
      pwMatch.classList.add('ok');
      pwConfirm.classList.remove('mismatch');
    } else {
      pwMatch.textContent = "Passwords don't match.";
      pwMatch.classList.remove('ok');
      pwConfirm.classList.add('mismatch');
    }
  }

  pwInput.addEventListener('input', () => { updatePwStrength(); updatePwMatch(); });
  pwConfirm.addEventListener('input', updatePwMatch);

  // Webhook toggle
  const whToggle = document.getElementById('webhookToggle');
  const whWrap   = document.getElementById('webhookWrap');
  whToggle.addEventListener('change', () => {
    whWrap.classList.toggle('visible', whToggle.checked);
    if (!whToggle.checked) document.getElementById('webhook_url').value = '';
  });

  // ── Toast notifications ───────────────────────────────────────────────────
  function showToast(msg, type = 'error') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    // Inline onclick would be blocked by CSP (no 'unsafe-inline' in script-src).
    // Build the close button in code and wire it via addEventListener.
    toast.innerHTML =
      `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>` +
      `<span></span>` +
      `<button type="button" class="toast-close">` +
      `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;
    toast.querySelector('span').textContent = msg;   // avoid HTML injection in msg
    toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
    document.body.appendChild(toast);
    // Trigger animation
    requestAnimationFrame(() => toast.classList.add('toast-visible'));
    // Auto-dismiss after 4s
    const timer = setTimeout(() => dismissToast(toast), 4000);
    toast.addEventListener('mouseenter', () => clearTimeout(timer));
    toast.addEventListener('mouseleave', () => setTimeout(() => dismissToast(toast), 1500));
  }

  function dismissToast(toast) {
    toast.classList.remove('toast-visible');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  }

  function showFormError(msg) { showToast(msg, 'error'); }

  if (window.__serverError) showToast(window.__serverError, 'error');

  async function submitPaste() {
    const content = cm.getValue();
    textarea.value = content; // keep hidden mirror in sync for any fallback consumers
    if (!content.trim()) { showFormError('Content cannot be empty.'); return; }

    const bytes = new TextEncoder().encode(content).length;
    if (bytes > MAX) { showFormError(`Paste too large (max ${(MAX/1024).toFixed(0)} KB).`); return; }

    if (!window.isSecureContext) {
      const localhostUrl = location.href.replace(location.hostname, 'localhost');
      showFormError(
        `Encryption requires a Secure Context. ` +
        `<a href="${localhostUrl}" style="color:inherit;text-decoration:underline">` +
        `Click here to switch to localhost</a> — or use HTTPS in production.`
      );
      return;
    }

    const btn = document.querySelector('#pasteForm [type=submit]');
    btn.disabled = true;

    try {
      const hasPassword = document.getElementById('passwordToggle').checked;
      const password    = hasPassword ? pwInput.value : '';

      if (hasPassword) {
        if (!password) { showFormError('Please enter a password or disable password protection.'); btn.disabled = false; return; }
        if (password !== pwConfirm.value) {
          showFormError("Passwords don't match. Please retype the confirmation.");
          pwConfirm.focus();
          btn.disabled = false;
          return;
        }
      }

      let key, kdfSalt = null;
      if (hasPassword && password) {
        kdfSalt = E2E.generateSalt();
        key     = await E2E.deriveKey(password, kdfSalt);
      } else {
        key = await E2E.generateKey();
      }

      const { ciphertext, nonce } = await E2E.encrypt(content, key);

      const expiresIn  = parseInt(document.getElementById('expires_in').value) || null;
      const maxViews   = parseInt(document.getElementById('max_views').value)  || null;
      const webhookUrl = whToggle.checked ? (document.getElementById('webhook_url').value.trim() || null) : null;

      const payload = {
        content:     ciphertext,
        nonce:       nonce,
        kdf_salt:    kdfSalt,
        language:    langSelect.value || null,
        expires_in:  expiresIn,
        burn:        document.getElementById('burnToggle').checked,
        max_views:   maxViews,
        webhook_url: webhookUrl,
      };

      const resp = await fetch('/api/v1/pastes', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        showFormError(err.detail || `Server error ${resp.status}.`);
        btn.disabled = false;
        return;
      }

      const result = await resp.json();

      // Fragment: KEY~DELETE_TOKEN (non-password) or ~DELETE_TOKEN (password)
      const fragment = (hasPassword && password)
        ? `~${result.delete_token}`
        : `${await E2E.exportKey(key)}~${result.delete_token}`;

      // Flag the paste view to greet the creator with a prominent Copy URL.
      // sessionStorage survives the redirect and is scoped to the tab.
      try { sessionStorage.setItem('ghostbit:justCreated:' + result.id, '1'); } catch (_) {}

      window.location.href = `/${result.id}#${fragment}`;

    } catch (err) {
      console.error('submitPaste error:', err);
      showFormError(err?.message ? `Error: ${err.message}` : 'Unexpected error. Please try again.');
      btn.disabled = false;
    }
  }

  document.getElementById('pasteForm').addEventListener('submit', e => {
    e.preventDefault();
    submitPaste();
  });

  // ── "/" focuses the editor (like GitHub) ─────────────────────────────────
  document.addEventListener('keydown', e => {
    if (e.key !== '/') return;
    const tag = document.activeElement?.tagName;
    if (tag === 'TEXTAREA' || tag === 'INPUT' || tag === 'SELECT') return;
    // CodeMirror's active input is a contenteditable inside the editor host.
    if (document.getElementById('cmHost').contains(document.activeElement)) return;
    e.preventDefault();
    cm.focus();
    cm.setCursor(cm.lineCount(), 0);
  });

  // ── Hero toggle ──────────────────────────────────────────────────────────
  (function() {
    const heroWrap = document.getElementById('heroWrap');
    const btn      = document.getElementById('heroToggle');
    const hidden   = localStorage.getItem('heroHidden') === '1';

    function setHidden(h) {
      heroWrap.classList.toggle('hero-hidden', h);
      btn.title = h ? 'Show terminal' : 'Hide terminal';
      btn.querySelector('svg').style.transform = h ? 'rotate(180deg)' : '';
      localStorage.setItem('heroHidden', h ? '1' : '0');
    }

    setHidden(hidden);
    btn.addEventListener('click', () => setHidden(!heroWrap.classList.contains('hero-hidden')));
  })();

  // ── Terminal typewriter (desktop only) ───────────────────────────────────
  (function() {
    if (window.matchMedia('(max-width: 760px)').matches) return;
    const messages = [
      'ghostbit paste main.py --burn',
      'cat secrets.env | gbit --expires 3600',
      'gbit config set server https://paste.example.com',
      'echo "end-to-end encrypted" | gbit',
      'gbit deploy.sh --max-views 1 -p',
      'curl api.example.com/data | gbit --lang json',
      'git diff HEAD~1 | gbit --lang diff',
    ];

    const el     = document.getElementById('terminalText');
    let msgIdx   = 0;
    let charIdx  = 0;
    let deleting = false;

    const TYPE_SPEED   = 55;
    const DELETE_SPEED = 25;
    const PAUSE_END    = 2200;
    const PAUSE_START  = 400;

    function tick() {
      const msg = messages[msgIdx];

      if (!deleting) {
        el.textContent = msg.slice(0, ++charIdx);
        if (charIdx === msg.length) {
          deleting = true;
          setTimeout(tick, PAUSE_END);
          return;
        }
      } else {
        el.textContent = msg.slice(0, --charIdx);
        if (charIdx === 0) {
          deleting = false;
          msgIdx   = (msgIdx + 1) % messages.length;
          setTimeout(tick, PAUSE_START);
          return;
        }
      }

      setTimeout(tick, deleting ? DELETE_SPEED : TYPE_SPEED);
    }

    setTimeout(tick, 600);
  })();

})();
