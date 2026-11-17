import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import ANY, MagicMock, call, patch

import requests
from requests.auth import HTTPBasicAuth

from sg_sync_function_tester import Work, encodeCv, staleCv

# Real-looking SG 4.x values: CVs contain '@' and base64 ('+', '/').
CV1 = "18e8e11501350000@+RTUz3ZWvU8ktL6AuG0csA"
CV2 = "18e8e11509750000@+RTUz3ZWvU8ktL6AuG0csA"
CV1_ENC = "18e8e11501350000%40%2BRTUz3ZWvU8ktL6AuG0csA"
JSON_HDR = {"Content-Type": "application/json"}


def okResponse(body):
    r = MagicMock()
    r.json.return_value = body
    r.text = json.dumps(body)
    r.raise_for_status = MagicMock()
    return r


def errorResponse(status, body):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    r.text = json.dumps(body)
    r.raise_for_status.side_effect = requests.HTTPError(response=r)
    return r


class TestWork(unittest.TestCase):

    def setUp(self):
        # Work in a temp dir so the repo's jsons/ folder is never touched.
        self.tmp = tempfile.mkdtemp()
        self.json_folder = os.path.join(self.tmp, "jsons")
        os.makedirs(self.json_folder)
        self.config = {
            "sgHost": "http://localhost",
            "sgPort": "4984",
            "sgAdminPort": "4985",
            "sgDb": "sync_gateway",
            "sgDbScope": "_default",
            "sgDbCollection": "_default",
            "sgTestUsers": [
                {"userName": "bob", "password": "12345", "sgSession": ""}
            ],
            "sgAdminUser": "Administrator",
            "sgAdminPassword": "password",
            "jsonFolder": self.json_folder,
            "logPathToWriteTo": os.path.join(self.tmp, "sync_gateway_log"),
            "debug": False,
            "operations": [],
        }
        self.config_file = os.path.join(self.tmp, "config.json")
        self.writeConfig()
        # A stale _rev in the input file must never be sent to SG 4.x.
        self.sample_doc = {"_id": "foo", "channels": ["bob"], "_rev": "9-x"}
        with open(os.path.join(self.json_folder, "foo.json"), "w") as f:
            json.dump(self.sample_doc, f)
        self.work = Work(self.config_file)
        self.bob = HTTPBasicAuth("bob", "12345")
        self.admin = HTTPBasicAuth("Administrator", "password")

    def tearDown(self):
        self.work.closeLogFile()
        shutil.rmtree(self.tmp)

    def writeConfig(self):
        with open(self.config_file, "w") as f:
            json.dump(self.config, f)

    def useOperations(self, ops, **overrides):
        self.work.closeLogFile()
        self.config["operations"] = ops
        self.config.update(overrides)
        self.writeConfig()
        self.work = Work(self.config_file)

    # --- helpers ------------------------------------------------------
    def test_encodeCv(self):
        self.assertEqual(encodeCv(CV1), CV1_ENC)
        self.assertEqual(encodeCv("1@a/b"), "1%40a%2Fb")

    def test_staleCv_keeps_source(self):
        self.assertEqual(staleCv(CV1),
                         "0000000000000001@+RTUz3ZWvU8ktL6AuG0csA")
        self.assertNotEqual(staleCv(CV1), CV1)

    def test_parseOperation(self):
        p = Work.parseOperation
        self.assertEqual(p("GET"), ("GET", False, ""))
        self.assertEqual(p("PUT_ADMIN"), ("PUT", True, ""))
        self.assertEqual(p("CHANGES:bob,water"),
                         ("CHANGES", False, "bob,water"))
        self.assertEqual(p("CHANGES_ADMIN:bob"), ("CHANGES", True, "bob"))
        self.assertEqual(p("GET_RAW"), ("GET_RAW", False, ""))

    def test_constructDbUrl(self):
        self.assertEqual(self.work.constructDbUrl(), "sync_gateway")
        self.work.sgDbScope = "scope1"
        self.work.sgDbCollection = "collection1"
        self.assertEqual(self.work.constructDbUrl(),
                         "sync_gateway.scope1.collection1")

    def test_docUrl_encodes_id(self):
        self.assertEqual(self.work.docUrl("job:1"),
                         "http://localhost:4984/sync_gateway/job%3A1")

    # --- http ---------------------------------------------------------
    @patch("requests.request")
    def test_httpRequest_success(self, mock_request):
        mock_request.return_value = okResponse({"_id": "foo", "_cv": CV1})
        url = "http://localhost:4984/sync_gateway/foo"
        result = self.work.httpRequest("GET", url, userName="bob",
                                       password="12345")
        self.assertEqual(result, {"_id": "foo", "_cv": CV1})
        self.assertIsNone(self.work.lastError)
        mock_request.assert_called_once_with(
            "GET", url, json=None, headers=JSON_HDR, auth=self.bob)

    @patch("requests.request")
    def test_httpRequest_error_keeps_status_and_reason(self, mock_request):
        mock_request.return_value = errorResponse(
            403, {"error": "Forbidden", "reason": "sg missing role"})
        result = self.work.httpRequest("GET", "http://x:4984/db/foo")
        self.assertIsNone(result)
        self.assertEqual(self.work.lastError, {
            "status": 403, "error": "Forbidden", "reason": "sg missing role"})

    @patch("requests.request")
    def test_getChangesFeed_uses_keyspace_and_cv(self, mock_request):
        mock_request.return_value = okResponse(
            {"results": [], "last_seq": "1"})
        self.work.sgDbScope, self.work.sgDbCollection = "s", "c"
        self.work.getChangesFeed(userName="bob", password="12345",
                                 channels="bob,water")
        mock_request.assert_called_once_with(
            "GET",
            "http://localhost:4984/sync_gateway.s.c/_changes?"
            "filter=sync_gateway/bychannel&channels=bob,water&version_type=cv",
            json=None, headers=JSON_HDR, auth=self.bob)

    @patch("requests.request")
    def test_postPurge_uses_keyspace(self, mock_request):
        mock_request.return_value = okResponse({"purged": {"foo": ["*"]}})
        self.work.sgDbScope, self.work.sgDbCollection = "s", "c"
        result = self.work.postPurge(["foo"])
        self.assertEqual(result, {"purged": {"foo": ["*"]}})
        mock_request.assert_called_once_with(
            "POST", "http://localhost:4985/sync_gateway.s.c/_purge",
            json={"foo": ["*"]}, headers=JSON_HDR, auth=self.admin)

    @patch("requests.request")
    def test_checkServerVersion(self, mock_request):
        mock_request.return_value = okResponse({"vendor": {"version": "4.1"}})
        self.assertEqual(self.work.checkServerVersion(), "4.1")

    # --- operations ---------------------------------------------------
    @patch("requests.request")
    def test_put_sends_current_cv_and_strips_rev(self, mock_request):
        mock_request.side_effect = [
            okResponse({"_id": "foo", "_rev": "1-a", "_cv": CV1}),
            okResponse({"id": "foo", "ok": True, "rev": "2-b", "cv": CV2}),
        ]
        self.useOperations(["PUT"])
        self.work.openJsonFolder()
        mock_request.assert_called_with(
            "PUT", "http://localhost:4984/sync_gateway/foo",
            json={"_id": "foo", "channels": ["bob"], "_cv": CV1,
                  "dateTimeStamp": ANY},
            headers=JSON_HDR, auth=self.bob)

    @patch("requests.request")
    def test_put_new_doc_has_no_cv(self, mock_request):
        mock_request.side_effect = [
            errorResponse(404, {"error": "not_found", "reason": "missing"}),
            okResponse({"id": "foo", "ok": True, "rev": "1-a", "cv": CV1}),
        ]
        self.useOperations(["PUT"])
        self.work.openJsonFolder()
        sent = mock_request.call_args.kwargs["json"]
        self.assertNotIn("_cv", sent)
        self.assertNotIn("_rev", sent)

    @patch("requests.request")
    def test_put_does_not_mutate_input_between_users(self, mock_request):
        mock_request.side_effect = [
            okResponse({"_cv": CV1}),
            okResponse({"ok": True, "cv": CV2}),
            errorResponse(404, {"error": "not_found"}),
            okResponse({"ok": True, "cv": CV1}),
        ]
        users = [{"userName": "bob", "password": "12345", "sgSession": ""},
                 {"userName": "amy", "password": "pw", "sgSession": ""}]
        self.useOperations(["PUT"], sgTestUsers=users)
        self.work.openJsonFolder()
        amy_put = mock_request.call_args_list[3]
        self.assertNotIn("_cv", amy_put.kwargs["json"])

    @patch("requests.request")
    def test_put_falls_back_to_admin_read_on_403(self, mock_request):
        mock_request.side_effect = [
            errorResponse(403, {"error": "Forbidden"}),
            okResponse({"_cv": CV1}),
            okResponse({"ok": True, "cv": CV2}),
        ]
        self.useOperations(["PUT"])
        self.work.openJsonFolder()
        self.assertEqual(mock_request.call_args_list[1], call(
            "GET", "http://localhost:4985/sync_gateway/foo",
            json=None, headers=JSON_HDR, auth=self.admin))
        put = mock_request.call_args_list[2]
        self.assertEqual(put.kwargs["json"]["_cv"], CV1)
        self.assertEqual(put.kwargs["auth"], self.bob)

    @patch("requests.request")
    def test_delete_url_encodes_cv(self, mock_request):
        mock_request.side_effect = [
            okResponse({"_cv": CV1}),
            okResponse({"id": "foo", "ok": True, "cv": CV2}),
        ]
        self.useOperations(["DELETE_ADMIN"])
        self.work.openJsonFolder()
        mock_request.assert_called_with(
            "DELETE", f"http://localhost:4985/sync_gateway/foo?rev={CV1_ENC}",
            json=None, headers=JSON_HDR, auth=self.admin)

    @patch("requests.request")
    def test_conflict_sends_stale_cv_and_expects_409(self, mock_request):
        mock_request.side_effect = [
            okResponse({"_cv": CV1}),
            errorResponse(409, {"error": "conflict"}),
        ]
        self.useOperations(["CONFLICT"])
        with self.assertLogs(level="INFO") as logs:
            self.work.openJsonFolder()
        self.assertEqual(mock_request.call_args.kwargs["json"]["_cv"],
                         staleCv(CV1))
        self.assertTrue(
            any("[success] - [CONFLICT]" in m for m in logs.output))

    @patch("requests.request")
    def test_failed_put_logs_sync_function_reason(self, mock_request):
        mock_request.side_effect = [
            okResponse({"_cv": CV1}),
            errorResponse(403, {"error": "Forbidden",
                                "reason": "sg admin required"}),
        ]
        self.useOperations(["PUT"])
        with self.assertLogs(level="INFO") as logs:
            self.work.openJsonFolder()
        line = [m for m in logs.output if "[PUT]" in m][0]
        self.assertIn("[failed] - [PUT] - [bob]", line)
        self.assertIn('"status": 403', line)
        self.assertIn("sg admin required", line)

    @patch("requests.request")
    def test_get_raw_logs_vv(self, mock_request):
        vv = {"src": "+RTUz3ZWvU8ktL6AuG0csA", "ver": "0x00009a9919e1e818"}
        mock_request.return_value = okResponse(
            {"channels": ["bob"], "_xattrs": {"_vv": vv, "_sync": {}}})
        self.useOperations(["GET_RAW"])
        with self.assertLogs(level="INFO") as logs:
            self.work.openJsonFolder()
        self.assertTrue(any(f"_vv:{json.dumps(vv)}" in m for m in logs.output))
        mock_request.assert_called_once_with(
            "GET", "http://localhost:4985/sync_gateway/_raw/foo",
            json=None, headers=JSON_HDR, auth=self.admin)

    @patch("requests.request")
    def test_admin_only_ops_run_once_per_doc(self, mock_request):
        mock_request.return_value = okResponse({"purged": {"foo": ["*"]}})
        users = [{"userName": "bob", "password": "12345", "sgSession": ""},
                 {"userName": "amy", "password": "pw", "sgSession": ""}]
        self.useOperations(["PURGE"], sgTestUsers=users)
        self.work.openJsonFolder()
        self.assertEqual(mock_request.call_count, 1)

    @patch("time.sleep")
    @patch("requests.request")
    def test_sleep(self, mock_request, mock_sleep):
        self.useOperations(["SLEEP:3", "SLEEP"])
        self.work.openJsonFolder()
        mock_sleep.assert_has_calls([call(3), call(1)])
        mock_request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
