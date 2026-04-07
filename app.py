# v20 - ユーザー提供PNGテンプレート使用版
import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import io
import base64
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
    return base64.b64decode(b64_string).decode("utf-8").split(",")

def parse_ems_qr(items):
    try:
        dt = datetime.strptime(items[1], "%Y/%m/%d %H:%M:%S")
        weeks = ["月","火","水","木","金","土","日"]
        name_raw = items[4]
        kanji, kana = (name_raw.split("θ",1) if "θ" in name_raw else (name_raw,""))
        field_8 = items[8].strip() if len(items)>8 else ""
        field_9 = items[9].strip() if len(items)>9 else ""
        field_10 = items[10].strip() if len(items)>10 else ""
        field_11 = items[11].strip() if len(items)>11 else ""
        complaint = ""
        history = field_9 if len(field_9) > len(field_8) else field_8
        for f in [field_8, field_10, field_11]:
            if f and len(f) <= 30 and not f.isdigit():
                complaint = f; break
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

def draw_maru(draw, xy, r=22):
    x, y = xy
    draw.ellipse((x-r,y-r,x+r,y+r), outline="red", width=5)

# ============================================================
# 座標定数（1339x2000 PNG テンプレート基準）
# グリッド H: 0,34,120,221,288,355,489,556,...,1294,1394,1428,1529,1797,1998
# グリッド V: 10,136,270,548,683,920,1053,1322
# ============================================================

st.set_page_config(page_title="台帳作成システム", layout="centered")
st.title("🚑 トリアージ台帳 v20")

uploaded_file = st.file_uploader("QRコードのスクリーンショットを選択", type=["png","jpg","jpeg"])

