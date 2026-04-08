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

st.set_page_config(page_title="トリアージ台帳自動作成", layout="centered")
st.title("🚑 トリアージ台帳自動作成")

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
def detect_shift(dt_str):
    """8:30-16:30 = 日勤、それ以外 = 夜勤"""
    try:
        # dt_strは "4/8（水）17:40" 形式
        time_part = dt_str.split("）")[-1].strip()
        h, m = map(int, time_part.split(":"))
        minutes = h * 60 + m
        if 8 * 60 + 30 <= minutes < 16 * 60 + 30:
            return "日勤"
        return "夜勤"
    except Exception:
        return "夜勤"

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
        "bp_s": safe(19),
        "bp_d": safe(20),
        "hr": safe(21),
        "rr": safe(22),
        "bt": safe(23),
        "spo2": safe(24),
        "team_name": team_name,
        "items": items,
    }

# ===== テンプレート描画 =====
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
        dept = history_dept.rstrip("科")
        d.text((1130, 150), dept, font=f24, fill="black")
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
    d.text((1120, 705), data["jcs"], font=f28, fill="black")
    d.text((1060, 775), data["rr"], font=f28, fill="black")
    d.text((1060, 845), data["hr"], font=f28, fill="black")
    d.text((1060, 915), f"{data['bp_s']}/{data['bp_d']}", font=f28, fill="black")
    d.text((1060, 978), data["spo2"], font=f28, fill="black")
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
        elif res.get("out") == "帰宅":
            draw_maru(d, (340, 1461), r=16)

        # 病棟
        ward_map = {"4東": (784, 1466), "HCU": (861, 1466), "ICU": (943, 1466)}
        if res.get("ward") in ward_map:
            draw_maru(d, ward_map[res["ward"]], r=18)
        elif res.get("ward") == "その他" and res.get("ward_other"):
            d.text((840, 1480), res["ward_other"], font=f18, fill="black")

        # 主科
        main_map = {"臨研": (1083, 1445), "救急科": (1095, 1480)}
        if res.get("main") in main_map:
            draw_maru(d, main_map[res["main"]], r=18)
        elif res.get("main") == "その他":
            draw_maru(d, (1095, 1480), r=18)
            if res.get("main_other"):
                d.text((1095, 1500), res["main_other"].rstrip("科"), font=f18, fill="black")
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

    return base

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
    rows_html = ""
    for idx, (key, rec) in enumerate(list(records.items()), start=1):
        outcome_str = rec.get("res", {}).get("out", "未記入")
        dt_str = rec.get("data", {}).get("dt_str", "")
        name = key.replace("　", "").replace(" ", "")
        edit_url = "?" + urllib.parse.urlencode({"action":"edit","key":key})
        del_url  = "?" + urllib.parse.urlencode({"action":"del", "key":key})
        rows_html += (
            f'<tr>'
            f'<td class="nm" style="white-space:nowrap;font-size:13px;padding:4px 3px"><b>{idx}.{name}</b></td>'
            f'<td class="dt" style="white-space:nowrap;font-size:12px;padding:4px 2px">{dt_str}</td>'
            f'<td class="dt" style="white-space:nowrap;font-size:12px;padding:4px 2px">{outcome_str}</td>'
            f'<td style="padding:4px 2px"><a href="{edit_url}" style="background:#1a7340;color:white;padding:3px 8px;border-radius:4px;font-size:12px;text-decoration:none;white-space:nowrap">更新</a></td>'
            f'<td style="padding:4px 2px"><a href="{del_url}" style="background:#a33;color:white;padding:3px 8px;border-radius:4px;font-size:12px;text-decoration:none;white-space:nowrap">削除</a></td>'
            f'</tr>'
        )
    html = f'''
<style>
  .pt td {{ border:none; }}
  .pt .nm {{ color: #111; }}
  .pt .dt {{ color: #444; }}
  @media (prefers-color-scheme: dark) {{
    .pt .nm {{ color: #fff; }}
    .pt .dt {{ color: #ccc; }}
  }}
</style>
<table class="pt" style="width:100%;border-collapse:collapse">{rows_html}</table>
'''
    components.html(html, height=len(records)*36+20, scrolling=False)
    st.divider()

