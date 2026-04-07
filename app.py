import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pyzbar.pyzbar as pyzbar
import base64
import io
import os
from datetime import datetime

st.set_page_config(page_title="トリアージ台帳自動作成", layout="centered")
st.title("🚑 トリアージ台帳自動作成")

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
    file_bytes = np.frombuffer(uploaded.read(), np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    if img is None:
        return None
    # コントラスト強調
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    for scale in [1.0, 0.75, 0.5, 1.5]:
        h, w = gray.shape
        resized = cv2.resize(gray, (int(w * scale), int(h * scale)))
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(resized)
        for proc in [enhanced, resized, cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]]:
            decoded = pyzbar.decode(proc)
            if decoded:
                return decoded[0].data.decode("utf-8")
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
        "items": items,
    }

# ===== テンプレート描画 =====
def render_triage(data, recorder, origin, history_yn, history_dept, decision, res, case_no):
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
    d.text((no_x, 48), no_str, font=f_no, fill="black")

    # ===== 記載者（V=911-1176, Y=55, 中央寄せ） =====
    cell_w = 1176 - 911
    tw = getlength(recorder, f44)
    kx_rec = 911 + (cell_w - tw) // 2
    d.text((kx_rec, 55), recorder, font=f44, fill="black")

    # ===== 依頼日時 =====
    d.text((155, 145), data["dt_str"], font=f36, fill="black")

    # ===== 依頼元（救急隊名, V=676-911） =====
    origin_clean = origin.replace("救急隊", "").strip()
    d.text((690, 148), origin_clean, font=f28, fill="black")

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

    # ===== 生年月日（右寄せ） =====
    # 年ラベルX=1038（911-1043列）、月ラベルX=1145、日ラベルX=1279
    for val, label_x in [(data["birth_y"], 1038), (data["birth_m"], 1145), (data["birth_d"], 1279)]:
        if val:
            tw = getlength(val, f24)
            d.text((label_x - tw - 4, 315), val, font=f24, fill="black")

    # ===== 年齢（年齢ラベル(~X755)の右, 歳ラベル(~X870)の前） =====
    d.text((800, 315), data["age"], font=f28, fill="black")

    # ===== 性別 =====
    if data["gender"] == "1":
        draw_maru(d, (1008, 322), r=18)
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
        d.text((150, 385 + i * 32), ln, font=f28, fill="black")

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
        reason_y = [1543, 1573, 1603, 1633, 1663, 1693, 1725, 1785]
        rk = res.get("reason", "")
        for label, ry in zip(reason_labels, reason_y):
            if rk and rk.split(".")[0].strip() == label.split(".")[0].strip():
                draw_maru(d, (148, ry), r=16)
                break

    return base

# ===== メインUI =====
uploaded = st.file_uploader("📷 スクリーンショットをアップロード", type=["png", "jpg", "jpeg"])

if uploaded:
    raw = decode_qr(uploaded)
    if raw is None:
        st.error("QRコードが見つかりません。画像を拡大するか、明るい場所で撮り直してください。")
    else:
        data = parse_qr(raw)

        with st.expander("🔍 QRデータ確認（デバッグ用）", expanded=False):
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
            origin = st.text_input("依頼元（救急隊）", value="中央")
            history_yn = st.radio("受診歴", ["無", "有"], horizontal=True)
        with col2:
            history_dept = ""
            if history_yn == "有":
                history_dept = st.text_input("受診科名")
            decision = st.radio("判定", ["応需", "不応需"], horizontal=True)

        complaint_edit = st.text_input("主訴（編集可）", value=data["complaint"])
        data["complaint"] = complaint_edit

        res = {}
        if decision == "応需":
            res["init"] = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
            if res["init"] == "その他":
                res["init_other"] = st.text_input("初期対応科名")
            res["out"] = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
            if res["out"] == "入院":
                res["ward"] = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"])
                if res["ward"] == "その他":
                    res["ward_other"] = st.text_input("病棟名")
                res["main"] = st.selectbox("主科", ["臨研", "救急科", "その他"])
                if res["main"] == "その他":
                    res["main_other"] = st.text_input("主科名")
        else:
            res["reason"] = st.selectbox("不応需理由", [
                "1. 緊急性なし",
                "2. ベッド満床",
                "3. 既定の応需不可",
                "4. 対応可能な医師不在",
                "5. 緊急手術制限中",
                "6-A. 医師処置中",
                "6-B. 看護師処置中",
                "7. その他",
            ])

        if st.button("🖨️ 台帳を生成", type="primary"):
            result = render_triage(data, recorder, origin, history_yn, history_dept, decision, res, case_no)
            st.image(result, use_container_width=True)
            buf = io.BytesIO()
            result.save(buf, format="JPEG", quality=95)
            st.download_button(
                "📥 台帳を保存",
                buf.getvalue(),
                f"triage_{data['kanji']}.jpg",
                "image/jpeg"
            )
