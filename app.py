import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode

# --- QRデータの解析関数 (デコード修正版) ---
def parse_ems_qr(b64_string):
    try:
        decoded_bytes = base64.b64decode(b64_string)
        decoded_text = decoded_bytes.decode('utf-8')
        items = decoded_text.split(',')
        # CSVインデックスに基づきマッピング
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

st.set_page_config(page_title="市立札幌病院 トリアージ台帳作成", layout="centered")
st.title("🚑 トリアージ台帳 自動作成システム")

# 1. QRコードのアップロード
uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=['png', 'jpg', 'jpeg'])

# セッション状態の初期化
if 'ledger_image' not in st.session_state:
    st.session_state.ledger_image = None
if 'patient_name' not in st.session_state:
    st.session_state.patient_name = ""

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded_objects = decode(img)

    if decoded_objects:
        qr_content = decoded_objects[0].data.decode('utf-8')
        data = parse_ems_qr(qr_content)
        
        if data:
            st.success(f"読み込み成功: {data['name']} 様")
            st.session_state.patient_name = data['name']
            
            # --- フォーム開始 ---
            with st.form("triage_form"):
                st.subheader("台帳情報の追記")
                
                # 基本情報
                col_info1, col_info2 = st.columns(2)
                with col_info1:
                    request_origin = st.text_input("依頼元（救急隊）", value="中央救急隊")
                with col_info2:
                    visit_history = st.radio("受診歴", ["無", "有"], horizontal=True)

                st.divider()
                
                # 判定メイン
                decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
                
                if decision == "応需":
                    # 初期対応した科 
                    initial_dept = st.selectbox("初期対応した科", ["当直医", "救急科", "その他の科"])
                    other_dept_name = ""
                    if initial_dept == "その他の科":
                        other_dept_name = st.text_input("具体的な科名を入力")

                    # 最終転帰 
                    final_outcome = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                    ward_name = ""
                    if final_outcome == "入院":
                        ward_name = st.selectbox("入院先病棟", ["4東", "HCU", "ICU", "臨研", "救急科", "その他"])
                
                else: # 不応需の場合 
                    reason_cat = st.selectbox("不応需理由を選択", [
                        "1. 緊急性なし",
                        "2. ベッド満床 (救急外来・HCU・4東・その他)",
                        "3. 既定の応需不可症例",
                        "4. 対応可能な医師不在",
                        "5. 緊急手術制限中",
                        "6-A. 医師処置中につき対応困難",
                        "6-B. 看護師処置中につき対応困難",
                        "7. その他"
                    ])
                    reason_detail = st.text_input("不応需理由の具体的な詳細 (任意)")

                free_notes = st.text_area("自由記載欄")
                
                submitted = st.form_submit_button("台帳のプレビューを生成")

                if submitted:
                    # PDFを画像に変換して描画開始
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base_img = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base_img)
                    
                    # --- 描画ロジック (座標はPDF  に合わせて要調整) ---
                    # ヘッダー・基本情報
                    draw.text((450, 480), request_origin, fill="black") # 依頼元
                    draw.text((450, 700), data['name'], fill="black") # 氏名
                    draw.text((1600, 700), f"{data['age']}歳 / {data['gender']}", fill="black")
                    draw.text((450, 850), data['complaint'], fill="black") # 主訴

                    # バイタルサイン
                    v_x = 2300
                    draw.text((v_x, 1220), data['jcs'], fill="black")
                    draw.text((v_x, 1330), data['rr'], fill="black")
                    draw.text((v_x, 1440), data['pr'], fill="black")
                    draw.text((v_x, 1550), f"{data['bp_s']}/{data['bp_d']}", fill="black")
                    draw.text((v_x, 1660), data['spo2'], fill="black")
                    draw.text((v_x, 1770), data['bt'], fill="black")

                    # 判定結果の描画
                    if decision == "応需":
                        res_txt = f"【応需】 {initial_dept} / 転帰: {final_outcome} ({ward_name})"
                    else:
                        res_txt = f"【不応需】 {reason_cat} / {reason_detail}"
                    draw.text((400, 2050), res_txt, fill="red")
                    draw.text((400, 2800), free_notes, fill="black") # 自由記載

                    st.session_state.ledger_image = base_img

    else:
        st.error("QRコードが見つかりませんでした。")

# --- フォームの外に配置 (エラー回避) ---
if st.session_state.ledger_image:
    st.divider()
    st.image(st.session_state.ledger_image, caption="生成された台帳プレビュー")
    
    buf = io.BytesIO()
    st.session_state.ledger_image.save(buf, format="JPEG")
    st.download_button(
        label="台帳（JPEG）をダウンロード",
        data=buf.getvalue(),
        file_name=f"triage_{st.session_state.patient_name}.jpg",
        mime="image/jpeg"
    )
