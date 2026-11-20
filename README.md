# Web scraping on Streamlit Cloud with Selenium

### This codes are from https://ohenziblog.com/streamlit_cloud_for_selenium/
### Thanks to the author for great help.

- Streamlit Cloud 에서 Selenium 을 구동시키는 코드입니다.
- 현재 테스트 목적으로 Selenium 을 이용하여 Scraping 하는 대상 사이트는 다음과 같습니다.
  - KOFIABOND: 금융투자협회 채권정보센터의 최종호가 수익률
  - HIRA: 심평원 빅데이터 개방포털

### HIRA 조회 안내

- 진료행위 코드 `U2233`은 HIRA에 `1U2233`으로 전달됩니다. 앱에는 `U2233`을 입력하세요.
- 연결 끊김이나 응답 지연 시 자동으로 재시도합니다. 계속 실패하면 잠시 후 다시 시도하거나 [HIRA 진료행위 통계](https://opendata.hira.or.kr/op/opc/olapDiagBhvInfoTab1.do)에서 직접 조회하세요. 여러 코드 중 일부가 실패해도 성공한 결과만 확인하고 내려받을 수 있습니다.
- 회귀 테스트: `python -m unittest test_hira`
