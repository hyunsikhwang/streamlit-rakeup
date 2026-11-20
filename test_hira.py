import unittest
from http.client import RemoteDisconnected
from io import BytesIO
from unittest.mock import patch

import requests
from openpyxl import Workbook

from hira import HiraExportError, HiraLookupError, call_HIRA_new, lookup_hira, parse_hira_procedure_export


_TABLE = """<html><head><meta charset="utf-8"></head><body>
<div class="tblType02 data webScroll"><table>
<thead>
<tr><th></th><th></th><th>심사년도</th><th colspan="3">2024년</th></tr>
<tr><th>항목</th><th>성별구분</th><th>연령구분5세</th><th>환자수</th><th>총사용량</th><th>진료금액</th></tr>
</thead>
<tbody><tr><th>U2233</th><th>계</th><th>계</th><td>1,234</td><td>-</td><td>5,678</td></tr></tbody>
</table></div></body></html>"""


def response(status, content=""):
    res = requests.Response()
    res.status_code = status
    res.raw = BytesIO(content.encode("utf-8") if isinstance(content, str) else content)
    return res


@patch("hira.time.sleep")
@patch("hira.requests.get")
class HiraLookupTests(unittest.TestCase):
    def test_u2233_succeeds_after_remote_disconnect(self, get, sleep):
        get.side_effect = [
            requests.ConnectionError(RemoteDisconnected("Remote end closed connection without response")),
            response(200, _TABLE),
        ]
        with self.assertLogs("hira", level="WARNING"):
            df = call_HIRA_new(3, "U2233", 2010, 2024)

        self.assertEqual(2, get.call_count)
        request = get.call_args
        self.assertTrue(request.args[0].endswith("/olapDiagBhvInfoTab2.do"))
        self.assertEqual("1U2233", request.kwargs["params"]["olapCd"])
        self.assertEqual(2010, request.kwargs["params"]["sRvYr"])
        self.assertEqual(2024, request.kwargs["params"]["eRvYr"])
        self.assertTrue(all(t > 0 for t in request.kwargs["timeout"]))
        self.assertEqual(
            [
                ("U2233", "2024년", "환자수", "계", "계", 1234),
                ("U2233", "2024년", "총사용량", "계", "계", 0),
                ("U2233", "2024년", "진료금액", "계", "계", 5678),
            ],
            list(df.itertuples(index=False, name=None)),
        )

    def test_stops_after_repeated_timeouts(self, get, sleep):
        get.side_effect = requests.ReadTimeout("Internal connection details")
        with self.assertLogs("hira", level="WARNING"):
            with self.assertRaisesRegex(HiraLookupError, "응답이 지연") as raised:
                call_HIRA_new(3, "U2233", 2010, 2024)
        self.assertNotIn("Internal connection details", str(raised.exception))
        self.assertEqual(3, get.call_count)
        self.assertEqual(2, sleep.call_count)

    def test_retries_temporary_http_error_but_not_bad_request(self, get, sleep):
        get.side_effect = [response(503), response(400)]
        with self.assertLogs("hira", level="WARNING"):
            with self.assertRaisesRegex(HiraLookupError, "HTTP 400"):
                call_HIRA_new(3, "U2233", 2010, 2024)
        self.assertEqual(2, get.call_count)
        sleep.assert_called_once()

    def test_does_not_retry_a_tls_verification_failure(self, get, sleep):
        get.side_effect = requests.exceptions.SSLError("Certificate verification failed")
        with self.assertLogs("hira", level="WARNING"):
            with self.assertRaisesRegex(HiraLookupError, "보안 연결"):
                call_HIRA_new(3, "U2233", 2010, 2024)
        get.assert_called_once()
        sleep.assert_not_called()

    def test_rejects_a_successful_http_response_without_the_table(self, get, sleep):
        get.return_value = response(200, "<html><title>HIRA</title></html>")
        with self.assertRaisesRegex(HiraLookupError, "통계표를 찾을 수 없습니다"):
            call_HIRA_new(3, "U2233", 2010, 2024)
        get.assert_called_once()
        sleep.assert_not_called()


def official_export_fixture(*, code="U2233", second_year="2024년", value=1234, rows=True):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["진료행위_성별연령5세구간별현황(단위_명, 회, 천원)_2023_2024"])
    sheet.merge_cells("A1:K1")
    sheet.append([])
    sheet.append([None, None, "심사년도", "2023년", None, None, second_year])
    sheet.append(["항목", "성별구분", "연령구분5세"] + ["환자수", "총사용량", "진료금액"] * 2)
    if rows:
        sheet.append([code, "계", "계", value, "-", 5678, 2345, 3456, 6789])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@patch("hira.requests.get")
