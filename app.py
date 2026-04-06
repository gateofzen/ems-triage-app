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
import re

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

# --- QR解析 (依頼日時[0]、主訴[9]、経過[8]を正確に分離) ---
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode('utf-8')
        items = decoded.split(',')
        name_raw = items[4]
        
        # 特殊記号（θや0）で漢字とカタカナを確実に分離
        parts = re.split(r'[θ0]', name_raw)
        kanji = parts[0].strip().replace('　', ' ')
        kana = parts[1].strip().replace('　', ' ') if len(parts) > 1 else ""
        
        return {
            "timestamp": items[0], # 依頼日時
            "kanji": kanji,
            "kana": kana,
            "gender": items[5], # 1:男, 2:女
            "history": items[8], # 経過等（現病歴）
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
st.title("🚑 トリアージ台帳 自動作成（最終調整）")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=['png', 'jpg', 'jpeg'])

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
                origin_in = st.text_input("依頼元（〇〇救急隊）", value="中央")
                # 「救急隊」を重複させないための処理
                origin_txt = origin_in.replace("救急隊", "")
                history = st.radio("受診歴", ["無", "有"], horizontal=True)
                history_dept = st.text_input("受診科（有の場合）")
            
            st.divider()
            decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
            
            # 応需・不応需に応じた入力出し分け
            res_info = {}
            if decision == "応需":
                res_info["init"] = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                res_info["out"] = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                res_info["ward"] = ""
                if res_info["out"] == "入院":
                    res_info["ward"] = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"])
            else:
                reasons = ["1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可", "4. 対応可能な医師不在", "5. 緊急手術制限中", "6-A. 医師処置中につき対応困難", "6-B. 看護師処置中につき対応困難", "7. その他"]
                res_info["reason"] = st.selectbox("不応需理由", reasons)

            if st.button("台帳を生成する"):
                with st.spinner("作成中..."):
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    f_s = get_font(38); f_m = get_font(58); f_l = get_font(95)

                    # --- 1. テキスト描画 (座標の精密再計算) ---
                    draw.text((320, 430), data['timestamp'], font=f_m, fill="black") # 依頼日時
                    draw.text((1200, 430), origin_txt, font=f_m, fill="black") # 依頼元

                    draw.text((450, 630), data['kana'], font=f_s, fill="black")  # ふりがな(漢字の上)
                    draw.text((450, 700), data['kanji'], font=f_l, fill="black") # 漢字氏名
                    draw.text((1650, 700), data['age'], font=f_m, fill="black") # 年齢 (数字のみ)
                    
                    draw.text((450, 950), data['complaint'], font=f_m, fill="black") # 主訴

                    # 経過等 (自動改行)
                    history_lines = textwrap.wrap(data['history'], width=38)
                    for i, line in enumerate(history_lines):
                        draw.text((450, 1250 + (i * 75)), line, font=f_m, fill="black")

                    # バイタルサイン (枠内に整列)
                    vx = 2280
                    draw.text((vx, 1240), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 1380), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 1520), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 1660), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 1800), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 1940), data['bt'], font=f_m, fill="black")

                    # --- 2. ◯（赤丸）の記入 (文字の真上に固定) ---
                    # 受診歴 (有:1940, 無:2350)
                    if history == "有":
                        draw_maru(draw, (1940, 435))
                        draw.text((2150, 425), history_dept, font=f_m, fill="black")
                    else: draw_maru(draw, (2350, 435))
                    
                    # 性別 (男:2000, 女:2220)
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2220, 610))
                    else: draw_maru(draw, (2000, 610))

                    # 判定 (応需:y=2430, 不応需:y=2530 付近)
                    if decision == "応需":
                        draw_maru(draw, (140, 2430), radius=75) # 「応需」
                        if res_info["init"] == "当直医": draw_maru(draw, (1330, 2430))
                        if res_info["out"] == "入院": draw_maru(draw, (830, 2520))
                    else:
                        draw_maru(draw, (140, 2530), radius=75) # 「不応需」
                        idx = ["1", "2", "3", "4", "5", "6-A", "6-B", "7"].index(res_info["reason"].split('.')[0])
                        draw_maru(draw, (140, 2640 + (idx * 85)), radius=35)

                    st.image(base, caption="台帳プレビュー")
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
