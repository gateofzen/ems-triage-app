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

# --- 日本語フォント取得 ---
def get_font(size):
    paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/fonts-japanese-gothic.ttf"
    ]
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

# --- QR解析ロジック ---
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode('utf-8')
        items = decoded.split(',')
        
        # 1. 依頼日時 (秒をカットして曜日付与)
        dt = datetime.strptime(items[0], '%Y/%m/%d %H:%M:%S')
        weeks = ["月", "火", "水", "木", "金", "土", "日"]
        ts = f"{dt.year}/{dt.month}/{dt.day} ({weeks[dt.weekday()]}) {dt.hour:02}:{dt.minute:02}"
        
        # 2. 氏名分割 (θで分割)
        name_raw = items[4]
        kanji, kana = name_raw.split('θ', 1) if 'θ' in name_raw else (name_raw, "")
        
        return {
            "ts": ts,
            "kanji": kanji.strip(),
            "kana": kana.strip(),
            "gender": items[5],    # 1:男, 2:女
            "history": items[8],   # 経過等 (現病歴)
            "complaint": items[9], # 主訴
            "birth": items[10],    # YYYYMMDD
            "age": items[11],
            "jcs": items[12],
            "bp_s": items[16],
            "bp_d": items[17],
            "pr": items[18],
            "rr": items[19],
            "bt": items[20],
            "spo2": items[21]
        }
    except:
        return None

# --- 赤丸描画関数 ---
def draw_maru(draw, xy, radius=60):
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=14)

st.title("🚑 市立札幌病院 トリアージ台帳作成")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded = decode(img)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"読込成功: {data['kanji']} 様")
            
            with st.form("ledger_form"):
                col1, col2 = st.columns(2)
                with col1:
                    origin = st.text_input("依頼元（〇〇救急隊）", value="中央").replace("救急隊", "")
                    history = st.radio("受診歴", ["無", "有"], index=0, horizontal=True)
                with col2:
                    decision = st.radio("判定", ["応需", "不応需"], index=0, horizontal=True)
                    outcome = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                    ward = st.selectbox("入院先病棟", ["4東", "HCU", "ICU", "その他"])
                    main_dept = st.selectbox("主科", ["臨研", "救急科", "その他"])

                if st.form_submit_button("台帳を生成する"):
                    pages = convert_from_path("トリアージ台帳.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    
                    f_s = get_font(38); f_m = get_font(55); f_l = get_font(90)

                    # --- 1. テキスト入力 (座標を精密調整) ---
                    # 依頼日時 & 依頼元
                    draw.text((220, 140), data['ts'], font=f_m, fill="black")
                    draw.text((1150, 140), origin, font=f_m, fill="black")

                    # 患者氏名 (ふりがなを漢字の上に)
                    draw.text((180, 210), data['kana'], font=f_s, fill="black")
                    draw.text((180, 245), data['kanji'], font=f_l, fill="black")

                    # 生年月日 (19960926 -> 1996年09月26日)
                    b = data['birth']
                    draw.text((1700, 160), b[:4], font=f_m, fill="black") # 年
                    draw.text((2050, 160), b[4:6], font=f_m, fill="black") # 月
                    draw.text((2280, 160), b[6:], font=f_m, fill="black") # 日
                    
                    # 年齢
                    draw.text((1750, 255), data['age'], font=f_m, fill="black")

                    # 主訴
                    draw.text((180, 340), data['complaint'], font=f_m, fill="black")

                    # 経過等 (枠内での自動改行)
                    history_lines = textwrap.wrap(data['history'], width=40)
                    for i, line in enumerate(history_lines):
                        draw.text((180, 480 + (i * 70)), line, font=f_m, fill="black")

                    # バイタルサイン (右側列)
                    vx = 2300
                    draw.text((vx, 435), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 485), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 540), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 595), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 645), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 700), data['bt'], font=f_m, fill="black")

                    # --- 2. ◯（赤丸）の記入 ---
                    # 受診歴 (有:1900, 無:2350)
                    if history == "有": draw_maru(draw, (1940, 145))
                    else: draw_maru(draw, (2350, 145))

                    # 性別 (女:2220, 男:2000)
                    if data['gender'] == "2": draw_maru(draw, (2220, 255))
                    else: draw_maru(draw, (2000, 255))

                    # 判定 (応需:x=140, y=860 / 不応需:x=140, y=900 付近)
                    if decision == "応需":
                        draw_maru(draw, (140, 860), radius=75)
                        if outcome == "入院": draw_maru(draw, (830, 880))
                        if ward == "4東": draw_maru(draw, (1630, 895), radius=45)
                        if main_dept == "臨研": draw_maru(draw, (2300, 885), radius=45)
                    else:
                        draw_maru(draw, (140, 900), radius=75)

                    # プレビュー表示
                    st.image(base)
                    
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
    else:
        st.error("QRコードが見つかりません。")
