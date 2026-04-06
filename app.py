import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode  # 強力な読み取りライブラリ

def parse_ems_qr(b64_string):
    try:
        decoded_bytes = base64.b64decode(b64_string)
        decoded_text = decoded_bytes.decode('utf-8')
        items = decoded_text.split(',')
        # インデックスは提供されたCSVデータに基づき調整
        return {
            "name": items[2].replace('　', ' '), # 氏名 
            "gender": items[5],                 # 性別 
            "complaint": items[8],              # 主訴 
            "age": items[11],                   # 年齢 
            "jcs": items[12],                   # JCS 
            "bp_s": items[16],                  # 血圧上 
            "bp_d": items[17],                  # 血圧下 
            "pr": items[18],                    # 脈拍 
            "rr": items[19],                    # 呼吸 
            "bt": items[20],                    # 体温 
            "spo2": items[21]                   # SpO2 
        }
    except:
        return None

st.title("🚑 トリアージ台帳 自動作成")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    # 画像を読み込み
    img = Image.open(uploaded_file)
    
    # pyzbarでデコード（OpenCVより格段に強いです）
    decoded_objects = decode(img)

    if decoded_objects:
        # 最初のQRコードの内容を取得
        qr_content = decoded_objects[0].data.decode('utf-8')
        data = parse_ems_qr(qr_content)
        
        if data:
            st.success(f"読み込み成功: {data['name']} 様")
            
            with st.form("edit_form"):
                status = st.radio("判定", ["応需", "不応需"])
                reason = st.selectbox("理由", ["なし", "ベッド満床", "医師不在"])
                
                if st.form_submit_button("台帳を作成"):
                    # PDFを画像に変換
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base_img = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base_img)
                    
                    # 座標設定（PDFのレイアウトに合わせて調整）
                    # 患者情報 
                    draw.text((450, 700), data['name'], fill="black")
                    draw.text((1600, 700), f"{data['age']} 歳", fill="black")
                    draw.text((450, 850), data['complaint'], fill="black")
                    
                    # バイタルサイン 
                    draw.text((2300, 1220), data['jcs'], fill="black")
                    draw.text((2300, 1330), data['rr'], fill="black")
                    draw.text((2300, 1440), data['pr'], fill="black")
                    draw.text((2300, 1550), f"{data['bp_s']}/{data['bp_d']}", fill="black")
                    draw.text((2300, 1660), data['spo2'], fill="black")
                    draw.text((2300, 1770), data['bt'], fill="black")
                    
                    # 結果
                    draw.text((400, 2100), f"【{status}】 {reason}", fill="red")

                    buf = io.BytesIO()
                    base_img.save(buf, format="JPEG")
                    st.image(base_img)
                    st.download_button("画像を保存", buf.getvalue(), f"triage_{data['name']}.jpg", "image/jpeg")
    else:
        st.error("QRコードが見つかりませんでした。pyzbarでも認識できない場合は、もう少し明るいスクリーンショットを試してください。")
