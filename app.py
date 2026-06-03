import streamlit as st
import json
import os
import time
import tempfile
from datetime import datetime
import google.generativeai as genai

# ── Config ──────────────────────────────────────────────────────────────────
GEMINI_API_KEY = "AIzaSyCLP4-z7ZojkV6XUCb7yAsUJHdGLzK0Fjw"
CHANNELS_FILE = "channels.json"
USAGE_FILE = "usage_log.json"

genai.configure(api_key=GEMINI_API_KEY)

st.set_page_config(page_title="Content Tool", page_icon="🎬", layout="wide")

# ── Data helpers ─────────────────────────────────────────────────────────────
def load_channels():
    if os.path.exists(CHANNELS_FILE):
        with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_channels(channels):
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)

def load_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_usage(usage):
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(usage, f, ensure_ascii=False, indent=2)

def record_usage(channel_name):
    usage = load_usage()
    usage[channel_name] = datetime.now().isoformat()
    save_usage(usage)

def sort_channels_by_recent(channels):
    usage = load_usage()
    def sort_key(ch):
        ts = usage.get(ch["name"], "")
        return ts if ts else "0"
    return sorted(channels, key=sort_key, reverse=True)

# ── Gemini analysis ──────────────────────────────────────────────────────────
def analyze_video(video_bytes, filename, channel):
    model = genai.GenerativeModel("gemini-1.5-flash")

    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name

    try:
        uploaded = genai.upload_file(tmp_path)

        # Wait for processing
        while uploaded.state.name == "PROCESSING":
            time.sleep(2)
            uploaded = genai.get_file(uploaded.name)

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

Ngôn ngữ output: {lang}

Trả lời theo đúng format 5 mục trên."""

        response = model.generate_content([uploaded, prompt])
        return response.text

    finally:
        os.unlink(tmp_path)
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
                    channels.append({
                        "name": new_name,
                        "platform": new_platform,
                        "language": new_lang,
                        "context": new_context
                    })
                    save_channels(channels)
                    st.success(f"Đã thêm: {new_name}")
                    st.rerun()
                else:
                    st.error("Nhập đủ tên và context nhé")

        if channels:
            st.divider()
            st.subheader("🗑️ Xóa channel")
            del_name = st.selectbox("Chọn channel để xóa", [ch["name"] for ch in channels], key="del_select")
            if st.button("Xóa", type="secondary"):
                channels = [ch for ch in channels if ch["name"] != del_name]
                save_channels(channels)
                st.success(f"Đã xóa: {del_name}")
                st.rerun()

    # Main area
    st.title("🎬 Content Tool")
    st.caption("Upload video → AI phân tích → Gợi ý Title, Hashtag, SEO")

    if not channels:
        st.info("👈 Chưa có channel nào. Thêm channel mới ở sidebar để bắt đầu.")
        return

    # Sort by recent usage
    sorted_channels = sort_channels_by_recent(channels)
    usage = load_usage()

    # Recent bar
    recent_channels = [ch for ch in sorted_channels if ch["name"] in usage][:4]
    if recent_channels:
        st.markdown("**🔥 Gần đây:**")
        cols = st.columns(len(recent_channels))
        for i, ch in enumerate(recent_channels):
            with cols[i]:
                if st.button(f"{ch['platform']} · {ch['name']}", key=f"recent_{ch['name']}"):
                    st.session_state["selected_channel"] = ch["name"]

    st.divider()

    # Channel tabs
    tab_labels = [f"{ch['platform']} · {ch['name']}" for ch in sorted_channels]
    tabs = st.tabs(tab_labels)

    for i, (tab, channel) in enumerate(zip(tabs, sorted_channels)):
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
                    with st.spinner("⏳ Đang upload và phân tích video... (có thể mất 30-60 giây)"):
                        try:
                            result = analyze_video(
                                uploaded_file.getvalue(),
                                uploaded_file.name,
                                channel
                            )
                            st.success("✅ Xong!")
                            st.markdown("---")
                            st.markdown(result)

                            st.download_button(
                                "💾 Tải kết quả (.txt)",
                                data=result,
                                file_name=f"content_{channel['name']}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                                mime="text/plain"
                            )
                        except Exception as e:
                            st.error(f"Lỗi: {str(e)}")

if __name__ == "__main__":
    main()
