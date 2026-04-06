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

# --- フォント設定 ---
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

# --- QR解析 (詳細版) ---
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode('utf-8')
        items = decoded.split(',')
        
        # 依頼日時 (秒を消して曜日を追加)
        raw_ts = items[0] # 2026/04/06 22:13:58
        dt = datetime.strptime(raw_ts, '%Y/%m/%d %H:%M:%S')
        weeks = ["月", "火", "水", "木", "金", "土", "日"]
        formatted_ts = f"{dt.year}/{dt.month}/{dt.day} ({weeks[dt.weekday()]}) {dt.hour:02}:{dt.minute:02}"
        
        # 氏名分割
        name_raw = items[4]
        kanji, kana = name_raw.split('θ', 1) if 'θ' in name_raw else (name_raw, "")
        
        return {
            "timestamp": formatted_ts,
            "kanji": kanji.strip(),
            "kana": kana.strip(),
            "gender": items[5],
            "history": items[8],     # 経過等
            "complaint": items[9],   # 主訴
            "birth": items[10],      # 19960926
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

# --- 赤丸描画 ---
def draw_maru(draw, xy, radius=65):
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=14)

st.title("🚑 市立札幌病院 トリアージ台帳")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded = decode(img)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"読込成功: {data['kanji']} 様")
            
            with st.form("detail_form"):
                col1, col2 = st.columns(2)
                with col1:
                    origin = st.text_input("依頼元（救急隊）", value="中央").replace("救急隊", "")
                    history_yn = st.radio("受診歴", ["無", "有"], horizontal=True)
                with col2:
                    history_dept = st.text_input("受診科（有の場合）")
                    decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
                
                submitted = st.form_submit_button("台帳を生成")

                if submitted:
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    
                    f_s = get_font(38); f_m = get_font(58); f_l = get_font(95)

                    # --- 文字入力 (座標を枠内に固定) ---
                    # 依頼日時
                    draw.text((250, 425), data['timestamp'], font=f_m, fill="black")
                    # 依頼元
                    draw.text((1250, 435), origin, font=f_m, fill="black")
                    
                    # 患者名 (左端に寄せる)
                    draw.text((180, 700), data['kana'], font=f_s, fill="black") # ふりがな
                    draw.text((180, 750), data['kanji'], font=f_l, fill="black") # 漢字

                    # 生年月日 (19960926 を分解)
                    b = data['birth']
                    draw.text((1680, 665), b[:4], font=f_m, fill="black") # 年
                    draw.text((2000, 665), b[4:6], font=f_m, fill="black") # 月
                    draw.text((2230, 665), b[6:], font=f_m, fill="black") # 日
                    
                    # 年齢 (枠の中央へ)
                    draw.text((1780, 765), data['age'], font=f_m, fill="black")

                    # 主訴
                    draw.text((180, 950), data['complaint'], font=f_m, fill="black")

                    # 経過等 (枠内で自動改行)
                    wrap_history = textwrap.wrap(data['history'], width=45)
                    for i, line in enumerate(wrap_history):
                        draw.text((180, 1150 + (i * 75)), line, font=f_m, fill="black")

                    # バイタルサイン (枠内に整列)
                    vx = 2220
                    draw.text((vx, 1235), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 1345), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 1455), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 1565), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 1675), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 1785), data['bt'], font=f_m, fill="black")

                    # --- ◯（赤丸）描画 (座標を下方へシフト) ---
                    # 受診歴
                    if history_yn == "有":
                        draw_maru(draw, (1810, 145))
                        draw.text((2150, 140), history_dept, font=f_m, fill="black")
                    else: draw_maru(draw, (2350, 145))

                    # 性別 (女:2220, 男:2000)
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2220, 200))
                    else: draw_maru(draw, (2000, 200))

                    # 判定 (応需:y=2070, 不応需:y=2160)
                    if decision == "応需": draw_maru(draw, (135, 2070), radius=75)
                    else: draw_maru(draw, (135, 2160), radius=75)

                    st.image(base)
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("画像を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
