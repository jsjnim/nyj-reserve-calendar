"""남양주시 시설 예약 현황 캘린더 (Streamlit)

실행:  pip install streamlit requests beautifulsoup4
       streamlit run app.py
"""
import calendar
import json
import random
from datetime import date
from pathlib import Path

import streamlit as st

DATA_FILE = Path("reservations.json")
ACCOUNT_FILE = Path(".account.json")  # 로컬 실행 시 계정 기억용 (공개 배포 시 사용 금지)

STATUS_STYLE = {
    "신청대기": ("#6b7280", "#fff"),
    "결제대기": ("#f59e0b", "#fff"),
    "예약완료": ("#2563eb", "#fff"),
    "환불대기": ("#ef4444", "#fff"),
    "환불완료": ("#9ca3af", "#fff"),
}
HIDDEN_BY_DEFAULT = {"환불완료"}  # 환불은 캘린더에서 제외


# ---------------------------------------------------------------- 데이터
def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


def save_data(rows):
    DATA_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def key_of(r):
    return (r["date"], r["facility"], r["court"], r["hour"])


def merge(old, new):
    """같은 (날짜/시설/코트/시간) 건은 최신 상태로 덮어쓴다. 변경된 건 수도 반환."""
    old_map = {key_of(r): r for r in old}
    changed = 0
    for r in new:
        k = key_of(r)
        if k in old_map and old_map[k]["status"] != r["status"]:
            changed += 1
        old_map[k] = r
    return sorted(old_map.values(), key=lambda r: (r["date"], r["hour"])), changed


def fetch_mypage(user_id, password):
    """남양주시 통합예약 마이페이지에서 신청현황/이력현황을 끝 페이지까지 순회해 가져온다.

    TODO: 실제 로그인 URL, 목록 URL, 파싱 규칙을 채워 넣어야 한다.
    (브라우저 개발자도구 > Network 탭에서 로그인/목록 요청을 확인)
    반환 형식: [{"date":"2026-10-01","facility":"와부","court":"A코트","hour":15,"status":"예약완료"}, ...]
    """
    raise NotImplementedError("fetch_mypage()에 마이페이지 크롤링 로직을 구현하세요.")
    # --- 구현 예시 뼈대 -------------------------------------------------
    # import requests
    # from bs4 import BeautifulSoup
    # s = requests.Session()
    # s.post(LOGIN_URL, data={"id": user_id, "pw": password})
    # rows = []
    # for url in (APPLY_LIST_URL, HISTORY_LIST_URL):
    #     page = 1
    #     while True:
    #         soup = BeautifulSoup(s.get(url, params={"page": page}).text, "html.parser")
    #         items = soup.select("table tbody tr")
    #         if not items:
    #             break
    #         for tr in items:
    #             ...  # 날짜/시설/코트/시간/상태 파싱 후 rows.append({...})
    #         page += 1
    # return rows


def make_sample(year, month):
    random.seed(year * 100 + month)
    rows, last = [], calendar.monthrange(year, month)[1]
    for d in range(1, last + 1):
        for _ in range(random.randint(0, 4)):
            facility = random.choice(["와부", "와부", "와부", "월문"])
            court = random.choice(["A코트", "B코트", "C코트"]) if facility == "와부" else "시민코트"
            rows.append({
                "date": f"{year}-{month:02d}-{d:02d}",
                "facility": facility,
                "court": court,
                "hour": random.choice([11, 13, 15, 17, 19, 21]),
                "status": random.choices(list(STATUS_STYLE), weights=[1, 1, 8, 1, 1])[0],
            })
    return rows


# ---------------------------------------------------------------- 화면
st.set_page_config(page_title="남양주시 시설 예약 현황 캘린더", page_icon="📅", layout="centered")

st.markdown(
    """
<style>
.block-container{padding-top:2rem;max-width:760px}
h1.t{color:#1d4ed8;font-size:1.9rem;margin:0 0 .3rem}
p.sub{color:#64748b;margin:0 0 1.2rem}
h3.sec{border-left:5px solid #3b82f6;padding-left:.7rem;color:#64748b;margin:1rem 0 .5rem}
table.cal{width:100%;border-collapse:separate;border-spacing:3px;table-layout:fixed;
  background:#f8fafc;border:1px solid #dbe4f0;border-radius:10px;padding:4px}
table.cal th{background:#eef2f8;border:1px solid #dbe4f0;border-radius:4px;padding:6px 0;font-size:.8rem}
table.cal td{vertical-align:top;background:#fff;border:1px solid #dbe4f0;border-radius:4px;
  height:92px;padding:3px;overflow:hidden}
table.cal td.empty{background:#f1f5f9}
.sun{color:#ef4444}.sat{color:#2563eb}
.dn{font-size:.72rem;font-weight:700}
.pill{display:block;font-size:.56rem;line-height:1.15;margin-top:2px;padding:1px 2px;
  border-left:3px solid #3b82f6;background:#f1f5f9;white-space:nowrap;overflow:hidden}
.pill b{border-radius:3px;padding:0 2px;margin-left:1px}
</style>
<h1 class="t">남양주시 시설 예약 현황 캘린더</h1>
<p class="sub">남양주시 통합예약 시스템 실시간 마이페이지 연동 뷰어</p>
<h3 class="sec">통합 예약 내역 달력</h3>
""",
    unsafe_allow_html=True,
)
st.caption("💡 신청현황 및 이력현황 마지막 페이지까지 직접 순회하여 환불을 제외하고 캘린더에 반영합니다.")

