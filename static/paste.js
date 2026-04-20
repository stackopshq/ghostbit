/**
 * Paste view — fetches ciphertext, decrypts it client-side, and renders
 * the result in CodeMirror with a burn / max-views notice strip.
 *
 * Per-request bootstrap data (paste id, language, CodeMirror mode map,
 * extension map) is passed via a <script type="application/json"> block
 * so this file can stay static and cacheable.
 */
(async () => {
  'use strict';

  const meta     = JSON.parse(document.getElementById('paste-meta').textContent);
  const CM_MODE  = meta.cm_mode_map;
  const EXT_MAP  = meta.extension_map;
  const LANGUAGE = meta.language;
  const IS_MD    = meta.is_markdown;

  let cm = null; // lazy — only instantiate after decryption

  // ── Fragment parsing ─────────────────────────────────────────────────────
  // Format: KEY_B64URL~DELETE_TOKEN  (non-password)
  //         ~DELETE_TOKEN            (password)
  const fragment    = window.location.hash.slice(1);
  const tildeIdx    = fragment.indexOf('~');
  const keyPart     = tildeIdx >= 0 ? fragment.slice(0, tildeIdx) : fragment;
  const deleteToken = tildeIdx >= 0 ? fragment.slice(tildeIdx + 1) : '';

  // ── State helpers ────────────────────────────────────────────────────────
  function showState(id) {
    ['statePassword', 'stateError', 'statePaste'].forEach(s => {
      document.getElementById(s).style.display = (s === id) ? '' : 'none';
    });
  }

  function showError(msg) {
    document.getElementById('errorMsg').textContent = msg;
    showState('stateError');
  }

  // ── Fetch ciphertext from API (this is the "view" event server-side) ─────
  async function fetchCiphertext() {
    const resp = await fetch(`/api/v1/pastes/${meta.id}`);
    if (resp.status === 404) throw new Error('This paste has expired or no longer exists.');
    if (!resp.ok) throw new Error(`Server error ${resp.status}.`);
    return resp.json();
  }

  // ── Render decrypted paste ───────────────────────────────────────────────
  function renderPaste(plaintext, apiData) {
    const mode = (LANGUAGE && CM_MODE[LANGUAGE] !== undefined) ? CM_MODE[LANGUAGE] : null;

    // Burn notice: shown if paste was burned (burn flag or max_views reached)
    const burned = apiData.burn || (apiData.max_views && apiData.view_count >= apiData.max_views);
    if (burned) document.getElementById('burnNotice').style.display = '';

    // ── Dynamic conditions after | ───────────────────────────────────────
    const conditions = [];

    if (apiData.max_views) {
      const left = apiData.max_views - apiData.view_count;
      if (left > 0) conditions.push(`${left} view${left > 1 ? 's' : ''} left`);
    }

    if (apiData.expires_at) {
      const delta = apiData.expires_at - Math.floor(Date.now() / 1000);
      if (delta > 0) {
        let label;
        if (delta < 3600)       label = `${Math.floor(delta / 60)}m left`;
        else if (delta < 86400) label = `${Math.floor(delta / 3600)}h left`;
        else                    label = `${Math.floor(delta / 86400)}d left`;
        conditions.push(label);
      }
    }

    const slot = document.getElementById('pasteConditions');
    if (conditions.length > 0) {
      slot.innerHTML =
        `<span class="paste-conditions-sep">|</span>` +
        conditions.map(c => `<span class="badge badge-condition">${c}</span>`).join('');
    }

    // Show Raw button
    const rawBtn = document.getElementById('rawBtn');
    if (rawBtn) rawBtn.style.display = '';

    // Show Download button
    const dlBtn = document.getElementById('downloadBtn');
    if (dlBtn) dlBtn.style.display = '';

    if (deleteToken) {
      const notice = document.getElementById('ownerNotice');
      notice.style.display = '';
      document.getElementById('deleteForm').style.display  = '';
      document.getElementById('deleteKey').value = deleteToken;

      // Fresh from the editor → green "created" treatment so the Copy URL
      // button is impossible to miss. Consume the flag so revisits revert
      // to the standard owner notice.
      const flagKey = 'ghostbit:justCreated:' + meta.id;
      try {
        if (sessionStorage.getItem(flagKey)) {
          notice.classList.add('just-created');
          document.getElementById('ownerNoticeTitle').textContent = 'Paste created.';
          sessionStorage.removeItem(flagKey);
        }
      } catch (_) {}
    }

    // Show the paste container FIRST so CodeMirror measures a real viewport.
    // Instantiating CM on a display:none host produces a 0-height editor that
    // renders blank even after the container becomes visible.
    showState('statePaste');

    cm = CodeMirror(document.getElementById('cmHost'), {
      value:            plaintext,
      mode,
      theme:            'dracula',
      lineNumbers:      true,
      lineWrapping:     false,
      readOnly:         'nocursor',
      matchBrackets:    true,
      styleActiveLine:  false,
      indentUnit:       2,
      tabSize:          2,
    });
    cm.refresh();
  }

  // ── Action handlers ──────────────────────────────────────────────────────

  function openRaw() {
    const text = cm ? cm.getValue() : '';
    const blob = new Blob([text], { type: 'text/plain; charset=utf-8' });
    window.open(URL.createObjectURL(blob), '_blank');
  }

  function downloadContent() {
    const text = cm ? cm.getValue() : '';
    // Empty string for extensionless slugs (makefile, dockerfile); fall back to '.txt'.
    const ext = (LANGUAGE && EXT_MAP[LANGUAGE]) ? EXT_MAP[LANGUAGE] : '.txt';
    const filename = meta.id + ext;
    const blob = new Blob([text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function copyUrl() {
    const label = document.getElementById('ownerCopyLabel');
    const flash = () => {
      if (!label) return;
      label.textContent = 'Copied!';
      setTimeout(() => { label.textContent = 'Copy URL'; }, 2000);
    };
    if (navigator.clipboard) {
      navigator.clipboard.writeText(window.location.href).then(flash).catch(flash);
    } else {
      flash();
    }
  }

  // CodeMirror handles its own copy event cleanly (plain text, no styled HTML).
  function copyContent() {
    const text = cm ? cm.getValue() : '';
    const btn  = document.getElementById('copyBtn');
    const stateCopy  = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><span>Copy content</span>`;
    const stateDone  = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg><span>Copied!</span>`;
    const done = () => {
      btn.innerHTML = stateDone;
      setTimeout(() => { btn.innerHTML = stateCopy; }, 2000);
    };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done).catch(() => _fallbackCopy(text, done));
    else _fallbackCopy(text, done);
  }

  function _fallbackCopy(text, cb) {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.cssText = 'position:fixed;opacity:0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); cb(); } finally { document.body.removeChild(ta); }
  }

  // Bind listeners up-front on the (hidden) controls in the paste shell.
  // They're inert until `renderPaste` reveals the container.
  document.getElementById('copyBtn').addEventListener('click', copyContent);
  document.getElementById('rawBtn').addEventListener('click', openRaw);
  document.getElementById('downloadBtn').addEventListener('click', downloadContent);
  document.getElementById('ownerCopyBtn').addEventListener('click', copyUrl);
  document.getElementById('deleteForm').addEventListener('submit', (e) => {
    if (!confirm('Delete this paste?')) e.preventDefault();
  });

  // ── Main decryption flow ─────────────────────────────────────────────────
  if (!meta.has_password) {
    if (!keyPart) {
      showError('Decryption key missing from URL. Make sure you copied the full link including the # fragment.');
      return;
    }
    try {
      const [key, apiData] = await Promise.all([
        E2E.importKey(keyPart),
        fetchCiphertext(),
      ]);
      const plaintext = await E2E.decrypt(apiData.content, apiData.nonce, key);
      renderPaste(plaintext, apiData);
    } catch (err) {
      showError(err.message || 'Decryption failed. The URL may be incomplete or the paste may have been tampered with.');
    }

  } else {
    // Fetch ciphertext first (we need kdf_salt before we can show the password form)
    let apiData;
    try {
      apiData = await fetchCiphertext();
    } catch (err) {
      showError(err.message);
      return;
    }

    showState('statePassword');
    const pwForm  = document.getElementById('pwForm');
    const pwInput = document.getElementById('pwInput');
    const pwError = document.getElementById('pwError');

    pwForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const password = pwInput.value;
      if (!password) return;

      const btn = pwForm.querySelector('[type=submit]');
      btn.disabled = true;
      pwError.style.display = 'none';

      try {
        const key       = await E2E.deriveKey(password, apiData.kdf_salt);
        const plaintext = await E2E.decrypt(apiData.content, apiData.nonce, key);
        renderPaste(plaintext, apiData);
      } catch {
        pwError.style.display = '';
        pwInput.value = '';
        pwInput.focus();
        btn.disabled = false;
      }
    });
  }

  // ── Markdown tab switcher ─────────────────────────────────────────────────
  if (IS_MD && typeof marked !== 'undefined') {
    marked.setOptions({ breaks: true, gfm: true });

    function switchTab(tab) {
      // The tab-switcher buttons live inside #viewCode > .paste-inbar, so
      // hiding #viewCode itself would hide the "Code" button with it —
      // trapping the user in preview. Toggle only the editor body and the
      // preview pane; the header (paste-id, badges, tabs, action buttons)
      // stays visible in both modes.
      const codeBody    = document.querySelector('#viewCode .paste-body');
      const viewPreview = document.getElementById('viewPreview');
      const tabCode     = document.getElementById('tabCode');
      const tabPreview  = document.getElementById('tabPreview');

      if (tab === 'preview') {
        const dirty = marked.parse(cm ? cm.getValue() : '');
        document.getElementById('mdBody').innerHTML = DOMPurify.sanitize(dirty);
        codeBody.style.display    = 'none';
        viewPreview.style.display = '';
        tabCode.classList.remove('active');
        tabPreview.classList.add('active');
      } else {
        codeBody.style.display    = '';
        viewPreview.style.display = 'none';
        tabCode.classList.add('active');
        tabPreview.classList.remove('active');
      }
    }

    document.getElementById('tabCode').addEventListener('click', () => switchTab('code'));
    document.getElementById('tabPreview').addEventListener('click', () => switchTab('preview'));
  }
})();
