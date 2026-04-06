import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode
import os
import textwrap
from datetime import datetime

# ============================================================
#  日本語フォント取得
# ============================================================
def get_font(size):
    paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/fonts-japanese-gothic.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

# ============================================================
#  QR データ解析
# ============================================================
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode("utf-8")
        items = decoded.split(",")

        dt = datetime.strptime(items[1], "%Y/%m/%d %H:%M:%S")
        weeks = ["月", "火", "水", "木", "金", "土", "日"]

        name_raw = items[4]
        kanji, kana = (
            name_raw.split("θ", 1) if "θ" in name_raw else (name_raw, "")
        )

        return {
            "month": str(dt.month),
            "day": str(dt.day),
            "weekday": weeks[dt.weekday()],
            "hour": f"{dt.hour:02}",
            "minute": f"{dt.minute:02}",
            "kanji": kanji.strip().replace("　", " "),
            "kana": kana.strip().replace("　", " "),
            "gender": items[5],        # 1:男, 2:女
            "history": items[8],       # 経過等
            "complaint": items[9],     # 主訴
            "birth": items[11],        # YYYYMMDD
            "age": items[12],
            "jcs": items[13],
            "bp_s": items[17],
            "bp_d": items[18],
            "pr": items[19],
            "rr": items[20],
            "bt": items[21],
            "spo2": items[22],
        }
    except Exception as e:
        st.error(f"データ解析失敗: {e}")
        return None

# ============================================================
#  赤丸（◯）描画
# ============================================================
def draw_maru(draw, xy, r=40):
    x, y = xy
    draw.ellipse((x - r, y - r, x + r, y + r), outline="red", width=10)

# ============================================================
#  座標定数（300 dpi テンプレート基準 – ピクセル解析済み）
# ============================================================
# --- グリッド線 ---
# 水平: 226,276,405,556,657,759,961,1061,1263,1364,1465,1567,1668,1768,1870,2173,2324,2374,2526,2930,3233
# 垂直: 211,405,1047,1256,1465,1624,1830,2248

# 依頼日時行 (Y=405-556)  プリント済記号: ／@548 （@700 ）@784 ：@916
POS_MONTH  = (455, 445)
POS_DAY    = (580, 445)
POS_WDAY   = (720, 445)
POS_HOUR   = (820, 445)
POS_MINUTE = (935, 445)

# 依頼元 (X=1047-1256 セル下部、「救急隊」の左)
POS_ORIGIN = (1060, 500)

# 受診歴  有の中心=1910,480  無の中心=2180,480
POS_HISTORY_YES = (1910, 480)
POS_HISTORY_NO  = (2180, 480)
# 有の場合の科名テキスト位置
POS_HISTORY_DEPT = (1960, 445)

# 患者名
POS_KANA  = (415, 562)
POS_KANJI = (415, 598)

# 生年月日 (Y=556-657)  年セル X=1465-1624, 月 X=1624-1830, 日 X=1830-2248
POS_BIRTH_Y = (1525, 580)   # 年（やや小さいフォント）
POS_BIRTH_M = (1640, 578)
POS_BIRTH_D = (1850, 578)

# 年齢 (Y=657-759)
POS_AGE = (1475, 680)

# 性別  男center=1980, 女center=2100, Y=708
POS_MALE   = (1980, 708)
POS_FEMALE = (2100, 708)

# 主訴 (Y=759-961, テキスト X>405)
POS_COMPLAINT = (420, 830)

# 経過等 (Y=961-2173, テキスト X>220, 幅〜820px)
POS_HISTORY_TEXT = (230, 1050)
HISTORY_LINE_HEIGHT = 55
HISTORY_WRAP_WIDTH = 32  # 全角文字数

# バイタルサイン (X=1845, 各行の Y)
VITAL_X = 1845
VITAL_Y = {
    "jcs":  1290,   # Y=1263-1364
    "rr":   1390,   # Y=1364-1465
    "hr":   1492,   # Y=1465-1567
    "bp":   1593,   # Y=1567-1668
    "spo2": 1695,   # Y=1668-1768
    "bt":   1795,   # Y=1768-1870
}

# 判定エリア
# 応需(Y_center=2260) / 不応需(Y_center=2360)  左列 X_center=265
POS_OUJI    = (265, 2260)
POS_FUOUJI  = (265, 2360)

