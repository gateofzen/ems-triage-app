import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode
import os
import re

# --- 日本語フォント設定 ---
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

# --- 強力なQR解析ロジック ---
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode('utf-8')
        items = decoded.split(',')
        
        # 名前から「θ」や「0」などの記号を完全に除去し、漢字とカタカナを分離
        name_raw = items[4]
        name_parts = re.split(r'[^一-龠ぁ-んァ-ヶー\s]+', name_raw)
        kanji = name_parts[0].strip() if len(name_parts) > 0 else name_raw
        kana = name_parts[1].strip() if len(name_parts) > 1 else ""

        # 日時 (秒を除去)
        dt_raw = items[0]
        dt_clean = dt_raw[:16] # YYYY/MM/DD HH:MM

        return {
            "timestamp": dt_clean,
            "kanji": kanji,
            "kana": kana,
            "gender": items[5], # 1:男, 2:女
            "history": items[8], # 経過等
            "complaint": items[9], # 主訴
            "birth": items[10], # 19960926
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
st.title("🚑 救急QR 転記アプリ（高精度版）")

uploaded_file = st.file_uploader("QRコードのスクリーンショット", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    # 画像読み込みと前処理（読み取り精度向上）
    img = Image.open(uploaded_file)
    
    # QRコード読み取りの試行
    with st.spinner("QRコードを解析中..."):
        # 1. そのまま読み取り
        decoded = decode(img)
        # 2. 失敗したらグレースケールで試行
        if not decoded:
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            decoded = decode(gray)
    
    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"読込成功: {data['kanji']} 様")
            
            # --- 入力 UI (判定切り替えを即座に反映させるため form 外に配置) ---
            st.subheader("台帳情報の追記")
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                origin_in = st.text_input("依頼元（〇〇救急隊）", value="中央")
                origin_clean = origin_in.replace("救急隊", "") # 重複防止
                history_yn = st.radio("受診歴", ["無", "有"], horizontal=True)
            with col_u2:
                history_dept = st.text_input("受診科（「有」の場合）") if history_yn == "有" else ""
                decision = st.radio("判定", ["応需", "不応需"], horizontal=True)

            # 詳細情報の動的入力
            result_info = {}
            if decision == "応需":
                result_info["init"] = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                result_info["out"] = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                result_info["ward"] = st.selectbox("病棟（入院時）", ["4東", "HCU", "ICU", "その他"]) if result_info["out"] == "入院" else ""
            else:
                reasons = ["1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可", "4. 対応可能な医師不在", "5. 緊急手術制限中", "6-A. 医師処置中につき対応困難", "6-B. 看護師処置中につき対応困難", "7. その他"]
                result_info["reason"] = st.selectbox("不応需理由を選択", reasons)

            if st.button("この内容で台帳を生成"):
                with st.spinner("画像を合成中..."):
                    # PDFテンプレート読み込み
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    
                    f_s = get_font(38); f_m = get_font(58); f_l = get_font(95)

                    # --- 1. テキスト配置 (座標を大幅修正) ---
                    draw.text((320, 435), data['timestamp'], font=f_m, fill="black") # 依頼日時
                    draw.text((1200, 435), origin_clean, font=f_m, fill="black") # 依頼元
                    
                    draw.text((450, 640), data['kana'], font=f_s, fill="black") # ふりがな(上)
                    draw.text((450, 710), data['kanji'], font=f_l, fill="black") # 漢字(下)
                    
                    # 生年月日
                    b = data['birth']
                    draw.text((1680, 665), b[:4], font=f_m, fill="black") # 年
                    draw.text((2000, 665), b[4:6], font=f_m, fill="black") # 月
                    draw.text((2230, 665), b[6:], font=f_m, fill="black") # 日
                    draw.text((1780, 775), data['age'], font=f_m, fill="black") # 年齢

                    draw.text((450, 960), data['complaint'], font=f_m, fill="black") # 主訴
                    
                    # 経過等 (枠内改行)
                    import textwrap
                    lines = textwrap.wrap(data['history'], width=38)
                    for i, l in enumerate(lines):
                        draw.text((450, 1280 + (i * 75)), l, font=f_m, fill="black")

                    # バイタルサイン (枠の左寄りに整列)
                    vx = 2270
                    draw.text((vx, 1240), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 1380), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 1520), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 1660), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 1800), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 1940), data['bt'], font=f_m, fill="black")

                    # --- 2. ◯（赤丸）の位置修正 ---
                    if history_yn == "有": draw_maru(draw, (1940, 440))
                    else: draw_maru(draw, (2350, 440))
                    
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2220, 610))
                    else: draw_maru(draw, (2000, 610))

                    if decision == "応需":
                        draw_maru(draw, (140, 2440), radius=75) # 応需
                        if result_info["init"] == "当直医": draw_maru(draw, (1335, 2440))
                        if result_info["out"] == "入院": draw_maru(draw, (835, 2530))
                    else:
                        draw_maru(draw, (140, 2540), radius=75) # 不応需
                        idx = ["1", "2", "3", "4", "5", "6-A", "6-B", "7"].index(result_info["reason"].split('.')[0])
                        draw_maru(draw, (140, 2650 + (idx * 86)), radius=35)

                    st.image(base, caption="完成イメージ")
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
    else:
        st.error("QRコードを認識できません。スクリーンショットをもう少し拡大して撮り直すか、明るい画像で試してください。")
