"""Unit tests: the hand-rolled JSON schema validator."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ev_common as C


class SchemaTest(unittest.TestCase):
    def test_minimal_valid(self):
        C.validate_against_schema({"a": 1, "b": "x"},
                                  {"type": "object",
                                   "required": ["a"],
                                   "properties": {
                                       "a": {"type": "integer"},
                                       "b": {"type": "string"}}})

    def test_missing_required(self):
        with self.assertRaises(C.SchemaError) as ctx:
            C.validate_against_schema({},
                                      {"type": "object",
                                       "required": ["a"],
                                       "properties": {
                                           "a": {"type": "integer"}}})
        self.assertIn("missing required", str(ctx.exception))

    def test_wrong_type(self):
        with self.assertRaises(C.SchemaError):
            C.validate_against_schema({"a": "1"},
                                      {"type": "object",
                                       "required": ["a"],
                                       "properties": {
                                           "a": {"type": "integer"}}})

    def test_bool_is_not_number(self):
        with self.assertRaises(C.SchemaError):
            C.validate_against_schema({"a": True},
                                      {"type": "object",
                                       "required": ["a"],
                                       "properties": {
                                           "a": {"type": "number"}}})

    def test_enum_violation(self):
        with self.assertRaises(C.SchemaError):
            C.validate_against_schema({"a": "x"},
                                      {"type": "object",
                                       "required": ["a"],
                                       "properties": {
                                           "a": {"type": "string",
                                                 "enum": ["y", "z"]}}})

    def test_array_items(self):
        with self.assertRaises(C.SchemaError):
            C.validate_against_schema(
                {"xs": [1, "two"]},
                {"type": "object", "required": ["xs"],
                 "properties": {"xs": {"type": "array",
                                       "items": {"type": "integer"}}}})

    def test_nested_path_in_error(self):
        with self.assertRaises(C.SchemaError) as ctx:
            C.validate_against_schema(
                {"xs": [{"a": "wrong"}]},
                {"type": "object", "required": ["xs"],
                 "properties": {"xs": {"type": "array", "items": {
                     "type": "object", "required": ["a"],
                     "properties": {"a": {"type": "integer"}}}}}})
        self.assertIn("xs[0].a", str(ctx.exception))

    def test_min_items_and_minimum(self):
        with self.assertRaises(C.SchemaError):
            C.validate_against_schema(
                {"xs": []},
                {"type": "object", "required": ["xs"],
                 "properties": {"xs": {"type": "array",
                                       "minItems": 1}}})
        with self.assertRaises(C.SchemaError):
            C.validate_against_schema(
                {"n": -1},
                {"type": "object", "required": ["n"],
                 "properties": {"n": {"type": "number",
                                     "minimum": 0}}})

    def test_unexpected_type_value(self):
        with self.assertRaises(C.SchemaError):
            C.validate_against_schema(42, {"type": "object"})


class StepSchemasTest(unittest.TestCase):
    def test_research_schema_rejects_empty_candidates_entry(self):
        schema = C.research_schema()
        bad = {"run_id": "r", "offer_period": "p", "candidates": [{}]}
        with self.assertRaises(C.SchemaError):
            C.validate_against_schema(bad, schema)

    def test_verdict_schema(self):
        good = {
            "run_id": "r", "verdict_line": "**1 deal** met all four criteria",
            "criteria_rows": [{"setting": "S", "value": "V"}],
            "report_markdown": "report",
            "deals": [{"header_text": "h",
                       "options": [{"label": "l", "link": "https://x",
                                    "rate_text": "r", "payment_text": "p",
                                    "qualifies": True}],
                       "notes": []}],
        }
        C.validate_against_schema(good, C.verdict_schema())

    def test_calculators_schema_configs_enum(self):
        schema = C.calculators_schema(["lease-48"])
        bad_cfg = {"run_id": "r", "configs": [{
            "candidate_index": 0, "config": "finance-72",
            "rate_apr": 1.0, "biweekly_payment": 180.0,
            "deep_link": "https://x", "url_notes": "",
            "calculator_applied_evap": False, "verified_live": True}]}
        with self.assertRaises(C.SchemaError):
            C.validate_against_schema(bad_cfg, schema)


if __name__ == "__main__":
    unittest.main()
