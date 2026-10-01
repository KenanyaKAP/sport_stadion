"""Seed data for the Sport Stadion catalog.

Run `python -m app.seed --reset` to wipe and recreate the database.
Stock levels are generated with a fixed random seed so the data is reproducible.
"""

import random
import re
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import models

# ---------- Reference data ----------

C = {  # colour palette: name -> hex
    "Hitam": "#1d1d1f", "Putih": "#f5f5f2", "Merah": "#d62f2f", "Biru Navy": "#1f2f5c",
    "Biru Muda": "#5aa9e6", "Abu-abu": "#8a8f98", "Hijau Neon": "#9be22d", "Hijau Army": "#55613d",
    "Oranye": "#f2711c", "Kuning": "#f5c518", "Ungu": "#6f42c1", "Pink": "#ec6fa2",
    "Krem": "#e8dcc4", "Tosca": "#1fa39a", "Merah Marun": "#7a1f2b", "Silver": "#c4c8cc",
}

SHOE_CHART = {
    "title": "Panduan Ukuran Sepatu",
    "headers": ["EU", "UK", "US Pria", "US Wanita", "Panjang Kaki (cm)"],
    "rows": [
        ["30", "11.5K", "12K", "-", "18.5"], ["31", "12.5K", "13K", "-", "19.2"],
        ["32", "13K", "13.5K", "-", "19.8"], ["33", "1", "1.5Y", "-", "20.5"],
        ["34", "2", "2.5Y", "-", "21.2"], ["35", "2.5", "3Y", "-", "21.8"],
        ["36", "3.5", "4", "5.5", "22.5"], ["37", "4", "4.5", "6", "23.2"],
        ["38", "5", "5.5", "7", "23.8"], ["39", "6", "6.5", "8", "24.5"],
        ["40", "6.5", "7", "8.5", "25.2"], ["41", "7.5", "8", "9.5", "25.8"],
        ["42", "8", "8.5", "10", "26.5"], ["43", "9", "9.5", "11", "27.2"],
        ["44", "9.5", "10", "11.5", "27.8"], ["45", "10.5", "11", "12.5", "28.5"],
    ],
    "note": "Ukur panjang kaki dari tumit ke ujung jari terpanjang. Jika di antara dua ukuran, pilih yang lebih besar.",
}

APPAREL_CHART = {
    "title": "Panduan Ukuran Pakaian",
    "headers": ["Ukuran", "Lingkar Dada (cm)", "Lingkar Pinggang (cm)", "Panjang Badan (cm)"],
    "rows": [
        ["XS", "82-87", "66-71", "64"], ["S", "88-93", "72-77", "67"],
        ["M", "94-99", "78-83", "70"], ["L", "100-106", "84-90", "73"],
        ["XL", "107-113", "91-97", "76"], ["XXL", "114-121", "98-105", "79"],
    ],
    "note": "Model memakai ukuran M dengan tinggi 178 cm. Potongan regular fit kecuali disebutkan lain.",
}

SOCK_CHART = {
    "title": "Panduan Ukuran Kaos Kaki",
    "headers": ["Ukuran", "EU", "Panjang Kaki (cm)"],
    "rows": [["S", "36-39", "22.5-24.5"], ["M", "40-43", "25.2-27.2"], ["L", "44-46", "27.8-29.5"]],
}

CATEGORIES = [
    ("sepatu-lari", "Sepatu Lari", "Sepatu untuk road running, trail, dan latihan harian.", "shoe", SHOE_CHART),
    ("sepatu-bola", "Sepatu Bola & Futsal", "Sepatu sepak bola FG/AG dan futsal indoor.", "boot", SHOE_CHART),
    ("sepatu-basket", "Sepatu Basket", "Sepatu basket dengan cushioning dan dukungan pergelangan.", "hightop", SHOE_CHART),
    ("jersey-kaos", "Jersey & Kaos", "Atasan olahraga yang ringan dan cepat kering.", "shirt", APPAREL_CHART),
    ("celana", "Celana", "Celana pendek dan panjang untuk latihan dan pertandingan.", "shorts", APPAREL_CHART),
    ("bola", "Bola", "Bola sepak, futsal, basket, dan voli.", "ball", None),
    ("raket", "Raket", "Raket badminton, tenis, dan padel.", "racket", None),
    ("tas", "Tas", "Backpack, duffel, dan tas sepatu.", "bag", None),
    ("aksesoris", "Aksesoris", "Kaos kaki, topi, botol minum, dan perlengkapan lain.", "bottle", SOCK_CHART),
]

BRANDS = [
    ("velocita", "Velocita", "Italia", "Spesialis sepatu lari performa sejak 1978."),
    ("garuda-sport", "Garuda Sport", "Indonesia", "Brand lokal untuk sepak bola dan futsal, dirancang untuk iklim tropis."),
    ("kinetik", "Kinetik", "Indonesia", "Apparel olahraga harian yang terjangkau dan nyaman."),
    ("apex-pro", "Apex Pro", "Amerika Serikat", "Perlengkapan basket dan training untuk atlet kompetitif."),
    ("nordline", "Nordline", "Swedia", "Tas dan perlengkapan outdoor yang tahan lama."),
    ("shuttlecraft", "Shuttlecraft", "Jepang", "Raket dan perlengkapan badminton presisi tinggi."),
]

