# This codes are from https://ohenziblog.com/streamlit_cloud_for_selenium/
# Thanks to the author for great help.

import streamlit as st
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome import service as fs
from selenium.webdriver import ChromeOptions
from webdriver_manager.core.utils import ChromeType
from selenium.webdriver.common.by import By

st.title("Selenium in streamlit cloud")

press_button = st.button("Scraping")

if press_button:
    URL = "https://ohenziblog.com"

    options = ChromeOptions()

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

    img = driver.find_element(By.TAG_NAME, 'img')
    src = img.get_attribute('src')

    # 검색된 이미지를 현재 디렉토리에 저장
    with open(f"tmp_img.png", "wb") as f:
        f.write(img.screenshot_as_png)

    # 저장된 이미지를 streamlit 앱에 표시
    st.image("tmp_img.png")

    # 웹페이지 닫기
    driver.close()

    # 스크래핑이 완료되었음을 streamlit 앱에 표시
    st.write("Scraping completed!!!")