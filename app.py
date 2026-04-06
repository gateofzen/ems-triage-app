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

# --- QR解析 (現病歴[8]と主訴[9]を正しく取得) ---
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode('utf-8')
        items = decoded.split(',')
        name_raw = items[4]
        # 「θ」で分割して漢字とカタカナに分ける
        kanji, kana = name_raw.split('θ', 1) if 'θ' in name_raw else (name_raw, "")
        
        return {
            "kanji": kanji.strip().replace('　', ' '),
            "kana": kana.strip().replace('　', ' '),
            "gender": items[5], # 1:男, 2:女
            "history": items[8], # 現病歴（経過等に記入）
            "complaint": items[9], # 主訴
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
def draw_maru(draw, xy, radius=60):
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=14)

st.set_page_config(page_title="市立札幌病院 台帳作成", layout="centered")
st.title("🚑 トリアージ台帳 自動作成（完成版）")

uploaded_file = st.file_uploader("QRコードのスクリーンショット", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded = decode(img)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"読込成功: {data['kanji']} 様")
            
            st.subheader("台帳情報の入力")
            col1, col2 = st.columns(2)
            with col1:
                origin = st.text_input("依頼元（救急隊）", value="中央救急隊")
                history = st.radio("受診歴", ["無", "有"], horizontal=True)
                history_dept = st.text_input("受診科（有の場合）")
            
            st.divider()
            decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
            
            result_data = {}
            if decision == "応需":
                init_dept = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                outcome = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                ward = ""; main_dept = ""
                if outcome == "入院":
                    c1, c2 = st.columns(2)
                    with c1: ward = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"])
                    with c2: main_dept = st.selectbox("主科", ["臨研", "救急科", "その他"])
                result_data = {"init": init_dept, "outcome": outcome, "ward": ward, "main": main_dept}
            else:
                reasons = ["1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可", "4. 対応可能な医師不在", "5. 緊急手術制限中", "6-A. 医師処置中につき対応困難", "6-B. 看護師処置中につき対応困難", "7. その他"]
                reason_cat = st.selectbox("不応需理由", reasons)
                result_data = {"reason": reason_cat}

            if st.button("この内容で台帳を生成する"):
                with st.spinner("作成中..."):
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    f_s = get_font(38); f_m = get_font(58); f_l = get_font(85)

                    # --- 1. テキスト描画 (座標修正版) ---
                    draw.text((1250, 420), origin, font=f_m, fill="black") # 依頼元
                    draw.text((380, 520), data['kana'], font=f_s, fill="black") # よみがな(上)
                    draw.text((380, 595), data['kanji'], font=f_l, fill="black") # 漢字(下)
                    draw.text((1600, 600), f"{data['age']} 歳", font=f_m, fill="black") # 年齢
                    draw.text((250, 780), data['complaint'], font=f_m, fill="black") # 主訴

                    # 経過等 (現病歴を自動改行して描画)
                    history_lines = textwrap.wrap(data['history'], width=35)
                    for i, line in enumerate(history_lines):
                        draw.text((250, 1050 + (i * 70)), line, font=f_m, fill="black")

                    # バイタルサイン
                    vx = 2220
                    draw.text((vx, 1235), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 1345), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 1455), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 1565), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 1675), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 1785), data['bt'], font=f_m, fill="black")

                    # --- 2. ◯（赤丸）の記入 (位置を正確に固定) ---
                    if history == "有": draw_maru(draw, (1815, 140)) # 受診歴 有
                    else: draw_maru(draw, (2350, 140)) # 受診歴 無
                    
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2225, 200)) # 女
                    else: draw_maru(draw, (2000, 200)) # 男

                    if decision == "応需":
                        draw_maru(draw, (135, 2070), radius=65) # 判定:応需
                        if result_data["init"] == "当直医": draw_maru(draw, (1335, 2060))
                        if result_data["outcome"] == "入院": draw_maru(draw, (835, 2130))
                        if result_data["ward"] == "4東": draw_maru(draw, (1635, 2145))
                    else:
                        draw_maru(draw, (135, 2185), radius=65) # 判定:不応需
                        idx = ["1", "2", "3", "4", "5", "6-A", "6-B", "7"].index(result_data["reason"].split('.')[0])
                        draw_maru(draw, (140, 2225 + (idx * 56)), radius=28)

                    st.image(base)
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
