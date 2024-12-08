import streamlit as st
import pytesseract
from PIL import Image
import re
from pdf2image import convert_from_path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import tempfile
import os
import base64
import io
import time
from google.cloud import vision
from datetime import datetime
import json
import extra_streamlit_components as stx
import pandas as pd

# Sayfa yapılandırması
st.set_page_config(
    page_title="QR Document Verification",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS stilleri
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stButton>button {
        width: 100%;
        background-color: #0066cc;
        color: white;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        margin: 1rem 0;
    }
    .stButton>button:hover {
        background-color: #0052a3;
    }
    .success-message {
        padding: 1rem;
        background-color: #d4edda;
        color: #155724;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .error-message {
        padding: 1rem;
        background-color: #f8d7da;
        color: #721c24;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .info-box {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 1rem 0;
    }
    .header-container {
        display: flex;
        align-items: center;
        justify-content: center;
        background-color: #F2BC80;
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .header-text {
        color: #302519;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# Google Vision API istemcisini başlat
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"
vision_client = vision.ImageAnnotatorClient()

# Belirtilen dosya yolu
base_folder = r"C:\Users\sinan\OneDrive\Belgeler\Qr_Document_Verification"
if not os.path.exists(base_folder):
    os.makedirs(base_folder)

# Klasör ismini sadece tarihe göre oluşturma
current_date = datetime.now().strftime('%Y-%m-%d')
unique_folder = os.path.join(base_folder, current_date)

# Yeni tarih ise klasör oluştur
if not os.path.exists(unique_folder):
    os.makedirs(unique_folder)

captcha_folder = os.path.join(unique_folder, "captcha")
if not os.path.exists(captcha_folder):
    os.makedirs(captcha_folder)

captcha_path = os.path.join(captcha_folder, "captcha.png")
info_file_path = os.path.join(unique_folder, "pdf_info.json")
result_file_path = os.path.join(unique_folder, "result_log.json")

# Header
st.markdown("""
    <div class="header-container">
        <div>
            <h1 class="header-text">KPSS Belge Doğrulama Sistemi</h1>
            <p style='text-align: center;'>ÖSYM Sonuç Belgesi Doğrulama ve Kontrol Sistemi</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### 📌 Sistem Hakkında")
    st.info("""
    Bu sistem, KPSS sonuç belgelerinizin doğruluğunu kontrol etmenizi sağlar.
    
    **Özellikler:**
    - PDF belge yükleme
    - Otomatik veri çıkarma
    - ÖSYM sistemi ile doğrulama
    - Detaylı karşılaştırma raporu
    """)
    
    st.markdown("### 📊 İstatistikler")
    if os.path.exists(result_file_path):
        try:
            with open(result_file_path, 'r', encoding='utf-8') as f:
                results = json.load(f)
                total_verifications = len(results)
                successful_verifications = sum(1 for r in results 
                    if 'status' in r and r['status'] == 'Başarılı')
        except (json.JSONDecodeError, KeyError):
            total_verifications = 0
            successful_verifications = 0
    else:
        total_verifications = 0
        successful_verifications = 0
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Toplam Sorgu", total_verifications)
    with col2:
        st.metric("Başarılı Sorgu", successful_verifications)
        # Yardımcı fonksiyonlar
def extract_pdf_info(pdf_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(pdf_file.read())
        temp_file_path = temp_file.name

    images = convert_from_path(temp_file_path)
    text = ""
    for img in images:
        text += pytesseract.image_to_string(img, lang='tur')
    return text

def extract_tc_kimlik_and_kontrol_kodu(text):
    tc_kimlik = re.search(r"\b\d{11}\b", text)
    tc_kimlik = tc_kimlik.group(0) if tc_kimlik else None

    kontrol_kodu = re.search(r"Sonuç Belgesi Kontrol Kodu:\s*([A-Za-z0-9]+)", text)
    kontrol_kodu = kontrol_kodu.group(1) if kontrol_kodu else None

    return tc_kimlik, kontrol_kodu

def extract_test_results(text):
    gy_patterns = [
        r"Genel Yetenek.*?Doğru\s*(\d+).*?Yanlış\s*(\d+)",
        r"Genel Yetenek.*?(\d+)\s*3.*?(\d+)\s*2",
        r"Genel Yetenek[\s\S]*?(\d+)[\s\S]*?(\d+)"
    ]
    
    gk_patterns = [
        r"Genel Kültür.*?Doğru\s*(\d+).*?Yanlış\s*(\d+)",
        r"Genel Kültür.*?(\d+)\s*2.*?(\d+)\s*2",
        r"Genel Kültür[\s\S]*?(\d+)[\s\S]*?(\d+)"
    ]
    
    gy_dogru = gy_yanlis = gk_dogru = gk_yanlis = None
    
    for pattern in gy_patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            gy_dogru, gy_yanlis = match.groups()
            break
    
    for pattern in gk_patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            gk_dogru, gk_yanlis = match.groups()
            break
    
    return {
        'genel_yetenek': {
            'dogru': gy_dogru,
            'yanlis': gy_yanlis
        },
        'genel_kultur': {
            'dogru': gk_dogru,
            'yanlis': gk_yanlis
        }
    }

def extract_kpss_info(text):
    patterns = {
        'puan_turu': r"KPSSP\d+",
        'kpss_puani': r"KPSS Puanı.*?(\d+[.,]\d+)",
        'basari_sirasi': r"Başarı Sırası.*?(\d+[\d.,]*)",
        'aday_sayisi': r"Aday Sayısı.*?(\d+[\d.,]*)"
    }
    
    results = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.DOTALL)
        results[key] = match.group(0) if key == 'puan_turu' and match else (
            match.group(1) if match else None)
    
    return results

def append_pdf_info(tc_numarasi, kontrol_kodu):
    try:
        if not os.path.exists(info_file_path):
            with open(info_file_path, "w", encoding="utf-8") as json_file:
                json.dump([], json_file, ensure_ascii=False, indent=4)

        with open(info_file_path, "r", encoding="utf-8") as json_file:
            try:
                data = json.load(json_file)
                if not isinstance(data, list):
                    data = []
            except json.JSONDecodeError:
                data = []

        new_entry = {
            "timestamp": datetime.now().isoformat(),
            "tc_numarasi": tc_numarasi,
            "kontrol_kodu": kontrol_kodu
        }
        data.append(new_entry)

        with open(info_file_path, "w", encoding="utf-8") as json_file:
            json.dump(data, json_file, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"JSON güncellenirken hata: {e}")

def append_result_log(status, details, pdf_text, screen_text):
    try:
        if os.path.exists(result_file_path):
            with open(result_file_path, "r", encoding="utf-8") as json_file:
                try:
                    results = json.load(json_file)
                except json.JSONDecodeError:
                    results = []
        else:
            results = []

        pdf_tc, pdf_kontrol = extract_tc_kimlik_and_kontrol_kodu(pdf_text)
        pdf_results = extract_test_results(pdf_text)
        pdf_kpss = extract_kpss_info(pdf_text)

        screen_tc, screen_kontrol = extract_tc_kimlik_and_kontrol_kodu(screen_text)
        screen_results = extract_test_results(screen_text)
        screen_kpss = extract_kpss_info(screen_text)

        new_result = {
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "details": details,
            "pdf_data": {
                "tc_kimlik": pdf_tc,
                "kontrol_kodu": pdf_kontrol,
                "genel_yetenek": pdf_results["genel_yetenek"],
                "genel_kultur": pdf_results["genel_kultur"],
                "kpss_bilgileri": pdf_kpss
            },
            "screen_data": {
                "tc_kimlik": screen_tc,
                "kontrol_kodu": screen_kontrol,
                "genel_yetenek": screen_results["genel_yetenek"],
                "genel_kultur": screen_results["genel_kultur"],
                "kpss_bilgileri": screen_kpss
            }
        }

        results.append(new_result)
        with open(result_file_path, "w", encoding="utf-8") as json_file:
            json.dump(results, json_file, ensure_ascii=False, indent=4)

    except Exception as e:
        st.error(f"Sonuç kaydı oluşturulurken hata: {e}")

def save_captcha_image(driver, element):
    try:
        captcha_base64 = element.screenshot_as_base64
        captcha_image = Image.open(io.BytesIO(base64.b64decode(captcha_base64)))
        unique_filename = f"captcha_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
        captcha_path = os.path.join(captcha_folder, unique_filename)
        captcha_image.save(captcha_path)
        return unique_filename
    except Exception as e:
        st.error(f"CAPTCHA kaydedilirken hata oluştu: {e}")
        return None

def solve_captcha_with_vision(captcha_path):
    try:
        with io.open(captcha_path, "rb") as image_file:
            content = image_file.read()

        image = vision.Image(content=content)
        response = vision_client.text_detection(image=image)
        texts = response.text_annotations

        if texts:
            captcha_text = texts[0].description.strip().replace(" ", "")
            return captcha_text if len(captcha_text) == 5 else None
        else:
            st.error("Google Vision OCR sonucu boş döndü.")
            return None
    except Exception as e:
        st.error(f"Google Vision CAPTCHA çözümünde hata oluştu: {e}")
        return None

def verify_document(tc_numarasi, kontrol_kodu):
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver_service = Service("C:/ChromeDriver/chromedriver.exe")
    driver = webdriver.Chrome(service=driver_service, options=chrome_options)
    driver.get("https://sonuc.osym.gov.tr/BelgeKontrol.aspx")

    try:
        tc_input = WebDriverWait(driver, 60).until(
            EC.visibility_of_element_located((By.ID, "adayNo"))
        )
        tc_input.clear()
        tc_input.send_keys(tc_numarasi)

        belge_kodu_input = WebDriverWait(driver, 60).until(
            EC.visibility_of_element_located((By.ID, "belgeKodu"))
        )
        belge_kodu_input.clear()
        belge_kodu_input.send_keys(kontrol_kodu)

        captcha_img_element = WebDriverWait(driver, 60).until(
            EC.presence_of_element_located((By.XPATH, "//div[@class='captchaImage']/img"))
        )
        captcha_filename = save_captcha_image(driver, captcha_img_element)
        captcha_code = solve_captcha_with_vision(os.path.join(captcha_folder, captcha_filename))

        if not captcha_code:
            st.error("CAPTCHA çözümü başarısız oldu.")
            driver.quit()
            return {"status": "Başarısız", "details": "CAPTCHA çözülemedi"}

        captcha_input = WebDriverWait(driver, 60).until(
            EC.visibility_of_element_located((By.ID, "captchaKod"))
        )
        captcha_input.clear()
        captcha_input.send_keys(captcha_code)
        
        time.sleep(10)

        submit_button = WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable((By.ID, "btng"))
        )
        submit_button.click()

        time.sleep(10)

        screenshot_path = os.path.join(unique_folder, "verification_screenshot.png")
        driver.save_screenshot(screenshot_path)
        screen_text = pytesseract.image_to_string(Image.open(screenshot_path), lang="tur")

        if screen_text:
            comparison_result = compare_texts(extracted_info, screen_text)
            
            details = []
            if not comparison_result['details']['tc_match']:
                details.append("TC Kimlik No uyuşmuyor")
            if not comparison_result['details']['kontrol_match']:
                details.append("Kontrol Kodu uyuşmuyor")
            
            detail_text = ", ".join(details) if details else "Tüm bilgiler uyuşuyor"
            
            report = {
                "status": "Başarılı" if comparison_result['match'] else "Başarısız",
                "details": "Belge Gerçek" if comparison_result['match'] else f"Belge Sahte ({detail_text})",
                "pdf_text": extracted_info,
                "screen_text": screen_text,
                "screenshot_path": screenshot_path
            }
        else:
            report = {"status": "Başarısız", "details": "Ekran görüntüsü metni alınamadı"}

        driver.quit()
        return report

    except Exception as e:
        driver.quit()
        return {"status": "Başarısız", "details": f"Hata: {str(e)}"}

def compare_texts(pdf_text, screen_text):
    pdf_tc, pdf_kontrol = extract_tc_kimlik_and_kontrol_kodu(pdf_text)
    pdf_results = extract_test_results(pdf_text)
    pdf_kpss = extract_kpss_info(pdf_text)
    
    screen_tc, screen_kontrol = extract_tc_kimlik_and_kontrol_kodu(screen_text)
    screen_results = extract_test_results(screen_text)
    screen_kpss = extract_kpss_info(screen_text)
    
    tc_match = pdf_tc == screen_tc
    kontrol_match = pdf_kontrol == screen_kontrol
    
    gy_dogru_match = pdf_results['genel_yetenek']['dogru'] == screen_results['genel_yetenek']['dogru']
    gy_yanlis_match = pdf_results['genel_yetenek']['yanlis'] == screen_results['genel_yetenek']['yanlis']
    gk_dogru_match = pdf_results['genel_kultur']['dogru'] == screen_results['genel_kultur']['dogru']
    gk_yanlis_match = pdf_results['genel_kultur']['yanlis'] == screen_results['genel_kultur']['yanlis']
    
    kpss_puan_match = pdf_kpss['kpss_puani'] == screen_kpss['kpss_puani']
    basari_sira_match = pdf_kpss['basari_sirasi'] == screen_kpss['basari_sirasi']
    
    all_match = tc_match and kontrol_match
    
    return {
        'match': all_match,
        'details': {
            'tc_match': tc_match,
            'kontrol_match': kontrol_match,
            'test_results': {
                'genel_yetenek': {
                    'dogru_match': gy_dogru_match,
                    'yanlis_match': gy_yanlis_match
                },
                'genel_kultur': {
                    'dogru_match': gk_dogru_match,
                    'yanlis_match': gk_yanlis_match
                }
            },
            'kpss_info': {
                'puan_match': kpss_puan_match,
                'sira_match': basari_sira_match
            }
        }
    }

# Ana uygulama mantığı
tabs = stx.tab_bar(data=[
    stx.TabBarItemData(id=1, title="Belge Yükleme", description="PDF belgesi yükleyin"),
    stx.TabBarItemData(id=2, title="Sonuçlar", description="Doğrulama sonuçları"),
    stx.TabBarItemData(id=3, title="Geçmiş", description="Geçmiş sorgular")
])

if tabs == "1":
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("### 📤 PDF Belge Yükleme")
        uploaded_file = st.file_uploader("PDF Belgesi Yükle", type="pdf", 
            help="Lütfen ÖSYM'den indirdiğiniz PDF formatındaki sonuç belgenizi yükleyin.")
        
        if uploaded_file is not None:
            with st.expander("📄 Çıkarılan Bilgiler", expanded=True):
                extracted_info = extract_pdf_info(uploaded_file)
                tc_numarasi, kontrol_kodu = extract_tc_kimlik_and_kontrol_kodu(extracted_info)
                
                info_col1, info_col2 = st.columns(2)
                with info_col1:
                    st.markdown("**T.C. Kimlik Numarası:**")
                    st.code(tc_numarasi if tc_numarasi else "Bulunamadı")
                with info_col2:
                    st.markdown("**Kontrol Kodu:**")
                    st.code(kontrol_kodu if kontrol_kodu else "Bulunamadı")
                
                if st.button("🔍 Belgeyi Doğrula", use_container_width=True):
                    with st.spinner('Belge doğrulanıyor...'):
                        result = verify_document(tc_numarasi, kontrol_kodu)
                        append_pdf_info(tc_numarasi, kontrol_kodu)
                        append_result_log(
                            result["status"],
                            result["details"],
                            result["pdf_text"],
                            result.get("screen_text", "")
                        )
                        
                        if result["status"] == "Başarılı":
                            st.success(result["details"])
                        else:
                            st.error(result["details"])
    
    with col2:
        st.markdown("### ℹ️ Bilgi")
        st.info("""
        **Belge Yükleme Adımları:**
        1. PDF formatındaki ÖSYM sonuç belgenizi yükleyin
        2. Sistem otomatik olarak gerekli bilgileri çıkaracaktır
        3. 'Belgeyi Doğrula' butonuna tıklayın
        4. Sonuçları kontrol edin
        """)

elif tabs == "2":
    st.markdown("### 📊 Son Doğrulama Sonuçları")
    if os.path.exists(result_file_path):
        try:
            with open(result_file_path, 'r', encoding='utf-8') as f:
                results = json.load(f)
                if results:
                    for result in results[-5:]:  # Son 5 sonucu göster
                        with st.expander(f"Doğrulama: {result.get('timestamp', 'Tarih Yok')}", expanded=False):
                            status = result.get('status', 'Belirsiz')
                            status_color = "green" if status == "Başarılı" else "red"
                            st.markdown(f"**Durum:** <span style='color:{status_color}'>{status}</span>", 
                                      unsafe_allow_html=True)
                            st.markdown(f"**Detaylar:** {result.get('details', 'Detay yok')}")
                            
                            if 'pdf_data' in result and 'screen_data' in result:
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.markdown("**PDF Verileri**")
                                    st.json(result['pdf_data'])
                                with col2:
                                    st.markdown("**Ekran Verileri**")
                                    st.json(result['screen_data'])
                else:
                    st.info("Henüz doğrulama sonucu bulunmuyor.")
        except (json.JSONDecodeError, KeyError) as e:
            st.error(f"Sonuç dosyası okunurken hata oluştu: {str(e)}")
    else:
        st.info("Henüz doğrulama sonucu bulunmuyor.")

elif tabs == "3":
    st.markdown("### 📜 Geçmiş Sorgular")
    if os.path.exists(info_file_path):
        with open(info_file_path, 'r', encoding='utf-8') as f:
            history = json.load(f)
            if history:
                df = pd.DataFrame(history)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values('timestamp', ascending=False)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("Geçmiş sorgu bulunmuyor.")
    else:
        st.info("Geçmiş sorgu bulunmuyor.")

# Footer
st.markdown("""
    <div style='text-align: center; margin-top: 2rem; padding: 1rem; background-color: #f1c232; border-radius: 5px;'>
        <p>© 2024 KPSS Belge Doğrulama Sistemi</p>
    </div>
    """, unsafe_allow_html=True)