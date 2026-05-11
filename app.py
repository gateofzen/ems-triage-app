import streamlit as st
import streamlit.components.v1 as components
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pyzbar.pyzbar as pyzbar
import base64
import io
import os
import json
import urllib.parse
from datetime import datetime
from leader_schedule import get_leader, schedule_editor_widget, STAFF_LIST as SCHEDULE_STAFF

st.set_page_config(page_title="トリアージ台帳自動作成", layout="centered")
st.title("🚑 トリアージ台帳自動作成")

# ボタン高さ統一CSS
st.markdown("""<style>
/* ダウンロードボタンをcomponents.htmlボタンと同じ高さに */
div[data-testid="stDownloadButton"] > button {
    height: 38px !important; padding: 0 14px !important;
    width: 100% !important;
}
/* ペーストボタンiframe - 高さ統一 */
iframe[title="streamlit_paste_button.paste_image_button"],
div[data-testid="stCustomComponentV1"] > iframe {
    height: 38px !important; min-height: 38px !important;
    max-height: 38px !important;
}
</style>""", unsafe_allow_html=True)

# モバイルでカラムが縦積みにならないよう強制
st.markdown("""
<style>
.patient-row [data-testid="column"] {
    min-width: 0 !important;
    flex: none !important;
}
</style>
""", unsafe_allow_html=True)

# ===== 日勤・夜勤の自動判定 =====
def _extract_time(dt_str):
    """dt_strから時刻(h, m)を抽出。'4/8（水）17:40' と '2026/04/11 9:33:20' 両対応"""
    import re
    # 末尾から最後のHH:MM(:SS)を探す
    matches = re.findall(r'(\d{1,2}):(\d{2})(?::\d{2})?', dt_str.strip())
    if matches:
        h, m = int(matches[-1][0]), int(matches[-1][1])
        return h, m
    raise ValueError(f"No time found in: {dt_str}")

def detect_shift(dt_str):
    """8:30-16:30 = 日勤、それ以外 = 夜勤"""
    try:
        h, m = _extract_time(dt_str)
        minutes = h * 60 + m
        if 8 * 60 + 30 <= minutes < 16 * 60 + 30:
            return "日勤"
        return "夜勤"
    except Exception:
        return "夜勤"

def get_shift_identity(dt_str):
    """(shift_date_str, shift_type) を返す
    夜勤で00:00-08:30の場合はshift_dateを前日にする"""
    try:
        import re
        # 日付抽出: "4/10" or "2026/04/10"
        dm = re.search(r'(\d{1,4})[/／](\d{1,2})[/／]?(\d{0,2})', dt_str)
        h, m = _extract_time(dt_str)
        minutes = h * 60 + m
        if dm:
            g1, g2, g3 = dm.group(1), dm.group(2), dm.group(3)
            if len(g1) == 4:  # YYYY/MM/DD
                mo, d = int(g2), int(g3) if g3 else 1
            else:  # M/D
                mo, d = int(g1), int(g2)
        else:
            from datetime import date as _d
            today = _d.today()
            mo, d = today.month, today.day
        if 8 * 60 + 30 <= minutes < 16 * 60 + 30:
            shift_type = "日勤"
            shift_date = f"{mo}/{d}"
        else:
            shift_type = "夜勤"
            if minutes < 8 * 60 + 30:
                from datetime import date as _d, timedelta
                year = _d.today().year
                try:
                    prev = _d(year, mo, d) - timedelta(days=1)
                except ValueError:
                    prev = _d(year - 1, 12, 31)
                shift_date = f"{prev.month}/{prev.day}"
            else:
                shift_date = f"{mo}/{d}"
        return shift_date, shift_type
    except Exception:
        return "?", "夜勤"

def auto_case_no(records, dt_str):
    """同一勤務帯（shift_date + shift_type）内の次のNo.を返す"""
    target_date, target_shift = get_shift_identity(dt_str)
    count = 0
    for rec in records.values():
        rec_dt = rec.get("data", {}).get("dt_str", "")
        rd, rs = get_shift_identity(rec_dt)
        if rd == target_date and rs == target_shift:
            count += 1
    return min(count + 1, 15)

def get_default_recorder(dt_str=None):
    """現在または指定日時のシフトリーダー名を返す。未設定なら last_recorder かデフォルト"""
    from datetime import date as _date, timezone, timedelta
    recorders = ["前川","中嶋","森木","小舘","遠藤","提嶋"]
    try:
        if dt_str:
            # get_shift_identityで夜勤0時またぎも正しく処理
            shift_date_str, shift = get_shift_identity(dt_str)
            # shift_date_strは "4/10" 形式
            mo, dy = map(int, shift_date_str.split("/"))
            d = _date(_date.today().year, mo, dy)
        else:
            jst = timezone(timedelta(hours=9))
            now = __import__('datetime').datetime.now(jst)
            tmp = f"{now.month}/{now.day}（）{now.hour:02d}:{now.minute:02d}"
            shift_date_str, shift = get_shift_identity(tmp)
            mo, dy = map(int, shift_date_str.split("/"))
            d = _date(now.year, mo, dy)
        leader = get_leader(d, shift)
        if leader and leader in recorders:
            return leader
    except Exception:
        pass
    return st.session_state.get("last_recorder", "前川")

# ===== ファイル永続化 =====
RECORDS_FILE = "triage_records.json"

def load_records():
    if os.path.exists(RECORDS_FILE):
        try:
            with open(RECORDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_records(records):
    try:
        with open(RECORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ===== フォントパス =====
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
]

def get_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

# ===== テキスト長（ピクセル）を計算 =====
def getlength(text, font):
    dummy = Image.new("RGB", (1, 1))
    d = ImageDraw.Draw(dummy)
    bbox = d.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]

# ===== 赤丸描画 =====
def draw_maru(draw, center, r=22):
    x, y = center
    draw.ellipse([x - r, y - r, x + r, y + r], outline="red", width=5)

# ===== QRデコード =====
def decode_qr(uploaded):
    # PILで読み込み（HEIC以外のカメラ形式・大容量JPEGに対応）
    try:
        pil_img = Image.open(uploaded).convert("RGB")
        # 大きすぎる画像（スマホカメラ等）は縮小してメモリ節約・速度向上
        max_size = 1920
        w, h = pil_img.size
        if max(w, h) > max_size:
            scale = max_size / max(w, h)
            pil_img = pil_img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        img_array = np.array(pil_img)
        img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    except Exception:
        # PILが失敗した場合はOpenCVで直接読み込み
        uploaded.seek(0)
        file_bytes = np.frombuffer(uploaded.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def try_decode(image):
        result = pyzbar.decode(image)
        if result:
            return result[0].data.decode("utf-8")
        return None

    def make_variants(g):
        variants = [g]
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        variants.append(clahe.apply(g))
        _, otsu = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(otsu)
        ada = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 11, 2)
        variants.append(ada)
        ada2 = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                     cv2.THRESH_BINARY, 15, 5)
        variants.append(ada2)
        kernel = np.array([[0,-1,0],[-1,5,-1],[0,-1,0]])
        sharp = cv2.filter2D(g, -1, kernel)
        variants.append(sharp)
        blur = cv2.GaussianBlur(g, (5, 5), 0)
        _, blur_otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        variants.append(blur_otsu)
        return variants

    h, w = gray.shape

    for scale in [1.0, 0.75, 1.5, 0.5, 2.0]:
        rw, rh = int(w * scale), int(h * scale)
        resized = cv2.resize(gray, (rw, rh))
        for variant in make_variants(resized):
            r = try_decode(variant)
            if r:
                return r
            for angle in [90, 180, 270]:
                M = cv2.getRotationMatrix2D((rw/2, rh/2), angle, 1)
                rotated = cv2.warpAffine(variant, M, (rw, rh))
                r = try_decode(rotated)
                if r:
                    return r

    try:
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:3]
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw > w * 0.1 and ch > h * 0.1:
                pad = 20
                x1 = max(0, x-pad); y1 = max(0, y-pad)
                x2 = min(w, x+cw+pad); y2 = min(h, y+ch+pad)
                crop = gray[y1:y2, x1:x2]
                crop_up = cv2.resize(crop, (crop.shape[1]*2, crop.shape[0]*2))
                for variant in make_variants(crop_up):
                    r = try_decode(variant)
                    if r:
                        return r
    except Exception:
        pass

    return None