MEN_SHOES = ["39", "40", "41", "42", "43", "44", "45"]
WOMEN_SHOES = ["36", "37", "38", "39", "40", "41"]
KIDS_SHOES = ["30", "31", "32", "33", "34", "35"]
APPAREL = ["S", "M", "L", "XL", "XXL"]
WOMEN_APPAREL = ["XS", "S", "M", "L", "XL"]

SHOE_CARE = "Bersihkan dengan kain lembap dan sabun lembut. Jangan dicuci mesin. Keringkan di tempat teduh, jauh dari panas langsung."
APPAREL_CARE = "Cuci mesin air dingin maks. 30°C. Jangan gunakan pemutih atau pelembut. Jangan disetrika di bagian sablon. Jemur di tempat teduh."

# Each product: colours (names from C), sizes, optional per-size price deltas.
PRODUCTS = [
    # ---- Sepatu Lari ----
    dict(slug="velocita-aero-glide-3", name="Velocita Aero Glide 3", category="sepatu-lari", brand="velocita",
         sport="running", gender="men", price=1_499_000, compare=1_799_000, rating=4.7, reviews=842,
         colors=["Hitam", "Biru Navy", "Oranye"], sizes=MEN_SHOES,
         short="Sepatu lari harian dengan busa responsif untuk jarak 5K hingga half marathon.",
         description="Aero Glide 3 adalah sepatu andalan untuk lari harian. Midsole GlideFoam generasi baru memberikan pantulan energi 12% lebih tinggi dari versi sebelumnya, sementara upper engineered mesh menjaga kaki tetap sejuk di cuaca tropis. Outsole karet karbon di area tumit membuatnya awet hingga 800 km.",
         material="Upper: engineered mesh daur ulang. Midsole: GlideFoam (EVA + TPU). Outsole: karet karbon.",
         care=SHOE_CARE,
         highlights=["Midsole GlideFoam responsif", "Upper mesh breathable", "Outsole tahan hingga 800 km", "Insole OrthoLite bisa dilepas"],
         specs={"Berat": "265 g (ukuran 42)", "Heel-to-toe drop": "8 mm", "Stack height": "36 mm / 28 mm", "Tipe kaki": "Netral", "Permukaan": "Aspal, treadmill", "Fit": "True to size"}),
    dict(slug="velocita-aero-glide-3-women", name="Velocita Aero Glide 3 Women", category="sepatu-lari", brand="velocita",
         sport="running", gender="women", price=1_499_000, compare=1_799_000, rating=4.8, reviews=516,
         colors=["Pink", "Putih", "Tosca"], sizes=WOMEN_SHOES,
         short="Versi wanita Aero Glide 3 dengan last yang lebih ramping di tumit.",
         description="Dirancang ulang khusus bentuk kaki wanita: tumit lebih ramping, collar lebih empuk, dan busa yang sedikit lebih lembut untuk berat badan rata-rata pelari wanita. Cocok untuk lari santai pagi hingga latihan tempo.",
         material="Upper: engineered mesh daur ulang. Midsole: GlideFoam Soft. Outsole: karet karbon.",
         care=SHOE_CARE,
         highlights=["Last khusus wanita", "Busa GlideFoam Soft", "Reflektif 360° untuk lari malam"],
         specs={"Berat": "225 g (ukuran 38)", "Heel-to-toe drop": "8 mm", "Tipe kaki": "Netral", "Permukaan": "Aspal, treadmill", "Fit": "True to size"}),
    dict(slug="velocita-carbon-elite", name="Velocita Carbon Elite", category="sepatu-lari", brand="velocita",
         sport="running", gender="unisex", price=3_299_000, rating=4.9, reviews=213,
         colors=["Hijau Neon", "Putih"], sizes=["38", "39", "40", "41", "42", "43", "44"],
         short="Sepatu balap dengan pelat karbon full-length untuk mengejar personal best.",
         description="Carbon Elite adalah sepatu balap paling cepat dari Velocita. Pelat karbon full-length berbentuk sendok dipadukan dengan busa PEBA super ringan untuk dorongan maksimal di setiap langkah. Direkomendasikan untuk race day 10K sampai full marathon.",
         material="Upper: monofilament mesh ultra tipis. Midsole: PEBA + pelat karbon full-length. Outsole: karet grip tipis.",
         care=SHOE_CARE,
         highlights=["Pelat karbon full-length", "Busa PEBA super ringan", "Disetujui World Athletics"],
         specs={"Berat": "198 g (ukuran 42)", "Heel-to-toe drop": "8 mm", "Stack height": "40 mm / 32 mm", "Tipe kaki": "Netral", "Penggunaan": "Race day", "Fit": "Sedikit kecil, naik 0.5 ukuran"}),
    dict(slug="velocita-trail-ridge", name="Velocita Trail Ridge", category="sepatu-lari", brand="velocita",
         sport="trail running", gender="men", price=1_899_000, rating=4.6, reviews=187,
         colors=["Hijau Army", "Hitam"], sizes=MEN_SHOES,
         short="Sepatu trail dengan lug 5 mm dan rock plate untuk medan gunung.",
         description="Trail Ridge siap menghadapi tanah, batu, dan lumpur. Lug 5 mm multi-arah memberikan cengkeraman di tanjakan maupun turunan, rock plate melindungi telapak dari batu tajam, dan gusset tongue mencegah kerikil masuk.",
         material="Upper: ripstop mesh dengan lapisan TPU. Midsole: EVA padat + rock plate. Outsole: karet MegaGrip lug 5 mm.",
         care=SHOE_CARE,
         highlights=["Lug 5 mm multi-arah", "Rock plate pelindung", "Toe cap anti benturan", "Gaiter attachment"],
         specs={"Berat": "310 g (ukuran 42)", "Heel-to-toe drop": "6 mm", "Permukaan": "Trail, tanah, batu", "Waterproof": "Tidak (water-resistant)", "Fit": "True to size"}),
    dict(slug="kinetik-daily-run-kids", name="Kinetik Daily Run Kids", category="sepatu-lari", brand="kinetik",
         sport="running", gender="kids", price=399_000, rating=4.5, reviews=301,
         colors=["Biru Muda", "Pink", "Hitam"], sizes=KIDS_SHOES,
         short="Sepatu anak ringan dengan strap velcro, mudah dipakai sendiri.",
         description="Sepatu lari anak yang ringan dan fleksibel untuk sekolah dan bermain. Strap velcro memudahkan anak memakai sendiri, toe cap karet melindungi ujung sepatu dari aus.",
         material="Upper: mesh + sintetis. Midsole: EVA ringan. Outsole: karet non-marking.",
         care=SHOE_CARE,
         highlights=["Strap velcro", "Outsole non-marking", "Ringan untuk anak aktif"],
         specs={"Berat": "180 g (ukuran 32)", "Penutup": "Velcro", "Usia": "6-11 tahun"}),

    # ---- Sepatu Bola & Futsal ----
    dict(slug="garuda-striker-fg", name="Garuda Striker FG", category="sepatu-bola", brand="garuda-sport",
         sport="football", gender="men", price=1_199_000, compare=1_399_000, rating=4.6, reviews=655,
         colors=["Merah", "Hitam", "Putih"], sizes=MEN_SHOES,
         short="Sepatu bola firm ground dengan upper sintetis tipis untuk sentuhan bola presisi.",
         description="Striker FG dirancang untuk penyerang yang mengandalkan kecepatan dan tendangan akurat. Upper SpeedSkin tipis memberikan sentuhan bola yang natural, sementara konfigurasi stud campuran bulat dan pisau memberi traksi saat akselerasi dan berbelok tajam.",
         material="Upper: sintetis SpeedSkin. Soleplate: TPU. Stud: campuran bulat & blade.",
         care="Bersihkan tanah setelah dipakai. Isi dengan kertas koran agar bentuk terjaga. Jangan dijemur di bawah matahari langsung.",
         highlights=["Upper SpeedSkin ultra tipis", "Stud kombinasi untuk akselerasi", "Insole anti slip"],
         specs={"Berat": "210 g (ukuran 42)", "Permukaan": "Rumput alami (FG)", "Collar": "Low-cut", "Fit": "Sempit, pilih 0.5 ukuran lebih besar untuk kaki lebar"}),
    dict(slug="garuda-sala-pro-futsal", name="Garuda Sala Pro Futsal", category="sepatu-bola", brand="garuda-sport",
         sport="futsal", gender="men", price=699_000, rating=4.7, reviews=1204,
         colors=["Biru Navy", "Putih", "Kuning"], sizes=MEN_SHOES,
         short="Sepatu futsal indoor dengan outsole karet gum non-marking.",
         description="Sepatu futsal favorit pemain lokal. Upper kulit sintetis lembut di area sentuhan bola, outsole karet gum dengan pola herringbone untuk cengkeraman maksimal di lapangan vinyl maupun parket.",
         material="Upper: kulit sintetis + suede di toe. Outsole: karet gum non-marking.",
         care=SHOE_CARE,
         highlights=["Outsole gum non-marking", "Toe suede untuk kontrol bola", "Bantalan tumit EVA"],
         specs={"Berat": "280 g (ukuran 42)", "Permukaan": "Indoor (IC) – vinyl, parket, semen halus", "Fit": "True to size"}),
    dict(slug="garuda-junior-ag", name="Garuda Junior AG", category="sepatu-bola", brand="garuda-sport",
         sport="football", gender="kids", price=459_000, rating=4.4, reviews=222,
         colors=["Oranye", "Biru Muda"], sizes=KIDS_SHOES,
         short="Sepatu bola anak untuk rumput sintetis (AG) dengan stud pendek.",
         description="Sepatu bola untuk pemain muda di sekolah sepak bola. Stud pendek berongga aman untuk rumput sintetis dan mengurangi beban pada lutut.",
         material="Upper: sintetis. Soleplate: karet. Stud: pendek berongga.",
         care=SHOE_CARE,
         highlights=["Aman untuk rumput sintetis", "Tali + velcro", "Insole empuk"],
         specs={"Berat": "190 g (ukuran 33)", "Permukaan": "Rumput sintetis (AG)", "Usia": "6-12 tahun"}),

    # ---- Sepatu Basket ----
    dict(slug="apex-skyline-mid", name="Apex Skyline Mid", category="sepatu-basket", brand="apex-pro",
         sport="basketball", gender="men", price=1_799_000, rating=4.7, reviews=389,
         colors=["Hitam", "Putih", "Merah Marun"], sizes=MEN_SHOES,
         short="Sepatu basket mid-top dengan unit Air-Lift untuk pendaratan empuk.",
         description="Skyline Mid adalah sepatu basket all-rounder untuk guard maupun forward. Unit Air-Lift di tumit meredam benturan saat mendarat, sementara pola herringbone multi-arah memberikan stop-and-go yang tajam. Kerah mid-top dengan padding menjaga stabilitas pergelangan kaki.",
         material="Upper: mesh + overlay sintetis. Midsole: Phylon + unit Air-Lift di tumit. Outsole: karet solid herringbone.",
         care=SHOE_CARE,
         highlights=["Unit Air-Lift di tumit", "Kerah mid-top stabil", "Outsole herringbone untuk indoor & outdoor"],
         specs={"Berat": "395 g (ukuran 42)", "Cut": "Mid-top", "Posisi": "Guard / Forward", "Permukaan": "Indoor & outdoor", "Fit": "True to size"}),
    dict(slug="apex-court-low", name="Apex Court Low", category="sepatu-basket", brand="apex-pro",
         sport="basketball", gender="unisex", price=1_299_000, compare=1_499_000, rating=4.5, reviews=176,
         colors=["Putih", "Biru Muda"], sizes=["38", "39", "40", "41", "42", "43", "44", "45"],
         short="Sepatu basket low-top yang ringan untuk pemain cepat.",
         description="Court Low mengutamakan kecepatan: low-top yang ringan, court feel dekat dengan lantai, dan forefoot yang fleksibel. Juga nyaman dipakai sehari-hari.",
         material="Upper: knit sintetis. Midsole: busa ringan. Outsole: karet translucent.",
         care=SHOE_CARE,
         highlights=["Low-top ringan", "Court feel responsif", "Nyaman untuk lifestyle"],
         specs={"Berat": "340 g (ukuran 42)", "Cut": "Low-top", "Posisi": "Guard", "Permukaan": "Indoor", "Fit": "True to size"}),

    # ---- Jersey & Kaos ----
    dict(slug="kinetik-drycore-tee", name="Kinetik DryCore Tee", category="jersey-kaos", brand="kinetik",
         sport="training", gender="men", price=199_000, rating=4.6, reviews=2310,
         colors=["Hitam", "Putih", "Abu-abu", "Biru Navy", "Hijau Army"], sizes=APPAREL,
         short="Kaos training quick-dry dengan teknologi anti bau.",
         description="Kaos olahraga paling laris di Sport Stadion. Kain DryCore menyerap keringat dan cepat kering, dilapisi treatment anti bakteri sehingga tidak bau meski dipakai latihan berat. Potongan regular fit cocok untuk gym, lari, maupun sehari-hari.",
         material="100% poliester daur ulang DryCore, 140 gsm.",
         care=APPAREL_CARE,
         highlights=["Quick-dry", "Anti bau (silver ion)", "Jahitan flatlock anti lecet", "UPF 30+"],
         specs={"Fit": "Regular", "Berat kain": "140 gsm", "Kerah": "Crew neck", "Lengan": "Pendek"}),
    dict(slug="kinetik-drycore-tee-women", name="Kinetik DryCore Tee Women", category="jersey-kaos", brand="kinetik",
         sport="training", gender="women", price=199_000, rating=4.7, reviews=1450,
         colors=["Hitam", "Pink", "Ungu", "Putih"], sizes=WOMEN_APPAREL,
         short="Kaos training wanita quick-dry dengan potongan slim.",
         description="Versi wanita dari DryCore Tee dengan potongan slim fit dan panjang sedikit lebih panjang di belakang untuk coverage saat squat dan yoga.",
         material="92% poliester daur ulang, 8% elastane.",
         care=APPAREL_CARE,
         highlights=["Slim fit dengan stretch", "Hem belakang lebih panjang", "Anti bau"],
         specs={"Fit": "Slim", "Berat kain": "130 gsm", "Kerah": "Crew neck", "Lengan": "Pendek"}),
    dict(slug="garuda-home-jersey-2026", name="Garuda Home Jersey 2026", category="jersey-kaos", brand="garuda-sport",
         sport="football", gender="unisex", price=549_000, rating=4.8, reviews=978,
         colors=["Merah", "Putih"], sizes=["S", "M", "L", "XL", "XXL"],
         size_prices={"XXL": 30_000},
         short="Jersey replika kandang musim 2026 dengan motif batik parang.",
         description="Jersey kandang musim 2026 dengan motif batik parang tone-on-tone di bagian badan. Kain mesh berlubang mikro menjaga sirkulasi udara di stadion yang panas. Badge dan logo heat-transfer agar ringan.",
         material="100% poliester, mesh berlubang mikro.",
         care=APPAREL_CARE,
         highlights=["Motif batik parang", "Badge heat-transfer", "Ventilasi mikro", "Ukuran XXL +Rp30.000"],
         specs={"Fit": "Regular (replika)", "Kerah": "V-neck", "Lengan": "Pendek", "Musim": "2026"}),
    dict(slug="apex-shooting-shirt", name="Apex Shooting Shirt", category="jersey-kaos", brand="apex-pro",
         sport="basketball", gender="men", price=429_000, rating=4.4, reviews=134,
         colors=["Hitam", "Biru Navy"], sizes=APPAREL,
         short="Kaos pemanasan basket lengan panjang dengan kain stretch.",
         description="Shooting shirt untuk pemanasan sebelum pertandingan. Kain stretch 4 arah tidak menghalangi gerakan menembak, dengan panel mesh di punggung untuk ventilasi.",
         material="88% poliester, 12% spandex.",
         care=APPAREL_CARE,
         highlights=["Stretch 4 arah", "Panel mesh punggung", "Lengan panjang"],
         specs={"Fit": "Athletic", "Lengan": "Panjang", "Kerah": "Crew neck"}),

    # ---- Celana ----
    dict(slug="kinetik-stride-shorts-7", name="Kinetik Stride Shorts 7\"", category="celana", brand="kinetik",
         sport="running", gender="men", price=249_000, rating=4.5, reviews=870,
         colors=["Hitam", "Biru Navy", "Abu-abu"], sizes=APPAREL,
         short="Celana lari 7 inci dengan inner brief dan kantong ponsel.",
         description="Celana lari ringan dengan inseam 7 inci, inner brief yang nyaman, dan kantong belakang berresleting yang muat ponsel hingga 6.7 inci. Pinggang elastis dengan tali serut.",
         material="Shell: 100% poliester woven. Inner: 88% poliester, 12% elastane.",
         care=APPAREL_CARE,
         highlights=["Inseam 7 inci", "Kantong ponsel berresleting", "Inner brief", "Detail reflektif"],
         specs={"Inseam": "7 inci / 18 cm", "Pinggang": "Elastis + tali serut", "Kantong": "1 belakang berresleting, 2 samping"}),
    dict(slug="kinetik-flex-jogger", name="Kinetik Flex Jogger", category="celana", brand="kinetik",
         sport="training", gender="unisex", price=349_000, rating=4.6, reviews=640,
         colors=["Hitam", "Abu-abu", "Krem"], sizes=["XS", "S", "M", "L", "XL", "XXL"],
         short="Jogger stretch untuk latihan dan santai.",
         description="Jogger dengan kain stretch ringan yang tidak gerah, potongan tapered, dan manset di pergelangan kaki. Cocok untuk gym, perjalanan, maupun di rumah.",
         material="78% nilon, 22% spandex.",
         care=APPAREL_CARE,
         highlights=["Stretch 4 arah", "Potongan tapered", "Kantong samping berresleting"],
         specs={"Fit": "Tapered", "Panjang": "Full length", "Kantong": "2 samping berresleting"}),
    dict(slug="apex-mesh-basketball-shorts", name="Apex Mesh Basketball Shorts", category="celana", brand="apex-pro",
         sport="basketball", gender="men", price=299_000, compare=359_000, rating=4.5, reviews=298,
         colors=["Hitam", "Putih", "Merah"], sizes=APPAREL,
         short="Celana basket mesh 9 inci dengan pinggang lebar.",
         description="Celana basket klasik dengan kain mesh double-layer, inseam 9 inci, dan pinggang elastis lebar yang tidak melorot saat bergerak cepat.",
         material="100% poliester mesh double-layer.",
         care=APPAREL_CARE,
         highlights=["Mesh double-layer", "Inseam 9 inci", "Pinggang elastis lebar"],
         specs={"Inseam": "9 inci / 23 cm", "Kantong": "2 samping"}),

    # ---- Bola ----
    dict(slug="garuda-match-ball-pro", name="Garuda Match Ball Pro", category="bola", brand="garuda-sport",
         sport="football", gender="unisex", price=899_000, rating=4.8, reviews=412,
         colors=["Putih"], sizes=["5"],
         short="Bola sepak kualitas pertandingan, thermal bonded, standar FIFA Quality Pro.",
         description="Bola pertandingan resmi liga lokal. Panel thermal bonded tanpa jahitan membuat bola menyerap air minimal dan lintasannya stabil. Tekstur mikro di permukaan memberikan kontrol lebih saat hujan.",
         material="Cover: PU. Konstruksi: thermal bonded 20 panel. Bladder: butyl.",
         care="Simpan di tempat kering. Pompa sesuai tekanan yang dianjurkan. Bersihkan dengan kain lembap.",
         highlights=["FIFA Quality Pro", "Thermal bonded", "Menyerap air minimal"],
         specs={"Ukuran": "5 (dewasa)", "Keliling": "68-70 cm", "Berat": "420-445 g", "Tekanan": "0.8-1.0 bar", "Permukaan": "Rumput alami & sintetis"}),
    dict(slug="garuda-training-ball", name="Garuda Training Ball", category="bola", brand="garuda-sport",
         sport="football", gender="unisex", price=249_000, rating=4.5, reviews=780,
         colors=["Putih", "Kuning", "Oranye"], sizes=["3", "4", "5"],
         size_prices={"3": -50_000, "4": -30_000},
         short="Bola latihan jahit mesin, awet untuk segala lapangan.",
         description="Bola latihan yang tahan banting untuk sekolah sepak bola dan main bareng. Tersedia ukuran 3 (anak < 8 tahun), 4 (8-12 tahun), dan 5 (dewasa).",
         material="Cover: TPU. Konstruksi: jahit mesin 32 panel. Bladder: karet.",
         care="Simpan di tempat kering. Pompa sesuai tekanan yang dianjurkan.",
         highlights=["Jahit mesin awet", "3 pilihan ukuran", "Cocok untuk semua permukaan"],
         specs={"Ukuran 3": "58-60 cm", "Ukuran 4": "63-66 cm", "Ukuran 5": "68-70 cm", "Tekanan": "0.6-0.9 bar"}),
    dict(slug="apex-indoor-basketball", name="Apex Indoor Basketball", category="bola", brand="apex-pro",
         sport="basketball", gender="unisex", price=749_000, rating=4.7, reviews=256,
         colors=["Oranye"], sizes=["6", "7"],
         short="Bola basket kulit komposit untuk lapangan indoor.",
         description="Bola basket kulit komposit dengan grip yang semakin baik seiring pemakaian. Channel yang dalam memudahkan kontrol saat dribble dan menembak. Ukuran 7 untuk pria, ukuran 6 untuk wanita & junior.",
         material="Cover: kulit komposit microfiber. Bladder: butyl.",
         care="Khusus indoor. Bersihkan dengan kain lembap, jangan direndam.",
         highlights=["Kulit komposit microfiber", "Deep channel", "Khusus indoor"],
         specs={"Ukuran 6": "72.4 cm, 510-567 g", "Ukuran 7": "75 cm, 567-650 g", "Permukaan": "Indoor"}),
    dict(slug="kinetik-volley-soft", name="Kinetik Volley Soft", category="bola", brand="kinetik",
         sport="volleyball", gender="unisex", price=329_000, rating=4.4, reviews=190,
         colors=["Kuning", "Biru Navy"], sizes=["5"],
         short="Bola voli soft-touch untuk latihan dan rekreasi.",
         description="Bola voli dengan cover busa soft-touch yang nyaman di lengan, cocok untuk pemula dan latihan rutin.",
         material="Cover: PU soft-touch. Konstruksi: laminated 18 panel.",
         care="Simpan di tempat kering. Hindari permukaan kasar.",
         highlights=["Soft-touch", "18 panel laminated"],
         specs={"Ukuran": "5", "Keliling": "65-67 cm", "Berat": "260-280 g"}),

    # ---- Raket ----
    dict(slug="shuttlecraft-nano-strike-88", name="Shuttlecraft Nano Strike 88", category="raket", brand="shuttlecraft",
         sport="badminton", gender="unisex", price=1_650_000, rating=4.8, reviews=341,
         colors=["Hitam", "Ungu"], sizes=["3U G5", "4U G5"],
         size_prices={"3U G5": 50_000},
         short="Raket badminton head-heavy untuk smash bertenaga.",
         description="Nano Strike 88 dibuat untuk pemain menyerang. Keseimbangan head-heavy dan frame high-modulus graphite memberikan smash yang tajam, sementara shaft medium-stiff tetap bisa dikendalikan oleh pemain menengah. Dijual tanpa senar (unstrung).",
         material="Frame & shaft: high-modulus graphite + nanomesh.",
         care="Simpan di tas raket, jauhkan dari suhu panas (mobil). Senar maks. 30 lbs.",
         highlights=["Head-heavy untuk smash", "Tension maks. 30 lbs", "Termasuk cover raket"],
         specs={"Berat": "3U: 85-89 g, 4U: 80-84 g", "Grip": "G5", "Balance": "Head-heavy (≈305 mm)", "Kekakuan shaft": "Medium-stiff", "Tension": "20-30 lbs", "Senar": "Tidak termasuk"}),
    dict(slug="shuttlecraft-swift-60", name="Shuttlecraft Swift 60", category="raket", brand="shuttlecraft",
         sport="badminton", gender="unisex", price=650_000, compare=790_000, rating=4.5, reviews=622,
         colors=["Biru Muda", "Merah", "Hijau Neon"], sizes=["4U G5"],
         short="Raket badminton ringan untuk pemula, sudah terpasang senar.",
         description="Raket ringan dan seimbang untuk pemain pemula hingga rekreasi. Sudah terpasang senar 24 lbs sehingga langsung bisa dipakai.",
         material="Frame: graphite. Shaft: graphite.",
         care="Simpan di tas raket, jauhkan dari suhu panas.",
         highlights=["Ringan 4U", "Sudah bersenar 24 lbs", "Balance seimbang"],
         specs={"Berat": "80-84 g", "Grip": "G5", "Balance": "Even", "Kekakuan shaft": "Flexible", "Senar": "Terpasang, 24 lbs"}),

    # ---- Tas ----
    dict(slug="nordline-arena-backpack-30l", name="Nordline Arena Backpack", category="tas", brand="nordline",
         sport="training", gender="unisex", price=699_000, rating=4.7, reviews=455,
         colors=["Hitam", "Abu-abu", "Biru Navy"], sizes=["22L", "30L"],
         size_prices={"30L": 100_000},
         short="Backpack olahraga dengan kompartemen sepatu terpisah dan sleeve laptop 15\".",
         description="Backpack serbaguna untuk dari kantor langsung ke gym. Kompartemen sepatu berventilasi di bagian bawah, sleeve laptop 15 inci berbantalan, dan bahan water-resistant yang tahan hujan ringan.",
         material="Bahan: poliester 600D daur ulang dengan coating PU water-resistant.",
         care="Lap dengan kain lembap. Jangan dicuci mesin.",
         highlights=["Kompartemen sepatu berventilasi", "Sleeve laptop 15\"", "Water-resistant", "Kantong botol samping"],
         specs={"22L": "45 x 30 x 16 cm, 680 g", "30L": "50 x 32 x 20 cm, 820 g", "Laptop": "Hingga 15 inci"}),
    dict(slug="nordline-team-duffel", name="Nordline Team Duffel", category="tas", brand="nordline",
         sport="training", gender="unisex", price=549_000, rating=4.6, reviews=233,
         colors=["Hitam", "Merah"], sizes=["M (40L)", "L (60L)"],
         size_prices={"L (60L)": 120_000},
         short="Duffel bag dengan tali ransel tersembunyi, cocok untuk turnamen.",
         description="Duffel bag kapasitas besar untuk pertandingan tandang dan perjalanan. Tali bahu bisa diubah menjadi tali ransel, kantong samping untuk sepatu, dan alas bawah tahan air.",
         material="Bahan: poliester 900D, alas bawah TPU tahan air.",
         care="Lap dengan kain lembap.",
         highlights=["Bisa jadi ransel", "Kantong sepatu samping", "Alas tahan air"],
         specs={"M (40L)": "55 x 28 x 28 cm", "L (60L)": "65 x 32 x 30 cm"}),

    # ---- Aksesoris ----
    dict(slug="kinetik-cushion-crew-socks-3pack", name="Kinetik Cushion Crew Socks (3 Pasang)", category="aksesoris", brand="kinetik",
         icon="sock", sport="training", gender="unisex", price=129_000, rating=4.6, reviews=1890,
         colors=["Putih", "Hitam", "Abu-abu"], sizes=["S", "M", "L"],
         short="Kaos kaki crew dengan bantalan di telapak, isi 3 pasang.",
         description="Kaos kaki olahraga dengan bantalan terry di telapak dan tumit, arch support elastis, dan benang anti bau. Isi 3 pasang dengan warna sama.",
         material="72% katun, 25% poliester, 3% elastane.",
         care="Cuci mesin air hangat. Jangan gunakan pemutih.",
         highlights=["Isi 3 pasang", "Bantalan terry", "Arch support"],
         specs={"Panjang": "Crew (di atas mata kaki)", "Isi": "3 pasang"}),
    dict(slug="kinetik-run-cap", name="Kinetik Run Cap", category="aksesoris", brand="kinetik",
         icon="cap", sport="running", gender="unisex", price=179_000, rating=4.5, reviews=402,
         colors=["Hitam", "Putih", "Hijau Neon"], sizes=["One Size"],
         short="Topi lari ringan dengan sweatband dan strap yang bisa disesuaikan.",
         description="Topi lari super ringan dengan panel samping berlubang laser, sweatband di dahi, dan strap belakang yang bisa disesuaikan. Bisa dilipat tanpa merusak bentuk.",
         material="100% poliester ringan.",
         care="Cuci tangan dengan air dingin.",
         highlights=["Ringan 55 g", "Ventilasi laser-cut", "Bisa dilipat"],
         specs={"Lingkar kepala": "54-60 cm (adjustable)", "Berat": "55 g"}),
    dict(slug="nordline-hydro-bottle", name="Nordline Hydro Bottle", category="aksesoris", brand="nordline",
         icon="bottle", sport="training", gender="unisex", price=249_000, rating=4.8, reviews=1120,
         colors=["Hitam", "Silver", "Tosca", "Pink"], sizes=["500 ml", "750 ml", "1 L"],
         size_prices={"750 ml": 50_000, "1 L": 100_000},
         short="Botol minum stainless steel double wall, dingin hingga 24 jam.",
         description="Botol vakum stainless steel double wall yang menjaga minuman dingin hingga 24 jam dan panas hingga 12 jam. Tutup sport dengan sedotan flip, bebas BPA, dan tidak berkeringat di luar.",
         material="Stainless steel 18/8, tutup polypropylene bebas BPA.",
         care="Cuci tangan. Tidak aman untuk mesin cuci piring dan microwave.",
         highlights=["Dingin 24 jam / panas 12 jam", "Bebas BPA", "Tutup sport anti tumpah"],
         specs={"500 ml": "Tinggi 21 cm, 320 g", "750 ml": "Tinggi 26 cm, 410 g", "1 L": "Tinggi 29 cm, 490 g"}),
    dict(slug="shuttlecraft-pro-shuttlecock-12", name="Shuttlecraft Pro Shuttlecock (12 pcs)", category="aksesoris", brand="shuttlecraft",
         icon="shuttle", sport="badminton", gender="unisex", price=189_000, rating=4.6, reviews=954,
         colors=["Putih"], sizes=["Speed 76", "Speed 77", "Speed 78"],
         short="Kok bulu angsa kelas turnamen, isi 12.",
         description="Kok bulu angsa dengan gabus komposit untuk lintasan stabil dan daya tahan lebih lama. Pilih speed sesuai suhu dan ketinggian lokasi bermain (Speed 77 untuk kebanyakan GOR di Indonesia).",
         material="Bulu: angsa grade A. Kepala: gabus komposit.",
         care="Simpan di tempat sejuk. Lembapkan sedikit sebelum dipakai agar bulu tidak mudah patah.",
         highlights=["Bulu angsa grade A", "Kelas turnamen", "Isi 12"],
         specs={"Isi": "12 pcs", "Speed 76": "Dataran tinggi / suhu > 30°C", "Speed 77": "Umum (rekomendasi)", "Speed 78": "Suhu < 25°C"}),
]

