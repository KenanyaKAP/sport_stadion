# Sport Stadion

Backend + storefront dummy untuk toko perlengkapan olahraga. Dibuat sebagai "third-party retailer" yang nanti akan dibungkus menjadi MCP server untuk Conversify.

- **Backend:** FastAPI + SQLAlchemy + SQLite (`sportstadion.db`)
- **Frontend:** HTML + vanilla JS di `web/`, di-serve oleh FastAPI yang sama. Website hanya memakai REST API `/api/...`, jadi MCP nanti cukup memanggil endpoint yang sama.
- **Python:** 3.13.13 (via pyenv, lihat `.python-version`), virtualenv di `.venv/`

## Menjalankan

```bash
cd backend_sportstadion
source .venv/bin/activate        # fish: source .venv/bin/activate.fish
pip install -r requirements.txt  # sekali saja
uvicorn app.main:app --reload --host 0.0.0.0 --port 8765
```

`--host 0.0.0.0` diperlukan supaya server bisa diakses dari perangkat lain (iPhone). Tanpa itu server hanya bisa diakses dari Mac ini.

- Website: http://127.0.0.1:8765
- Dokumentasi API (Swagger): http://127.0.0.1:8765/docs

Database dibuat dan diisi data contoh otomatis saat pertama kali start. Untuk reset ke data awal:

```bash
python -m app.seed --reset
```

Test: `pytest`

> Port 8000 di mesin ini sudah dipakai nginx, makanya contoh di atas pakai 8765.

## Data contoh

29 produk, 347 varian (SKU = produk × warna × ukuran) di 9 kategori: sepatu lari, sepatu bola/futsal, sepatu basket, jersey & kaos, celana, bola, raket, tas, aksesoris. Setiap produk punya deskripsi, material, perawatan, highlights, spesifikasi, dan panduan ukuran (per kategori). Beberapa varian sengaja stoknya 0, dan beberapa produk harganya beda per ukuran (mis. botol 500 ml / 750 ml / 1 L).

Kode promo: `STADION10` (10%, maks. Rp100.000, min. Rp200.000), `HEMAT50` (Rp50.000, min. Rp500.000), `WELCOME` (15%, maks. Rp150.000).

Semua harga dalam Rupiah (integer).

## API

| Method | Endpoint | Fungsi |
|---|---|---|
| GET | `/api/info` | Handshake: nama toko, versi API, jumlah produk (dipakai Conversify untuk cek koneksi) |
| GET | `/api/categories` | Daftar kategori + jumlah produk |
| GET | `/api/brands` | Daftar brand |
| GET | `/api/facets` | Semua nilai filter (kategori, brand, olahraga, gender, warna, ukuran, rentang harga) |
| GET | `/api/products` | Cari & filter: `q, category, brand, sport, gender, color, size, min_price, max_price, in_stock, sort, page, page_size` |
| GET | `/api/products/{slug}` | Detail lengkap + semua varian & stok |
| GET | `/api/variants/{sku}` | Cek satu SKU (harga, stok) |
| POST | `/api/carts` | Buat keranjang baru |
| GET | `/api/carts/{id}?shipping_method=` | Lihat keranjang + total (opsional termasuk ongkir) |
| POST | `/api/carts/{id}/items` | Tambah item (`variant_id` atau `sku`, `quantity`) |
| PATCH | `/api/carts/{id}/items/{item_id}` | Ubah jumlah (0 = hapus) |
| DELETE | `/api/carts/{id}/items/{item_id}` | Hapus item |
| POST / DELETE | `/api/carts/{id}/promo` | Pasang / lepas kode promo |
| GET | `/api/shipping-methods` | `regular`, `express`, `same_day`, `pickup` |
| GET | `/api/payment-methods` | `bank_transfer`, `e_wallet`, `credit_card` |
| POST | `/api/checkout` | Ubah keranjang jadi pesanan (stok berkurang, keranjang dihapus) |
| GET | `/api/orders?email=` | Riwayat pesanan per email |
| GET | `/api/orders/{order_number}?email=` | Detail pesanan (email sebagai cek kepemilikan) |
| POST | `/api/orders/{order_number}/pay` | Simulasi pembayaran berhasil |
| POST | `/api/orders/{order_number}/cancel` | Batalkan pesanan (stok dikembalikan) |

Status pesanan: `pending_payment → paid → shipped → delivered`, atau `cancelled`.

### Contoh alur lengkap (curl)

```bash
B=http://127.0.0.1:8765/api
CART=$(curl -s -X POST $B/carts | jq -r .id)
curl -s "$B/products?q=sepatu lari&color=Hitam&size=42" | jq '.items[].slug'
curl -s -X POST $B/carts/$CART/items -H 'content-type: application/json' -d '{"sku":"VAG3-HIT-42","quantity":1}'
curl -s -X POST $B/checkout -H 'content-type: application/json' -d "{
  \"cart_id\": \"$CART\",
  \"customer\": {\"name\": \"Budi\", \"email\": \"budi@example.com\", \"phone\": \"081234567890\"},
  \"shipping_address\": {\"street\": \"Jl. Sudirman 1\", \"city\": \"Jakarta\", \"province\": \"DKI Jakarta\", \"postal_code\": \"12190\"},
  \"shipping_method\": \"regular\", \"payment_method\": \"bank_transfer\"}"
```

### Deep link ke website

- `/product/{slug}?color=Hitam&size=42`: buka produk dengan warna/ukuran sudah terpilih
- `/cart?cart={cart_id}`: buka keranjang tertentu di browser (berguna kalau agent sudah mengisi keranjang dan user mau lanjut checkout sendiri)
- `/order/{order_number}?email=...`: halaman status pesanan

## Struktur

```
app/
  main.py        # FastAPI app, routing halaman web
  database.py    # engine SQLite (override via env SPORTSTADION_DB_URL)
  models.py      # tabel: categories, brands, products, product_variants, carts, cart_items, orders, order_items, promo_codes
  schemas.py     # Pydantic request/response
  services.py    # logika harga, promo, ongkir, serialisasi
  seed.py        # data contoh
  routers/       # catalog.py, cart.py, orders.py
web/             # index, product, cart, checkout, order, orders + static/app.js, static/styles.css
tests/           # test end-to-end API
```
