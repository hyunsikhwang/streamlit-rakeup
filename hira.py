import logging
import time
from io import StringIO

import pandas as pd
import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)
_BASE_URL = "https://opendata.hira.or.kr/op/opc/"
_ROUTES = {
    1: ("olap3thDsInfoTab2.do", "A"),
    2: ("olap4thDsInfoTab2.do", "A"),
    3: ("olapDiagBhvInfoTab2.do", "1"),
}
_TIMEOUT = (5, 15)  # Connect and read, in seconds.
_RETRY_DELAYS = (1, 2)
_RETRY_STATUSES = {500, 502, 503, 504}


class HiraLookupError(Exception):
    """A failed lookup with a message safe to display in Streamlit."""


def _fetch_page(url, params):
    for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
        try:
            response = requests.get(url, params=params, timeout=_TIMEOUT)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            retryable = status in _RETRY_STATUSES or (
                isinstance(exc, (requests.ConnectionError, requests.Timeout,
                                 requests.exceptions.ChunkedEncodingError))
                and not isinstance(exc, requests.exceptions.SSLError)
            )
            final_attempt = not retryable or delay is None
            logger.warning(
                "HIRA %r lookup attempt %d failed: %s (status=%s)",
                params["olapCd"], attempt, type(exc).__name__, status, exc_info=final_attempt,
            )
            if final_attempt:
                if status is not None:
                    message = f"심평원 조회 요청이 실패했습니다(HTTP {status}). 잠시 후 다시 시도해 주세요."
                elif isinstance(exc, requests.exceptions.SSLError):
                    message = "심평원 서버와 보안 연결을 설정하지 못했습니다. 잠시 후 다시 시도해 주세요."
                else:
                    message = "심평원 서버에 연결할 수 없거나 응답이 지연됩니다. 잠시 후 다시 시도해 주세요."
                raise HiraLookupError(message) from exc
            time.sleep(delay)


def _parse_table(page):
    table = BeautifulSoup(page, "lxml").select_one(".tblType02.data.webScroll table, table.tblType02.data.webScroll")
    if table is None:
        raise HiraLookupError("심평원 응답에서 통계표를 찾을 수 없습니다. 조회 조건이나 포털 상태를 확인해 주세요.")

    df = pd.read_html(StringIO(str(table)))[0].dropna(axis=0)
    df.columns = ["_".join(col).strip() for col in df.columns.values]
    df.columns = [col.split("_")[3] if "Unnamed" in col else col for col in df.columns]
    df = df.melt(id_vars=["항목", "성별구분", "심사년도_연령구분5세"])

    df[["심사년도", "항목구분"]] = df["variable"].str.split("_", expand=True)
    df = df.rename(columns={"심사년도_연령구분5세": "연령구분"})
    df = df[["항목", "심사년도", "항목구분", "성별구분", "연령구분", "value"]].copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0)
    return df


def call_HIRA_new(datatype, code, fstYr, lstYr):
    path, prefix = _ROUTES[datatype]
    params = {
        "olapCd": prefix + code,
        "tabGubun": "Tab2",
        "gubun": "R",
        "sRvYr": fstYr,
        "eRvYr": lstYr,
        "sDiagYm": "",
        "eDiagYm": "",
        "sYm": "",
        "eYm": "",
    }
    page = _fetch_page(_BASE_URL + path, params)
    try:
        return _parse_table(page)
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        logger.warning("Could not parse HIRA statistics for %s", params["olapCd"], exc_info=True)
        raise HiraLookupError("심평원 통계표를 읽을 수 없습니다. 포털에서 조회 결과를 확인해 주세요.") from exc
