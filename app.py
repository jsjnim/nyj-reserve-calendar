"""남양주시 시설 예약 현황 캘린더 (Streamlit)

실행:  pip install streamlit requests beautifulsoup4
       streamlit run app.py
"""
import calendar
import json
import random
import re
from datetime import date
from pathlib import Path

import streamlit as st

DATA_FILE = Path("reservations.json")

STATUS_STYLE = {
    "신청대기": ("#6b7280", "#fff"),
    "결제대기": ("#f59e0b", "#fff"),
    "예약완료": ("#2563eb", "#fff"),
    "환불대기": ("#ef4444", "#fff"),
    "환불완료": ("#9ca3af", "#fff"),
}
DEFAULT_STYLE = ("#6b7280", "#fff")
HIDDEN_BY_DEFAULT = {"환불완료", "예약취소", "자동취소", "승인불가"}  # 캘린더에서 제외


# ---------------------------------------------------------------- 데이터
def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


def save_data(rows):
    DATA_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def key_of(r):
    # 접수번호가 있으면 접수번호로 구분 (같은 시간대 재신청/취소 건이 섞이지 않게)
    return r.get("id") or (r["date"], r["facility"], r["court"], r["hour"])


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


BASE = "https://www.nyj.go.kr/rent"
LOGIN_URL = f"{BASE}/member/login"  # 로그인 화면 (폼 전송 주소: /member/process)
# 신청현황 목록: /mypage/rlist/index/{접수상태(0=전체)}/{페이지당 개수}/{페이지}
# 이력현황 목록(결제완료/환불 건): /mypage/rhistlist/index/0/{페이지당 개수}/{페이지}
LIST_URLS = [
    BASE + "/mypage/rlist/index/0/{rows}/{page}",
    BASE + "/mypage/rhistlist/index/0/{rows}/{page}",
]
# 사이트 표기 → 이 앱의 표기 (표에 없는 상태는 그대로 표시)
STATUS_MAP = {"결제완료": "예약완료", "환불": "환불완료"}
# 센터명 → 시설 표기 (이력현황은 시설명 없이 센터명·코트명만 나옴)
CENTER_MAP = {"와부조안행정복지센터": "와부"}


