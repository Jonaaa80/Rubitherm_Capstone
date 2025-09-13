import unittest
from pathlib import Path
from email import message_from_binary_file
import json

from src.main import handle_email
from src.utils.data_collector import collect_and_write


EMAIL_DIR = Path(__file__).parent / "emails"  # src/tests/emails


def load_eml(path: Path):
    with path.open("rb") as f:
        return message_from_binary_file(f)


def run_pipeline_and_capture(email_obj):
    data = handle_email(email_obj)
    if data is None:
        raise AssertionError("handle_email() hat None zurückgegeben – erwartet wurde ein Dictionary.")
    # Pretty print to stdout for visibility during tests (optional)
    try:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except TypeError as e:
        raise AssertionError(f"Ergebnis ist nicht JSON-serialisierbar: {e}\nObjekt: {data}")
    return data


def deep_get(d, dotted_key, default=None):
    cur = d
    for part in dotted_key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


class TestEmailPipelineFromFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not EMAIL_DIR.exists():
            raise AssertionError(
                f"EMail-Testordner fehlt: {EMAIL_DIR}. "
                f"Lege dort *.eml an (optional: passende *.expected.json)."
            )

    def test_all_emls(self):
        eml_files = sorted(EMAIL_DIR.glob("*.eml"))
        self.assertTrue(eml_files, f"Keine .eml-Dateien in {EMAIL_DIR}")

        collected = []
        for eml_path in eml_files:
            with self.subTest(email=eml_path.name):
                msg = load_eml(eml_path)
                data = run_pipeline_and_capture(msg)

                # Smoke-Checks
                self.assertIn("meta", data)
                
                # Optional: erwartete Assertions aus .expected.json laden
                exp_path = eml_path.with_suffix(".expected.json")
                if exp_path.exists():
                    with exp_path.open("r", encoding="utf-8") as f:
                        expected = json.load(f)
                    # expected als { "pfad.zum.feld": "wert" } oder verschachtelt
                    # beide Varianten unterstützen:
                    if all(isinstance(k, str) and "." in k for k in expected.keys()):
                        # Dot-Path Assertions
                        for dotted_key, exp_val in expected.items():
                            got = deep_get(data, dotted_key)
                            self.assertEqual(
                                exp_val, got,
                                msg=f"Erwartet {dotted_key} == {exp_val!r} in {eml_path.name}, erhalten: {got!r}"
                            )
                    else:
                        # Teilvergleich verschachtelt: jeder Top-Level-Key in expected muss in data matchen
                        def assert_subset(exp, got, ctx="$"):
                            self.assertIsInstance(got, dict, f"{ctx} sollte ein Objekt sein")
                            for k, v in exp.items():
                                self.assertIn(k, got, f"{ctx}.{k} fehlt in Ergebnis")
                                if isinstance(v, dict):
                                    assert_subset(v, got[k], f"{ctx}.{k}")
                                else:
                                    self.assertEqual(
                                        v, got[k],
                                        f"{ctx}.{k} Erwartet {v!r}, erhalten {got[k]!r}"
                                    )
                        assert_subset(expected, data, "$")
                collected.append(data)
        columns = [
            # Meta
            "meta.from",
            "meta.to",
            "meta.subject",
            "meta.message_id",
            "meta.date",
            # Visible body
            "parsed.body_window",
            # Signature fields (flattened)
            "signature.full_name",
            "signature.role",
            "signature.company",
            "signature.address[*]",
            "signature.phone[*]",
            "signature.email[*]",
            "signature.url[*]",
            # CRM extraction (flattened)
            "ai_extract_crm.extracted_by",
            "ai_extract_crm.extracted_data.first_name",
            "ai_extract_crm.extracted_data.last_name",
            "ai_extract_crm.extracted_data.company[*]",
            "ai_extract_crm.extracted_data.customer_phone",
            "ai_extract_crm.extracted_data.email[*]",
            "ai_extract_crm.extracted_data.roles",
            "ai_extract_crm.extracted_data.address",
            "ai_extract_crm.extracted_data.website[*]",
            "ai_extract_crm.extracted_data.message",
            # Web enrichment
            "ai_web._sources[*]",
            # Klassifikation raw
            "klassifikation_raw.StatusAngebot",
            "klassifikation_raw.Universität",
            "klassifikation_raw.PhaseCube",
            "klassifikation_raw.PhaseTube",
            "klassifikation_raw.PhaseDrum",
        ]
        collect_and_write(collected, columns, "test_output.csv")


if __name__ == "__main__":
    unittest.main()