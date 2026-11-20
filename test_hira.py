import unittest
from http.client import RemoteDisconnected
from unittest.mock import patch

import requests

from hira import HiraLookupError, call_HIRA_new


_TABLE = """<html><head><meta charset="utf-8"></head><body>
<div class="tblType02 data webScroll"><table>
<thead>
<tr><th></th><th></th><th>심사년도</th><th colspan="3">2024년</th></tr>
<tr><th>항목</th><th>성별구분</th><th>연령구분5세</th><th>환자수</th><th>총사용량</th><th>진료금액</th></tr>
</thead>
<tbody><tr><th>U2233</th><th>계</th><th>계</th><td>1,234</td><td>-</td><td>5,678</td></tr></tbody>
</table></div></body></html>"""


def response(status, html=""):
    res = requests.Response()
    res.status_code = status
    res._content = html.encode("utf-8")
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
