import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import io
import os
import json
import re
import unicodedata
import streamlit.components.v1 as components

# ==========================================
# THIẾT LẬP GIAO DIỆN & TIÊU ĐỀ
# ==========================================
st.set_page_config(layout="wide", page_title="reTIME", page_icon="⏱️")

components.html("""
<script>
if (!window.parent.document.getElementById('enter-to-tab-script')) {
    const script = window.parent.document.createElement('script');
    script.id = 'enter-to-tab-script';
    script.innerHTML = `
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                const active = document.activeElement;
                if (active && active.tagName === 'BUTTON') return;
                if (active && active.tagName === 'INPUT' && active.getAttribute('role') !== 'combobox') {
                    e.preventDefault();
                    e.stopPropagation();
                    const elements = Array.from(document.querySelectorAll('input:not([disabled]), div[data-baseweb="select"] input, button:not([disabled])'));
                    const index = elements.indexOf(active);
                    if (index > -1 && index < elements.length - 1) {
                        elements[index + 1].focus();
                    }
                }
            }
        }, true);
    `;
    window.parent.document.head.appendChild(script);
}
</script>
""", height=0, width=0)

st.markdown("""
    <style>
    button[kind="primary"] { background-color: #27AE60 !important; border-color: #27AE60 !important; color: white !important; font-weight: bold; }
    button[kind="primary"]:hover { background-color: #1E8449 !important; border-color: #1E8449 !important; }
    button[kind="secondary"] { background-color: #F39C12 !important; border-color: #F39C12 !important; color: white !important; font-weight: bold;}
    button[kind="secondary"]:hover { background-color: #E67E22 !important; border-color: #E67E22 !important; }
    </style>
""", unsafe_allow_html=True)

st.markdown("""
    <div style='text-align: center;'>
        <h1 style='font-size: 3.2rem; font-weight: 900; margin-bottom: 0px;'>
            <span style='color: #E74C3C;'>re</span><span style='color: #5DADE2;'>TIME</span>
            <span style='color: #2E86C1;'> - TỐI ƯU LỊCH LÀM VIỆC</span>
        </h1>
    </div>
    <hr style='margin-top: 15px; margin-bottom: 25px;'>
""", unsafe_allow_html=True)

# ==========================================
# HÀM LƯU TRỮ ĐỒNG BỘ 2 CHIỀU
# ==========================================
def cleanup_old_files():
    limit_date = datetime.today().date() - timedelta(days=7)
    try:
        for f in os.listdir():
            if f.startswith(('ns_', 'bn_', 'sched_')) and (f.endswith('.csv') or f.endswith('.json')):
                date_str = f.split('_')[1].split('.')[0]
                if datetime.strptime(date_str, "%Y-%m-%d").date() < limit_date: os.remove(f)
    except: pass
cleanup_old_files()

WEEKDAY_VN = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]

def to_bool(v, default=True):
    if isinstance(v, bool): return v
    if v is None: return default
    try:
        if pd.isna(v): return default
    except (TypeError, ValueError): pass
    s = str(v).strip().lower()
    if s in ('true', '1', '1.0', 'có', 'co', 'x', 'yes', 'y', '✔', '✓', '✅'): return True
    if s in ('false', '0', '0.0', 'không', 'khong', 'no', 'n', '✘', '✗', '❌'): return False
    return default

def clean_str(v):
    if v is None: return ""
    try:
        if pd.isna(v): return ""
    except (TypeError, ValueError): pass
    s = str(v).strip()
    return "" if s.lower() in ('nan', 'none', 'nat') else s

def norm_key(s):
    # Chuẩn hoá chuỗi để so khớp: bỏ dấu, bỏ khoảng trắng/ký tự đặc biệt, chữ thường
    s = unicodedata.normalize('NFD', clean_str(s).replace('đ', 'd').replace('Đ', 'D'))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]', '', s.lower())

def gen_ma_bn(existing_codes):
    prefix = f"BN{datetime.now().strftime('%d%m')}-"
    n = 1
    while f"{prefix}{n:02d}" in existing_codes: n += 1
    return f"{prefix}{n:02d}"

def sanitize_bn_list(bn_list):
    for bn in bn_list:
        bn['Gio_Ra_Vien'] = clean_str(bn.get('Gio_Ra_Vien', ""))
        bn['Gio_Kham'] = clean_str(bn.get('Gio_Kham', ""))
        bn['Kham_Benh'] = to_bool(bn.get('Kham_Benh', True), default=True)
    return bn_list

USE_GSHEETS = False
try:
    from streamlit_gsheets import GSheetsConnection
    conn = st.connection("gsheets", type=GSheetsConnection)
    USE_GSHEETS = True
except Exception: USE_GSHEETS = False

def update_gsheets_safe(worksheet_name, df_day, date_str):
    if not USE_GSHEETS: return
    try:
        try:
            df_all = conn.read(worksheet=worksheet_name, ttl=0)
            if df_all.empty or 'Date' not in df_all.columns:
                df_all = pd.DataFrame(columns=['Date'] + list(df_day.columns))
        except: df_all = pd.DataFrame(columns=['Date'] + list(df_day.columns))

        limit_date_str = (datetime.today().date() - timedelta(days=7)).strftime("%Y-%m-%d")
        df_all = df_all[df_all['Date'] >= limit_date_str]
        df_all = df_all[df_all['Date'] != date_str]

        df_new = df_day.copy()
        if not df_new.empty:
            df_new['Date'] = date_str
            df_all = pd.concat([df_all, df_new], ignore_index=True)

        conn.update(worksheet=worksheet_name, data=df_all)
    except: pass

def get_data_from_db(worksheet_name, target_date_str):
    if not USE_GSHEETS: return None
    try:
        df_all = conn.read(worksheet=worksheet_name, ttl=0)
        if df_all.empty or 'Date' not in df_all.columns: return None
        df_day = df_all[df_all['Date'] == target_date_str]
        if df_day.empty: return None
        return df_day.drop(columns=['Date'])
    except: return None

def get_fallback_from_db(worksheet_name, target_date):
    if not USE_GSHEETS: return None
    target_date_str = target_date.strftime("%Y-%m-%d")
    try:
        df_all = conn.read(worksheet=worksheet_name, ttl=0)
        if df_all.empty or 'Date' not in df_all.columns: return None
        df_past = df_all[df_all['Date'] < target_date_str].sort_values(by='Date', ascending=False)
        if df_past.empty: return None
        latest_date = df_past.iloc[0]['Date']
        return df_past[df_past['Date'] == latest_date].drop(columns=['Date'])
    except: return None

def get_fallback_file(prefix, ext, target_date):
    for i in range(1, 8):
        test_date = target_date - timedelta(days=i)
        test_path = f"{prefix}_{test_date.strftime('%Y-%m-%d')}.{ext}"
        if os.path.exists(test_path): return test_path
    return None

def get_default_ns():
    return pd.DataFrame({
        'Di_Lam': [True]*11, 
        'Ma_Nhan_Vien': ['bs-Quyen', 'bs-Hong', 'bs-Trung', 'bs-Thu', 'bs-Vy', 'bs-Thanh', 'bs-Nha', 'ktv-Huu', 'ktv-Duyen', 'ktv-LuanPhien1', 'ktv-LuanPhien2'],
        'Ten_Nhan_Vien': ['Bs. Chung Tú Quyên', 'Bs. Đậu Thị Hồng', 'Bs. Hoàng Thế Trung', 'Bs. Huỳnh Anh Thư', 'Bs. Lê Uyên Phương Vy', 'Bs. Phạm Quốc Thanh', 'Bs. Cao Pha Nha', 'KTV. Phan Phúc Hữu', 'KTV. Nguyễn Mỹ Duyên', 'KTV Luân Phiên 1', 'KTV Luân Phiên 2'],
        'Ca_Lam_Viec': ['Cả ngày']*11, 'Gio_Bat_Dau': ['07:10']*11, 'Ghi_Chu': ['']*11
    })

def save_ns_data_db(df, date_str):
    df_save = df.drop(columns=['STT']) if 'STT' in df.columns else df
    df_save.to_csv(f"ns_{date_str}.csv", index=False)
    update_gsheets_safe("NhanSu", df_save, date_str)

def save_bn_data_db(bn_list, date_str):
    with open(f"bn_{date_str}.json", 'w', encoding='utf-8') as f: json.dump(bn_list, f, ensure_ascii=False, indent=2)
    df = pd.DataFrame(bn_list)
    if df.empty: df = pd.DataFrame(columns=["Ma_BN", "Ten_BN", "BS_Kham", "Y_Lenh", "Created_At", "Gio_Ra_Vien", "Gio_Kham", "Kham_Benh"])
    update_gsheets_safe("BenhNhan", df, date_str)

