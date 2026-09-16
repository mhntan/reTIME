import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import io
import os
import json
import re
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
# HÀM LƯU TRỮ ĐỒNG BỘ 2 CHIỀU (LOCAL + GOOGLE SHEETS)
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

def sanitize_bn_list(bn_list):
    for bn in bn_list:
        if 'Gio_Ra_Vien' not in bn: bn['Gio_Ra_Vien'] = ""
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

        # Dọn rác 7 ngày trực tiếp trên Google Sheets
        limit_date_str = (datetime.today().date() - timedelta(days=7)).strftime("%Y-%m-%d")
        df_all = df_all[df_all['Date'] >= limit_date_str]
        
        # Xóa dữ liệu của ngày hiện tại để ghi đè mảng mới
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
    df.to_csv(f"ns_{date_str}.csv", index=False)
    update_gsheets_safe("NhanSu", df, date_str)

def save_bn_data_db(bn_list, date_str):
    with open(f"bn_{date_str}.json", 'w', encoding='utf-8') as f: json.dump(bn_list, f, ensure_ascii=False, indent=2)
    df = pd.DataFrame(bn_list)
    if df.empty: df = pd.DataFrame(columns=["Ma_BN", "Ten_BN", "BS_Kham", "Y_Lenh", "Created_At", "Gio_Ra_Vien"])
    update_gsheets_safe("BenhNhan", df, date_str)

def save_sched_data_db(df, date_str):
    df.to_json(f"sched_{date_str}.json", orient='records', date_format='iso')
    update_gsheets_safe("LichTrinh", df, date_str)

def parse_time_input(time_str):
    if pd.isna(time_str): return ""
    time_str = str(time_str).strip().replace(';', ':')
    if not time_str: return ""
    if re.match(r'^\d{4}$', time_str): time_str = f"{time_str[:2]}:{time_str[2:]}"
    elif re.match(r'^\d{3}$', time_str): time_str = f"0{time_str[0]}:{time_str[1:]}"
    try: datetime.strptime(time_str, "%H:%M"); return time_str
    except: return time_str

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
    selected_date = st.date_input("📅 Chọn Ngày làm việc", value=st.session_state.get('selected_date', datetime.today().date()))
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

if USE_GSHEETS: st.caption("🟢 Đang kết nối Google Sheets")
else: st.caption("🟡 Đang hoạt động offline")

