import json, os, io, re
from datetime import date

STAFF_LIST    = ["前川","中嶋","森木","小舘","遠藤","提嶋"]
SCHEDULE_FILE = "leader_schedule.json"

_DEFAULT_SCHEDULE = {
    (4, 1):{"日勤":"小舘","夜勤":"遠藤"}, (4, 2):{"日勤":"小舘","夜勤":"小舘"},
    (4, 3):{"日勤":"森木","夜勤":"遠藤"}, (4, 4):{"日勤":"小舘","夜勤":"中嶋"},
    (4, 5):{"日勤":"遠藤","夜勤":"小舘"}, (4, 6):{"日勤":"遠藤","夜勤":"前川"},
    (4, 7):{"日勤":"森木","夜勤":"遠藤"}, (4, 8):{"日勤":"小舘","夜勤":"前川"},
    (4, 9):{"日勤":"小舘","夜勤":"遠藤"}, (4,10):{"日勤":"前川","夜勤":"小舘"},
    (4,11):{"日勤":"前川","夜勤":"中嶋"}, (4,12):{"日勤":"前川","夜勤":"提嶋"},
    (4,13):{"日勤":"小舘","夜勤":"遠藤"}, (4,14):{"日勤":"中嶋","夜勤":"森木"},
    (4,15):{"日勤":"前川","夜勤":"遠藤"}, (4,16):{"日勤":"小舘","夜勤":"前川"},
    (4,17):{"日勤":"遠藤","夜勤":"小舘"}, (4,18):{"日勤":"森木","夜勤":"遠藤"},
    (4,19):{"日勤":"提嶋","夜勤":"前川"}, (4,20):{"日勤":"遠藤","夜勤":"中嶋"},
    (4,21):{"日勤":"小舘","夜勤":"森木"}, (4,22):{"日勤":"小舘","夜勤":"前川"},
    (4,23):{"日勤":"遠藤","夜勤":"小舘"}, (4,24):{"日勤":"前川","夜勤":"中嶋"},
    (4,25):{"日勤":"遠藤","夜勤":"小舘"}, (4,26):{"日勤":"前川","夜勤":"提嶋"},
    (4,27):{"日勤":"森木","夜勤":"中嶋"}, (4,28):{"日勤":"遠藤","夜勤":"小舘"},
    (4,29):{"日勤":"前川","夜勤":"遠藤"}, (4,30):{"日勤":"小舘","夜勤":"前川"},
}

def load_schedule():
    if os.path.exists(SCHEDULE_FILE):
        try:
            raw = json.load(open(SCHEDULE_FILE, encoding="utf-8"))
            return {(int(k.split(",")[0]), int(k.split(",")[1])): v for k, v in raw.items()}
        except Exception:
            pass
    return _DEFAULT_SCHEDULE.copy()

