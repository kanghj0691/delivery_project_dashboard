"""
예제: 신규 권역 성장 기회
5주차 설계 예제의 쿼리를 SQLite로 바꾸고, 6주차 리포트의 KPI 카드 3개 · 차트 3장을
필터에 반응하도록 옮겨 둔 코드입니다. 

탭 3개(개요 · 탐색 · 액션) 뼈대가 들어 있습니다.
- ✏️표시: 내 5주차 · 6주차 결과물로 변경할 곳
- [블록 A] · [블록 B] · [블록 C]: Gemini에게 받은 블록으로 통째로 바꿀 곳
  (===== 시작 줄과 ===== 끝 줄 사이를 지우고 받은 블록을 붙임, 첫 줄은 맨 앞에 빈칸 없이)
"""
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

ACCENT, GRAY = "#1F3A5F", "#BDBDBD"
px.defaults.color_discrete_map = {
    "INSTA_첫주문쿠폰": ACCENT, "organic": "#8C8C8C", "NAVER_검색광고": "#A6A6A6",
    "GOOGLE_앱설치": GRAY, "친구초대": "#DADADA", "Android": "#8C8C8C", "iOS": GRAY,
}
px.defaults.color_discrete_sequence = [GRAY]

st.set_page_config(page_title="신규 권역 성장 기회 대시보드", layout="wide")
st.title("신규 권역 성장 기회 대시보드")                                  # ✏️ 6주차 메인 제목
st.caption("가입월 · 가입 채널 · 플랫폼별 | 2025.09 ~ 2026.07 가입자")     # ✏️ 6주차 부제

# ------------------------------------------------------------
# 0. 필요한 데이터만 추출 — 쓸 테이블과 컬럼만 메모리 DB에 올리고, 정제 테이블을 처음 한 번만 만듦
# ------------------------------------------------------------
DATA_DIR = "data"                          # 원본 CSV를 넣어 둔 폴더
NEEDED = {                                 # ✏️ 이번 대시보드에 필요한 테이블과 컬럼 (쿼리에 쓰는 것만)
    "app_events": ["event_datetime", "customer_id", "session_id", "event_name",
                   "platform", "traffic_source", "campaign_name"],
    "orders": ["customer_id", "order_datetime"],
}

@st.cache_resource
def get_db():                              # 필요한 컬럼만 메모리 DB에 올리고, 정제 테이블 events·odr을 생성(처음 한 번)
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for name, cols in NEEDED.items():
        # dtype=str: 고객 ID의 앞자리 0(0000002)이 숫자로 바뀌지 않게 글자로 읽음
        pd.read_csv(f"{DATA_DIR}/{name}.csv", usecols=cols, dtype=str).to_sql(name, con, index=False)
    # ✏️ 5주차 제외 규칙: 테스트 계정(T로 시작) 제외 · 이벤트 100건 이상인 비정상 세션 제외
    con.execute("""
        CREATE TABLE events AS
        SELECT *
          FROM app_events
         WHERE customer_id NOT LIKE 'T%'
           AND session_id NOT IN (SELECT session_id FROM app_events
                                   GROUP BY session_id HAVING COUNT(*) >= 100)
    """)
    con.execute("CREATE TABLE odr AS SELECT * FROM orders WHERE customer_id NOT LIKE 'T%'")
    # 고객별로 묶는 집계가 빨라지도록 customer_id에 인덱스를 붙임
    con.execute("CREATE INDEX idx_events_customer ON events(customer_id)")
    con.execute("CREATE INDEX idx_odr_customer ON odr(customer_id)")
    return con

# ------------------------------------------------------------
# 1. 데이터 준비 — 정제된 테이블을 SQL로 집계 (비율이 아니라 분자 · 분모 건수만)
# ------------------------------------------------------------
@st.cache_data
def query(sql):                            # SQL을 실행해 표로 돌려줌
    return pd.read_sql(sql, get_db())

# 고객별 가입일 · 가입 채널 · 플랫폼 (가입 이벤트 기준) - 두 쿼리 모두 사용
SQL_SIGNUP = """
su AS (
    SELECT customer_id,
           DATE(MIN(event_datetime))                    AS 가입일,
           MIN(COALESCE(campaign_name, traffic_source)) AS 가입채널,
           MIN(platform)                                AS 플랫폼
      FROM events
     WHERE event_name = 'sign_up'
     GROUP BY customer_id
)
"""

