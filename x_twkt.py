# -*- coding: utf-8 -*-
"""
Scraper komentar (reply) postingan X memakai library twikit (login via cookies)
untuk proyek analisis sentimen isu ekonomi - BPS Kota Malang.

Dependencies (pakai fork twifork, impor tetap `from twikit import ...`):
    pip uninstall twikit -y
    pip install twifork

    Catatan: twikit upstream dan twifork sama-sama terpasang sebagai paket
    "twikit", jadi JANGAN pasang keduanya sekaligus.

Cara dapat cookies:
    1. Login ke x.com di browser biasa (Chrome/Edge).
    2. F12 > Application > Cookies > https://x.com
    3. Salin nilai `auth_token` dan `ct0`, tempel ke X_AUTH_TOKEN dan X_CT0 di bawah.

Catatan:
    - Gunakan akun X KHUSUS riset, bukan akun pribadi.
    - Scraping X melanggar Ketentuan Layanan X. Pakai volume kecil, hanya
      untuk riset akademik/PKL, dan jangan publikasikan data mentah.
    - Script ini berisi kredensial: jangan di-commit ke Git atau dibagikan.
    - Kalau logout dari X di browser, cookies jadi tidak berlaku -> ambil ulang.
    - Penulis komentar sengaja tidak disimpan (privasi).
"""

import asyncio
import csv
import random
from datetime import datetime, timedelta, timezone

from twikit import Client

from keywords import KEYWORDS

# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------

X_AUTH_TOKEN = ""
X_CT0 = ""

MAKS_POSTINGAN_PER_KATA_KUNCI = 50   # postingan BERBALASAN yang diproses per kata kunci
MAKS_KOMENTAR_PER_POSTINGAN = 10    # batas komentar per postingan
MAKS_HALAMAN_PENCARIAN = 6           # berapa halaman hasil pencarian yang dibuka per tab
MAKS_HALAMAN_KOMENTAR = 6            # berapa halaman balasan yang dibuka per postingan

JEDA_MIN = 3.0   # detik, jeda acak antar-request
JEDA_MAX = 6.0

OUTPUT_CSV = "data_x_twikit_mentah.csv"

# Operator pencarian X. Kalau hasil kosong, biarkan False
# (filter bahasa & reply tetap dilakukan di kode setelah data diambil).
GUNAKAN_LANG_ID = False
GUNAKAN_FILTER_NO_REPLY = False
GUNAKAN_RENTANG_TANGGAL = True

# Rentang waktu pengambilan data (ganti sesuai kebutuhan, mis. 7 atau 90)
HARI_TERAKHIR = 202
BATAS_AWAL = datetime.now(timezone.utc) - timedelta(days=HARI_TERAKHIR)


async def jeda():
    await asyncio.sleep(random.uniform(JEDA_MIN, JEDA_MAX))


# ---------------------------------------------------------------------------
# Helper membaca atribut tweet (defensif, karena struktur X sering berubah)
# ---------------------------------------------------------------------------

def teks_tweet(t):
    return getattr(t, "full_text", None) or getattr(t, "text", "") or ""


