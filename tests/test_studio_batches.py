"""Make many: reading lists, matching columns, validating rows and queueing one export each."""

import asyncio
import datetime
import io
import json
import os
import time

import pytest

from studio import batches
from studio.api import router
from studio.errors import BusyError
from studio.registry import TemplateError
from studio.service import StudioService
from tests.studio_fakes import FakeRunner, RunnerFactory, make_service, wait_until


def run(coro):
    return asyncio.run(coro)


def announcement_schema():
    from studio import registry

    return registry.get_template("announcement").params_model.model_json_schema()


def settled(service, count=None, statuses=None):
    """Every batch record, once the expected number/statuses have arrived."""
    records = service._export_manager().list()
    if count is not None and len(records) != count:
        return None
    if statuses is not None and {record["status"] for record in records} != set(statuses):
        return None
    return records


def workbook_bytes(rows, formula=None):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(list(row))
    if formula:
        sheet[formula[0]] = formula[1]
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# -- reading the list -------------------------------------------------------------------

def test_csv_and_tsv_detect_the_delimiter_and_keep_cells_text():
    headers, rows = batches.parse_text("Product,Price\nMug,12\nTote,9")
    assert headers == ["Product", "Price"] and rows == [["Mug", "12"], ["Tote", "9"]]

    headers, rows = batches.parse_text("Name\tCity\nAna\tBerlin")
    assert headers == ["Name", "City"] and rows == [["Ana", "Berlin"]]

    headers, rows = batches.parse_text("Name;City\nAna;Berlin")
    assert headers == ["Name", "City"] and rows == [["Ana", "Berlin"]]

    headers, rows = batches.parse_text('Product,Note\nMug,"Café, 9 am"\n')
    assert headers == ["Product", "Note"] and rows == [["Mug", "Café, 9 am"]]


def test_utf8_bom_and_cp1252_both_read_as_text():
    headers, rows = batches.parse_bytes("Title,Name\nJava,André\n".encode("utf-8-sig"))
    assert headers == ["Title", "Name"] and rows == [["Java", "André"]]

    headers, rows = batches.parse_bytes("Café,Crème\n1,2".encode("cp1252"), "list.csv")
    assert headers == ["Café", "Crème"] and rows == [["1", "2"]]


def test_blank_rows_and_trailing_columns_are_dropped_and_headers_are_named():
    headers, rows = batches.parse_text("Name,,City,,\nAna,,Berlin,,\n   ,,   ,,\n")
    assert headers == ["Name", "Column 2", "City"]
    assert rows == [["Ana", "", "Berlin"]]


def test_excel_dates_numbers_booleans_and_formulas_become_plain_text():
    data = workbook_bytes(
        [["When", "Number", "Small", "Paid", "Note", "Formula"],
         [datetime.date(2026, 6, 14), 42, 1.5, True, "ok", None],
         [datetime.datetime(2026, 6, 14, 19, 30), 3.0, -0.25, False, "fine", None]],
        formula=("F2", "=1+1"),
    )
    headers, rows = batches.parse_bytes(data, "list.xlsx")
    assert headers == ["When", "Number", "Small", "Paid", "Note", "Formula"]
    assert rows[0] == ["14 June 2026", "42", "1.5", "Yes", "ok", ""]
    assert rows[1] == ["14 June 2026, 19:30", "3", "-0.25", "No", "fine", ""]
    assert "=1+1" not in json.dumps(rows)  # the formula was never evaluated


def test_control_characters_are_stripped_and_unknown_files_are_named():
    headers, rows = batches.parse_text("Name\nA\x00B\x07")
    assert headers == ["Name"] and rows == [["AB"]]
    assert batches.clean_cell(0) == "0" and batches.clean_cell(None) == ""

    with pytest.raises(batches.BatchError, match="empty"):
        batches.parse_bytes(b"", "list.csv")
    with pytest.raises(batches.BatchError, match="Only .xlsx"):
        batches.parse_bytes(b"anything", "list.xls")
    with pytest.raises(batches.BatchError, match="column names but no rows"):
        batches.parse_text("Name,City\n")