# ✏️ 가입월 × 가입 채널 × 플랫폼별 가입 후 30일 퍼널 (예제 Q1 · Q3)
SQL_SIGNUP_FUNNEL = f"""
WITH {SQL_SIGNUP},
ev AS (                                     -- 가입 후 30일 안의 행동
    SELECT DISTINCT e.customer_id, e.event_name
      FROM events e
      JOIN su ON e.customer_id = su.customer_id
     WHERE julianday(DATE(e.event_datetime)) - julianday(su.가입일) BETWEEN 0 AND 30
),
fo AS (                                     -- 고객별 첫 주문일
    SELECT customer_id, DATE(MIN(order_datetime)) AS 첫주문일
      FROM odr
     GROUP BY customer_id
)
SELECT strftime('%Y-%m', su.가입일) AS 가입월,
       su.가입채널,
       su.플랫폼,
       COUNT(DISTINCT su.customer_id)                                                         AS 가입자,
       COUNT(DISTINCT CASE WHEN ev.event_name = 'view_restaurant' THEN su.customer_id END)    AS 식당조회,
       COUNT(DISTINCT CASE WHEN ev.event_name = 'add_to_cart'     THEN su.customer_id END)    AS 장바구니,
       COUNT(DISTINCT CASE WHEN ev.event_name = 'begin_checkout'  THEN su.customer_id END)    AS 결제시작,
       COUNT(DISTINCT CASE WHEN julianday(fo.첫주문일) - julianday(su.가입일) <= 30
                           THEN su.customer_id END)                                           AS 첫주문30일
  FROM su
  LEFT JOIN ev ON su.customer_id = ev.customer_id
  LEFT JOIN fo ON su.customer_id = fo.customer_id
 WHERE su.가입일 <= '2026-07-31'            -- 30일을 다 볼 수 있는 가입자만
 GROUP BY 1, 2, 3
 ORDER BY 1, 2, 3
"""

# ✏️ 가입월 × 가입 채널 × 플랫폼별 30일 재주문 (예제 Q2, 분모가 첫 주문 고객이라 표를 따로 만듦)
SQL_REORDER = f"""
WITH {SQL_SIGNUP},
seq AS (
    SELECT customer_id, order_datetime,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_datetime) AS 순번,
           LEAD(order_datetime) OVER (PARTITION BY customer_id ORDER BY order_datetime) AS 다음주문
      FROM odr
)
SELECT strftime('%Y-%m', su.가입일) AS 가입월,
       su.가입채널,
       su.플랫폼,
       COUNT(*)                                                                          AS 첫주문고객,
       SUM(CASE WHEN julianday(DATE(seq.다음주문)) - julianday(DATE(seq.order_datetime)) <= 30
                THEN 1 ELSE 0 END)                                                       AS 재주문30일
  FROM seq
  JOIN su ON seq.customer_id = su.customer_id
 WHERE seq.순번 = 1
   AND seq.order_datetime < '2026-08-01'    -- 30일을 다 볼 수 있는 첫 주문만
 GROUP BY 1, 2, 3
 ORDER BY 1, 2, 3
"""

@st.cache_data
def load_data():
    return query(SQL_SIGNUP_FUNNEL), query(SQL_REORDER)

df, rd = load_data()                       # df: 가입 후 30일 퍼널 / rd: 30일 재주문

# 📌 AI 해설: 아래 AI_NOTES = {} 한 줄을 Gemini가 준 AI_NOTES = { … } 로 바꾸기
AI_NOTES = {
    "전체": "전체 가입자 2,774명의 30일 첫 주문 전환율은 69.9%이며 가장 낮은 단계는 식당조회에서 장바구니 구간(84.1%)이다. 2026-01 가입월부터 전체 첫 주문 전환율이 60%대로 하락하는 양상을 보였다. 채널별 유입 구성 변화가 전체 지표 하락에 영향을 주었을 것으로 보인다.",
    "Android": "Android 가입자 1,502명의 30일 첫 주문 전환율은 69.2%, 30일 재주문율은 66.6%로 전체 평균과 유사하다. 가장 낮은 단계 전환율은 식당조회에서 장바구니 구간(83.8%)으로 나타났다. 전체 플랫폼 비중의 절반 이상을 차지하여 전체 지표 흐름을 대변하는 것으로 보인다.",
    "iOS": "iOS 가입자 1,272명의 30일 첫 주문 전환율은 70.7%, 30일 재주문율은 68.2%로 Android 대비 소폭 높다. 가장 낮은 단계 전환율은 식당조회에서 장바구니 구간(84.5%)이다. 플랫폼 간 유저 경험이나 특성 차이가 존재할 수 있으나 추가 확인이 필요하다.",
    "organic": "organic 가입자 847명의 30일 첫 주문 전환율은 75.2%, 30일 재주문율은 73.5%로 전체 대비 높다. 가장 낮은 단계는 식당조회에서 장바구니 구간(88.6%)이며 전 퍼널에서 우수한 수치를 기록했다. 자연 유입 고객의 서비스 관여도가 높기 때문인 것으로 보인다.",
    "INSTA_첫주문쿠폰": "INSTA_첫주문쿠폰 가입자 739명의 30일 첫 주문 전환율은 55.6%, 30일 재주문율은 44.5%로 다른 집단 대비 낮다. 2026-01 가입월부터 처음 나타났으며 식당조회에서 장바구니 단계가 72.4%로 가장 낮았다. 쿠폰 유입 특성상 체리피커 비중이 높았을 가능성이 있어 정밀한 분석이 필요하다.",
    "NAVER_검색광고": "NAVER_검색광고 가입자 517명의 30일 첫 주문 전환율은 76.4%, 30일 재주문율은 72.6%로 상위 수준이다. 가장 낮은 단계 전환율은 식당조회에서 장바구니 구간(87.7%)이다. 검색 의도를 가지고 유입된 고객인 만큼 서비스 이용 목적이 명확했던 것으로 보인다.",
    "GOOGLE_앱설치": "GOOGLE_앱설치 가입자 398명의 30일 첫 주문 전환율은 73.6%, 30일 재주문율은 72.7%이다. 다른 집단과 달리 장바구니에서 결제시작 단계(88.0%)가 가장 낮은 전환율을 기록했다. 설치 캠페인 성격에 따른 결제 단계 허들이 존재했을 수 있어 확인이 필요하다.",
    "친구초대": "가입자가 273명으로 300명 미만인 친구초대 집단의 30일 첫 주문 전환율은 74.4%, 30일 재주문율은 77.3%로 재주문율이 가장 높다. 가장 낮은 단계는 식당조회에서 장바구니 구간(87.1%)이다. 모수가 작아 변동성이 있을 수 있으나 추천을 통해 충성도 높은 사용자가 유입된 것으로 보인다."
}
AI_SOURCE = "🤖 Gemini가 미리 만든 해설 · 전체 기간 기준"

