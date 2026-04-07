# v18 - 生年月日完全固定座標版
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
from datetime import datetime

def get_font(size):
    for p in ["/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
              "/usr/share/fonts/fonts-japanese-gothic.ttf"]:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def decode_qr_raw(b64_string):
    decoded = base64.b64decode(b64_string).decode("utf-8")
    return decoded.split(",")

def parse_ems_qr(items):
    try:
        dt = datetime.strptime(items[1], "%Y/%m/%d %H:%M:%S")
        weeks = ["月","火","水","木","金","土","日"]
        name_raw = items[4]
        kanji, kana = (name_raw.split("θ",1) if "θ" in name_raw else (name_raw,""))

        field_8 = items[8].strip() if len(items) > 8 else ""
        field_9 = items[9].strip() if len(items) > 9 else ""
        field_10 = items[10].strip() if len(items) > 10 else ""
        field_11 = items[11].strip() if len(items) > 11 else ""
        complaint = ""
        history = ""
        for f in [field_8, field_10, field_11]:
            if f and len(f) <= 30 and not f.isdigit():
                complaint = f; break
        history = field_9 if len(field_9) > len(field_8) else field_8
        if not complaint and history:
            for sep in ["。","、"]:
                if sep in history:
                    c = history[:history.index(sep)]
                    if len(c) <= 30: complaint = c; break

        return {
            "month": str(dt.month), "day": str(dt.day),
            "weekday": weeks[dt.weekday()],
            "hour": f"{dt.hour:02}", "minute": f"{dt.minute:02}",
            "kanji": kanji.strip().replace("　"," "),
            "kana": kana.strip().replace("　"," "),
            "gender": items[5],
            "complaint": complaint, "history": history,
            "birth": items[13],
            "age": items[14] if len(items)>14 else "",
            "jcs": items[15] if len(items)>15 else "",
            "bp_s": items[19] if len(items)>19 else "",
            "bp_d": items[20] if len(items)>20 else "",
            "hr": items[21] if len(items)>21 else "",
            "rr": items[22] if len(items)>22 else "",
            "bt": items[23] if len(items)>23 else "",
            "spo2": items[24] if len(items)>24 else "",
        }
    except Exception as e:
        st.error(f"データ解析失敗: {e}")
        return None

def draw_maru(draw, xy, r=40):
    x, y = xy
    draw.ellipse((x-r,y-r,x+r,y+r), outline="red", width=10)