def test_limits_are_explained_in_plain_words():
    with pytest.raises(batches.BatchError, match="201 rows"):
        batches.parse_text("Name\n" + "\n".join(f"Row {index}" for index in range(201)))
    with pytest.raises(batches.BatchError, match="41 columns"):
        batches.parse_text(",".join(f"C{index}" for index in range(41)) + "\n" + ",".join("x" for _ in range(41)))
    with pytest.raises(batches.BatchError, match="most you can use at once is 2 MB"):
        batches.parse_bytes(b"x" * (batches.MAX_BYTES + 1), "big.csv")
    with pytest.raises(batches.BatchError, match="readable as text"):
        batches.parse_bytes(b"\x81\x8d\x8f", "legacy.csv")


def test_a_tab_on_the_first_line_wins_over_commas_inside_cells():
    headers, rows = batches.parse_text("Smith, John\tPaid\nAna, Maria\tUnpaid")
    assert headers == ["Smith, John", "Paid"]
    assert rows == [["Ana, Maria", "Unpaid"]]

    headers, rows = batches.parse_text("Name,Paid\nAna,yes")
    assert headers == ["Name", "Paid"] and rows == [["Ana", "yes"]]


def test_blank_spreadsheet_rows_do_not_hide_the_rows_after_them():
    data = workbook_bytes([["Name"], ["First"], *([[None]] * 300), ["After the blanks"]])
    headers, rows = batches.parse_bytes(data, "list.xlsx")
    assert headers == ["Name"]
    assert rows == [["First"], ["After the blanks"]]


def test_too_many_rows_is_still_explained_when_blanks_sit_between_real_rows():
    rows = [["Name"]]
    for index in range(201):
        rows.append([f"Row {index}"])
        rows.append([None])
    with pytest.raises(batches.BatchError, match="201 rows"):
        batches.parse_bytes(workbook_bytes(rows), "list.xlsx")


def test_a_sheet_of_blank_rows_stops_reading(monkeypatch):
    rows = [["Name"], ["First"], *([[None]] * 10), ["Second"]]
    monkeypatch.setattr(batches, "MAX_SHEET_ROWS", 5)
    headers, read = batches.parse_bytes(workbook_bytes(rows), "list.xlsx")
    assert headers == ["Name"] and read == [["First"]]


def test_a_spreadsheet_that_breaks_while_reading_says_it_cannot_be_read(monkeypatch):
    openpyxl = pytest.importorskip("openpyxl")

    class BrokenSheet:
        def iter_rows(self, values_only=True):
            raise OSError("truncated member")

    class BrokenWorkbook:
        worksheets = [BrokenSheet()]

        def close(self):
            pass

    monkeypatch.setattr(openpyxl, "load_workbook", lambda *args, **kwargs: BrokenWorkbook())
    with pytest.raises(batches.BatchError, match="spreadsheet can't be read"):
        batches.parse_bytes(b"PK\x03\x04broken", "list.xlsx")


# -- columns and fields -------------------------------------------------------------------

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "title": "Headline", "x-widget": "textarea", "maxLength": 40},
        "product": {"type": "string", "title": "Product Name", "x-widget": "text", "maxLength": 60},
        "price": {"type": "number", "title": "Price", "x-widget": "number"},
        "accent": {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Accent color", "x-widget": "color"},
        "details": {"type": "array", "title": "Details", "x-widget": "list", "items": {"type": "object"}},
        "photo": {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Photo", "x-widget": "image"},
        "layout": {"type": "string", "title": "Layout", "enum": ["a", "b"], "x-widget": "choice"},
        "big": {"type": "string", "title": "Big text", "maxLength": 12},
    },
    "required": ["headline"],
}


