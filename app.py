import json
import streamlit as st
import pytesseract
from PIL import Image
import tempfile
import re
import time
from pdf2image import convert_from_path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import requests
import os
import cv2
import numpy as np

# JSON kayıt fonksiyonu
def save_to_json(log, filename="log.json"):
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(log, file, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"JSON kaydetme hatası: {e}")

# JSON kayıtları için başlangıç
log_data = {"işlemler": []}

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
    log_data["işlemler"].append({"aşama": "PDF'ten metin çıkarma", "çıkarılan_metin": extracted_info})
    save_to_json(log_data)

    st.subheader("PDF'ten Çıkarılan Bilgiler")
    st.text(extracted_info)

    def extract_tc_kimlik_and_kontrol_kodu(text):
        tc_kimlik = re.search(r"\b\d{11}\b", text)
        tc_kimlik = tc_kimlik.group(0) if tc_kimlik else None

        kontrol_kodu = re.search(r"Sonuç Belgesi Kontrol Kodu:\s*([A-Za-z0-9]+)", text)
        kontrol_kodu = kontrol_kodu.group(1) if kontrol_kodu else None
        
        return tc_kimlik, kontrol_kodu

    tc_numarasi, kontrol_kodu = extract_tc_kimlik_and_kontrol_kodu(extracted_info)
    log_data["işlemler"].append({
        "aşama": "T.C. Kimlik ve Kontrol Kodu çıkarma",
        "tc_numarasi": tc_numarasi,
        "kontrol_kodu": kontrol_kodu
    })
    save_to_json(log_data)

    st.write(f"T.C. Kimlik Numarası: {tc_numarasi}")
    st.write(f"Sonuç Belgesi Kontrol Kodu: {kontrol_kodu}")

    if not tc_numarasi or not kontrol_kodu:
        st.error("T.C. Kimlik Numarası veya Sonuç Belgesi Kontrol Kodu bulunamadı.")

    # CAPTCHA çözüm fonksiyonu
    def solve_captcha(driver):
        try:
            captcha_img_element = WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.XPATH, "//div[@class='captchaImage']/img"))
            )
            captcha_url = captcha_img_element.get_attribute("src")
            captcha_image_response = requests.get(captcha_url, stream=True)
            if captcha_image_response.status_code != 200:
                st.warning(f"CAPTCHA resmi indirilemedi. Durum Kodu: {captcha_image_response.status_code}")
                return None
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as captcha_file:
                captcha_file.write(captcha_image_response.content)
                captcha_path = captcha_file.name
            contours, img = preprocess_image(captcha_path)
            characters = []
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                if w > 5 and h > 15:
                    roi = img[y:y+h, x:x+w]
                    text = pytesseract.image_to_string(roi, config='--psm 8 --oem 3')
                    characters.append(re.sub(r'\W+', '', text))
            os.remove(captcha_path)
            captcha_text = ''.join(characters)
            log_data["işlemler"].append({"aşama": "CAPTCHA çözümü", "captcha_metni": captcha_text})
            save_to_json(log_data)
            return captcha_text.strip() if captcha_text else None
        except Exception as e:
            st.error(f"CAPTCHA çözümünde hata: {e}")
            return None

    # Belge doğrulama düğmesi
    if st.button("Belgeyi Doğrula"):
        if tc_numarasi and kontrol_kodu:
            try:
                chrome_options = Options()
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                driver_service = Service('C:/ChromeDriver/chromedriver.exe')
                driver = webdriver.Chrome(service=driver_service, options=chrome_options)
                driver.get("https://sonuc.osym.gov.tr/BelgeKontrol.aspx")
                tc_input = WebDriverWait(driver, 60).until(EC.visibility_of_element_located((By.ID, "adayNo")))
                tc_input.send_keys(tc_numarasi)
                belge_kodu_input = WebDriverWait(driver, 60).until(EC.visibility_of_element_located((By.ID, "belgeKodu")))
                belge_kodu_input.send_keys(kontrol_kodu)
                captcha_code = solve_captcha(driver)
                if captcha_code:
                    captcha_input = WebDriverWait(driver, 60).until(EC.visibility_of_element_located((By.ID, "captchaKod")))
                    captcha_input.send_keys(captcha_code)
                    submit_button = WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.ID, "btng")))
                    submit_button.click()
                    time.sleep(15)
                    result_element = WebDriverWait(driver, 60).until(
                        EC.visibility_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_lblSonuc"))
                    )
                    result_text = result_element.text
                    log_data["işlemler"].append({"aşama": "Belge doğrulama", "sonuç": result_text})
                    save_to_json(log_data)
                    st.write(result_text)
                else:
                    st.error("CAPTCHA çözümü başarısız oldu.")
            except Exception as e:
                st.error(f"Belge doğrulamada hata: {e}")
            finally:
                driver.quit()
        else:
            st.error("T.C. Kimlik Numarası veya Sonuç Belgesi Kontrol Kodu eksik.")
