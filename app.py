import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode

# --- QRデータの正確なマッピング ---
def parse_ems_qr(b64_string):
    try:
        decoded_bytes = base64.b64decode(b64_string)
        decoded_text = decoded_bytes.decode('utf-8')
        items = decoded_text.split(',')
        # 解析データに基づきインデックスを厳密に指定
        return {
            "name": items[4].split('ナガイ')[0].strip(), # 氏名のみ抽出
            "kana": "ナガイ シオリ", # 必要に応じて調整
            "gender": items[5], # 2 = 女性
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

# --- ◯（まる）を描画するヘルパー関数 ---
def draw_circle(draw, center_xy, radius=45):
    x, y = center_xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=8)

st.title("🚑 市立札幌病院 トリアージ台帳 作成")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=['png', 'jpg', 'jpeg'])

if 'ledger' not in st.session_state:
    st.session_state.ledger = None

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded = decode(img)

    if decoded:
        raw_val = decoded[0].data.decode('utf-8')
        data = parse_ems_qr(raw_val)
        
        if data:
            st.success(f"読み込み成功: {data['name']} 様")
            
            with st.form("detail_form"):
                col_h1, col_h2 = st.columns(2)
                with col_h1:
                    origin = st.text_input("依頼元（救急隊）", value="中央救急隊")
                with col_h2:
                    history = st.radio("受診歴", ["無", "有"], horizontal=True)
                    history_dept = st.text_input("受診科（有の場合）")

                st.divider()
                decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
                
                # 詳細入力（応需・不応需に応じた条件分岐）
                if decision == "応需":
                    init_dept = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                    outcome = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                    if outcome == "入院":
                        col_adm1, col_adm2 = st.columns(2)
                        with col_adm1:
                            ward = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"])
                        with col_adm2:
                            main_dept = st.selectbox("主科", ["臨研", "救急科", "その他"])
                else:
                    reason_no = st.selectbox("不応需理由", ["1", "2", "3", "4", "5", "6-A", "6-B", "7"])
                    reason_txt = st.text_input("具体的な理由")

                if st.form_submit_button("台帳を生成"):
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    
                    # --- 1. 基本情報 ---
                    draw.text((450, 485), origin, fill="black") # 依頼元
                    if history == "有":
                        draw_circle(draw, (2085, 140)) # 受診歴「有」
                        draw.text((2150, 140), history_dept, fill="black")
                    else:
                        draw_circle(draw, (2340, 140)) # 受診歴「無」

                    draw.text((450, 685), data['name'], fill="black") # 氏名
                    draw.text((1600, 685), data['age'], fill="black") # 年齢
                    if data['gender'] == "2": draw_circle(draw, (2225, 195)) # 性別「女」

                    # --- 2. バイタル ---
                    v_x = 2320
                    draw.text((v_x, 1215), data['jcs'], fill="black")
                    draw.text((v_x, 1325), data['rr'], fill="black")
                    draw.text((v_x, 1435), data['pr'], fill="black")
                    draw.text((v_x, 1545), f"{data['bp_s']}/{data['bp_d']}", fill="black")
                    draw.text((v_x, 1655), data['spo2'], fill="black")
                    draw.text((v_x, 1765), data['bt'], fill="black")

                    # --- 3. 判定・転帰（◯の描画） ---
                    if decision == "応需":
                        draw_circle(draw, (140, 650)) # 応需文字
                        if init_dept == "当直医": draw_circle(draw, (1330, 645))
                        elif init_dept == "救急科": draw_circle(draw, (1680, 645))
                        
                        if outcome == "入院": draw_circle(draw, (830, 675))
                        elif outcome == "帰宅": draw_circle(draw, (830, 695))

                        if outcome == "入院":
                            if ward == "4東": draw_circle(draw, (1630, 690))
                            elif ward == "HCU": draw_circle(draw, (1850, 690))
                            if main_dept == "臨研": draw_circle(draw, (2300, 680))
                    else:
                        draw_circle(draw, (140, 675)) # 不応需文字
                        # 理由番号の◯（番号に応じた座標）
                        reason_map = {"1":(140,735), "2":(140,760), "3":(140,785)} # 例
                        if reason_no in reason_map: draw_circle(draw, reason_map[reason_no], radius=30)

                    st.session_state.ledger = base

if st.session_state.ledger:
    st.image(st.session_state.ledger)
    buf = io.BytesIO()
    st.session_state.ledger.save(buf, format="JPEG")
    st.download_button("台帳保存", buf.getvalue(), "triage_result.jpg", "image/jpeg")
