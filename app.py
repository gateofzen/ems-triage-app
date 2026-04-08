import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont
import io, os, json
from datetime import date, datetime

st.set_page_config(page_title="ホットライン受付対応表", layout="centered")
st.title("📞 ホットライン受付対応表")

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
]
_FONT_PATH = None
for _p in FONT_CANDIDATES:
    if os.path.exists(_p):
        _FONT_PATH = _p; break
if _FONT_PATH is None:
    st.error("⚠️ 日本語フォントが見つかりません。packages.txt に fonts-noto-cjk を追加してください。")

def get_font(size):
    if _FONT_PATH:
        return ImageFont.truetype(_FONT_PATH, max(10, size))
    return ImageFont.load_default()

# ===== ファイル永続化 =====
CASES_FILE = "hl_cases.json"

def load_cases():
    if os.path.exists(CASES_FILE):
        try:
            with open(CASES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def save_cases(cases):
    try:
        with open(CASES_FILE, "w", encoding="utf-8") as f:
            json.dump(cases, f, ensure_ascii=False, indent=2)
    except: pass

# ===== 時刻から勤務帯判定 =====
def time_to_shift(time_str):
    """'HH:MM' → '日勤' or '夜勤'。8:30-16:30=日勤"""
    try:
        h, m = map(int, time_str.split(":"))
        minutes = h * 60 + m
        if 8*60+30 <= minutes < 16*60+30:
            return "日勤"
        return "夜勤"
    except:
        return "夜勤"

RESCUE_TEAMS = [
    "","中央","大通","桑園","山鼻","北","篠路","新光","東","栄","東苗穂",
    "白石","菊水","厚別","厚別西","豊平","西岡","平岸","清田","南","定山渓",
    "西","前田","西野","手稲","石山","あいの里","北野","警防","豊水","幌西",
    "藤野","八軒","北郷","札苗","苗穂","北エルム","東モエレ",
]
LEADERS   = ["前川","中嶋","森木","小舘","遠藤","提嶋"]
WEEKDAYS  = ["月","火","水","木","金","土","日"]
BLOCK_TOPS = [168, 460, 749, 1039, 1329, 1619]
TIME_OPTIONS = [""] + [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0,60,5)]