def tanggal_tweet(t):
    dt = getattr(t, "created_at_datetime", None)
    if dt is None:
        try:
            dt = datetime.strptime(t.created_at, "%a %b %d %H:%M:%S %z %Y")
        except (ValueError, TypeError, AttributeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def jumlah_balasan(t):
    return getattr(t, "reply_count", 0) or 0


def layak_postingan(t):
    """Postingan utama (bukan RT/reply) dalam rentang tanggal."""
    tgl = tanggal_tweet(t)
    return (
        tgl is not None
        and tgl >= BATAS_AWAL
        and not teks_tweet(t).startswith("RT @")
        and not getattr(t, "in_reply_to", None)
    )


# ---------------------------------------------------------------------------
# 1. Cari postingan berdasarkan kata kunci
# ---------------------------------------------------------------------------

async def cari_postingan(client, keyword):
    """
    Mencari postingan yang PUNYA balasan. Mencoba tab Top dulu, lalu Latest,
    dan membuka halaman berikutnya sampai jumlahnya cukup atau hasil habis.
    """
    since = BATAS_AWAL.strftime("%Y-%m-%d")
    until = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    bagian = [keyword]
    if GUNAKAN_LANG_ID:
        bagian.append("lang:id")
    if GUNAKAN_RENTANG_TANGGAL:
        bagian.append(f"since:{since} until:{until}")
    if GUNAKAN_FILTER_NO_REPLY:
        bagian.append("-filter:replies")
    query = " ".join(bagian)
    print(f"  query: {query}")

    gabungan = {}

    def berbalasan():
        return sum(1 for t in gabungan.values() if jumlah_balasan(t) > 0)

    for produk in ("Top", "Latest"):
        try:
            hasil = await client.search_tweet(query, produk, count=20)
        except Exception as e:
            print(f"  [GAGAL] pencarian {produk}: {type(e).__name__}: {e}")
            continue

        halaman = 0
        while hasil and halaman < MAKS_HALAMAN_PENCARIAN:
            halaman += 1
            for t in hasil:
                if layak_postingan(t):
                    gabungan[str(t.id)] = t

            print(f"  [{produk}] halaman {halaman}: lolos filter (kumulatif) "
                  f"{len(gabungan)}, yang punya balasan {berbalasan()}")

            if berbalasan() >= MAKS_POSTINGAN_PER_KATA_KUNCI:
                break

            await jeda()
            try:
                hasil = await hasil.next()
            except Exception:
                break   # tidak ada halaman berikutnya

        if berbalasan() >= MAKS_POSTINGAN_PER_KATA_KUNCI:
            break

    terpilih = [t for t in gabungan.values() if jumlah_balasan(t) > 0]
    terpilih.sort(key=jumlah_balasan, reverse=True)
    return terpilih[:MAKS_POSTINGAN_PER_KATA_KUNCI]


# ---------------------------------------------------------------------------
# 2. Ambil komentar (reply) dari satu postingan
# ---------------------------------------------------------------------------

async def ambil_komentar(client, post_id):
    """Mengambil komentar langsung (top-level) ke satu postingan dalam rentang tanggal."""
    komentar = []
    sudah = set()

    try:
        tweet = await client.get_tweet_by_id(post_id)
        balasan = tweet.replies
    except Exception as e:
        print(f"  [INFO] Tidak bisa ambil postingan {post_id}: {type(e).__name__}: {e}")
        return komentar

    halaman = 0
    while balasan and halaman < MAKS_HALAMAN_KOMENTAR and len(komentar) < MAKS_KOMENTAR_PER_POSTINGAN:
        halaman += 1
        baru = 0
        for r in balasan:
            rid = str(r.id)
            if rid in sudah:
                continue
            sudah.add(rid)

            if str(getattr(r, "in_reply_to", "") or "") != str(post_id):
                continue   # lewati balasan bersarang
            tgl = tanggal_tweet(r)
            if tgl is None or tgl < BATAS_AWAL:
                continue

            komentar.append({
                "komentar_id": rid,
                "teks": teks_tweet(r),
                "tanggal": tgl.isoformat(),
                "like_count": getattr(r, "favorite_count", 0) or 0,
                "retweet_count": getattr(r, "retweet_count", 0) or 0,
                "bahasa": getattr(r, "lang", ""),
                # Penulis komentar sengaja tidak disimpan (privasi).
            })
            baru += 1
            if len(komentar) >= MAKS_KOMENTAR_PER_POSTINGAN:
                break

        await jeda()
        try:
            balasan = await balasan.next()
        except Exception:
            break   # tidak ada halaman berikutnya

    return komentar


# ---------------------------------------------------------------------------
# 3. Gabungkan pencarian postingan + komentar untuk semua kata kunci
# ---------------------------------------------------------------------------

async def kumpulkan_semua_x(client, keywords_dict):
    semua_data = []
    post_sudah_diambil = set()

    for isu, daftar_kata_kunci in keywords_dict.items():
        for kw in daftar_kata_kunci:
            print(f"\nMencari postingan untuk: {kw}")
            daftar_post = await cari_postingan(client, kw)
            print(f"  postingan berbalasan terpilih: {len(daftar_post)}")

            for post in daftar_post:
                pid = str(post.id)
                if pid in post_sudah_diambil:
                    continue
                post_sudah_diambil.add(pid)

                print(f"  Mengambil komentar: {teks_tweet(post)[:60].strip()}...")
                komentar_list = await ambil_komentar(client, pid)
                print(f"    komentar terambil: {len(komentar_list)}")

                for k in komentar_list:
                    semua_data.append({
                        "isu": isu,
                        "kata_kunci": kw,
                        "post_id": pid,
                        "teks_post": teks_tweet(post),
                        "url_post": f"https://x.com/i/status/{pid}",
                        **k,
                    })

                await jeda()

    return semua_data


# ---------------------------------------------------------------------------
# 4. Simpan ke CSV
# ---------------------------------------------------------------------------

def simpan_csv(data, nama_file=OUTPUT_CSV):
    if not data:
        print("Tidak ada data untuk disimpan.")
        return

    kolom = list(data[0].keys())
    with open(nama_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=kolom)
        writer.writeheader()
        writer.writerows(data)

    print(f"Tersimpan {len(data)} baris ke {nama_file}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    if "ISI_" in X_AUTH_TOKEN or "ISI_" in X_CT0:
        print("Isi X_AUTH_TOKEN dan X_CT0 dulu (lihat petunjuk di atas file).")
        return

    client = Client("id-ID")
    client.set_cookies({"auth_token": X_AUTH_TOKEN, "ct0": X_CT0})

    # Cek cookies valid
    try:
        me = await client.user()
        print(f"Login cookies OK sebagai @{me.screen_name}")
    except Exception as e:
        print(f"[GAGAL] Cookies tidak valid atau request ditolak: {type(e).__name__}: {e}")
        return

    print(f"Rentang data: {HARI_TERAKHIR} hari terakhir "
          f"(sejak {BATAS_AWAL.strftime('%Y-%m-%d')})")
    print("=== Mengumpulkan komentar X (twikit) ===")
    data = await kumpulkan_semua_x(client, KEYWORDS)
    simpan_csv(data)
    print(f"\nSelesai. Waktu proses: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())