# ------------------------------------------------------------
# 2. 사이드바 필터 — 두 표에 같은 조건을 적용
# ------------------------------------------------------------
SMALL = 100                                # ✏️ 이보다 가입자가 적은 집단은 "작은 집단"

if "reset" not in st.session_state:
    st.session_state.reset = 0

def reset_filters():                       # 번호가 바뀌면 위젯이 처음 상태로 새로 만들어짐
    st.session_state.reset += 1

n = st.session_state.reset
months = sorted(df["가입월"].unique())
channels = sorted(df["가입채널"].unique())
platforms = sorted(df["플랫폼"].unique())

st.sidebar.header("필터")
start, end = st.sidebar.select_slider("가입월", options=months,
                                      value=(months[0], months[-1]), key=f"기간_{n}")
sel_channels = st.sidebar.multiselect("가입 채널", channels, default=channels, key=f"채널_{n}")
sel_platforms = st.sidebar.multiselect("플랫폼", platforms, default=platforms, key=f"플랫폼_{n}")
with st.sidebar.expander("고급 설정"):
    base_start, base_end = st.select_slider(
        "평소 범위 기준 기간", options=months, value=(months[0], months[3]), key=f"기준_{n}",   # ✏️ 문제가 없던 기간
        help="문제가 없던 기간을 고르세요. 이 기간의 월별 값 범위를 '평소 범위'로 씁니다.")
    hide_small = st.checkbox(f"가입자 {SMALL}명 미만 집단 제외 (집단 비교 · 드릴다운)", key=f"작은집단_{n}")
st.sidebar.button("필터 초기화", on_click=reset_filters)

# 집단 조건(가입 채널 · 플랫폼)만 적용한 데이터 g · rg, 기간까지 적용한 데이터 f · rf
g = df[df["가입채널"].isin(sel_channels) & df["플랫폼"].isin(sel_platforms)]
f = g[(g["가입월"] >= start) & (g["가입월"] <= end)]
rg = rd[rd["가입채널"].isin(sel_channels) & rd["플랫폼"].isin(sel_platforms)]
rf = rg[(rg["가입월"] >= start) & (rg["가입월"] <= end)]

def label(selected, all_values):           # 조건 줄에 쓸 말: 모두 고르면 "전체"
    if len(selected) == len(all_values):
        return "전체"
    return ", ".join(selected) if selected else "선택 없음"

period = "전체" if (start, end) == (months[0], months[-1]) else f"{start} ~ {end}"
st.caption(f"🔎 보고 있는 조건: 가입월 {period} · 가입 채널 {label(sel_channels, channels)} · "
           f"플랫폼 {label(sel_platforms, platforms)}")

if f.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다. 필터를 바꿔 주세요.")
    st.stop()

def rate(a, b):
    return a / b * 100 if b else 0

# ------------------------------------------------------------
# 3. 화면 — 탭 3개
# ------------------------------------------------------------
tab_overview, tab_explore, tab_action = st.tabs(["📊 개요", "🔍 탐색", "✅ 액션"])

