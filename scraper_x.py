from datetime import datetime, timezone, timedelta
from apify_client import ApifyClient
import pandas as pd

# 1. Inisialisasi ApifyClient dengan API Token Anda
client = ApifyClient("")

# 2. Cari postingan berdasarkan kata kunci
search_input = {
    "query": "Sensus Ekonomi 2026",  # Ganti dengan kata kunci Anda
    "resultsCount": 10,                # Jumlah postingan yang dicari
    "searchType": "top",               # Wajib huruf kecil: "top" atau "latest"
}

print("Mencari postingan...")
search_run = client.actor("scraper_one/x-posts-search").call(run_input=search_input)

# Ambil ID postingan (menggunakan atribut .default_dataset_id untuk apify-client v2+)
post_ids = []
for post in client.dataset(search_run.default_dataset_id).iterate_items():
    post_id = post.get("postId") or post.get("id")
    if post_id:
        post_ids.append(str(post_id))

print(f"Ditemukan {len(post_ids)} postingan. Mengambil komentar...")

# 3. Scrape komentar dan rapikan data (termasuk timestamp komentar dipost)
cleaned_comments = []
WIB = timezone(timedelta(hours=7))  # Zona waktu WIB (UTC+7)

if post_ids:
    replies_input = {
        "tweets": post_ids
    }
    
    replies_run = client.actor("arjun_code/x-twitter-replies-scraper").call(run_input=replies_input)
    
    for comment in client.dataset(replies_run.default_dataset_id).iterate_items():
        # Ambil timestamp asli saat komentar diposting
        raw_time = (
            comment.get("createdAt") 
            or comment.get("created_at") 
            or comment.get("timestamp") 
            or comment.get("date")
        )
        
        # Konversi ke format tanggal & jam WIB (YYYY-MM-DD HH:MM:SS)
        formatted_time = raw_time
        if raw_time:
            try:
                dt_utc = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
                dt_wib = dt_utc.astimezone(WIB)
                formatted_time = dt_wib.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    dt_utc = datetime.strptime(str(raw_time), "%a %b %d %H:%M:%S %z %Y")
                    dt_wib = dt_utc.astimezone(WIB)
                    formatted_time = dt_wib.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass

        cleaned_comments.append({
            "post_id": comment.get("inReplyToStatusId") or comment.get("conversationId") or "",
            "comment_id": comment.get("id") or comment.get("postId") or "",
            "username": comment.get("author", {}).get("userName") if isinstance(comment.get("author"), dict) else comment.get("username", ""),
            "comment_text": comment.get("text") or comment.get("fullText") or "",
            "comment_posted_at_wib": formatted_time,
            "raw_timestamp": raw_time,
            "likes": comment.get("likeCount") or comment.get("likes") or 0,
            "replies": comment.get("replyCount") or comment.get("replies") or 0,
        })
        
    # 4. Simpan ke file CSV
    if cleaned_comments:
        df = pd.DataFrame(cleaned_comments)
        filename = f"x_comments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"Berhasil! {len(cleaned_comments)} komentar disimpan ke '{filename}'.")
    else:
        print("Tidak ada komentar yang berhasil diambil.")
else:
    print("Tidak ada postingan ditemukan.")