# ===== QRデータ解析 =====
def parse_qr(raw):
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
    except Exception:
        decoded = raw
    items = decoded.split(",")

    def safe(i, default=""):
        return items[i].strip() if i < len(items) else default

    # 氏名
    name_raw = safe(4)
    if "θ" in name_raw:
        parts = name_raw.split("θ")
        kanji = parts[0].strip()
        kana = parts[1].strip() if len(parts) > 1 else ""
    else:
        kanji = name_raw
        kana = ""

    # 依頼日時
    dt_raw = safe(1)
    try:
        dt = datetime.strptime(dt_raw[:16], "%Y/%m/%d %H:%M")
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        dt_str = dt.strftime(f"%-m/%-d（{weekdays[dt.weekday()]}）%H:%M")
    except Exception:
        dt_str = dt_raw

    # 生年月日
    birth_raw = safe(13)
    if len(birth_raw) == 8 and birth_raw.isdigit():
        birth_y = birth_raw[:4]
        birth_m = birth_raw[4:6].lstrip("0")
        birth_d = birth_raw[6:8].lstrip("0")
    else:
        birth_y = birth_m = birth_d = ""

    # 主訴の自動抽出
    complaint = safe(8)
    if not complaint:
        for idx in [8, 10, 11]:
            v = safe(idx)
            if v and len(v) <= 30 and not v.isdigit():
                complaint = v
                break
    if not complaint:
        history_text = safe(9)
        for sep in ["。", "、", "\n"]:
            if sep in history_text:
                complaint = history_text.split(sep)[0]
                break

    # 救急隊名: インデックス[29]が確定（実データ検証済み）
    # "大通５" → "大通" のように末尾の数字を除去
    import re
    team_raw = safe(29)
    team_name = re.sub(r'\d+$', '', team_raw).strip()
    # [29]が空の場合は "救急隊" を含む項目を全体から検索
    if not team_name:
        for idx in range(len(items)):
            v = safe(idx)
            if "救急隊" in v:
                team_name = v.replace("救急隊", "").strip()
                break

    return {
        "kanji": kanji,
        "kana": kana,
        "dt_str": dt_str,
        "birth_y": birth_y,
        "birth_m": birth_m,
        "birth_d": birth_d,
        "age": safe(14),
        "gender": safe(5),
        "complaint": complaint,
        "history": safe(9),
        "jcs": safe(15),
        "o2_flow": safe(44),    # 酸素流量 (L/min)
        "o2_device": safe(45),  # 酸素デバイス（リザーバーマスク等）
        "bp_s": safe(19),
        "bp_d": safe(20),
        "hr": safe(21),
        "rr": safe(22),
        "bt": safe(23),
        "spo2": safe(43) if safe(43) else safe(24),  # 酸素投与後SpO2[43]優先、なければ投与前[24]
        "spo2_before": safe(24),  # 投与前SpO2
        "team_name": team_name,
        "items": items,
    }

# ===== テンプレート描画 =====

def add_margin_to_image(pil_img, margin_mm=10):
    """A4用紙に合わせた余白付き画像を生成"""
    from PIL import Image as PILImg
    # A4 at 150dpi: 1240x1754px, 10mm margin = ~59px
    A4_W, A4_H = 1240, 1754
    margin_px = int(margin_mm / 25.4 * 150)
    avail_w = A4_W - 2*margin_px
    avail_h = A4_H - 2*margin_px
    iw, ih = pil_img.size
    scale = min(avail_w/iw, avail_h/ih)
    nw, nh = int(iw*scale), int(ih*scale)
    canvas = PILImg.new("RGB", (A4_W, A4_H), (255,255,255))
    x = (A4_W - nw)//2; y = (A4_H - nh)//2
    canvas.paste(pil_img.resize((nw,nh), PILImg.LANCZOS), (x,y))
    return canvas

def make_print_widget(pil_img, key="print"):
    """印刷ボタン：クリックするとiframe内で画像を表示しwindow.print()を実行"""
    import base64
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=95)
    b64 = base64.b64encode(buf.getvalue()).decode()
    html = f"""<!DOCTYPE html>
<html><head>
<style>
  body {{ margin:0; padding:0; background:transparent; font-family:sans-serif; }}
  @media screen {{
    .img-wrap {{ display:none; }}
    .print-btn {{
      display:block; width:100%; height:38px; padding:0 14px; box-sizing:border-box;
      background:transparent; color:inherit;
      border:1px solid rgba(49,51,63,0.2);
      border-radius:4px; font-size:0.875rem; font-weight:400;
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      cursor:pointer; letter-spacing:normal; line-height:1;
    }}
    .print-btn:hover {{ border-color:#f63366; color:#f63366; }}
    @media (prefers-color-scheme: dark) {{
      .print-btn {{ border-color:rgba(250,250,250,0.2); color:#fff; }}
    }}
  }}
  @media print {{
    .print-btn {{ display:none; }}
    .img-wrap {{ display:block; }}
    @page {{ size:A4; margin:0; }}
    html, body {{ height:100%; overflow:hidden; margin:0; padding:0; }}
    img {{ width:100%; height:auto; max-height:100vh; display:block; }}
  }}
</style>
</head><body>
<div class="img-wrap"><img src="data:image/jpeg;base64,{b64}"></div>
<button class="print-btn" onclick="window.print()">🖨️ 台帳を印刷</button>
</body></html>"""
    return html


def safe_triage_fname(data, case_no):
    """患者名を含まない安全なファイル名を生成"""
    dt_raw = data.get("dt_str","")
    # "4/8（水）21:25" → "20260408_2125"
    try:
        from datetime import datetime as _dt2
        # dt_rawから月/日と時刻を抽出
        date_part = dt_raw.split("（")[0].strip()  # "4/8"
        time_part = dt_raw.split("）")[-1].strip() if "）" in dt_raw else ""  # "21:25"
        m, d = date_part.split("/")
        h, mi = time_part.replace(":","")[:2], time_part.replace(":","")[2:4]
        from datetime import date as _date2
        year = _date2.today().year
        dt = f"{year}{int(m):02d}{int(d):02d}_{h}{mi}"
    except Exception:
        dt = dt_raw.replace("/","").replace("（","").replace("）","").replace(":","").replace(" ","")[:12]
    age = data.get("age","")
    sex = "M" if data.get("gender")=="1" else ("F" if data.get("gender")=="2" else "")
    return f"triage_{case_no:02d}_{dt}_{age}{sex}.jpg"