st.set_page_config(page_title="台帳作成システム", layout="centered")
st.title("🚑 トリアージ台帳 v18")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=["png","jpg","jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    with st.spinner("QRコードをスキャン中..."):
        qr = decode(img)
        if not qr:
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            qr = decode(gray)
        if not qr:
            sharp = cv2.detailEnhance(np.array(img), sigma_s=10, sigma_r=0.15)
            qr = decode(sharp)

    if qr:
        items = decode_qr_raw(qr[0].data.decode("utf-8"))
        data = parse_ems_qr(items)
        if data:
            st.success(f"読込成功: {data['kanji']} 様")

            with st.expander("🔍 QRデータ確認"):
                labels = {1:"依頼日時",4:"氏名",5:"性別",8:"主訴",9:"経過等",
                          13:"生年月日",14:"年齢",15:"JCS",19:"BP上",20:"BP下",
                          21:"HR",22:"RR",23:"SpO2",24:"BT"}
                for i, v in enumerate(items):
                    lbl = f"  ← {labels[i]}" if i in labels else ""
                    st.text(f"[{i:2d}] {v[:80]}{lbl}")

            st.subheader("台帳情報の入力")
            recorder = st.selectbox("記載者", ["前川","森木","小舘","遠藤"])
            col1, col2 = st.columns(2)
            with col1:
                origin = st.text_input("依頼元（救急隊）", value="中央").replace("救急隊","").strip()
                history_yn = st.radio("受診歴", ["無","有"], index=0, horizontal=True)
            with col2:
                history_dept = st.text_input("受診科名（有の場合）")
                decision = st.radio("判定", ["応需","不応需"], index=0, horizontal=True)
            complaint_edit = st.text_input("主訴（編集可）", value=data.get("complaint",""))

            res = {}
            if decision == "応需":
                res["init"] = st.selectbox("初期対応した科", ["当直医","救急科","その他"])
                if res["init"] == "その他":
                    res["init_other"] = st.text_input("初期対応科名")
                res["out"] = st.selectbox("最終転帰", ["入院","帰宅","その他"])
                if res["out"] == "入院":
                    res["ward"] = st.selectbox("病棟", ["4東","HCU","ICU","その他"])
                    if res["ward"] == "その他":
                        res["ward_other"] = st.text_input("病棟名")
                    res["main"] = st.selectbox("主科", ["臨研","救急科","その他"])
                    if res["main"] == "その他":
                        res["main_other"] = st.text_input("主科名")
            else:
                reasons = ["1. 緊急性なし","2. ベッド満床","3. 既定の応需不可症例",
                           "4. 対応可能な医師不在","5. 緊急手術制限中",
                           "6-A. 医師処置中につき対応困難","6-B. 看護師処置中につき対応困難","7. その他"]
                res["reason"] = st.selectbox("不応需理由", reasons)

            if st.button("台帳を生成する", type="primary"):
                with st.spinner("作成中..."):
                    pages = convert_from_path("トリアージ台帳.pdf", dpi=300)
                    base = pages[0].convert("RGB")
                    d = ImageDraw.Draw(base)
                    f_s = get_font(30)
                    f_m = get_font(42)
                    f_l = get_font(68)

                    # ========== 依頼日時 ==========
                    d.text((455,445), data["month"], font=f_m, fill="black")
                    d.text((580,445), data["day"], font=f_m, fill="black")
                    d.text((720,445), data["weekday"], font=f_m, fill="black")
                    d.text((820,445), data["hour"], font=f_m, fill="black")
                    d.text((935,445), data["minute"], font=f_m, fill="black")

                    # ========== 依頼元（救急隊の左） ==========
                    d.text((1270, 495), origin, font=f_m, fill="black")

                    # ========== 記載者 ==========
                    d.text((1750, 300), recorder, font=f_l, fill="black")

                    # ========== 受診歴 ==========
                    if history_yn == "有":
                        draw_maru(d, (1910,480))
                        if history_dept:
                            d.text((1960,445), history_dept, font=f_m, fill="black")
                    else:
                        draw_maru(d, (2180,480))

                    # ========== 患者名 ==========
                    d.text((450,562), data["kana"], font=f_s, fill="black")
                    d.text((450,598), data["kanji"], font=f_l, fill="black")

                    # ========== 生年月日 ==========
                    # 「年」ラベルX=1624, 「月」ラベルX=1787, 「日」ラベルX=2209
                    # 各値を各ラベルの直前に配置（右端基準）
                    b = data["birth"]
                    if len(b) >= 8:
                        f_bd = get_font(36)
                        year_str = b[:4]
                        month_str = b[4:6]
                        day_str = b[6:8]

                        # デバッグ情報表示
                        st.info(f"v18 生年月日: birth='{b}', year='{year_str}', month='{month_str}', day='{day_str}'")

                        # 年号: 「年」(X=1624)の直前に右端を揃える
                        year_right_x = 1618
                        try:
                            yw = int(f_bd.getlength(year_str))
                        except Exception:
                            yw = 80
                        year_x = year_right_x - yw
                        d.text((year_x, 585), year_str, font=f_bd, fill="black")

                        # 月: 「月」(X=1787)の直前に右端を揃える
                        month_right_x = 1780
                        try:
                            mw = int(f_bd.getlength(month_str))
                        except Exception:
                            mw = 40
                        month_x = month_right_x - mw
                        d.text((month_x, 585), month_str, font=f_bd, fill="black")

                        # 日: 「日」(X=2209)の直前に右端を揃える
                        day_right_x = 2202
                        try:
                            dw = int(f_bd.getlength(day_str))
                        except Exception:
                            dw = 40
                        day_x = day_right_x - dw
                        d.text((day_x, 585), day_str, font=f_bd, fill="black")

                        st.info(f"v18 座標: year=({year_x},585) w={yw}, month=({month_x},585) w={mw}, day=({day_x},585) w={dw}")

                    # ========== 年齢 ==========
                    if data["age"]:
                        d.text((1475,680), data["age"], font=f_m, fill="black")

                    # ========== 性別 ==========
                    if data["gender"] == "2" or "女" in data["gender"]:
                        draw_maru(d, (2100,708), r=35)
                    else:
                        draw_maru(d, (1980,708), r=35)

                    # ========== 主訴 ==========
                    if complaint_edit:
                        for i, line in enumerate(textwrap.wrap(complaint_edit, width=45)):
                            d.text((420, 830+i*55), line, font=f_m, fill="black")

                    # ========== 経過等 ==========
                    if data["history"]:
                        for i, line in enumerate(textwrap.wrap(data["history"], width=28)):
                            y = 1000 + i*55
                            if y > 2100: break
                            d.text((420, y), line, font=f_m, fill="black")

                    # ========== バイタルサイン ==========
                    if data["jcs"]:
                        d.text((1960, 1278), data["jcs"], font=f_m, fill="black")
                    for key, field in [("rr","rr"),("hr","hr"),("spo2","spo2"),("bt","bt")]:
                        if data[field]:
                            d.text((1845, {"rr":1390,"hr":1492,"spo2":1695,"bt":1795}[key]), data[field], font=f_m, fill="black")
                    if data["bp_s"] and data["bp_d"]:
                        d.text((1845, 1593), f"{data['bp_s']}/{data['bp_d']}", font=f_m, fill="black")

                    # ========== 判定 ==========
                    if decision == "応需":
                        draw_maru(d, (300,2260), r=48)
                        if res["init"] == "当直医":
                            draw_maru(d, (1167,2260), r=50)
                        elif res["init"] == "救急科":
                            draw_maru(d, (1356,2260), r=50)
                        elif res["init"] == "その他":
                            draw_maru(d, (1574,2260), r=50)
                            if res.get("init_other"):
                                d.text((1720,2235), res["init_other"].rstrip("科"), font=get_font(26), fill="black")

                        if res["out"] == "入院":
                            draw_maru(d, (841,2390), r=30)
                            wp = {"4東":(1433,2440),"HCU":(1546,2440),"ICU":(1660,2440)}
                            if res.get("ward") in wp:
                                draw_maru(d, wp[res["ward"]], r=32)
                            elif res.get("ward") == "その他" and res.get("ward_other"):
                                d.text((1420,2460), res["ward_other"], font=get_font(26), fill="black")
                            if res.get("main") == "臨研":
                                draw_maru(d, (1892,2400), r=35)
                            elif res.get("main") == "救急科":
                                draw_maru(d, (1913,2445), r=35)
                            elif res.get("main") == "その他" and res.get("main_other"):
                                d.text((1890,2475), res["main_other"].rstrip("科"), font=get_font(26), fill="black")
                        elif res["out"] == "帰宅":
                            draw_maru(d, (764,2450), r=30)
                    else:
                        draw_maru(d, (265,2360), r=48)
                        rl = ["1","2","3","4","5","6-A","6-B","7"]
                        rk = res["reason"].split(".")[0].strip()
                        if rk in rl:
                            draw_maru(d, (230, [2553,2603,2653,2703,2753,2803,2853,2902][rl.index(rk)]), r=30)

                    st.image(base, use_container_width=True)
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("📥 台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
    else:
        st.error("QRコードが見つかりません。画像を拡大するか、明るい場所で撮り直してください。")
