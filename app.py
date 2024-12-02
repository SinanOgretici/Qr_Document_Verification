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
result_file_path = os.path.join(unique_folder, "result_log.txt")

# Başlık
st.title("Belge Doğrulama Sistemi")

# PDF Yükleme
uploaded_file = st.file_uploader("PDF Belgesi Yükle", type="pdf")

if uploaded_file is not None:
    # PDF'ten metin çıkarma fonksiyonu
    def extract_pdf_info(pdf_file):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf_file.read())
            temp_file_path = temp_file.name

        images = convert_from_path(temp_file_path)
        text = ""
        for img in images:
            text += pytesseract.image_to_string(img, lang='tur')
        return text

    extracted_info = extract_pdf_info(uploaded_file)
    st.subheader("PDF'ten Çıkarılan Bilgiler")
    st.text(extracted_info)

    # PDF'den TC Kimlik Numarası ve Kontrol Kodu Çekme
    def extract_tc_kimlik_and_kontrol_kodu(text):
        tc_kimlik = re.search(r"\b\d{11}\b", text)
        tc_kimlik = tc_kimlik.group(0) if tc_kimlik else None

        kontrol_kodu = re.search(r"Sonuç Belgesi Kontrol Kodu:\s*([A-Za-z0-9]+)", text)
        kontrol_kodu = kontrol_kodu.group(1) if kontrol_kodu else None

        return tc_kimlik, kontrol_kodu

    tc_numarasi, kontrol_kodu = extract_tc_kimlik_and_kontrol_kodu(extracted_info)

    st.write(f"T.C. Kimlik Numarası: {tc_numarasi}")
    st.write(f"Sonuç Belgesi Kontrol Kodu: {kontrol_kodu}")

    if not tc_numarasi or not kontrol_kodu:
        st.error("T.C. Kimlik Numarası veya Sonuç Belgesi Kontrol Kodu bulunamadı.")

    # JSON dosyasına yeni bilgi eklemek
    def append_pdf_info(tc_numarasi, kontrol_kodu):
        try:
            # JSON dosyasını kontrol et ve yoksa oluştur
            if not os.path.exists(info_file_path):
                with open(info_file_path, "w", encoding="utf-8") as json_file:
                    json.dump([], json_file, ensure_ascii=False, indent=4)

            # JSON dosyasını açıp liste olarak al
            with open(info_file_path, "r", encoding="utf-8") as json_file:
                try:
                    data = json.load(json_file)
                    if not isinstance(data, list):  # Liste değilse temizle
                        data = []
                except json.JSONDecodeError:  # JSON bozuksa temizle
                    data = []

            # Yeni girişi ekle
            new_entry = {
                "timestamp": datetime.now().isoformat(),
                "tc_numarasi": tc_numarasi,
                "kontrol_kodu": kontrol_kodu
            }
            data.append(new_entry)  # Listeye yeni girişi ekle

            # JSON dosyasına yaz
            with open(info_file_path, "w", encoding="utf-8") as json_file:
                json.dump(data, json_file, ensure_ascii=False, indent=4)
        except Exception as e:
            st.error(f"JSON güncellenirken hata: {e}")

    # Sonuçları txt dosyasına eklemek
    def append_result_log(status, details):
        try:
            with open(result_file_path, "a", encoding="utf-8") as txt_file:
                txt_file.write(f"{datetime.now()} - Durum: {status}\nDetaylar: {details}\n\n")
        except Exception as e:
            st.error(f"TXT dosyasına yazılırken hata: {e}")

    # CAPTCHA kaydetme fonksiyonu (benzersiz ad)
    def save_captcha_image(driver, element):
        try:
            captcha_base64 = element.screenshot_as_base64  # CAPTCHA'yı base64 formatında al
            captcha_image = Image.open(io.BytesIO(base64.b64decode(captcha_base64)))  # Görüntüye çevir
            unique_filename = f"captcha_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            captcha_image.save(os.path.join(captcha_folder, unique_filename))
            return unique_filename
        except Exception as e:
            st.error(f"CAPTCHA kaydedilirken hata oluştu: {e}")
            return None

    # Google Vision API ile CAPTCHA çözme
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

    # Belge doğrulama fonksiyonu
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

            submit_button = WebDriverWait(driver, 60).until(
                EC.element_to_be_clickable((By.ID, "btng"))
            )
            time.sleep(10)  # Butona basmadan önce bekle
            submit_button.click()

            time.sleep(5)
            avatar_element = driver.find_elements(By.CLASS_NAME, "avatar")
            driver.quit()

            if avatar_element:
                return {"status": "Başarılı", "details": "Belge doğrulama başarılı"}
            else:
                return {"status": "Başarısız", "details": "Doğrulama sırasında hata oluştu"}
        except Exception as e:
            driver.quit()
            return {"status": "Başarısız", "details": f"Hata: {str(e)}"}

    # Belge doğrulama düğmesi
    if st.button("Belgeyi Doğrula"):
        if tc_numarasi and kontrol_kodu:
            result = verify_document(tc_numarasi, kontrol_kodu)
            append_pdf_info(tc_numarasi, kontrol_kodu)  # JSON'a ekleme
            append_result_log(result["status"], result["details"])  # Log dosyasına ekleme
            if result["status"] == "Başarılı":
                st.success(result["details"])
            else:
                st.error(result["details"])
        else:
            st.error("Geçerli bir TC Kimlik Numarası ve Kontrol Kodu girilmedi.")
