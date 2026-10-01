// Shared storefront helpers: API client, cart state, formatting, header/footer, product art.

const API = {
  async req(method, path, body) {
    const res = await fetch(`/api${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = res.status === 204 ? null : await res.json().catch(() => null);
    if (!res.ok) {
      let msg = data?.detail ?? `Request failed (${res.status})`;
      if (Array.isArray(msg)) msg = msg.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join(", ");
      const err = new Error(msg);
      err.status = res.status;
      err.detail = data?.detail;
      throw err;
    }
    return data;
  },
  get: (p) => API.req("GET", p),
  post: (p, b) => API.req("POST", p, b ?? {}),
  patch: (p, b) => API.req("PATCH", p, b),
  del: (p) => API.req("DELETE", p),
};

// ---------- Cart (id persisted per browser) ----------
const Cart = {
  KEY: "sportstadion.cart_id",
  id() {
    // A `?cart=<id>` link (e.g. handed out by the Conversify agent) adopts that cart in this browser.
    const fromUrl = new URLSearchParams(location.search).get("cart");
    if (fromUrl) this.setId(fromUrl);
    try { return localStorage.getItem(this.KEY) ?? fromUrl; } catch { return fromUrl; }
  },
  setId(id) {
    try { id ? localStorage.setItem(this.KEY, id) : localStorage.removeItem(this.KEY); } catch {}
  },
  async get(shipping) {
    const id = this.id();
    if (!id) return null;
    try {
      return await API.get(`/carts/${id}${shipping ? `?shipping_method=${shipping}` : ""}`);
    } catch (e) {
      if (e.status === 404) { this.setId(null); return null; }
      throw e;
    }
  },
  async ensure() {
    const existing = await this.get();
    if (existing) return existing;
    const cart = await API.post("/carts");
    this.setId(cart.id);
    return cart;
  },
  async add(variantId, quantity) {
    const cart = await this.ensure();
    const updated = await API.post(`/carts/${cart.id}/items`, { variant_id: variantId, quantity });
    updateBadge(updated);
    return updated;
  },
};

// ---------- Formatting ----------
const rupiah = (n) => "Rp" + Math.round(n).toLocaleString("id-ID");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const GENDER_LABEL = { men: "Pria", women: "Wanita", unisex: "Unisex", kids: "Anak" };
const SPORT_LABEL = {
  running: "Lari", "trail running": "Trail Running", football: "Sepak Bola", futsal: "Futsal",
  basketball: "Basket", training: "Training", volleyball: "Voli", badminton: "Badminton",
};
const sportLabel = (s) => SPORT_LABEL[s] ?? s;
const priceRange = (p) => (p.price_min === p.price_max ? rupiah(p.price_min) : `${rupiah(p.price_min)} – ${rupiah(p.price_max)}`);
const stars = (r) => `<span class="star">★</span> ${r.toFixed(1)}`;

// ---------- Product illustrations (SVG drawn per category, tinted by variant colour) ----------
function hexToRgb(h) { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; }
function mix(h1, h2, t) {
  const a = hexToRgb(h1), b = hexToRgb(h2);
  return "#" + a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, "0")).join("");
}
function lum(h) { const [r, g, b] = hexToRgb(h); return (0.299 * r + 0.587 * g + 0.114 * b) / 255; }

const SHAPES = {
  shoe: (c, a, o) => `
    <path d="M24 134 L30 98 Q33 86 46 88 L66 92 Q82 70 100 72 L120 77 Q134 100 160 107 Q184 113 184 134 Z" fill="${c}" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <path d="M58 124 Q100 96 150 112" fill="none" stroke="${a}" stroke-width="7" stroke-linecap="round"/>
    <path d="M82 84 L92 98 M92 80 L102 94 M103 78 L112 91" stroke="${o}" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M20 136 L186 136 Q190 150 178 152 L32 152 Q18 150 20 136 Z" fill="#fafafa" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <path d="M26 146 L182 146" stroke="${o}" stroke-opacity=".25" stroke-width="2"/>`,
  boot: (c, a, o) => `
    <path d="M24 134 L30 98 Q33 86 46 88 L66 92 Q82 70 100 72 L120 77 Q134 100 160 107 Q184 113 184 134 Z" fill="${c}" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <path d="M60 110 L150 118 M70 122 L160 128" stroke="${a}" stroke-width="5" stroke-linecap="round"/>
    <path d="M82 84 L92 98 M92 80 L102 94 M103 78 L112 91" stroke="${o}" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M22 134 L186 134 Q188 142 180 143 L30 143 Q20 142 22 134 Z" fill="${mix(c, "#000000", .35)}" stroke="${o}" stroke-width="2.5"/>
    ${[38, 62, 120, 146, 170].map((x) => `<rect x="${x}" y="143" width="9" height="12" rx="2" fill="${mix(c, "#000000", .35)}" stroke="${o}" stroke-width="2"/>`).join("")}`,
  hightop: (c, a, o) => `
    <path d="M28 134 L32 58 Q34 48 46 48 L80 50 Q90 82 110 92 Q148 102 168 110 Q186 118 184 134 Z" fill="${c}" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <circle cx="56" cy="94" r="16" fill="${a}" opacity=".9"/>
    <path d="M78 60 L90 66 M80 72 L94 78 M84 84 L98 90" stroke="${o}" stroke-width="2.5" stroke-linecap="round"/>
    <path d="M110 116 Q140 108 176 120" fill="none" stroke="${a}" stroke-width="6" stroke-linecap="round"/>
    <path d="M22 136 L188 136 Q192 152 178 154 L32 154 Q18 152 22 136 Z" fill="#fafafa" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>`,
  shirt: (c, a, o) => `
    <path d="M62 38 L84 28 Q100 46 116 28 L138 38 L172 66 L154 90 L140 80 L140 172 L60 172 L60 80 L46 90 L28 66 Z" fill="${c}" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <path d="M84 28 Q100 46 116 28" fill="none" stroke="${a}" stroke-width="5"/>
    <path d="M60 110 L140 110" stroke="${a}" stroke-width="8" opacity=".85"/>
    <circle cx="122" cy="62" r="7" fill="${a}"/>`,
  shorts: (c, a, o) => `
    <path d="M48 52 L152 52 L164 156 L112 156 L100 96 L88 156 L36 156 Z" fill="${c}" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <rect x="48" y="44" width="104" height="14" rx="3" fill="${mix(c, "#000000", .25)}" stroke="${o}" stroke-width="2.5"/>
    <path d="M44 120 L40 150 M156 120 L160 150" stroke="${a}" stroke-width="6" stroke-linecap="round"/>
    <path d="M96 58 L94 76 M104 58 L106 76" stroke="${a}" stroke-width="2.5"/>`,
  ball: (c, a, o) => `
    <circle cx="100" cy="100" r="66" fill="${c}" stroke="${o}" stroke-width="2.5"/>
    <path d="M100 74 L124 92 L115 120 L85 120 L76 92 Z" fill="${a}"/>
    <path d="M100 74 L100 36 M124 92 L158 80 M115 120 L136 150 M85 120 L64 150 M76 92 L42 80" stroke="${a}" stroke-width="3"/>
    <path d="M100 36 Q82 40 70 48 M158 80 Q160 62 150 50 M136 150 Q154 140 162 122 M64 150 Q80 162 100 164 M42 80 Q38 98 44 118" stroke="${a}" stroke-width="3" fill="none"/>`,
  racket: (c, a, o) => `
    <defs><clipPath id="rh"><ellipse cx="100" cy="70" rx="40" ry="52"/></clipPath></defs>
    <g clip-path="url(#rh)" stroke="${o}" stroke-opacity=".35" stroke-width="1.5">
      ${Array.from({ length: 11 }, (_, i) => `<line x1="${60 + i * 8}" y1="10" x2="${60 + i * 8}" y2="130"/>`).join("")}
      ${Array.from({ length: 13 }, (_, i) => `<line x1="50" y1="${20 + i * 8}" x2="150" y2="${20 + i * 8}"/>`).join("")}
    </g>
    <ellipse cx="100" cy="70" rx="40" ry="52" fill="none" stroke="${c}" stroke-width="9"/>
    <ellipse cx="100" cy="70" rx="40" ry="52" fill="none" stroke="${o}" stroke-width="1.5" stroke-opacity=".4"/>
    <path d="M100 122 L100 150" stroke="${c}" stroke-width="5"/>
    <rect x="93" y="148" width="14" height="40" rx="5" fill="${a}" stroke="${o}" stroke-width="2"/>`,
  bag: (c, a, o) => `
    <path d="M76 52 Q76 30 100 30 Q124 30 124 52" fill="none" stroke="${o}" stroke-width="6"/>
    <rect x="46" y="48" width="108" height="130" rx="26" fill="${c}" stroke="${o}" stroke-width="2.5"/>
    <rect x="62" y="112" width="76" height="52" rx="14" fill="${mix(c, "#000000", .18)}" stroke="${o}" stroke-width="2"/>
    <path d="M70 124 L130 124" stroke="${a}" stroke-width="4" stroke-linecap="round"/>
    <rect x="88" y="70" width="24" height="10" rx="4" fill="${a}"/>`,
  bottle: (c, a, o) => `
    <rect x="80" y="22" width="40" height="22" rx="6" fill="${mix(c, "#000000", .3)}" stroke="${o}" stroke-width="2.5"/>
    <rect x="86" y="14" width="28" height="10" rx="4" fill="${a}" stroke="${o}" stroke-width="2"/>
    <path d="M78 44 L122 44 Q134 54 134 70 L134 168 Q134 182 120 182 L80 182 Q66 182 66 168 L66 70 Q66 54 78 44 Z" fill="${c}" stroke="${o}" stroke-width="2.5"/>
    <rect x="66" y="100" width="68" height="34" fill="${a}" opacity=".85"/>
    <path d="M76 70 L76 160" stroke="#ffffff" stroke-opacity=".35" stroke-width="5" stroke-linecap="round"/>`,
  sock: (c, a, o) => `
    <path d="M70 24 L124 24 L124 116 Q124 128 134 136 L158 152 Q172 164 160 178 Q150 188 134 180 L82 152 Q70 144 70 128 Z" fill="${c}" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <rect x="70" y="24" width="54" height="18" fill="${mix(c, "#000000", .15)}" stroke="${o}" stroke-width="2.5"/>
    <path d="M70 58 L124 58 M70 68 L124 68" stroke="${a}" stroke-width="5"/>
    <path d="M130 140 Q150 150 158 168" fill="none" stroke="${a}" stroke-width="10" stroke-linecap="round" opacity=".7"/>`,
  cap: (c, a, o) => `
    <path d="M40 120 Q40 56 100 56 Q160 56 160 120 Z" fill="${c}" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <path d="M100 56 L100 120 M70 64 Q60 90 62 120 M130 64 Q140 90 138 120" stroke="${o}" stroke-opacity=".3" stroke-width="2" fill="none"/>
    <path d="M36 120 L164 120 Q190 124 188 136 Q150 150 100 140 Q60 134 36 120 Z" fill="${mix(c, "#000000", .15)}" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <circle cx="100" cy="56" r="5" fill="${a}"/>
    <rect x="86" y="88" width="28" height="12" rx="3" fill="${a}"/>`,
  shuttle: (c, a, o) => `
    <path d="M70 40 L130 40 L114 130 L86 130 Z" fill="${c}" stroke="${o}" stroke-width="2.5" stroke-linejoin="round"/>
    <path d="M80 40 L92 130 M100 40 L100 130 M120 40 L108 130" stroke="${o}" stroke-opacity=".35" stroke-width="1.8"/>
    <path d="M74 70 L126 70 M78 100 L122 100" stroke="${a}" stroke-width="3"/>
    <path d="M84 130 L116 130 L116 142 Q116 168 100 168 Q84 168 84 142 Z" fill="#f2e6cf" stroke="${o}" stroke-width="2.5"/>`,
  box: (c, a, o) => `<rect x="50" y="50" width="100" height="100" rx="12" fill="${c}" stroke="${o}" stroke-width="2.5"/>`,
};

/** Returns an SVG string drawing `icon` in colour `hex`. */
function productArt(icon, hex = "#8a8f98", { bg = true } = {}) {
  const c = hex;
  const accent = lum(hex) > 0.6 ? "#1d1d1f" : lum(hex) < 0.25 ? "#d4f25a" : "#ffffff";
  const outline = "#1d1d1f";
  const bgFill = mix(hex, "#f2f3ef", lum(hex) > 0.85 ? 0.2 : 0.82);
  const shape = (SHAPES[icon] ?? SHAPES.box)(c, accent, outline);
  return `<svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    ${bg ? `<rect width="200" height="200" fill="${lum(hex) > 0.85 ? "#e6e8e3" : bgFill}"/>` : ""}
    <ellipse cx="100" cy="186" rx="70" ry="6" fill="#000" opacity=".08"/>
    ${shape}
  </svg>`;
}

const ICON_SVG = {
  search: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>`,
  cart: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h2l2.4 11.2a2 2 0 0 0 2 1.6h7.7a2 2 0 0 0 2-1.5L21 8H6"/><circle cx="10" cy="20" r="1.4"/><circle cx="17" cy="20" r="1.4"/></svg>`,
  check: `<svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5 10 17 19 7"/></svg>`,
};

// ---------- Layout chrome ----------
function renderChrome() {
  const header = document.createElement("header");
  header.className = "site-header";
  const q = new URLSearchParams(location.search).get("q") ?? "";
  header.innerHTML = `
    <div class="container">
      <a class="logo" href="/"><span class="logo-mark">⚽</span>SPORT<span class="accent">STADION</span></a>
      <form class="header-search" action="/" method="get" role="search">
        ${ICON_SVG.search}
        <input name="q" type="search" placeholder="Cari sepatu, jersey, raket…" value="${esc(location.pathname === "/" ? q : "")}" aria-label="Cari produk">
      </form>
      <nav class="nav-links">
        <a class="hide-sm" href="/orders">Pesanan Saya</a>
        <a class="hide-sm" href="/docs" target="_blank">API</a>
        <a class="cart-link" href="/cart" aria-label="Keranjang">${ICON_SVG.cart}<span class="cart-badge" id="cart-badge"></span></a>
      </nav>
    </div>`;
  document.body.prepend(header);

  const footer = document.createElement("footer");
  footer.className = "site-footer";
  footer.innerHTML = `<div class="container">
      <span>© 2026 Sport Stadion — toko dummy untuk pengembangan Conversify. Semua transaksi adalah simulasi.</span>
      <span><a href="/docs" target="_blank">Dokumentasi API</a></span>
    </div>`;
  document.body.append(footer);

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.id = "toast";
  document.body.append(toast);

  Cart.get().then(updateBadge).catch(() => {});
}

function updateBadge(cart) {
  const el = document.getElementById("cart-badge");
  if (el) el.textContent = cart?.item_count ? cart.item_count : "";
}

let toastTimer;
function toast(html, { error = false, ms = 3200 } = {}) {
  const el = document.getElementById("toast");
  el.innerHTML = html;
  el.classList.toggle("err", error);
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), ms);
}

document.addEventListener("DOMContentLoaded", renderChrome);