def render_hotline(header, cases, sheet_no=1):
    base = Image.open("hotline.png").convert("RGB")
    W, H = base.size
    sx=W/1413; sy=H/2000; s=min(sx,sy)
    def X(v): return int(v*sx)
    def Y(v): return int(v*sy)
    def R(v): return max(4,int(v*s))
    def F(v): return get_font(max(8,int(v*s)))
    def dm(cx,cy,r=14):
        d.ellipse([X(cx)-R(r),Y(cy)-R(r),X(cx)+R(r),Y(cy)+R(r)],outline="black",width=max(2,R(4)))

    def draw_check(cx, cy):
        """□の中にチェックマークを描画"""
        s = R(10)
        x, y = X(cx), Y(cy)
        d.line([(x-s, y), (x-s//3, y+s), (x+s, y-s)], fill="black", width=max(2,R(3)))

    d = ImageDraw.Draw(base)
    f34=F(34); f30=F(30); f26=F(26); f22=F(22)

    # ===== No.（ヘッダー行 Y=109-168, X=0-194の中央）=====
    f_no = F(42)
    no_str = str(sheet_no)
    bb = d.textbbox((0,0), no_str, font=f_no)
    tw = bb[2]-bb[0]; th = bb[3]-bb[1]
    no_x = X(104 + (194-104-tw)//2 + 8)   # 少し右
    no_y = Y(109)                            # 上端ぴったり
    d.text((no_x, no_y), no_str, font=f_no, fill="black")

    # ===== ヘッダー =====
    dt = header["date"] if isinstance(header["date"],date) else date.fromisoformat(str(header["date"]))
    wd = WEEKDAYS[dt.weekday()]
    d.text((X(260),Y(114)),str(dt.year),font=f30,fill="black")
    d.text((X(420),Y(114)),str(dt.month),font=f30,fill="black")
    d.text((X(485),Y(114)),str(dt.day),font=f30,fill="black")
    d.text((X(590),Y(114)),wd,font=f30,fill="black")
    shift = header["shift"]
    if shift=="日勤": dm(701,138,r=18)
    else: dm(778,138,r=18)
    d.text((X(1080),Y(106)),header["leader"],font=f34,fill="black")

    for i,case in enumerate(cases):
        if i>=6: break
        yt=BLOCK_TOPS[i]
        yn=yt-5; yc=yt+21; yg=yt+60; yn2=yt+131
        yr1=yt+222; yr2=yt+247; yr3=yt+276

        if case.get("time"): d.text((X(300),Y(yn)),case["time"],font=f26,fill="black")
        if case.get("req_count")=="初回": dm(620,yn+20,r=16)
        else:
            num=(case.get("req_count") or "").replace("回目","").replace("回","")
            if num: d.text((X(718),Y(yn)),num,font=f26,fill="black")
        if case.get("team"): d.text((X(970),Y(yn)),case["team"],font=f26,fill="black")
        if case.get("age"): d.text((X(235),Y(yc)),str(case["age"]),font=f26,fill="black")
        if case.get("gender")=="M": dm(432,yc+26,r=14)
        elif case.get("gender")=="F": dm(500,yc+26,r=14)

        lines=[]; line=""
        for ch in (case.get("summary") or ""):
            line+=ch
            if len(line)>=30: lines.append(line); line=""
        if line: lines.append(line)
        for li,ln in enumerate(lines[:2]):
            d.text((X(168),Y(yg+li*30)),ln,font=f22,fill="black")

        outcome=case.get("outcome","")
        tenki_map={"搬入":(172,yn2),"お断り":(270,yn2),"2次やかかりつけ医案内":(500,yn2),"患者都合":(743,yn2),"その他":(172,yt+160)}
        if outcome in tenki_map:
            cx,cy = tenki_map[outcome]
            draw_check(cx,cy)

        if outcome=="お断り":
            reason=case.get("reason","")
            if reason=="1_満床":
                dm(292,yr1,r=12)  # yr3 cluster[0]と同じX=292
                sub_map={
                    "満床・満床に準ずる状態":(503,yr1),  # 519→503（少し左）
                    "ICU個室(感染等)満床":    (730,yr1),  # cluster[19-20]間・左 X=730
                    "熱傷患者受入不能":       (948,yr1),  # cluster[27]の左 X=948
                }
                if case.get("reason1_sub") in sub_map:
                    draw_check(*sub_map[case["reason1_sub"]])
            elif reason=="2_マンパワー":
                dm(295,yr2,r=12)
                sub_map2={"他患の処置・手術等で余力なし":(465,yr2),"別の救急患者の搬入直前・直後":(735,yr2)}
                if case.get("reason2_sub") in sub_map2:
                    draw_check(*sub_map2[case["reason2_sub"]])
            elif reason=="3_院内専門科":
                dm(292,yr3,r=12)  # cluster[0] X=292
                if case.get("reason3_dept"):
                    d.text((X(415),Y(yr3-20)),case["reason3_dept"].rstrip("科"),font=f22,fill="black")
                sub_map3={
                    "当該科手術中":(673,yr3),  # cluster[11-12]間・中央 X=673
                    "学会等で不在":(820,yr3),  # cluster[19-20]間・中央右 X=820
                    "麻酔科対応不能":(960,yr3), # cluster[24-25]間・中央右 X=960
                }
                if case.get("reason3_sub") in sub_map3:
                    draw_check(*sub_map3[case["reason3_sub"]])
    return base

# ===== セッション状態 =====
if "hl_cases" not in st.session_state:
    st.session_state.hl_cases = load_cases()
if "hl_header" not in st.session_state:
    st.session_state.hl_header = {"date": date.today().isoformat(), "leader": "前川"}

# ===== ヘッダー =====
st.subheader("📋 基本情報")
c1,c2 = st.columns(2)
with c1:
    saved_date = st.session_state.hl_header.get("date", date.today().isoformat())
    input_date = st.date_input("日付", value=date.fromisoformat(str(saved_date)))
with c2:
    leader = st.selectbox("リーダー医師名", LEADERS,
                          index=LEADERS.index(st.session_state.hl_header.get("leader","前川")))
st.session_state.hl_header = {"date": input_date.isoformat(), "leader": leader}

# ===== 登録済み一覧 =====
st.divider()
cases = st.session_state.hl_cases
n = len(cases)

# 日勤・夜勤で件数集計
nisshin = [c for c in cases if time_to_shift(c.get("time","")) == "日勤"]
yashin  = [c for c in cases if time_to_shift(c.get("time","")) == "夜勤"]
st.markdown(f"**🚑 登録済み: {n}件（日勤 {len(nisshin)}件 / 夜勤 {len(yashin)}件）**")

# 編集モード管理
if "hl_editing" not in st.session_state:
    st.session_state.hl_editing = None

if n > 0:
    st.markdown("""<style>
    [data-testid="stHorizontalBlock"] > div { min-width:0!important; }
    button[kind="secondary"] { padding:1px 6px!important; font-size:11px!important; min-height:24px!important; height:24px!important; line-height:1!important; }
    </style>""", unsafe_allow_html=True)

    for i, c in enumerate(cases):
        t = c.get("time","--:--")
        team = c.get("team","") or "不明"
        outcome = c.get("outcome","")
        ci, ce, cd = st.columns([8, 1, 1])
        with ci:
            age_str = f"{c.get('age','')}才" if c.get("age") else ""
            gender_str = c.get("gender","")
            info = " ".join(filter(None, [age_str, gender_str]))
            st.markdown(f"<div style='font-size:15px;padding:4px 0'><b>{i+1}.{t}</b> {team} {info} →{outcome}</div>",
                        unsafe_allow_html=True)
        with ce:
            if st.button("✏", key=f"hl_edit_{i}", help="編集"):
                st.session_state.hl_editing = i
                st.rerun()
        with cd:
            if st.button("🗑", key=f"hl_del_{i}", help="削除"):
                st.session_state.hl_cases.pop(i)
                save_cases(st.session_state.hl_cases)
                if st.session_state.hl_editing == i:
                    st.session_state.hl_editing = None
                st.rerun()

# ===== 編集モード =====
hl_edit_idx = st.session_state.hl_editing
if hl_edit_idx is not None and 0 <= hl_edit_idx < len(cases):
    ec = cases[hl_edit_idx]
    st.divider()
    st.subheader(f"✏️ 症例 {hl_edit_idx+1} を編集")
    ec1,ec2 = st.columns(2)
    with ec1:
        e_time = st.selectbox("時刻", TIME_OPTIONS,
            index=TIME_OPTIONS.index(ec["time"]) if ec.get("time") in TIME_OPTIONS else 0,
            key="e_time")
        if e_time: st.caption(f"→ **{time_to_shift(e_time)}**")
    with ec2:
        _team_val = ec.get("team","")
        _team_opts = RESCUE_TEAMS + ["その他（直接入力）"]
        _team_idx = RESCUE_TEAMS.index(_team_val) if _team_val in RESCUE_TEAMS else (len(RESCUE_TEAMS) if _team_val else 0)
        e_team_sel = st.selectbox("依頼先救急隊", _team_opts, index=_team_idx, key="e_team")
        if e_team_sel == "その他（直接入力）":
            e_team = st.text_input("救急隊名を入力", value=_team_val if _team_val not in RESCUE_TEAMS else "", key="e_team_other", placeholder="例: 石狩")
        else:
            e_team = e_team_sel
    ec3,ec4,ec5 = st.columns(3)
    with ec3:
        e_req = st.selectbox("依頼回数", ["初回","2回目","3回目","4回目以上"],
            index=["初回","2回目","3回目","4回目以上"].index(ec["req_count"]) if ec.get("req_count") in ["初回","2回目","3回目","4回目以上"] else 0,
            key="e_req")
    with ec4:
        e_age = st.number_input("年齢（才）", min_value=0, max_value=120,
            value=int(ec["age"]) if ec.get("age") else 0, step=1, key="e_age")
    with ec5:
        gender_opts = ["M","F","未記載"]
        e_gender = st.radio("性別", gender_opts, horizontal=True,
            index=gender_opts.index(ec["gender"]) if ec.get("gender") in gender_opts else 2,
            key="e_gender")
    e_summary = st.text_area("概略", value=ec.get("summary",""), height=70, key="e_summary")
    e_outcome = st.radio("転帰", ["搬入","お断り","2次やかかりつけ医案内","患者都合","その他"],
        horizontal=True,
        index=["搬入","お断り","2次やかかりつけ医案内","患者都合","その他"].index(ec["outcome"]) if ec.get("outcome") in ["搬入","お断り","2次やかかりつけ医案内","患者都合","その他"] else 0,
        key="e_outcome")
    e_reason=e_r1=e_r2=e_r3dept=e_r3sub=""
    if e_outcome == "お断り":
        reason_opts = ["1_満床","2_マンパワー","3_院内専門科"]
        e_reason = st.radio("お断り理由", reason_opts,
            format_func=lambda x:{"1_満床":"1. 病床の都合","2_マンパワー":"2. マンパワーの問題","3_院内専門科":"3. 院内専門科の都合"}[x],
            index=reason_opts.index(ec["reason"]) if ec.get("reason") in reason_opts else 0,
            key="e_reason")
        if e_reason=="1_満床":
            e_r1 = st.selectbox("病床理由詳細",["","満床・満床に準ずる状態","ICU個室(感染等)満床","熱傷患者受入不能"],
                index=["","満床・満床に準ずる状態","ICU個室(感染等)満床","熱傷患者受入不能"].index(ec.get("reason1_sub","")) if ec.get("reason1_sub","") in ["","満床・満床に準ずる状態","ICU個室(感染等)満床","熱傷患者受入不能"] else 0,
                key="e_r1")
        elif e_reason=="2_マンパワー":
            e_r2 = st.selectbox("マンパワー理由詳細",["","他患の処置・手術等で余力なし","別の救急患者の搬入直前・直後"],
                index=["","他患の処置・手術等で余力なし","別の救急患者の搬入直前・直後"].index(ec.get("reason2_sub","")) if ec.get("reason2_sub","") in ["","他患の処置・手術等で余力なし","別の救急患者の搬入直前・直後"] else 0,
                key="e_r2")
        elif e_reason=="3_院内専門科":
            e_r3dept = st.text_input("専門科名", value=ec.get("reason3_dept",""), key="e_r3dept")
            e_r3sub = st.selectbox("専門科理由詳細",["","当該科手術中","学会等で不在","麻酔科対応不能"],
                index=["","当該科手術中","学会等で不在","麻酔科対応不能"].index(ec.get("reason3_sub","")) if ec.get("reason3_sub","") in ["","当該科手術中","学会等で不在","麻酔科対応不能"] else 0,
                key="e_r3sub")
    ex1,ex2 = st.columns(2)
    with ex1:
        if st.button("💾 保存", type="primary", use_container_width=True, key="e_save"):
            st.session_state.hl_cases[hl_edit_idx] = {
                "time":e_time,"team":e_team,"req_count":e_req,
                "age":e_age if e_age>0 else "","gender":e_gender if e_gender!="未記載" else "",
                "summary":e_summary,"outcome":e_outcome,"reason":e_reason,
                "reason1_sub":e_r1,"reason2_sub":e_r2,
                "reason3_dept":e_r3dept,"reason3_sub":e_r3sub,
            }
            save_cases(st.session_state.hl_cases)
            st.session_state.hl_editing = None
            st.rerun()
    with ex2:
        if st.button("キャンセル", use_container_width=True, key="e_cancel"):
            st.session_state.hl_editing = None
            st.rerun()

# ===== 新規入力 =====
st.divider()
st.subheader(f"➕ 症例 {n+1} を入力")
cc1,cc2=st.columns(2)
with cc1:
    # 現在時刻（JST）を切り捨て（5分刻み）でデフォルトに
    from datetime import timezone, timedelta
    _jst = timezone(timedelta(hours=9))
    _now = datetime.now(_jst)
    _rounded = f"{_now.hour:02d}:{(_now.minute // 5) * 5:02d}"
    _nearest_idx = TIME_OPTIONS.index(_rounded) if _rounded in TIME_OPTIONS else 0
    sel_time=st.selectbox("時刻", TIME_OPTIONS, index=_nearest_idx, key="inp_time")
    if sel_time:
        st.caption(f"→ **{time_to_shift(sel_time)}**")
with cc2:
    team_sel = st.selectbox("依頼先救急隊", RESCUE_TEAMS + ["その他（直接入力）"], key="inp_team")
    if team_sel == "その他（直接入力）":
        team = st.text_input("救急隊名を入力", key="inp_team_other", placeholder="例: 石狩")
    else:
        team = team_sel
cc3,cc4,cc5=st.columns(3)
with cc3: req_count=st.selectbox("依頼回数",["初回","2回目","3回目","4回目以上"],key="inp_req")
with cc4: age=st.number_input("年齢（才）",min_value=0,max_value=120,value=0,step=1,key="inp_age")
with cc5: gender=st.radio("性別",["M","F","未記載"],horizontal=True,key="inp_gender")
summary=st.text_area("概略",height=70,key="inp_summary",placeholder="主訴・経過を入力")
outcome=st.radio("転帰",["搬入","お断り","2次やかかりつけ医案内","患者都合","その他"],horizontal=True,key="inp_outcome")
reason=reason1_sub=reason2_sub=reason3_dept=reason3_sub=""
if outcome=="お断り":
    reason=st.radio("お断り理由",["1_満床","2_マンパワー","3_院内専門科"],
        format_func=lambda x:{"1_満床":"1. 病床の都合","2_マンパワー":"2. マンパワーの問題","3_院内専門科":"3. 院内専門科の都合"}[x],
        key="inp_reason")
    if reason=="1_満床":
        reason1_sub=st.selectbox("病床理由詳細",
            ["","満床・満床に準ずる状態","ICU個室(感染等)満床","熱傷患者受入不能"],key="inp_r1")
    elif reason=="2_マンパワー":
        reason2_sub=st.selectbox("マンパワー理由詳細",
            ["","他患の処置・手術等で余力なし","別の救急患者の搬入直前・直後"],key="inp_r2")
    elif reason=="3_院内専門科":
        reason3_dept=st.text_input("専門科名",key="inp_dept",placeholder="循環器")
        reason3_sub=st.selectbox("専門科理由詳細",["","当該科手術中","学会等で不在","麻酔科対応不能"],key="inp_r3")

if st.button("✅ この症例を登録",type="primary",use_container_width=True):
    st.session_state.hl_cases.append({
        "time":sel_time,"team":team,"req_count":req_count,
        "age":age if age>0 else "","gender":gender if gender!="未記載" else "",
        "summary":summary,"outcome":outcome,"reason":reason,
        "reason1_sub":reason1_sub,"reason2_sub":reason2_sub,
        "reason3_dept":reason3_dept,"reason3_sub":reason3_sub,
    })
    save_cases(st.session_state.hl_cases)
    st.rerun()

# ===== 出力（日勤・夜勤を別紙）=====
st.divider()
oc1,oc2=st.columns(2)
with oc1:
    if st.button("🖨️ 受付対応表を生成",type="primary",use_container_width=True,
                 disabled=(len(st.session_state.hl_cases)==0)):
        date_str = input_date.strftime('%Y%m%d')

        for shift_label, shift_cases in [("日勤", nisshin), ("夜勤", yashin)]:
            if not shift_cases:
                continue
            st.write(f"### 📄 {shift_label}（{len(shift_cases)}件）")
            n_sh = max(1,(len(shift_cases)+5)//6)
            header_for_render = {"date": input_date.isoformat(), "shift": shift_label, "leader": leader}
            for sh in range(n_sh):
                sheet_cases = shift_cases[sh*6:sh*6+6]
                with st.spinner(f"{shift_label} No.{sh+1} 生成中..."):
                    result = render_hotline(header_for_render, sheet_cases, sheet_no=sh+1)
                st.write(f"**{shift_label} No.{sh+1}**（症例{sh*6+1}〜{min(sh*6+len(sheet_cases),len(shift_cases))}）")
                st.image(result, use_container_width=True)
                buf=io.BytesIO()
                result.save(buf,format="JPEG",quality=95)
                st.download_button(
                    f"📥 {shift_label} No.{sh+1} 保存", buf.getvalue(),
                    f"hotline_{date_str}_{shift_label}_No{sh+1}.jpg","image/jpeg",
                    key=f"dl_{shift_label}_{sh}")
with oc2:
    if st.button("🗑️ 全症例をリセット",use_container_width=True):
        st.session_state.hl_cases=[]
        save_cases([])
        st.rerun()
