import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode
import os

# --- 日本語フォントの設定 ---
def get_font(size):
    # Streamlit Cloud (Linux) の標準的な日本語フォントパス
    paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/fonts-japanese-gothic.ttf"
    ]
    for path in paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def parse_ems_qr(b64_string):
    try:
        decoded_bytes = base64.b64decode(b64_string)
        decoded_text = decoded_bytes.decode('utf-8')
        items = decoded_text.split(',')
        # インデックス修正: 4=氏名, 11=年齢, 8=主訴 
        return {
            "name": items[4].split('　')[0].strip(), # 姓名のみ
            "gender": items[5], # 2=女, 1=男
            "complaint": items[8],
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

def draw_maru(draw, center, radius=45):
    """指定座標に赤い◯を描画"""
    x, y = center
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=10)

st.set_page_config(page_title="市立札幌病院 転記システム")
st.title("🚑 トリアージ台帳作成（最終修正版）")

uploaded_file = st.file_uploader("QRコードのスクリーンショット", type=['png', 'jpg', 'jpeg'])

if 'output' not in st.session_state:
    st.session_state.output = None

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded = decode(img)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"解析成功: {data['name']} 様")
            
            with st.form("ledger_form"):
                col1, col2 = st.columns(2)
                with col1:
                    origin = st.text_input("依頼元", value="中央救急隊")
                    history = st.radio("受診歴", ["無", "有"], horizontal=True)
                with col2:
                    decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
                    outcome = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])

                if st.form_submit_button("台帳を生成"):
                    # PDFを300dpiで画像化
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    font_m = get_font(50)  # 中サイズ
                    font_l = get_font(70)  # 大サイズ

                    # --- 文字入力 (座標をPDFの枠に最適化) ---
                    draw.text((1100, 380), origin, font=font_m, fill="black")
                    draw.text((350, 480), data['name'], font=font_l, fill="black")
                    draw.text((1350, 520), data['age'], font=font_m, fill="black")
                    draw.text((250, 680), data['complaint'], font=font_m, fill="black")

                    # バイタルサイン
                    v_x = 2200
                    draw.text((v_x, 1080), data['jcs'], font=font_m, fill="black")
                    draw.text((v_x, 1200), data['rr'], font=font_m, fill="black")
                    draw.text((v_x, 1310), data['pr'], font=font_m, fill="black")
                    draw.text((v_x, 1430), f"{data['bp_s']}/{data['bp_d']}", font=font_m, fill="black")
                    draw.text((v_x, 1550), data['spo2'], font=font_m, fill="black")
                    draw.text((v_x, 1680), data['bt'], font=font_m, fill="black")

                    # --- ◯（赤丸）の記入 ---
                    # 受診歴
                    if history == "無": draw_maru(draw, (2060, 145))
                    else: draw_maru(draw, (1810, 145))
                    
                    # 性別
                    if data['gender'] == "2": draw_maru(draw, (2090, 195)) # 女
                    else: draw_maru(draw, (1890, 195)) # 男

                    # 判定
                    if decision == "応需": draw_maru(draw, (130, 650))
                    else: draw_maru(draw, (130, 680))

                    # 最終転帰
                    if outcome == "入院": draw_maru(draw, (830, 675), radius=35)
                    elif outcome == "帰宅": draw_maru(draw, (830, 700), radius=35)

                    st.session_state.output = base

if st.session_state.output:
    st.image(st.session_state.output)
    buf = io.BytesIO()
    st.session_state.output.save(buf, format="JPEG", quality=95)
    st.download_button("台帳を保存", buf.getvalue(), "triage_complete.jpg", "image/jpeg")
