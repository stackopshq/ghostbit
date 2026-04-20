/**
 * Footer star counter — reads the GitHub repo stargazer count once per
 * hour per browser and caches it in localStorage to stay polite with
 * the API (unauthenticated rate limit is 60/h/IP).
 */
(function () {
  const el    = document.getElementById('footerStarCount');
  const key   = 'gb_stars';
  const tsKey = 'gb_stars_ts';
  const TTL   = 3600 * 1000;

  function show(n) {
    if (el && n != null) el.textContent = n >= 1000 ? (n / 1000).toFixed(1) + 'k' : n;
  }

  const cached = localStorage.getItem(key);
  const ts     = parseInt(localStorage.getItem(tsKey) || '0');
  if (cached && Date.now() - ts < TTL) {
    show(parseInt(cached));
    return;
  }

  fetch('https://api.github.com/repos/stackopshq/ghostbit')
    .then(r => r.json())
    .then(d => {
      if (d.stargazers_count == null) return;
      localStorage.setItem(key, d.stargazers_count);
      localStorage.setItem(tsKey, Date.now());
      show(d.stargazers_count);
    })
    .catch(() => {});
})();
