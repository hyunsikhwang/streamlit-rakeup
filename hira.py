import logging
import re
import time
from io import BytesIO, StringIO
from math import isfinite
from urllib.parse import urlencode
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

import pandas as pd
import requests
from bs4 import BeautifulSoup
from defusedxml.common import DefusedXmlException
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException


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


class HiraExportError(Exception):
    """An invalid HIRA spreadsheet with a message safe to display."""


HIRA_PROCEDURE_PORTAL = _BASE_URL + _ROUTES[3][0]
HIRA_EXPORT_MAX_MB = 2
_OUTPUT_COLUMNS = ["항목", "심사년도", "항목구분", "성별구분", "연령구분", "value"]
_EXPORT_TITLE = re.compile(r"진료행위_성별연령5세구간별현황\(단위_명, 회, 천원\)_(\d{4})_(\d{4})")
_EXPORT_METRICS = ("환자수", "총사용량", "진료금액")
_INVALID_EXPORT = "심평원 진료행위 통계의 ‘성별/연령5세구간별’ 탭에서 심사년도로 조회해 받은 .xlsx 파일을 올려 주세요."


def parse_hira_procedure_export(content):
    """Convert the portal's annual procedure export to the live lookup schema."""
    if len(content) > HIRA_EXPORT_MAX_MB * 1024**2:
        raise HiraExportError(f"파일이 너무 큽니다. {HIRA_EXPORT_MAX_MB}MB 이하의 .xlsx 파일을 올려 주세요.")

    stream = BytesIO(content)
    try:
        with ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) > 100 or sum(m.file_size for m in members) > 10 * 1024**2:
                raise HiraExportError("파일을 펼쳤을 때 크기가 너무 큽니다. 심평원 원본 파일을 올려 주세요.")
        stream.seek(0)
        book = load_workbook(stream, read_only=True, keep_links=False)
        try:
            if len(book.worksheets) != 1:
                raise HiraExportError(_INVALID_EXPORT)
            sheet = book.worksheets[0]
            if (sheet.max_row or 0) > 250 or (sheet.max_column or 0) > 200:
                raise HiraExportError(_INVALID_EXPORT)
            rows = list(sheet.iter_rows(max_row=251, max_col=200, values_only=True))
        finally:
            book.close()
    except (BadZipFile, InvalidFileException, OSError, ValueError, KeyError, IndexError,
            TypeError, AttributeError, RuntimeError, ParseError, DefusedXmlException) as exc:
        raise HiraExportError("엑셀 파일을 읽을 수 없습니다. 심평원에서 받은 .xlsx 원본인지 확인해 주세요.") from exc

    if len(rows) < 4:
        raise HiraExportError(_INVALID_EXPORT)
    title = _EXPORT_TITLE.fullmatch(str(rows[0][0]))
    if not title:
        raise HiraExportError(_INVALID_EXPORT)
    first, last = map(int, title.groups())
    year_count = last - first + 1
    if not 1 <= year_count <= 65:
        raise HiraExportError(_INVALID_EXPORT)

    years = [f"{year}년" for year in range(first, last + 1)]
    width = 3 + 3 * year_count
    year_header, metric_header = rows[2:4]
    if (
        year_header[2] != "심사년도"
        or list(year_header[3:width:3]) != years
        or metric_header[:width] != ("항목", "성별구분", "연령구분5세") + _EXPORT_METRICS * year_count
        or any(cell is not None for cell in metric_header[width:])
    ):
        raise HiraExportError(_INVALID_EXPORT)

    data = []
    for row in rows[4:]:
        if not any(cell is not None for cell in row):
            continue
        code, sex, age = row[:3]
        if (
            not re.fullmatch(r"[A-Z0-9]{5,9}", str(code))
            or sex not in ("계", "남", "여")
            or not re.fullmatch(r"계|소계|\d{1,3}(?:[_~–-]\d{1,3})?세(?:미만|이상)?", str(age))
            or any(cell is not None for cell in row[width:])
        ):
            raise HiraExportError("통계표에 올바르지 않은 항목·성별·연령 값이 있습니다. 심평원 원본 파일을 확인해 주세요.")
        values = tuple(0 if cell == "-" else cell for cell in row[3:width])
        if any(type(cell) not in (int, float) or not isfinite(cell) or cell < 0 for cell in values):
            raise HiraExportError("통계표에 비어 있거나 숫자가 아닌 통계 값이 있습니다. 심평원 원본 파일을 확인해 주세요.")
        data.append((str(code), sex, age, values))

    if not data:
        raise HiraExportError("업로드한 파일에 변환할 통계 데이터가 없습니다.")
    if len({code for code, _, _, _ in data}) != 1 or len({row[:3] for row in data}) != len(data):
        raise HiraExportError("통계표에 코드가 섞여 있거나 중복 행이 있습니다. 한 코드의 심평원 원본 파일을 올려 주세요.")

    return pd.DataFrame.from_records(
        ((code, year, metric, sex, age, values[3 * i + j])
         for i, year in enumerate(years) for j, metric in enumerate(_EXPORT_METRICS)
         for code, sex, age, values in data),
        columns=_OUTPUT_COLUMNS,
    )


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
    df = df[_OUTPUT_COLUMNS].copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0)
    return df


