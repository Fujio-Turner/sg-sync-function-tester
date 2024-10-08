import unittest
from unittest.mock import patch, MagicMock
import json
import os
from requests.auth import HTTPBasicAuth
from sg_sync_function_tester import Work


class TestWORK(unittest.TestCase):

    def setUp(self):
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
            "jsonFolder": "jsons",
            "logPathToWriteTo": "sync_gateway_log",
            "debug": False,
            "operations": [
                "GET", "PUT", "DELETE", "CHANGES", "GET_ADMIN", "PUT_ADMIN",
                "DELETE_ADMIN", "CHANGES_ADMIN:bob", "SLEEP:3", "GET_RAW",
                "PURGE"
            ]
        }

        self.config_file = 'test_config.json'
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f)

        self.json_folder = 'jsons'
        os.makedirs(self.json_folder, exist_ok=True)
        self.sample_doc = {"_id": "foo", "channels": ["bob"]}
        with open(os.path.join(self.json_folder, 'foo.json'), 'w') as f:
            json.dump(self.sample_doc, f)
        self.work = Work(self.config_file)

    def tearDown(self):
        os.remove(self.config_file)
        for filename in os.listdir(self.json_folder):
            file_path = os.path.join(self.json_folder, filename)
            os.remove(file_path)
        os.rmdir(self.json_folder)
        self.work.closeLogFile()

    @patch('requests.request')
    def test_httpRequest_get(self, mock_request):
        mock_response = MagicMock()
        mock_response.json.return_value = self.sample_doc
        mock_response.text = json.dumps(self.sample_doc)
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        url = f"{self.work.sgHost}:{self.work.sgPort}/{self.work.constructDbUrl()}/foo"
        result = self.work.httpRequest("GET", url, userName="bob", password="12345")

        self.assertEqual(result, self.sample_doc)
        mock_request.assert_called_once_with(
            "GET", url,
            json=None,
            headers={'Content-Type': 'application/json'},
            auth=HTTPBasicAuth("bob", "12345")
        )

    @patch('requests.request')
    def test_httpRequest_put(self, mock_request):
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "id": "foo", "rev": "1-a"}
        mock_response.text = json.dumps({"ok": True, "id": "foo", "rev": "1-a"})
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        url = (f"{self.work.sgHost}:{self.work.sgPort}/"
               f"{self.work.constructDbUrl()}/foo")
        result = self.work.httpRequest("PUT", url, json_data=self.sample_doc,
                                       userName="bob", password="12345")

        self.assertEqual(result, {"ok": True, "id": "foo", "rev": "1-a"})
        mock_request.assert_called_once_with(
            "PUT", url,
            json=self.sample_doc,
            headers={'Content-Type': 'application/json'},
            auth=HTTPBasicAuth("bob", "12345")
        )

    @patch('requests.request')
    def test_getChangesFeed(self, mock_request):
        changes_feed = {
            "results": [{"seq": 1, "id": "foo", "changes": [{"rev": "1-a"}]}],
            "last_seq": "1"
        }
        mock_response = MagicMock()
        mock_response.json.return_value = changes_feed
        mock_response.text = json.dumps(changes_feed)
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.work.getChangesFeed(
            userName="bob", password="12345", channels="bob"
        )

        self.assertEqual(result, changes_feed)
        url = (f"{self.work.sgHost}:{self.work.sgPort}/{self.work.constructDbUrl()}/"
               f"_changes?filter=sync_gateway/bychannel&channels=bob")
        mock_request.assert_called_once_with(
            "GET", url,
            json=None, headers={'Content-Type': 'application/json'},
            auth=HTTPBasicAuth("bob", "12345")
            )

    @patch('requests.request')
    def test_postPurge(self, mock_request):
        purge_response = {"purged": {"foo": ["*"]}}
        mock_response = MagicMock()
        mock_response.json.return_value = purge_response
        mock_response.text = json.dumps(purge_response)
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        result = self.work.postPurge(["foo"])

        self.assertEqual(result, purge_response)
        url = (f"{self.work.sgHost}:{self.work.sgAdminPort}/"
               f"{self.work.constructDbUrl()}/_purge")
        purge_data = {"foo": ["*"]}
        mock_request.assert_called_once_with(
            "POST", url,
            json=purge_data,
            headers={'Content-Type': 'application/json'},
            auth=HTTPBasicAuth(self.work.sgAdminUser, self.work.sgAdminPassword)
        )

    @patch('requests.request')
    def test_openJsonFolder(self, mock_request):
        def side_effect(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            if args[0] == "GET":
                mock_response.json.return_value = {
                    "_id": "foo", "_rev": "1-a", "channels": ["bob"]
                }
            elif args[0] == "PUT":
                mock_response.json.return_value = {
                    "ok": True, "id": "foo", "rev": "1-a"
                }
            elif args[0] == "DELETE":
                mock_response.json.return_value = {"ok": True}
            elif args[0] == "POST" and "/_purge" in args[1]:
                mock_response.json.return_value = {"purged": {"foo": ["*"]}}
            else:
                mock_response.json.return_value = {}
            mock_response.text = json.dumps(mock_response.json.return_value)
            return mock_response

        mock_request.side_effect = side_effect

        self.work.openJsonFolder()

        sgDbUrl = f"{self.work.sgHost}:{self.work.sgPort}/{self.work.sgDb}"
        sgAdminUrl = f"{self.work.sgHost}:{self.work.sgAdminPort}/{self.work.sgDb}"
        expected_calls = [
            unittest.mock.call(
                "GET", f"{sgDbUrl}/foo",
                json=None, headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth("bob", "12345")
            ),
            unittest.mock.call(
                "PUT", f"{sgDbUrl}/foo",
                json={'_id': 'foo', 'channels': ['bob'],
                      '_rev': '1-a', 'dateTimeStamp': unittest.mock.ANY},
                headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth("bob", "12345")
                ),
            unittest.mock.call(
                "DELETE", f"{sgDbUrl}/foo?rev=1-a",
                json=None, headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth("bob", "12345")
            ),
            unittest.mock.call(
                "GET", f"{sgDbUrl}/_changes",
                json=None, headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth("bob", "12345")
            ),
            unittest.mock.call(
                "GET", f"{sgAdminUrl}/foo",
                json=None, headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth(self.work.sgAdminUser, self.work.sgAdminPassword)
            ),
            unittest.mock.call(
                "PUT", f"{sgAdminUrl}/foo",
                json={'_id': 'foo', 'channels': ['bob'], '_rev': '1-a',
                      'dateTimeStamp': unittest.mock.ANY},
                headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth(self.work.sgAdminUser, self.work.sgAdminPassword)
            ),
            unittest.mock.call(
                "DELETE", f"{sgAdminUrl}/foo?rev=1-a",
                json=None, headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth(self.work.sgAdminUser, self.work.sgAdminPassword)
            ),
            unittest.mock.call(
                "GET",
                f"{sgAdminUrl}/_changes?filter=sync_gateway/bychannel&channels=bob",
                json=None, headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth(self.work.sgAdminUser, self.work.sgAdminPassword)
            ),
            unittest.mock.call(
                "GET", f"{sgAdminUrl}/_raw/foo",
                json=None, headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth(self.work.sgAdminUser, self.work.sgAdminPassword)
            ),
            unittest.mock.call(
                "POST", f"{sgAdminUrl}/_purge",
                json={"foo": ["*"]}, headers={'Content-Type': 'application/json'},
                auth=HTTPBasicAuth(self.work.sgAdminUser, self.work.sgAdminPassword)
            )
        ]
        mock_request.assert_has_calls(expected_calls, any_order=True)

    def test_constructDbUrl(self):
        self.assertEqual(self.work.constructDbUrl(), "sync_gateway")
        self.work.sgDbScope = "scope1"
        self.work.sgDbCollection = "collection1"
        self.assertEqual(
            self.work.constructDbUrl(),
            "sync_gateway.scope1.collection1"
        )


if __name__ == '__main__':
    unittest.main()
