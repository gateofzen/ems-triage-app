import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from pdf2image import convert_from_path

# --- QRデータの解析関数 ---
def parse_ems_qr(b64_string):
    try:
        # Base64をデコードしてカンマ区切りのテキストへ
        decoded_bytes = base64.b64decode(b64_string)
        decoded_text = decoded_bytes.decode('utf-8')
        items = decoded_text.split(',')
        
        # 提供されたデータに基づいたマッピング (0から数えたインデックス)
        return {
            "name": items[4].replace('　', ' '),  # 氏名
            "kana": items[5],                   # カナ
            "gender": items[7],                 # 性別
            "complaint": items[10],              # 主訴
            "birthday": items[12],              # 生年月日
            "age": items[13],                   # 年齢
            "jcs": items[14],                   # JCS
            "gcs": f"E{items[15]} V{items[16]} M{items[17]}", # GCS
            "bp_s": items[18],                  # 血圧上
            "bp_d": items[19],                  # 血圧下
            "pr": items[20],                    # 脈拍
            "rr": items[21],                    # 呼吸数
            "bt": items[22],                    # 体温
            "spo2": items[23]                   # SpO2
        }
    except Exception as e:
        st.error(f"解析エラー: {e}")
        return None

# --- アプリの画面構成 ---
st.set_page_config(page_title="トリアージ台帳作成", layout="centered")
st.title("🚑 救急QR 転記アプリ")
st.caption("QRのスクショから台帳を自動作成します。データはメモリ上で処理され、保存されません。")

# 1. 画像アップロード
uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    # メモリ上でQRコードを読み取る
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    opencv_img = cv2.imdecode(file_bytes, 1)
    detector = cv2.QRCodeDetector()
    val, _, _ = detector.detectAndDecode(opencv_img)

    if val:
        data = parse_ems_qr(val)
        if data:
            st.success(f"読み込み成功: {data['name']} 様")
            
            # 2. ユーザーによる追加情報の入力
            with st.form("edit_form"):
                col1, col2 = st.columns(2)
                with col1:
                    status = st.radio("応需結果", ["応需", "不応需"])
                with col2:
                    reason = st.selectbox("不応需理由", ["なし", "1.緊急性なし", "2.ベッド満床", "3.既定の応需不可", "4.医師不在", "その他"])
                
                submitted = st.form_submit_button("台帳PDFを作成")

                if submitted:
                    with st.spinner("台帳を作成中..."):
                        # PDFを画像に変換してテンプレートにする
                        images = convert_from_path("triage_template.pdf", dpi=300)
                        template_img = images[0].convert("RGB")
                        draw = ImageDraw.Draw(template_img)
                        
                        # --- 書き込み位置の調整 (x, y) ---
                        # ※お手元のPDFに合わせてここの数字を微調整してください
                        draw.text((450, 685), data['name'], fill="black")       # 患者名
                        draw.text((1600, 685), f"{data['age']}歳", fill="black") # 年齢
                        draw.text((450, 850), data['complaint'], fill="black")  # 主訴
                        
                        # バイタルサイン欄
                        draw.text((2300, 1205), data['jcs'], fill="black")     # JCS
                        draw.text((2300, 1315), data['rr'], fill="black")      # RR
                        draw.text((2300, 1425), data['pr'], fill="black")      # HR/PR
                        draw.text((2300, 1535), f"{data['bp_s']}/{data['bp_d']}", fill="black") # BP
                        draw.text((2300, 1645), data['spo2'], fill="black")    # SpO2
                        draw.text((2300, 1755), data['bt'], fill="black")      # BT
                        
                        # 応需・不応需の記入
                        draw.text((400, 2050), f"判定: {status} / 理由: {reason}", fill="red")

                        # 3. 結果の表示とダウンロード
                        buf = io.BytesIO()
                        template_img.save(buf, format="JPEG")
                        st.image(template_img, caption="生成されたプレビュー")
                        st.download_button(
                            label="画像を保存する",
                            data=buf.getvalue(),
                            file_name=f"triage_{data['name']}.jpg",
                            mime="image/jpeg"
                        )
    else:
        st.error("QRコードが見つかりませんでした。")