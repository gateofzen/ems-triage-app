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

# --- インデックスと記号を修正した解析関数 ---
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode('utf-8')
        items = decoded.split(',')
        
        # 依頼日時 (インデックス1)
        dt = datetime.strptime(items[1], '%Y/%m/%d %H:%M:%S')
        weeks = ["月", "火", "水", "木", "金", "土", "日"]
        ts = f"{dt.year}/{dt.month}/{dt.day} ({weeks[dt.weekday()]}) {dt.hour:02}:{dt.minute:02}"
        
        # 氏名 (インデックス4: 永井 栞θナガイ シオリ)
        name_raw = items[4]
        kanji, kana = name_raw.split('θ', 1) if 'θ' in name_raw else (name_raw, "")
        
        return {
            "ts": ts,
            "kanji": kanji.strip().replace('　', ' '),
            "kana": kana.strip().replace('　', ' '),
            "gender": items[5],    # 2:女性, 1:男性
            "history": items[8],   # 経過等
            "complaint": items[9], # 主訴
            "birth": items[11],   # 19960926
            "age": items[12],      # 29
            "jcs": items[13],
            "bp_s": items[17],
            "bp_d": items[18],
            "pr": items[19],
            "rr": items[20],
            "bt": items[21],
            "spo2": items[22]
        }
    except Exception as e:
        st.error(f"データ解析失敗: {e}")
        return None

# --- 赤丸描画 ---
def draw_maru(draw, xy, radius=60):
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=14)

st.set_page_config(page_title="台帳作成システム", layout="centered")
st.title("🚑 市立札幌病院 トリアージ台帳（完全版）")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    
    with st.spinner("QRコードを精密スキャン中..."):
        # 読み取り精度向上のための3段階試行
        decoded = decode(img)
        if not decoded:
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            decoded = decode(gray)
        if not decoded:
            sharp = cv2.detailEnhance(np.array(img), sigma_s=10, sigma_r=0.15)
            decoded = decode(sharp)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"読込成功: {data['kanji']} 様")
            
            # --- UI設定 ---
            st.subheader("台帳情報の入力")
            col1, col2 = st.columns(2)
            with col1:
                origin = st.text_input("依頼元（救急隊）", value="中央").replace("救急隊", "")
                history_yn = st.radio("受診歴", ["無", "有"], index=0, horizontal=True)
            with col2:
                history_dept = st.text_input("受診科名（有の場合）")
                decision = st.radio("判定", ["応需", "不応需"], index=0, horizontal=True)
            
            # 詳細入力
            res_data = {}
            if decision == "応需":
                res_data["init"] = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                res_data["out"] = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                res_data["ward"] = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"]) if res_data["out"] == "入院" else ""
                res_data["main"] = st.selectbox("主科", ["臨研", "救急科", "その他"]) if res_data["out"] == "入院" else ""
            else:
                reasons = ["1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可", "4. 対応可能な医師不在", "5. 緊急手術制限中", "6-A. 医師処置中につき対応困難", "6-B. 看護師処置中につき対応困難", "7. その他"]
                res_data["reason"] = st.selectbox("不応需理由", reasons)

            if st.button("台帳を生成する"):
                with st.spinner("作成中..."):
                    # PDFを背景として読み込み
                    pages = convert_from_path("トリアージ台帳.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    
                    f_s = get_font(38); f_m = get_font(58); f_l = get_font(95)

                    # --- 1. テキスト描画 (座標をミリ単位で修正) ---
                    # 依頼日時 & 依頼元
                    draw.text((250, 420), data['ts'], font=f_m, fill="black")
                    draw.text((1200, 430), origin, font=f_m, fill="black")
                    
                    # 患者名 (ふりがな・漢字)
                    draw.text((180, 540), data['kana'], font=f_s, fill="black")
                    draw.text((180, 590), data['kanji'], font=f_l, fill="black")

                    # 生年月日 (19960926 を分解)
                    b = data['birth']
                    draw.text((1680, 530), b[:4], font=f_m, fill="black") # 年
                    draw.text((2000, 530), b[4:6], font=f_m, fill="black") # 月
                    draw.text((2230, 530), b[6:], font=f_m, fill="black") # 日
                    
                    # 年齢
                    draw.text((1780, 640), data['age'], font=f_m, fill="black")

                    # 主訴
                    draw.text((180, 750), data['complaint'], font=f_m, fill="black")

                    # 経過等 (枠内改行)
                    wrap_h = textwrap.wrap(data['history'], width=45)
                    for i, line in enumerate(wrap_h):
                        draw.text((180, 950 + (i * 75)), line, font=f_m, fill="black")

                    # バイタルサイン (枠内に正確に配置)
                    vx = 2220
                    draw.text((vx, 1240), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 1345), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 1450), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 1555), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 1660), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 1765), data['bt'], font=f_m, fill="black")

                    # --- 2. ◯（赤丸）描画 (指定の場所に正確に配置) ---
                    # 受診歴 (無:2350, 435)
                    if history_yn == "有":
                        draw_maru(draw, (1810, 435))
                        draw.text((1950, 425), history_dept, font=f_m, fill="black")
                    else: draw_maru(draw, (2350, 435))
                    
                    # 性別 (女性:2220, 640)
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2220, 640))
                    else: draw_maru(draw, (2000, 640))

                    # 判定 (応需:2430)
                    if decision == "応需":
                        draw_maru(draw, (135, 2430), radius=75) # 「応需」
                        if res_data["init"] == "当直医": draw_maru(draw, (1335, 2430))
                        if res_data["out"] == "入院": draw_maru(draw, (835, 2520)) # 「入院」
                        if res_data.get("ward") == "4東": draw_maru(draw, (1630, 2540), radius=45) # 「4東」
                        if res_data.get("main") == "臨研": draw_maru(draw, (2305, 2515), radius=45) # 「臨研」
                    else:
                        draw_maru(draw, (135, 2530), radius=75) # 「不応需」
                        idx = ["1", "2", "3", "4", "5", "6-A", "6-B", "7"].index(res_data["reason"].split('.')[0])
                        draw_maru(draw, (140, 2630 + (idx * 86)), radius=35)

                    st.image(base)
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
    else:
        st.error("QRコードが見つかりません。画像を拡大するか、明るい場所で撮り直してください。")
