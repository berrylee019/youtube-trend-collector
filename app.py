from datetime import datetime
import isodate
from googleapiclient.discovery import build
import pandas as pd
import streamlit as st

# 페이지 기본 설정
st.set_page_config(
    page_title="유튜브 떡상 영상 수집기", page_icon="🎬", layout="wide"
)

st.title("🎬 외국인 반응/브이로그 떡상 영상 수집기")
st.caption("구독자 수 대비 높은 조회수를 기록한 2차 창작용 영상을 발굴합니다.")

# 사이드바: 설정 및 API 키 입력
with st.sidebar:
  st.header("⚙️ 검색 및 API 설정")

  # Secrets에서 기본 키 가져오기 (없으면 빈 값)
  default_api_key = (
      st.secrets.get("YOUTUBE_API_KEY", "") if "YOUTUBE_API_KEY" in st.secrets else ""
  )

  api_key = st.text_input(
      "YouTube API Key", value=default_api_key, type="password"
  )
  search_keyword = st.text_input("검색 키워드", value="Korea vlog")
  max_results = st.slider("수집할 영상 수", min_value=10, max_value=50, value=20)
  min_ratio = st.number_input(
      "최소 성과 비율 (조회수/구독자수 %)", value=200, step=50
  )
  st.markdown("---")
  start_button = st.button("🚀 데이터 수집 시작", use_container_width=True)


# ISO 8601 영상 길이 변환 함수
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


# 등급 매기기 함수
def get_grade(ratio):
  if ratio >= 500:
    return "🔥 S등급 (500% 이상)"
  elif ratio >= 300:
    return "✨ A등급 (300% 이상)"
  elif ratio >= 150:
    return "👍 B등급 (150% 이상)"
  else:
    return "⚪ 일반"


# 영상 수집 실행 로직
if start_button:
  if not api_key:
    st.error(
        "YouTube API Key를 입력해주세요! (Streamlit Secrets 설정 또는 사이드바 입력)"
    )
  else:
    with st.spinner("유튜브 데이터를 분석 중입니다..."):
      try:
        youtube = build("youtube", "v3", developerKey=api_key)

        # 1. 키워드로 영상 검색
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
          # 2. 영상 상세 정보 추출
          videos_response = (
              youtube.videos()
              .list(
                  id=",".join(video_ids), part="snippet,statistics,contentDetails"
              )
              .execute()
          )

          channel_ids = list(
              set([
                  v["snippet"]["channelId"]
                  for v in videos_response.get("items", [])
              ])
          )

          # 3. 채널 정보 추출 (구독자 수)
          channels_response = (
              youtube.channels()
              .list(id=",".join(channel_ids), part="statistics")
              .execute()
          )

          channel_subs = {
              c["id"]: int(c["statistics"].get("subscriberCount", 0))
              for c in channels_response.get("items", [])
          }

          # 4. 데이터 정제 및 조합
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
                file_name=f"youtube_trends_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

      except Exception as e:
        st.error(f"오류가 발생했습니다: {e}")
