import streamlit as st
import os
import time
import tempfile
import threading
from datetime import datetime
import google.generativeai as genai
from supabase import create_client

# ── Config ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Content Tool", page_icon="🎬", layout="wide")

# ── Data helpers ─────────────────────────────────────────────────────────────
def load_channels():
    res = supabase.table("channels").select("*").order("last_used", desc=True, nullsfirst=False).execute()
    return res.data or []

def add_channel(name, platform, language, context):
    supabase.table("channels").insert({
        "name": name,
        "platform": platform,
        "language": language,
        "context": context
    }).execute()

def delete_channel(name):
    supabase.table("channels").delete().eq("name", name).execute()

def record_usage(name):
    supabase.table("channels").update({"last_used": datetime.now().isoformat()}).eq("name", name).execute()

# ── Gemini analysis ──────────────────────────────────────────────────────────
def analyze_video_with_progress(video_bytes, filename, channel, progress, status):
    model = genai.GenerativeModel("gemini-2.0-flash")

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name

    uploaded = None
    try:
        # Step 1: Upload với progress estimate theo file size (10% → 40%)
        file_mb = len(video_bytes) / (1024 * 1024)
        # Estimate ~3 MB/s upload speed → tổng giây upload
        estimated_seconds = max(5, file_mb / 3)

        result_holder = [None]
        error_holder = [None]

        def do_upload():
            try:
                result_holder[0] = genai.upload_file(tmp_path)
            except Exception as e:
                error_holder[0] = e

        upload_thread = threading.Thread(target=do_upload)
        upload_thread.start()

        elapsed = 0
        while upload_thread.is_alive():
            time.sleep(0.5)
            elapsed += 0.5
            pct = int(10 + min(28, (elapsed / estimated_seconds) * 28))
            progress.progress(pct)
            status.info(f"📤 Bước 1/4 — Đang upload lên Gemini... ({min(100, int(elapsed/estimated_seconds*100))}%  •  {file_mb:.0f} MB)")

        upload_thread.join()
        if error_holder[0]:
            raise error_holder[0]

        uploaded = result_holder[0]
        progress.progress(40)

        # Step 2: Wait for Gemini processing (40% → 70%)
        status.info("⚙️ Bước 2/4 — Gemini đang xử lý video...")
        wait_steps = 0
        while uploaded.state.name == "PROCESSING":
            time.sleep(3)
            uploaded = genai.get_file(uploaded.name)
            wait_steps += 1
            pct = min(70, 40 + wait_steps * 5)
            progress.progress(pct)

        progress.progress(70)

        # Step 3: AI analyze (70% → 95%)
        status.info("🤖 Bước 3/4 — AI đang phân tích nội dung và tạo đề xuất...")
        platform = channel.get("platform", "")
        context = channel.get("context", "")
        lang = channel.get("language", "Tiếng Việt")

        prompt = f"""Bạn là chuyên gia content cho kênh {platform}.

Context kênh: {context}

Hãy xem video này và phân tích nội dung, sau đó tạo ra:

1. **Tóm tắt nội dung** (3-5 câu): Video nói về/thể hiện điều gì?

2. **5 gợi ý Title** cho {platform} (hấp dẫn, tối ưu SEO, phù hợp tone kênh)

3. **Hashtags** (20-30 hashtag phù hợp, mix trending + niche)

4. **SEO Description** (150-200 từ, tự nhiên, có keyword)

5. **Gợi ý thêm** (hook đầu video, CTA, thời điểm đăng tốt)

Ngôn ngữ output: {lang}"""

        response = model.generate_content([uploaded, prompt])
        progress.progress(95)

        # Step 4: Done
        status.info("📝 Bước 4/4 — Đang hoàn thiện kết quả...")
        return response.text

    finally:
        os.unlink(tmp_path)
        if uploaded:
            try:
                genai.delete_file(uploaded.name)
            except:
                pass