def test_only_simple_fields_can_be_filled_from_a_list():
    fields = batches.mappable_fields(SCHEMA)
    assert [field["field"] for field in fields] == ["headline", "product", "price", "accent", "big"]
    assert [field["kind"] for field in fields] == ["text", "text", "number", "color", "text"]
    assert {field["label"] for field in fields} >= {"Headline", "Product Name", "Price", "Accent color"}
    assert next(field for field in fields if field["field"] == "headline")["required"] is True

    real = {field["field"]: field["kind"] for field in batches.mappable_fields(announcement_schema())}
    assert {"headline", "kicker", "big_text", "call_to_action", "teaser", "qr_text", "accent"} <= set(real)
    assert real["accent"] == "color"
    assert not {"details", "image", "logo", "layout"} & set(real)


def test_columns_match_field_names_and_labels_ignoring_case_and_punctuation():
    fields = batches.mappable_fields(SCHEMA)
    headers = ["HEADLINE!", "product name", "Price (€)", "accent_color", "Big text"]
    mapping = batches.suggest_mapping(fields, headers)
    assert mapping == {"headline": 0, "product": 1, "price": 2, "accent": 3, "big": 4}
    assert len(set(mapping.values())) == len(mapping)  # never one column for two fields

    mapping = batches.suggest_mapping(fields, ["Who it's for", "Colour", "Amount"])
    assert mapping == {}

    # Prefixes and spacing still find a home; a short unrelated name does not.
    assert batches.suggest_mapping(fields, ["Headline text"]) == {"headline": 0}
    assert batches.suggest_title_column(fields, ["Product", "Headline"], {"product": 0, "headline": 1}) == 1
    assert batches.suggest_title_column(fields, ["Name", "Price"], {}) == 0


# -- rows and validation ------------------------------------------------------------------

def test_empty_cells_keep_the_design_and_colors_are_normalized():
    fields = batches.mappable_fields(SCHEMA)
    mapping = {"headline": 1, "accent": 2}
    params = batches.row_params({"headline": "Design text", "accent": None, "product": "Original"},
                                fields, mapping, ["", "", "2563eb"])
    assert params == {"headline": "Design text", "accent": "#2563EB", "product": "Original"}
    assert batches.normalize_color("#0f9f6e") == "#0F9F6E"
    assert batches.normalize_color("not a color") == "not a color"


def test_file_stems_are_safe_unique_and_windows_friendly():
    assert batches.safe_file_stem("../../etc/passwd") == "etc-passwd"
    assert batches.safe_file_stem("Summer fair") == "summer-fair"
    assert batches.safe_file_stem("CON") == "con-video"
    assert batches.safe_file_stem("lpt1") == "lpt1-video"
    assert batches.safe_file_stem("   ") == "video"
    assert "/" not in batches.safe_file_stem("a/b\\c")


def test_each_row_is_validated_and_the_good_ones_still_queue(tmp_path):
    service, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("ok"), FakeRunner("ok")))
    try:
        rows = [["Summer fair", "14.06"], ["x" * 60, "14.06"], ["Bake sale", "21.06"]]
        result = service.start_batch_sync(
            "announcement", {"headline": "Design"}, {"theme": "pop"},
            mapping={"headline": 0, "big_text": 1}, rows=rows, title_column=0, quality="draft")
        assert len(result["export_ids"]) == 2 and result["batch"]["total"] == 2
        assert [error["row"] for error in result["row_errors"]] == [2]
        problem = result["row_errors"][0]["errors"][0]
        assert problem["field"] == "params.headline" and problem["label"] == "Headline"
        assert problem["message"] == "Use at most 40 characters."
        assert result["batch"]["name"].endswith("2 videos")

        records = service._export_manager().list()
        assert {record["batch_id"] for record in records} == {result["batch_id"]}
        assert {record["batch_total"] for record in records} == {2}
        assert {record["batch_title"] for record in records} == {result["batch"]["name"]}
        assert {record["folder"] for record in records} == {result["batch"]["folder"]}
        assert all(os.path.basename(record["folder"]) == record["folder"] for record in records)

        done = wait_until(lambda: settled(service, count=2, statuses={"done"}))
        folder = os.path.join(service.exports_dir, done[0]["folder"])
        assert os.path.isdir(folder)
        for record in done:
            assert record["filename"].startswith(("summer-fair-", "bake-sale-"))
            assert os.path.isfile(os.path.join(folder, record["filename"]))
            assert record["url"].startswith("/media/studio/exports/" + record["folder"] + "/")
        assert len({record["filename"] for record in done}) == 2

        counts = service.get_batch_sync(result["batch_id"])["counts"]
        assert counts == {"queued": 0, "rendering": 0, "done": 2, "failed": 0, "cancelled": 0}
    finally:
        service.shutdown_sync()