def render_triage(data, recorder, origin, shift, history_yn, history_dept, decision, res, case_no, free_note=""):
    base = Image.open("template.png").convert("RGB")
    d = ImageDraw.Draw(base)

    f18 = get_font(18)
    f24 = get_font(24)
    f28 = get_font(28)
    f36 = get_font(36)
    f44 = get_font(44)

    # ===== No.（X=11-135, Y=3-122, 中央寄せ） =====
    no_str = str(case_no)
    f_no = get_font(52)
    tw_no = getlength(no_str, f_no)
    cell_w_no = 135 - 11
    no_x = 11 + (cell_w_no - tw_no) // 2
    d.text((no_x, 26), no_str, font=f_no, fill="black")

    # ===== 記載者（V=911-1176, Y=55, 中央寄せ） =====
    cell_w = 1176 - 911
    tw = getlength(recorder, f44)
    kx_rec = 911 + (cell_w - tw) // 2
    d.text((kx_rec, 38), recorder, font=f44, fill="black")

    # ===== 依頼日時 =====
    d.text((155, 145), data["dt_str"], font=f36, fill="black")

    # ===== 日勤・夜勤 ◯（(日勤・夜勤)テキスト Y≈185, 日勤X≈57, 夜勤X≈107）=====
    if shift == "日勤":
        draw_maru(d, (57, 185), r=15)
    else:
        draw_maru(d, (107, 185), r=15)

    # ===== 依頼元（救急隊名, V=676-911） =====
    origin_clean = origin.replace("救急隊", "").strip()
    d.text((730, 148), origin_clean, font=f28, fill="black")

    # ===== 受診歴 =====
    if history_yn == "有":
        draw_maru(d, (1100, 165), r=22)
        f16 = get_font(16)
        dept = history_dept.rstrip("科")
        # 7文字ごとに改行して縦に並べる（X=1130〜1248の範囲）
        line_h = 18
        max_chars = 6
        lines = [dept[i:i+max_chars] for i in range(0, len(dept), max_chars)] if dept else []
        for li, line in enumerate(lines[:3]):
            d.text((1100, 143 + li * line_h), line, font=f16, fill="black")
    else:
        draw_maru(d, (1270, 165), r=22)

    # ===== 患者氏名（V=135-543, 中央寄せ） =====
    cell_w_name = 543 - 135
    kw = getlength(data["kanji"], f44)
    kx = 135 + (cell_w_name - kw) // 2
    d.text((kx, 245), data["kana"], font=f18, fill="black")
    d.text((kx, 268), data["kanji"], font=f44, fill="black")

    f30 = get_font(30)

    # ===== 生年月日（上段行 Y=222-289, Y=242） =====
    # ズームテスト確認済み: 「年」label_x=1018, 「月」label_x=1152, 「日」label_x=1284
    for val, label_x in [(data["birth_y"], 1018), (data["birth_m"], 1152), (data["birth_d"], 1284)]:
        if val:
            tw_val = getlength(val, f30)
            d.text((label_x - tw_val - 4, 242), val, font=f30, fill="black")

    # ===== 年齢（下段行 Y=289-356）=====
    # ズームテスト確認: 「歳」はX=999-1020 → 年の数字（X≈961）と同じ位置に来るよう右寄せ
    if data["age"]:
        age_tw = getlength(data["age"], f30)
        d.text((999 - age_tw - 4, 305), data["age"], font=f30, fill="black")

    # ===== 性別 =====
    if data["gender"] == "1":
        draw_maru(d, (1140, 318), r=18)
    elif data["gender"] == "2":
        draw_maru(d, (1214, 322), r=18)

    # ===== 主訴（折返し幅30文字） =====
    complaint_lines = []
    line = ""
    for ch in data["complaint"]:
        line += ch
        if len(line) >= 30:
            complaint_lines.append(line)
            line = ""
    if line:
        complaint_lines.append(line)
    for i, ln in enumerate(complaint_lines):
        d.text((150, 405 + i * 32), ln, font=f28, fill="black")

    # ===== 経過等（折返し幅18文字, Y>1260で打切り） =====
    history_lines = []
    line = ""
    for ch in data["history"]:
        line += ch
        if len(line) >= 18:
            history_lines.append(line)
            line = ""
    if line:
        history_lines.append(line)
    for i, ln in enumerate(history_lines):
        y = 530 + i * 32
        if y > 1260:
            break
        d.text((150, y), ln, font=f28, fill="black")

    # ===== バイタルサイン =====
    # 酸素投与
    o2_flow   = data.get("o2_flow", "").strip()
    o2_device = data.get("o2_device", "").strip()
    if o2_flow and o2_flow != "0":
        draw_maru(d, (1090, 612), r=16)
        d.text((1200, 588), o2_flow, font=f28, fill="black")
        # デバイス名（流量の下に小さく）
        if o2_device:
            d.text((1130, 630), o2_device, font=f28, fill="black")
    else:
        draw_maru(d, (1090, 665), r=16)

    d.text((1120, 705), data["jcs"], font=f28, fill="black")
    d.text((1060, 775), data["rr"], font=f28, fill="black")
    d.text((1060, 845), data["hr"], font=f28, fill="black")
    d.text((1060, 915), f"{data['bp_s']}/{data['bp_d']}", font=f28, fill="black")
    # SpO2: 投与前→投与後の両方を表示
    spo2_before = data.get("spo2_before", "").strip()
    spo2_after  = data.get("spo2", "").strip()
    if spo2_before and spo2_after and spo2_before != spo2_after:
        spo2_str = f"{spo2_before}→{spo2_after}"
    else:
        spo2_str = spo2_after or spo2_before
    d.text((1060, 978), spo2_str, font=f28, fill="black")
    d.text((1060, 1048), data["bt"], font=f28, fill="black")

    # ===== 判定 =====
    if decision == "応需":
        draw_maru(d, (74, 1355), r=26)
    else:
        draw_maru(d, (74, 1420), r=26)

    if decision == "応需":
        # 初期対応した科
        init_map = {"当直医": (615, 1345), "救急科": (737, 1345), "その他": (888, 1345)}
        if res.get("init") in init_map:
            draw_maru(d, init_map[res["init"]], r=27)
        if res.get("init") == "その他" and res.get("init_other"):
            d.text((960, 1332), res["init_other"].rstrip("科"), font=f18, fill="black")

        # 最終転帰
        if res.get("out") == "入院":
            draw_maru(d, (400, 1435), r=16)
            # 病棟
            ward_map = {"4東": (784, 1466), "HCU": (861, 1466), "ICU": (943, 1466)}
            if res.get("ward") in ward_map:
                draw_maru(d, ward_map[res["ward"]], r=18)
            elif res.get("ward") == "6東":
                draw_maru(d, (784, 1490), r=18)
                d.text((806, 1480), "6東", font=f18, fill="black")
            elif res.get("ward") == "その他":
                draw_maru(d, (784, 1490), r=18)
                if res.get("ward_other"):
                    d.text((806, 1480), res["ward_other"], font=f18, fill="black")
            # 主科
            main_map = {"臨研": (1083, 1445), "救急科": (1095, 1480)}
            if res.get("main") in main_map:
                draw_maru(d, main_map[res["main"]], r=18)
            elif res.get("main") == "その他":
                draw_maru(d, (1083, 1510), r=18)
                if res.get("main_other"):
                    d.text((1100, 1500), res["main_other"].rstrip("科"), font=f18, fill="black")
        elif res.get("out") == "帰宅":
            draw_maru(d, (395, 1461), r=16)
    else:
        # 不応需理由
        # テンプレート画像解析済みY座標（各行テキスト中央）
        reason_labels = [
            "1. 緊急性なし",
            "2. ベッド満床",
            "3. 既定の応需不可",
            "4. 対応可能な医師不在",
            "5. 緊急手術制限中",
            "6-A. 医師処置中",
            "6-B. 看護師処置中",
            "7. その他",
        ]
        reason_y = [1537, 1570, 1604, 1640, 1671, 1704, 1738, 1772]

        rk = res.get("reason", "")
        for label, ry in zip(reason_labels, reason_y):
            if rk and rk.split(".")[0].strip() == label.split(".")[0].strip():
                draw_maru(d, (148, ry), r=16)

                # 理由2: ベッド満床のサブ選択肢
                if rk.startswith("2."):
                    bed_map = {
                        "救急外来": (427, 1570),
                        "HCU":    (523, 1570),
                        "4東":    (635, 1570),
                        "その他": (752, 1570),
                    }
                    sub = res.get("bed_sub", "")
                    if sub in bed_map:
                        draw_maru(d, bed_map[sub], r=13)

                # 理由3-6B: フリーコメント
                comment_x = {
                    "3.": 480, "4.": 490, "5.": 430,
                    "6-A.": 700, "6-B.": 720,
                }
                rk_prefix = rk.split(" ")[0]
                if rk_prefix in comment_x and res.get("reason_comment"):
                    d.text((comment_x[rk_prefix], ry - 14),
                           res["reason_comment"], font=f24, fill="black")
                break

    # ===== 自由記載（Y=1870付近, 折返し幅35文字） =====
    if free_note:
        fn_lines = []
        line = ""
        for ch in free_note:
            line += ch
            if len(line) >= 35:
                fn_lines.append(line)
                line = ""
        if line:
            fn_lines.append(line)
        for i, ln in enumerate(fn_lines):
            d.text((150, 1870 + i * 36), ln, font=f28, fill="black")

    return add_margin_to_image(base)

