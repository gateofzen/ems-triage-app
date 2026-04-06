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

def decode_qr_raw(b64_string):
    decoded = base64.b64decode(b64_string).decode("utf-8")
    return decoded.split(",")

def parse_ems_qr(items):
    try:
        dt = datetime.strptime(items[1], "%Y/%m/%d %H:%M:%S")
        weeks = ["月", "火", "水", "木", "金", "土", "日"]
        name_raw = items[4]
        kanji, kana = (
            name_raw.split("θ", 1) if "θ" in name_raw else (name_raw, "")
        )
        # 主訴と経過等の抽出
        # QRデータでは主訴[9]に長文が入ることがある
        # 短いテキスト（20文字以下）があれば主訴、長文は経過等として扱う
        field_8 = items[8].strip() if len(items) > 8 else ""
        field_9 = items[9].strip() if len(items) > 9 else ""
        field_10 = items[10].strip() if len(items) > 10 else ""
        field_11 = items[11].strip() if len(items) > 11 else ""

        # 主訴候補: 短いフィールドを探す
        complaint = ""
        history = ""
        for f in [field_8, field_10, field_11]:
            if f and len(f) <= 30 and not f.isdigit():
                complaint = f
                break
        # 経過等: 最も長いテキストフィールドを使用
        history = field_9 if len(field_9) > len(field_8) else field_8
        # 主訴が見つからない場合、経過等の冒頭から抽出を試みる
        if not complaint and history:
            # 最初の句点または読点までを主訴とする
            for sep in ["。", "、"]:
                if sep in history:
                    candidate = history[:history.index(sep)]
                    if len(candidate) <= 30:
                        complaint = candidate
                        break

        return {
            "month": str(dt.month),
            "day": str(dt.day),
            "weekday": weeks[dt.weekday()],
            "hour": f"{dt.hour:02}",
            "minute": f"{dt.minute:02}",
            "kanji": kanji.strip().replace("　", " "),
            "kana": kana.strip().replace("　", " "),
            "gender": items[5],
            "complaint": complaint,
            "history": history,
            "birth": items[13],
            "age": items[14] if len(items) > 14 else "",
            "jcs": items[15] if len(items) > 15 else "",
            "bp_s": items[19] if len(items) > 19 else "",
            "bp_d": items[20] if len(items) > 20 else "",
            "hr": items[21] if len(items) > 21 else "",
            "rr": items[22] if len(items) > 22 else "",
            "bt": items[23] if len(items) > 23 else "",
            "spo2": items[24] if len(items) > 24 else "",
        }
    except Exception as e:
        st.error(f"データ解析失敗: {e}")
        return None

def draw_maru(draw, xy, r=40):
    x, y = xy
    draw.ellipse((x - r, y - r, x + r, y + r), outline="red", width=10)

# === 座標定数 (300dpi) ===
POS_MONTH  = (455, 445)
POS_DAY    = (580, 445)
POS_WDAY   = (720, 445)
POS_HOUR   = (820, 445)
POS_MINUTE = (935, 445)
POS_ORIGIN = (1060, 420)
POS_HISTORY_YES  = (1910, 480)
POS_HISTORY_NO   = (2180, 480)
POS_HISTORY_DEPT = (1960, 445)
POS_KANA  = (450, 562)
POS_KANJI = (450, 598)
POS_BIRTH_Y = (1560, 582)
POS_BIRTH_M = (1640, 578)
POS_BIRTH_D = (1850, 578)
POS_AGE = (1475, 680)
POS_MALE   = (1980, 708)
POS_FEMALE = (2100, 708)
POS_COMPLAINT = (420, 830)
COMPLAINT_WRAP_WIDTH = 45
POS_HISTORY_TEXT = (420, 1000)
HISTORY_LINE_HEIGHT = 55
HISTORY_WRAP_WIDTH = 28
VITAL_X = 1845
JCS_X = 1960
VITAL_Y = {"jcs":1278,"rr":1390,"hr":1492,"bp":1593,"spo2":1695,"bt":1795}
POS_OUJI   = (300, 2260)
POS_FUOUJI = (265, 2360)
POS_TOCHOKU     = (1167, 2260)
POS_KYUKYU_INIT = (1356, 2260)
POS_SONOTA_INIT = (1574, 2260)
POS_SONOTA_INIT_TEXT = (1700, 2250)
POS_NYUIN  = (841, 2390)
POS_KITAKU = (764, 2450)
POS_4EAST = (1433, 2440)
POS_HCU   = (1546, 2440)
POS_ICU   = (1660, 2440)
POS_WARD_OTHER_TEXT = (1300, 2500)
POS_RINKEN      = (1892, 2400)
POS_KYUKYU_MAIN = (1913, 2445)
POS_MAIN_OTHER_TEXT = (1900, 2485)
FUOUJI_REASON_Y = [2553, 2603, 2653, 2703, 2753, 2803, 2853, 2902]
FUOUJI_REASON_X = 230
POS_RECORDER = (1750, 300)