def test_a_running_list_does_not_block_one_normal_export(tmp_path):
    blocker = FakeRunner("block")
    service, _ = make_service(tmp_path, runners=RunnerFactory(blocker), max_active_exports=1)
    try:
        result = service.start_batch_sync(
            "announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
            rows=[["One"], ["Two"], ["Three"]], title_column=0, quality="draft")
        assert len(result["export_ids"]) == 3
        assert blocker.started.wait(5)

        single = service.start_export_sync("countdown", {}, {"sound": {"effects": False}}, quality="draft")
        assert service._export_manager().get(single["id"])["status"] == "queued"
        with pytest.raises(BusyError):
            service.start_export_sync("countdown", {}, {"sound": {"effects": False}}, quality="draft")
    finally:
        blocker.release.set()
        service.shutdown_sync()


def test_the_whole_queue_is_bounded_across_lists(tmp_path, monkeypatch):
    monkeypatch.setattr("studio.service.MAX_WAITING_EXPORTS", 3)
    blocker = FakeRunner("block")
    service, _ = make_service(tmp_path, runners=RunnerFactory(blocker))
    try:
        first = service.start_batch_sync(
            "announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
            rows=[["One"], ["Two"]], title_column=0, quality="draft")
        assert blocker.started.wait(5)

        with pytest.raises(batches.BatchError, match="You already have 2 videos waiting"):
            service.start_batch_sync("announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
                                     rows=[["Three"], ["Four"]], title_column=0, quality="draft")
        assert len(service._export_manager().list()) == 2
        assert [record["id"] for record in service._batch_store.list()] == [first["batch_id"]]

        service.start_batch_sync("announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
                                 rows=[["Three"]], title_column=0, quality="draft")
        with pytest.raises(batches.BatchError, match="You already have 3 videos waiting"):
            service.start_batch_sync("announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
                                     rows=[["Four"]], title_column=0, quality="draft")
        assert len(service._export_manager().list()) == 3
    finally:
        blocker.release.set()
        service.shutdown_sync()


def test_a_list_where_no_row_can_be_used_queues_and_writes_nothing(tmp_path):
    service, _ = make_service(tmp_path)
    try:
        with pytest.raises(batches.BatchError) as info:
            service.start_batch_sync("announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
                                     rows=[["x" * 60, "ok"], ["y" * 60, "ok"]], title_column=0)
        message = str(info.value)
        assert message.startswith("None of these rows can be made yet.")
        assert "Row 1" in message and "Use at most 40 characters." in message
        assert service._export_manager().list() == []
        assert service._batch_store.list() == []
    finally:
        service.shutdown_sync()


