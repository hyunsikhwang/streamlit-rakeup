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
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import requests
import numpy as np


st.title("Selenium in streamlit cloud")

press_button = st.button("Scraping")

URL = 'https://www.kofiabond.or.kr/websquare/websquare.html?w2xPath=/xml/bondint/lastrop/BISLastAskPrcDay.xml&divisionId=MBIS01010010000000&divisionNm=%25EC%259D%25BC%25EC%259E%2590%25EB%25B3%2584&tabIdx=1&w2xHome=/xml/&w2xDocumentRoot='

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

#datatype: 0-환자수, 1-총사용량, 2-진료금액
#tabletype: 0-성/5세연령단위별, 1-입원외래별, 2-요양기관종별 / 10-KCD코드 성/5세연령단위별(3~4단 자동 구분)
def scrapToDf(hiraStr, hiraCode, datatype, tabletype):
    patternYr = '[0-9]+년'

    if tabletype == 0:
        patternNum = '[0-9]+_[0-9]+세|[0-9]+세미만|[0-9]+세이상'
    elif tabletype == 1:
        patternNum = '입원$|외래$'
    elif tabletype == 2:
        patternNum = '[가-힣]{2,}'
    elif tabletype == 10:
        patternNum = '[0-9]+_[0-9]+세|[0-9]+세미만|[0-9]+세이상'
    else:
        patternNum = '[0-9]+_[0-9]+세|[0-9]+세미만|[0-9]+세이상'

    count = 0
    flag = False

    # 데이터 연도 체크
    Yr = []
    for itm in hiraStr:
        result = re.match(patternYr, itm)
        if result:
            Yr.append(itm)
            count = count + 1

    if tabletype == 0:
        Yr.insert(0, 'Age')
        Yr.insert(0, 'Gender')
        Yr.insert(0, 'Code')
    elif tabletype == 1:
        Yr.insert(0, 'In/Outpatient')
        Yr.insert(0, 'Gender')
        Yr.insert(0, 'Code')
    elif tabletype == 2:
        Yr.insert(0, 'Hospital Type')
        Yr.insert(0, 'Code')
    elif tabletype == 10:
        Yr.insert(0, 'Age')
        Yr.insert(0, 'Gender')
        Yr.insert(0, 'Code')
    else:
        Yr.insert(0, 'Age')
        Yr.insert(0, 'Gender')
        Yr.insert(0, 'Code')

    # 여기에서 추가할 항목 갯수(환자수, 사용량, 금액)만큼 컬럼을 늘려줘야 함
    df = pd.DataFrame(columns=Yr)

    flag = False
    df_row = []
    df_data = []

    for itm in hiraStr:

        if tabletype != 2 and (itm == '남' or itm == '여'):
            gender = itm
            df_row = [hiraCode, gender]
        elif tabletype == 2:
            if '병원' in itm or '의원' in itm:
                df_row = [hiraCode]

        # result: patternNum 과 정규표현식이 일치하는지 확인, "컬럼항목" 인지 "데이터값" 인지 구분하기 위함
        # flag: 라인이 끝났는지 확인하기 위함, False 가 새로운 Row 의 시작을 의미
        if tabletype != 2:
            result = re.match(patternNum, itm)
        elif '병원' in itm or '의원' in itm:
            result = True
            hospType = itm
        else:
            result = False

        # result = True 이면, df_row 에 "컬럼항목" 추가 & flag = True 세팅
        # result = False / flag = True 이면, df_data 에 "데이터값" 추가
        if result:
            #print(itm)
            flag = True
            df_row.append(itm)
        elif flag == True:
            df_data.append(itm.replace('-', '0'))

        # 행 넘어갈때 초기화
        # count: 데이터 연도 갯수
        # numCol: 연도별 데이터 컬럼 갯수
        if tabletype < 10:
            numCol = 3
        else:
            numCol = 5
        
        # print(itm, result, flag, df_row, df_data)

        if len(df_data) / numCol == count :
            flag = False
            df_row.extend(df_data[datatype::numCol])
            df.loc[len(df)] = df_row
            if tabletype != 2:
                df_row = [hiraCode, gender]
            else:
                df_row = [hiraCode]

            df_data = []

    return df