def save_schedule(sched):
    raw = {f"{k[0]},{k[1]}": v for k, v in sched.items()}
    json.dump(raw, open(SCHEDULE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def get_leader(date_obj, shift):
    sched = load_schedule()
    return sched.get((date_obj.month, date_obj.day), {}).get(shift, "")

def parse_kinmuhyo_pdf(pdf_bytes):
    """勤務表PDFを解析 → {(month, day): {"日勤": name, "夜勤": name}}"""
    try:
        import pdfplumber
    except ImportError:
        return {}
    result = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            all_text = page.extract_text() or ""
            ym = re.search(r'(\d{4})年\s*(\d{1,2})\s*月', all_text)
            if not ym:
                continue
            main_year  = int(ym.group(1))
            main_month = int(ym.group(2))
            prev_month = main_month - 1 if main_month > 1 else 12
            prev_year  = main_year if main_month > 1 else main_year - 1
            boundary_x = 190
            for w in words:
                if w['text'] == str(main_month) + '月':
                    boundary_x = w['x0']
                    break
            date_x_map = {}
            y_groups = {}
            for w in words:
                yk = round(w['top'] / 8) * 8
                y_groups.setdefault(yk, []).append(w)
            for y in sorted(y_groups):
                ws = y_groups[y]
                nums = [(w, int(w['text'])) for w in ws if re.match(r'^\d{1,2}$', w['text'])]
                if len(nums) < 20:
                    continue
                for w, day in nums:
                    xc = (w['x0'] + w['x1']) / 2
                    mo = main_month if xc >= boundary_x else prev_month
                    date_x_map[xc] = (mo, day)
                break
            if not date_x_map:
                continue
            date_xs = sorted(date_x_map.keys())
            def x_to_date(x, slack=20):
                closest = min(date_xs, key=lambda dx: abs(dx - x))
                return date_x_map[closest] if abs(closest - x) <= slack else None
            name_ys = {}
            for w in sorted(words, key=lambda x: x['top']):
                for name in STAFF_LIST:
                    if name in w['text'] and name not in name_ys:
                        name_ys[name] = w['top']
            for name, ny in name_ys.items():
                for w in words:
                    if abs(w['top'] - ny) > 12:
                        continue
                    t = w['text']
                    if '*' not in t:
                        continue
                    is_day   = '〇' in t or '○' in t
                    is_night = '●' in t
                    is_toosh = '㉕' in t or '㊵' in t
                    if not (is_day or is_night or is_toosh):
                        continue
                    xc = (w['x0'] + w['x1']) / 2
                    di = x_to_date(xc) or x_to_date(xc + 10) or x_to_date(xc - 10)
                    if not di:
                        continue
                    mo, day = di
                    key = (mo, day)
                    result.setdefault(key, {"日勤": "", "夜勤": ""})
                    if (is_day or is_toosh) and not result[key]["日勤"]:
                        result[key]["日勤"] = name
                    if (is_night or is_toosh) and not result[key]["夜勤"]:
                        result[key]["夜勤"] = name
    return result

def schedule_editor_widget(key_prefix="sched"):
    import streamlit as st
    import calendar
    sched = load_schedule()
    today = date.today()

    # PDFアップロード
    pdf_file = st.file_uploader(
        "📋 勤務表PDF（毎月20日頃にアップロード）",
        type=["pdf"],
        key=f"{key_prefix}_pdf_upload"
    )
    if pdf_file is not None:
        with st.spinner("勤務表を解析中..."):
            parsed = parse_kinmuhyo_pdf(pdf_file.read())
        if parsed:
            months_in_parsed = set(k[0] for k in parsed.keys())
            sched = {k: v for k, v in sched.items() if k[0] not in months_in_parsed}
            sched.update(parsed)
            save_schedule(sched)
            st.success(f"✅ {len(parsed)}日分のリーダー情報を更新しました（{sorted(months_in_parsed)}月）")
            st.rerun()
        else:
            st.error("⚠️ 解析できませんでした。フォーマットを確認してください")

    st.divider()

    # 月選択
    existing_months = sorted(set(k[0] for k in sched.keys()))
    all_months = sorted(set([today.month, today.month % 12 + 1] + existing_months))
    month_sel = st.selectbox("確認・修正する月", all_months,
                             index=all_months.index(today.month) if today.month in all_months else 0,
                             format_func=lambda m: f"{m}月",
                             key=f"{key_prefix}_month")

    _, days_in_month = calendar.monthrange(today.year, month_sel)
    st.caption("🌕日勤リーダー（〇*）　🌑夜勤リーダー（●*）　空欄=未設定")

    changed = False
    for week_start in range(1, days_in_month + 1, 7):
        week_days = list(range(week_start, min(week_start + 7, days_in_month + 1)))
        cols = st.columns(len(week_days))
        for ci, day in enumerate(week_days):
            key = (month_sel, day)
            entry = sched.get(key, {"日勤": "", "夜勤": ""})
            with cols[ci]:
                wd_names = ["月","火","水","木","金","土","日"]
                try:
                    wd = wd_names[date(today.year, month_sel, day).weekday()]
                except: wd = ""
                is_today = (today.month == month_sel and today.day == day)
                st.markdown(f"**{day}({wd})**" if is_today else f"{day}({wd})")
                opts = [""] + STAFF_LIST
                cur_n = entry.get("日勤","")
                cur_y = entry.get("夜勤","")
                new_n = st.selectbox("🌕", opts,
                                     index=opts.index(cur_n) if cur_n in opts else 0,
                                     key=f"{key_prefix}_{month_sel}_{day}_n",
                                     label_visibility="collapsed")
                new_y = st.selectbox("🌑", opts,
                                     index=opts.index(cur_y) if cur_y in opts else 0,
                                     key=f"{key_prefix}_{month_sel}_{day}_y",
                                     label_visibility="collapsed")
                if new_n != cur_n or new_y != cur_y:
                    sched[key] = {"日勤": new_n, "夜勤": new_y}
                    changed = True
    if changed:
        save_schedule(sched)
        st.toast("✅ 保存しました")