def test_deleting_a_lists_last_video_removes_its_folder(tmp_path):
    service, _ = make_service(tmp_path)
    try:
        result = service.start_batch_sync(
            "announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
            rows=[["One"], ["Two"]], title_column=0, quality="draft")
        done = wait_until(lambda: settled(service, count=2, statuses={"done"}))
        folder = os.path.join(service.exports_dir, result["batch"]["folder"])
        assert os.path.isdir(folder)

        service._export_manager().remove(done[0]["id"])
        assert os.path.isdir(folder)  # the other row's file still lives there
        service._export_manager().remove(done[1]["id"])
        assert not os.path.isdir(folder)
        assert os.path.isdir(service.exports_dir)
    finally:
        service.shutdown_sync()


def test_title_column_controls_the_file_name_and_never_escapes_the_batch_folder(tmp_path):
    service, _ = make_service(tmp_path)
    try:
        result = service.start_batch_sync(
            "announcement", {}, {"theme": "clean"},
            mapping={"headline": 1}, rows=[["../../CON", "Summer fair"], ["..\\..\\nul", "Summer fair"]],
            title_column=0, quality="draft")
        assert len(result["export_ids"]) == 2
        done = wait_until(lambda: settled(service, count=2, statuses={"done"}))
        root = os.path.realpath(service.exports_dir)
        for record in done:
            path = os.path.realpath(os.path.join(service.exports_dir, record["folder"], record["filename"]))
            assert os.path.commonpath([root, path]) == root
            assert os.path.basename(record["filename"]) == record["filename"]
            assert record["filename"].startswith(("con-video-", "nul-video-"))
        assert len({record["filename"] for record in done}) == 2
    finally:
        service.shutdown_sync()


def test_batch_cancel_stops_unfinished_rows_and_retry_queues_failed_ones(tmp_path):
    blocker = FakeRunner("block")
    service, _ = make_service(tmp_path, runners=RunnerFactory(blocker, FakeRunner("ok")))
    try:
        result = service.start_batch_sync(
            "announcement", {}, {"theme": "clean"},
            mapping={"headline": 0}, rows=[["One"], ["Two"]], title_column=0, quality="draft")
        assert blocker.started.wait(5)
        cancelled = service.cancel_batch_sync(result["batch_id"])
        assert cancelled["cancelled"] == 2
        wait_until(lambda: all(record["status"] == "cancelled" for record in service._export_manager().list()))
        assert service.get_batch_sync(result["batch_id"])["counts"]["cancelled"] == 2
    finally:
        blocker.release.set()
        service.shutdown_sync()

    # A failed row is retried into the same batch, with a new export id and file.
    failing = FakeRunner("fail")
    retry_dir = tmp_path / "retry"
    retry_dir.mkdir()
    service, _ = make_service(retry_dir, runners=RunnerFactory(failing, FakeRunner("ok"), FakeRunner("ok")))
    try:
        result = service.start_batch_sync(
            "announcement", {}, {"theme": "clean"},
            mapping={"headline": 0}, rows=[["Broken"], ["Fine"]], title_column=0, quality="draft")
        wait_until(lambda: settled(service, count=2, statuses={"failed", "done"}))
        failed = next(record for record in service._export_manager().list() if record["status"] == "failed")
        retried = service.retry_batch_sync(result["batch_id"])
        assert retried["retried"] and retried["skipped"] == []
        assert failed["id"] not in retried["retried"]
        wait_until(lambda: settled(service, count=2, statuses={"done"}))
        assert service.get_batch_sync(result["batch_id"])["counts"]["failed"] == 0
        assert service.get_batch_sync(result["batch_id"])["counts"]["done"] == 2
        assert len(service._export_manager().list()) == 2  # the failed row was replaced, not duplicated
    finally:
        service.shutdown_sync()


