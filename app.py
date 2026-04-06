import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode

def parse_ems_qr(b64_string):
    try:
        decoded_bytes = base64.b64decode(b64_string)
        decoded_text = decoded_bytes.decode('utf-8')
        items = decoded_text.split(',')
        return {
            "name": items[2].replace('　', ' '),
            "gender": items[5],
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

st.set_page_config(page_title="トリアージ台帳作成システム", layout="centered")
st.title("🚑 トリアージ台帳 自動作成")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=['png', 'jpg', 'jpeg'])

if 'ledger_image' not in st.session_state:
    st.session_state.ledger_image = None

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded_objects = decode(img)

    if decoded_objects:
        qr_content = decoded_objects[0].data.decode('utf-8')
        data = parse_ems_qr(qr_content)
        
        if data:
            st.success(f"読み込み成功: {data['name']} 様")
            
            with st.form("triage_form"):
                st.subheader("台帳情報の入力")
                
                # 1. 基本情報・受診歴
                col1, col2 = st.columns(2)
                with col1:
                    req_origin = st.text_input("依頼元（救急隊）", value="中央救急隊")
                with col2:
                    visit_history = st.radio("受診歴", ["無", "有"], horizontal=True)
                    visit_dept = ""
                    if visit_history == "有":
                        visit_dept = st.text_input("受診科名を入力")

                st.divider()

                # 2. 判定と詳細
                decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
                
                res_detail = {} # 描画用データ保持

                if decision == "応需":
                    # 初期対応した科
                    init_dept = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                    init_dept_free = st.text_input("その他の科名") if init_dept == "その他" else ""
                    
                    # 最終転帰
                    outcome = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                    outcome_free = st.text_input("その他の転帰詳細") if outcome == "その他" else ""
                    
                    # 入院の場合の追加詳細
                    ward = ""; ward_free = ""; main_dept = ""; main_dept_free = ""
                    if outcome == "入院":
                        col_adm1, col_adm2 = st.columns(2)
                        with col_adm1:
                            ward = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"])
                            if ward == "その他": ward_free = st.text_input("その他の病棟名")
                        with col_adm2:
                            main_dept = st.selectbox("主科", ["臨研", "救急科", "その他"])
                            if main_dept == "その他": main_dept_free = st.text_input("その他の診療科名")
                    
                    res_detail = {
                        "init": init_dept_free if init_dept == "その他" else init_dept,
                        "outcome": outcome_free if outcome == "その他" else outcome,
                        "ward": ward_free if ward == "その他" else ward,
                        "main": main_dept_free if main_dept == "その他" else main_dept
                    }

                else: # 不応需
                    reason_cat = st.selectbox("不応需理由", [
                        "1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可症例", 
                        "4. 対応可能な医師不在", "5. 緊急手術制限中", 
                        "6-A. 医師処置中につき対応困難", "6-B. 看護師処置中につき対応困難", "7. その他"
                    ])
                    reason_free = st.text_input("不応需理由の具体的な詳細")
                    res_detail = {"reason": f"{reason_cat} ({reason_free})"}

                free_notes = st.text_area("自由記載欄")
                
                if st.form_submit_button("台帳プレビューを生成"):
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base_img = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base_img)
                    
                    # --- 描画 (座標は目安です) ---
                    draw.text((450, 480), req_origin, fill="black") # 依頼元 
                    draw.text((1200, 480), f"{visit_history}({visit_dept})", fill="black") # 受診歴 
                    draw.text((450, 700), data['name'], fill="black") # 氏名 
                    draw.text((1600, 700), f"{data['age']}歳 / {data['gender']}", fill="black") # 年齢性別 
                    draw.text((450, 850), data['complaint'], fill="black") # 主訴 

                    # バイタル 
                    v_x = 2300
                    draw.text((v_x, 1220), data['jcs'], fill="black")
                    draw.text((v_x, 1330), data['rr'], fill="black")
                    draw.text((v_x, 1440), data['pr'], fill="black")
                    draw.text((v_x, 1550), f"{data['bp_s']}/{data['bp_d']}", fill="black")
                    draw.text((v_x, 1660), data['spo2'], fill="black")
                    draw.text((v_x, 1770), data['bt'], fill="black")

                    # 判定・転帰 
                    if decision == "応需":
                        draw.text((400, 2050), f"応需: {res_detail['init']} / 転帰: {res_detail['outcome']}", fill="red")
                        if res_detail['ward']:
                            draw.text((1500, 2050), f"病棟: {res_detail['ward']} / 主科: {res_detail['main']}", fill="red")
                    else:
                        draw.text((400, 2050), f"不応需: {res_detail['reason']}", fill="red")
                    
                    draw.text((400, 2800), free_notes, fill="black")
                    st.session_state.ledger_image = base_img
                    st.session_state.p_name = data['name']

if st.session_state.ledger_image:
    st.divider()
    st.image(st.session_state.ledger_image)
    buf = io.BytesIO()
    st.session_state.ledger_image.save(buf, format="JPEG")
    st.download_button("台帳を保存", buf.getvalue(), f"triage_{st.session_state.p_name}.jpg", "image/jpeg")
