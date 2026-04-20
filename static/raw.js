/**
 * Raw paste view — decrypts the ciphertext and renders it as plain text
 * inside a single <pre>. Kept intentionally tiny; the richer interactive
 * view lives in paste.js.
 */
(async () => {
  'use strict';

  const meta     = JSON.parse(document.getElementById('paste-meta').textContent);
  const fragment = window.location.hash.slice(1);
  const keyPart  = fragment.split('~')[0];

  if (!keyPart) {
    document.getElementById('error').textContent =
      'Decryption key missing from URL. Make sure you copied the full link including the #fragment.';
    return;
  }

  try {
    const [key, data] = await Promise.all([
      E2E.importKey(keyPart),
      fetch(`/api/v1/pastes/${meta.id}`).then(r => {
        if (r.status === 404) throw new Error('Paste not found or expired.');
        if (!r.ok) throw new Error(`Server error ${r.status}.`);
        return r.json();
      }),
    ]);
    const plaintext = await E2E.decrypt(data.content, data.nonce, key);
    const pre = document.getElementById('content');
    pre.textContent = plaintext;
    pre.style.display = '';
  } catch (err) {
    document.getElementById('error').textContent =
      err.message || 'Decryption failed. The URL may be incomplete or the paste may have been tampered with.';
  }
})();
