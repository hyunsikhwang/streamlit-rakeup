# This codes are from https://ohenziblog.com/streamlit_cloud_for_selenium/
# Thanks to the author for great help.
import os
os.system("playwright install")

import streamlit as st
from selenium import webdriver
# from webdriver_manager.chrome import ChromeDriverManager
# from selenium.webdriver.chrome import service as fs
from selenium.webdriver import ChromeOptions
# from webdriver_manager.core.utils import ChromeType
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import requests
import numpy as np
import extra_streamlit_components as stx
from io import BytesIO
from stqdm import stqdm
from playwright.sync_api import Playwright, sync_playwright, expect
from datetime import datetime
from pytz import timezone, utc
from stqdm import stqdm
import streamlit_authenticator as stauth
import json
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Error as PlaywrightError
from pathlib import Path


st.title("Scraping in streamlit cloud")

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

# CHROMEDRIVER = ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
# service = fs.Service(CHROMEDRIVER)
service = Service()

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

def call_HIRA_new(datatype, code, fstYr, lstYr):

    if datatype == 1:
        # 질병 소분류(3단 상병) 통계
        url = f"https://opendata.hira.or.kr/op/opc/olap3thDsInfoTab2.do?olapCd=A{code}&tabGubun=Tab2&gubun=R&sRvYr={fstYr}&eRvYr={lstYr}&sDiagYm=&eDiagYm=&sYm=&eYm="
    elif datatype == 2:
        # 질병 세분류(4단 상병) 통계
        url = f"https://opendata.hira.or.kr/op/opc/olap4thDsInfoTab2.do?olapCd=A{code}&tabGubun=Tab2&gubun=R&sRvYr={fstYr}&eRvYr={lstYr}&sDiagYm=&eDiagYm=&sYm=&eYm="
    elif datatype == 3:
        # 진료행위(검사/수술 등) 통계
        url = f"https://opendata.hira.or.kr/op/opc/olapDiagBhvInfoTab2.do?olapCd=1{code}&tabGubun=Tab2&gubun=R&sRvYr={fstYr}&eRvYr={lstYr}&sDiagYm=&eDiagYm=&sYm=&eYm="
    
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
    
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df['value'] = df['value'].fillna(0)

    return df

def to_excel(df):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Sheet1')
    writer.close()

    processed_data = output.getvalue()

    return processed_data


def run_kofiabond(playwright: Playwright):

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.kofiabond.or.kr/websquare/websquare.html?w2xPath=/xml/bondint/lastrop/BISLastAskPrcDay.xml&divisionId=MBIS01010010000000&divisionNm=%25EC%259D%25BC%25EC%259E%2590%25EB%25B3%2584&tabIdx=1&w2xHome=/xml/&w2xDocumentRoot=")
    page.get_by_role("link", name="조회").click()

    content = page.content()
    
    soup = BeautifulSoup(content, 'html5lib').find_all('table', attrs={'id':'grdMain_body_table'})

    df = pd.read_html(str(soup[0]))[0]

    context.close()
    browser.close()

    return df

def run_lottery(playwright: Playwright):

    id = st.secrets["lottery"]["id"]
    pw = st.secrets["lottery"]["password"]

    KST = timezone('Asia/Seoul')
    now = datetime.utcnow()

    SeoulTime = utc.localize(now).astimezone(KST)
    ThisYr0101 = SeoulTime.strftime("%Y0101")
    curDate = SeoulTime.strftime("%Y%m%d")

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.goto("https://dhlottery.co.kr/user.do?method=login&returnUrl=")
    page.get_by_placeholder("아이디").click()
    page.get_by_placeholder("아이디").fill(id)
    page.get_by_placeholder("아이디").press("Tab")
    page.get_by_placeholder("비밀번호").fill(pw)
    page.get_by_placeholder("비밀번호").press("Tab")
    page.get_by_role("group", name="LOGIN").get_by_role("link", name="로그인").press("Enter")

    time.sleep(2)
    page.goto("https://dhlottery.co.kr/userSsl.do?method=myPage")

    page.get_by_role("link", name="구매/당첨").click()
    page.get_by_role("link", name="1개월").click()
    page.get_by_role("link", name="조회", exact=True).click()
    page.get_by_role("link", name="조회", exact=True).click()
    page.get_by_role("link", name="조회", exact=True).click()
    page.goto(f"https://dhlottery.co.kr/myPage.do?method=lottoBuyList&searchStartDate={ThisYr0101}&searchEndDate={curDate}&lottoId=&nowPage=1")
    
    content = page.content()

    soup = BeautifulSoup(content, 'html5lib').find_all('table', attrs={'class':'tbl_data tbl_data_col'})

    df = pd.read_html(str(soup[0]))[0]

    context.close()
    browser.close()

    return df