def take_HIRA_data(code, datatype, tabletype):

    success = False
    result_df = pd.DataFrame()

    while not success:
        try:
            # HIRA 의료통계정보 사이트 내부의 iframe 부분에 대한 URL 호출
            driver = webdriver.Chrome(options=options,
                                      service=service
                                      )

            if tabletype == 0:
                # 수가코드 성별/연령5세구간별
                url = 'http://olapopendata.hira.or.kr/analysis/desktop/poc2.jsp#report_id=cc2e8d5a-fd4146ce&PARAM1=1' + code
            elif tabletype == 1:            
                # 수가코드 입원외래별
                url = 'http://olapopendata.hira.or.kr/analysis/desktop/poc2.jsp#report_id=a51b2db5-2aea4cfd&PARAM1=1' + code
            elif tabletype == 2:
                # 수가코드 요양기관종별
                url = 'http://olapopendata.hira.or.kr/analysis/desktop/poc2.jsp#report_id=60039d2b-9d6746b0&PARAM1=1' + code
            elif tabletype == 10:
                # KCD 코드 성별/연령5세구간별 (3단 / 4단)
                if len(code) == 3:
                    url = 'http://olapopendata.hira.or.kr/analysis/desktop/poc2.jsp#report_id=a576a04f-79a44e41&PARAM1=A' + code
                else:
                    url = 'http://olapopendata.hira.or.kr/analysis/desktop/poc2.jsp#report_id=8edbc258-9b01430b&PARAM1=A' + code
            else:
                # 수가코드 성별/연령5세구간별
                url = 'http://olapopendata.hira.or.kr/analysis/desktop/poc2.jsp#report_id=cc2e8d5a-fd4146ce&PARAM1=1' + code

            driver.get(url)

            element = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, '//*[@id="ext-gen1645"]/table/tbody/tr/td/div[6]/select')))

            # 시작년도 2010년(기본값 2015년)으로 변경
            select = Select(driver.find_element(By.XPATH, '//*[@id="ext-gen1645"]/table/tbody/tr/td/div[6]/select'))
            select.select_by_value('2010')

            time.sleep(10)

            select = Select(driver.find_element(By.XPATH, '//*[@id="ext-gen1645"]/table/tbody/tr/td/div[8]/select'))
            select.select_by_value('2022')

            driver.set_window_size(15360, 8640)

            element = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CLASS_NAME, 'dt-btn-search')))

            # 조회 버튼 클릭
            btn_search = driver.find_element(By.CLASS_NAME, 'dt-btn-search')
            btn_search.click()
            
            element = WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.CLASS_NAME, 'm-cell-text')))
            data_grid = driver.find_elements(By.CLASS_NAME, 'm-cell-text')

            result = [e.text for e in data_grid if e.text != '']

            if result == []:
                print(f'There is no data for {code}.')
            else:
                result_df = scrapToDf(result, code, datatype, tabletype)

            success = True

            driver.close()
            driver.quit()

        except Exception as e:
            driver.close()
            driver.quit()
            pass

    return result_df

def call_HIRA():
    with st.spinner('Wait for it...'):
        df = take_HIRA_data(code=code, datatype=datatype, tabletype=tabletype)

    st.write(df)

def call_HIRA_new(datatype, code):

    if datatype == 1:
        # 질병 소분류(3단 상병) 통계
        url = f"https://opendata.hira.or.kr/op/opc/olap3thDsInfoTab2.do?olapCd=A{code}&tabGubun=Tab2&gubun=R&sRvYr=2010&eRvYr=2022&sDiagYm=&eDiagYm=&sYm=&eYm="
    elif datatype == 2:
        # 질병 세분류(4단 상병) 통계
        url = f"https://opendata.hira.or.kr/op/opc/olap4thDsInfoTab2.do?olapCd=A{code}&tabGubun=Tab2&gubun=R&sRvYr=2010&eRvYr=2022&sDiagYm=&eDiagYm=&sYm=&eYm="
    elif datatype == 3:
        # 진료행위(검사/수술 등) 통계
        url = f"https://opendata.hira.or.kr/op/opc/olapDiagBhvInfoTab2.do?olapCd=1{code}&tabGubun=Tab2&gubun=R&sRvYr=2010&eRvYr=2022&sDiagYm=&eDiagYm=&sYm=&eYm="
    res = requests.get(url)
    soup = BeautifulSoup(res.text, 'lxml')
    result = soup.find(attrs={'class':'tblType02 data webScroll'})

    df = pd.read_html(str(result))[0]
    df = df.dropna(axis=0)

    df.columns = ['_'.join(col).strip() for col in df.columns.values]

    column = []
    for col in df.columns:
        if 'Unnamed' in col:
            col = col.split('_')[3]
        column.append(col)

    df.columns = column
    df = df.melt(id_vars=['항목', '성별구분', '심사년도_연령구분5세'])

    df[['심사년도', '항목구분']] = df['variable'].str.split('_', expand=True)
    df.rename(columns={'심사년도_연령구분5세':'연령구분'}, inplace=True)
    df.drop(['variable'], axis='columns', inplace=True)
    df = df[['항목', '심사년도', '항목구분', '성별구분', '연령구분', 'value']]
    st.write(df)
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df['value'] = df['value'].fillna(0)

    return df


tab1, tab2 = st.tabs(["KOFIABOND", "HIRA"])

with tab1:
    st.subheader("KOFIABOND")

    if press_button:
        try:
            driver = webdriver.Chrome(options=options,
                                        service=service
                                        )
            driver.get(URL)
            
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
    st.subheader("HIRA")

    help_datatype = "datatype: 1-질병 소분류(3단 상병), 2-질병 소분류(4단 상병), 3-진료행위(검사/수술 등)"
    datatype = st.selectbox("Select Data Type", options=[1, 2, 3], index=0, help=help_datatype)

    if datatype == 1:
        defaultCode = 'C50'
    elif datatype == 2:
        defaultCode = 'L400'
    elif datatype == 3:
        defaultCode = 'U2233'
    code = st.text_input("Input HIRA Code", value=defaultCode)

    if press_button:
        df = call_HIRA_new(datatype, code)

        st.write(df)