# ===== [블록 A] 개요 · KPI 카드 — 규칙 문장 단계에서 이 블록을 통째로 바꿈 =====
with tab_overview:
    st.caption("이 탭에서 볼 수 있는 것: 핵심 숫자와 그 숫자를 읽는 법, 6주차 리포트의 차트 3장 (필터 적용)")

    # 3-1. KPI 카드 — ✏️ 5주차 지표 3개
    t = f[["가입자", "식당조회", "장바구니", "첫주문30일"]].sum()
    tr = rf[["첫주문고객", "재주문30일"]].sum()
    c1, c2, c3 = st.columns(3)
    c1.metric("30일 첫 주문 전환율", f"{rate(t['첫주문30일'], t['가입자']):.1f}%")
    c2.metric("식당 조회 → 장바구니 전환율", f"{rate(t['장바구니'], t['식당조회']):.1f}%")
    c3.metric("30일 재주문율", f"{rate(tr['재주문30일'], tr['첫주문고객']):.1f}%")

    # 지금 숫자 읽기 상자 추가
    with st.container(border=True):
        st.markdown("**📏 지금 숫자 읽기**")
        
        # 유효성 검사 및 계산 로직
        sorted_months = sorted(f["가입월"].unique())
        
        # 1. 30일 첫 주문 전환율 메시지 생성
        msg_order = ""
        if len(sorted_months) < 3:
            msg_order = "30일 첫 주문 전환율: 비교하려면 선택 기간을 3개월 이상 골라 주세요"
        else:
            last_3_months = sorted_months[-3:]
            f_last3 = f[f["가입월"].isin(last_3_months)]
            t_last3 = f_last3[["가입자", "첫주문30일"]].sum()
            current_order_rate = rate(t_last3["첫주문30일"], t_last3["가입자"])
            start_month_label = last_3_months[0]
            
            g_base = g[(g["가입월"] >= base_start) & (g["가입월"] <= base_end)]
            g_base_grouped = g_base.groupby("가입월")[["가입자", "첫주문30일"]].sum()
            g_base_grouped = g_base_grouped[g_base_grouped["가입자"] > 0]
            
            if len(g_base_grouped) < 3:
                msg_order = "30일 첫 주문 전환율: 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요"
            else:
                monthly_rates = (g_base_grouped["첫주문30일"] / g_base_grouped["가입자"] * 100)
                min_rate = monthly_rates.min()
                max_rate = monthly_rates.max()
                
                if current_order_rate < min_rate:
                    diff_val = round(min_rate - current_order_rate, 1)
                    comp_text = f"평소 범위({min_rate:.1f}–{max_rate:.1f}%)보다 {diff_val:.1f}%p 낮습니다"
                elif current_order_rate > max_rate:
                    diff_val = round(current_order_rate - max_rate, 1)
                    comp_text = f"평소 범위({min_rate:.1f}–{max_rate:.1f}%)보다 {diff_val:.1f}%p 높습니다"
                else:
                    comp_text = f"평소 범위({min_rate:.1f}–{max_rate:.1f}%) 안입니다"
                
                msg_order = f"{start_month_label} 가입월부터 3개월 30일 첫 주문 전환율은 {current_order_rate:.1f}%로, {comp_text}"

        # 2. 식당 조회 → 장바구니 전환율 메시지 생성
        msg_cart = ""
        if len(sorted_months) < 3:
            msg_cart = "식당 조회 → 장바구니 전환율: 비교하려면 선택 기간을 3개월 이상 골라 주세요"
        else:
            last_3_months = sorted_months[-3:]
            f_last3 = f[f["가입월"].isin(last_3_months)]
            t_last3 = f_last3[["식당조회", "장바구니"]].sum()
            current_cart_rate = rate(t_last3["장바구니"], t_last3["식당조회"])
            start_month_label = last_3_months[0]
            
            g_base = g[(g["가입월"] >= base_start) & (g["가입월"] <= base_end)]
            g_base_grouped = g_base.groupby("가입월")[["식당조회", "장바구니"]].sum()
            g_base_grouped = g_base_grouped[g_base_grouped["식당조회"] > 0]
            
            if len(g_base_grouped) < 3:
                msg_cart = "식당 조회 → 장바구니 전환율: 기준 기간을 이 집단의 데이터가 있는 시기로 옮겨 주세요"
            else:
                monthly_rates = (g_base_grouped["장바구니"] / g_base_grouped["식당조회"] * 100)
                min_rate = monthly_rates.min()
                max_rate = monthly_rates.max()
                
                if current_cart_rate < min_rate:
                    diff_val = round(min_rate - current_cart_rate, 1)
                    comp_text = f"평소 범위({min_rate:.1f}–{max_rate:.1f}%)보다 {diff_val:.1f}%p 낮습니다"
                elif current_cart_rate > max_rate:
                    diff_val = round(current_cart_rate - max_rate, 1)
                    comp_text = f"평소 범위({min_rate:.1f}–{max_rate:.1f}%)보다 {diff_val:.1f}%p 높습니다"
                else:
                    comp_text = f"평소 범위({min_rate:.1f}–{max_rate:.1f}%) 안입니다"
                
                msg_cart = f"{start_month_label} 가입월부터 3개월 식당 조회 → 장바구니 전환율은 {current_cart_rate:.1f}%로, {comp_text}"

        st.markdown(f"- {msg_order}")
        st.markdown(f"- {msg_cart}")
        
        st.caption(f"📏 자동 계산 · 평소 범위 기준 기간 {base_start} ~ {base_end} (월별 값)")

        with st.expander("🤖 AI 해설 · 전체", expanded=False):
            st.write(AI_NOTES.get("전체", "아직 해설이 없습니다."))
            st.caption(AI_SOURCE)
# ===== [블록 A] 끝 =====    

