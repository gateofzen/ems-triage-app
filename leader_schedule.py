"""
leader_schedule.py — 勤務表アプリ連携版

このモジュールは、勤務表アプリ (duty-roster-app) が GitHub に保存した
月次データ (month_YYYY-MM.json) を読み取って、リーダー医師名を返します。

旧版との互換性を保つため、以下の公開シンボルを提供:
- get_leader(date, shift) -> str
- schedule_editor_widget(key) -> None  (Streamlit UIウィジェット)
- STAFF_LIST -> list (救命センター医師名リスト)
- parse_kinmuhyo_pdf(pdf_bytes) -> dict  (廃止予定、空dictを返す)
- save_schedule(sched) -> None  (廃止予定、no-op)
- load_schedule() -> dict  (互換目的で勤務表アプリのデータをこの形式に変換)

旧仕様: get_leader(date_obj, shift_str) は date オブジェクトと文字列を受け取る
新仕様: 同シグネチャを維持し、内部で年月日に分解して GitHub API から取得
"""
import base64
import json
from datetime import date as _date
from typing import Optional

import requests
import streamlit as st

# ===== 救命センター医師名リスト (リーダー候補) =====
STAFF_LIST = [
    "提嶋", "遠藤", "前川", "小舘", "森木",
    "中嶋", "福原", "富田", "上島", "原",
    "笹", "完山",
]


# ===== 勤務表アプリのデータ取得 =====
@st.cache_data(ttl=3600)
def _fetch_month_data(year: int, month: int) -> Optional[dict]:
    """勤務表アプリの GitHub から month_YYYY-MM.json を取得。"""
    repo = st.secrets.get("SCHEDULE_REPO", "")
    token = st.secrets.get("SCHEDULE_TOKEN", "")
    if not repo or not token:
        return None
    
    url = f"https://api.github.com/repos/{repo}/contents/month_{year:04d}-{month:02d}.json"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        d = r.json()
        # 1MB以下なら content フィールドに直接 base64 が入っている
        content_b64 = (d.get("content") or "").replace("\n", "").strip()
        if content_b64:
            content = base64.b64decode(content_b64).decode("utf-8")
            return json.loads(content)
        # 1MB超の場合は Git Blobs API へフォールバック
        sha = d.get("sha")
        if sha:
            blob_url = f"https://api.github.com/repos/{repo}/git/blobs/{sha}"
            r2 = requests.get(blob_url, headers=headers, timeout=30)
            r2.raise_for_status()
            blob = r2.json()
            content = base64.b64decode(blob["content"].replace("\n", "")).decode("utf-8")
            return json.loads(content)
        return None
    except Exception:
        return None


# ===== 公開API: get_leader =====
def get_leader(date_obj, shift: str) -> str:
    """指定日のリーダー医師名を返す。
    
    Args:
        date_obj: datetime.date オブジェクト
        shift: "日勤" または "夜勤"
    Returns:
        リーダー名 (見つからなければ空文字)
    """
    if not date_obj:
        return ""
    try:
        year = date_obj.year
        month = date_obj.month
        day = date_obj.day
    except AttributeError:
        return ""
    
    data = _fetch_month_data(year, month)
    if not data:
        return ""
    
    date_key = f"{year:04d}-{month:02d}-{day:02d}"
    day_data = data.get("days", {}).get(date_key, {})
    
    # shift 引数を勤務表アプリの形式に変換
    if shift in ("日勤", "day"):
        return day_data.get("day_leader", "")
    elif shift in ("夜勤", "night"):
        return day_data.get("night_leader", "")
    return ""


# ===== 公開API: load_schedule =====
def load_schedule() -> dict:
    """互換目的: 旧形式の {(year, month, day, shift): leader_name} を返す。
    勤務表アプリのデータから現在月+翌月のリーダー情報を変換。
    
    旧コードがこの関数を直接使ってリーダー名を取得していた場合の互換性のため。
    """
    from datetime import date as _d, timedelta as _td
    today = _d.today()
    result = {}
    # 当月と翌月を取得 (月またぎでも安心)
    for offset_days in [0, 31]:
        target = today + _td(days=offset_days)
        data = _fetch_month_data(target.year, target.month)
        if not data:
            continue
        days_dict = data.get("days", {})
        for date_str, day_info in days_dict.items():
            try:
                y, m, d = map(int, date_str.split("-"))
            except Exception:
                continue
            day_leader = day_info.get("day_leader", "")
            night_leader = day_info.get("night_leader", "")
            if day_leader:
                result[(y, m, d, "日勤")] = day_leader
            if night_leader:
                result[(y, m, d, "夜勤")] = night_leader
    return result