# ===== 転帰更新モード =====
editing_key = st.session_state.editing_key
if editing_key and editing_key in records:
    rec = records[editing_key]
    st.subheader(f"✏️ 転帰更新：{editing_key}")
    data = rec["data"]
    res = dict(rec.get("res", {}))
    case_no = rec.get("case_no", 1)
    shift = rec.get("shift", "日勤")
    recorder = rec.get("recorder", "前川")
    origin = rec.get("origin", "中央")
    history_yn = rec.get("history_yn", "無")
    history_dept = rec.get("history_dept", "")
    free_note = rec.get("free_note", "")

    st.info(f"🕐 受付時刻: {data['dt_str']}　勤務帯: **{shift}**")
    decision = st.radio("判定", ["応需", "不応需"], horizontal=True,
                        index=0 if res.get("decision","応需")=="応需" else 1)
    if decision == "応需":
        res["init"] = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"],
                                   index=["当直医","救急科","その他"].index(res.get("init","当直医")))
        if res["init"] == "その他":
            res["init_other"] = st.text_input("初期対応科名", value=res.get("init_other",""))
        res["out"] = st.selectbox("最終転帰", ["入院", "帰宅", "その他"],
                                  index=["入院","帰宅","その他"].index(res.get("out","入院")))
        if res["out"] == "入院":
            res["ward"] = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"],
                                       index=["4東","HCU","ICU","その他"].index(res.get("ward","4東")))
            if res["ward"] == "その他":
                res["ward_other"] = st.text_input("病棟名", value=res.get("ward_other",""))
            res["main"] = st.selectbox("主科", ["臨研", "救急科", "その他"],
                                       index=["臨研","救急科","その他"].index(res.get("main","臨研")))
            if res["main"] == "その他":
                res["main_other"] = st.text_input("主科名", value=res.get("main_other",""))
    free_note = st.text_area("自由記載", value=free_note, height=80)

    col_gen, col_cancel = st.columns(2)
    with col_gen:
        if st.button("🖨️ 台帳を生成", type="primary", use_container_width=True):
            res["decision"] = decision
            records[editing_key]["res"] = res
            records[editing_key]["free_note"] = free_note
            save_records(st.session_state.triage_records)
            result = render_triage(data, recorder, origin, shift, history_yn, history_dept,
                                   decision, res, case_no, free_note)
            st.image(result, use_container_width=True)
            buf = io.BytesIO()
            result.save(buf, format="JPEG", quality=95)
            st.download_button("📥 台帳を保存", buf.getvalue(),
                               f"triage_{data['kanji']}.jpg", "image/jpeg")
    with col_cancel:
        if st.button("キャンセル", use_container_width=True):
            st.session_state.editing_key = None
            st.rerun()
    st.stop()

# ===== 新規患者入力 =====
st.subheader("🆕 新規患者")
uploaded = st.file_uploader(
    "📷 画像を選択（スクリーンショットまたはカメラ撮影）",
    type=["png", "jpg", "jpeg"],
    help="カメラ撮影時：OSの「QRコード認識できません」メッセージは無視してそのまま撮影→アップロードしてください",
    key=f"uploader_{st.session_state.uploader_key}"
)

# アップロードされたファイルのバイトをセッションに保持（モバイルでのリロード対策）
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
                import io
                raw = decode_qr(io.BytesIO(st.session_state.uploaded_bytes))
        if raw is None:
            st.error("❌ QRコードが認識できませんでした。\n\n**対処法：**\n- QRコードを画面の中央に大きく写して再撮影\n- 明るい場所でピントを合わせてから撮影\n- スクリーンショット画像を使用")
        else:
            st.session_state.triage_raw = raw
            st.success("✅ QRコード読み取り成功！")

    raw = st.session_state.triage_raw

    if raw:
        data = parse_qr(raw)

        # 受付時刻から勤務帯を自動判定
        shift = detect_shift(data["dt_str"])
        st.info(f"🕐 受付時刻: {data['dt_str']}　→ 勤務帯: **{shift}**（8:30-16:30=日勤、それ以外=夜勤）")

        with st.expander("🔍 QRデータ確認（デバッグ用）", expanded=False):
            st.write(f"**救急隊名候補（自動）:** `{data['team_name']}` ← 正しくない場合は下のリストから正しいインデックスを確認してください")
            for i, v in enumerate(data["items"]):
                label = ""
                if i == 1: label = "← 依頼日時"
                elif i == 4: label = "← 氏名"
                elif i == 5: label = "← 性別"
                elif i == 8: label = "← 主訴"
                elif i == 9: label = "← 経過等"
                elif i == 13: label = "← 生年月日"
                elif i == 14: label = "← 年齢"
                elif i == 15: label = "← JCS"
                elif i == 19: label = "← BP(上)"
                elif i == 20: label = "← BP(下)"
                elif i == 21: label = "← HR"
                elif i == 22: label = "← RR"
                elif i == 23: label = "← BT"
                elif i == 24: label = "← SpO2"
                st.text(f"[{i:2d}] {v[:80]}  {label}")

        st.subheader("台帳情報の入力")

        col1, col2 = st.columns(2)
        with col1:
            case_no = st.selectbox("No.", list(range(1, 16)))
            recorder = st.selectbox("記載者", ["前川", "森木", "小舘", "遠藤"])
            origin = st.text_input("依頼元（救急隊）", value=data.get("team_name", "中央"))
            history_yn = st.radio("受診歴", ["無", "有"], horizontal=True)
        with col2:
            history_dept = ""
            if history_yn == "有":
                history_dept = st.text_input("受診科名")
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
                res["ward"] = st.selectbox("病棟", ["（後で入力）", "4東", "HCU", "ICU", "その他"])
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
                st.session_state.triage_raw = None
                st.session_state.uploader_key += 1
                st.session_state.uploaded_bytes = None
                st.success(f"✅ {key}（{shift}）のデータを保存しました。")
                st.rerun()
        with col_gen:
            if st.button("🖨️ 今すぐ台帳を生成", type="primary", use_container_width=True):
                result = render_triage(data, recorder, origin, shift, history_yn, history_dept,
                                       decision, res, case_no, free_note)
                st.image(result, use_container_width=True)
                buf = io.BytesIO()
                result.save(buf, format="JPEG", quality=95)
                st.download_button("📥 台帳を保存", buf.getvalue(),
                                   f"triage_{data['kanji']}.jpg", "image/jpeg")