# 初期対応した科  当直医center=1167, 救急科center=1575, Y=2260
POS_TOCHOKU   = (1167, 2260)
POS_KYUKYU_INIT = (1575, 2260)

# 最終転帰  入院Y=2400, 帰宅Y=2450  X=770
POS_NYUIN   = (770, 2400)
POS_KITAKU  = (770, 2450)

# 病棟  4東=1151, HCU=1350, ICU=1500  Y=2480
POS_4EAST = (1151, 2480)
POS_HCU   = (1350, 2480)
POS_ICU   = (1500, 2480)

# 主科  臨研=1892, 救急科=1913 Y=2400/2445
POS_RINKEN      = (1892, 2400)
POS_KYUKYU_MAIN = (1913, 2445)

# 不応需理由 Y中心（8行）
FUOUJI_REASON_Y = [2553, 2603, 2653, 2703, 2753, 2803, 2853, 2902]
FUOUJI_REASON_X = 230  # 左寄りに◯

# ============================================================
#  メイン UI
# ============================================================
st.set_page_config(page_title="台帳作成システム", layout="centered")
st.title("🚑 市立札幌病院 トリアージ台帳")

uploaded_file = st.file_uploader(
    "QRコードのスクリーンショットを選択", type=["png", "jpg", "jpeg"]
)

