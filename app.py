import streamlit as st
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
import io
import re
import time
from pdf2image import convert_from_path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import tempfile
import requests
import os
import cv2
import numpy as np

# Başlık
st.title("Belge Doğrulama Sistemi")

# PDF Yükleme
uploaded_file = st.file_uploader("PDF Belgesi Yükle", type="pdf")

if uploaded_file is not None:
    # PDF'ten metin çıkarma fonksiyonu (Tesseract OCR ile)
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

    # Görüntü işleme fonksiyonu
    def preprocess_image(img_path):
        # Görüntüyü oku
        img = cv2.imread(img_path, 0)
        
        # Gürültü azaltma ve eşikleme
        blurred = cv2.GaussianBlur(img, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 11, 2)

        # Morfolojik işlemler (karakterleri daha iyi ayırmak için)
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        eroded = cv2.erode(dilated, kernel, iterations=1)

        # Keskinleştirme (Daha net konturlar elde etmek için)
        sharpen_kernel = np.array([[-1, -1, -1], [-1, 9,-1], [-1, -1, -1]])
        sharpened = cv2.filter2D(eroded, -1, sharpen_kernel)

        # Contours bulma
        contours, hierarchy = cv2.findContours(sharpened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        return contours, img

    # Karakter tanıma fonksiyonu
    def recognize_characters(contours, img):
        characters = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # Gürültüyü azaltmak için minimum boyut kontrolü
            if w > 5 and h > 15:
                # Karakteri kırp
                roi = img[y:y+h, x:x+w]
                
                # Tesseract ile metin çıkarma (daha iyi çözüm için PSM modunu değiştiriyoruz)
                text = pytesseract.image_to_string(roi, config='--psm 8 --oem 3')
                
                # Karakterde boşlukları temizle
                clean_text = re.sub(r'\W+', '', text)
                
                characters.append(clean_text)
        
        print(f"Tanınan Karakterler: {characters}")
        return characters

    # CAPTCHA çözüm fonksiyonu
    def solve_captcha(driver):
        captcha_path = None  # captcha_path'in boş olduğunu belirtiyoruz
        try:
            time.sleep(10)  # CAPTCHA'nın yüklenmesini bekle

            # CAPTCHA resminin bulunduğu elementi yakala
            captcha_img_element = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.XPATH, "//div[@class='captchaImage']/img"))
            )
            
            # CAPTCHA resminin URL'sini al
            captcha_url = captcha_img_element.get_attribute("src")
            print(f"CAPTCHA URL: {captcha_url}")  # Hata ayıklama için

            # CAPTCHA'yı indir
            captcha_image_response = requests.get(captcha_url, stream=True)

            if captcha_image_response.status_code != 200:
                st.warning(f"CAPTCHA resmi indirilemedi. Durum Kodu: {captcha_image_response.status_code}")
                return None

            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as captcha_file:
                captcha_file.write(captcha_image_response.content)
                captcha_path = captcha_file.name  # Dosya yolunu kaydediyoruz

            # CAPTCHA'yı işleme ve çözme
            contours, img = preprocess_image(captcha_path)
            characters = recognize_characters(contours, img)

            captcha_text = ''.join(characters)
            print(f"CAPTCHA metni: {captcha_text}")  # Hata ayıklama için

            if captcha_text:
                return captcha_text.strip()
            else:
                st.error("OCR sonucu boş döndü. CAPTCHA'yı çözemedik.")
                return None
        except Exception as e:
            st.error(f"CAPTCHA çözümünde hata: {e}")
            return None
        finally:
            if captcha_path and os.path.exists(captcha_path):
                os.remove(captcha_path)

    # Belge doğrulama fonksiyonu
    def verify_document(tc_numarasi, kontrol_kodu, captcha_code):
        # Headless modda Chrome tarayıcısını başlat
        chrome_options = Options()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        driver_service = Service('C:/ChromeDriver/chromedriver.exe')  # ChromeDriver yolunu ayarlayın
        driver = webdriver.Chrome(service=driver_service, options=chrome_options)
        driver.get("https://sonuc.osym.gov.tr/BelgeKontrol.aspx")

        try:
            print("T.C. Kimlik Numarası alanını bulmaya çalışıyor...")  # Hata ayıklama için
            tc_input = WebDriverWait(driver, 30).until(
                EC.visibility_of_element_located((By.ID, "adayNo"))
            )
            tc_input.clear()
            tc_input.send_keys(tc_numarasi)

            print("Belge Doğrulama Kodu alanını bulmaya çalışıyor...")  # Hata ayıklama için
            belge_kodu_input = WebDriverWait(driver, 30).until(
                EC.visibility_of_element_located((By.ID, "belgeKodu"))
            )
            belge_kodu_input.clear()
            belge_kodu_input.send_keys(kontrol_kodu)

            # CAPTCHA'yı çözmek için resmi al
            captcha_code = solve_captcha(driver)

            if captcha_code is None:
                st.error("CAPTCHA çözümü başarısız oldu.")
                return None

            # CAPTCHA'yı form alanına yaz
            captcha_input = WebDriverWait(driver, 30).until(
                EC.visibility_of_element_located((By.ID, "captchaKod"))
            )
            captcha_input.clear()
            captcha_input.send_keys(captcha_code)

            print("Gönder butonuna tıklıyor...")  # Hata ayıklama için
            submit_button = WebDriverWait(driver, 30).until(
                EC.element_to_be_clickable((By.ID, "btng"))
            )
            submit_button.click()

            print("Doğrulama sonuç ekranını alıyor...")  # Hata ayıklama için
            time.sleep(5)  # Sayfanın yüklenmesi için bekle
            result_element = WebDriverWait(driver, 30).until(
                EC.visibility_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_lblSonuc"))
            )
            result_text = result_element.text

        except Exception as e:
            print(f"Hata oluştu: {str(e)}")  # Hata ayıklama için
            result_text = f"Hata oluştu: {str(e)}"
        finally:
            driver.quit()
        return result_text

    # Belge doğrulama düğmesi
    if st.button("Belgeyi Doğrula"):
        if tc_numarasi and kontrol_kodu:
            result = verify_document(tc_numarasi, kontrol_kodu, None)
            st.write(result)
        else:
            st.error("T.C. Kimlik Numarası veya Sonuç Belgesi Kontrol Kodu eksik.")