if uploaded_file:
    img = Image.open(uploaded_file)
    with st.spinner("QRコードをスキャン中..."):
        qr = decode(img)
        if not qr:
            qr = decode(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY))
        if not qr:
            qr = decode(cv2.detailEnhance(np.array(img), sigma_s=10, sigma_r=0.15))

    if qr:
        items = decode_qr_raw(qr[0].data.decode("utf-8"))
        data = parse_ems_qr(items)
        if data:
            st.success(f"読込成功: {data['kanji']} 様")

            with st.expander("🔍 QRデータ確認"):
                labels = {1:"依頼日時",4:"氏名",5:"性別",8:"主訴",9:"経過等",
                          13:"生年月日",14:"年齢",15:"JCS",19:"BP上",20:"BP下",
                          21:"HR",22:"RR",23:"BT",24:"SpO2"}
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
                    base = Image.open("template.png").convert("RGB")
                    d = ImageDraw.Draw(base)
                    f16 = get_font(16)
                    f20 = get_font(20)
                    f22 = get_font(22)
                    f36 = get_font(36)

                    # ===== 記載者 (H2セル: V=920-1187, Y=34-120) =====
                    d.text((950, 60), recorder, font=f36, fill="black")

                    # ===== 依頼日時 (Y=120-221) =====
                    d.text((235,150), data["month"], font=f22, fill="black")
                    d.text((295,150), data["day"], font=f22, fill="black")
                    d.text((370,150), data["weekday"], font=f22, fill="black")
                    d.text((420,150), data["hour"], font=f22, fill="black")
                    d.text((480,150), data["minute"], font=f22, fill="black")

                    # ===== 依頼元 (F3セル: V=548-683, Y=120-221) =====
                    d.text((580, 140), origin, font=f20, fill="black")

                    # ===== 受診歴 (I3セル: V=1053-1322) =====
                    if history_yn == "有":
                        draw_maru(d, (1100, 165))
                        if history_dept:
                            d.text((1140, 155), history_dept, font=f20, fill="black")
                    else:
                        draw_maru(d, (1280, 165))

                    # ===== 患者名 (B6セル: V=136-548, Y=221-355) =====
                    d.text((155, 228), data["kana"], font=f16, fill="black")
                    d.text((155, 248), data["kanji"], font=f36, fill="black")

                    # ===== 生年月日 (検証済み) =====
                    b = data["birth"]
                    if len(b) >= 8:
                        d.text((960, 240), b[:4], font=f22, fill="black")   # 年
                        d.text((1110, 240), b[4:6], font=f22, fill="black") # 月
                        d.text((1250, 240), b[6:8], font=f22, fill="black") # 日

                    # ===== 年齢 (G8セル) =====
                    if data["age"]:
                        d.text((700, 310), data["age"], font=f22, fill="black")

                    # ===== 性別 =====
                    if data["gender"] == "2" or "女" in data["gender"]:
                        draw_maru(d, (1125, 320), r=18)
                    else:
                        draw_maru(d, (1015, 320), r=18)

                    # ===== 主訴 (B10セル: V=136-1322, Y=355-489) =====
                    if complaint_edit:
                        for i, line in enumerate(textwrap.wrap(complaint_edit, width=45)):
                            d.text((150, 380+i*28), line, font=f22, fill="black")

                    # ===== 経過等 (B14セル: V=136-683, Y=489-1294) =====
                    if data["history"]:
                        for i, line in enumerate(textwrap.wrap(data["history"], width=22)):
                            y = 530 + i*28
                            if y > 1260: break
                            d.text((150, y), line, font=f22, fill="black")

                    # ===== バイタルサイン =====
                    vx = 990
                    if data["jcs"]:
                        d.text((vx+60, 700), data["jcs"], font=f22, fill="black")
                    if data["rr"]:
                        d.text((vx, 765), data["rr"], font=f22, fill="black")
                    if data["hr"]:
                        d.text((vx, 835), data["hr"], font=f22, fill="black")
                    if data["bp_s"] and data["bp_d"]:
                        d.text((vx, 905), f"{data['bp_s']}/{data['bp_d']}", font=f22, fill="black")
                    if data["spo2"]:
                        d.text((vx, 970), data["spo2"], font=f22, fill="black")
                    if data["bt"]:
                        d.text((vx, 1040), data["bt"], font=f22, fill="black")

                    # ===== 判定 =====
                    if decision == "応需":
                        draw_maru(d, (74, 1335), r=26)
                        # 初期対応した科
                        if res["init"] == "当直医":
                            draw_maru(d, (620, 1340), r=27)
                        elif res["init"] == "救急科":
                            draw_maru(d, (735, 1340), r=27)
                        elif res["init"] == "その他":
                            draw_maru(d, (855, 1340), r=27)
                            if res.get("init_other"):
                                d.text((920, 1330), res["init_other"].rstrip("科"), font=f16, fill="black")
                        # 最終転帰
                        if res["out"] == "入院":
                            draw_maru(d, (380, 1455), r=16)
                            # 病棟
                            wp = {"4東":(770,1475),"HCU":(830,1475),"ICU":(890,1475)}
                            if res.get("ward") in wp:
                                draw_maru(d, wp[res["ward"]], r=18)
                            elif res.get("ward") == "その他" and res.get("ward_other"):
                                d.text((770, 1495), res["ward_other"], font=f16, fill="black")
                            # 主科
                            if res.get("main") == "臨研":
                                draw_maru(d, (1100, 1450), r=18)
                            elif res.get("main") == "救急科":
                                draw_maru(d, (1100, 1475), r=18)
                            elif res.get("main") == "その他" and res.get("main_other"):
                                d.text((1095, 1500), res["main_other"].rstrip("科"), font=f16, fill="black")
                        elif res["out"] == "帰宅":
                            draw_maru(d, (380, 1480), r=16)
                    else:
                        draw_maru(d, (74, 1400), r=26)
                        rl = ["1","2","3","4","5","6-A","6-B","7"]
                        reason_y = [1543, 1575, 1605, 1635, 1665, 1695, 1725, 1785]
                        rk = res["reason"].split(".")[0].strip()
                        if rk in rl:
                            draw_maru(d, (148, reason_y[rl.index(rk)]), r=16)

                    # ===== 出力 =====
                    st.image(base, use_container_width=True)
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("📥 台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
    else:
        st.error("QRコードが見つかりません。画像を拡大するか、明るい場所で撮り直してください。")