if uploaded_file:
    img = Image.open(uploaded_file)

    with st.spinner("QRコードをスキャン中..."):
        decoded = decode(img)
        if not decoded:
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            decoded = decode(gray)
        if not decoded:
            sharp = cv2.detailEnhance(np.array(img), sigma_s=10, sigma_r=0.15)
            decoded = decode(sharp)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode("utf-8"))
        if data:
            st.success(f"読込成功: {data['kanji']} 様")

            # ------ UI 入力 ------
            st.subheader("台帳情報の入力")
            col1, col2 = st.columns(2)
            with col1:
                origin = st.text_input("依頼元（救急隊）", value="中央").replace("救急隊", "").strip()
                history_yn = st.radio("受診歴", ["無", "有"], index=0, horizontal=True)
            with col2:
                history_dept = st.text_input("受診科名（有の場合）")
                decision = st.radio("判定", ["応需", "不応需"], index=0, horizontal=True)

            res = {}
            if decision == "応需":
                res["init"] = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                if res["init"] == "その他":
                    res["init_other"] = st.text_input("初期対応科名")
                res["out"] = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                if res["out"] == "入院":
                    res["ward"] = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"])
                    res["main"] = st.selectbox("主科", ["臨研", "救急科", "その他"])
                    if res["main"] == "その他":
                        res["main_other"] = st.text_input("主科名")
            else:
                reasons = [
                    "1. 緊急性なし",
                    "2. ベッド満床",
                    "3. 既定の応需不可症例",
                    "4. 対応可能な医師不在",
                    "5. 緊急手術制限中",
                    "6-A. 医師処置中につき対応困難",
                    "6-B. 看護師処置中につき対応困難",
                    "7. その他",
                ]
                res["reason"] = st.selectbox("不応需理由", reasons)

            # ------ 台帳生成 ------
            if st.button("台帳を生成する", type="primary"):
                with st.spinner("作成中..."):
                    pages = convert_from_path("トリアージ台帳.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    d = ImageDraw.Draw(base)

                    f_s  = get_font(30)
                    f_sm = get_font(36)
                    f_m  = get_font(42)
                    f_l  = get_font(68)

                    # --- 依頼日時 ---
                    d.text(POS_MONTH,  data["month"],  font=f_m, fill="black")
                    d.text(POS_DAY,    data["day"],    font=f_m, fill="black")
                    d.text(POS_WDAY,   data["weekday"],font=f_m, fill="black")
                    d.text(POS_HOUR,   data["hour"],   font=f_m, fill="black")
                    d.text(POS_MINUTE, data["minute"], font=f_m, fill="black")

                    # --- 依頼元 ---
                    d.text(POS_ORIGIN, origin, font=f_m, fill="black")

                    # --- 受診歴 ---
                    if history_yn == "有":
                        draw_maru(d, POS_HISTORY_YES)
                        if history_dept:
                            d.text(POS_HISTORY_DEPT, history_dept, font=f_m, fill="black")
                    else:
                        draw_maru(d, POS_HISTORY_NO)

                    # --- 患者名 ---
                    d.text(POS_KANA,  data["kana"],  font=f_s, fill="black")
                    d.text(POS_KANJI, data["kanji"], font=f_l, fill="black")

                    # --- 生年月日 ---
                    b = data["birth"]
                    d.text(POS_BIRTH_Y, b[:4],  font=f_sm, fill="black")
                    d.text(POS_BIRTH_M, b[4:6], font=f_m,  fill="black")
                    d.text(POS_BIRTH_D, b[6:],  font=f_m,  fill="black")

                    # --- 年齢 ---
                    d.text(POS_AGE, data["age"], font=f_m, fill="black")

                    # --- 性別 ---
                    if data["gender"] == "2" or "女" in data["gender"]:
                        draw_maru(d, POS_FEMALE, r=35)
                    else:
                        draw_maru(d, POS_MALE, r=35)

                    # --- 主訴 ---
                    d.text(POS_COMPLAINT, data["complaint"], font=f_m, fill="black")

                    # --- 経過等（自動改行）---
                    lines = textwrap.wrap(data["history"], width=HISTORY_WRAP_WIDTH)
                    for i, line in enumerate(lines):
                        d.text(
                            (POS_HISTORY_TEXT[0], POS_HISTORY_TEXT[1] + i * HISTORY_LINE_HEIGHT),
                            line,
                            font=f_m,
                            fill="black",
                        )

                    # --- バイタルサイン ---
                    d.text((VITAL_X, VITAL_Y["jcs"]),  data["jcs"],  font=f_m, fill="black")
                    d.text((VITAL_X, VITAL_Y["rr"]),   data["rr"],   font=f_m, fill="black")
                    d.text((VITAL_X, VITAL_Y["hr"]),   data["pr"],   font=f_m, fill="black")
                    bp = f"{data['bp_s']}/{data['bp_d']}"
                    d.text((VITAL_X, VITAL_Y["bp"]),   bp,           font=f_m, fill="black")
                    d.text((VITAL_X, VITAL_Y["spo2"]), data["spo2"], font=f_m, fill="black")
                    d.text((VITAL_X, VITAL_Y["bt"]),   data["bt"],   font=f_m, fill="black")

                    # --- 判定 ---
                    if decision == "応需":
                        draw_maru(d, POS_OUJI, r=48)

                        # 初期対応した科
                        if res["init"] == "当直医":
                            draw_maru(d, POS_TOCHOKU, r=50)
                        elif res["init"] == "救急科":
                            draw_maru(d, POS_KYUKYU_INIT, r=50)

                        # 最終転帰
                        if res["out"] == "入院":
                            draw_maru(d, POS_NYUIN, r=40)
                            # 病棟
                            ward_pos = {"4東": POS_4EAST, "HCU": POS_HCU, "ICU": POS_ICU}
                            if res.get("ward") in ward_pos:
                                draw_maru(d, ward_pos[res["ward"]], r=35)
                            # 主科
                            if res.get("main") == "臨研":
                                draw_maru(d, POS_RINKEN, r=35)
                            elif res.get("main") == "救急科":
                                draw_maru(d, POS_KYUKYU_MAIN, r=35)
                        elif res["out"] == "帰宅":
                            draw_maru(d, POS_KITAKU, r=40)

                    else:  # 不応需
                        draw_maru(d, POS_FUOUJI, r=48)
                        # 理由番号を取得して対応するY座標に◯
                        reason_labels = ["1", "2", "3", "4", "5", "6-A", "6-B", "7"]
                        reason_key = res["reason"].split(".")[0].strip()
                        if reason_key in reason_labels:
                            idx = reason_labels.index(reason_key)
                            draw_maru(d, (FUOUJI_REASON_X, FUOUJI_REASON_Y[idx]), r=30)

                    # --- 表示・保存 ---
                    st.image(base, use_container_width=True)
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button(
                        "📥 台帳を保存",
                        buf.getvalue(),
                        f"triage_{data['kanji']}.jpg",
                        "image/jpeg",
                    )
    else:
        st.error(
            "QRコードが見つかりません。\n画像を拡大するか、明るい場所で撮り直してください。"
        )