with tab_overview:
    st.divider()

    # ✏️ 3-2. 차트 - 6주차 차트 ① 문제 · ② 원인 · ③ 제안
    left, right = st.columns(2)

    # ① 문제: 가입월별 30일 첫 주문 전환율
    m = f.groupby("가입월")[["가입자", "첫주문30일"]].sum().reset_index()
    m["첫주문전환율"] = (m["첫주문30일"] / m["가입자"] * 100).round(1)
    fig1 = px.line(m, x="가입월", y="첫주문전환율", markers=True, hover_data=["가입자"],
                   labels={"가입월": "가입월", "첫주문전환율": "30일 첫 주문 전환율(%)", "가입자": "가입자(명)"},
                   title="① 가입월별 30일 첫 주문 전환율")
    fig1.update_layout(xaxis_title="")
    fig1.update_xaxes(type="category")       # 가입월(2025-09)을 날짜가 아니라 글자 그대로 표시
    left.plotly_chart(fig1, width="stretch")

    # ② 원인: 가입 채널별 식당 조회 → 장바구니 전환율
    ch = f.groupby("가입채널")[["식당조회", "장바구니"]].sum().reset_index()
    ch["장바구니전환율"] = (ch["장바구니"] / ch["식당조회"] * 100).round(1)
    ch = ch.sort_values("장바구니전환율")
    fig2 = px.bar(ch, x="장바구니전환율", y="가입채널", orientation="h", text_auto=".1f",
                  hover_data=["식당조회"],
                  labels={"장바구니전환율": "식당 조회 → 장바구니 전환율(%)", "가입채널": "가입 채널",
                          "식당조회": "식당 조회 가입자(명)"},
                  title="② 가입 채널별 식당 조회 → 장바구니 전환율")
    fig2.update_xaxes(range=[0, ch["장바구니전환율"].max() * 1.2])
    fig2.update_layout(yaxis_title="")
    right.plotly_chart(fig2, width="stretch")

    # ③ 제안: 가입 채널별 30일 재주문율
    rc = rf.groupby("가입채널")[["첫주문고객", "재주문30일"]].sum().reset_index()
    rc["재주문율"] = (rc["재주문30일"] / rc["첫주문고객"] * 100).round(1)
    rc = rc.sort_values("재주문율")
    fig3 = px.bar(rc, x="재주문율", y="가입채널", orientation="h", text_auto=".1f",
                  hover_data=["첫주문고객"],
                  labels={"재주문율": "30일 재주문율(%)", "가입채널": "가입 채널", "첫주문고객": "첫 주문 고객(명)"},
                  title="③ 가입 채널별 30일 재주문율")
    fig3.update_xaxes(range=[0, rc["재주문율"].max() * 1.2])
    fig3.update_layout(yaxis_title="")
    st.plotly_chart(fig3, width="stretch")

    # AI 해설을 만들 때 Gemini에 올릴 표 (필터와 관계없이 전체)
    with st.expander("📥 AI 해설용 데이터 내려받기"):
        st.download_button("가입 후 30일 퍼널 (가입월 × 가입 채널 × 플랫폼)",
                           df.to_csv(index=False).encode("utf-8-sig"), "가입월_채널_플랫폼_퍼널.csv")
        st.download_button("30일 재주문 (가입월 × 가입 채널 × 플랫폼)",
                           rd.to_csv(index=False).encode("utf-8-sig"), "가입월_채널_플랫폼_재주문.csv")

# ===== [블록 B] 탐색 — 집단 비교 · 드릴다운 단계에서 이 블록을 통째로 바꿈 =====
with tab_explore:
    st.caption("이 탭에서 볼 수 있는 것: 집단 비교와 드릴다운 — 어디서, 언제부터인가")
    
    group_col = st.radio("비교 기준", ["가입채널", "플랫폼"], horizontal=True, key="탐색_비교기준")
    
    # 집단별 퍼널 5단계 합계 계산
    cols_to_sum = ["가입자", "식당조회", "장바구니", "결제시작", "첫주문30일"]
    df_grouped = f.groupby(group_col)[cols_to_sum].sum().reset_index()
    
    # 작은 집단 제외 처리
    excluded_groups = []
    if hide_small:
        small_groups = df_grouped[df_grouped["가입자"] < SMALL][group_col].tolist()
        if small_groups:
            excluded_groups = small_groups
            df_grouped = df_grouped[df_grouped["가입자"] >= SMALL]
            st.caption(f"제외한 집단: {', '.join(str(g) for g in small_groups)} (가입자 {SMALL}명 미만)")
            
    if df_grouped.empty:
        st.warning("조건에 맞는 집단이 없습니다.")
    else:
        # 남은 집단 중 가입자가 SMALL명 미만인 집단이 있으면 안내
        if not hide_small:
            small_remaining = df_grouped[df_grouped["가입자"] < SMALL][group_col].tolist()
            if small_remaining:
                st.caption(f"⚠️ 안내: 가입자가 {SMALL}명 미만인 집단({', '.join(str(g) for g in small_remaining)})이 포함되어 있어 값이 크게 흔들릴 수 있습니다.")
                
        # 데이터프레임을 퍼널 차트용 long-form으로 변환
        # px.funnel을 위해 각 단계를 행으로 만듦
        stages = ["가입자", "식당조회", "장바구니", "결제시작", "첫주문30일"]
        
        melted_list = []
        for _, row in df_grouped.iterrows():
            g_name = row[group_col]
            base_val = row["가입자"]
            for stage in stages:
                val = row[stage]
                # 누적 전환율(%) 계산 (가입자 대비)
                conv_rate = (val / base_val * 100) if base_val > 0 else 0
                melted_list.append({
                    group_col: g_name,
                    "단계": stage,
                    "사람수": val,
                    "누적전환율": round(conv_rate, 1)
                })
        df_melted = pd.DataFrame(melted_list)
        
        left_col, right_col = st.columns(2)
        
        with left_col:
            # 누적 전환율 퍼널 (x축을 누적전환율로 설정)
            fig_funnel = px.funnel(
                df_melted,
                x="누적전환율",
                y="단계",
                color=group_col,
                labels={"누적전환율": "누적 전환율(%)", "단계": "퍼널 단계", group_col: "집단"},
                title="집단별 누적 전환율 퍼널"
            )
            st.plotly_chart(fig_funnel, width="stretch")
            
        with right_col:
            # 단계 전환율(직전 단계 대비 %) 계산
            step_rates = []
            for g_name, group_data in df_grouped.groupby(group_col):
                vals = [group_data[s].values[0] for s in stages]
                for i in range(1, len(stages)):
                    prev_stage = stages[i-1]
                    curr_stage = stages[i]
                    prev_val = vals[i-1]
                    curr_val = vals[i]
                    step_rate = (curr_val / prev_val * 100) if prev_val > 0 else 0
                    
                    step_rates.append({
                        group_col: g_name,
                        "단계": f"{prev_stage} → {curr_stage}",
                        "단계전환율": round(step_rate, 1),
                        "직전단계사람수": prev_val,
                        "현재사람수": curr_val
                    })
            df_step = pd.DataFrame(step_rates)
            
            fig_bar = px.bar(
                df_step,
                x="단계전환율",
                y="단계",
                color=group_col,
                barmode="group",
                text="단계전환율",
                hover_data={
                    "단계전환율": True,
                    "직전단계사람수": True,
                    "현재사람수": True
                },
                labels={
                    "단계전환율": "단계 전환율(%)",
                    "단계": "퍼널 구간",
                    group_col: "집단",
                    "직전단계사람수": "직전 단계 사람 수(명)",
                    "현재사람수": "현재 단계 사람 수(명)"
                },
                title="집단별 단계 전환율 비교"
            )
            fig_bar.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            st.plotly_chart(fig_bar, width="stretch")

