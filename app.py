# v21 - トリアージ台帳2.png対応版（全座標修正済み）
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
        if os.path.exists(p): return ImageFont.truetype(p, size)
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

# =================================================================
# テンプレート: トリアージ台帳2.png (1327x2000)
# グリッド H: 3,36,122,222,289,356,490,557,691,758,825,892,959,1026,1093,1294,1395,1428,1528,1797,1998
# グリッド V: 11,135,268,543,676,911,1043,1309
# =================================================================

st.set_page_config(page_title="台帳作成システム", layout="centered")
st.title("🚑 トリアージ台帳 v21")

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
                    f18 = get_font(18)
                    f24 = get_font(24)
                    f28 = get_font(28)
                    f36 = get_font(36)
                    f44 = get_font(44)

                    # ===== 記載者（セル中央に大きく）=====
                    # H2セル: V=911-1309, Y=36-122
                    rec_w = f44.getlength(recorder)
                    rec_x = int(911 + (398 - rec_w) / 2)
                    d.text((rec_x, 55), recorder, font=f44, fill="black")

                    # ===== 依頼日時 =====
                    # B-Dセル: V=135-543, Y=122-222 (/()：消去済み)
                    dt_str = f"{data['month']}/{data['day']}（{data['weekday']}）{data['hour']}:{data['minute']}"
                    d.text((155, 148), dt_str, font=f28, fill="black")

                    # ===== 依頼元 救急隊名（F-Gセル: V=676-911）=====
                    d.text((690, 148), origin, font=f28, fill="black")

                    # ===== 受診歴 =====
                    if history_yn == "有":
                        draw_maru(d, (1100, 165))
                        if history_dept:
                            d.text((1130, 150), history_dept, font=f24, fill="black")
                    else:
                        draw_maru(d, (1270, 165))

                    # ===== 患者名（セル中央に大きく）=====
                    # B-Eセル: V=135-543, Y=222-356
                    d.text((170, 232), data["kana"], font=f18, fill="black")
                    name_w = f44.getlength(data["kanji"])
                    name_x = int(135 + (408 - name_w) / 2)
                    d.text((name_x, 260), data["kanji"], font=f44, fill="black")

                    # ===== 生年月日（右寄せ配置）=====
                    # 年label左端=1015, 月label左端=1150, 日label左端=1284
                    b = data["birth"]
                    if len(b) >= 8:
                        f_bd = f24
                        for val, lbl_x in [(b[:4], 1010), (b[4:6], 1145), (b[6:8], 1279)]:
                            w = f_bd.getlength(val)
                            d.text((int(lbl_x - w), 245), val, font=f_bd, fill="black")

                    # ===== 年齢（ラベルの右に）=====
                    if data["age"]:
                        d.text((785, 308), data["age"], font=f28, fill="black")

                    # ===== 性別 =====
                    if data["gender"] == "2" or "女" in data["gender"]:
                        draw_maru(d, (1105, 320), r=18)
                    else:
                        draw_maru(d, (1010, 320), r=18)

                    # ===== 主訴 =====
                    if complaint_edit:
                        for i, line in enumerate(textwrap.wrap(complaint_edit, width=38)):
                            d.text((150, 385+i*30), line, font=f24, fill="black")

                    # ===== 経過等 =====
                    if data["history"]:
                        for i, line in enumerate(textwrap.wrap(data["history"], width=22)):
                            y = 530 + i*28
                            if y > 1260: break
                            d.text((150, y), line, font=f24, fill="black")

                    # ===== バイタルサイン =====
                    # 値セル: V=1043-1309 内、各行に配置
                    vx = 1060
                    if data["jcs"]:
                        d.text((vx+55, 715), data["jcs"], font=f28, fill="black")
                    if data["rr"]:
                        d.text((vx, 775), data["rr"], font=f28, fill="black")
                    if data["hr"]:
                        d.text((vx, 845), data["hr"], font=f28, fill="black")
                    if data["bp_s"] and data["bp_d"]:
                        d.text((vx, 915), f"{data['bp_s']}/{data['bp_d']}", font=f28, fill="black")
                    if data["spo2"]:
                        d.text((vx, 978), data["spo2"], font=f28, fill="black")
                    if data["bt"]:
                        d.text((vx, 1048), data["bt"], font=f28, fill="black")

                    # ===== 判定 =====
                    if decision == "応需":
                        draw_maru(d, (74, 1355), r=26)  # 応需

                        # 初期対応した科
                        if res["init"] == "当直医":
                            draw_maru(d, (615, 1345), r=27)
                        elif res["init"] == "救急科":
                            draw_maru(d, (737, 1345), r=27)
                        elif res["init"] == "その他":
                            draw_maru(d, (888, 1345), r=27)
                            if res.get("init_other"):
                                d.text((920, 1332), res["init_other"].rstrip("科"), font=f18, fill="black")

                        # 最終転帰
                        if res["out"] == "入院":
                            draw_maru(d, (345, 1445), r=16)
                            # 病棟
                            wp = {"4東":(790,1488),"HCU":(861,1488),"ICU":(943,1488)}
                            if res.get("ward") in wp:
                                draw_maru(d, wp[res["ward"]], r=18)
                            elif res.get("ward") == "その他" and res.get("ward_other"):
                                d.text((770, 1505), res["ward_other"], font=f18, fill="black")
                            # 主科
                            if res.get("main") == "臨研":
                                draw_maru(d, (1095, 1457), r=18)
                            elif res.get("main") == "救急科":
                                draw_maru(d, (1095, 1480), r=18)
                            elif res.get("main") == "その他" and res.get("main_other"):
                                d.text((1095, 1500), res["main_other"].rstrip("科"), font=f18, fill="black")
                        elif res["out"] == "帰宅":
                            draw_maru(d, (345, 1470), r=16)
                    else:
                        draw_maru(d, (74, 1420), r=26)  # 不応需
                        rl = ["1","2","3","4","5","6-A","6-B","7"]
                        ry = [1543, 1573, 1603, 1633, 1663, 1693, 1725, 1785]
                        rk = res["reason"].split(".")[0].strip()
                        if rk in rl:
                            draw_maru(d, (148, ry[rl.index(rk)]), r=16)

                    # ===== 出力 =====
                    st.image(base, use_container_width=True)
                    buf = io.BytesIO()
                    base.save(buf, format="JPEG", quality=95)
                    st.download_button("📥 台帳を保存", buf.getvalue(), f"triage_{data['kanji']}.jpg", "image/jpeg")
    else:
        st.error("QRコードが見つかりません。画像を拡大するか、明るい場所で撮り直してください。")