if "rows" not in st.session_state:
    st.session_state.rows = load_data()
if "acct" not in st.session_state:
    st.session_state.acct = (
        json.loads(ACCOUNT_FILE.read_text()) if ACCOUNT_FILE.exists() else {"id": "", "pw": ""}
    )

with st.expander("🔑 마이페이지 조회용 계정 설정 (개인 브라우저 자동 기억)", expanded=True):
    uid = st.text_input("조회용 아이디", value=st.session_state.acct["id"])
    upw = st.text_input("조회용 비밀번호", value=st.session_state.acct["pw"], type="password")
    if st.button("계정 기억/저장", use_container_width=True):
        st.session_state.acct = {"id": uid, "pw": upw}
        ACCOUNT_FILE.write_text(json.dumps(st.session_state.acct))
        st.success("저장했습니다.")

if st.button("🔄 마이페이지 실시간 동기화", use_container_width=True):
    try:
        with st.spinner("마이페이지를 순회하는 중..."):
            new_rows = fetch_mypage(st.session_state.acct["id"], st.session_state.acct["pw"])
        merged, changed = merge(st.session_state.rows, new_rows)
        st.session_state.rows = merged
        save_data(merged)
        st.success(f"동기화 완료 (상태 변경 {changed}건)")
    except NotImplementedError as e:
        st.warning(str(e))
    except Exception as e:  # noqa: BLE001
        st.error(f"동기화 실패: {e}")

today = date.today()
c1, c2 = st.columns(2)
year = c1.selectbox("연도 선택", list(range(today.year - 2, today.year + 2)), index=2)
month = c2.selectbox("월 선택", list(range(1, 13)), index=today.month - 1)

with st.sidebar:
    st.header("옵션")
    show_refund = st.checkbox("환불완료 건도 표시", value=False)
    if st.button("샘플 데이터 채우기"):
        merged, _ = merge(st.session_state.rows, make_sample(year, month))
        st.session_state.rows = merged
        save_data(merged)
        st.rerun()
    up = st.file_uploader("예약 JSON 가져오기", type="json")
    if up:
        merged, _ = merge(st.session_state.rows, json.load(up))
        st.session_state.rows = merged
        save_data(merged)
    if st.button("데이터 초기화"):
        st.session_state.rows = []
        save_data([])
        st.rerun()

prefix = f"{year}-{month:02d}-"
month_rows = [r for r in st.session_state.rows if r["date"].startswith(prefix)]
visible = [r for r in month_rows if show_refund or r["status"] not in HIDDEN_BY_DEFAULT]

tab_cal, tab_list = st.tabs(["📆 달력으로 보기", "📋 리스트형(예약건만)"])

with tab_cal:
    by_day = {}
    for r in visible:
        by_day.setdefault(int(r["date"][-2:]), []).append(r)

    html = '<table class="cal"><tr>'
    for i, n in enumerate(["일", "월", "화", "수", "목", "금", "토"]):
        cls = "sun" if i == 0 else "sat" if i == 6 else ""
        html += f'<th class="{cls}">{n}</th>'
    html += "</tr>"
    for week in calendar.Calendar(firstweekday=6).monthdayscalendar(year, month):
        html += "<tr>"
        for i, d in enumerate(week):
            if d == 0:
                html += '<td class="empty"></td>'
                continue
            items = sorted(by_day.get(d, []), key=lambda r: r["hour"])
            cls = "sun" if i == 0 else "sat" if i == 6 else ""
            cnt = f" ({len(items)}건)" if items else ""
            html += f'<td><div class="dn {cls}">{d}{cnt}</div>'
            for r in items:
                bg, fg = STATUS_STYLE[r["status"]]
                html += (
                    f'<span class="pill">{r["facility"]}<b style="background:{bg};color:{fg}">'
                    f'{r["status"]}</b><br>{r["court"]} {r["hour"]}시</span>'
                )
            html += "</td>"
        html += "</tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

    legend = " ".join(
        f'<span style="background:{bg};color:{fg};border-radius:4px;padding:1px 6px;font-size:.75rem">{k}</span>'
        for k, (bg, fg) in STATUS_STYLE.items()
    )
    st.markdown(f"<div style='margin-top:.6rem'>{legend}</div>", unsafe_allow_html=True)

with tab_list:
    if not visible:
        st.info("표시할 예약 내역이 없습니다.")
    else:
        wd = "월화수목금토일"
        table = [
            {
                "날짜": f'{r["date"][5:].replace("-", "/")} ({wd[date.fromisoformat(r["date"]).weekday()]})',
                "시설": f'{r["facility"]} {r["court"]}',
                "시간": f'{r["hour"]}시',
                "상태": r["status"],
            }
            for r in sorted(visible, key=lambda r: (r["date"], r["hour"]))
        ]
        st.dataframe(table, use_container_width=True, hide_index=True)