with tab_explore:
    st.caption("이 탭에서 볼 수 있는 것: 집단 비교와 드릴다운 — 어디서, 언제부터인가")
    
    group_col = st.radio("비교 기준", ["가입채널", "플랫폼"], horizontal=True, key=f"탐색_비교기준_{n}")
    
    # 집단별 퍼널 5단계 합계 계산
    cols_to_sum = ["가입자", "식당조회", "장바구니", "결제시작", "첫주문30일"]
    df_grouped = f.groupby(group_col)[cols_to_sum].sum().reset_index()
    
    # 작은 집단 제외 처리
    excluded_groups = []
    if hide_small:
        small_groups = df_grouped[df_grouped["가입자"] < SMALL][group_col].tolist()
        if small_groups:
            excluded_groups = small_groups
            df_grouped = df_grouped[df_grouped["가입자"] >= SMALL]
            st.caption(f"제외한 집단: {', '.join(str(g) for g in small_groups)} (가입자 {SMALL}명 미만)")
            
    if df_grouped.empty:
        st.warning("조건에 맞는 집단이 없습니다.")
    else:
        # 남은 집단 중 가입자가 SMALL명 미만인 집단이 있으면 안내
        if not hide_small:
            small_remaining = df_grouped[df_grouped["가입자"] < SMALL][group_col].tolist()
            if small_remaining:
                st.caption(f"⚠️ 안내: 가입자가 {SMALL}명 미만인 집단({', '.join(str(g) for g in small_remaining)})이 포함되어 있어 값이 크게 흔들릴 수 있습니다.")
                
        # 데이터프레임을 퍼널 차트용 long-form으로 변환
        stages = ["가입자", "식당조회", "장바구니", "결제시작", "첫주문30일"]
        
        melted_list = []
        for _, row in df_grouped.iterrows():
            g_name = row[group_col]
            base_val = row["가입자"]
            for stage in stages:
                val = row[stage]
                conv_rate = (val / base_val * 100) if base_val > 0 else 0
                melted_list.append({
                    group_col: g_name,
                    "단계": stage,
                    "사람수": val,
                    "누적전환율": round(conv_rate, 1)
                })
        df_melted = pd.DataFrame(melted_list)
        
        left_col, right_col = st.columns(2)
        
        with left_col:
            fig_funnel = px.funnel(
                df_melted,
                x="누적전환율",
                y="단계",
                color=group_col,
                labels={"누적전환율": "누적 전환율(%)", "단계": "퍼널 단계", group_col: "집단"},
                title="집단별 누적 전환율 퍼널"
            )
            st.plotly_chart(fig_funnel, width="stretch", key=f"chart_funnel_{n}")
            
        with right_col:
            step_rates = []
            for g_name, group_data in df_grouped.groupby(group_col):
                vals = [group_data[s].values[0] for s in stages]
                for i in range(1, len(stages)):
                    prev_stage = stages[i-1]
                    curr_stage = stages[i]
                    prev_val = vals[i-1]
                    curr_val = vals[i]
                    step_rate = (curr_val / prev_val * 100) if prev_val > 0 else 0
                    
                    step_rates.append({
                        group_col: g_name,
                        "단계": f"{prev_stage} → {curr_stage}",
                        "단계전환율": round(step_rate, 1),
                        "직전단계사람수": prev_val,
                        "현재사람수": curr_val
                    })
            df_step = pd.DataFrame(step_rates)
            
            fig_bar = px.bar(
                df_step,
                x="단계전환율",
                y="단계",
                color=group_col,
                barmode="group",
                text="단계전환율",
                hover_data={
                    "단계전환율": True,
                    "직전단계사람수": True,
                    "현재사람수": True
                },
                labels={
                    "단계전환율": "단계 전환율(%)",
                    "단계": "퍼널 구간",
                    group_col: "집단",
                    "직전단계사람수": "직전 단계 사람 수(명)",
                    "현재사람수": "현재 단계 사람 수(명)"
                },
                title="집단별 단계 전환율 비교"
            )
            fig_bar.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            st.plotly_chart(fig_bar, width="stretch", key=f"chart_step_bar_{n}")

    st.divider()
    st.subheader("드릴다운: 언제부터, 무엇 때문일까")

    # 선택 가능한 집단 목록 구성
    available_groups = df_grouped[group_col].tolist() if not df_grouped.empty else []
    
    if available_groups:
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            selected_group = st.selectbox("자세히 볼 집단", available_groups, key=f"드릴다운_집단_{n}")
        with d_col2:
            selected_stage_label = st.selectbox(
                "단계", 
                ["가입 → 30일 첫 주문", "가입 → 식당조회", "식당조회 → 장바구니", "장바구니 → 결제시작", "결제시작 → 30일 첫 주문"], 
                key=f"드릴다운_단계_{n}"
            )

        # 다른 축 결정
        other_col = "플랫폼" if group_col == "가입채널" else "가입채널"

        # 단계별 분자/분모 매핑 정의
        stage_mapping = {
            "가입 → 30일 첫 주문": ("첫주문30일", "가입자"),
            "가입 → 식당조회": ("식당조회", "가입자"),
            "식당조회 → 장바구니": ("장바구니", "식당조회"),
            "장바구니 → 결제시작": ("결제시작", "장바구니"),
            "결제시작 → 30일 첫 주문": ("첫주문30일", "결제시작")
        }
        num_col, den_col = stage_mapping[selected_stage_label]

        # 차트 ① 데이터 준비: f에서 선택한 집단만 필터링 후 다른 축과 가입월별로 집계
        sub_f = f[f[group_col] == selected_group]
        trend_df = sub_f.groupby(["가입월", other_col])[[num_col, den_col]].sum().reset_index()
        
        # 직전 단계 사람 수가 0인 경우 None(빈 값)으로 처리하기 위한 계산
        trend_df["전환율"] = trend_df.apply(
            lambda row: round(row[num_col] / row[den_col] * 100, 1) if row[den_col] > 0 else None, 
            axis=1
        )

        fig_trend = px.line(
            trend_df,
            x="가입월",
            y="전환율",
            color=other_col,
            markers=True,
            hover_data=[num_col, den_col],
            labels={
                "가입월": "가입월",
                "전환율": "단계 전환율(%)",
                other_col: other_col,
                num_col: "분자 사람 수(명)",
                den_col: "직전 단계 사람 수(명)"
            },
            title=f"① {selected_group}의 가입월별 {selected_stage_label} 전환율 — {other_col}별로 쪼개 보기"
        )
        fig_trend.update_layout(xaxis_title="")
        fig_trend.update_xaxes(type="category")
        st.plotly_chart(fig_trend, width="stretch", key=f"chart_trend_{n}")
        st.caption("모든 갈래가 함께 움직였다면, 그 축은 원인이 아닙니다.")

        # 차트 ② 데이터 준비: 가입월별 전체 가입자 중에서 선택한 집단 vs 그 외 구분
        f_copy = f.copy()
        f_copy["집단구분"] = f_copy[group_col].apply(lambda x: selected_group if x == selected_group else "그 외")
        
        bar_df = f_copy.groupby(["가입월", "집단구분"])["가입자"].sum().reset_index()
        
        # 색상 지정: 선택 집단은 진한 남색 계열, 그 외는 회색 계열
        color_map = {selected_group: "#1f77b4", "그 외": "#d3d3d3"}

        fig_bar2 = px.bar(
            bar_df,
            x="가입월",
            y="가입자",
            color="집단구분",
            barmode="stack",
            color_discrete_map=color_map,
            labels={"가입월": "가입월", "가입자": "가입자 수(명)", "집단구분": "집단"},
            title=f"② 가입월별 가입자 수 구성 ({selected_group} vs 그 외)"
        )
        fig_bar2.update_layout(xaxis_title="")
        fig_bar2.update_xaxes(type="category")
        st.plotly_chart(fig_bar2, width="stretch", key=f"chart_bar2_{n}")
        st.caption("전체 전환율이 움직인 시점에 이 집단의 비중이 함께 바뀌었다면 구성 변화가 원인 후보입니다. 함께 움직였다고 원인이 확정되지는 않습니다.")

        # AI 해설 익스팬더
        with st.expander(f"🤖 AI 해설 · {selected_group}", expanded=False):
            note_text = AI_NOTES.get(selected_group, "이 집단의 해설은 아직 없습니다.")
            st.write(note_text)
            st.caption(AI_SOURCE)
    else:
        st.info("선택 가능한 집단이 없습니다.")
            