def run_lottery_all(playwright: Playwright) -> pd.DataFrame:
    id = st.secrets["lottery"]["id"]
    pw = st.secrets["lottery"]["password"]

    KST = timezone('Asia/Seoul')
    now = datetime.utcnow()

    SeoulTime = utc.localize(now).astimezone(KST)
    curDate = SeoulTime.strftime("%Y%m%d")

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.goto("https://dhlottery.co.kr/user.do?method=login&returnUrl=")
    page.get_by_placeholder("아이디").click()
    page.get_by_placeholder("아이디").fill(id)
    page.get_by_placeholder("아이디").press("Tab")
    page.get_by_placeholder("비밀번호").fill(pw)
    page.get_by_placeholder("비밀번호").press("Tab")
    page.get_by_role("group", name="LOGIN").get_by_role("link", name="로그인").press("Enter")

    time.sleep(2)

    # 마지막 페이지 찾기
    page.goto(f"https://dhlottery.co.kr/myPage.do?method=lottoBuyList&searchStartDate=20200502&searchEndDate={curDate}&lottoId=&nowPage=100000")

    content_end = page.content()
    soup_end = BeautifulSoup(content_end, 'html5lib').find_all('div', attrs={'class':'paginate_common'})
    for pageList in soup_end:
        for pagenum in pageList.find_all('a'):
            lastPageStr = pagenum.text.replace(" ", "")

    lastPageNum = int(lastPageStr) + 1
    print(lastPageNum)

    page.goto("https://dhlottery.co.kr/userSsl.do?method=myPage")

    page.get_by_role("link", name="구매/당첨").click()
    page.get_by_role("link", name="1개월").click()
    page.get_by_role("link", name="조회", exact=True).click()
    page.get_by_role("link", name="조회", exact=True).click()
    page.get_by_role("link", name="조회", exact=True).click()

    df_all = pd.DataFrame()
    
    for i in stqdm(range(1, lastPageNum)):
        page.goto(f"https://dhlottery.co.kr/myPage.do?method=lottoBuyList&searchStartDate=20200502&searchEndDate={curDate}&lottoId=&nowPage={i}")
    # print(page.content())
        content = page.content()
        soup = BeautifulSoup(content, 'html5lib').find_all('table', attrs={'class':'tbl_data tbl_data_col'})

        df = pd.read_html(str(soup[0]))[0]
        df_all = pd.concat([df_all, df])

    # with open('lottery.txt', 'w') as textfile:
    #     textfile.write(page.content())
    
    df_all.to_excel('lottery.xlsx', index=False)

    # ---------------------
    context.close()
    browser.close()

    return df_all

def run_benecafe(playwright):
    user_id = st.secrets["benecafe"]["id"]
    user_pw = st.secrets["benecafe"]["password"]

    browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    context = browser.new_context(ignore_https_errors=True, timezone_id="Asia/Seoul", locale="ko-KR")
    context.set_default_timeout(60_000)  # 기본 타임아웃
    page = context.new_page()

    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)

    def dump_debug(tag: str):
        try:
            page.screenshot(path=str(debug_dir / f"benecafe_{tag}.png"), full_page=True)
        except Exception:
            pass
        try:
            (debug_dir / f"benecafe_{tag}.html").write_text(page.content(), encoding="utf-8")
        except Exception:
            pass

    try:
        # 1) 로그인 페이지
        page.goto("https://cert.benecafe.co.kr/member/login?&cmpyNo=AA5", wait_until="domcontentloaded")

        # 2) 입력 및 로그인 클릭
        page.get_by_placeholder("아이디").fill(user_id)
        page.get_by_placeholder("비밀번호").fill(user_pw)
        page.get_by_role("link", name="로그인", exact=True).click()

        # ❌ page.wait_for_load_state("networkidle")  # <- 이 줄이 지금 문제의 원인입니다.

        # 3) 로그인 성공의 “확정 신호”를 기다림 (요소 기반)
        page.wait_for_selector('text="나의정보"', timeout=60_000)

        # 4) 팝업 닫기 (있으면)
        close_btn = page.get_by_role("link", name="닫기")
        if close_btn.count() > 0:
            close_btn.first.click()

        # 5) 데이터 호출은 page.goto 대신 context.request로 (세션/쿠키 공유)
        #    날짜는 예시(기존 하드코딩 유지). 필요하면 UI 입력으로 바꾸세요.
        api_url = (
            "https://rga.benecafe.co.kr/mywel/getWelfarecardDemandListVer"
            "?crdcoNo=HA&rtnTpCd=&crtcrdProdNo=&ecluCrtcrdRealHhAskYn=N&necluCrtcrdRealHhAskYn=N"
            "&searchStartDate=2025-11-26&searchEndDate=2025-12-26"
            "&applStatCd=00&alreadyApplicationExclustion=&multiCrtcrdRealYn=false&adminPswd="
        )

        resp = context.request.get(api_url, timeout=60_000)
        st.write(f"[benecafe] API status = {resp.status}")

        if resp.status != 200:
            dump_debug(f"api_status_{resp.status}")
            raise RuntimeError(f"Benecafe API returned HTTP {resp.status}")

        return resp.text()

    except PlaywrightTimeoutError:
        dump_debug("timeout")
        raise
    except PlaywrightError:
        dump_debug("playwright_error")
        raise
    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass


