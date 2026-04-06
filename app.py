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
        # 「0」で分割して漢字とカタカナに分ける
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
def draw_maru(draw, xy, radius=60):
    x, y = xy
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=14)

st.set_page_config(page_title="市立札幌病院 台帳作成", layout="centered")
st.title("🚑 トリアージ台帳 自動作成（完成版）")

uploaded_file = st.file_uploader("QRコードのスクリーンショット", type=['png', 'jpg', 'jpeg'])

if uploaded_file:
    img = Image.open(uploaded_file)
    decoded = decode(img)

    if decoded:
        data = parse_ems_qr(decoded[0].data.decode('utf-8'))
        if data:
            st.success(f"読込完了: {data['kanji']} 様")
            
            # --- 入力 UI (リアルタイム反映のため form 外に配置) ---
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
                reason_list = [
                    "1. 緊急性なし", "2. ベッド満床", "3. 既定の応需不可症例", 
                    "4. 対応可能な医師不在", "5. 緊急手術制限中", 
                    "6-A. 医師処置中につき対応困難", "6-B. 看護師処置中につき対応困難", "7. その他"
                ]
                reason_cat = st.selectbox("不応需理由", reason_list)
                reason_free = st.text_input("具体的な理由詳細")
                result_data = {"reason": reason_cat, "reason_free": reason_free}

            if st.button("この内容で台帳を生成する"):
                with st.spinner("台帳を作成中..."):
                    # PDF読み込み
                    pages = convert_from_path("triage_template.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    draw = ImageDraw.Draw(base)
                    
                    f_s = get_font(40)  # よみがな用
                    f_m = get_font(60)  # 標準用
                    f_l = get_font(95)  # 漢字氏名用

                    # --- 1. テキスト描画 (座標の修正) ---
                    draw.text((1350, 430), origin, font=f_m, fill="black") # 依頼元
                    draw.text((400, 680), data['kana'], font=f_s, fill="black") # よみがな(上)
                    draw.text((400, 750), data['kanji'], font=f_l, fill="black") # 漢字(下)
                    draw.text((1650, 750), f"{data['age']} 歳", font=f_m, fill="black") # 年齢
                    draw.text((400, 950), data['complaint'], font=f_m, fill="black") # 主訴

                    # バイタルサイン (右側列)
                    vx = 2300
                    draw.text((vx, 1300), data['jcs'], font=f_m, fill="black")
                    draw.text((vx, 1450), data['rr'], font=f_m, fill="black")
                    draw.text((vx, 1600), data['pr'], font=f_m, fill="black")
                    draw.text((vx, 1750), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")
                    draw.text((vx, 1900), data['spo2'], font=f_m, fill="black")
                    draw.text((vx, 2050), data['bt'], font=f_m, fill="black")

                    # --- 2. ◯（赤丸）の記入 ---
                    # 受診歴
                    if history == "有":
                        draw_maru(draw, (1950, 160)) # 「有」の文字位置
                        draw.text((2100, 150), history_dept, font=f_m, fill="black")
                    else: draw_maru(draw, (2300, 160)) # 「無」

                    # 性別 (男:1950, 女:2200 付近)
                    if "女" in data['gender'] or data['gender'] == "2": draw_maru(draw, (2220, 210))
                    else: draw_maru(draw, (2000, 210))

                    # 判定・転帰 (ページ下部)
                    if decision == "応需":
                        draw_maru(draw, (140, 2400), radius=75) # 「応需」
                        if result_data["init"] == "当直医": draw_maru(draw, (1330, 2390))
                        elif result_data["init"] == "救急科": draw_maru(draw, (1680, 2390))
                        
                        if result_data["outcome"] == "入院": draw_maru(draw, (880, 2520))
                        elif result_data["outcome"] == "帰宅": draw_maru(draw, (880, 2580))
                        
                        if result_data["ward"] == "4東": draw_maru(draw, (1650, 2550))
                        elif result_data["ward"] == "HCU": draw_maru(draw, (1870, 2550))
                    else:
                        draw_maru(draw, (140, 2550), radius=75) # 「不応需」
                        # 不応需理由 1~7 番号の横に◯
                        y_base = 2650
                        idx = ["1","2","3","4","5","6-A","6-B","7"].index(result_data["reason"].split('.')[0].strip())
                        draw_maru(draw, (140, y_base + (idx * 85)), radius=35)
                        # 理由のテキスト内容を自由記載欄または空きスペースに出力
                        draw.text((400, 3100), f"不応需詳細: {result_data['reason']} / {result_data['reason_free']}", font=f_m, fill="black")

                    # --- プレビュー表示 ---
                    st.image(base, caption="生成された台帳イメージ")
                    
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("台帳(JPEG)をダウンロード", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