# ===== メインUI =====

# セッション状態初期化（ページリロード時はファイルから復元）
if "triage_records" not in st.session_state:
    st.session_state.triage_records = load_records()
if "triage_raw" not in st.session_state:
    st.session_state.triage_raw = None
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "uploaded_bytes" not in st.session_state:
    st.session_state.uploaded_bytes = None
if "editing_key" not in st.session_state:
    st.session_state.editing_key = None

# ===== 新規患者入力 =====
st.subheader("🆕 新規患者")

# 手入力モード切替
if "manual_mode" not in st.session_state:
    st.session_state.manual_mode = False
if "input_mode" not in st.session_state:
    st.session_state.input_mode = None  # None, "qr", "manual"

col_qr, col_manual = st.columns(2)
with col_qr:
    if st.button("📷 QRコード読み取り", use_container_width=True,
                 type="primary" if st.session_state.input_mode == "qr" else "secondary"):
        st.session_state.input_mode = "qr"
        st.session_state.manual_mode = False
        st.rerun()
with col_manual:
    if st.button("✍️ 手入力", use_container_width=True,
                 type="primary" if st.session_state.input_mode == "manual" else "secondary"):
        st.session_state.input_mode = "manual"
        st.session_state.manual_mode = True
        st.session_state.triage_raw = None
        st.session_state.uploaded_bytes = None
        st.rerun()