def run_tmoney(playwright: Playwright):
    id = st.secrets["tmoney"]["id"]
    pw = st.secrets["tmoney"]["password"]

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://pay.tmoney.co.kr/ncs/pct/mtmn/ReadTrprInqr.dev")
    page.get_by_placeholder("아이디").click()
    page.get_by_placeholder("아이디").fill(id)
    page.get_by_placeholder("비밀번호").click()
    page.get_by_placeholder("비밀번호").fill(pw)
    page.get_by_title("로그인하기").press("Enter")

    time.sleep(2)

    page.get_by_label("동의함").click()
    page.get_by_role("combobox", name="사용내역 카드선택").select_option(value="1010010071641385")
    page.get_by_text("최근1년").click()
    page.get_by_role("link", name="조회", exact=True).click()

    time.sleep(3)

    content = page.content()
    soup = BeautifulSoup(content, 'html5lib').find_all('table', attrs={'id':'protable'})

    soup_tr1 = str(soup[0])
    soup_tr2 = str(soup[1])
    soup_cs = str(soup[2])

    df_tr1 = pd.read_html(soup_tr1)[0]
    df_tr2 = pd.read_html(soup_tr2)[0]
    df_cs = pd.read_html(soup_cs)[0]

    # ---------------------
    context.close()
    browser.close()

    return df_tr1, df_tr2, df_cs

def benecafe_json_write(html_content: str):
    json_match = re.search(r'<pre>(.*?)</pre>', html_content, re.DOTALL)
    if json_match:
        json_str = json_match.group(1).strip()
        try:
            # JSON 파싱
            data = json.loads(json_str)
            
            # 성공 여부 확인
            if data.get("success"):
                # welfarecardDemandList 추출
                demand_list = data["resultMap"]["welfarecardDemandList"]
                
                # 각 항목을 예쁘게 출력
                for idx, item in enumerate(demand_list, start=1):
                    st.subheader(f"항목 {idx}")
                    
                    # 주요 정보 선택적으로 출력 (null 값은 제외)
                    key_info = {
                        "영수증 번호": item.get("slsRcvNo"),
                        "카드사": item.get("crdcoNm"),
                        "사용 일자": item.get("crtcrdUseDd"),
                        "사용 시간": item.get("crtcrdUseHh"),
                        "사용 금액": item.get("usePrc"),
                        "지불 일자": item.get("prsnPayDd"),
                        "상점 이름": item.get("mcnsNm"),
                        "상점 유형": item.get("mcnsBntpNm"),
                        "등록 여부": item.get("regYn"),
                        "환불 여부": item.get("rtnYn"),
                        "신청 상태": item.get("cstApplStatNm"),
                        "신청 금액": item.get("applPrc")
                    }
                    
                    # null이나 None인 값 제거
                    filtered_info = {k: v for k, v in key_info.items() if v is not None}
                    
                    # Markdown으로 예쁘게 출력
                    for key, value in filtered_info.items():
                        st.markdown(f"**{key}:** {value}")
                    
                    st.divider()  # 구분선 추가
            else:
                st.error("JSON 데이터가 성공적으로 처리되지 않았습니다.")
        except json.JSONDecodeError:
            st.error("JSON 파싱 중 오류가 발생했습니다.")
    else:
        st.error("HTML에서 JSON을 추출할 수 없습니다.")


