"""
leader_schedule.py
患者受け持ち表アプリ（gateofzen/schedule-storage）と連携して
日勤・夜勤のリーダー名を取得するモジュール。

Streamlit Secrets に以下が必要:
  SCHEDULE_REPO  = "gateofzen/schedule-storage"
  SCHEDULE_TOKEN = "ghp_xxxxxxxxxxxx..."
"""

import json, os, base64
from datetime import date

STAFF_LIST = ["前川","中嶋","森木","小舘","遠藤","提嶋"]

# === GitHub Storage からの読み込み ===
_cache = {}  # {(year,month): dict} メモリキャッシュ

def _fetch_month_data(year: int, month: int) -> dict:
    """GitHub schedule-storage から month_YYYY-MM.json を取得"""
    key = (year, month)
    if key in _cache:
        return _cache[key]
    try:
        import streamlit as st
        import requests as _req
        # GITHUB_REPO / GITHUB_TOKEN（患者受け持ち表アプリと同じキー名）
        repo  = st.secrets.get("GITHUB_REPO",  st.secrets.get("SCHEDULE_REPO", "gateofzen/schedule-storage"))
        token = st.secrets.get("GITHUB_TOKEN", st.secrets.get("SCHEDULE_TOKEN", ""))
        if not token:
            return {}
        url = f"https://api.github.com/repos/{repo}/contents/month_{year:04d}-{month:02d}.json"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        r = _req.get(url, headers=headers, timeout=15)
        if r.status_code == 404:
            return {}
        r.raise_for_status()
        content = base64.b64decode(r.json()["content"].replace("\n", ""))
        data = json.loads(content.decode("utf-8"))
        _cache[key] = data
        return data
    except Exception:
        return {}

def get_leader(date_obj: date, shift: str) -> str:
    """
    date_obj: datetime.date
    shift: "日勤" or "夜勤"
    返り値: リーダー名（不明なら空文字）
    """
    data = _fetch_month_data(date_obj.year, date_obj.month)
    if not data:
        return ""
    date_key = date_obj.strftime("%Y-%m-%d")
    day_data = data.get("days", {}).get(date_key, {})
    # shift_key: "day_leader" or "night_leader"
    shift_key = "day_leader" if shift == "日勤" else "night_leader"
    return day_data.get(shift_key, "")

def schedule_editor_widget(key_prefix="sched"):
    """勤務表エディタ（schedule-storageから読み込んで表示）"""
    import streamlit as st
    import calendar

    today = date.today()
    data  = _fetch_month_data(today.year, today.month)
    days_info = data.get("days", {}) if data else {}

    st.caption("📡 患者受け持ち表アプリ（schedule-storage）から自動取得")

    if not data:
        st.warning("⚠️ schedule-storageへの接続に失敗しました。\n"
                   "Streamlit Secrets に `GITHUB_REPO` と `GITHUB_TOKEN` が設定されているか確認してください。")
        return

    # 月選択
    all_months = sorted(set([today.month, today.month % 12 + 1]))
    month_sel = st.selectbox("確認する月", all_months,
                             format_func=lambda m: f"{m}月",
                             key=f"{key_prefix}_month")

    if month_sel != today.month:
        data_sel = _fetch_month_data(today.year, month_sel)
        days_info_sel = data_sel.get("days", {}) if data_sel else {}
    else:
        days_info_sel = days_info

    _, days_in_month = calendar.monthrange(today.year, month_sel)
    st.caption("🌕=日勤リーダー　🌑=夜勤リーダー")

    for week_start in range(1, days_in_month + 1, 7):
        week_days = list(range(week_start, min(week_start + 7, days_in_month + 1)))
        cols = st.columns(len(week_days))
        for ci, day in enumerate(week_days):
            dk = f"{today.year:04d}-{month_sel:02d}-{day:02d}"
            entry = days_info_sel.get(dk, {})
            dl = entry.get("day_leader", "")
            nl = entry.get("night_leader", "")
            wd = ["月","火","水","木","金","土","日"][date(today.year, month_sel, day).weekday()]
            is_today = (today.month == month_sel and today.day == day)
            with cols[ci]:
                label = f"**{day}({wd})**" if is_today else f"{day}({wd})"
                st.markdown(label)
                st.markdown(f"🌕{dl or '—'}")
                st.markdown(f"🌑{nl or '—'}")
