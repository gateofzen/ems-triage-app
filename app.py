import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode
import os

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

# --- QRデータ解析 ---
def parse_ems_qr(b64_string):
    try:
        decoded_text = base64.b64decode(b64_string).decode('utf-8')
        items = decoded_text.split(',')
        return {
            "name": items[4].replace('　', ' ').strip(), # フルネーム取得
            "gender": items[5], # 2:女性, 1:男性
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

# --- ◯描画関数 ---
def draw_maru(draw, xy, radius=45):
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=12)

st.title("🚑 市立札幌病院 トリアージ台帳作成")

uploaded_file = st.file_uploader("QRコードのスクリーンショット", type=['png', 'jpg', 'jpeg'])

if 'final_img' not in st.session_state:
    st.session_state.final_img = None

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded = decode(img)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"解析成功: {data['name']} 様")
            
            with st.form("ledger_form"):
                st.subheader("台帳情報の追記")
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    origin = st.text_input("依頼元（救急隊）", value="中央救急隊")
                    history = st.radio("受診歴", ["無", "有"], horizontal=True)
                    history_dept = st.text_input("受診科（有の場合）")
                
                st.divider()
                
                decision = st.radio("応需判定", ["応需", "不応需"], horizontal=True)
                
                # --- 条件分岐UI ---
                if decision == "応需":
                    init_dept = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                    init_free = st.text_input("その他の科名") if init_dept == "その他" else ""
                    
                    outcome = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                    outcome_free = st.text_input("その他の転帰詳細") if outcome == "その他" else ""
                    
                    ward = ""; ward_free = ""; main_dept = ""; main_dept_free = ""
                    if outcome == "入院":
                        c1, c2 = st.columns(2)
                        with c1:
                            ward = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"])
                            if ward == "その他": ward_free = st.text_input("その他の病棟")
                        with c2:
                            main_dept = st.selectbox("主科", ["臨研", "救急科", "その他"])
                            if main_dept == "その他": main_dept_free = st.text_input("その他の主科")
                
                else: # 不応需
                    reason_cat = st.selectbox("不応需理由", [
                        "1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可", 
                        "4. 対応可能な医師不在", "5. 緊急手術制限中", 
                        "6-A. 医師処置中につき対応困難", "6-B. 看護師処置中につき対応困難", "7. その他"
                    ])
                    reason_free = st.text_input("理由の詳細（その他等）")

                free_text = st.text_area("自由記載欄")

                if st.form_submit_button("台帳を生成"):
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    f_m = get_font(50)
                    f_l = get_font(70)

                    # --- 文字描画 ---
                    draw.text((1200, 480), origin, font=f_m, fill="black")
                    draw.text((350, 700), data['name'], font=f_l, fill="black")
                    draw.text((1600, 710), f"{data['age']} 歳", font=f_m, fill="black")
                    draw.text((450, 850), data['complaint'], font=f_m, fill="black")

                    # バイタル (右側)
                    v_x = 2300
                    draw.text((v_x, 1220), data['jcs'], font=f_m, fill="black")
                    draw.text((v_x, 1330), data['rr'], font=f_m, fill="black")
                    draw.text((v_x, 1440), data['pr'], font=f_m, fill="black")
                    draw.text((v_x, 1550), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((v_x, 1660), data['spo2'], font=f_m, fill="black")
                    draw.text((v_x, 1770), data['bt'], font=f_m, fill="black")

                    # --- ◯描画 ---
                    # 受診歴 (有:1900,145, 無:2350,145)
                    if history == "有": 
                        draw_maru(draw, (1940, 145))
                        draw.text((2050, 145), history_dept, font=f_m, fill="black")
                    else: draw_maru(draw, (2350, 145))

                    # 性別 (男:2000,200, 女:2200,200)
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2220, 200))
                    else: draw_maru(draw, (2000, 200))

                    # 判定・転帰
                    if decision == "応需":
                        draw_maru(draw, (140, 650)) # 応需
                        if outcome == "入院": draw_maru(draw, (830, 680))
                        elif outcome == "帰宅": draw_maru(draw, (830, 710))
                        # 初期対応科
                        if init_dept == "当直医": draw_maru(draw, (1330, 645))
                        elif init_dept == "救急科": draw_maru(draw, (1680, 645))
                        # 入院詳細
                        if ward == "4東": draw_maru(draw, (1630, 690))
                        elif ward == "HCU": draw_maru(draw, (1850, 690))
                        if main_dept == "臨研": draw_maru(draw, (2300, 680))
                        elif main_dept == "救急科": draw_maru(draw, (2300, 710))
                    else:
                        draw_maru(draw, (140, 680)) # 不応需
                        # 理由 (1~7の座標簡易マッピング)
                        y_off = 740 + (["1","2","3","4","5","6-A","6-B","7"].index(reason_cat[:3].strip('.')) * 30)
                        draw_maru(draw, (140, y_off), radius=25)

                    draw.text((400, 2800), free_text, font=f_m, fill="black")
                    st.session_state.final_img = base

if st.session_state.final_img:
    st.divider()
    st.image(st.session_state.final_img)
    buf = io.BytesIO()
    st.session_state.final_img.save(buf, format="JPEG", quality=95)
    st.download_button("台帳を保存", buf.getvalue(), "triage_ledger.jpg", "image/jpeg")