@patch("hira.requests.post")
class HiraAutomaticExportTests(unittest.TestCase):
    def test_posts_requested_code_and_years_and_converts_without_html(self, post, get):
        post.return_value = response(200, official_export_fixture())

        df, from_excel = lookup_hira(3, "U2233", 2023, 2024)

        self.assertTrue(from_excel)
        self.assertEqual([1234, 0, 5678, 2345, 3456, 6789], df["value"].tolist())
        request = post.call_args
        self.assertTrue(request.args[0].endswith("/downExcelDiagBhvInfo.do"))
        data = request.kwargs["data"]
        self.assertEqual(("U2233", "1U2233", 2023, 2024), tuple(
            data[key] for key in ("searchWrd", "olapCd", "sRvYr", "eRvYr")
        ))
        get.assert_not_called()

    def test_falls_back_when_download_is_unavailable_or_not_the_requested_workbook(self, post, get):
        for content in (b"<html>not an export</html>", official_export_fixture(code="U2234"),
                        official_export_fixture()):
            with self.subTest(size=len(content)):
                post.return_value = response(200, content)
                get.return_value = response(200, _TABLE)
                with self.assertLogs("hira", level="WARNING"):
                    df, from_excel = lookup_hira(3, "U2233", 2024, 2024)
                self.assertFalse(from_excel)
                self.assertEqual([1234, 0, 5678], df["value"].tolist())

    def test_explains_when_neither_download_nor_table_is_available(self, post, get):
        post.side_effect = requests.ReadTimeout("internal network details")
        get.return_value = response(200, "<html>no table</html>")
        with self.assertLogs("hira", level="WARNING"), self.assertRaisesRegex(
            HiraLookupError, "공식 엑셀을 자동으로 받지 못했습니다. 통계표 조회도 실패했습니다"
        ):
            lookup_hira(3, "U2233", 2024, 2024)

    def test_does_not_send_another_request_when_the_portal_rate_limits(self, post, get):
        post.return_value = response(429)
        with self.assertLogs("hira", level="WARNING"), self.assertRaisesRegex(HiraLookupError, "HTTP 429"):
            lookup_hira(3, "U2233", 2024, 2024)
        get.assert_not_called()

    def test_disease_still_uses_the_existing_lookup(self, post, get):
        get.return_value = response(200, _TABLE.replace("U2233", "C50"))
        df, from_excel = lookup_hira(1, "C50", 2024, 2024)
        self.assertFalse(from_excel)
        self.assertEqual(["C50"], df["항목"].unique().tolist())
        post.assert_not_called()


class HiraExportTests(unittest.TestCase):
    @patch("hira.requests.get")
    def test_converts_a_two_year_export_without_network(self, get):
        df = parse_hira_procedure_export(official_export_fixture())
        self.assertEqual(["항목", "심사년도", "항목구분", "성별구분", "연령구분", "value"], list(df.columns))
        self.assertEqual(["U2233"], df["항목"].unique().tolist())
        self.assertEqual(["2023년"] * 3 + ["2024년"] * 3, df["심사년도"].tolist())
        self.assertEqual(["환자수", "총사용량", "진료금액"] * 2, df["항목구분"].tolist())
        self.assertEqual([1234, 0, 5678, 2345, 3456, 6789], df["value"].tolist())
        get.assert_not_called()

    def test_rejects_a_corrupt_workbook(self):
        with self.assertRaisesRegex(HiraExportError, "읽을 수 없습니다"):
            parse_hira_procedure_export(b"not an excel workbook")

    def test_rejects_a_blank_generic_workbook(self):
        buffer = BytesIO()
        Workbook().save(buffer)
        with self.assertRaisesRegex(HiraExportError, "성별/연령5세구간별"):
            parse_hira_procedure_export(buffer.getvalue())

    def test_rejects_year_headers_not_matching_the_export_period(self):
        with self.assertRaisesRegex(HiraExportError, "성별/연령5세구간별"):
            parse_hira_procedure_export(official_export_fixture(second_year="2025년"))

    def test_rejects_empty_or_formula_data_instead_of_exporting_it(self):
        with self.assertRaisesRegex(HiraExportError, "변환할 통계 데이터가 없습니다"):
            parse_hira_procedure_export(official_export_fixture(rows=False))
        with self.assertRaisesRegex(HiraExportError, "숫자가 아닌 통계 값"):
            parse_hira_procedure_export(official_export_fixture(value="=1+1"))
