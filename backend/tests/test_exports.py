import csv
import io
import unittest

from flask import Flask
from openpyxl import load_workbook
from werkzeug.exceptions import BadRequest

from backend.app.services.exports import export_table


class ExportTableTestCase(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def export(self, extension, rows):
        with self.app.test_request_context(f"/export.{extension}"):
            response = export_table(["学号", "原文"], rows, "test-records", "学习记录")
            response.direct_passthrough = False
            data = response.get_data()
            response.close()
            return data

    def test_unicode_newlines_identifiers_and_formula_like_text(self):
        rows = [["001234", '中文、日本語, English\n"多行原文"'],
                ["001235", '=HYPERLINK("https://example.invalid")'],
                ["001236", "+123"], ["001237", "@文字"], ["001238", "#N/A"]]
        workbook = load_workbook(io.BytesIO(self.export("xlsx", rows)))
        sheet = workbook.active
        self.assertEqual([list(row) for row in list(sheet.values)[1:]], rows)
        self.assertTrue(all(cell.data_type == "s" for row in sheet for cell in row))
        workbook.close()
        csv_data = self.export("csv", rows)
        self.assertTrue(csv_data.startswith(b"\xef\xbb\xbf"))
        parsed = list(csv.reader(io.StringIO(csv_data.decode("utf-8-sig"))))
        self.assertEqual(parsed[1], rows[0])
        for index in (1, 2, 3):
            self.assertEqual(parsed[index + 1][1], "'" + rows[index][1])

    def test_excel_rejects_overlong_cells_instead_of_silently_truncating(self):
        rows = [["001234", "长" * 32768]]
        with self.assertRaises(BadRequest) as raised:
            self.export("xlsx", rows)
        self.assertIn("CSV", raised.exception.description)
        parsed = list(csv.reader(io.StringIO(self.export("csv", rows).decode("utf-8-sig"))))
        self.assertEqual(parsed[1], rows[0])
