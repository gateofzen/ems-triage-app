import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode
import os

# --- フォント読み込み ---
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

# --- QR解析 ---
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode('utf-8')
        items = decoded.split(',')
        # 4番目の要素「氏名0カタカナ」を分割
        name_part = items[4].split('0')
        return {
            "kanji": name_part[0].strip(),
            "kana": name_part[1].strip() if len(name_part) > 1 else "",
            "gender": items[5], # 1:男, 2:女
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

# --- ◯描画 ---
def draw_maru(draw, xy, radius=50):
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=12)

st.title("🚑 トリアージ台帳 自動作成（最終座標調整版）")

uploaded_file = st.file_uploader("QRコードのスクリーンショット", type=['png', 'jpg', 'jpeg'])

if 'ledger_img' not in st.session_state:
    st.session_state.ledger_img = None

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded = decode(img)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"読込完了: {data['kanji']} 様")
            
            with st.form("triage_form"):
                col1, col2 = st.columns(2)
                with col1:
                    origin = st.text_input("依頼元（救急隊）", value="中央救急隊")
                    history = st.radio("受診歴", ["無", "有"], horizontal=True)
                    history_dept = st.text_input("受診科名（有の場合）")
                
                st.divider()
                decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
                
                if decision == "応需":
                    init_dept = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                    init_free = st.text_input("その他の科名") if init_dept == "その他" else ""
                    
                    outcome = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                    outcome_free = st.text_input("その他詳細") if outcome == "その他" else ""
                    
                    ward = ""; main_dept = ""; ward_free = ""; main_free = ""
                    if outcome == "入院":
                        c1, c2 = st.columns(2)
                        with c1:
                            ward = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"])
                            if ward == "その他": ward_free = st.text_input("その他病棟名")
                        with c2:
                            main_dept = st.selectbox("主科", ["臨研", "救急科", "その他"])
                            if main_dept == "その他": main_free = st.text_input("その他主科名")
                else:
                    reason_cat = st.selectbox("不応需理由", ["1", "2", "3", "4", "5", "6-A", "6-B", "7"])
                    reason_free = st.text_input("理由詳細")

                if st.form_submit_button("台帳を生成"):
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    f_s = get_font(35)
                    f_m = get_font(55)
                    f_l = get_font(75)

                    # --- 基本情報 (座標は台帳枠に合わせて微調整済) ---
                    draw.text((1250, 480), origin, font=f_m, fill="black") # 依頼元
                    draw.text((350, 660), data['kana'], font=f_s, fill="black") # よみがな（上）
                    draw.text((350, 710), data['kanji'], font=f_l, fill="black") # 漢字名（下）
                    draw.text((1600, 715), f"{data['age']} 歳", font=f_m, fill="black") # 年齢
                    draw.text((450, 850), data['complaint'], font=f_m, fill="black") # 主訴

                    # --- バイタルサイン (右側枠内) ---
                    vx = 2250
                    draw.text((vx, 1230), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 1340), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 1450), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 1560), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 1670), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 1780), data['bt'], font=f_m, fill="black")

                    # --- ◯（赤丸）の記入 ---
                    # 受診歴 (有:1900, 無:2350)
                    if history == "有":
                        draw_maru(draw, (1900, 145), radius=50)
                        draw.text((2050, 140), history_dept, font=f_m, fill="black")
                    else: draw_maru(draw, (2350, 145), radius=50)

                    # 性別 (男:2000, 女:2200)
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2220, 200), radius=50)
                    else: draw_maru(draw, (2000, 200), radius=50)

                    # 判定 (応需:120, 不応需:120)
                    if decision == "応需":
                        draw_maru(draw, (120, 2060), radius=60) # 応需文字
                        if outcome == "入院": draw_maru(draw, (830, 2125), radius=45)
                        elif outcome == "帰宅": draw_maru(draw, (830, 2155), radius=45)
                        if init_dept == "当直医": draw_maru(draw, (1330, 2055), radius=45)
                        elif init_dept == "救急科": draw_maru(draw, (1680, 2055), radius=45)
                        if ward == "4東": draw_maru(draw, (1630, 2140), radius=40)
                        elif ward == "HCU": draw_maru(draw, (1850, 2140), radius=40)
                        if main_dept == "臨研": draw_maru(draw, (2300, 2110), radius=40)
                        elif main_dept == "救急科": draw_maru(draw, (2300, 2150), radius=40)
                    else:
                        draw_maru(draw, (120, 2150), radius=60) # 不応需文字
                        # 不応需理由 1-7 (y座標を等間隔で計算)
                        idx = ["1","2","3","4","5","6-A","6-B","7"].index(reason_cat)
                        draw_maru(draw, (140, 2220 + (idx * 55)), radius=25)

                    st.session_state.ledger_img = base

if st.session_state.ledger_img:
    st.divider()
    st.image(st.session_state.ledger_img)
    buf = io.BytesIO()
    st.session_state.ledger_img.save(buf, format="JPEG", quality=95)
    st.download_button("台帳をダウンロード", buf.getvalue(), "triage_final.jpg", "image/jpeg")
