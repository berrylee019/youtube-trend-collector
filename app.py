from datetime import datetime
import re
from googleapiclient.discovery import build
import isodate
import pandas as pd
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi

# 페이지 기본 설정
st.set_page_config(
    page_title="유튜브 떡상 영상 수집기 & 대본 생성기",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 외국인 반응/브이로그 떡상 영상 수집 & 2차 창작 대본 도우미")
st.caption(
    "구독자 수 대비 높은 조회수를 기록한 영상 검색부터 스크립트 추출, AI 대본 생성"
    " 프롬프트까지 지원합니다."
)

# 탭 구성: 1. 영상 수집기 / 2. 스크립트 추출 및 AI 대본 생성
tab1, tab2 = st.tabs(["🔍 떡상 영상 수집기", "📝 스크립트 추출 & AI 대본 생성"])

# ---------------------------------------------------------
# [탭 1] 떡상 영상 수집기
# ---------------------------------------------------------
with tab1:
  # 사이드바: 설정 및 API 키 입력
  with st.sidebar:
    st.header("⚙️ 검색 및 API 설정")
    default_api_key = (
        st.secrets.get("YOUTUBE_API_KEY", "")
        if "YOUTUBE_API_KEY" in st.secrets
        else ""
    )
    api_key = st.text_input(
        "YouTube API Key", value=default_api_key, type="password"
    )
    search_keyword = st.text_input("검색 키워드", value="Korea vlog")
    max_results = st.slider(
        "수집할 영상 수", min_value=10, max_value=50, value=20
    )
    min_ratio = st.number_input(
        "최소 성과 비율 (조회수/구독자수 %)", value=200, step=50
    )
    st.markdown("---")
    start_button = st.button("🚀 데이터 수집 시작", use_container_width=True)

  def parse_duration(duration_str):
    try:
      td = isodate.parse_duration(duration_str)
      total_seconds = int(td.total_seconds())
      minutes, seconds = divmod(total_seconds, 60)
      hours, minutes = divmod(minutes, 60)
      if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
      return f"{minutes}:{seconds:02d}"
    except Exception:
      return "N/A"

  def get_grade(ratio):
    if ratio >= 500:
      return "🔥 S등급 (500% 이상)"
    elif ratio >= 300:
      return "✨ A등급 (300% 이상)"
    elif ratio >= 150:
      return "👍 B등급 (150% 이상)"
    else:
      return "⚪ 일반"

  if start_button:
    if not api_key:
      st.error("YouTube API Key를 입력해주세요!")
    else:
      with st.spinner("유튜브 데이터를 분석 중입니다..."):
        try:
          youtube = build("youtube", "v3", developerKey=api_key)

          search_response = (
              youtube.search()
              .list(
                  q=search_keyword,
                  part="snippet",
                  maxResults=max_results,
                  type="video",
                  order="viewCount",
              )
              .execute()
          )

          video_ids = [
              item["id"]["videoId"] for item in search_response.get("items", [])
          ]

          if not video_ids:
            st.warning("검색 결과가 없습니다.")
          else:
            videos_response = (
                youtube.videos()
                .list(
                    id=",".join(video_ids),
                    part="snippet,statistics,contentDetails",
                )
                .execute()
            )

            channel_ids = list(
                set([
                    v["snippet"]["channelId"]
                    for v in videos_response.get("items", [])
                ])
            )

            channels_response = (
                youtube.channels()
                .list(id=",".join(channel_ids), part="statistics")
                .execute()
            )

            channel_subs = {
                c["id"]: int(c["statistics"].get("subscriberCount", 0))
                for c in channels_response.get("items", [])
            }

            data = []
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

            for item in videos_response.get("items", []):
              v_id = item["id"]
              snippet = item["snippet"]
              stats = item.get("statistics", {})
              content = item.get("contentDetails", {})

              ch_id = snippet["channelId"]
              sub_count = channel_subs.get(ch_id, 0)
              view_count = int(stats.get("viewCount", 0))
              ratio = (
                  round((view_count / sub_count) * 100, 1) if sub_count > 0 else 0
              )

              if ratio >= min_ratio:
                pub_date = snippet["publishedAt"][:10]
                data.append({
                    "수집일": now_str,
                    "등급": get_grade(ratio),
                    "성과비율(%)": ratio,
                    "썸네일": snippet["thumbnails"]["high"]["url"],
                    "영상제목": snippet["title"],
                    "채널명": snippet["channelTitle"],
                    "구독자수": sub_count,
                    "조회수": view_count,
                    "영상길이": parse_duration(content.get("duration", "")),
                    "업로드일": pub_date,
                    "링크": f"https://www.youtube.com/watch?v={v_id}",
                })

            if not data:
              st.info("설정한 최소 성과 비율을 충족하는 영상이 없습니다.")
            else:
              df = pd.DataFrame(data)
              df = df.sort_values(by="성과비율(%)", ascending=False)
              st.success(
                  f"총 {len(df)}개의 떡상 영상을 성공적으로 추출했습니다!"
              )

              st.dataframe(
                  df,
                  column_config={
                      "썸네일": st.column_config.ImageColumn("썸네일"),
                      "링크": st.column_config.LinkColumn("영상링크"),
                      "구독자수": st.column_config.NumberColumn(
                          "구독자수", format="%d 명"
                      ),
                      "조회수": st.column_config.NumberColumn(
                          "조회수", format="%d 회"
                      ),
                      "성과비율(%)": st.column_config.NumberColumn(
                          "성과비율", format="%.1f%%"
                      ),
                  },
                  use_container_width=True,
                  hide_index=True,
              )

              csv = df.to_csv(index=False).encode("utf-8-sig")
              st.download_button(
                  label="📥 엑셀(CSV) 파일로 다운로드",
                  data=csv,
                  file_name=(
                      f"youtube_trends_{datetime.now().strftime('%Y%m%d')}.csv"
                  ),
                  mime="text/csv",
              )
        except Exception as e:
          st.error(f"오류가 발생했습니다: {e}")

# ---------------------------------------------------------
# [탭 2] 스크립트 추출 및 AI 대본 생성기
# ---------------------------------------------------------
with tab2:
  st.subheader("🎥 영상 분석 & ChatGPT/Claude 프롬프트 생성기")

  video_url_input = st.text_input(
      "분석할 유튜브 영상 링크 입력",
      placeholder="https://www.youtube.com/watch?v=XXXXXX",
  )
  num_captures = st.slider(
      "주요 장면 타임스탬프 추출 개수", min_value=8, max_value=12, value=10
  )


  def extract_video_id(url):
    pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None


  if st.button("⚡ 스크립트 추출 및 프롬프트 생성", type="primary"):
    if not video_url_input:
      st.warning("유튜브 영상 링크를 입력해 주세요.")
    else:
      v_id = extract_video_id(video_url_input)
      if not v_id:
        st.error("유효한 유튜브 영상 URL이 아닙니다.")
      else:
        with st.spinner("자막 및 주요 장면 타임스탬프를 처리 중입니다..."):
          try:
            # =========================================================
            # [수정 위치] 1. 프록시(Proxy) 주소 설정 (Streamlit Cloud IP 차단 우회)
            # =========================================================
            # 공용 프록시 서버 등록 (필요시 다른 동작하는 무료/유료 프록시 IP로 교체 가능)
            proxies = {
                "http": "http://103.152.112.162:80",
                "https": "http://103.152.112.162:80",
            }

            # =========================================================
            # [수정 위치] 2. 자막 요청 시 proxies 파라미터 전달
            # =========================================================
            try:
              # 최신 인스턴스 형태 호출 시 proxies 전달
              ytt = YouTubeTranscriptApi()
              fetched = ytt.fetch(
                  v_id, languages=["ko", "en", "en-US"], proxies=proxies
              )
              transcript_list = fetched.data
            except Exception:
              # 구버전/대체 함수 호출 시 proxies 전달
              transcript_list = YouTubeTranscriptApi.get_transcript(
                  v_id, languages=["ko", "en", "en-US"], proxies=proxies
              )

            # ---------------------------------------------------------
            # 이하 기존 자막 텍스트 결합 및 타임스탬프 추출 로직 (동일)
            # ---------------------------------------------------------
            full_text = " ".join([
                item["text"] if isinstance(item, dict) else item.text
                for item in transcript_list
            ])
            total_duration = (
                transcript_list[-1]["start"]
                if isinstance(transcript_list[-1], dict)
                else transcript_list[-1].start
            )

            # 주요 장면 타임스탬프 산출
            interval = (
                total_duration / num_captures if total_duration > 0 else 0
            )
            timestamps = []

            st.markdown("### 📸 주요 장면 캡처 (타임스탬프 기반)")
            cols = st.columns(4)

            for i in range(num_captures):
              target_sec = int(i * interval)
              m, s = divmod(target_sec, 60)
              h, m = divmod(m, 60)
              time_str = (
                  f"{h:02d}:{m:02d}:{s:02d}"
                  if h > 0
                  else f"{m:02d}:{s:02d}"
              )

              ts_link = f"https://youtu.be/{v_id}?t={target_sec}"
              timestamps.append(f"장면 {i+1} [{time_str}]: {ts_link}")

              with cols[i % 4]:
                st.caption(f"📍 장면 {i+1} ({time_str})")
                st.image(
                    f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg",
                    use_column_width=True,
                )
                st.markdown(f"[▶️ 해당 장면 보기]({ts_link})")

            # ChatGPT / Claude 프롬프트 자동 구성
            timestamps_text = "\n".join(timestamps)
            ai_prompt = f"""아래는 외국인이 한국을 여행하며 남긴 영상 스크립트와 주요 장면 캡처 타임스탬프 정보야.
한국 시청자가 흥미를 느낄 수 있도록 '외국인의 시선과 본국의 문화 차이'를 비교 분석하는 제3자 나레이션 대본을 작성해줘.
시청 지속률이 잘 나오도록 궁금증을 유발하는 구조로 8분 이상의 롱폼 유튜브 대본을 만들어줘.

[유튜브 원본 영상 URL]
{video_url_input}

[주요 장면 타임스탬프 (캡처 구간)]
{timestamps_text}

[원본 자막 스크립트]
{full_text[:3000]} ...(이하 생략)
"""

            st.markdown("---")
            st.markdown("### 🤖 ChatGPT / Claude 전달용 프롬프트")
            st.code(ai_prompt, language="markdown")

            st.text_area(
                "📄 원본 전체 스크립트 (복사용)", value=full_text, height=150
            )

          except Exception as e:
            st.error(
                "자막을 불러올 수 없습니다. 프록시 서버 연결 실패 또는 원본"
                f" 영상에 자막이 없을 수 있습니다: {e}"
            )
