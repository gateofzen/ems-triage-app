"""
leader_schedule.py（トークン不要・パブリックリポジトリ版）
gateofzen/schedule-storage が Public の場合に使用
"""
import json, base64
from datetime import date

STAFF_LIST = ["前川","中嶋","森木","小舘","遠藤","提嶋"]
_REPO = "gateofzen/schedule-storage"
_cache = {}

def _fetch_month_data(year: int, month: int) -> dict:
    key = (year, month)
    if key in _cache:
        return _cache[key]
    try:
        import urllib.request
        url = f"https://raw.githubusercontent.com/{_REPO}/main/month_{year:04d}-{month:02d}.json"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
        _cache[key] = data
        return data
    except Exception:
        return {}

def get_leader(date_obj: date, shift: str) -> str:
    data = _fetch_month_data(date_obj.year, date_obj.month)
    if not data:
        return ""
    date_key = date_obj.strftime("%Y-%m-%d")
    day_data = data.get("days", {}).get(date_key, {})
    shift_key = "day_leader" if shift == "日勤" else "night_leader"
    return day_data.get(shift_key, "")

def schedule_editor_widget(key_prefix="sched"):
    import streamlit as st
    import calendar
    today = date.today()
    data = _fetch_month_data(today.year, today.month)

    if not data:
        st.warning("⚠️ schedule-storageへの接続に失敗しました")
        return

    st.caption("📡 患者受け持ち表アプリ（schedule-storage）から自動取得")
    all_months = sorted(set([today.month, today.month % 12 + 1]))
    month_sel = st.selectbox("確認する月", all_months,
                             format_func=lambda m: f"{m}月",
                             key=f"{key_prefix}_month")

    data_sel = _fetch_month_data(today.year, month_sel)
    days_info = data_sel.get("days", {}) if data_sel else {}
    _, days_in_month = calendar.monthrange(today.year, month_sel)
    st.caption("🌕=日勤リーダー　🌑=夜勤リーダー")

    for week_start in range(1, days_in_month + 1, 7):
        week_days = list(range(week_start, min(week_start + 7, days_in_month + 1)))
        cols = st.columns(len(week_days))
        for ci, day in enumerate(week_days):
            dk = f"{today.year:04d}-{month_sel:02d}-{day:02d}"
            entry = days_info.get(dk, {})
            dl = entry.get("day_leader", "")
            nl = entry.get("night_leader", "")
            wd = ["月","火","水","木","金","土","日"][date(today.year, month_sel, day).weekday()]
            is_today = (today.month == month_sel and today.day == day)
            with cols[ci]:
                st.markdown(f"**{day}({wd})**" if is_today else f"{day}({wd})")
                st.markdown(f"🌕{dl or '—'}")
                st.markdown(f"🌑{nl or '—'}")
