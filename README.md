# Web scraping on Streamlit Cloud with Selenium

### This codes are from https://ohenziblog.com/streamlit_cloud_for_selenium/
### Thanks to the author for great help.

- Streamlit Cloud 에서 Selenium 을 구동시키는 코드입니다.
- 현재 테스트 목적으로 Selenium 을 이용하여 Scraping 하는 대상 사이트는 다음과 같습니다.
  - KOFIABOND: 금융투자협회 채권정보센터의 최종호가 수익률
  - HIRA: 심평원 빅데이터 개방포털

### HIRA 조회 안내

- 진료행위 코드 `U2233`은 HIRA에 `1U2233`으로 전달됩니다. 앱에는 `U2233`을 입력하세요.
- 연결 끊김이나 응답 지연 시 자동으로 재시도합니다. 여러 코드 중 일부가 실패해도 성공한 결과만 확인하고 내려받을 수 있습니다.
- 진료행위 실시간 조회가 실패하면 [심평원 진료행위 통계](https://opendata.hira.or.kr/op/opc/olapDiagBhvInfoTab2.do)에서 **성별/연령5세구간별** 탭을 열고, `U2233` 등 코드 하나와 **심사년도** 범위를 선택해 **엑셀 다운로드**를 누르세요. 앱의 **심평원 엑셀 가져오기**에 받은 `.xlsx` 원본(2MB 이하)을 올리면 심평원 연결 없이 변환된 통계표를 내려받을 수 있습니다.
- 가져오기는 파일에 들어 있는 코드와 연도를 사용합니다. `-` 값은 기존 실시간 조회와 동일하게 `0`으로 변환합니다. 질병 통계와 진료년월 기준 파일은 지원하지 않습니다.
- 회귀 테스트: `python -m unittest test_hira`