# ===== 公開API: save_schedule (no-op、書き込みは勤務表アプリのみ可能) =====
def save_schedule(sched: dict) -> None:
    """互換目的のスタブ。
    新仕様では、リーダースケジュールは勤務表アプリ (duty-roster-app) で
    管理されるため、トリアージ台帳から書き込みはできません。
    """
    pass  # 何もしない


# ===== 公開API: parse_kinmuhyo_pdf (no-op、PDF解析は廃止) =====
def parse_kinmuhyo_pdf(pdf_bytes: bytes) -> dict:
    """互換目的のスタブ。
    新仕様では、勤務表は Excel ファイルで勤務表アプリ側にアップロードします。
    トリアージ台帳での PDF 解析機能は廃止されました。
    """
    return {}


# ===== 公開API: schedule_editor_widget =====
def schedule_editor_widget(key: str = "sched_editor") -> None:
    """Streamlit UI ウィジェット: 月次のリーダースケジュール表示用。
    
    新仕様では編集はできません (勤務表アプリで管理)。
    現在月と翌月のリーダー一覧を表示するだけの read-only ウィジェットです。
    """
    from datetime import date as _d
    
    # 設定状態を確認
    repo = st.secrets.get("SCHEDULE_REPO", "")
    token = st.secrets.get("SCHEDULE_TOKEN", "")
    
    if not repo or not token:
        st.warning(
            "⚠️ 勤務表アプリ連携の設定が未完了です。\n\n"
            "Streamlit Cloud → Settings → Secrets に以下を追加してください:\n"
            "```toml\n"
            'SCHEDULE_REPO = "gateofzen/schedule-storage"\n'
            'SCHEDULE_TOKEN = "github_pat_xxx..."\n'
            "```"
        )
        return
    
    today = _d.today()
    
    # 表示する年月を選択 (デフォルトは当月)
    col_y, col_m = st.columns(2)
    with col_y:
        view_year = st.number_input(
            "表示年", min_value=2024, max_value=2030,
            value=today.year, step=1, key=f"{key}_year",
        )
    with col_m:
        view_month = st.number_input(
            "表示月", min_value=1, max_value=12,
            value=today.month, step=1, key=f"{key}_month",
        )
    
    view_year = int(view_year)
    view_month = int(view_month)
    
    # データ取得
    data = _fetch_month_data(view_year, view_month)
    if not data:
        st.info(
            f"ℹ️ {view_year}年{view_month}月のデータがまだ勤務表アプリに登録されていません。\n\n"
            "管理者が勤務表アプリでExcelをアップロードすると、ここにリーダー一覧が表示されます。"
        )
        return
    
    days = data.get("days", {})
    if not days:
        st.warning("データが空です。")
        return
    
    # 一覧表示
    import calendar as _cal
    weekdays_jp = "月火水木金土日"
    days_in_month = _cal.monthrange(view_year, view_month)[1]
    
    rows = []
    for d in range(1, days_in_month + 1):
        date_str = f"{view_year:04d}-{view_month:02d}-{d:02d}"
        date_obj = _d(view_year, view_month, d)
        wd = weekdays_jp[date_obj.weekday()]
        day_info = days.get(date_str, {})
        rows.append({
            "日": d,
            "曜": wd,
            "日勤リーダー": day_info.get("day_leader", "—"),
            "夜勤リーダー": day_info.get("night_leader", "—"),
        })
    
    try:
        import pandas as pd
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True, height=400)
    except ImportError:
        # pandas 無しなら text 表示
        for row in rows:
            st.text(
                f"{row['日']:>2}日({row['曜']}) "
                f"日勤={row['日勤リーダー']:<6} 夜勤={row['夜勤リーダー']}"
            )
    
    # 末尾に管理リンク
    st.caption(
        "💡 リーダー情報の変更は **勤務表アプリ (duty-roster-app)** で行います。"
        "このアプリでは閲覧のみ可能です。"
    )