# === メイン ===
st.set_page_config(page_title="台帳作成システム", layout="centered")
st.title("🚑 市立札幌病院 トリアージ台帳")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=["png","jpg","jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    with st.spinner("QRコードをスキャン中..."):
        qr = decode(img)
        if not qr:
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            qr = decode(gray)
        if not qr:
            sharp = cv2.detailEnhance(np.array(img), sigma_s=10, sigma_r=0.15)
            qr = decode(sharp)

    if qr:
        raw_b64 = qr[0].data.decode("utf-8")
        items = decode_qr_raw(raw_b64)
        data = parse_ems_qr(items)

        if data:
            st.success(f"読込成功: {data['kanji']} 様")

            with st.expander("🔍 QRデータ確認（インデックス調整用）"):
                st.text(f"CSV項目数: {len(items)}")
                labels = {1:"依頼日時",4:"氏名",5:"性別",8:"主訴",9:"経過等",
                          13:"生年月日",14:"年齢",15:"JCS",19:"BP上",20:"BP下",
                          21:"HR",22:"RR",23:"SpO2",24:"BT"}
                for i, v in enumerate(items):
                    lbl = f"  ← {labels[i]}" if i in labels else ""
                    st.text(f"[{i:2d}] {v[:80]}{lbl}")

            st.subheader("台帳情報の入力")
            recorder = st.selectbox("記載者", ["前川", "森木", "小舘", "遠藤"])
            col1, col2 = st.columns(2)
            with col1:
                origin = st.text_input("依頼元（救急隊）", value="中央").replace("救急隊","").strip()
                history_yn = st.radio("受診歴", ["無","有"], index=0, horizontal=True)
            with col2:
                history_dept = st.text_input("受診科名（有の場合）")
                decision = st.radio("判定", ["応需","不応需"], index=0, horizontal=True)
            complaint_edit = st.text_input("主訴（編集可）", value=data.get("complaint", ""))

            res = {}
            if decision == "応需":
                res["init"] = st.selectbox("初期対応した科", ["当直医","救急科","その他"])
                if res["init"] == "その他":
                    res["init_other"] = st.text_input("初期対応科名")
                res["out"] = st.selectbox("最終転帰", ["入院","帰宅","その他"])
                if res["out"] == "入院":
                    res["ward"] = st.selectbox("病棟", ["4東","HCU","ICU","その他"])
                    if res["ward"] == "その他":
                        res["ward_other"] = st.text_input("病棟名")
                    res["main"] = st.selectbox("主科", ["臨研","救急科","その他"])
                    if res["main"] == "その他":
                        res["main_other"] = st.text_input("主科名")
            else:
                reasons = ["1. 緊急性なし","2. ベッド満床","3. 既定の応需不可症例",
                           "4. 対応可能な医師不在","5. 緊急手術制限中",
                           "6-A. 医師処置中につき対応困難","6-B. 看護師処置中につき対応困難","7. その他"]
                res["reason"] = st.selectbox("不応需理由", reasons)

            if st.button("台帳を生成する", type="primary"):
                with st.spinner("作成中..."):
                    pages = convert_from_path("トリアージ台帳.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    d = ImageDraw.Draw(base)
                    f_s=get_font(30); f_sm=get_font(36); f_m=get_font(42); f_l=get_font(68)

                    # 依頼日時
                    d.text(POS_MONTH, data["month"], font=f_m, fill="black")
                    d.text(POS_DAY, data["day"], font=f_m, fill="black")
                    d.text(POS_WDAY, data["weekday"], font=f_m, fill="black")
                    d.text(POS_HOUR, data["hour"], font=f_m, fill="black")
                    d.text(POS_MINUTE, data["minute"], font=f_m, fill="black")

                    # 依頼元
                    d.text(POS_ORIGIN, origin, font=get_font(26), fill="black")

                    # --- 記載者 ---
                    d.text(POS_RECORDER, recorder, font=f_l, fill="black")
                    # 受診歴
                    if history_yn == "有":
                        draw_maru(d, POS_HISTORY_YES)
                        if history_dept:
                            d.text(POS_HISTORY_DEPT, history_dept, font=f_m, fill="black")
                    else:
                        draw_maru(d, POS_HISTORY_NO)

                    # 患者名
                    d.text(POS_KANA, data["kana"], font=f_s, fill="black")
                    d.text(POS_KANJI, data["kanji"], font=f_l, fill="black")

                    # 生年月日
                    b = data["birth"]
                    if len(b) == 8:
                        d.text(POS_BIRTH_Y, b[:4], font=get_font(26), fill="black")
                        d.text(POS_BIRTH_M, b[4:6], font=f_m, fill="black")
                        d.text(POS_BIRTH_D, b[6:], font=f_m, fill="black")

                    # 年齢
                    if data["age"]:
                        d.text(POS_AGE, data["age"], font=f_m, fill="black")

                    # 性別
                    if data["gender"] == "2" or "女" in data["gender"]:
                        draw_maru(d, POS_FEMALE, r=35)
                    else:
                        draw_maru(d, POS_MALE, r=35)

                    # 主訴（枠内改行）
                    if complaint_edit:
                        for i, line in enumerate(textwrap.wrap(complaint_edit, width=COMPLAINT_WRAP_WIDTH)):
                            d.text((POS_COMPLAINT[0], POS_COMPLAINT[1]+i*55), line, font=f_m, fill="black")

                    # 経過等（自動改行、枠内制限）
                    if data["history"]:
                        for i, line in enumerate(textwrap.wrap(data["history"], width=HISTORY_WRAP_WIDTH)):
                            y = POS_HISTORY_TEXT[1] + i * HISTORY_LINE_HEIGHT
                            if y > 2100: break
                            d.text((POS_HISTORY_TEXT[0], y), line, font=f_m, fill="black")

                    # バイタルサイン
                    if data["jcs"]:
                        d.text((JCS_X, VITAL_Y["jcs"]), data["jcs"], font=f_m, fill="black")
                    for key, field in [("rr","rr"),("hr","hr"),("spo2","spo2"),("bt","bt")]:
                        if data[field]:
                            d.text((VITAL_X, VITAL_Y[key]), data[field], font=f_m, fill="black")
                    if data["bp_s"] and data["bp_d"]:
                        d.text((VITAL_X, VITAL_Y["bp"]), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")

                    # 判定
                    if decision == "応需":
                        draw_maru(d, POS_OUJI, r=48)
                        # 初期対応した科
                        if res["init"] == "当直医":
                            draw_maru(d, POS_TOCHOKU, r=50)
                        elif res["init"] == "救急科":
                            draw_maru(d, POS_KYUKYU_INIT, r=50)
                        elif res["init"] == "その他":
                            draw_maru(d, POS_SONOTA_INIT, r=50)
                            if res.get("init_other"):
                                d.text(POS_SONOTA_INIT_TEXT, res["init_other"], font=f_s, fill="black")
                        # 最終転帰
                        if res["out"] == "入院":
                            draw_maru(d, POS_NYUIN, r=30)
                            # 病棟
                            wp = {"4東":POS_4EAST,"HCU":POS_HCU,"ICU":POS_ICU}
                            if res.get("ward") in wp:
                                draw_maru(d, wp[res["ward"]], r=35)
                            elif res.get("ward") == "その他" and res.get("ward_other"):
                                d.text(POS_WARD_OTHER_TEXT, res["ward_other"], font=f_s, fill="black")
                            # 主科
                            if res.get("main") == "臨研":
                                draw_maru(d, POS_RINKEN, r=35)
                            elif res.get("main") == "救急科":
                                draw_maru(d, POS_KYUKYU_MAIN, r=35)
                            elif res.get("main") == "その他" and res.get("main_other"):
                                d.text(POS_MAIN_OTHER_TEXT, res["main_other"], font=f_s, fill="black")
                        elif res["out"] == "帰宅":
                            draw_maru(d, POS_KITAKU, r=30)
                    else:
                        draw_maru(d, POS_FUOUJI, r=48)
                        rl = ["1","2","3","4","5","6-A","6-B","7"]
                        rk = res["reason"].split(".")[0].strip()
                        if rk in rl:
                            draw_maru(d, (FUOUJI_REASON_X, FUOUJI_REASON_Y[rl.index(rk)]), r=30)

                    st.image(base, use_container_width=True)
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("📥 台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
    else:
        st.error("QRコードが見つかりません。画像を拡大するか、明るい場所で撮り直してください。")