# TÍNH NĂNG TIME TRAVEL: KẾT HỢP ĐỌC TỪ LOCAL -> GOOGLE SHEETS
if 'selected_date' not in st.session_state or st.session_state.selected_date != selected_date:
    st.session_state.selected_date = selected_date
    
    # 1. LOAD NHÂN SỰ
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
    for col in ['Gio_Bat_Dau', 'Ghi_Chu', 'Ten_Nhan_Vien', 'Ca_Lam_Viec']:
        if col in st.session_state.ns_data.columns:
            st.session_state.ns_data[col] = st.session_state.ns_data[col].fillna("").astype(str).replace("nan", "")

    # 2. LOAD BỆNH NHÂN
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
        
    # 3. LOAD LỊCH TRÌNH (BIỂU ĐỒ)
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
    with col_n1: new_ten = st.text_input("Họ và Tên Nhân viên")
    with col_n2: new_role = st.selectbox("Vai trò", ["Bác sĩ", "Kỹ thuật viên"])
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
    with col_d1: nv_xoa = st.selectbox("Chọn nhân viên cần xóa:", options=["-- Chọn --"] + st.session_state.ns_data['Ten_Nhan_Vien'].tolist())
    with col_d2:
        st.write("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button("Xóa nhân viên", type="secondary", use_container_width=True):
            if nv_xoa != "-- Chọn --":
                st.session_state.ns_data = st.session_state.ns_data[st.session_state.ns_data['Ten_Nhan_Vien'] != nv_xoa].reset_index(drop=True)
                save_ns_data_db(st.session_state.ns_data, date_str)
                st.rerun()

edited_ns = st.data_editor(
    st.session_state.ns_data, key="ns_editor_widget",
    column_config={
        "Di_Lam": st.column_config.CheckboxColumn("Đi làm?", default=True),
        "Ma_Nhan_Vien": st.column_config.TextColumn("Mã NV", disabled=True),
        "Ten_Nhan_Vien": st.column_config.TextColumn("Họ và Tên"),
        "Ca_Lam_Viec": st.column_config.SelectboxColumn("Ca làm", options=["Sáng", "Chiều", "Cả ngày"]),
        "Gio_Bat_Dau": st.column_config.TextColumn("Giờ bắt đầu (Vd: 07:10)"),
        "Ghi_Chu": "Ghi chú"
    }, hide_index=True, use_container_width=True
)

if not edited_ns.equals(st.session_state.ns_data):
    for i in range(len(edited_ns)):
        val = str(edited_ns.at[i, 'Gio_Bat_Dau']).strip()
        if val and val not in ['None', 'nan']: 
            parsed = parse_time_input(val)
            if parsed != val: 
                edited_ns.at[i, 'Gio_Bat_Dau'] = parsed
                
    st.session_state.ns_data = edited_ns.copy()
    save_ns_data_db(st.session_state.ns_data, date_str)
    st.rerun() 

active_staff = edited_ns[edited_ns['Di_Lam'] == True]
ktv_list = active_staff[active_staff['Ma_Nhan_Vien'].str.startswith('ktv-')]['Ma_Nhan_Vien'].tolist()
bs_list = active_staff[active_staff['Ma_Nhan_Vien'].str.startswith('bs-')]['Ma_Nhan_Vien'].tolist()
ten_nv_dict = dict(zip(edited_ns['Ma_Nhan_Vien'], edited_ns['Ten_Nhan_Vien']))

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

col_form, col_table = st.columns([1, 1.5])
with col_form:
    st.markdown("#### ➕ Thêm Bệnh Nhân Mới")
    with st.container(border=True):
        with st.form("form_nhap_bn", clear_on_submit=True):
            col_b1, col_b2 = st.columns([2, 1])
            with col_b1: ten_bn = st.text_input("Tên Bệnh Nhân (Bắt buộc)")
            with col_b2: gio_ra_vien = st.text_input("Giờ ra viện (nếu có)")
            
            bs_kham = st.selectbox("Bác sĩ phụ trách", options=bs_list, format_func=lambda x: ten_nv_dict.get(x, x))
            y_lenh_chon = st.multiselect("Chỉ định Thủ thuật", options=danh_sach_thu_thuat)
            
            if st.form_submit_button("Lập Hồ Sơ", type="primary", use_container_width=True):
                if ten_bn.strip() == "": st.error("Vui lòng nhập tên Bệnh nhân!")
                elif not y_lenh_chon: st.error("Vui lòng chọn ít nhất 1 thủ thuật!")
                else:
                    today_prefix = datetime.now().strftime("%d%m")
                    count_today = sum(1 for b in st.session_state.bn_list if str(b['Ma_BN']).startswith(f"BN{today_prefix}"))
                    ma_bn = f"BN{today_prefix}-{count_today+1:02d}"
                    st.session_state.bn_list.append({
                        "Ma_BN": ma_bn, "Ten_BN": ten_bn, "BS_Kham": bs_kham, 
                        "Y_Lenh": ", ".join(y_lenh_chon), "Created_At": datetime.now().timestamp(),
                        "Gio_Ra_Vien": parse_time_input(gio_ra_vien)
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
            st.dataframe(df_hienthi[['Ma_BN', 'Ten_BN', 'Gio_Ra_Vien', 'BS_Kham', 'Y_Lenh']].rename(columns={'Gio_Ra_Vien': 'Hẹn về'}), hide_index=True, use_container_width=True, height=200)
            
            with st.expander("✏️ Điều chỉnh Y Lệnh hoặc Cho Ra Viện"):
                edit_idx = st.selectbox("🔍 Chọn Bệnh nhân:", options=range(len(st.session_state.bn_list)), format_func=lambda i: f"{st.session_state.bn_list[i]['Ma_BN']} - {st.session_state.bn_list[i]['Ten_BN']}")
                selected_bn = st.session_state.bn_list[edit_idx]
                current_yl = [t.strip() for t in selected_bn['Y_Lenh'].split(",") if t.strip()]
                
                col_e1, col_e2 = st.columns(2)
                with col_e1: edit_bs = st.selectbox("Đổi BS phụ trách:", options=bs_list, format_func=lambda x: ten_nv_dict.get(x, x), index=bs_list.index(selected_bn['BS_Kham']) if selected_bn['BS_Kham'] in bs_list else 0)
                with col_e2: edit_rv = st.text_input("Giờ ra viện mới, VD 16:30 ", value=selected_bn.get('Gio_Ra_Vien', ''))
                
                edit_yl = st.multiselect("Thêm/Bớt Thủ thuật:", options=danh_sach_thu_thuat, default=current_yl)
                
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("💾 Cập nhật", type="primary", use_container_width=True):
                    st.session_state.bn_list[edit_idx]['BS_Kham'] = edit_bs
                    st.session_state.bn_list[edit_idx]['Y_Lenh'] = ", ".join(edit_yl)
                    st.session_state.bn_list[edit_idx]['Gio_Ra_Vien'] = parse_time_input(edit_rv)
                    save_bn_data_db(st.session_state.bn_list, date_str)
                    st.rerun()
                if col_btn2.button("🏥 Ra viện", type="secondary", use_container_width=True):
                    st.session_state.bn_list.pop(edit_idx)
                    save_bn_data_db(st.session_state.bn_list, date_str)
                    st.rerun()
        else: st.info("Khoa hiện không có bệnh nhân.")

# ==========================================
# KHU VỰC 3: TÍNH TOÁN & RÀNG BUỘC
# ==========================================
st.markdown("<br><h3 style='color: #27AE60; border-bottom: 2px solid #27AE60; padding-bottom: 5px;'>3. CHẠY THUẬT TOÁN XẾP LỊCH</h3>", unsafe_allow_html=True)

def adjust_for_lunch_break(start_t, duration_m, date_string):
    limit_morning = datetime.strptime(f"{date_string} 11:00:00", "%Y-%m-%d %H:%M:%S")
    start_afternoon = datetime.strptime(f"{date_string} 13:00:00", "%Y-%m-%d %H:%M:%S")
    end_t = start_t + timedelta(minutes=duration_m)
    if start_t < limit_morning and end_t > limit_morning: return start_afternoon
    elif limit_morning <= start_t < start_afternoon: return start_afternoon
    return start_t

def is_staff_available(staff_id, start_t, staff_shifts):
    shift = staff_shifts.get(staff_id, "Cả ngày")
    if shift == "Sáng" and start_t.hour >= 12: return False 
    if shift == "Chiều" and start_t.hour < 12: return False 
    return True

if st.button("🚀 TIẾN HÀNH XẾP LỊCH TỰ ĐỘNG", type="primary", use_container_width=True):
    if len(st.session_state.bn_list) == 0: st.stop()

    jobs = []
    ten_bn_dict = {}
    discharge_dict = {}
    
    for bn in st.session_state.bn_list:
        ma_bn = bn['Ma_BN']
        ten_bn_dict[ma_bn] = bn['Ten_BN']
        
        rv_str = bn.get('Gio_Ra_Vien', '')
        if rv_str:
            try: discharge_dict[ma_bn] = datetime.strptime(f"{date_str} {rv_str}", "%Y-%m-%d %H:%M")
            except: discharge_dict[ma_bn] = datetime.max
        else:
            discharge_dict[ma_bn] = datetime.max

        for tt in [t.strip() for t in bn['Y_Lenh'].split(",") if t.strip()]:
            jobs.append({'Ma_BN': ma_bn, 'BS_Kham': bn['BS_Kham'], 'Ma_Thu_Thuat': ma_thu_thuat_dict[tt], 'Ten_Thu_Thuat': tt, 'Created_At': bn.get('Created_At', 0), 'Discharge_Time': discharge_dict[ma_bn]})

    base_time_sang = datetime.strptime(f"{date_str} 07:10:00", "%Y-%m-%d %H:%M:%S")
    base_time_chieu = datetime.strptime(f"{date_str} 13:00:00", "%Y-%m-%d %H:%M:%S")
    
    staff_ready, staff_shifts = {}, {}
    for _, row in active_staff.iterrows():
        nv, ca = row['Ma_Nhan_Vien'], row['Ca_Lam_Viec']
        staff_shifts[nv] = ca
        gbd = parse_time_input(str(row.get('Gio_Bat_Dau', '')))
        if gbd:
            try: staff_ready[nv] = datetime.strptime(f"{date_str} {gbd}", "%Y-%m-%d %H:%M")
            except: staff_ready[nv] = base_time_chieu if ca == "Chiều" else base_time_sang
        else:
            staff_ready[nv] = base_time_chieu if ca == "Chiều" else base_time_sang

    patient_ready = {bn['Ma_BN']: staff_ready.get(bn['BS_Kham'], base_time_sang) for bn in st.session_state.bn_list}
    schedule_records = []
    actual_bs_dict = {}

    for bn in st.session_state.bn_list:
        ma_bn, actual_bs = bn['Ma_BN'], bn['BS_Kham']
        if actual_bs not in staff_shifts: actual_bs = min(bs_list, key=lambda b: staff_ready[b])
        adj_time = adjust_for_lunch_break(max(staff_ready[actual_bs], patient_ready[ma_bn]), 5, date_str)
        
        if not is_staff_available(actual_bs, adj_time, staff_shifts):
            available_bs = [b for b in bs_list if is_staff_available(b, adjust_for_lunch_break(max(staff_ready[b], patient_ready[ma_bn]), 5, date_str), staff_shifts)]
            if available_bs:
                actual_bs = min(available_bs, key=lambda b: adjust_for_lunch_break(max(staff_ready[b], patient_ready[ma_bn]), 5, date_str))
                adj_time = adjust_for_lunch_break(max(staff_ready[actual_bs], patient_ready[ma_bn]), 5, date_str)

        actual_bs_dict[ma_bn] = actual_bs
        end_exam = adj_time + timedelta(minutes=5)
        schedule_records.append(dict(Task="Khám bệnh", Base_Task="Khám bệnh", Loai_Thoi_Gian="Thực hiện", Ma_BN=ma_bn, Ten_BN=ten_bn_dict[ma_bn], Nhan_Vien=actual_bs, Ten_NV_Full=ten_nv_dict.get(actual_bs, actual_bs), Start=adj_time, Finish=end_exam))
        
        staff_ready[actual_bs] = end_exam
        patient_ready[ma_bn] = end_exam + timedelta(minutes=2)

    machine_pool = {}
    machine_capacities = {
        'Máy điện xung': 2, 'Máy từ trường': 1, 'Máy xoa bóp': 2, 'Máy kéo dãn': 1, 
        'Máy kéo': 1, 'Máy siêu âm': 2, 'Máy Laser': 1, 'Máy xung kích': 1, 
        'Máy hồng ngoại': 3, 'Máy Laser NM': 2, 'Máy Parafin': 2, 'Máy sóng ngắn': 1,
        'Không': 76, 'Không dùng máy': 76
    }
    for _, row in df_thongso.iterrows():
        may = str(row['Yeu_Cau_May_Moc']).strip()
        if may not in machine_pool: machine_pool[may] = [base_time_sang] * machine_capacities.get(may, 1)
    if 'Không' not in machine_pool: machine_pool['Không'] = [base_time_sang] * 76
    tt_dict = df_thongso.set_index('Ma_Thu_Thuat').to_dict('index')
    
    while jobs:
        jobs.sort(key=lambda j: (j['Discharge_Time'], patient_ready[j['Ma_BN']], j['Created_At']))
        job = jobs.pop(0)
        ma_bn, ma_tt, actual_bs = job['Ma_BN'], job['Ma_Thu_Thuat'], actual_bs_dict[job['Ma_BN']]
        tt_info = tt_dict[ma_tt]
        thao_tac, cho = int(tt_info['Thoi_Gian_Thao_Tac_Phut']), int(tt_info['Thoi_Gian_Cho_Phut'])
        may_moc = str(tt_info['Yeu_Cau_May_Moc']).strip()
        if may_moc not in machine_pool: may_moc = 'Không'
        
        potential_staff = [actual_bs] + [b for b in bs_list if b != actual_bs] if tt_info['Nguoi_Phu_Trach'] == 'BS' else ktv_list
        earliest_start, best_staff, best_machine_idx = datetime.max, None, None
        valid_slot_found = False
        
        for s in potential_staff:
            if s not in staff_ready: continue
            for m_idx, m_ready in enumerate(machine_pool[may_moc]):
                adj_start = adjust_for_lunch_break(max(patient_ready[ma_bn], staff_ready[s], m_ready), thao_tac + cho, date_str)
                if not is_staff_available(s, adj_start, staff_shifts): continue
                if tt_info['Nguoi_Phu_Trach'] == 'BS' and s != actual_bs:
                    prim_adj = adjust_for_lunch_break(max(patient_ready[ma_bn], staff_ready[actual_bs], m_ready), thao_tac + cho, date_str)
                    if is_staff_available(actual_bs, prim_adj, staff_shifts): continue
                
                if adj_start + timedelta(minutes=thao_tac+cho) <= job['Discharge_Time']:
                    if adj_start < earliest_start: 
                        earliest_start, best_staff, best_machine_idx = adj_start, s, m_idx
                        valid_slot_found = True

        if not valid_slot_found:
            for s in potential_staff:
                if s not in staff_ready: continue
                for m_idx, m_ready in enumerate(machine_pool[may_moc]):
                    adj_start = adjust_for_lunch_break(max(patient_ready[ma_bn], staff_ready[s], m_ready), thao_tac + cho, date_str)
                    if not is_staff_available(s, adj_start, staff_shifts): continue
                    if tt_info['Nguoi_Phu_Trach'] == 'BS' and s != actual_bs:
                        prim_adj = adjust_for_lunch_break(max(patient_ready[ma_bn], staff_ready[actual_bs], m_ready), thao_tac + cho, date_str)
                        if is_staff_available(actual_bs, prim_adj, staff_shifts): continue
                        
                    if adj_start < earliest_start: 
                        earliest_start, best_staff, best_machine_idx = adj_start, s, m_idx
                    
        end_active = earliest_start + timedelta(minutes=thao_tac) 
        end_total = end_active + timedelta(minutes=cho)       
        
        schedule_records.append(dict(Task=job['Ten_Thu_Thuat'], Base_Task=job['Ten_Thu_Thuat'], Loai_Thoi_Gian="Thực hiện", Ma_BN=ma_bn, Ten_BN=ten_bn_dict[ma_bn], Nhan_Vien=best_staff, Ten_NV_Full=ten_nv_dict.get(best_staff, best_staff), Start=earliest_start, Finish=end_active))
        if cho > 0:
            schedule_records.append(dict(Task=f"{job['Ten_Thu_Thuat']} - Lưu", Base_Task=job['Ten_Thu_Thuat'], Loai_Thoi_Gian="Theo dõi", Ma_BN=ma_bn, Ten_BN=ten_bn_dict[ma_bn], Nhan_Vien=f"{best_staff} (Theo dõi)", Ten_NV_Full=f"{ten_nv_dict.get(best_staff, best_staff)} (Theo dõi)", Start=end_active, Finish=end_total))
            
        staff_ready[best_staff] = end_active + timedelta(minutes=2)
        patient_ready[ma_bn] = end_total + timedelta(minutes=2)
        machine_pool[may_moc][best_machine_idx] = end_total + timedelta(minutes=2)

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

    df_schedule['Start_str'] = df_schedule['Start'].dt.strftime('%H:%M')
    df_schedule['Finish_str'] = df_schedule['Finish'].dt.strftime('%H:%M')
    
    df_export = df_schedule.copy()
    df_export['Ngày'] = df_export['Start'].dt.strftime('%d/%m/%Y')
    df_export = df_export[['Ngày', 'Ten_NV_Full', 'Ma_BN', 'Ten_BN', 'Task', 'Start_str', 'Finish_str']]
    df_export.columns = ['Ngày', 'Nhân Viên', 'Mã BN', 'Tên Bệnh Nhân', 'Thủ thuật', 'Bắt Đầu', 'Kết Thúc']
    df_export.sort_values(by=['Nhân Viên', 'Bắt Đầu'], inplace=True)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer: df_export.to_excel(writer, index=False, sheet_name='Lich_Trinh')
    st.download_button("📥 TẢI XUỐNG FILE EXCEL LỊCH SẮP XẾP", data=buffer.getvalue(), file_name=f"Lich_YHCT_{selected_date.strftime('%Y%m%d')}.xlsx", type="primary")
    st.divider()

    st.markdown("<h3 style='color: #8E44AD; border-bottom: 2px solid #8E44AD; padding-bottom: 5px;'>4. TRA CỨU LỊCH TRÌNH CÁ NHÂN</h3>", unsafe_allow_html=True)
    col_tc_nv, col_tc_bn = st.columns(2)
    with col_tc_nv:
        nv_chon = st.selectbox("Xem lịch Nhân viên:", options=["-- Chọn Nhân viên --"] + list(df_schedule['Ten_NV_Full'].str.replace(" (Theo dõi)", "").unique()))
        if nv_chon != "-- Chọn Nhân viên --":
            df_nv = df_schedule[df_schedule['Ten_NV_Full'].str.contains(nv_chon, regex=False)].sort_values(by='Start')
            st.dataframe(df_nv[['Start_str', 'Finish_str', 'Task', 'Ten_BN']].rename(columns={'Start_str': 'Bắt đầu', 'Finish_str': 'Kết thúc', 'Task': 'Công việc', 'Ten_BN': 'Bệnh nhân'}), hide_index=True, use_container_width=True)

    with col_tc_bn:
        bn_chon = st.selectbox("Xem lịch Bệnh nhân:", options=["-- Chọn Bệnh nhân --"] + list(df_schedule['Ten_BN'].unique()))
        if bn_chon != "-- Chọn Bệnh nhân --":
            df_bn = df_schedule[df_schedule['Ten_BN'] == bn_chon].sort_values(by='Start')
            st.dataframe(df_bn[['Start_str', 'Finish_str', 'Task', 'Ten_NV_Full']].rename(columns={'Start_str': 'Bắt đầu', 'Finish_str': 'Kết thúc', 'Task': 'Thủ thuật', 'Ten_NV_Full': 'Nhân viên phụ trách'}), hide_index=True, use_container_width=True)

    st.divider()
    
    with st.expander("📊 HIỂN THỊ / THU GỌN BIỂU ĐỒ GANTT", expanded=False):
        def sort_nv_group(name): return (name.replace(" (Theo dõi)", ""), 1 if " (Theo dõi)" in name else 0)
        y_order = sorted(df_schedule['Nhan_Vien'].unique(), key=sort_nv_group)

        st.subheader("Lịch tổng quát Nhân viên")
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
# ĐỊNH DẠNG LẠI TÊN TÁC GIẢ BÊN DƯỚI
st.markdown("""
    <div style='text-align: center; font-size: 1.2rem; font-weight: bold; margin-top: 30px; color: #34495E;'>
        XÂY DỰNG BỞI <span style='color: #0000FF;'>BS. MAI HUỲNH NGỌC TÂN</span> - <span style='color: #8E44AD;'>BS. LÊ UYÊN PHƯƠNG VY</span>
    </div>
""", unsafe_allow_html=True)