def parse_rlist(html):
    """신청현황/이력현황 목록 HTML → (예약 목록, 전체 페이지 수)"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("table.rlist_table tbody tr"):
        no = tr.select_one("td.rlist_no")
        if not no:
            continue
        st = tr.select_one("td.rlist_status")
        img = st.find("img")
        status = (img.get("alt") if img and img.get("alt") else st.get_text(strip=True)).strip()
        status = STATUS_MAP.get(status, status)
        center = tr.select_one("td.rlist_facility").get_text(strip=True)
        parts = list(tr.select_one("td.rlist_place").stripped_strings)
        # 신청현황: ["와부 실내배드민턴장", "(배드민턴코트C)"] / 이력현황: ["배드민턴코트A"]
        name = parts[0] if len(parts) > 1 else ""
        raw = parts[1] if len(parts) > 1 else parts[0]
        detail = raw.strip("() ")
        if "일반" in raw:  # 월문은 "배드민턴코트 B (일반)" 한 코트뿐
            facility, court = "월문", "B코트(시민)"
        else:
            m = re.search(r"코트\s*([A-Za-z0-9])", detail)
            court = f"{m.group(1).upper()}코트" if m else detail
            if name:
                facility = re.sub(r"(리|읍|면)$", "", name.split()[0])
            else:
                facility = CENTER_MAP.get(center, center[:2])
        d = re.search(r"\d{4}-\d{2}-\d{2}", tr.select_one("td.rlist_usedate").get_text())
        t = re.search(r"(\d{1,2}):(\d{2})\s*~\s*(\d{1,2}):(\d{2})", tr.select_one("td.rlist_usetime").get_text())
        if not (d and t):
            continue
        rows.append({
            "id": no.get_text(strip=True), "date": d.group(0), "facility": facility,
            "court": court, "hour": int(t.group(1)), "end": int(t.group(3)), "status": status,
            "time": f"{int(t.group(1)):02d}:{t.group(2)}~{int(t.group(3)):02d}:{t.group(4)}",
        })
    tot = soup.select_one(".total_area")
    m = re.search(r"페이지\s*:\s*(\d+)\s*/\s*(\d+)", tot.get_text(" ")) if tot else None
    return rows, (int(m.group(2)) if m else 1)


def login(session, user_id, password):
    """로그인 화면의 폼(memid/mempw + CSRFToken 등 hidden 값)을 그대로 채워 /member/process 로 전송한다."""
    from urllib.parse import urlencode

    from bs4 import BeautifulSoup

    r = session.get(LOGIN_URL, timeout=15)
    r.encoding = "euc-kr"
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.select_one("form#login_form")
    if not form:
        raise RuntimeError("로그인 페이지에서 로그인 폼을 찾지 못했습니다. LOGIN_URL을 확인하세요.")
    data = {i.get("name"): i.get("value", "") for i in form.select("input[type=hidden]") if i.get("name")}
    data["memid"] = user_id
    data["mempw"] = password
    action = form.get("action") or f"{BASE}/member/process"
    body = urlencode(data, encoding="euc-kr")  # 사이트가 euc-kr 폼을 사용
    session.post(
        action,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Referer": LOGIN_URL},
        timeout=15,
    )


def fetch_mypage(user_id, password):
    """마이페이지의 신청현황(및 이력현황)을 마지막 페이지까지 순회해서 가져온다."""
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    login(s, user_id, password)

    out = []
    for tpl in LIST_URLS:
        page, total = 1, 1
        while page <= total:
            r = s.get(tpl.format(rows=100, page=page), timeout=15)
            r.encoding = "euc-kr"
            if "rlist_table" not in r.text:
                raise RuntimeError("로그인에 실패했거나 목록 화면 구조가 다릅니다. (아이디/비밀번호, 캡차 여부 확인)")
            rows, total = parse_rlist(r.text)
            out += rows
            page += 1
    return out


def make_sample(year, month):
    random.seed(year * 100 + month)
    rows, last = [], calendar.monthrange(year, month)[1]
    for d in range(1, last + 1):
        for _ in range(random.randint(0, 4)):
            facility = random.choice(["와부", "와부", "와부", "월문"])
            court = random.choice(["A코트", "B코트", "C코트"]) if facility == "와부" else "B코트(시민)"
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
.block-container{padding-top:2rem;max-width:920px!important}
h1.t{color:#1d4ed8;font-size:1.9rem;margin:0 0 .3rem}
p.sub{color:#64748b;margin:0 0 1.2rem}
h3.sec{border-left:5px solid #3b82f6;padding-left:.7rem;color:#64748b;margin:1rem 0 .5rem}
table.cal{color:#1e293b;width:100%;border-collapse:separate;border-spacing:2px;table-layout:fixed;
  background:#f8fafc;border:1px solid #dbe4f0;border-radius:10px;padding:2px}
table.cal th{background:#eef2f8;border:1px solid #dbe4f0;border-radius:4px;padding:5px 0;font-size:.78rem}
table.cal td{vertical-align:top;background:#fff;border:1px solid #dbe4f0;border-radius:4px;
  height:58px;padding:2px;overflow:hidden}
table.cal td.empty{background:#f1f5f9}
.sun{color:#ef4444}.sat{color:#2563eb}
.dn{font-size:.72rem;font-weight:700;white-space:nowrap}
.cn{font-size:.55rem;font-weight:500;color:#64748b;margin-left:2px}
.chip{display:block;font-size:.58rem;line-height:1.25;margin-top:2px;padding:1px 2px;
  border-radius:3px;white-space:nowrap;overflow:hidden;font-weight:700}
.chip .w{display:none}
.chip .st{display:block;font-weight:500;font-size:.85em}
.calwrap{overflow:hidden}
table.cal.full .chip{font-size:.66rem;padding:2px 4px;margin-top:3px}
table.cal.full .chip .n{display:none}
table.cal.full .chip .w{display:block}
table.cal.full td{height:70px;padding:3px}
@media (max-width:640px){table.cal.full{width:560px}table.cal.full .chip{font-size:.58rem;padding:1px 3px}table.cal.full td{height:64px}}
@media (max-width:600px){table.cal.full{zoom:1.000}}
@media (max-width:580px){table.cal.full{zoom:0.971}}
@media (max-width:560px){table.cal.full{zoom:0.936}}
@media (max-width:540px){table.cal.full{zoom:0.900}}
@media (max-width:520px){table.cal.full{zoom:0.864}}
@media (max-width:500px){table.cal.full{zoom:0.829}}
@media (max-width:480px){table.cal.full{zoom:0.793}}
@media (max-width:460px){table.cal.full{zoom:0.757}}
@media (max-width:440px){table.cal.full{zoom:0.721}}
@media (max-width:420px){table.cal.full{zoom:0.686}}
@media (max-width:400px){table.cal.full{zoom:0.650}}
@media (max-width:380px){table.cal.full{zoom:0.614}}
@media (max-width:360px){table.cal.full{zoom:0.579}}
@media (max-width:340px){table.cal.full{zoom:0.543}}
.lg{display:inline-block;font-size:.72rem;padding:1px 6px;border-radius:4px;margin:2px 4px 2px 0}
.card{border-radius:8px;padding:.5rem .7rem;margin:.35rem 0}
.ch{display:flex;justify-content:space-between;align-items:center;font-size:1rem}
.bd{color:#fff;border-radius:6px;padding:2px 8px;font-size:.78rem;font-weight:700}
.cb{font-weight:600;margin-top:.15rem}
@media (max-width:640px){
  .block-container{padding-left:.4rem;padding-right:.4rem;padding-top:1.2rem}
  h1.t{font-size:1.5rem}
}
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
    # 보안: 계정은 이 접속(세션) 메모리에만 두고 서버 파일에는 저장하지 않는다.
    st.session_state.acct = {"id": "", "pw": ""}

with st.expander("🔑 마이페이지 조회용 계정 설정 (개인 브라우저 자동 기억)", expanded=True):
    uid = st.text_input("조회용 아이디", value=st.session_state.acct["id"])
    upw = st.text_input("조회용 비밀번호", value=st.session_state.acct["pw"], type="password")
    if st.button("계정 기억/저장", use_container_width=True):
        st.session_state.acct = {"id": uid, "pw": upw}
        st.success("이번 접속 동안 기억합니다. (새로고침하면 다시 입력)")

if st.button("🔄 마이페이지 실시간 동기화", use_container_width=True):
    st.session_state.acct = {"id": uid, "pw": upw}
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
    show_refund = st.checkbox("환불완료·취소 건도 표시", value=False)
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

FAC = {  # 시설별 색: 와부=연한 파랑, 월문=주황
    "와부": {"bg": "#dbeafe", "bar": "#60a5fa", "fg": "#1e3a8a", "card": "#eff6ff"},
    "월문": {"bg": "#ffedd5", "bar": "#f97316", "fg": "#9a3412", "card": "#fff7ed"},
}
FAC_DEFAULT = {"bg": "#e5e7eb", "bar": "#9ca3af", "fg": "#374151", "card": "#f3f4f6"}
GRAY = {"bg": "#e5e7eb", "fg": "#374151", "bar": "#9ca3af", "card": "#f3f4f6", "badge": "#6b7280", "badge_fg": "#fff"}
REFUND = {"환불대기", "환불완료"}
CANCELED = {"예약취소", "자동취소", "승인불가"}
WD = "월화수목금토일"


def look(r):
    """상태별 색: 예약완료=시설색 / 결제대기=빨강 / 신청대기=회색 / 환불=시설색 반전"""
    col = FAC.get(r["facility"], FAC_DEFAULT)
    s = r["status"]
    if s == "신청대기":
        return {**GRAY, "line": False, "dash": True}
    if s in REFUND:  # 배경과 글자색을 맞바꿔 반전
        return {"bg": col["fg"], "fg": col["bg"], "bar": col["fg"], "card": col["fg"],
                "badge": col["bg"], "badge_fg": col["fg"], "line": s == "환불완료", "dash": False}
    if s in CANCELED:
        return {**GRAY, "line": True, "dash": False}
    if s == "결제대기":  # 시설과 상관없이 빨간색
        return {"bg": "#fee2e2", "fg": "#991b1b", "bar": "#ef4444", "card": "#fef2f2",
                "badge": "#ef4444", "badge_fg": "#fff", "line": False, "dash": False}
    return {"bg": col["bg"], "fg": col["fg"], "bar": col["bar"], "card": col["card"],
            "badge": col["bar"], "badge_fg": "#fff", "line": False, "dash": False}


def time_text(r):
    return r.get("time") or f'{r["hour"]:02d}:00~{r.get("end", r["hour"] + 2):02d}:00'


def court_letter(r):
    m = re.match(r"([A-Za-z0-9])코트", r["court"])
    return m.group(1) if m else r["court"][:1]


def day_chips(items):
    """같은 시설·시간·상태의 예약을 한 칸으로 묶는다.
    좁은 화면: '19 ABC' / 넓은 화면: '와부 ABC코트 · 19:00~21:00' (+ 예약완료가 아니면 상태 표시)"""
    groups = {}
    for r in sorted(items, key=lambda r: (r["hour"], r["facility"], r["court"])):
        groups.setdefault((time_text(r), r["facility"], r["status"]), []).append(r)
    out = ""
    for (tm, facility, status), rs in groups.items():
        lk = look(rs[0])
        letters = "".join(court_letter(r) for r in rs)
        short = f'{rs[0]["hour"]} ' + ("월" if facility == "월문" else letters)
        court_txt = "B(시민)" if facility == "월문" else f"{letters}코트"
        third = f'<span class="st">{status}</span>' if status != "예약완료" else ""
        style = (
            f'background:{lk["bg"]};color:{lk["fg"]};'
            f'border:1px {"dashed" if lk["dash"] else "solid"} {lk["bar"]};border-left:3px solid {lk["bar"]};'
            + ("text-decoration:line-through;" if lk["line"] else "")
        )
        out += (
            f'<span class="chip" style="{style}"><span class="n">{short}</span>'
            f'<span class="w">{facility} {court_txt}<br>{tm}{third}</span></span>'
        )
    return out


def day_cards(items):
    out = ""
    for r in sorted(items, key=lambda r: (r["hour"], r["court"])):
        lk = look(r)
        line = "text-decoration:line-through;" if lk["line"] else ""
        out += (
            f'<div class="card" style="background:{lk["card"]};border-left:4px solid {lk["bar"]}">'
            f'<div class="ch"><b style="color:{lk["fg"]}">{r["facility"]}</b>'
            f'<span class="bd" style="background:{lk["badge"]};color:{lk["badge_fg"]}">{r["status"]}</span></div>'
            f'<div class="cb" style="color:{lk["fg"]};{line}">{r["court"]} {time_text(r)}</div></div>'
        )
    return out


tab_cal, tab_list = st.tabs(["📆 달력으로 보기", "📋 리스트형(예약건만)"])

with tab_cal:
    by_day = {}
    for r in visible:
        by_day.setdefault(int(r["date"][-2:]), []).append(r)

    html = '<div class="calwrap"><table class="cal full"><tr>'
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
            items = by_day.get(d, [])
            cls = "sun" if i == 0 else "sat" if i == 6 else ""
            cnt = f'<span class="cn">{len(items)}건</span>' if items else ""
            html += f'<td><div class="dn {cls}">{d}{cnt}</div>{day_chips(items)}</td>'
        html += "</tr>"
    html += "</table></div>"
    st.markdown(html, unsafe_allow_html=True)

    legend = (
        '<span class="lg" style="background:#dbeafe;border-left:3px solid #60a5fa;color:#1e3a8a">와부</span>'
        '<span class="lg" style="background:#ffedd5;border-left:3px solid #f97316;color:#9a3412">월문</span>'
        '<span class="lg" style="background:#fee2e2;border-left:3px solid #ef4444;color:#991b1b">빨강 결제대기</span>'
        '<span class="lg" style="background:#e5e7eb;color:#374151;border:1px dashed #9ca3af">회색 신청대기</span>'
        '<span class="lg" style="background:#1e3a8a;color:#dbeafe">환불(와부)</span>'
        '<span class="lg" style="background:#9a3412;color:#ffedd5">환불(월문)</span>'
    )
    st.markdown(
        f"<div style='margin-top:.5rem'>{legend}</div>"
        "<div style='font-size:.72rem;color:#64748b'>좁은 화면 표기: 시작시간 + 코트 (예: <b>19 ABC</b> = 19시 A·B·C코트, <b>21 월</b> = 월문 21시)</div>",
        unsafe_allow_html=True,
    )

    days = sorted(by_day)
    if days:
        default = today.day if (year, month) == (today.year, today.month) and today.day in by_day else days[0]
        sel = st.selectbox(
            "📌 날짜별 상세 보기",
            days,
            index=days.index(default),
            format_func=lambda d: f"{month}/{d} ({WD[date(year, month, d).weekday()]}) · {len(by_day[d])}건",
        )
        st.markdown(day_cards(by_day[sel]), unsafe_allow_html=True)

with tab_list:
    if not visible:
        st.info("표시할 예약 내역이 없습니다.")
    else:
        table = [
            {
                "날짜": f'{r["date"][5:].replace("-", "/")} ({WD[date.fromisoformat(r["date"]).weekday()]})',
                "시설": f'{r["facility"]} {r["court"]}',
                "시간": time_text(r),
                "상태": r["status"],
            }
            for r in sorted(visible, key=lambda r: (r["date"], r["hour"]))
        ]
        st.dataframe(table, use_container_width=True, hide_index=True)
