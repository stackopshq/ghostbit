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

  /** Encrypt a plaintext string OR raw bytes. Returns { ciphertext, nonce } (both base64). */
  async function encrypt(input, key) {
    const nonce = crypto.getRandomValues(new Uint8Array(12));
    const data  = typeof input === 'string' ? new TextEncoder().encode(input) : input;
    const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce }, key, data);
    return { ciphertext: _b64(new Uint8Array(ct)), nonce: _b64(nonce) };
  }

  /** Decrypt base64 ciphertext+nonce, returning raw bytes. */
  async function decryptBytes(ciphertextB64, nonceB64, key) {
    const pt = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: _unb64(nonceB64) }, key, _unb64(ciphertextB64)
    );
    return new Uint8Array(pt);
  }

  /** Decrypt base64 ciphertext+nonce as a UTF-8 string. */
  async function decrypt(ciphertextB64, nonceB64, key) {
    return new TextDecoder().decode(await decryptBytes(ciphertextB64, nonceB64, key));
  }

  /** Gzip a string into raw bytes, using the browser's CompressionStream. */
  async function gzipString(plaintext) {
    const stream = new Blob([plaintext]).stream().pipeThrough(new CompressionStream('gzip'));
    return new Uint8Array(await new Response(stream).arrayBuffer());
  }

  /** Gunzip raw bytes back into a UTF-8 string. */
  async function gunzipToString(bytes) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return await new Response(stream).text();
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

  // Argon2id parameters MUST match cli/_crypto.py and the ADR 0002 table —
  // a drift here silently fails decryption of CLI-created argon2id pastes.
  const ARGON2_PARAMS = { parallelism: 1, iterations: 2, memorySize: 19_456, hashLength: 32 };

  /** Derive an AES-256 key from a password + base64 salt via Argon2id.
   *  Requires the hash-wasm bundle to be already loaded on the page
   *  (templates ship it under /static/hash-wasm-argon2.umd.min.js). */
  async function deriveKeyArgon2id(password, saltB64) {
    if (typeof window.hashwasm === 'undefined' || !window.hashwasm.argon2id) {
      throw new Error('Argon2id library not loaded — refresh the page.');
    }
    const raw = await window.hashwasm.argon2id({
      password,
      salt: _unb64(saltB64),
      outputType: 'binary',
      ...ARGON2_PARAMS,
    });
    return crypto.subtle.importKey('raw', raw, ALGO, false, ['encrypt', 'decrypt']);
  }

  /** Dispatch to the right KDF based on the paste's kdf hint. */
  async function deriveKeyFor(kdf, password, saltB64) {
    if (kdf === 'argon2id') return deriveKeyArgon2id(password, saltB64);
    return deriveKey(password, saltB64);  // pbkdf2-sha256 (default)
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

  return {
    generateKey, encrypt, decrypt, decryptBytes,
    exportKey, importKey, generateSalt,
    deriveKey, deriveKeyArgon2id, deriveKeyFor,
    gzipString, gunzipToString,
  };
})();