def save_sched_data_db(df, date_str):
    df.to_json(f"sched_{date_str}.json", orient='records', date_format='iso')
    update_gsheets_safe("LichTrinh", df, date_str)

def parse_time_input(time_str):
    # Ô giờ trong Excel có thể được đọc thành kiểu time/datetime
    if hasattr(time_str, 'strftime') and not isinstance(time_str, str):
        try: return time_str.strftime("%H:%M")
        except: return ""
    if pd.isna(time_str): return ""
    time_str = str(time_str).strip().replace(';', ':')
    if not time_str or time_str.lower() in ['nan', 'none']: return ""
    if re.match(r'^\d{4}$', time_str): time_str = f"{time_str[:2]}:{time_str[2:]}"
    elif re.match(r'^\d{3}$', time_str): time_str = f"0{time_str[0]}:{time_str[1:]}"
    elif re.match(r'^\d{1,2}:\d{2}:\d{2}$', time_str): time_str = time_str[:-3]
    try: 
        datetime.strptime(time_str, "%H:%M")
        return time_str
    except: 
        return "" 

@st.cache_data
def load_base_data(file_name):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, file_name)
    return pd.read_excel(file_path, sheet_name='Thong_So_Co_Dinh')

try: df_thongso = load_base_data('data.xlsx')
except Exception as e: st.error(f"⚠️ Không tìm thấy file 'data.xlsx'. Lỗi hệ thống: {e}"); st.stop()

# ==========================================
# THANH CÔNG CỤ CHỌN NGÀY & LÀM MỚI 
# ==========================================
col_date, col_blank, col_btn = st.columns([2, 6, 2])
with col_date:
    selected_date = st.date_input("📅 Chọn Ngày làm việc", value=st.session_state.get('selected_date', datetime.today().date()), key="main_date")