def test_a_batch_survives_a_restart_like_its_exports(tmp_path):
    blocker = FakeRunner("block")
    first, _ = make_service(tmp_path, runners=RunnerFactory(blocker))
    result = first.start_batch_sync(
        "announcement", {}, {"theme": "clean"}, mapping={"headline": 0},
        rows=[["One"], ["Two"]], title_column=0, quality="draft")
    assert blocker.started.wait(5)
    first.shutdown_sync()  # a clean stop hands the unfinished exports back to the queue
    blocker.release.set()

    second, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("ok"), FakeRunner("ok")))
    try:
        records = wait_until(lambda: settled(second, count=2, statuses={"done"}))
        assert {record["batch_id"] for record in records} == {result["batch_id"]}
        batch = second.get_batch_sync(result["batch_id"])
        assert batch["counts"]["done"] == 2 and batch["folder"] == result["batch"]["folder"]
    finally:
        second.shutdown_sync()


def test_unknown_batch_and_impossible_rows_say_what_is_wrong(tmp_path):
    service, _ = make_service(tmp_path)
    try:
        with pytest.raises(Exception, match="isn't here anymore"):
            service.get_batch_sync("000000000000")
        with pytest.raises(batches.BatchError, match="no rows"):
            service.start_batch_sync("announcement", {}, {}, mapping={}, rows=[])
        with pytest.raises(batches.BatchError, match="can't be filled"):
            service.start_batch_sync("announcement", {}, {}, mapping={"details": 0}, rows=[["x"]])
        with pytest.raises(TemplateError) as info:
            service.start_batch_sync("announcement", {}, {"theme": "neon"}, mapping={}, rows=[["x"]])
        assert {error["field"] for error in info.value.errors} == {"settings.theme"}

        with pytest.raises(batches.BatchError) as info:
            service.start_batch_sync("announcement", {"headline": "x" * 60}, {}, mapping={},
                                     rows=[["x"], ["y"]])
        assert "None of these rows can be made yet." in str(info.value)
        assert "Row 1" in str(info.value) and "Use at most 40 characters." in str(info.value)
        assert service._export_manager().list() == []
        assert service._batch_store.list() == []
    finally:
        service.shutdown_sync()


# -- the REST routes ----------------------------------------------------------------------

def test_batch_routes_parse_create_group_cancel_and_retry(tmp_path):
    from fastapi import FastAPI
    import httpx
    from studio import api

    service, _ = make_service(tmp_path, runners=RunnerFactory(FakeRunner("fail"), FakeRunner("ok")))
    app = FastAPI()
    app.include_router(router)
    original = api.service_module.service
    api.service_module.service = service

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            parsed = (await client.post("/api/studio/batches/parse", json={
                "template": "announcement",
                "text": "Headline,Big text\nSummer fair,14.06\nBake sale,21.06\n"})).json()
            assert parsed["headers"] == ["Headline", "Big text"]
            assert parsed["suggested_mapping"] == {"headline": 0, "big_text": 1}
            assert [field["field"] for field in parsed["fields"]][:2] == ["teaser", "kicker"]

            checked = (await client.post("/api/studio/batches/parse", json={
                "template": "announcement", "rows": [["x" * 60, "14.06"]], "mapping": {"headline": 0},
                "params": {}, "settings": {}})).json()
            assert checked["row_errors"][0]["errors"][0]["message"] == "Use at most 40 characters."

            created = await client.post("/api/studio/batches", json={
                "template": "announcement", "params": {}, "settings": {"theme": "clean"},
                "mapping": {"headline": 0}, "rows": [["Summer fair"], ["Bake sale"]],
                "title_column": 0, "format": "mp4", "quality": "draft"})
            assert created.status_code == 202
            body = created.json()
            assert len(body["export_ids"]) == 2 and body["row_errors"] == []
            batch_id = body["batch_id"]

            status = (await client.get(f"/api/studio/batches/{batch_id}")).json()
            assert sum(status["counts"].values()) == 2
            listing = (await client.get("/api/studio/exports")).json()
            assert {record["batch_id"] for record in listing} == {batch_id}

            await asyncio.to_thread(wait_until, lambda: any(
                record["status"] == "failed" for record in service._export_manager().list()))
            retried = (await client.post(f"/api/studio/batches/{batch_id}/retry")).json()
            assert len(retried["retried"]) == 1 and sum(retried["counts"].values()) == 2
            cancelled = (await client.post(f"/api/studio/batches/{batch_id}/cancel")).json()
            assert cancelled["cancelled"] >= 0
            assert (await client.get(f"/api/studio/batches/{batch_id}")).status_code == 200
            assert (await client.get("/api/studio/batches/000000000000")).status_code == 404
            unusable = await client.post("/api/studio/batches", json={
                "template": "announcement", "params": {}, "settings": {"theme": "clean"},
                "mapping": {"headline": 0}, "rows": [["x" * 60]], "title_column": 0})
            assert unusable.status_code == 422
            assert "None of these rows can be made yet." in unusable.json()["detail"]
            bad = await client.post("/api/studio/batches", json={"template": "announcement", "nope": 1})
            assert bad.status_code == 422
    try:
        run(scenario())
    finally:
        api.service_module.service = original
        service.shutdown_sync()