def _query_params(prefix, code, fstYr, lstYr):
    return {
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


def _fetch_procedure_export(code, first_year, last_year):
    form = {"searchWrd": code, **_query_params(_ROUTES[3][1], code, first_year, last_year)}
    with requests.post(
        _BASE_URL + "downExcelDiagBhvInfo.do",
        data=form,
        headers={"Referer": f"{HIRA_PROCEDURE_PORTAL}?{urlencode(form)}"},
        timeout=(5, 12),
        stream=True,
        allow_redirects=False,
    ) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise HiraExportError("다운로드 주소가 변경되었습니다.")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > HIRA_EXPORT_MAX_MB * 1024**2:
                raise HiraExportError("다운로드 파일이 너무 큽니다.")
    result = parse_hira_procedure_export(content)
    if result["항목"].unique().tolist() != [code] or result["심사년도"].unique().tolist() != [
        f"{year}년" for year in range(first_year, last_year + 1)
    ]:
        raise HiraExportError("다운로드한 통계의 코드 또는 연도가 조회 조건과 다릅니다.")
    return result


def lookup_hira(datatype, code, first_year, last_year):
    """Return the result and whether it came from the official Excel export."""
    if datatype != 3:
        return call_HIRA_new(datatype, code, first_year, last_year), False
    if not re.fullmatch(r"[A-Z0-9]{5,9}", code):
        raise HiraLookupError("진료행위 코드를 확인해 주세요(예: U2233).")
    if not 1 <= last_year - first_year + 1 <= 65:
        raise HiraLookupError("시작 연도와 종료 연도를 확인해 주세요.")
    try:
        return _fetch_procedure_export(code, first_year, last_year), True
    except (requests.RequestException, HiraExportError) as exc:
        status = exc.response.status_code if isinstance(exc, requests.RequestException) and exc.response is not None else None
        logger.warning("HIRA %s Excel download failed: %s (status=%s)", code, type(exc).__name__, status)
        if status in (401, 403, 429):
            raise HiraLookupError(f"심평원 엑셀 다운로드가 제한되었습니다(HTTP {status}).") from exc
        if isinstance(exc, requests.exceptions.SSLError):
            raise HiraLookupError("심평원 서버와 보안 연결을 설정하지 못했습니다.") from exc
    try:
        return call_HIRA_new(datatype, code, first_year, last_year), False
    except HiraLookupError as exc:
        raise HiraLookupError(f"공식 엑셀을 자동으로 받지 못했습니다. 통계표 조회도 실패했습니다: {exc}") from exc


def call_HIRA_new(datatype, code, fstYr, lstYr):
    path, prefix = _ROUTES[datatype]
    params = _query_params(prefix, code, fstYr, lstYr)
    page = _fetch_page(_BASE_URL + path, params)
    try:
        return _parse_table(page)
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        logger.warning("Could not parse HIRA statistics for %s", params["olapCd"], exc_info=True)
        raise HiraLookupError("심평원 통계표를 읽을 수 없습니다. 포털에서 조회 결과를 확인해 주세요.") from exc