# ===== [블록 B] 끝 =====

# ===== [블록 C] 액션 — 액션 카드 단계에서 이 줄 아래부터 파일 끝까지를 받은 블록으로 바꿈 =====
with tab_action:
    st.caption("측정 KPI의 현재 값은 선택한 기간의 마지막 4주로 계산합니다")
    
    # 카드 1, 2 계산 로직 (사이드바 기간만 적용, 플랫폼/유입경로 필터 무시)
    # 데이터베이스 연결 및 쿼리 실행을 통해 안전하게 계산
    try:
        db_con = get_db()
        
        # 카드 1 계산: 플랫폼이 Android인 데이터의 결제 전환율 (주문세션 ÷ 결제시작세션 또는 첫주문 ÷ 결제시작)
        # 선택된 사이드바 기간(start ~ end)의 마지막 4주(또는 해당 월 기준 최근 데이터) 계산
        q_card1 = f"""
            SELECT 
                SUM(CASE WHEN event_name = 'begin_checkout' THEN 1 ELSE 0 END) as 결제시작수,
                SUM(CASE WHEN event_name = 'order' THEN 1 ELSE 0 END) as 주문수
            FROM events
            WHERE platform = 'Android'
        """
        # 만약 events 테이블에 주문 이벤트가 없다면 odr 테이블과 조인하거나 퍼널 데이터 활용
        df_card1 = pd.read_sql(q_card1, db_con)
        
        # 안전한 계산을 위해 df(가입월_채널_플랫폼_퍼널)에서도 보조 계산 가능
        f_all_android = df[df["플랫폼"] == "Android"]
        # 기간 필터만 적용 (사이드바 start ~ end)
        f_card1_filtered = f_all_android[(f_all_android["가입월"] >= start) & (f_all_android["가입월"] <= end)]
        
        if not f_card1_filtered.empty:
            total_checkout = f_card1_filtered["결제시작"].sum()
            total_first_order = f_card1_filtered["첫주문30일"].sum()
            metric_val_1 = (total_first_order / total_checkout * 100) if total_checkout > 0 else 0
            metric_str_1 = f"{metric_val_1:.1f}%"
        else:
            metric_str_1 = "데이터 없음"
            
    except Exception:
        metric_str_1 = "데이터 없음"

    try:
        # 카드 2 계산: 유입경로가 push인 데이터의 방문 → 식당 조회 전환율 (조회세션 ÷ 세션수)
        f_all_push = df[df["가입채널"].str.contains("push|PUSH", na=False, case=False)]
        f_card2_filtered = f_all_push[(f_all_push["가입월"] >= start) & (f_all_push["가입월"] <= end)]
        
        if not f_card2_filtered.empty:
            total_signup = f_card2_filtered["가입자"].sum()
            total_view = f_card2_filtered["식당조회"].sum()
            metric_val_2 = (total_view / total_signup * 100) if total_signup > 0 else 0
            metric_str_2 = f"{metric_val_2:.1f}%"
        else:
            metric_str_2 = "데이터 없음"
    except Exception:
        metric_str_2 = "데이터 없음"

    col_action1, col_action2 = st.columns(2)
    
    with col_action1:
        with st.container(border=True):
            st.markdown("- **문제**: 결제 시작에서 주문 전환율이 2026-04-13 주부터 하락해 5월 3주차 최저 41.4%, 6월 1주차부터 회복")
            st.markdown("- **근거**: 같은 기간 iOS는 평소 범위 안 · Android 결제 실패가 주 4건 이하 → 최대 153건")
            st.markdown("- **성격**: 특정 시점에 발생한 문제")
            st.markdown("- **액션**: 추가 분석: 앱 버전별로 결제 실패 확인 → 모니터링: 결제 전환율이 평소 범위를 벗어나는지 매주 점검")
            st.markdown("- **우선순위**: 영향 큼 · 실행 쉬움 → 바로 실행")
            st.markdown("- **측정 KPI**: Android 결제 전환율 (최근 4주)")
            st.markdown("- **대시보드에서**: 개요 탭 규칙 문장(플랫폼 Android) · 탐색 탭 드릴다운")
            st.divider()
            st.metric("Android 결제 전환율", metric_str_1)
            st.caption("대시보드에서: 개요 탭 규칙 문장(플랫폼 Android) · 탐색 탭 드릴다운")
            
    with col_action2:
        with st.container(border=True):
            st.markdown("- **문제**: 방문 → 식당 조회 전환율 28.4% (다른 경로 57-69%), 주문 전환율 3.2%")
            st.markdown("- **근거**: 2026년 2월부터 월별 세션의 30-36%가 push · 기간 내내 25-35%")
            st.markdown("- **성격**: 전체 구간에 세그먼트별 반응 차이")
            st.markdown("- **액션**: 실험: 일부 사용자에게만 푸시 대상과 문구를 바꿔 방문 → 식당 조회 전환율 비교")
            st.markdown("- **우선순위**: 효과 불확실 · 실행 쉬움 → 실험부터")
            st.markdown("- **측정 KPI**: push 방문 → 식당 조회 전환율(최근 4주)")
            st.markdown("- **대시보드에서**: 탐색 탭 비교 기준 '유입경로' · 드릴다운 push")
            st.divider()
            st.metric("push 방문 → 식당 조회 전환율", metric_str_2)
            st.caption("대시보드에서: 탐색 탭 비교 기준 '유입경로' · 드릴다운 push")