# -- one real render ----------------------------------------------------------------------

def test_two_rows_render_to_real_mp4_in_one_folder(tmp_path):
    pytest.importorskip("manim")
    from executor import media_file_is_complete

    service = StudioService(str(tmp_path / "ws"))
    try:
        result = service.start_batch_sync(
            "countdown", {}, {"aspect": "16:9", "theme": "pop", "sound": {"effects": False}},
            mapping={"title": 0, "seconds": 1}, rows=[["Class A", "3"], ["Class B", "3"]],
            title_column=0, format="mp4", quality="draft")
        assert len(result["export_ids"]) == 2 and result["row_errors"] == []
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            records = service._export_manager().list()
            if len(records) == 2 and all(record["status"] in ("done", "failed", "cancelled")
                                         for record in records):
                break
            time.sleep(0.25)
        assert [record["status"] for record in records] == ["done", "done"], records
        folder = os.path.join(service.exports_dir, records[0]["folder"])
        assert len({record["folder"] for record in records}) == 1
        for record in records:
            assert record["filename"].startswith(("class-a-", "class-b-"))
            assert media_file_is_complete(os.path.join(folder, record["filename"]))
    finally:
        service.shutdown_sync()


# -- the MCP tool -------------------------------------------------------------------------

def test_agent_make_many_and_the_guide_section(tmp_path):
    pytest.importorskip("mcp.server.mcpserver")
    from studio.mcp_server import create_server

    service, _ = make_service(tmp_path)
    server = create_server(service)
    try:
        names = {tool.name for tool in run(server.list_tools())}
        assert "make_many" in names
        result = run(server.call_tool("make_many", {
            "template": "announcement", "preset": "weekend-sale",
            "rows": [["Summer fair", "14.06"], ["Bake sale", "21.06"]],
            "mapping": {"headline": 0, "big_text": 1}, "title_column": 0, "quality": "draft"}))
        assert not result.is_error, result
        data = json.loads(next(block.text for block in result.content if block.type == "text"))
        assert data["batch_id"] and len(data["export_ids"]) == 2 and data["row_errors"] == []
        assert data["app_url"].endswith("/#/exports")
        assert sum(data["batch"]["counts"].values()) == 2
        assert {record["batch_id"] for record in service._export_manager().list()} == {data["batch_id"]}

        with pytest.raises(Exception, match="Unknown preset"):
            run(server.call_tool("make_many", {"template": "announcement", "preset": "nope",
                                               "rows": [["x"]], "mapping": {}}))
        guide = "".join(block.text for block in run(server.call_tool("guide", {"topic": "many"})).content
                        if block.type == "text")
        assert "make_many" in guide and "200 rows" in guide and "row_errors" in guide
        start = "".join(block.text for block in run(server.call_tool("guide", {})).content if block.type == "text")
        assert 'guide("many")' in start
    finally:
        service.shutdown_sync()