# ===== 手入力モード =====
if st.session_state.manual_mode:
    from datetime import datetime as dt2
    jst = __import__('datetime').timezone(__import__('datetime').timedelta(hours=9))
    now_jst = dt2.now(jst)

    # --- 患者基本情報 ---
    mc1, mc2 = st.columns(2)
    with mc1:
        from datetime import timezone as _tz, timedelta as _td
        _jst_now = datetime.now(_tz(_td(hours=9)))
        _tmp_dt = f"{_jst_now.month}/{_jst_now.day}（）{_jst_now.hour:02d}:{_jst_now.minute:02d}"
        _next = auto_case_no(st.session_state.triage_records, _tmp_dt)
        m_case_no = st.selectbox("No.", list(range(1,16)), index=_next-1, key="m_case_no_inp")
        recorders = ["前川", "中嶋", "森木", "小舘", "遠藤", "提嶋"]
        _def_rec = get_default_recorder()
        rec_idx = recorders.index(_def_rec) if _def_rec in recorders else 0
        m_recorder = st.selectbox("記載者", recorders, index=rec_idx, key="m_recorder")
        m_kanji = st.text_input("患者氏名（漢字）", placeholder="山田 太郎")
        m_kana  = st.text_input("患者氏名（カナ）", placeholder="ヤマダ タロウ")
        m_age   = st.number_input("年齢（才）", min_value=0, max_value=120, value=0, step=1)
        m_gender = st.radio("性別", ["1（男）","2（女）","未記載"], horizontal=True)
    with mc2:
        m_date = st.date_input("受付日", value=now_jst.date(), key="m_date")
        m_time = st.time_input("受付時刻", value=now_jst.replace(minute=(now_jst.minute//5)*5, second=0, microsecond=0).time(), key="m_time")
        m_birth_y = st.number_input("生年（西暦）", min_value=1900, max_value=2026, value=1950, step=1)
        mc_b1, mc_b2 = st.columns(2)
        with mc_b1: m_birth_m = st.number_input("月", min_value=1, max_value=12, value=1, step=1)
        with mc_b2: m_birth_d = st.number_input("日", min_value=1, max_value=31, value=1, step=1)

    m_complaint = st.text_input("主訴", placeholder="胸痛、呼吸困難")
    m_history   = st.text_area("経過等", height=60, placeholder="発症経緯など")
    mc3,mc4,mc5,mc6,mc7 = st.columns(5)
    with mc3: m_jcs  = st.text_input("JCS", value="0")
    with mc4: m_bp   = st.text_input("BP(上/下)", placeholder="120/80")
    with mc5: m_hr   = st.text_input("HR", placeholder="80")
    with mc6: m_rr   = st.text_input("RR", placeholder="16")
    with mc7: m_spo2 = st.text_input("SpO2", placeholder="98")
    m_bt = st.text_input("体温（BT）", placeholder="36.5")

    # --- 救急隊・台帳情報 ---
    RESCUE_TEAMS_M = ["","警防","中央","大通","山鼻","豊水","幌西","北","北エルム","あいの里",
        "篠路","新光","東","東モエレ","栄","札苗","苗穂","白石","南郷","菊水",
        "北郷","厚別","厚別西","豊平","月寒","平岸","西岡","清田","北野","南",
        "藤野","定山渓","西","発寒","八軒","西野","手稲","前田","その他（直接入力）"]
    mc_a, mc_b = st.columns(2)
    with mc_a:
        m_team_sel = st.selectbox("依頼元救急隊", RESCUE_TEAMS_M, key="m_team_sel")
        if m_team_sel == "その他（直接入力）":
            m_team = st.text_input("救急隊名を入力", key="m_team_other", placeholder="例: 石狩")
        else:
            m_team = m_team_sel
    with mc_b:
        m_history_yn = st.radio("受診歴", ["無","有"], horizontal=True, key="m_hist_yn")
        m_history_dept = ""
        if m_history_yn == "有":
            m_history_dept = st.text_input("受診科名", key="m_hist_dept")
        m_decision = st.radio("判定", ["応需","不応需"], horizontal=True, key="m_decision")

    m_free_note = st.text_area("自由記載", height=80, key="m_free_note")

    m_res = {"decision": m_decision}
    if m_decision == "応需":
        m_res["init"] = st.selectbox("初期対応した科", ["当直医","救急科","その他"], key="m_init")
        if m_res["init"] == "その他":
            m_res["init_other"] = st.text_input("初期対応科名", key="m_init_other")
        m_res["out"] = st.selectbox("最終転帰", ["（後で入力）","入院","帰宅","その他"], key="m_out")
        if m_res["out"] == "入院":
            m_res["ward"] = st.selectbox("病棟", ["（後で入力）","4東","6東","HCU","ICU","その他"], key="m_ward")
            if m_res["ward"] == "その他":
                m_res["ward_other"] = st.text_input("病棟名", key="m_ward_other")
            m_res["main"] = st.selectbox("主科", ["（後で入力）","臨研","救急科","その他"], key="m_main")
            if m_res["main"] == "その他":
                m_res["main_other"] = st.text_input("主科名", key="m_main_other")
    else:
        m_res["reason"] = st.selectbox("不応需理由", [
            "1. 緊急性なし","2. ベッド満床","3. 既定の応需不可",
            "4. 対応可能な医師不在","5. 緊急手術制限中",
            "6-A. 医師処置中","6-B. 看護師処置中","7. その他",
        ], key="m_reason")
        if m_res["reason"].startswith("2."):
            m_res["bed_sub"] = st.radio("ベッド満床の場所", ["救急外来","HCU","4東","その他"], horizontal=True, key="m_bed_sub")
        if any(m_res["reason"].startswith(p) for p in ["3.","4.","5.","6-A.","6-B."]):
            m_res["reason_comment"] = st.text_input("コメント", key="m_reason_comment")

    def _build_manual_data():
        weekdays = ["月","火","水","木","金","土","日"]
        dt_str = f"{m_date.month}/{m_date.day}（{weekdays[m_date.weekday()]}）{m_time.strftime('%H:%M')}"
        bp_parts = m_bp.replace("/"," ").split() if m_bp else ["",""]
        gender_val = "1" if "男" in m_gender else ("2" if "女" in m_gender else "")
        return {
            "kanji": m_kanji, "kana": m_kana, "dt_str": dt_str,
            "birth_y": str(m_birth_y), "birth_m": str(m_birth_m), "birth_d": str(m_birth_d),
            "age": str(m_age) if m_age > 0 else "", "gender": gender_val,
            "complaint": m_complaint, "history": m_history,
            "jcs": m_jcs, "bp_s": bp_parts[0] if bp_parts else "",
            "bp_d": bp_parts[1] if len(bp_parts)>1 else "",
            "hr": m_hr, "rr": m_rr, "bt": m_bt, "spo2": m_spo2,
            "team_name": m_team, "items": [],
        }

    ms1, ms2 = st.columns(2)
    with ms1:
        if st.button("💾 患者データを保存", use_container_width=True, key="m_save"):
            data = _build_manual_data()
            shift = detect_shift(data["dt_str"])
            key = data["kanji"] or data["kana"] or "不明"
            st.session_state.triage_records[key] = {
                "data": data, "shift": shift, "case_no": m_case_no,
                "recorder": m_recorder, "origin": m_team,
                "history_yn": m_history_yn, "history_dept": m_history_dept,
                "decision": m_decision, "res": m_res, "free_note": m_free_note,
            }
            save_records(st.session_state.triage_records)
            st.session_state.last_recorder = m_recorder
            st.session_state.manual_mode = False
            st.session_state.input_mode = None
            st.success(f"✅ {key} を保存しました。")
            st.rerun()
    with ms2:
        if st.button("🖨️ 今すぐ台帳を生成", type="primary", use_container_width=True, key="m_gen"):
            data = _build_manual_data()
            shift = detect_shift(data["dt_str"])
            result = render_triage(data, m_recorder, m_team, shift, m_history_yn, m_history_dept,
                                   m_decision, m_res, m_case_no, m_free_note)
            st.image(result, use_container_width=True)
            buf = io.BytesIO()
            result.save(buf, format="JPEG", quality=95)
            components.html(make_print_widget(result, "m_print"), height=38)

# ===== QRコードモード =====
if st.session_state.input_mode == "qr":

    _qc1, _qc2 = st.columns(2)
    with _qc1:
        try:
            from streamlit_paste_button import paste_image_button as pbutton
            paste_result = pbutton(
                label="📋 クリップボードから貼り付け",
                key="paste_btn",
                background_color="#262730",
                hover_background_color="#3d3f4a",
                text_color="#ffffff",
            )
            if paste_result.image_data is not None:
                _buf = io.BytesIO()
                paste_result.image_data.save(_buf, format="PNG")
                _bytes = _buf.getvalue()
                if _bytes != st.session_state.get("uploaded_bytes"):
                    st.session_state.uploaded_bytes = _bytes
                    st.session_state.triage_raw = None
                    st.rerun()
        except ImportError:
            st.info("ペースト機能不可")
    with _qc2:
        # st.file_uploaderをボタン風にCSSでスタイリング（カメラ対応・データ取得可）
        st.markdown("""<style>
        /* ファイルアップローダーをボタン風に */
        div[data-testid="stFileUploader"] > label {display:none}
        div[data-testid="stFileUploader"] section {
            border:none !important; padding:0 !important; background:transparent !important;
        }
        div[data-testid="stFileUploaderDropzone"] {
            padding:0 !important; border-radius:4px !important; min-height:0 !important;
            border:1px solid rgba(250,250,250,0.2) !important; background:#262730 !important;
        }
        div[data-testid="stFileUploaderDropzone"]:hover {background:#3d3f4a !important;}
        div[data-testid="stFileUploaderDropzoneInstructions"] {display:none !important;}
        div[data-testid="stFileUploaderDropzone"] > button {
            width:100% !important; height:38px !important; background:transparent !important;
            color:white !important; border:none !important;
            font-size:0.875rem !important; cursor:pointer !important;
        }
        div[data-testid="stFileUploaderDropzone"] > button > span {color:white !important;}
        div[data-testid="stFileUploaderDropzone"] > button svg {fill:white !important;}
        div[data-testid="stFileUploader"] section > div:last-child {display:none !important;}
        </style>""", unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "📁 画像をアップロード",
            type=["png","jpg","jpeg"],
            label_visibility="collapsed",
            key=f"uploader_{st.session_state.uploader_key}"
        )

    # アップロードされたファイルのバイトをセッションに保持
    if uploaded is not None:
        st.session_state.uploaded_bytes = uploaded.read()
        uploaded.seek(0)

    # セッションに保存済みのファイルを使う
    has_file = uploaded is not None or st.session_state.get("uploaded_bytes") is not None

    if has_file:
        # まだ読み取っていない場合のみデコード実行
        if st.session_state.triage_raw is None:
            with st.spinner("QRコードを読み取り中..."):
                if uploaded is not None:
                    raw = decode_qr(uploaded)
                else:
                    raw = decode_qr(io.BytesIO(st.session_state.uploaded_bytes))
            if raw is None:
                st.error("❌ QRコードが認識できませんでした。\n\n**対処法：**\n- QRコードを画面の中央に大きく写して再撮影\n- 明るい場所でピントを合わせてから撮影\n- スクリーンショット画像を使用")
            else:
                st.session_state.triage_raw = raw
                st.success("✅ QRコード読み取り成功！")

        raw = st.session_state.triage_raw

        if raw:
            data = parse_qr(raw)
            shift = detect_shift(data["dt_str"])
            kanji = data.get("kanji","")
            birth_y = data.get("birth_y",""); birth_m = data.get("birth_m",""); birth_d = data.get("birth_d","")
            dob = f"{birth_y}年{birth_m}月{birth_d}日" if birth_y else ""
            age = data.get("age","")
            age_str = f"{age}歳" if age else ""
            info_parts = [p for p in [kanji, dob, age_str] if p]
            if info_parts:
                st.markdown(f"**患者:** {'　'.join(info_parts)}")


            st.subheader("台帳情報の入力")
            col1, col2 = st.columns(2)
            with col1:
                next_no = auto_case_no(st.session_state.triage_records, data["dt_str"])
                case_no = st.selectbox("No.", list(range(1, 16)), index=next_no-1)
                recorders = ["前川", "中嶋", "森木", "小舘", "遠藤", "提嶋"]
                _def_rec_qr = get_default_recorder(data["dt_str"])
                rec_idx = recorders.index(_def_rec_qr) if _def_rec_qr in recorders else 0
                recorder = st.selectbox("記載者", recorders, index=rec_idx)
                origin = st.text_input("依頼元（救急隊）", value=data.get("team_name", "中央"))
                history_yn = st.radio("受診歴", ["無", "有"], horizontal=True, key="qr_hist_yn")
            with col2:
                history_dept = ""
                if history_yn == "有":
                    history_dept = st.text_input("受診科名", key="qr_hist_dept")
                decision = st.radio("判定", ["応需", "不応需"], horizontal=True)

            complaint_edit = st.text_input("主訴（編集可）", value=data["complaint"])
            data["complaint"] = complaint_edit
            free_note = st.text_area("自由記載", placeholder="自由記載欄へのコメントを入力", height=80)

            res = {"decision": decision}
            if decision == "応需":
                res["init"] = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                if res["init"] == "その他":
                    res["init_other"] = st.text_input("初期対応科名")
                res["out"] = st.selectbox("最終転帰", ["（後で入力）", "入院", "帰宅", "その他"])
                if res["out"] == "入院":
                    res["ward"] = st.selectbox("病棟", ["（後で入力）", "4東", "6東", "HCU", "ICU", "その他"])
                    if res["ward"] == "その他":
                        res["ward_other"] = st.text_input("病棟名")
                    res["main"] = st.selectbox("主科", ["（後で入力）", "臨研", "救急科", "その他"])
                    if res["main"] == "その他":
                        res["main_other"] = st.text_input("主科名")
            else:
                res["reason"] = st.selectbox("不応需理由", [
                    "1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可",
                    "4. 対応可能な医師不在", "5. 緊急手術制限中",
                    "6-A. 医師処置中", "6-B. 看護師処置中", "7. その他",
                ])
                if res["reason"].startswith("2."):
                    res["bed_sub"] = st.radio("ベッド満床の場所",
                        ["救急外来", "HCU", "4東", "その他"], horizontal=True)
                if any(res["reason"].startswith(p) for p in ["3.", "4.", "5.", "6-A.", "6-B."]):
                    res["reason_comment"] = st.text_input("コメント（理由の右欄）")

            col_save, col_gen = st.columns(2)
            with col_save:
                if st.button("💾 患者データを保存（転帰は後で入力）", use_container_width=True):
                    key = data["kanji"] or data["kana"] or "不明"
                    st.session_state.triage_records[key] = {
                        "data": data, "shift": shift, "case_no": case_no,
                        "recorder": recorder, "origin": origin,
                        "history_yn": history_yn, "history_dept": history_dept,
                        "decision": decision, "res": res, "free_note": free_note,
                    }
                    save_records(st.session_state.triage_records)
                    st.session_state.last_recorder = recorder
                    st.session_state.triage_raw = None
                    st.session_state.uploader_key += 1
                    st.session_state.uploaded_bytes = None
                    st.session_state.input_mode = None
                    st.success(f"✅ {key}（{shift}）のデータを保存しました。")
                    st.rerun()
            with col_gen:
                if st.button("🖨️ 今すぐ台帳を生成", type="primary", use_container_width=True):
                    result = render_triage(data, recorder, origin, shift, history_yn, history_dept,
                                           decision, res, case_no, free_note)
                    st.image(result, use_container_width=True)
                    buf = io.BytesIO()
                    result.save(buf, format="JPEG", quality=95)
                    components.html(make_print_widget(result, "qr_print"), height=38)

# ===== 編集モード =====
records = st.session_state.triage_records  # 編集モードで必要
editing_key = st.session_state.editing_key
if editing_key and editing_key in records:
    rec = records[editing_key]
    data = rec["data"]
    kana = data.get("kana","").strip()
    display = kana if kana else editing_key
    st.subheader(f"✏️ 編集：{display}")
    res = dict(rec.get("res", {}))

    # 基本情報
    st.markdown("**基本情報**")
    ec1, ec2 = st.columns(2)
    with ec1:
        case_no = st.selectbox("No.", list(range(1,16)),
                               index=int(rec.get("case_no",1))-1, key="ed_case_no")
        e_kanji = st.text_input("患者氏名（漢字）", value=data.get("kanji",""), key="ed_kanji")
        e_kana  = st.text_input("患者氏名（カナ）",  value=data.get("kana",""),  key="ed_kana")
        e_age   = st.text_input("年齢",  value=data.get("age",""),  key="ed_age")
        # 生年月日を年齢の近くに表示
        birth_y = data.get("birth_y",""); birth_m = data.get("birth_m",""); birth_d = data.get("birth_d","")
        dob_str = f"{birth_y}年{birth_m}月{birth_d}日" if birth_y else ""
        if dob_str:
            st.caption(f"生年月日: {dob_str}")
        gender_opts = ["1（男）","2（女）","未記載"]
        g_cur = "1（男）" if data.get("gender")=="1" else ("2（女）" if data.get("gender")=="2" else "未記載")
        e_gender_sel = st.radio("性別", gender_opts, index=gender_opts.index(g_cur), horizontal=True, key="ed_gender")
    with ec2:
        recorders = ["前川", "中嶋", "森木", "小舘", "遠藤", "提嶋"]
        rec_idx = recorders.index(rec.get("recorder","前川")) if rec.get("recorder") in recorders else 0
        e_recorder = st.selectbox("記載者", recorders, index=rec_idx, key="ed_recorder")
        RESCUE_TEAMS_E = ["","警防","中央","大通","山鼻","豊水","幌西","北","北エルム","あいの里",
    "篠路","新光","東","東モエレ","栄","札苗","苗穂","白石","南郷","菊水",
    "北郷","厚別","厚別西","豊平","月寒","平岸","西岡","清田","北野","南",
    "藤野","定山渓","西","発寒","八軒","西野","手稲","前田"
]
        _orig = rec.get("origin","")
        _eidx = RESCUE_TEAMS_E.index(_orig) if _orig in RESCUE_TEAMS_E else len(RESCUE_TEAMS_E)-1
        e_team_sel = st.selectbox("依頼元救急隊", RESCUE_TEAMS_E, index=_eidx, key="ed_team")
        if e_team_sel == "その他（直接入力）":
            e_origin = st.text_input("救急隊名", value=_orig if _orig not in RESCUE_TEAMS_E else "", key="ed_team_other")
        else:
            e_origin = e_team_sel
        e_history_yn = st.radio("受診歴", ["無","有"],
                                index=0 if rec.get("history_yn","無")=="無" else 1,
                                horizontal=True, key="ed_hist_yn")
        e_history_dept = ""
        if e_history_yn == "有":
            e_history_dept = st.text_input("受診科名", value=rec.get("history_dept",""), key="ed_hist_dept")

    e_complaint = st.text_input("主訴", value=data.get("complaint",""), key="ed_complaint")

    # バイタル
    st.markdown("**バイタルサイン**")
    ev1,ev2,ev3,ev4,ev5,ev6 = st.columns(6)
    with ev1: e_jcs  = st.text_input("JCS",  value=data.get("jcs",""),  key="ed_jcs")
    with ev2: e_bps  = st.text_input("BP上",  value=data.get("bp_s",""), key="ed_bps")
    with ev3: e_bpd  = st.text_input("BP下",  value=data.get("bp_d",""), key="ed_bpd")
    with ev4: e_hr   = st.text_input("HR",   value=data.get("hr",""),   key="ed_hr")
    with ev5: e_rr   = st.text_input("RR",   value=data.get("rr",""),   key="ed_rr")
    with ev6: e_bt   = st.text_input("BT",   value=data.get("bt",""),   key="ed_bt")
    # 酸素・SpO2
    st.markdown("**酸素・SpO2**")
    eo1,eo2,eo3,eo4,eo5 = st.columns(5)
    with eo1: e_o2_flow   = st.text_input("酸素流量(L)", value=data.get("o2_flow",""),   key="ed_o2_flow",   placeholder="0=なし")
    with eo2: e_o2_device = st.text_input("デバイス",    value=data.get("o2_device",""), key="ed_o2_device", placeholder="鼻カニューレ等")
    with eo3: e_spo2_b    = st.text_input("SpO2(前)",   value=data.get("spo2_before",""),key="ed_spo2_b",    placeholder="投与前")
    with eo4: e_spo2      = st.text_input("SpO2(後)",   value=data.get("spo2",""),       key="ed_spo2",      placeholder="投与後")
    with eo5: st.markdown(f"<div style='font-size:13px;padding-top:28px'>{data.get('spo2_before','')}→{data.get('spo2','')}</div>", unsafe_allow_html=True)

    shift = rec.get("shift","日勤")
    shift = st.radio("勤務帯", ["日勤","夜勤"],
                     index=0 if shift=="日勤" else 1,
                     horizontal=True, key="ed_shift")
    st.info(f"🕐 受付時刻: {data['dt_str']}　勤務帯: **{shift}**")
    free_note = st.text_area("自由記載", value=rec.get("free_note",""), height=80, key="ed_free")

    # 転帰
    st.markdown("**転帰**")
    decision = st.radio("判定", ["応需","不応需"], horizontal=True,
                        index=0 if res.get("decision","応需")=="応需" else 1, key="ed_decision")
    if decision == "応需":
        init_opts = ["当直医","救急科","その他"]
        res["init"] = st.selectbox("初期対応した科", init_opts,
                                   index=init_opts.index(res["init"]) if res.get("init") in init_opts else 0, key="ed_init")
        if res["init"] == "その他":
            res["init_other"] = st.text_input("初期対応科名", value=res.get("init_other",""), key="ed_init_other")
        out_opts = ["入院","帰宅","その他"]
        cur_out = res.get("out","") if res.get("out") in out_opts else "入院"
        res["out"] = st.selectbox("最終転帰", out_opts, index=out_opts.index(cur_out), key="ed_out")
        if res["out"] == "入院":
            ward_opts = ["4東","6東","HCU","ICU","その他"]
            cur_ward = res.get("ward","") if res.get("ward") in ward_opts else "4東"
            res["ward"] = st.selectbox("病棟", ward_opts, index=ward_opts.index(cur_ward), key="ed_ward")
            if res["ward"] == "その他":
                res["ward_other"] = st.text_input("病棟名", value=res.get("ward_other",""), key="ed_ward_other")
            main_opts = ["臨研","救急科","その他"]
            cur_main = res.get("main","") if res.get("main") in main_opts else "臨研"
            res["main"] = st.selectbox("主科", main_opts, index=main_opts.index(cur_main), key="ed_main")
            if res["main"] == "その他":
                res["main_other"] = st.text_input("主科名", value=res.get("main_other",""), key="ed_main_other")
    else:  # 不応需
        reason_opts = [
            "1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可",
            "4. 対応可能な医師不在", "5. 緊急手術制限中",
            "6-A. 医師処置中", "6-B. 看護師処置中", "7. その他",
        ]
        cur_reason = res.get("reason","") if res.get("reason") in reason_opts else reason_opts[0]
        res["reason"] = st.selectbox("不応需理由", reason_opts,
                                     index=reason_opts.index(cur_reason), key="ed_reason")
        if res["reason"].startswith("2."):
            bed_opts = ["救急外来","HCU","4東","その他"]
            cur_bed = res.get("bed_sub","") if res.get("bed_sub") in bed_opts else bed_opts[0]
            res["bed_sub"] = st.radio("ベッド満床の場所", bed_opts,
                                      index=bed_opts.index(cur_bed), horizontal=True, key="ed_bed_sub")
        if any(res["reason"].startswith(p) for p in ["3.","4.","5.","6-A.","6-B."]):
            res["reason_comment"] = st.text_input("コメント", value=res.get("reason_comment",""), key="ed_reason_comment")

    # ボタン
    col_save, col_gen, col_cancel = st.columns(3)
    with col_save:
        if st.button("💾 保存", use_container_width=True):
            res["decision"] = decision
            # dataを更新
            data["kanji"] = e_kanji; data["kana"] = e_kana; data["age"] = e_age
            data["gender"] = "1" if "男" in e_gender_sel else ("2" if "女" in e_gender_sel else "")
            data["complaint"] = e_complaint
            data["jcs"]=e_jcs; data["bp_s"]=e_bps; data["bp_d"]=e_bpd
            data["hr"]=e_hr; data["rr"]=e_rr; data["spo2"]=e_spo2; data["bt"]=e_bt
            data["o2_flow"]=e_o2_flow; data["o2_device"]=e_o2_device; data["spo2_before"]=e_spo2_b
            records[editing_key]["data"] = data
            records[editing_key]["res"] = res
            records[editing_key]["free_note"] = free_note
            records[editing_key]["case_no"] = case_no
            records[editing_key]["recorder"] = e_recorder
            records[editing_key]["origin"] = e_origin
            records[editing_key]["history_yn"] = e_history_yn
            records[editing_key]["history_dept"] = e_history_dept
            records[editing_key]["shift"] = shift
            save_records(st.session_state.triage_records)
            st.session_state.editing_key = None
            st.success("保存しました")
            st.rerun()
    with col_gen:
        if st.button("🖨️ 台帳を生成", type="primary", use_container_width=True):
            res["decision"] = decision
            data["kanji"] = e_kanji; data["kana"] = e_kana; data["age"] = e_age
            data["gender"] = "1" if "男" in e_gender_sel else ("2" if "女" in e_gender_sel else "")
            data["complaint"] = e_complaint
            data["jcs"]=e_jcs; data["bp_s"]=e_bps; data["bp_d"]=e_bpd
            data["hr"]=e_hr; data["rr"]=e_rr; data["spo2"]=e_spo2; data["bt"]=e_bt
            data["o2_flow"]=e_o2_flow; data["o2_device"]=e_o2_device; data["spo2_before"]=e_spo2_b
            records[editing_key]["data"] = data
            records[editing_key]["res"] = res
            records[editing_key]["free_note"] = free_note
            records[editing_key]["case_no"] = case_no
            records[editing_key]["recorder"] = e_recorder
            records[editing_key]["origin"] = e_origin
            records[editing_key]["history_yn"] = e_history_yn
            records[editing_key]["history_dept"] = e_history_dept
            records[editing_key]["shift"] = shift
            save_records(st.session_state.triage_records)
            result = render_triage(data, e_recorder, e_origin, shift, e_history_yn, e_history_dept,
                                   decision, res, case_no, free_note)
            st.image(result, use_container_width=True)
            buf = io.BytesIO()
            result.save(buf, format="JPEG", quality=95)
            components.html(make_print_widget(result, "ed_print"), height=38)
    with col_cancel:
        if st.button("キャンセル", use_container_width=True):
            st.session_state.editing_key = None
            st.rerun()
    st.stop()


# ===== 保存済み患者一覧 =====
records = st.session_state.triage_records

# クエリパラメータでボタンアクション処理
params = st.query_params
if "action" in params and "key" in params:
    action = params["action"]
    target = params["key"]
    if action == "edit" and target in records:
        st.session_state.editing_key = target
    elif action == "del" and target in records:
        del st.session_state.triage_records[target]
        save_records(st.session_state.triage_records)
        if st.session_state.editing_key == target:
            st.session_state.editing_key = None
    st.query_params.clear()
    st.rerun()

if records:
    st.subheader("📋 保存済み患者")
    st.markdown("""<style>
    [data-testid="stHorizontalBlock"]>div{min-width:0!important}
    [data-testid="stHorizontalBlock"] button{padding:2px 8px!important;font-size:12px!important;min-height:28px!important;height:28px!important;line-height:1!important}
    </style>""", unsafe_allow_html=True)
    # case_noでソート
    sorted_records = sorted(records.items(), key=lambda x: (
            *get_shift_identity(x[1].get("data",{}).get("dt_str","")),
            int(x[1].get("case_no", 99))
        ))
    current_group = None
    for key, rec in sorted_records:
        # シフトグループヘッダー
        sd, st_type = get_shift_identity(rec.get("data",{}).get("dt_str",""))
        group_key = (sd, st_type)
        if group_key != current_group:
            current_group = group_key
            icon = "🌕" if st_type == "日勤" else "🌑"
            st.markdown(
                f"<div style='margin:10px 0 2px 0;font-size:13px;font-weight:bold;"
                f"color:#888;border-bottom:1px solid #444;padding-bottom:2px'>"
                f"{icon} {sd} {st_type}</div>",
                unsafe_allow_html=True)
        rec_res = rec.get("res", {})
        if rec_res.get("decision") == "不応需":
            outcome_str = "不応需"
        else:
            outcome_str = rec_res.get("out", "未記入")
        dt_str = rec.get("data", {}).get("dt_str", "")
        case_no_disp = rec.get("case_no", "?")
        kana = rec.get("data", {}).get("kana", "").replace("　","").replace(" ","")
        display_name = kana if kana else key.replace("　","").replace(" ","")
        ci, ce, cd = st.columns([6, 1, 1])
        with ci:
            st.markdown(
                f"<div style='font-size:14px;padding:3px 0'>"
                f"<b>{case_no_disp}.{display_name}</b> {dt_str} 転帰:{outcome_str}</div>",
                unsafe_allow_html=True)
        with ce:
            if st.button("編集", key=f"edit_{key}"):
                st.session_state.editing_key = key
                st.rerun()
        with cd:
            if st.button("削除", key=f"del_{key}"):
                del st.session_state.triage_records[key]
                save_records(st.session_state.triage_records)
                if st.session_state.editing_key == key:
                    st.session_state.editing_key = None
                st.rerun()

    # 台帳一括生成ボタン
    if st.button("🖨️ 全患者の台帳を一括生成", type="primary", use_container_width=True):
        all_records = st.session_state.triage_records
        if all_records:
            # case_no順にソート
            sorted_bulk = sorted(all_records.items(), key=lambda x: (
            *get_shift_identity(x[1].get("data",{}).get("dt_str","")),
            int(x[1].get("case_no", 99))
        ))
            all_images = []  # Gmail添付用
            for key, rec in sorted_bulk:
                data = rec["data"]
                shift = rec.get("shift","夜勤")
                recorder = rec.get("recorder","前川")
                origin = rec.get("origin","中央")
                history_yn = rec.get("history_yn","無")
                history_dept = rec.get("history_dept","")
                decision = rec.get("decision","応需")
                res = rec.get("res",{})
                case_no = rec.get("case_no", 1)
                free_note = rec.get("free_note","")
                kana = data.get("kana","").strip()
                display = kana if kana else key
                shift_date, _ = get_shift_identity(data.get("dt_str",""))
                st.write(f"**{case_no}. {display}**")
                result = render_triage(data, recorder, origin, shift, history_yn, history_dept,
                                       decision, res, case_no, free_note)
                st.image(result, use_container_width=True)
                buf = io.BytesIO()
                result.save(buf, format="JPEG", quality=95)
                img_bytes = buf.getvalue()
                # ファイル名に患者名を含めない（個人情報保護）
                _age  = data.get("age","")
                _sex  = "M" if data.get("gender")=="1" else ("F" if data.get("gender")=="2" else "")
                try:
                    _dt_raw = data.get("dt_str","")
                    _dp = _dt_raw.split("（")[0].strip(); _tp = _dt_raw.split("）")[-1].strip() if "）" in _dt_raw else ""
                    _m,_d = _dp.split("/"); _hm = _tp.replace(":","")
                    from datetime import date as _d2; _y = _d2.today().year
                    _dt = f"{_y}{int(_m):02d}{int(_d):02d}_{_hm[:4]}"
                except: _dt = ""
                filename = f"triage_{case_no:02d}_{_dt}_{_age}{_sex}.jpg"
                all_images.append((filename, img_bytes, shift_date, shift))
            # セッションに保存
            st.session_state.bulk_images = all_images
            st.success(f"✅ {len(all_images)}件の台帳を生成しました。")

    # 一括PDFダウンロード（日勤・夜勤別）
    if st.session_state.get("bulk_images"):
        try:
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.utils import ImageReader
            from PIL import Image as PILImage
            from datetime import date

            A4_W, A4_H = A4
            MARGIN = 28
            avail_w = A4_W - 2*MARGIN
            avail_h = A4_H - 2*MARGIN

            def make_pdf(img_list):
                pdf_buf = io.BytesIO()
                c = rl_canvas.Canvas(pdf_buf, pagesize=A4)
                for img_bytes in img_list:
                    img = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
                    iw, ih = img.size
                    scale = min(avail_w/iw, avail_h/ih)
                    pw, ph = iw*scale, ih*scale
                    x = MARGIN + (avail_w - pw) / 2
                    y = MARGIN + (avail_h - ph) / 2
                    _ibuf = io.BytesIO()
                    img.save(_ibuf, format="JPEG", quality=95)
                    _ibuf.seek(0)
                    c.drawImage(ImageReader(_ibuf), x, y, width=pw, height=ph)
                    c.showPage()
                c.save()
                pdf_buf.seek(0)
                return pdf_buf.getvalue()

            # 日勤・夜勤ごとにグループ化
            from itertools import groupby
            bulk = st.session_state.bulk_images
            # (shift_date, shift) でグループ化
            # bulk要素が3要素(古い形式)の場合に対応
            def get_shift_key(item):
                if len(item) >= 4:
                    return (item[2], item[3])  # (shift_date, shift)
                return ("", "")

            groups = {}
            for item in bulk:
                k = get_shift_key(item)
                groups.setdefault(k, []).append(item[1])  # img_bytes

            sorted_groups = sorted(groups.items())
            if len(sorted_groups) > 1:
                pdf_cols = st.columns(len(sorted_groups))
            else:
                pdf_cols = None

            for ci, ((sdate, sshift), imgs) in enumerate(sorted_groups):
                pdf_bytes_out = make_pdf(imgs)
                label = f"{sdate} {sshift}" if sdate else sshift
                fname = f"triage_{sdate.replace('/','')}_{sshift}_{date.today().strftime('%Y%m%d')}.pdf"
                btn_label = f"📄 {label} PDF（{len(imgs)}件）"
                if pdf_cols:
                    with pdf_cols[ci]:
                        st.download_button(btn_label, pdf_bytes_out, fname, "application/pdf",
                                           use_container_width=True, type="primary",
                                           key=f"pdf_{ci}")
                else:
                    st.download_button(btn_label, pdf_bytes_out, fname, "application/pdf",
                                       use_container_width=True, type="primary",
                                       key=f"pdf_{ci}")
        except Exception as e:
            st.error(f"PDF生成エラー: {e}")

    st.divider()
    # 一括削除ボタン（確認あり）
    if "confirm_clear" not in st.session_state:
        st.session_state.confirm_clear = False

    if not st.session_state.confirm_clear:
        if st.button("🗑️ 保存済み患者を一括削除", use_container_width=True):
            st.session_state.confirm_clear = True
            st.rerun()
    else:
        st.warning("⚠️ 保存済み患者を全員削除します。この操作は取り消せません。")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ はい、全削除する", type="primary", use_container_width=True):
                st.session_state.triage_records = {}
                save_records({})
                st.session_state.confirm_clear = False
                st.rerun()
        with c2:
            if st.button("❌ キャンセル", use_container_width=True):
                st.session_state.confirm_clear = False
                st.rerun()

    st.divider()

# ===== 勤務表リーダー設定 =====
with st.expander("📅 勤務表リーダー設定", expanded=False):
    from datetime import timezone as _stz, timedelta as _std
    from leader_schedule import parse_kinmuhyo_pdf as parse_schedule_pdf, save_schedule, load_schedule
    _jst_now2 = __import__('datetime').datetime.now(_stz(_std(hours=9)))
    _today2 = _jst_now2.date()
    _shift_now2 = detect_shift(f"{_today2.month}/{_today2.day}（）{_jst_now2.hour:02d}:{_jst_now2.minute:02d}")
    _leader_now2 = get_leader(_today2, _shift_now2)
    if _leader_now2:
        st.info(f"👤 本日 {_today2.month}/{_today2.day} {_shift_now2}のリーダー: **{_leader_now2}**")
    else:
        st.warning(f"⚠️ 本日 {_today2.month}/{_today2.day} {_shift_now2}のリーダーが未設定です")
    # PDFアップロード
    pdf_file = st.file_uploader("📄 勤務表PDFをアップロード（毎月20日頃に更新）",
                                 type=["pdf"], key="sched_pdf_upload",
                                 label_visibility="collapsed")
    if pdf_file:
        with st.spinner("勤務表を解析中..."):
            result = parse_schedule_pdf(pdf_file.read())
        if result:
            sched = load_schedule()
            months = set(k[0] for k in result.keys())
            sched = {k:v for k,v in sched.items() if k[0] not in months}
            sched.update(result)
            save_schedule(sched)
            st.success(f"✅ {len(result)}日分を更新しました")
            st.rerun()
        else:
            st.error("⚠️ 解析できませんでした")
    st.caption("PDFアップロード後に内容を確認・修正できます（日勤=〇*、夜勤=●*）")
    schedule_editor_widget("triage_sched")
