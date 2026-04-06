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

# --- QR解析 (主訴[9]と経過[8]を分離) ---
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode('utf-8')
        items = decoded.split(',')
        name_raw = items[4]
        # 「θ」で分割して漢字とカタカナに分ける
        kanji, kana = name_raw.split('θ', 1) if 'θ' in name_raw else (name_raw, "")
        
        return {
            "kanji": kanji.strip().replace('　', ' '),
            "kana": kana.strip().replace('　', ' '),
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

# --- 赤丸描画 (不透明度を調整) ---
def draw_maru(draw, xy, radius=65):
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=14)

st.set_page_config(page_title="市立札幌病院 台帳作成", layout="centered")
st.title("🚑 トリアージ台帳 自動作成（完成版）")

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
                origin_input = st.text_input("依頼元（〇〇救急隊）", value="中央")
                # 「救急隊」という文字を重複させないための処理
                origin_name = origin_input.replace("救急隊", "")
                history = st.radio("受診歴", ["無", "有"], horizontal=True)
                history_dept = st.text_input("受診科（有の場合）")
            
            st.divider()
            decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
            
            result_data = {}
            if decision == "応需":
                init_dept = st.selectbox("初期対応した科", ["当直医", "救急科", "その他"])
                outcome = st.selectbox("最終転帰", ["入院", "帰宅", "その他"])
                ward = ""; main_dept = ""
                if outcome == "入院":
                    c1, c2 = st.columns(2)
                    with c1: ward = st.selectbox("病棟", ["4東", "HCU", "ICU", "その他"])
                    with c2: main_dept = st.selectbox("主科", ["臨研", "救急科", "その他"])
                result_data = {"init": init_dept, "outcome": outcome, "ward": ward, "main": main_dept}
            else:
                reasons = ["1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可", "4. 対応可能な医師不在", "5. 緊急手術制限中", "6-A. 医師処置中につき対応困難", "6-B. 看護師処置中につき対応困難", "7. その他"]
                reason_cat = st.selectbox("不応需理由", reasons)
                result_data = {"reason": reason_cat}

            if st.button("この内容で台帳を生成する"):
                with st.spinner("台帳を作成中..."):
                    # PDFを300dpiで画像化
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    
                    f_s = get_font(38)  # ふりがな用
                    f_m = get_font(58)  # 標準用
                    f_l = get_font(95)  # 漢字氏名用

                    # --- 1. テキスト描画 (座標の精密調整) ---
                    # 依頼元（救急隊の前に配置）
                    draw.text((1150, 425), origin_name, font=f_m, fill="black")
                    
                    # 患者名
                    draw.text((450, 520), data['kana'], font=f_s, fill="black")  # ふりがな(上)
                    draw.text((450, 595), data['kanji'], font=f_l, fill="black") # 漢字氏名(下)
                    draw.text((1650, 600), f"{data['age']} 歳", font=f_m, fill="black") # 年齢
                    
                    # 主訴（主訴欄のみに記入）
                    draw.text((450, 780), data['complaint'], font=f_m, fill="black")

                    # 経過等（現病歴をこちらに記入）
                    history_lines = textwrap.wrap(data['history'], width=38)
                    for i, line in enumerate(history_lines):
                        draw.text((450, 1050 + (i * 75)), line, font=f_m, fill="black")

                    # バイタルサイン (右側枠の座標を修正)
                    vx = 2300
                    draw.text((vx, 1225), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 1335), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 1445), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 1555), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 1665), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 1775), data['bt'], font=f_m, fill="black")

                    # --- 2. ◯（赤丸）の記入 (位置を文字の上に修正) ---
                    # 受診歴
                    if history == "有": draw_maru(draw, (1935, 140)) # 有
                    else: draw_maru(draw, (2350, 140)) # 無
                    if history == "有": draw.text((2150, 140), history_dept, font=f_m, fill="black")

                    # 性別 (男:2000, 女:2220)
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2220, 200))
                    else: draw_maru(draw, (2000, 200))

                    # 判定 (応需:y=2060, 不応需:y=2150 付近)
                    if decision == "応需":
                        draw_maru(draw, (140, 2060), radius=75) # 「応需」
                        if result_data["init"] == "当直医": draw_maru(draw, (1330, 2055))
                        if result_data["outcome"] == "入院": draw_maru(draw, (830, 2125))
                        elif result_data["outcome"] == "帰宅": draw_maru(draw, (830, 2155))
                    else:
                        draw_maru(draw, (140, 2150), radius=75) # 「不応需」
                        idx = ["1", "2", "3", "4", "5", "6-A", "6-B", "7"].index(result_data["reason"].split('.')[0])
                        draw_maru(draw, (140, 2220 + (idx * 55)), radius=25)

                    # --- プレビューとダウンロード ---
                    st.image(base, caption="台帳プレビュー")
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