with col_btn:
    st.write("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True) 
    if st.button("🔄 Làm mới dữ liệu", type="secondary", use_container_width=True):
        date_str = selected_date.strftime("%Y-%m-%d")
        for pfx, ext in [('ns', 'csv'), ('bn', 'json'), ('sched', 'json')]:
            if os.path.exists(f"{pfx}_{date_str}.{ext}"): os.remove(f"{pfx}_{date_str}.{ext}")
        if USE_GSHEETS:
            update_gsheets_safe("NhanSu", pd.DataFrame(), date_str)
            update_gsheets_safe("BenhNhan", pd.DataFrame(), date_str)
            update_gsheets_safe("LichTrinh", pd.DataFrame(), date_str)
        st.session_state.clear()
        st.rerun()

date_str = selected_date.strftime("%Y-%m-%d")

if USE_GSHEETS: st.caption("🟢 Đang kết nối Google Sheets (Lưu online)")
else: st.caption("🟡 Đang lưu nội bộ (offline)")

if 'selected_date' not in st.session_state or st.session_state.selected_date != selected_date:
    st.session_state.selected_date = selected_date
    
    if os.path.exists(f"ns_{date_str}.csv"): st.session_state.ns_data = pd.read_csv(f"ns_{date_str}.csv")
    else:
        db_data = get_data_from_db("NhanSu", date_str)
        if db_data is not None: st.session_state.ns_data = db_data
        else:
            fb_ns = get_fallback_file('ns', 'csv', selected_date)
            if fb_ns: st.session_state.ns_data = pd.read_csv(fb_ns)
            else:
                fb_db = get_fallback_from_db("NhanSu", selected_date)
                if fb_db is not None: st.session_state.ns_data = fb_db
                else: st.session_state.ns_data = get_default_ns()
            
    st.session_state.ns_data['Di_Lam'] = st.session_state.ns_data['Di_Lam'].astype(bool)
    if 'Gio_Bat_Dau' not in st.session_state.ns_data.columns: st.session_state.ns_data['Gio_Bat_Dau'] = '07:10'
    if 'STT' in st.session_state.ns_data.columns: st.session_state.ns_data = st.session_state.ns_data.drop(columns=['STT'])
    for col in ['Gio_Bat_Dau', 'Ghi_Chu', 'Ten_Nhan_Vien', 'Ca_Lam_Viec']:
        if col in st.session_state.ns_data.columns:
            st.session_state.ns_data[col] = st.session_state.ns_data[col].fillna("").astype(str).replace("nan", "")

    if os.path.exists(f"bn_{date_str}.json"):
        with open(f"bn_{date_str}.json", 'r', encoding='utf-8') as f: st.session_state.bn_list = sanitize_bn_list(json.load(f))
    else:
        db_data = get_data_from_db("BenhNhan", date_str)
        if db_data is not None: st.session_state.bn_list = sanitize_bn_list(db_data.to_dict('records'))
        else:
            fb_bn = get_fallback_file('bn', 'json', selected_date)
            if fb_bn: 
                with open(fb_bn, 'r', encoding='utf-8') as f: st.session_state.bn_list = sanitize_bn_list(json.load(f))
            else:
                fb_db = get_fallback_from_db("BenhNhan", selected_date)
                if fb_db is not None: st.session_state.bn_list = sanitize_bn_list(fb_db.to_dict('records'))
                else: st.session_state.bn_list = []
            # Danh sách mang sang từ ngày trước: T2–T6 mặc định có khám, T7–CN mặc định không khám
            for bn in st.session_state.bn_list: bn['Kham_Benh'] = selected_date.weekday() < 5
        
    if os.path.exists(f"sched_{date_str}.json"):
        st.session_state.df_schedule = pd.read_json(f"sched_{date_str}.json", orient='records')
        st.session_state.df_schedule['Start'] = pd.to_datetime(st.session_state.df_schedule['Start'])
        st.session_state.df_schedule['Finish'] = pd.to_datetime(st.session_state.df_schedule['Finish'])
    else:
        db_data = get_data_from_db("LichTrinh", date_str)
        if db_data is not None:
            st.session_state.df_schedule = db_data
            st.session_state.df_schedule['Start'] = pd.to_datetime(st.session_state.df_schedule['Start'])
            st.session_state.df_schedule['Finish'] = pd.to_datetime(st.session_state.df_schedule['Finish'])
        else:
            if 'df_schedule' in st.session_state: del st.session_state['df_schedule']
    
    st.rerun()

# ==========================================
# KHU VỰC 1: QUẢN LÝ NHÂN SỰ
# ==========================================
st.markdown("<h3 style='color: #5DADE2; border-bottom: 2px solid #5DADE2; padding-bottom: 5px;'>1. CẬP NHẬT NHÂN SỰ LÀM VIỆC</h3>", unsafe_allow_html=True)

with st.expander("⚙️ Quản lý Nhân sự (Thêm mới / Xóa)"):
    st.markdown("**➕ Thêm nhân viên mới**")
    col_n1, col_n2, col_n3 = st.columns([2, 1, 1])
    with col_n1: new_ten = st.text_input("Họ và Tên Nhân viên", key="new_staff_name")
    with col_n2: new_role = st.selectbox("Vai trò", ["Bác sĩ", "Kỹ thuật viên"], key="new_staff_role")
    with col_n3:
        st.write("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("Lưu nhân viên", type="primary"):
            if new_ten.strip():
                prefix = "bs" if new_role == "Bác sĩ" else "ktv"
                new_ma = f"{prefix}-{new_ten.split()[-1]}{len(st.session_state.ns_data)}"
                new_row = pd.DataFrame([{'Di_Lam': True, 'Ma_Nhan_Vien': new_ma, 'Ten_Nhan_Vien': new_ten, 'Ca_Lam_Viec': 'Cả ngày', 'Gio_Bat_Dau': '07:10', 'Ghi_Chu': ''}])
                st.session_state.ns_data = pd.concat([st.session_state.ns_data, new_row], ignore_index=True)
                save_ns_data_db(st.session_state.ns_data, date_str)
                st.rerun()
                
    st.divider()
    st.markdown("**🗑️ Xóa nhân viên**")
    col_d1, col_d2, col_d3 = st.columns([2, 1, 1])
    with col_d1: nv_xoa = st.selectbox("Chọn nhân viên cần xóa:", options=["-- Chọn --"] + st.session_state.ns_data['Ten_Nhan_Vien'].tolist(), key="del_staff_name")
    with col_d2:
        st.write("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("Xóa nhân viên", type="secondary", use_container_width=True):
            if nv_xoa != "-- Chọn --":
                st.session_state.ns_data = st.session_state.ns_data[st.session_state.ns_data['Ten_Nhan_Vien'] != nv_xoa].reset_index(drop=True)
                save_ns_data_db(st.session_state.ns_data, date_str)
                st.rerun()

ns_display = st.session_state.ns_data.copy()
ns_display.insert(0, 'STT', range(1, len(ns_display) + 1))

edited_ns = st.data_editor(
    ns_display, key="ns_editor_widget",
    column_config={
        "STT": st.column_config.NumberColumn("STT", disabled=True),
        "Di_Lam": st.column_config.CheckboxColumn("Đi làm?", default=True),
        "Ma_Nhan_Vien": st.column_config.TextColumn("Mã NV", disabled=True),
        "Ten_Nhan_Vien": st.column_config.TextColumn("Họ và Tên"),
        "Ca_Lam_Viec": st.column_config.SelectboxColumn("Ca làm", options=["Sáng", "Chiều", "Cả ngày"]),
        "Gio_Bat_Dau": st.column_config.TextColumn("Giờ bắt đầu (Vd: 07:10)"),
        "Ghi_Chu": "Ghi chú"
    }, hide_index=True, use_container_width=True
)

edited_ns_clean = edited_ns.drop(columns=['STT'])
if not edited_ns_clean.equals(st.session_state.ns_data):
    for i in range(len(edited_ns_clean)):
        val = str(edited_ns_clean.at[i, 'Gio_Bat_Dau']).strip()
        if val and val not in ['None', 'nan']: 
            parsed = parse_time_input(val)
            if parsed != val: 
                edited_ns_clean.at[i, 'Gio_Bat_Dau'] = parsed
                
    st.session_state.ns_data = edited_ns_clean.copy()
    save_ns_data_db(st.session_state.ns_data, date_str)
    st.rerun() 

active_staff = st.session_state.ns_data[st.session_state.ns_data['Di_Lam'] == True]
ktv_list = active_staff[active_staff['Ma_Nhan_Vien'].str.startswith('ktv-')]['Ma_Nhan_Vien'].tolist()
bs_list = active_staff[active_staff['Ma_Nhan_Vien'].str.startswith('bs-')]['Ma_Nhan_Vien'].tolist()
ten_nv_dict = dict(zip(st.session_state.ns_data['Ma_Nhan_Vien'], st.session_state.ns_data['Ten_Nhan_Vien']))

if not ktv_list or not bs_list:
    st.warning("⚠️ Hệ thống cần ít nhất 1 BS và 1 KTV đánh dấu 'Đi làm' để tiếp tục.")
    st.stop()

# ==========================================
# KHU VỰC 2: QUẢN LÝ BỆNH NHÂN NỘI TRÚ
# ==========================================
st.markdown("<br><h3 style='color: #E67E22; border-bottom: 2px solid #E67E22; padding-bottom: 5px;'>2. QUẢN LÝ BỆNH NHÂN ĐANG ĐIỀU TRỊ</h3>", unsafe_allow_html=True)
st.session_state.bn_list.sort(key=lambda x: x.get('Created_At', 0))

danh_sach_thu_thuat = df_thongso['Ten_Thu_Thuat'].tolist()
ma_thu_thuat_dict = dict(zip(df_thongso['Ten_Thu_Thuat'], df_thongso['Ma_Thu_Thuat']))
tt_lookup = {norm_key(t): t for t in danh_sach_thu_thuat}
tt_role = dict(zip(df_thongso['Ten_Thu_Thuat'], df_thongso['Nguoi_Phu_Trach']))
bs_all_codes = [c for c in st.session_state.ns_data['Ma_Nhan_Vien'] if str(c).startswith('bs-')]
is_weekend = selected_date.weekday() >= 5
KHAM_LABEL = "🩺 Khám bệnh (xếp 5 phút khám ban đầu)"

def build_bn_export_df(bn_list):
    rows = []
    for i, bn in enumerate(bn_list, 1):
        rows.append({
            'STT': i, 'Mã BN': bn['Ma_BN'], 'Tên Bệnh Nhân': bn['Ten_BN'],
            'Bác sĩ phụ trách': ten_nv_dict.get(bn['BS_Kham'], bn['BS_Kham']), 'Mã BS': bn['BS_Kham'],
            'Thủ thuật (Y lệnh)': bn['Y_Lenh'], 'Khám bệnh': 'Có' if bn.get('Kham_Benh', True) else 'Không',
            'Giờ khám': bn.get('Gio_Kham', ''), 'Giờ ra viện': bn.get('Gio_Ra_Vien', '')
        })
    return pd.DataFrame(rows, columns=['STT', 'Mã BN', 'Tên Bệnh Nhân', 'Bác sĩ phụ trách', 'Mã BS', 'Thủ thuật (Y lệnh)', 'Khám bệnh', 'Giờ khám', 'Giờ ra viện'])

if 'import_msg' in st.session_state:
    st.success(st.session_state.pop('import_msg'))

col_form, col_table = st.columns([1, 1.5])
with col_form:
    st.markdown("#### ➕ Thêm Bệnh Nhân Mới")
    with st.container(border=True):
        with st.form("form_nhap_bn", clear_on_submit=True):
            ten_bn = st.text_input("Tên Bệnh Nhân (Bắt buộc)")
            
            col_b1, col_b2 = st.columns(2)
            with col_b1: gio_kham = st.text_input("Giờ khám (Nếu có)")
            with col_b2: gio_ra_vien = st.text_input("Giờ ra viện (nếu có)")
            
            bs_kham = st.selectbox("Bác sĩ phụ trách", options=bs_list, format_func=lambda x: ten_nv_dict.get(x, x))
            kham_benh = st.checkbox(KHAM_LABEL, value=not is_weekend,
                                    help="Bỏ chọn nếu BN chỉ làm thủ thuật theo y lệnh đã có (VD: Thứ 7, Chủ nhật).")
            if is_weekend: st.caption(f"ℹ️ {WEEKDAY_VN[selected_date.weekday()]}: mặc định KHÔNG khám, chỉ làm thủ thuật theo y lệnh cũ.")
            y_lenh_chon = st.multiselect("Chỉ định Thủ thuật", options=danh_sach_thu_thuat)
            
            if st.form_submit_button("Lập Hồ Sơ", type="primary", use_container_width=True):
                if ten_bn.strip() == "": st.error("Vui lòng nhập tên Bệnh nhân!")
                elif not y_lenh_chon: st.error("Vui lòng chọn ít nhất 1 thủ thuật!")
                else:
                    ma_bn = gen_ma_bn({str(b['Ma_BN']) for b in st.session_state.bn_list})
                    st.session_state.bn_list.append({
                        "Ma_BN": ma_bn, "Ten_BN": ten_bn, "BS_Kham": bs_kham, 
                        "Y_Lenh": ", ".join(y_lenh_chon), "Created_At": datetime.now().timestamp(),
                        "Gio_Ra_Vien": parse_time_input(gio_ra_vien),
                        "Gio_Kham": parse_time_input(gio_kham),
                        "Kham_Benh": bool(kham_benh)
                    })
                    save_bn_data_db(st.session_state.bn_list, date_str)
                    st.success(f"Đã lập hồ sơ: {ten_bn} (Mã: {ma_bn})")
                    st.rerun()

with col_table:
    st.markdown("#### 📋 Bệnh Nhân Đang Nằm Viện")
    with st.container(border=True):
        if len(st.session_state.bn_list) > 0:
            df_hienthi = pd.DataFrame(st.session_state.bn_list)
            df_hienthi['BS_Kham'] = df_hienthi['BS_Kham'].map(lambda x: ten_nv_dict.get(x, x))
            df_hienthi.insert(0, 'STT', range(1, len(df_hienthi) + 1))
            st.dataframe(df_hienthi[['STT', 'Ma_BN', 'Ten_BN', 'Kham_Benh', 'Gio_Kham', 'Gio_Ra_Vien', 'BS_Kham', 'Y_Lenh']].rename(columns={'Gio_Ra_Vien': 'Hẹn về', 'Gio_Kham': 'Giờ khám'}),
                         column_config={"Kham_Benh": st.column_config.CheckboxColumn("Khám")},
                         hide_index=True, use_container_width=True, height=200)
            
            n_kham = sum(1 for b in st.session_state.bn_list if b.get('Kham_Benh', True))
            st.caption(f"🩺 Có khám: **{n_kham}** BN · Chỉ làm thủ thuật: **{len(st.session_state.bn_list) - n_kham}** BN")
            col_k1, col_k2, col_k3 = st.columns(3)
            if col_k1.button("🩺 Tất cả CÓ khám", use_container_width=True):
                for b in st.session_state.bn_list: b['Kham_Benh'] = True
                save_bn_data_db(st.session_state.bn_list, date_str)
                st.rerun()
            if col_k2.button("🚫 Tất cả KHÔNG khám", use_container_width=True):
                for b in st.session_state.bn_list: b['Kham_Benh'] = False
                save_bn_data_db(st.session_state.bn_list, date_str)
                st.rerun()
            buf_bn = io.BytesIO()
            with pd.ExcelWriter(buf_bn, engine='openpyxl') as writer: build_bn_export_df(st.session_state.bn_list).to_excel(writer, index=False, sheet_name='Danh_Sach_BN')
            col_k3.download_button("📤 Xuất DS BN", data=buf_bn.getvalue(), file_name=f"DanhSach_BN_{selected_date.strftime('%Y%m%d')}.xlsx", use_container_width=True)
            
            with st.expander("✏️ Điều chỉnh Y Lệnh hoặc Cho Ra Viện"):
                edit_idx = st.selectbox("🔍 Chọn Bệnh nhân:", options=range(len(st.session_state.bn_list)), format_func=lambda i: f"{st.session_state.bn_list[i]['Ma_BN']} - {st.session_state.bn_list[i]['Ten_BN']}")
                selected_bn = st.session_state.bn_list[edit_idx]
                current_yl = [t.strip() for t in selected_bn['Y_Lenh'].split(",") if t.strip()]
                
                col_e1, col_e2 = st.columns(2)
                with col_e1: 
                    edit_ten = st.text_input("Sửa Tên BN:", value=selected_bn['Ten_BN'])
                    edit_bs = st.selectbox("Đổi BS phụ trách:", options=bs_list, format_func=lambda x: ten_nv_dict.get(x, x), index=bs_list.index(selected_bn['BS_Kham']) if selected_bn['BS_Kham'] in bs_list else 0)
                with col_e2: 
                    edit_gk = st.text_input("Giờ khám mới:", value=selected_bn.get('Gio_Kham', ''))
                    edit_rv = st.text_input("Giờ ra viện mới:", value=selected_bn.get('Gio_Ra_Vien', ''))
                
                edit_kb = st.checkbox(KHAM_LABEL, value=selected_bn.get('Kham_Benh', True), key=f"edit_kb_{selected_bn['Ma_BN']}")
                edit_yl = st.multiselect("Thêm/Bớt Thủ thuật:", options=danh_sach_thu_thuat, default=current_yl)
                
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("💾 Cập nhật", type="primary", use_container_width=True):
                    st.session_state.bn_list[edit_idx]['Ten_BN'] = edit_ten
                    st.session_state.bn_list[edit_idx]['BS_Kham'] = edit_bs
                    st.session_state.bn_list[edit_idx]['Y_Lenh'] = ", ".join(edit_yl)
                    st.session_state.bn_list[edit_idx]['Gio_Kham'] = parse_time_input(edit_gk)
                    st.session_state.bn_list[edit_idx]['Gio_Ra_Vien'] = parse_time_input(edit_rv)
                    st.session_state.bn_list[edit_idx]['Kham_Benh'] = bool(edit_kb)
                    save_bn_data_db(st.session_state.bn_list, date_str)
                    st.rerun()
                if col_btn2.button("🏥 Ra viện", type="secondary", use_container_width=True):
                    st.session_state.bn_list.pop(edit_idx)
                    save_bn_data_db(st.session_state.bn_list, date_str)
                    st.rerun()
        else: st.info("Khoa hiện không có bệnh nhân.")

# ---------- NHẬP DANH SÁCH BN TỪ NGÀY KHÁC / FILE EXCEL ----------
def resolve_bs(values):
    # Nhận mã BS hoặc tên BS (có/không dấu), trả về mã BS trong danh sách nhân sự hiện tại
    if not isinstance(values, (list, tuple)): values = [values]
    for value in values:
        v = clean_str(value).replace(" (Theo dõi)", "")
        if not v: continue
        if v in bs_all_codes: return v
        k = norm_key(v)
        for code in bs_all_codes:
            if norm_key(ten_nv_dict.get(code, '')) == k or norm_key(code) == k: return code
    return None

def resolve_y_lenh(value):
    parts = value if isinstance(value, (list, tuple)) else re.split(r'[,;\n]+', clean_str(value))
    found, unknown = [], []
    for p in parts:
        p = clean_str(p)
        if not p: continue
        tt = tt_lookup.get(norm_key(p))
        if tt:
            if tt not in found: found.append(tt)
        else: unknown.append(p)
    return found, unknown

def list_saved_bn_dates():
    result = {}
    for f in os.listdir():
        m = re.match(r'^bn_(\d{4}-\d{2}-\d{2})\.json$', f)
        if m and m.group(1) != date_str:
            try:
                with open(f, 'r', encoding='utf-8') as fh: n = len(json.load(fh))
                if n > 0: result[m.group(1)] = n
            except: pass
    if USE_GSHEETS:
        try:
            df_all = conn.read(worksheet="BenhNhan", ttl=0)
            if not df_all.empty and 'Date' in df_all.columns:
                for d, n in df_all.dropna(subset=['Date']).groupby('Date').size().items():
                    d = str(d)[:10]
                    if d != date_str and d not in result: result[d] = int(n)
        except: pass
    return dict(sorted(result.items(), reverse=True))

def load_bn_of_date(d):
    p = f"bn_{d}.json"
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as fh: return sanitize_bn_list(json.load(fh))
    db = get_data_from_db("BenhNhan", d)
    return sanitize_bn_list(db.to_dict('records')) if db is not None else []

def parse_import_excel(uploaded):
    # Hỗ trợ: (1) file "Xuất DS BN" (sheet Danh_Sach_BN), (2) file Lịch phân công đã xuất, (3) danh sách tự soạn
    xls = pd.ExcelFile(uploaded)
    sheets = xls.sheet_names
    order = (['Danh_Sach_BN'] if 'Danh_Sach_BN' in sheets else []) + [s for s in sheets if s != 'Danh_Sach_BN']
    for sh in order:
        df = pd.read_excel(xls, sheet_name=sh)
        if df.empty: continue
        cols = {norm_key(c): c for c in df.columns}
        def pick(*aliases):
            for a in aliases:
                if a in cols: return cols[a]
            return None
        c_ma = pick('mabn', 'mabenhnhan')
        c_ten = pick('tenbenhnhan', 'tenbn', 'hoten', 'hovaten', 'benhnhan')
        c_tt = pick('thuthuatylenh', 'ylenh', 'chidinhthuthuat', 'chidinh', 'thuthuat')
        c_nv = pick('nhanvien')
        c_start = pick('batdau')
        if c_ten is None or c_tt is None: continue
        
        if c_nv and c_start:  # File LỊCH PHÂN CÔNG -> gom lại theo từng bệnh nhân
            groups = {}
            for _, row in df.iterrows():
                ten = clean_str(row[c_ten]); ma = clean_str(row[c_ma]) if c_ma else ''
                key = ma or ten
                if not key: continue
                g = groups.setdefault(key, {'Ma_BN': ma, 'Ten_BN': ten, 'tasks': [], 'bs_kham': None, 'bs_tt': None})
                task = clean_str(row[c_tt]); nv = clean_str(row[c_nv]).replace(" (Theo dõi)", "")
                if not task or task.endswith(" - Lưu"): continue
                if norm_key(task) == 'khambenh':
                    g['bs_kham'] = nv; continue
                if task not in g['tasks']: g['tasks'].append(task)
                tt_name = tt_lookup.get(norm_key(task))
                if tt_name and tt_role.get(tt_name) == 'BS' and not g['bs_tt']: g['bs_tt'] = nv
            raw = []
            for _, g in sorted(groups.items()):
                tasks = sorted(g['tasks'], key=lambda t: danh_sach_thu_thuat.index(tt_lookup[norm_key(t)]) if norm_key(t) in tt_lookup else 999)
                raw.append({'Ma_BN': g['Ma_BN'], 'Ten_BN': g['Ten_BN'], 'BS_Kham': [g['bs_kham'], g['bs_tt']], 'Y_Lenh': tasks})
            return raw, f"Lịch phân công (sheet '{sh}')"
        
        c_bs_ma = pick('mabs', 'bskham', 'mabacsi')
        c_bs_ten = pick('bacsiphutrach', 'bacsi', 'bacsikham', 'bs')
        c_gk = pick('giokham')
        c_rv = pick('gioravien', 'henve', 'giohenve')
        raw = []
        for _, row in df.iterrows():
            raw.append({
                'Ma_BN': row[c_ma] if c_ma else '', 'Ten_BN': row[c_ten],
                'BS_Kham': [row[c_bs_ma] if c_bs_ma else None, row[c_bs_ten] if c_bs_ten else None],
                'Y_Lenh': row[c_tt],
                'Gio_Kham': row[c_gk] if c_gk else '', 'Gio_Ra_Vien': row[c_rv] if c_rv else ''
            })
        return raw, f"Danh sách bệnh nhân (sheet '{sh}')"
    return [], None

def build_import_candidates(raw_list, keep_times):
    rows, warns = [], []
    for r in raw_list:
        ten = clean_str(r.get('Ten_BN'))
        if not ten: continue
        yl, unknown = resolve_y_lenh(r.get('Y_Lenh', ''))
        if unknown: warns.append(f"**{ten}**: bỏ qua thủ thuật không có trong danh mục: {', '.join(unknown)}")
        if not yl: warns.append(f"**{ten}**: không có thủ thuật hợp lệ → không được chọn.")
        bs = resolve_bs(r.get('BS_Kham')) or bs_list[0]
        rows.append({
            'Chon': bool(yl), 'Ma_BN': clean_str(r.get('Ma_BN')), 'Ten_BN': ten,
            'BS_Ten': ten_nv_dict.get(bs, bs), 'Y_Lenh': ", ".join(yl), 'Kham_Benh': not is_weekend,
            'Gio_Kham': parse_time_input(r.get('Gio_Kham', '')) if keep_times else "",
            'Gio_Ra_Vien': parse_time_input(r.get('Gio_Ra_Vien', '')) if keep_times else "",
        })
    return pd.DataFrame(rows, columns=['Chon', 'Ma_BN', 'Ten_BN', 'BS_Ten', 'Y_Lenh', 'Kham_Benh', 'Gio_Kham', 'Gio_Ra_Vien']), warns

IMPORT_MODE_ADD = "➕ Thêm vào danh sách hiện tại"
IMPORT_MODE_REPLACE = "♻️ Thay thế toàn bộ danh sách hiện tại"

def do_import(df_sel, mode, skip_dup_name):
    bs_name_to_code = {ten_nv_dict.get(c, c): c for c in bs_all_codes}
    base = [] if mode == IMPORT_MODE_REPLACE else list(st.session_state.bn_list)
    names = {norm_key(b['Ten_BN']) for b in base}
    codes = {str(b['Ma_BN']) for b in base}
    now_ts = datetime.now().timestamp()
    added, dups = 0, []
    for _, r in df_sel.iterrows():
        ten, yl = clean_str(r['Ten_BN']), clean_str(r['Y_Lenh'])
        if not ten or not yl: continue
        ma = clean_str(r['Ma_BN'])
        if (ma and ma in codes) or (skip_dup_name and norm_key(ten) in names):
            dups.append(ten); continue
        if not ma: ma = gen_ma_bn(codes)
        base.append({
            "Ma_BN": ma, "Ten_BN": ten, "BS_Kham": bs_name_to_code.get(r['BS_Ten'], bs_list[0]),
            "Y_Lenh": yl, "Created_At": now_ts + added * 0.001,
            "Gio_Ra_Vien": parse_time_input(r['Gio_Ra_Vien']), "Gio_Kham": parse_time_input(r['Gio_Kham']),
            "Kham_Benh": to_bool(r['Kham_Benh'], default=not is_weekend)
        })
        names.add(norm_key(ten)); codes.add(ma); added += 1
    st.session_state.bn_list = base
    save_bn_data_db(base, date_str)
    st.session_state.import_open = False
    msg = f"✅ Đã nhập {added} bệnh nhân vào ngày {selected_date.strftime('%d/%m/%Y')}."
    if dups: msg += f" Bỏ qua {len(dups)} BN đã có sẵn: {', '.join(dups)}."
    st.session_state.import_msg = msg

if st.toggle("📥 Nhập danh sách bệnh nhân từ ngày khác / file Excel", key="import_open"):
    with st.container(border=True):
        src = st.radio("Nguồn dữ liệu:", ["📅 Chọn từ ngày đã lưu trong app", "📄 Từ file Excel"], horizontal=True, key="import_src")
        keep_times = st.checkbox("Giữ lại Giờ khám / Giờ ra viện của ngày cũ", value=False, key="import_keep_times")
        raw_list, src_key, warns = [], None, []
        
        if src.startswith("📅"):
            saved = list_saved_bn_dates()
            if not saved:
                st.info("Chưa có ngày nào được lưu (app chỉ giữ dữ liệu 7 ngày gần nhất). Hãy dùng tuỳ chọn 'Từ file Excel'.")
            else:
                d_sel = st.selectbox("Chọn ngày nguồn:", options=list(saved.keys()), key="import_src_date",
                                     format_func=lambda d: f"{WEEKDAY_VN[datetime.strptime(d, '%Y-%m-%d').weekday()]}, {datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m/%Y')} — {saved[d]} BN")
                raw_list = load_bn_of_date(d_sel)
                for r in raw_list: r['BS_Kham'] = [r.get('BS_Kham')]
                src_key = f"d{d_sel}"
        else:
            up = st.file_uploader("Chọn file Excel (file 'Xuất DS BN', file Lịch phân công đã tải xuống, hoặc danh sách tự soạn có cột 'Tên Bệnh Nhân' và 'Thủ thuật')", type=['xlsx'], key="import_file")
            if up is not None:
                try:
                    raw_list, fmt = parse_import_excel(up)
                    if fmt: st.caption(f"📄 Nhận dạng file: **{fmt}**")
                    else: st.error("Không tìm thấy cột 'Tên Bệnh Nhân' và 'Thủ thuật' trong file.")
                except Exception as e:
                    st.error(f"Không đọc được file Excel: {e}")
                src_key = f"f{up.name}_{up.size}"
        
        if raw_list:
            df_cand, warns = build_import_candidates(raw_list, keep_times)
            if warns:
                with st.expander(f"⚠️ {len(warns)} cảnh báo khi đọc dữ liệu"):
                    for w in warns: st.markdown(f"- {w}")
            st.caption(f"Đánh dấu/bỏ chọn BN cần nhập. Cột 'Khám bệnh' đã đặt sẵn theo {WEEKDAY_VN[selected_date.weekday()]} "
                       f"({'không khám' if is_weekend else 'có khám'}), có thể sửa từng dòng. Y lệnh có thể chỉnh lại sau khi nhập.")
            edited_cand = st.data_editor(
                df_cand, key=f"import_editor_{src_key}_{keep_times}_{date_str}", hide_index=True, use_container_width=True, num_rows="fixed",
                column_config={
                    "Chon": st.column_config.CheckboxColumn("Chọn"),
                    "Ma_BN": st.column_config.TextColumn("Mã BN", disabled=True),
                    "Ten_BN": st.column_config.TextColumn("Tên BN"),
                    "BS_Ten": st.column_config.SelectboxColumn("BS phụ trách", options=[ten_nv_dict.get(c, c) for c in bs_all_codes], required=True),
                    "Y_Lenh": st.column_config.TextColumn("Thủ thuật", disabled=True),
                    "Kham_Benh": st.column_config.CheckboxColumn("Khám bệnh"),
                    "Gio_Kham": st.column_config.TextColumn("Giờ khám"),
                    "Gio_Ra_Vien": st.column_config.TextColumn("Giờ ra viện"),
                })
            df_sel = edited_cand[edited_cand['Chon'] == True]
            
            col_i1, col_i2 = st.columns([2, 1])
            with col_i1:
                mode = st.radio("Cách nhập:", [IMPORT_MODE_ADD, IMPORT_MODE_REPLACE], horizontal=True, key="import_mode")
                skip_dup = st.checkbox("Bỏ qua BN trùng tên với danh sách hiện tại", value=True, key="import_skip_dup")
            with col_i2:
                st.write("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                st.button(f"✅ Nhập {len(df_sel)} BN đã chọn", type="primary", use_container_width=True,
                          disabled=len(df_sel) == 0, on_click=do_import, args=(df_sel, mode, skip_dup))

# ==========================================
# KHU VỰC 3: THUẬT TOÁN QUÉT KHE THỜI GIAN (INTERVAL SWEEPING)
# ==========================================
st.markdown("<br><h3 style='color: #27AE60; border-bottom: 2px solid #27AE60; padding-bottom: 5px;'>3. CHẠY THUẬT TOÁN XẾP LỊCH</h3>", unsafe_allow_html=True)

def get_conflict_end(intervals, start, end):
    for (s, e) in intervals:
        if start < e and end > s: return e
    return None

def check_shift(t, ca_lam, limit_morning, start_afternoon):
    # Trả về False nếu t vượt ra ngoài giới hạn ca làm việc
    if ca_lam == "Sáng" and t >= limit_morning: return False
    if ca_lam == "Chiều" and t < start_afternoon: return False
    return True

if st.button("🚀 TIẾN HÀNH XẾP LỊCH", type="primary", use_container_width=True):
    if len(st.session_state.bn_list) == 0: st.stop()

    limit_morning = datetime.strptime(f"{date_str} 11:00:00", "%Y-%m-%d %H:%M:%S")
    start_afternoon = datetime.strptime(f"{date_str} 13:00:00", "%Y-%m-%d %H:%M:%S")
    limit_end_of_day = datetime.strptime(f"{date_str} 23:59:00", "%Y-%m-%d %H:%M:%S")
    base_time_sang = datetime.strptime(f"{date_str} 07:10:00", "%Y-%m-%d %H:%M:%S")

    st.session_state.unscheduled_logs = []
    unscheduled_logs = []
    schedule_records = []
    ten_bn_dict = {bn['Ma_BN']: bn['Ten_BN'] for bn in st.session_state.bn_list}
    
    # Tự động gán BS phụ trách thay thế nếu BS cũ vắng mặt hôm nay
    actual_bs_dict = {}
    for bn in st.session_state.bn_list:
        bs = bn['BS_Kham']
        if bs not in bs_list: bs = bs_list[0] 
        actual_bs_dict[bn['Ma_BN']] = bs

    all_bn = [bn['Ma_BN'] for bn in st.session_state.bn_list]
    patient_busy = {bn: [] for bn in all_bn}
    patient_ready = {} # Đánh dấu thời điểm Bệnh nhân khám xong để chạy thủ thuật
    staff_active_busy = {s: [] for s in (bs_list + ktv_list)}
    
    machine_capacities = {'Máy điện xung': 4, 'Máy từ trường': 1, 'Máy xoa bóp': 2, 'Máy kéo dãn': 1, 'Máy kéo': 1, 'Máy siêu âm': 2, 'Máy Laser': 1, 'Máy xung kích': 1, 'Máy hồng ngoại': 3, 'Máy Laser NM': 2, 'Máy Parafin': 2, 'Máy sóng ngắn': 1, 'Không': 100, 'Không dùng máy': 100}
    machine_busy = {}
    for _, row in df_thongso.iterrows():
        may = str(row['Yeu_Cau_May_Moc']).strip()
        cap = machine_capacities.get(may, 1)
        if may not in machine_busy: machine_busy[may] = {i: [] for i in range(cap)}
    if 'Không' not in machine_busy: machine_busy['Không'] = {0: []}

    staff_shifts = {}
    staff_starts = {}
    for _, row in active_staff.iterrows():
        nv, ca = row['Ma_Nhan_Vien'], row['Ca_Lam_Viec']
        staff_shifts[nv] = ca
        gbd = str(row.get('Gio_Bat_Dau', '')).strip()
        if gbd and gbd.lower() not in ['nan', 'none']:
            try: staff_starts[nv] = datetime.strptime(f"{date_str} {gbd}", "%Y-%m-%d %H:%M")
            except: staff_starts[nv] = start_afternoon if ca == "Chiều" else base_time_sang
        else:
            staff_starts[nv] = start_afternoon if ca == "Chiều" else base_time_sang

    # ================== KHÔI PHỤC LỊCH ĐÃ XẾP TRƯỚC ĐÓ ==================
    scheduled_khambenh = set()
    scheduled_thuthuat = []
    tt_dict = df_thongso.set_index('Ma_Thu_Thuat').to_dict('index')
    
    if 'df_schedule' in st.session_state and not st.session_state.df_schedule.empty:
        df_old = st.session_state.df_schedule.copy()
        for _, row in df_old.iterrows():
            ma_bn = row['Ma_BN']
            if ma_bn not in all_bn: continue
            
            b_task = row['Base_Task']
            t_start = row['Start']
            t_finish = row['Finish']
            nv = row['Nhan_Vien']
            l_tg = row.get('Loai_Thoi_Gian', 'Thực hiện')
            
            bn_obj = next((b for b in st.session_state.bn_list if b['Ma_BN'] == ma_bn), None)
            if not bn_obj: continue
            
            if b_task == "Khám bệnh":
                if not bn_obj.get('Kham_Benh', True): continue  # BN đã được bỏ chọn khám -> huỷ ca khám cũ
                if l_tg == "Thực hiện":
                    scheduled_khambenh.add(ma_bn)
                    patient_ready[ma_bn] = max(patient_ready.get(ma_bn, datetime.min), t_finish)
            else:
                y_lenh_list = [t.strip() for t in bn_obj['Y_Lenh'].split(",") if t.strip()]
                if b_task not in y_lenh_list: continue
                if l_tg == "Thực hiện":
                    scheduled_thuthuat.append((ma_bn, b_task))
            
            schedule_records.append(row.to_dict())
            
            if l_tg == "Thực hiện":
                if b_task == "Khám bệnh":
                    patient_busy[ma_bn].append((t_start, t_finish + timedelta(minutes=2)))
                    if nv in staff_active_busy: staff_active_busy[nv].append((t_start, t_finish + timedelta(minutes=2)))
                else:
                    tt_info = tt_dict.get(ma_thu_thuat_dict.get(b_task))
                    if tt_info:
                        thao_tac = int(tt_info['Thoi_Gian_Thao_Tac_Phut'])
                        cho = int(tt_info['Thoi_Gian_Cho_Phut'])
                        end_total = t_start + timedelta(minutes=thao_tac + cho)
                        
                        patient_busy[ma_bn].append((t_start, end_total + timedelta(minutes=2)))
                        if nv in staff_active_busy: staff_active_busy[nv].append((t_start, t_finish + timedelta(minutes=2)))
                        
                        may_moc = str(tt_info['Yeu_Cau_May_Moc']).strip()
                        if may_moc not in machine_busy: may_moc = 'Không'
                        for idx, m_intervals in machine_busy[may_moc].items():
                            if not get_conflict_end(m_intervals, t_start, end_total):
                                m_intervals.append((t_start, end_total))
                                break

    # ================== GIAI ĐOẠN 1: XẾP LỊCH KHÁM BỆNH ==================
    bns_fixed = []
    bns_auto = []
    for bn in st.session_state.bn_list:
        if bn['Ma_BN'] in scheduled_khambenh:
            continue
        gk_str = str(bn.get('Gio_Kham', '')).strip()
        if not bn.get('Kham_Benh', True):
            # BN KHÔNG khám (VD: T7, CN): bỏ qua 5 phút khám, làm thủ thuật luôn theo y lệnh cũ.
            # Nếu có nhập "Giờ khám" thì xem như giờ BN có mặt -> thủ thuật bắt đầu từ giờ đó.
            if gk_str and gk_str.lower() not in ['nan', 'none']:
                try: patient_ready[bn['Ma_BN']] = datetime.strptime(f"{date_str} {gk_str}", "%Y-%m-%d %H:%M")
                except: pass
            continue
        if gk_str and gk_str.lower() not in ['nan', 'none']:
            try: 
                start_t = datetime.strptime(f"{date_str} {gk_str}", "%Y-%m-%d %H:%M")
                bns_fixed.append((bn, start_t))
            except: bns_auto.append(bn)
        else: bns_auto.append(bn)

    # 1A. Ưu tiên rải lịch Khám có giờ cố định trước
    bns_fixed.sort(key=lambda x: x[1])
    for bn, start_t in bns_fixed:
        ma_bn = bn['Ma_BN']
        bs = actual_bs_dict[ma_bn]
        
        t = start_t
        scheduled = False
        while t < limit_end_of_day:
            end_t = t + timedelta(minutes=5)
            if t < limit_morning and end_t > limit_morning: t = start_afternoon; continue
            if limit_morning <= t < start_afternoon: t = start_afternoon; continue
            
            if not check_shift(t, staff_shifts[bs], limit_morning, start_afternoon):
                t += timedelta(minutes=1); continue

            c_p = get_conflict_end(patient_busy[ma_bn], t, end_t + timedelta(minutes=2))
            if c_p: t = c_p; continue

            c_s = get_conflict_end(staff_active_busy[bs], t, end_t + timedelta(minutes=2))
            if c_s: t = c_s; continue
            
            scheduled = True
            break
            
        if scheduled:
            patient_busy[ma_bn].append((t, end_t + timedelta(minutes=2)))
            staff_active_busy[bs].append((t, end_t + timedelta(minutes=2)))
            patient_ready[ma_bn] = end_t + timedelta(minutes=2) # Lưu giờ BS khám xong
            schedule_records.append(dict(Task="Khám bệnh", Base_Task="Khám bệnh", Loai_Thoi_Gian="Thực hiện", Ma_BN=ma_bn, Ten_BN=ten_bn_dict[ma_bn], Nhan_Vien=bs, Ten_NV_Full=ten_nv_dict.get(bs, bs), Start=t, Finish=end_t))
        else:
            unscheduled_logs.append(f"❌ **{ten_bn_dict[ma_bn]}**: Không kịp xếp 'Khám bệnh' do Bác sĩ {ten_nv_dict.get(bs, bs)} đã quá tải/hết giờ ca {staff_shifts[bs]}.")
            patient_ready[ma_bn] = limit_end_of_day # Khóa không cho làm thủ thuật nếu chưa khám

    # 1B. Điền các ca Khám không chọn giờ (Auto) vào khe hở của BS
    bns_auto.sort(key=lambda x: x.get('Created_At', 0))
    for bn in bns_auto:
        ma_bn = bn['Ma_BN']
        bs = actual_bs_dict[ma_bn]
        
        t = staff_starts[bs]
        scheduled = False
        while t < limit_end_of_day:
            end_t = t + timedelta(minutes=5)
            if t < limit_morning and end_t > limit_morning: t = start_afternoon; continue
            if limit_morning <= t < start_afternoon: t = start_afternoon; continue
            
            if not check_shift(t, staff_shifts[bs], limit_morning, start_afternoon):
                t += timedelta(minutes=1); continue

            c_p = get_conflict_end(patient_busy[ma_bn], t, end_t + timedelta(minutes=2))
            if c_p: t = c_p; continue

            c_s = get_conflict_end(staff_active_busy[bs], t, end_t + timedelta(minutes=2))
            if c_s: t = c_s; continue
            
            scheduled = True
            break
            
        if scheduled:
            patient_busy[ma_bn].append((t, end_t + timedelta(minutes=2)))
            staff_active_busy[bs].append((t, end_t + timedelta(minutes=2)))
            patient_ready[ma_bn] = end_t + timedelta(minutes=2) # Lưu giờ BS khám xong
            schedule_records.append(dict(Task="Khám bệnh", Base_Task="Khám bệnh", Loai_Thoi_Gian="Thực hiện", Ma_BN=ma_bn, Ten_BN=ten_bn_dict[ma_bn], Nhan_Vien=bs, Ten_NV_Full=ten_nv_dict.get(bs, bs), Start=t, Finish=end_t))
        else:
            unscheduled_logs.append(f"❌ **{ten_bn_dict[ma_bn]}**: Không kịp xếp 'Khám bệnh' do Bác sĩ {ten_nv_dict.get(bs, bs)} đã quá tải/hết giờ ca {staff_shifts[bs]}.")
            patient_ready[ma_bn] = limit_end_of_day # Khóa không cho làm thủ thuật nếu chưa khám

    # ================== GIAI ĐOẠN 2: XẾP LỊCH THỦ THUẬT QUÉT NGANG ==================
    jobs = []
    # tt_dict = df_thongso.set_index('Ma_Thu_Thuat').to_dict('index') # Already defined above
    for bn in st.session_state.bn_list:
        ma_bn = bn['Ma_BN']
        if patient_ready.get(ma_bn) == limit_end_of_day: 
            continue # Bỏ qua xếp lịch thủ thuật cho các ca không khám được
            
        rv_str = str(bn.get('Gio_Ra_Vien', '')).strip()
        discharge_dt = limit_end_of_day
        if rv_str and rv_str.lower() not in ['nan', 'none']:
            try: discharge_dt = datetime.strptime(f"{date_str} {rv_str}", "%Y-%m-%d %H:%M")
            except: pass

        for tt in [t.strip() for t in bn['Y_Lenh'].split(",") if t.strip()]:
            if (ma_bn, tt) in scheduled_thuthuat:
                scheduled_thuthuat.remove((ma_bn, tt))
                continue
            jobs.append({'Ma_BN': ma_bn, 'Ma_Thu_Thuat': ma_thu_thuat_dict[tt], 'Ten_Thu_Thuat': tt, 'Discharge_Time': discharge_dt, 'Created_At': bn.get('Created_At', 0)})

    while jobs:
        best_job_idx = -1
        best_start = limit_end_of_day
        best_staff = None
        best_machine_idx = None
        
        for i, job in enumerate(jobs):
            ma_bn = job['Ma_BN']
            ma_tt = job['Ma_Thu_Thuat']
            tt_info = tt_dict[ma_tt]
            thao_tac = int(tt_info['Thoi_Gian_Thao_Tac_Phut'])
            cho = int(tt_info['Thoi_Gian_Cho_Phut'])
            may_moc = str(tt_info['Yeu_Cau_May_Moc']).strip()
            if may_moc not in machine_busy: may_moc = 'Không'
            
            actual_bs = actual_bs_dict[ma_bn]
            
            # Nguyên tắc ĐỘC QUYỀN: Bác sĩ nào khám thì Bác sĩ đó làm
            potential_staff = [actual_bs] if tt_info['Nguoi_Phu_Trach'] == 'BS' else ktv_list
            
            # Quét tìm khe hở sớm nhất (Bắt đầu dò từ lúc bệnh nhân vừa khám xong)
            t = max(base_time_sang, patient_ready.get(ma_bn, base_time_sang))
            
            job_best_t = limit_end_of_day
            job_best_s = None
            job_best_m = None
            
            while t < limit_end_of_day:
                end_active = t + timedelta(minutes=thao_tac)
                end_total = t + timedelta(minutes=thao_tac + cho)
                
                if t < limit_morning and end_total > limit_morning: t = start_afternoon; continue
                if limit_morning <= t < start_afternoon: t = start_afternoon; continue
                    
                c_p = get_conflict_end(patient_busy[ma_bn], t, end_total + timedelta(minutes=2))
                if c_p: t = c_p; continue
                    
                m_idx, min_m_c = None, limit_end_of_day
                for idx, m_intervals in machine_busy[may_moc].items():
                    c_e = get_conflict_end(m_intervals, t, end_total)
                    if not c_e: m_idx = idx; break
                    if c_e < min_m_c: min_m_c = c_e
                if m_idx is None: t = min_m_c; continue
                    
                staff_assigned, min_s_c = None, limit_end_of_day
                for s in potential_staff:
                    if not check_shift(t, staff_shifts[s], limit_morning, start_afternoon): continue
                    c_e = get_conflict_end(staff_active_busy[s], t, end_active + timedelta(minutes=2))
                    if not c_e: staff_assigned = s; break
                    if c_e < min_s_c: min_s_c = c_e
                    
                if staff_assigned is None:
                    t = min_s_c if min_s_c != limit_end_of_day else t + timedelta(minutes=1)
                    continue
                    
                job_best_t = t
                job_best_s = staff_assigned
                job_best_m = m_idx
                break
                
            if job_best_t < best_start:
                best_start, best_job_idx, best_staff, best_machine_idx = job_best_t, i, job_best_s, job_best_m
            elif job_best_t == best_start and job_best_t != limit_end_of_day:
                if job['Discharge_Time'] < jobs[best_job_idx]['Discharge_Time']:
                    best_start, best_job_idx, best_staff, best_machine_idx = job_best_t, i, job_best_s, job_best_m

        # BẮT LỖI CẢNH BÁO QUÁ TẢI (Không tìm được chỗ nào cho tất cả các thủ thuật còn lại)
        if best_job_idx == -1:
            for job in jobs:
                req_s = actual_bs_dict[job['Ma_BN']] if tt_dict[job['Ma_Thu_Thuat']]['Nguoi_Phu_Trach'] == 'BS' else 'KTV'
                nv_name = ten_nv_dict.get(req_s, req_s)
                ca_lam = staff_shifts.get(req_s, 'Ca làm')
                unscheduled_logs.append(f"❌ **{ten_bn_dict[job['Ma_BN']]}**: Không kịp xếp '{job['Ten_Thu_Thuat']}' (do {nv_name} đã hết giờ ca {ca_lam}).")
            break
            
        job = jobs.pop(best_job_idx)
        ma_bn = job['Ma_BN']
        tt_info = tt_dict[job['Ma_Thu_Thuat']]
        thao_tac = int(tt_info['Thoi_Gian_Thao_Tac_Phut'])
        cho = int(tt_info['Thoi_Gian_Cho_Phut'])
        may_moc = str(tt_info['Yeu_Cau_May_Moc']).strip()
        if may_moc not in machine_busy: may_moc = 'Không'
        
        end_active = best_start + timedelta(minutes=thao_tac) 
        end_total = best_start + timedelta(minutes=thao_tac + cho)       
        
        schedule_records.append(dict(Task=job['Ten_Thu_Thuat'], Base_Task=job['Ten_Thu_Thuat'], Loai_Thoi_Gian="Thực hiện", Ma_BN=ma_bn, Ten_BN=ten_bn_dict[ma_bn], Nhan_Vien=best_staff, Ten_NV_Full=ten_nv_dict.get(best_staff, best_staff), Start=best_start, Finish=end_active))
        if cho > 0:
            schedule_records.append(dict(Task=f"{job['Ten_Thu_Thuat']} - Lưu", Base_Task=job['Ten_Thu_Thuat'], Loai_Thoi_Gian="Theo dõi", Ma_BN=ma_bn, Ten_BN=ten_bn_dict[ma_bn], Nhan_Vien=f"{best_staff} (Theo dõi)", Ten_NV_Full=f"{ten_nv_dict.get(best_staff, best_staff)} (Theo dõi)", Start=end_active, Finish=end_total))
            
        patient_busy[ma_bn].append((best_start, end_total + timedelta(minutes=2)))
        staff_active_busy[best_staff].append((best_start, end_active + timedelta(minutes=2)))
        machine_busy[may_moc][best_machine_idx].append((best_start, end_total))

    st.session_state.unscheduled_logs = unscheduled_logs
    df_sched = pd.DataFrame(schedule_records)
    st.session_state.df_schedule = df_sched
    save_sched_data_db(df_sched, date_str)
    st.rerun()

# ==========================================
# KHU VỰC 4: KẾT QUẢ, TRA CỨU & BIỂU ĐỒ
# ==========================================
if 'df_schedule' in st.session_state:
    df_schedule = st.session_state.df_schedule
    st.success(f"✅ Đã lập xong lịch cho ngày: {selected_date.strftime('%d/%m/%Y')}")
    
    # ⚠️ HIỂN THỊ CẢNH BÁO QUÁ TẢI/VƯỢT GIỜ
    if st.session_state.get('unscheduled_logs'):
        st.error("⚠️ CẢNH BÁO QUÁ TẢI LỊCH LÀM VIỆC")
        for log in st.session_state.unscheduled_logs:
            st.markdown(f"- {log}")
        st.info("💡 Hướng xử lý: đổi ca làm việc thành 'Cả ngày' hoặc điều chỉnh y lệnh để giảm thủ thuật hoặc chuyển BN cho BS khác.")

    df_schedule['Start_str'] = df_schedule['Start'].dt.strftime('%H:%M')
    df_schedule['Finish_str'] = df_schedule['Finish'].dt.strftime('%H:%M')
    
    df_export = df_schedule.copy()
    df_export['Ngày'] = df_export['Start'].dt.strftime('%d/%m/%Y')
    df_export = df_export[['Ngày', 'Ten_NV_Full', 'Ma_BN', 'Ten_BN', 'Task', 'Start_str', 'Finish_str']]
    df_export.columns = ['Ngày', 'Nhân Viên', 'Mã BN', 'Tên Bệnh Nhân', 'Thủ thuật', 'Bắt Đầu', 'Kết Thúc']
    df_export.sort_values(by=['Nhân Viên', 'Bắt Đầu'], inplace=True)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Lich_Trinh')
        build_bn_export_df(st.session_state.bn_list).to_excel(writer, index=False, sheet_name='Danh_Sach_BN')
    st.download_button("📥 TẢI XUỐNG FILE EXCEL LỊCH PHÂN CÔNG", data=buffer.getvalue(), file_name=f"Lich_YHCT_{selected_date.strftime('%Y%m%d')}.xlsx", type="primary")
    st.divider()

    st.markdown("<h3 style='color: #8E44AD; border-bottom: 2px solid #8E44AD; padding-bottom: 5px;'>4. TRA CỨU LỊCH TRÌNH CÁ NHÂN</h3>", unsafe_allow_html=True)
    col_tc_nv, col_tc_bn = st.columns(2)
    with col_tc_nv:
        nv_chon = st.selectbox("Tra cứu lịch Nhân viên:", options=["-- Chọn Nhân viên --"] + list(df_schedule['Ten_NV_Full'].str.replace(" (Theo dõi)", "").unique()))
        if nv_chon != "-- Chọn Nhân viên --":
            df_nv = df_schedule[df_schedule['Ten_NV_Full'].str.contains(nv_chon, regex=False)].sort_values(by='Start')
            st.dataframe(df_nv[['Start_str', 'Finish_str', 'Task', 'Ten_BN']].rename(columns={'Start_str': 'Bắt đầu', 'Finish_str': 'Kết thúc', 'Task': 'Công việc', 'Ten_BN': 'Bệnh nhân'}), hide_index=True, use_container_width=True)

    with col_tc_bn:
        bn_chon = st.selectbox("Tra cứu lịch Bệnh nhân:", options=["-- Chọn Bệnh nhân --"] + list(df_schedule['Ten_BN'].unique()))
        if bn_chon != "-- Chọn Bệnh nhân --":
            df_bn = df_schedule[df_schedule['Ten_BN'] == bn_chon].sort_values(by='Start')
            st.dataframe(df_bn[['Start_str', 'Finish_str', 'Task', 'Ten_NV_Full']].rename(columns={'Start_str': 'Bắt đầu', 'Finish_str': 'Kết thúc', 'Task': 'Thủ thuật', 'Ten_NV_Full': 'Nhân viên phụ trách'}), hide_index=True, use_container_width=True)

    st.divider()
    
    with st.expander("📊 HIỂN THỊ / THU GỌN BIỂU ĐỒ GANTT", expanded=False):
        def sort_nv_group(name): return (name.replace(" (Theo dõi)", ""), 1 if " (Theo dõi)" in name else 0)
        y_order = sorted(df_schedule['Nhan_Vien'].unique(), key=sort_nv_group)

        st.subheader("Lịch trình Tổng quát Nhân viên")
        fig_nv = px.timeline(df_schedule, x_start="Start", x_end="Finish", y="Nhan_Vien", color="Base_Task", text="Ma_BN", custom_data=['Task', 'Start_str', 'Finish_str', 'Ten_BN', 'Ten_NV_Full'])
        fig_nv.update_traces(marker_line_color='rgba(0,0,0,0.7)', marker_line_width=1.5, opacity=0.9, textfont=dict(color='white', size=13, weight="bold"), hovertemplate="<b>%{customdata[4]}</b><br>Bệnh nhân: %{customdata[3]}<br>Thủ thuật: %{customdata[0]}<br>Thời gian: %{customdata[1]} - %{customdata[2]}<extra></extra>", textposition='inside', insidetextanchor='middle')
        fig_nv.update_layout(yaxis=dict(categoryorder='array', categoryarray=y_order, autorange="reversed", title=""), legend_title="Chú thích Y lệnh", uniformtext_minsize=10, uniformtext_mode='hide', xaxis_tickformat="%H:%M", xaxis_title="", plot_bgcolor="rgba(240, 240, 240, 0.5)", height=700)
        st.plotly_chart(fig_nv, use_container_width=True)

        st.subheader("Lộ trình Bệnh nhân di chuyển")
        fig_bn = px.timeline(df_schedule, x_start="Start", x_end="Finish", y="Ma_BN", color="Base_Task", text="Task", custom_data=['Ten_NV_Full', 'Start_str', 'Finish_str', 'Task', 'Ten_BN'])
        fig_bn.update_traces(marker_line_color='rgba(0,0,0,0.7)', marker_line_width=1.5, opacity=0.9, textfont=dict(color='white', size=13, weight="bold"), hovertemplate="<b>Bệnh nhân: %{customdata[4]}</b><br>Nhân viên: %{customdata[0]}<br>Thủ thuật: %{customdata[3]}<br>Thời gian: %{customdata[1]} - %{customdata[2]}<extra></extra>", textposition='inside', insidetextanchor='middle')
        fig_bn.update_layout(yaxis=dict(autorange="reversed", title=""), showlegend=False, uniformtext_minsize=10, uniformtext_mode='hide', xaxis_tickformat="%H:%M", xaxis_title="", plot_bgcolor="rgba(240, 240, 240, 0.5)", height=500)
        st.plotly_chart(fig_bn, use_container_width=True)

st.markdown("---")
st.markdown("""
    <div style='text-align: center; font-size: 1.2rem; font-weight: bold; margin-top: 30px; color: #34495E;'>
        XÂY DỰNG BỞI <span style='color: #0000FF;'>BS. MAI HUỲNH NGỌC TÂN</span> - <span style='color: #8E44AD;'>BS. LÊ UYÊN PHƯƠNG VY</span>
    </div>
""", unsafe_allow_html=True)