PROMOS = [
    ("STADION10", "Diskon 10% maks. Rp100.000", 10, 0, 200_000, 100_000),
    ("HEMAT50", "Potongan Rp50.000 min. belanja Rp500.000", 0, 50_000, 500_000, None),
    ("WELCOME", "Diskon 15% pembelian pertama, maks. Rp150.000", 15, 0, 0, 150_000),
]


def _sku(slug: str, color: str, size: str) -> str:
    base = "".join(w[0] for w in slug.split("-") if w)[:5].upper()
    col = re.sub(r"[^A-Z]", "", color.upper())[:3]
    sz = re.sub(r"[^A-Z0-9]", "", size.upper())[:5]
    return f"{base}-{col}-{sz}"


def seed(db: Session) -> None:
    rng = random.Random(42)
    cats = {}
    for slug, name, desc, icon, chart in CATEGORIES:
        cats[slug] = models.Category(slug=slug, name=name, description=desc, icon=icon, size_chart=chart)
    brands = {slug: models.Brand(slug=slug, name=n, country=c, description=d) for slug, n, c, d in BRANDS}
    db.add_all([*cats.values(), *brands.values()])

    now = datetime.now(timezone.utc)
    used_skus: set[str] = set()
    for i, p in enumerate(PRODUCTS):
        product = models.Product(
            slug=p["slug"], name=p["name"], category=cats[p["category"]], brand=brands[p["brand"]],
            icon=p.get("icon"), sport=p["sport"], gender=p["gender"],
            short_description=p["short"], description=p["description"], material=p["material"],
            care_instructions=p["care"], highlights=p["highlights"], specs=p["specs"],
            base_price=p["price"], compare_at_price=p.get("compare"),
            rating=p["rating"], review_count=p["reviews"],
            created_at=now - timedelta(days=len(PRODUCTS) - i),
        )
        for color in p["colors"]:
            for size in p["sizes"]:
                sku = _sku(p["slug"], color, size)
                n = 2
                while sku in used_skus:
                    sku = f"{_sku(p['slug'], color, size)}-{n}"
                    n += 1
                used_skus.add(sku)
                # ~8% of variants sold out, rest 1-40 units
                stock = 0 if rng.random() < 0.08 else rng.randint(1, 40)
                product.variants.append(
                    models.ProductVariant(
                        sku=sku, color_name=color, color_hex=C[color], size=size, stock=stock,
                        price=p["price"] + p.get("size_prices", {}).get(size, 0),
                    )
                )
        db.add(product)

    for code, desc, pct, amt, min_sub, max_disc in PROMOS:
        db.add(models.PromoCode(code=code, description=desc, percent_off=pct, amount_off=amt,
                                min_subtotal=min_sub, max_discount=max_disc))
    db.commit()


def seed_if_empty(db: Session) -> None:
    if db.query(models.Product.id).first() is None:
        seed(db)


if __name__ == "__main__":
    from .database import Base, SessionLocal, engine

    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_if_empty(session)
        print(f"Seeded: {session.query(models.Product).count()} products, "
              f"{session.query(models.ProductVariant).count()} variants")
