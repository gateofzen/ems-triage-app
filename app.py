import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import base64
from pdf2image import convert_from_path
from pyzbar.pyzbar import decode
import os

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

# --- QR解析 (0の除去と上下分割) ---
def parse_ems_qr(b64_string):
    try:
        decoded = base64.b64decode(b64_string).decode('utf-8')
        items = decoded.split(',')
        name_raw = items[4]
        if '0' in name_raw:
            kanji, kana = name_raw.split('0', 1)
        else:
            kanji, kana = name_raw, ""
        
        return {
            "kanji": kanji.strip().replace('　', ' '),
            "kana": kana.strip().replace('　', ' '),
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

# --- 赤丸描画 ---
def draw_maru(draw, xy, radius=55):
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=12)

st.set_page_config(page_title="市立札幌病院 台帳作成")
st.title("🚑 トリアージ台帳 自動作成（最終調整版）")

uploaded_file = st.file_uploader("QRコードのスクリーンショット", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded = decode(img)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"読込成功: {data['kanji']} 様")
            
            # --- 入力 UI (動的表示のため form の外に配置) ---
            st.subheader("台帳情報の入力")
            col1, col2 = st.columns(2)
            with col1:
                origin = st.text_input("依頼元（救急隊）", value="中央救急隊")
                history = st.radio("受診歴", ["無", "有"], horizontal=True)
                history_dept = st.text_input("受診科（有の場合）")
            
            st.divider()
            decision = st.radio("判定", ["応需", "不応需"], horizontal=True)
            
            # 応需・不応需に応じた入力項目の出し分け
            result_data = {}
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
                        ward_free = st.text_input("その他病棟名") if ward == "その他" else ""
                    with c2:
                        main_dept = st.selectbox("主科", ["臨研", "救急科", "その他"])
                        main_free = st.text_input("その他主科名") if main_dept == "その他" else ""
                result_data = {"init": init_dept, "outcome": outcome, "ward": ward, "main": main_dept}
            else:
                reason_cat = st.selectbox("不応需理由", ["1", "2", "3", "4", "5", "6-A", "6-B", "7"])
                reason_free = st.text_input("具体的な理由 (任意)")
                result_data = {"reason": reason_cat}

            if st.button("台帳を生成する"):
                with st.spinner("作成中..."):
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    
                    f_s = get_font(38)
                    f_m = get_font(58)
                    f_l = get_font(85)

                    # --- 1. テキスト描画 (座標の大幅見直し) ---
                    draw.text((1300, 420), origin, font=f_m, fill="black") # 依頼元
                    draw.text((380, 520), data['kana'], font=f_s, fill="black") # よみがな(上)
                    draw.text((380, 595), data['kanji'], font=f_l, fill="black") # 漢字(下)
                    draw.text((1600, 600), f"{data['age']} 歳", font=f_m, fill="black") # 年齢
                    draw.text((200, 800), data['complaint'], font=f_m, fill="black") # 主訴

                    # バイタルサイン (右側枠)
                    vx = 2220
                    draw.text((vx, 1235), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 1345), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 1455), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 1565), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 1675), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 1785), data['bt'], font=f_m, fill="black")

                    # --- 2. ◯（赤丸）の記入 ---
                    # 受診歴
                    if history == "有":
                        draw_maru(draw, (1940, 435))
                        draw.text((2050, 425), history_dept, font=f_m, fill="black")
                    else: draw_maru(draw, (2285, 435))

                    # 性別
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2230, 595))
                    else: draw_maru(draw, (2005, 595))

                    # 判定結果 (応需/不応需)
                    if decision == "応需":
                        draw_maru(draw, (130, 2075), radius=65) # 「応需」
                        if result_data["init"] == "当直医": draw_maru(draw, (1335, 2060))
                        elif result_data["init"] == "救急科": draw_maru(draw, (1685, 2060))
                        
                        if result_data["outcome"] == "入院": draw_maru(draw, (835, 2130))
                        elif result_data["outcome"] == "帰宅": draw_maru(draw, (835, 2160))
                        
                        if result_data["ward"] == "4東": draw_maru(draw, (1635, 2145), radius=45)
                        elif result_data["ward"] == "HCU": draw_maru(draw, (1855, 2145), radius=45)
                        
                        if result_data["main"] == "臨研": draw_maru(draw, (2305, 2115), radius=45)
                        elif result_data["main"] == "救急科": draw_maru(draw, (2305, 2155), radius=45)
                    else:
                        draw_maru(draw, (130, 2185), radius=65) # 「不応需」
                        # 番号 1~7 への◯
                        idx = ["1","2","3","4","5","6-A","6-B","7"].index(result_data["reason"])
                        draw_maru(draw, (140, 2225 + (idx * 56)), radius=28)

                    # --- プレビュー表示 ---
                    st.image(base, caption="完成イメージ")
                    
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("台帳をダウンロード", buf.getvalue(), "triage_final.jpg", "image/jpeg")