chosen_id = stx.tab_bar(data=[
    stx.TabBarItemData(id=1, title="KOFIABOND", description="with Selenium"),
    stx.TabBarItemData(id=2, title="HIRA", description="with Requests"),
    stx.TabBarItemData(id=3, title="KOFIABOND", description="with Playwright"),
    # stx.TabBarItemData(id=4, title="복권", description="with Playwright"),
    stx.TabBarItemData(id=5, title="복리후생", description="with Playwright"),
    # stx.TabBarItemData(id=6, title="tmoney", description="with Playwright"),
], default=1)

placeholder = st.container()

# tab1, tab2 = st.tabs(["KOFIABOND", "HIRA"])

if chosen_id == '1':
# with tab1:
    placeholder.subheader("KOFIABOND")

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

            placeholder.write(df_bond)

        finally:
            driver.quit()
            # 스크래핑이 완료되었음을 streamlit 앱에 표시
            placeholder.write("Scraping completed!!!")
elif chosen_id == '2':
# with tab2:
    placeholder.subheader("HIRA")

    help_datatype = "datatype: 1-질병 소분류(3단 상병), 2-질병 소분류(4단 상병), 3-진료행위(검사/수술 등)"
    datatype_dict = {'질병 소분류(3단 상병)':1, '질병 소분류(4단 상병)':2, '진료행위(검사/수술 등)':3}
    datatype = placeholder.selectbox("Select Data Type", options=datatype_dict.keys(), index=0, help=help_datatype)

    if datatype_dict[datatype] == 1:
        defaultCode = 'C50'
    elif datatype_dict[datatype] == 2:
        defaultCode = 'L400'
    elif datatype_dict[datatype] == 3:
        defaultCode = 'U2233'
    codes = placeholder.text_input("Input HIRA Code", value=defaultCode)
    
    codes = codes.upper().replace(' ', '').split(',')

    fstYr = placeholder.selectbox("Select first year", options=range(2010, 2023), index=0)
    lstYr = placeholder.selectbox("Select last year", options=range(2010, 2023), index=2023-2010-1)

    if press_button:
        df = pd.DataFrame()
        for code in stqdm(codes):
            df_code = call_HIRA_new(datatype_dict[datatype], code, fstYr, lstYr)
            df = pd.concat([df, df_code])

        placeholder.write(df)

        file_name = f'HIRA_{datatype_dict[datatype]}_{code}_{fstYr}_{lstYr}.xlsx'
        df_xlsx = to_excel(df)

        download = st.download_button(
            label="📥 Download Current Result",
            data=df_xlsx,
            file_name=file_name,
            )
elif chosen_id == '3':
    placeholder.subheader("KOFIABOND")
    if press_button:
        with sync_playwright() as playwright:
            df = run_kofiabond(playwright)
        st.write(df)
elif chosen_id == '4':
    placeholder.subheader("복권")
    if press_button:
        with sync_playwright() as playwright:
            df = run_lottery(playwright)
        st.write(df)
    if st.button("Extract all"):
        with sync_playwright() as playwright:
            df = run_lottery_all(playwright)
            df_ltr = df.copy()

            df_ltr = df_ltr[(df_ltr['복권명']=='연금복권720')]
            df_ltr['당첨금'] = df_ltr['당첨금'].str.replace(',', '', regex=True).replace('원', '', regex=True).replace('-', '0', regex=True).astype(int)

            total_buy = df_ltr['구입매수'].sum() * 1000
            count_buy = df_ltr['구입매수'].count()
            total_won = df_ltr['당첨금'].sum()
            count_won = df_ltr[(df_ltr['당첨금']>0)]['당첨금'].count()

            st.write(f'{total_buy:,.0f}원 구입해서, {total_won:,.0f}원 당첨')
            st.write(f'금액기준: {total_won/total_buy:.1%}, 횟수기준: {count_won/count_buy:.1%}')
        
        st.write(df)
elif chosen_id == '5':
    placeholder.subheader("복리후생")
    if press_button:
        with sync_playwright() as playwright:
            html_content = run_benecafe(playwright)
        benecafe_json_write(html_content)
        # st.write(res)
elif chosen_id == '6':
    placeholder.subheader("티머니")
    tm_pw = st.text_input("Input passkey", type="password")
    stl_pw = st.secrets["general"]["password"]
    if tm_pw == stl_pw:
        st.write("Success!")
        with sync_playwright() as playwright:
            df_tr1, df_tr2, df_cs = run_tmoney(playwright)
        st.write(df_tr1)
        st.write(df_tr2)
        st.write(df_cs)
