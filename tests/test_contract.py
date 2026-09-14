"""Regression tests prove the verifier rejects representative contract mistakes."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_contract import ContractError, load_contract, verify  # noqa: E402


class ContractChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = load_contract(ROOT / "contracts/openapi.yaml")
        cls.fixtures = json.loads((ROOT / "contracts/fixtures.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.document = copy.deepcopy(self.source)

    def rejected(self):
        with self.assertRaises(Exception):
            verify(self.document, self.fixtures)

    def test_repository_contract_and_fixtures(self):
        self.assertEqual(verify(self.document, self.fixtures)["operations"], 5)

    def test_unknown_reference_rejected(self):
        self.document["components"]["schemas"]["CreateProject"]["properties"]["displayName"] = {"$ref": "#/missing"}
        self.rejected()

    def test_external_reference_rejected_before_validation(self):
        self.document["components"]["schemas"]["ProjectId"] = {"$ref": "https://example.com/schema.json"}
        with self.assertRaisesRegex(ContractError, "Only local"):
            verify(self.document, self.fixtures)

    def test_missing_explicit_security_rejected(self):
        del self.document["paths"]["/v1/projects"]["get"]["security"]
        self.rejected()

    def test_anonymous_security_rejected(self):
        self.document["paths"]["/v1/projects"]["get"]["security"] = []
        self.rejected()

    def test_duplicate_operation_identifier_rejected(self):
        self.document["paths"]["/v1/projects"]["post"]["operationId"] = "listProjects"
        self.rejected()

    def test_incorrect_example_type_rejected(self):
        self.document["paths"]["/v1/projects"]["post"]["requestBody"]["content"]["application/json"]["example"]["displayName"] = 123
        self.rejected()

    def test_error_http_status_mismatch_rejected(self):
        self.document["components"]["responses"]["NotFound"]["content"]["application/problem+json"]["example"]["status"] = 403
        self.rejected()

    def test_missing_authentication_challenge_rejected(self):
        del self.document["components"]["responses"]["Unauthorized"]["headers"]["WWW-Authenticate"]
        self.rejected()

    def test_missing_retry_after_rejected(self):
        del self.document["components"]["responses"]["Unavailable"]["headers"]["Retry-After"]
        self.rejected()

    def test_unknown_request_fields_policy_rejected(self):
        self.document["components"]["schemas"]["CreateProject"]["additionalProperties"] = True
        self.rejected()

    def test_closed_response_schema_rejected(self):
        self.document["components"]["schemas"]["Project"]["additionalProperties"] = False
        self.rejected()

    def test_dollar_members_in_instance_data_are_not_references(self):
        response = self.source["paths"]["/v1/projects/{projectId}"]["get"]["responses"]["200"]
        sample = copy.deepcopy(response["content"]["application/json"]["example"])
        sample["futureExtension"] = {"$ref": "https://example.com/business-data", "$id": "ordinary-business-value"}
        for placement in ("media-example", "example-object-value", "schema-examples"):
            with self.subTest(placement=placement):
                document = copy.deepcopy(self.source)
                media = document["paths"]["/v1/projects/{projectId}"]["get"]["responses"]["200"]["content"]["application/json"]
                if placement == "media-example":
                    media["example"] = sample
                elif placement == "example-object-value":
                    del media["example"]
                    media["examples"] = {"future": {"value": sample}}
                else:
                    document["components"]["schemas"]["Project"]["examples"] = [sample]
                self.assertEqual(verify(document, self.fixtures)["operations"], 5)

    def test_schema_property_named_ref_is_data_name(self):
        self.document["components"]["schemas"]["Project"]["properties"]["$ref"] = {"type": "string"}
        self.assertEqual(verify(self.document, self.fixtures)["operations"], 5)

    def test_missing_expected_operation_rejected(self):
        del self.document["paths"]["/v1/projects/{projectId}"]["delete"]
        self.rejected()

    def test_required_request_headers_cannot_be_removed(self):
        for path, method in (("/v1/projects", "post"), ("/v1/projects/{projectId}", "patch"),
                             ("/v1/projects/{projectId}", "delete")):
            with self.subTest(method=method):
                self.document = copy.deepcopy(self.source)
                del self.document["paths"][path][method]["parameters"]
                self.rejected()

    def test_required_request_headers_cannot_be_optional(self):
        for parameter in ("IdempotencyKey", "IfMatch"):
            with self.subTest(parameter=parameter):
                self.document = copy.deepcopy(self.source)
                self.document["components"]["parameters"][parameter]["required"] = False
                self.rejected()

    def test_required_success_headers_cannot_be_removed(self):
        cases = (("/v1/projects", "post", "201", "Location"),
                 ("/v1/projects", "post", "201", "ETag"),
                 ("/v1/projects/{projectId}", "get", "200", "ETag"),
                 ("/v1/projects/{projectId}", "patch", "200", "ETag"))
        for path, method, status, name in cases:
            with self.subTest(method=method, header=name):
                self.document = copy.deepcopy(self.source)
                del self.document["paths"][path][method]["responses"][status]["headers"][name]
                self.rejected()

    def test_required_success_headers_cannot_be_optional(self):
        for header in ("ETag", "Location"):
            with self.subTest(header=header):
                self.document = copy.deepcopy(self.source)
                if header == "ETag":
                    self.document["components"]["headers"]["ETag"]["required"] = False
                else:
                    self.document["paths"]["/v1/projects"]["post"]["responses"]["201"]["headers"][header]["required"] = False
                self.rejected()

    def test_all_response_objects_require_request_id(self):
        for name in self.source["components"]["responses"]:
            with self.subTest(error_response=name):
                self.document = copy.deepcopy(self.source)
                del self.document["components"]["responses"][name]["headers"]["X-Request-Id"]
                self.rejected()
        cases = (("/v1/projects", "get", "200"), ("/v1/projects", "post", "201"),
                 ("/v1/projects/{projectId}", "get", "200"),
                 ("/v1/projects/{projectId}", "patch", "200"),
                 ("/v1/projects/{projectId}", "delete", "204"))
        for path, method, status in cases:
            with self.subTest(success_response=method + path):
                self.document = copy.deepcopy(self.source)
                del self.document["paths"][path][method]["responses"][status]["headers"]["X-Request-Id"]
                self.rejected()

    def test_request_id_header_cannot_be_optional(self):
        self.document["components"]["headers"]["RequestId"]["required"] = False
        self.rejected()


if __name__ == "__main__":
    unittest.main()
