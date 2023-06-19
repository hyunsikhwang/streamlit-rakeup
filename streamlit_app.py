# This codes are from https://ohenziblog.com/streamlit_cloud_for_selenium/
# Thanks to the author for great help.

import streamlit as st
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome import service as fs
from selenium.webdriver import ChromeOptions
from webdriver_manager.core.utils import ChromeType
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd


st.title("Selenium in streamlit cloud")

press_button = st.button("Scraping")

URL_value = 'https://www.kofiabond.or.kr/websquare/websquare.html?w2xPath=/xml/bondint/lastrop/BISLastAskPrcDay.xml&divisionId=MBIS01010010000000&divisionNm=%25EC%259D%25BC%25EC%259E%2590%25EB%25B3%2584&tabIdx=1&w2xHome=/xml/&w2xDocumentRoot='
URL = st.text_input("Input URL", value=URL_value)

tab1, tab2 = st.tabs(["Kofiabond", "HIRA"])

if press_button:
    # URL = "https://ohenziblog.com"

    options = ChromeOptions()

# 팝업창 차단
    options.add_experimental_option("excludeSwitches", ["disable-popup-blocking"])
    options.add_argument("--headless")
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--remote-debugging-port=9222')

    CHROMEDRIVER = ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
    service = fs.Service(CHROMEDRIVER)
    driver = webdriver.Chrome(
                              options=options,
                              service=service
                             )

    driver.get(URL)

    # img = driver.find_element(By.TAG_NAME, 'img')
    # src = img.get_attribute('src')

    # # 검색된 이미지를 현재 디렉토리에 저장
    # with open(f"tmp_img.png", "wb") as f:
    #     f.write(img.screenshot_as_png)

    # # 저장된 이미지를 streamlit 앱에 표시
    # st.image("tmp_img.png")

    # # 웹페이지 닫기
    # driver.close()

    with tab1:

        try:
            element = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, '//*[@id="row2"]')))
            soup = driver.find_element(By.XPATH, '//*[@id="grdMain_dataLayer"]').get_attribute('outerHTML')
            soup_bs = BeautifulSoup(soup, 'html5lib')
            df_bond = pd.read_html(str(soup))[0]
            df_bond.columns = df_bond.columns.get_level_values(2)
            st.write(df_bond)

        finally:
            driver.quit()
            # 스크래핑이 완료되었음을 streamlit 앱에 표시
            st.write("Scraping completed!!!")

    with tab2:
        st.write("HIRA")