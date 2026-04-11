/**
 * E2E encryption — AES-256-GCM (Web Crypto API)
 *
 * Non-password pastes : random key stored in URL #fragment (never sent to server).
 * Password pastes     : key derived via PBKDF2-SHA256 (600 000 iterations).
 *
 * Fragment format: KEY_B64URL~DELETE_TOKEN   (non-password)
 *                  ~DELETE_TOKEN              (password)
 */
const E2E = (() => {
  const ALGO        = { name: 'AES-GCM', length: 256 };
  const PBKDF2_ITER = 600_000;

  /** Generate a fresh random AES-256 key. */
  async function generateKey() {
    return crypto.subtle.generateKey(ALGO, true, ['encrypt', 'decrypt']);
  }

  /** Encrypt a plaintext string. Returns { ciphertext: base64, nonce: base64 }. */
  async function encrypt(plaintext, key) {
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt(
      { name: 'AES-GCM', iv: nonce },
      key,
      new TextEncoder().encode(plaintext)
    );
    return { ciphertext: _b64(new Uint8Array(ct)), nonce: _b64(nonce) };
  }

  /** Decrypt base64 ciphertext+nonce. Throws DOMException on wrong key/tampered data. */
  async function decrypt(ciphertextB64, nonceB64, key) {
    const pt = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: _unb64(nonceB64) },
      key,
      _unb64(ciphertextB64)
    );
    return new TextDecoder().decode(pt);
  }

  /** Export a CryptoKey to a base64url string safe for URL fragments. */
  async function exportKey(key) {
    const raw = await crypto.subtle.exportKey('raw', key);
    return _b64url(new Uint8Array(raw));
  }

  /** Import a base64url string as a decryption-only CryptoKey. */
  async function importKey(b64url) {
    return crypto.subtle.importKey('raw', _unb64url(b64url), ALGO, false, ['decrypt']);
  }

  /** Generate a random 16-byte PBKDF2 salt (base64-encoded). */
  function generateSalt() {
    return _b64(crypto.getRandomValues(new Uint8Array(16)));
  }

  /** Derive an AES-256 key from a password + base64 salt via PBKDF2-SHA256. */
  async function deriveKey(password, saltB64) {
    const mat = await crypto.subtle.importKey(
      'raw', new TextEncoder().encode(password), 'PBKDF2', false, ['deriveKey']
    );
    return crypto.subtle.deriveKey(
      { name: 'PBKDF2', salt: _unb64(saltB64), iterations: PBKDF2_ITER, hash: 'SHA-256' },
      mat, ALGO, false, ['encrypt', 'decrypt']
    );
  }

  // ── Encoding helpers ──────────────────────────────────────────────────────

  function _b64(u8) {
    let s = '';
    for (let i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
    return btoa(s);
  }

  function _unb64(s) {
    const bin = atob(s);
    const u8  = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    return u8;
  }

  function _b64url(u8) {
    return _b64(u8).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function _unb64url(s) {
    const b64 = s.replace(/-/g, '+').replace(/_/g, '/');
    const pad = (4 - b64.length % 4) % 4;
    return _unb64(b64 + '='.repeat(pad));
  }

  return { generateKey, encrypt, decrypt, exportKey, importKey, generateSalt, deriveKey };
})();
