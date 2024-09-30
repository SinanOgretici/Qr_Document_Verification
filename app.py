import streamlit as st
from PyPDF2 import PdfReader
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re  # Düzenli ifadelerle ayıklama yapmak için
import time

# Başlık
st.title(" Belge Doğrulama Sistemi")

# PDF Yükleme
uploaded_file = st.file_uploader("PDF Belgesi Yükle", type="pdf")

if uploaded_file is not None:
    # PDF'ten bilgi çıkarma fonksiyonu
    def extract_pdf_info(pdf_file):
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        print(text)
        return text

    # PDF'teki bilgileri göster
    extracted_info = extract_pdf_info(uploaded_file)
    st.subheader("PDF'ten Çıkarılan Bilgiler")
    st.text(extracted_info)

    # T.C. Kimlik Numarası ve Sonuç Belgesi Kontrol Kodunu ayıklama
    def extract_tc_kimlik_and_kontrol_kodu(text):
        # T.C. Kimlik Numarası 11 rakamdan oluşur
        tc_kimlik = re.search(r"\b\d{11}\b", text)
        tc_kimlik = tc_kimlik.group(0) if tc_kimlik else None

        # Sonuç Belgesi Kontrol Kodu ayıklama
        kontrol_kodu = re.search(r"Sonuç Belgesi Kontrol Kodu[:\s]*([A-Z0-9]+)", text)
        kontrol_kodu = kontrol_kodu.group(1) if kontrol_kodu else None

        return tc_kimlik, kontrol_kodu

    # PDF'ten bilgileri ayıklama
    tc_numarasi, kontrol_kodu = extract_tc_kimlik_and_kontrol_kodu(extracted_info)

    # T.C. Kimlik Numarası ve Sonuç Belgesi Kontrol Kodunu göster
    st.write(f"T.C. Kimlik Numarası: {tc_numarasi}")
    st.write(f"Sonuç Belgesi Kontrol Kodu: {kontrol_kodu}")

    # Eğer bilgiler bulunamazsa hata ver
    if not tc_numarasi or not kontrol_kodu:
        st.error("T.C. Kimlik Numarası veya Sonuç Belgesi Kontrol Kodu bulunamadı.")

    # Captcha'yı girmesi için kullanıcıdan veri alma
    captcha_code = st.text_input("Resimdeki Karakterleri Giriniz", max_chars=6)

    # Selenium ile doğrulama yapma
    def verify_document(tc_numarasi, kontrol_kodu, captcha_code):
        driver = webdriver.Chrome()  # ChromeDriver yolunu belirt
        driver.get("https://sonuc.osym.gov.tr/BelgeKontrol.aspx")  # ÖSYM'nin doğrulama sayfası

        try:
            # T.C. Kimlik Numarası alanı (id="adayNo") bul ve değer gir
            tc_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "adayNo"))
            )
            tc_input.clear()
            tc_input.send_keys(tc_numarasi)

            # Belge Doğrulama Kodu alanını (id="belgeKodu") bul ve değer gir
            belge_kodu_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "belgeKodu"))
            )
            belge_kodu_input.clear()
            belge_kodu_input.send_keys(kontrol_kodu)

            # Captcha'nın src linkini al ve ekrana yazdır
            captcha_image_element = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_CaptchaImage"))
            )
            captcha_src = captcha_image_element.get_attribute("src")
            st.write(f"Captcha Kaynak Linki: {captcha_src}")  # Captcha linkini göster

            # Captcha resmini Streamlit'te görüntüle
            st.image(captcha_src)

            # Captcha (Resimdeki Karakterler) alanını bul ve kullanıcıdan aldığımız değeri gir
            captcha_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "captchaKod"))
            )
            captcha_input.clear()
            captcha_input.send_keys(captcha_code)

            # "Gönder" butonunu bul ve tıkla
            submit_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "btng"))
            )
            submit_button.click()

            # Doğrulama sonucunu al
            time.sleep(3)  # Sayfanın yüklenmesi için bekle

            # Sayfada sonucu çekelim
            result_element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "ctl00_ContentPlaceHolder1_lblSonuc"))
            )
            result_text = result_element.text

        except Exception as e:
            result_text = f"Hata oluştu: {str(e)}"
        finally:
            driver.quit()  # Tarayıcıyı kapat
        return result_text

    # Doğrulama butonu
    if st.button("Belgeyi Doğrula"):
        if tc_numarasi and kontrol_kodu and captcha_code:  # Bilgiler ve Captcha girilmiş mi?
            result = verify_document(tc_numarasi, kontrol_kodu, captcha_code)
            st.success(f"Doğrulama Sonucu: {result}")
        else:
            st.error("Lütfen eksik bilgileri giriniz.")