# ── UI ───────────────────────────────────────────────────────────────────────
def main():
    channels = load_channels()

    # Sidebar: Admin panel
    with st.sidebar:
        st.header("⚙️ Quản lý Channels")

        with st.expander("➕ Thêm channel mới"):
            new_name = st.text_input("Tên channel", key="new_name")
            new_platform = st.selectbox("Platform", ["TikTok", "YouTube", "Facebook", "Instagram", "Khác"], key="new_platform")
            new_lang = st.selectbox("Ngôn ngữ output", ["Tiếng Việt", "English", "Cả hai"], key="new_lang")
            new_context = st.text_area(
                "Context / Tone của kênh",
                placeholder="VD: Kênh về đồ da handmade, tone chuyên nghiệp nhưng gần gũi, target khách hàng 25-40 tuổi...",
                key="new_context",
                height=120
            )
            if st.button("✅ Thêm", type="primary"):
                if new_name and new_context:
                    try:
                        add_channel(new_name, new_platform, new_lang, new_context)
                        st.success(f"Đã thêm: {new_name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi: {e}")
                else:
                    st.error("Nhập đủ tên và context nhé")

        if channels:
            st.divider()
            st.subheader("🗑️ Xóa channel")
            del_name = st.selectbox("Chọn channel để xóa", [ch["name"] for ch in channels], key="del_select")
            if st.button("Xóa", type="secondary"):
                delete_channel(del_name)
                st.success(f"Đã xóa: {del_name}")
                st.rerun()

    # Main area
    st.title("🎬 Content Tool")
    st.caption("Upload video → AI phân tích → Gợi ý Title, Hashtag, SEO")

    if not channels:
        st.info("👈 Chưa có channel nào. Thêm channel mới ở sidebar để bắt đầu.")
        return

    # Recent bar (channels đã dùng, sort theo last_used)
    recent = [ch for ch in channels if ch.get("last_used")][:4]
    if recent:
        st.markdown("**🔥 Gần đây:**")
        cols = st.columns(len(recent))
        for i, ch in enumerate(recent):
            with cols[i]:
                st.button(f"{ch['platform']} · {ch['name']}", key=f"recent_{ch['name']}", disabled=True)

    st.divider()

    # Channel tabs (sorted by last_used, nulls last)
    tab_labels = [f"{ch['platform']} · {ch['name']}" for ch in channels]
    tabs = st.tabs(tab_labels)

    for tab, channel in zip(tabs, channels):
        with tab:
            st.markdown(f"**Platform:** {channel['platform']} &nbsp;|&nbsp; **Output:** {channel.get('language','Tiếng Việt')}")
            with st.expander("📋 Context kênh"):
                st.write(channel["context"])

            uploaded_file = st.file_uploader(
                "Upload video",
                type=["mp4", "mov", "avi", "mkv", "webm"],
                key=f"upload_{channel['name']}"
            )

            if uploaded_file:
                st.video(uploaded_file)
                file_size_mb = len(uploaded_file.getvalue()) / (1024 * 1024)
                st.caption(f"📁 {uploaded_file.name} — {file_size_mb:.1f} MB")

                if st.button("🚀 Phân tích & Tạo content", type="primary", key=f"analyze_{channel['name']}"):
                    record_usage(channel["name"])
                    progress = st.progress(0)
                    status = st.empty()
                    try:
                        status.info("📤 Bước 1/4 — Đang upload video lên Gemini...")
                        progress.progress(10)
                        result = analyze_video_with_progress(
                            uploaded_file.getvalue(),
                            uploaded_file.name,
                            channel,
                            progress,
                            status
                        )
                        progress.progress(100)
                        status.success("✅ Hoàn thành!")
                        st.markdown("---")
                        st.markdown(result)
                        st.download_button(
                            "💾 Tải kết quả (.txt)",
                            data=result,
                            file_name=f"content_{channel['name']}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                            mime="text/plain"
                        )
                    except Exception as e:
                        progress.empty()
                        status.error(f"❌ Lỗi: {str(e)}")

if __name__ == "__main__":
    main()
