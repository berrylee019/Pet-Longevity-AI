import streamlit as st
import google.generativeai as genai
import os
import sqlite3
import datetime
import re
import pandas as pd
from PIL import Image
from fpdf import FPDF
from icrawler.builtin import BingImageCrawler, GoogleImageCrawler, BaiduImageCrawler

# --- Timezone Logic (Kept KST for consistency in logs) ---
def get_kst_now():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst)

# --- 1. System Initialization ---
def init_system():
    for path in ["dataset/multi_view", "reports", "database_images"]:
        if not os.path.exists(path):
            os.makedirs(path)
    
    conn = sqlite3.connect('pet_analysis.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, bcs INTEGER, pace REAL, reason TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS collected_images
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, img_path TEXT, source TEXT, collect_date TEXT)''')
    conn.commit()
    conn.close()

init_system()

# --- 2. PDF Report Logic (Global/English) ---
class PetReportPDF(FPDF):
    def header(self):
        header_img = "card_bg1.png" # Updated English version image
        if os.path.exists(header_img):
            self.image(header_img, x=10, y=10, w=190)
            self.ln(32)
        else:
            self.set_font('Arial', 'B', 20)
            self.cell(0, 15, 'Pet Health Report', ln=True, align='C')
            self.ln(5)

def create_pdf_report(breed, bcs, pace, reason):
    try:
        pdf = PetReportPDF()
        pdf.set_auto_page_break(auto=False, margin=0) 
        pdf.add_page()
        
        pdf.set_font('Arial', 'B', 18)
        pdf.cell(0, 10, '', ln=True, align='C')
        pdf.ln(5)
        
        kst_time = get_kst_now().strftime('%Y-%m-%d %H:%M')
        table_width = 160
        start_x = (210 - table_width) / 2
        
        data = [
            ['Selected Breed', f'{breed}'], 
            ['Body Condition Score (BCS)', f'{bcs} / 9 pts'], 
            ['Estimated Aging Pace', f'{pace}x Speed'], 
            ['Report Date (KST)', f'{kst_time}']
        ]
        
        pdf.set_font('Arial', 'B', 10)
        for row in data:
            pdf.set_x(start_x)
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(60, 8, row[0], border=1, fill=True)
            pdf.cell(100, 8, row[1], border=1, ln=True, align='C')
            
        pdf.ln(8)
        pdf.set_x(start_x)
        pdf.set_font('Arial', 'B', 14)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 8, '[ AI Veterinarian Comprehensive Opinion ]', ln=True)
        pdf.ln(2)
        
        clean_reason = reason.replace('**', '').replace('*', '').strip()
        font_size = 8 if len(clean_reason) > 600 else 9 if len(clean_reason) > 400 else 10
            
        pdf.set_font('Arial', '', font_size)
        pdf.set_text_color(60, 60, 60)
        pdf.set_x(start_x)
        pdf.multi_cell(table_width, 5.5, clean_reason, border=0, align='L')
        
        pdf.set_y(260)
        pdf.set_font('Arial', 'B', 11)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 8, 'Premium Analysis Request: bslee@yahoo.com', align='C', ln=True)
        
        pdf.set_font('Arial', 'I', 8)
        pdf.set_text_color(160, 160, 160)
        pdf.cell(0, 5, 'Powered by: [Pet Longevity AI] | AI Simulation Results', align='C', ln=True)
        
        report_path = f"reports/Report_{breed}_{get_kst_now().strftime('%Y%m%d%H%M')}.pdf"
        pdf.output(report_path)
        return report_path
    except Exception as e:
        return None

# --- 3. AI Analysis Function ---
def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        prompt = f"As a professional veterinarian, analyze these photos of a {breed_name}. Provide 'Score / Clinical Opinion' in English. No special characters."
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        
        if '/' in res_text:
            parts = res_text.split('/')
            bcs_val = int(re.search(r'\d', parts[0]).group()) if re.search(r'\d', parts[0]) else 5
            clean_reason = parts[1].strip()
        else:
            bcs_match = re.search(r'\d', res_text)
            bcs_val = int(bcs_match.group()) if bcs_match else 5
            clean_reason = res_text
        return {"bcs": bcs_val, "reason": clean_reason}
    except: return {"bcs": 5, "reason": "An error occurred during AI analysis."}

def calculate_pace_of_aging(bcs, breed):
    pace = 1.0 + (abs(5-bcs) * 0.15)
    if breed in ["Retriever", "German Shepherd"]: pace *= 1.15
    return round(pace, 2)

# --- 4. Streamlit UI (English) ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')

st.sidebar.title("🐾 System Config")
selected_breed = st.sidebar.selectbox("Target Breed", ["Retriever", "Maltese", "Poodle", "Pomeranian", "Others"])
st.sidebar.divider()
admin_pass = st.sidebar.text_input("Admin Password", type="password")
is_admin = (admin_pass == "2004")

tabs = st.tabs(["🔍 AI Diagnosis"] + (["🌐 Global Data Collection", "📊 Admin Data Center"] if is_admin else []))

with tabs[0]:
    st.header("🐶 AI Veterinarian: Precision Aging Diagnosis")
    
    with st.expander("💡 How to Request Analysis (Guide)", expanded=True):
        st.markdown("""
        1.  **Select Breed:** Use the **sidebar on the left** to pick your dog's breed.
        2.  **Upload Images:** Upload clear photos of your dog's **Side** and **Top** views.
        3.  **Run AI:** Click the **'🧠 Run AI Analysis'** button.
        4.  **Review:** After 10s, read the **Veterinarian's Clinical Opinion**.
        5.  **Save PDF:** Download your professional **PDF Health Report**.
        6.  **Premium:** For deeper insights, email us at the address below.
        """)
    
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1: side_f = st.file_uploader("📸 Upload Side View", type=['jpg', 'jpeg', 'png'], key="side_f")
    with c2: top_f = st.file_uploader("📸 Upload Top View", type=['jpg', 'jpeg', 'png'], key="top_f")
    
    if st.button("🧠 Run AI Analysis & Create Report", use_container_width=True, type="primary"):
        if side_f and top_f:
            t_stamp = get_kst_now().strftime("%Y%m%d_%H%M%S")
            s_p, t_p = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            with open(s_p, "wb") as f: f.write(side_f.getbuffer())
            with open(t_p, "wb") as f: f.write(top_f.getbuffer())
            with st.spinner("AI Veterinarian is analyzing images..."):
                res = analyze_pet_multi_view(s_p, t_p, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                
                st.success("✅ Analysis Complete!")
                st.info(f"**[AI Clinical Opinion]**\n\n{res['reason']}")
                
                pdf_p = create_pdf_report(selected_breed, res["bcs"], pace, res["reason"])
                
                conn = sqlite3.connect('pet_analysis.db')
                conn.cursor().execute("INSERT INTO analysis_logs (breed, bcs, pace, reason, date) VALUES (?,?,?,?,?)",
                                     (selected_breed, res["bcs"], pace, res["reason"], get_kst_now().strftime('%Y-%m-%d %H:%M')))
                conn.commit()
                conn.close()

                if pdf_p:
                    with open(pdf_p, "rb") as f:
                        st.download_button("📄 Download PDF Report", f, file_name=f"Report_{selected_breed}.pdf", use_container_width=True)
        else: st.warning("Please upload both Side and Top view images.")

# --- 5. Updated Data Collection Tab (Global Edition) ---
if is_admin:
    with tabs[1]:
        st.header("🌐 Global Data Collection (Status Tracked)")
        query = st.text_input("Search Query", f"{selected_breed} dog full body side view")
        sources = st.multiselect("Search Engines (Bing Recommended)", ["Google", "Bing", "Baidu"], default=["Bing"])
        max_imgs = st.slider("Max Images per Engine", 5, 50, 10)
        
        if st.button("🚀 Start Collection"):
            save_base = f"dataset/multi_view/{selected_breed}"
            if not os.path.exists(save_base): os.makedirs(save_base)
            
            status_log = st.empty() # Real-time status update
            progress_bar = st.progress(0)
            
            conn = sqlite3.connect('pet_analysis.db')
            for idx, src in enumerate(sources):
                status_log.write(f"📡 Attempting to connect to **{src}**...")
                src_dir = os.path.join(save_base, src.lower())
                if not os.path.exists(src_dir): os.makedirs(src_dir)
                
                try:
                    search_kw = query if src != "Baidu" else f"{selected_breed} 狗狗 侧面 真实照片"
                    
                    if src == "Google": crawler = GoogleImageCrawler(storage={'root_dir': src_dir})
                    elif src == "Bing": crawler = BingImageCrawler(storage={'root_dir': src_dir})
                    else: crawler = BaiduImageCrawler(storage={'root_dir': src_dir})
                    
                    status_log.write(f"📥 Downloading images from **{src}**... (Up to {max_imgs} files)")
                    crawler.crawl(keyword=search_kw, max_num=max_imgs)
                    
                    # Update DB
                    for f_name in os.listdir(src_dir):
                        f_path = os.path.join(src_dir, f_name)
                        if not conn.cursor().execute("SELECT id FROM collected_images WHERE img_path=?", (f_path,)).fetchone():
                            conn.cursor().execute("INSERT INTO collected_images (breed, img_path, source, collect_date) VALUES (?,?,?,?)", 
                                                 (selected_breed, f_path, src, get_kst_now().strftime('%Y-%m-%d %H:%M')))
                    status_log.write(f"✅ **{src}** collection finished successfully!")
                    
                except Exception as e:
                    st.error(f"❌ Error with {src}: {str(e)}")
                    status_log.write(f"⚠️ Skipping {src} and moving to next...")
                
                progress_bar.progress((idx + 1) / len(sources))
            
            conn.commit()
            conn.close()
            status_log.write("🏁 **All collection processes completed.**")
            st.success("Check the Data Center for results!")

    with tabs[2]:
            st.header("📊 Admin Data Center")
            l_tab, c_tab = st.tabs(["📋 Analysis Logs", "🖼️ Image Gallery & Cleanup"])
            
            # 1. Analysis Logs (Existing)
            with l_tab:
                conn = sqlite3.connect('pet_analysis.db')
                df_logs = pd.read_sql_query("SELECT * FROM analysis_logs ORDER BY id DESC", conn)
                st.dataframe(df_logs, use_container_width=True)
                conn.close()
    
            # 2. Image Gallery & Deletion (New Feature)
            with c_tab:
                st.subheader("🖼️ Collected Image Management")
                
                conn = sqlite3.connect('pet_analysis.db')
                # Fetch images filtered by selected breed to keep it organized
                df_imgs = pd.read_sql_query("SELECT * FROM collected_images WHERE breed = ? ORDER BY id DESC", conn, params=(selected_breed,))
                conn.close()
    
                if df_imgs.empty:
                    st.info(f"No collected images found for **{selected_breed}**.")
                else:
                    st.write(f"Total images for {selected_breed}: {len(df_imgs)}")
                    
                    # Use columns to create a gallery grid (4 images per row)
                    cols = st.columns(4)
                    for index, row in df_imgs.iterrows():
                        with cols[index % 4]:
                            img_id = row['id']
                            img_path = row['img_path']
                            
                            if os.path.exists(img_path):
                                # Display Image
                                st.image(img_path, use_container_width=True, caption=f"Source: {row['source']}")
                                
                                # Delete Button for each image
                                if st.button(f"🗑️ Delete #{img_id}", key=f"del_{img_id}"):
                                    try:
                                        # 1. Delete actual file
                                        if os.path.exists(img_path):
                                            os.remove(img_path)
                                        
                                        # 2. Delete from SQLite DB
                                        conn = sqlite3.connect('pet_analysis.db')
                                        cur = conn.cursor()
                                        cur.execute("DELETE FROM collected_images WHERE id = ?", (img_id,))
                                        conn.commit()
                                        conn.close()
                                        
                                        st.success(f"Deleted #{img_id}")
                                        st.rerun() # Refresh page to update gallery
                                    except Exception as e:
                                        st.error(f"Error: {e}")
                            else:
                                # If file is missing but DB entry exists
                                st.warning(f"File missing: {img_id}")
                                if st.button(f"Clean DB #{img_id}", key=f"clean_{img_id}"):
                                    conn = sqlite3.connect('pet_analysis.db')
                                    cur = conn.cursor()
                                    cur.execute("DELETE FROM collected_images WHERE id = ?", (img_id,))
                                    conn.commit()
                                    conn.close()
                                    st.rerun()
    
                    st.divider()
                    # Bulk Delete Option
                    if st.button("🚨 Clear All Collected Images for this Breed", type="secondary"):
                        confirm = st.checkbox("Confirm bulk delete?")
                        if confirm:
                            try:
                                for p in df_imgs['img_path']:
                                    if os.path.exists(p): os.remove(p)
                                
                                conn = sqlite3.connect('pet_analysis.db')
                                cur = conn.cursor()
                                cur.execute("DELETE FROM collected_images WHERE breed = ?", (selected_breed,))
                                conn.commit()
                                conn.close()
                                st.success("All images cleared.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

st.divider()
st.caption("Partnerships & Media Inquiry: bslee@yahoo.com")
