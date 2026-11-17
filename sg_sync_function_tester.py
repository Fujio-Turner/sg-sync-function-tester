"""Sync Gateway 4.x Sync Function tester.

Runs a list of operations (PUT, GET, DELETE, CHANGES, ...) against Sync
Gateway for every JSON document in a folder, as one or more users, and logs
whether each one succeeded or was rejected.

This branch targets Sync Gateway 4.x and uses **version vectors**: documents
are versioned by their Current Version (CV, ``_cv``), e.g.
``18e8e11501350000@+RTUz3ZWvU8ktL6AuG0csA``. For Sync Gateway 3.x (revision
tree ``_rev`` IDs) use the ``sg-3.x-rest`` branch.
"""
import copy
import json
import logging
import os
import sys
import time
from datetime import datetime
from urllib.parse import quote, urlencode

import requests
from requests.auth import HTTPBasicAuth

# Fields that identify a document version. They are stripped from the input
# JSON before every write so a stale value in a test file never causes a
# 409/400; the tester always supplies the live CV itself.
VERSION_FIELDS = ("_rev", "_cv", "_revisions")

# The CV used by the CONFLICT operation: a well-formed but never-current
# version, so Sync Gateway must reject the write with 409.
STALE_CV_VERSION = "0000000000000001"


def encodeCv(cv):
    """URL-encode a CV for use in a query string.

    CVs contain '@' and base64 characters ('+', '/'). An unencoded '+'
    is read as a space and Sync Gateway rejects the request with 400.
    """
    return quote(cv, safe="")


def staleCv(cv):
    """Return a CV with the same source but a version that can't be current."""
    source = cv.split("@", 1)[1] if cv and "@" in cv else "stale"
    return f"{STALE_CV_VERSION}@{source}"


class Work():

    # Default configuration values
    debug = False
    sgHost = "http://localhost"
    sgPort = "4984"
    sgAdminPort = "4985"
    sgDb = "sync_gateway"
    sgDbScope = "_default"
    sgDbCollection = "_default"
    sgTestUsers = [{"userName": "bob", "password": "12345", "sgSession": ""}]
    sgAdminUser = ""
    sgAdminPassword = ""
    logPathToWriteTo = "sync_gateway_log"
    jsonFolder = "jsons"
    operations = []

    def __init__(self, config_file):
        self.readConfig(config_file)
        self.setupLogging()
        # Status code and body of the most recent failed request, so the
        # log shows *why* it failed (403 from the Sync Function, 409, ...).
        self.lastError = None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def readConfig(self, config_file):
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            raise Exception(f"Configuration file '{config_file}' not found.")
        except json.JSONDecodeError:
            raise Exception(f"Configuration file '{config_file}' "
                            f"is not valid JSON.")

        self.sgLogName = config.get("logPathToWriteTo", self.logPathToWriteTo)
        self.sgHost = config.get("sgHost", self.sgHost)
        self.sgPort = config.get("sgPort", self.sgPort)
        self.sgAdminPort = config.get("sgAdminPort", self.sgAdminPort)
        self.sgDb = config.get("sgDb", self.sgDb)
        self.sgDbScope = config.get("sgDbScope", self.sgDbScope)
        self.sgDbCollection = config.get("sgDbCollection", self.sgDbCollection)
        self.sgTestUsers = config.get("sgTestUsers", self.sgTestUsers)
        self.sgAdminUser = config.get("sgAdminUser", self.sgAdminUser)
        self.sgAdminPassword = config.get(
            "sgAdminPassword", self.sgAdminPassword
        )
        self.jsonFolder = config.get("jsonFolder", self.jsonFolder)
        self.debug = config.get("debug", self.debug)
        self.operations = config.get("operations", self.operations)

    def setupLogging(self):
        """Log to a timestamped file with ISO 8601 timestamps."""
        # No ':' in the filename so it is valid on macOS/Windows.
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{self.sgLogName}_{timestamp}.log"

        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG if self.debug else logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s",
            datefmt='%Y-%m-%dT%H:%M:%S'
        )
        file_handler = logging.FileHandler(log_filename)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)
        self.file_handler = file_handler

    def closeLogFile(self):
        if getattr(self, 'file_handler', None):
            self.file_handler.close()
            self.logger.removeHandler(self.file_handler)

    def checkServerVersion(self):
        """Warn if the target Sync Gateway is older than 4.x.

        Returns the version string, or None if it can't be read (the public
        port can hide it with ``hide_product_version``).
        """
        if self.sgAdminUser:
            url = f"{self.sgHost}:{self.sgAdminPort}/"
            root = self.httpRequest("GET", url, is_admin=True)
        else:
            root = self.httpRequest("GET", f"{self.sgHost}:{self.sgPort}/")
        version = None
        if root:
            version = (root.get("vendor") or {}).get("version")
        if not version:
            self.logger.warning(
                "[info] - Could not read the Sync Gateway version; "
                "assuming 4.x (version vectors)."
            )
            return None
        try:
            major = int(str(version).split(".")[0])
        except ValueError:
            major = None
        if major is not None and major < 4:
            self.logger.warning(
                f"[info] - Sync Gateway {version} does not support version "
                f"vectors. Use the sg-3.x-rest branch of this tester."
            )
        else:
            self.logger.info(f"[info] - Sync Gateway version {version}")
        return version

    # ------------------------------------------------------------------
    # URLs
    # ------------------------------------------------------------------
    def constructDbUrl(self):
        """Return the keyspace: ``db`` or ``db.scope.collection``."""
        if self.sgDbScope == "_default" and self.sgDbCollection == "_default":
            return self.sgDb
        return f"{self.sgDb}.{self.sgDbScope}.{self.sgDbCollection}"

    def keyspaceUrl(self, is_admin=False):
        port = self.sgAdminPort if is_admin else self.sgPort
        return f"{self.sgHost}:{port}/{self.constructDbUrl()}"

    def docUrl(self, doc_id, is_admin=False):
        return f"{self.keyspaceUrl(is_admin)}/{quote(doc_id, safe='')}"

    def changesUrl(self, channels=None, is_admin=False):
        params = {}
        if channels:
            params["filter"] = "sync_gateway/bychannel"
            params["channels"] = channels
        params["version_type"] = "cv"
        return (f"{self.keyspaceUrl(is_admin)}/_changes?"
                f"{urlencode(params, safe='/,')}")

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def httpRequest(
        self,
        method,
        url,
        json_data=None,
        userName="",
        password="",
        session="",
        is_admin=False,
        headers=None,
    ):
        """Send a request; return the JSON body on 2xx, else None.

        On failure ``self.lastError`` holds ``{"status": code, ...body}``.
        """
        self.lastError = None
        try:
            req_headers = {"Content-Type": "application/json"}
            if headers:
                req_headers.update(headers)
            if session:
                req_headers["Cookie"] = f"SyncGatewaySession={session}"

            if is_admin:
                auth = HTTPBasicAuth(self.sgAdminUser, self.sgAdminPassword)
                url = url.replace(f":{self.sgPort}/", f":{self.sgAdminPort}/")
            else:
                auth = (HTTPBasicAuth(userName, password)
                        if userName and password else None)

            response = requests.request(
                method, url, json=json_data, headers=req_headers, auth=auth
            )
            response.raise_for_status()
            return response.json() if response.text else None
        except requests.HTTPError as e:
            self.lastError = self._errorBody(e.response)
            if self.debug:
                self.logger.error(f"Error in HTTP {method} {url}: {e}")
        except requests.RequestException as e:
            self.lastError = {"error": type(e).__name__, "reason": str(e)}
            if self.debug:
                self.logger.error(f"Error in HTTP {method} {url}: {e}")
        return None

    @staticmethod
    def _errorBody(response):
        status = getattr(response, "status_code", None)
        try:
            body = response.json()
            if not isinstance(body, dict):
                body = {"body": body}
        except (ValueError, AttributeError):
            body = {}
        return {"status": status, **body}

    def _resultText(self, result):
        """What goes after the final ' - ' on a log line."""
        if result is not None:
            return json.dumps(result)
        if self.lastError:
            return json.dumps(self.lastError)
        return "null"

    def getChangesFeed(
        self, userName="", password="", session="",
        is_admin=False, channels=None
    ):
        return self.httpRequest(
            "GET", self.changesUrl(channels, is_admin),
            userName=userName, password=password,
            session=session, is_admin=is_admin
        )

    def postPurge(self, docIds):
        url = f"{self.keyspaceUrl(is_admin=True)}/_purge"
        purgeData = {docId: ["*"] for docId in docIds}
        return self.httpRequest(
            "POST", url, json_data=purgeData, is_admin=True
        )

    def getCurrentVersion(self, doc_id, user, is_admin):
        """Return the document's current CV, or None if it doesn't exist.

        Reads as the same user first. If that user can write but not read
        the document (403), falls back to the admin port when admin
        credentials are configured, so the write still gets tested.
        """
        doc = self.httpRequest(
            "GET", self.docUrl(doc_id, is_admin),
            userName=user["userName"], password=user["password"],
            session=user.get("sgSession", ""), is_admin=is_admin
        )
        if doc is None and not is_admin and self.sgAdminUser \
                and (self.lastError or {}).get("status") == 403:
            self.logger.info(
                f"[info] - [{user['userName']}] - read of [{doc_id}] denied; "
                f"reading current CV via admin port"
            )
            doc = self.httpRequest(
                "GET", self.docUrl(doc_id, True), is_admin=True
            )
        return doc.get("_cv") if doc else None

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------
    def _who(self, user, is_admin):
        return "Admin" if is_admin else user["userName"]

    def _auth(self, user):
        return {
            "userName": user["userName"],
            "password": user["password"],
            "session": user.get("sgSession", ""),
        }

    def opGet(self, doc_id, doc, user, is_admin, params):
        result = self.httpRequest(
            "GET", self.docUrl(doc_id, is_admin),
            is_admin=is_admin, **self._auth(user)
        )
        status = "success" if result else "failed"
        self.logger.info(
            f"[{status}] - [GET] - [{self._who(user, is_admin)}] - "
            f"GET result for [{doc_id}] - {self._resultText(result)}"
        )

    def _put(self, doc_id, doc, user, is_admin, cv):
        body = {k: v for k, v in copy.deepcopy(doc).items()
                if k not in VERSION_FIELDS}
        body["dateTimeStamp"] = datetime.now().isoformat()
        if cv:
            body["_cv"] = cv
        return self.httpRequest(
            "PUT", self.docUrl(doc_id, is_admin), json_data=body,
            is_admin=is_admin, **self._auth(user)
        )

    def opPut(self, doc_id, doc, user, is_admin, params):
        cv = self.getCurrentVersion(doc_id, user, is_admin)
        result = self._put(doc_id, doc, user, is_admin, cv)
        status = "success" if result and result.get("ok") else "failed"
        self.logger.info(
            f"[{status}] - [PUT] - [{self._who(user, is_admin)}] - "
            f"PUT result for [{doc_id}] - {self._resultText(result)}"
        )

    def opConflict(self, doc_id, doc, user, is_admin, params):
        """PUT with a stale CV. Success means Sync Gateway returned 409."""
        cv = self.getCurrentVersion(doc_id, user, is_admin)
        if not cv:
            self.logger.warning(
                f"[failed] - [CONFLICT] - [{self._who(user, is_admin)}] - "
                f"Unable to test conflict on [{doc_id}] - Document not found"
            )
            return
        result = self._put(doc_id, doc, user, is_admin, staleCv(cv))
        got409 = result is None and (self.lastError or {}).get("status") == 409
        status = "success" if got409 else "failed"
        self.logger.info(
            f"[{status}] - [CONFLICT] - [{self._who(user, is_admin)}] - "
            f"CONFLICT result for [{doc_id}] (expect 409) - "
            f"{self._resultText(result)}"
        )

    def opDelete(self, doc_id, doc, user, is_admin, params):
        who = self._who(user, is_admin)
        cv = self.getCurrentVersion(doc_id, user, is_admin)
        if not cv:
            self.logger.warning(
                f"[failed] - [DELETE] - [{who}] - "
                f"Unable to delete [{doc_id}] - "
                f"Document not found or no version available"
            )
            return
        result = self.httpRequest(
            "DELETE", f"{self.docUrl(doc_id, is_admin)}?rev={encodeCv(cv)}",
            is_admin=is_admin, **self._auth(user)
        )
        status = "success" if result and result.get("ok") else "failed"
        self.logger.info(
            f"[{status}] - [DELETE] - [{who}] - "
            f"DELETE result for [{doc_id}] - {self._resultText(result)}"
        )

    def opChanges(self, doc_id, doc, user, is_admin, params):
        channels = params or None
        result = self.getChangesFeed(
            is_admin=is_admin, channels=channels, **self._auth(user)
        )
        status = "success" if result else "failed"
        rows = len(result.get("results", [])) if result else 0
        self.logger.info(
            f"[{status}] - [CHANGES] - [{self._who(user, is_admin)}] - "
            f"Changes feed result for [{doc_id}], "
            f"channelFilter:{'true' if channels else 'false'}, "
            f"channels:{channels or 'None'}, "
            f"rows: {rows} - {self._resultText(result)}"
        )

    def opPurge(self, doc_id, doc, user, is_admin, params):
        result = self.postPurge([doc_id])
        status = "success" if result and result.get("purged") else "failed"
        self.logger.info(
            f"[{status}] - [PURGE] - [Admin] - "
            f"Purge result for [{doc_id}] - {self._resultText(result)}"
        )

    def opGetRaw(self, doc_id, doc, user, is_admin, params):
        url = (f"{self.keyspaceUrl(is_admin=True)}/_raw/"
               f"{quote(doc_id, safe='')}")
        result = self.httpRequest("GET", url, is_admin=True)
        status = "success" if result else "failed"
        # The version vector lives in the _vv system xattr
        # (src = source ID, ver = version, plus pv/mv when present).
        vv = ((result or {}).get("_xattrs") or {}).get("_vv")
        self.logger.info(
            f"[{status}] - [GET_RAW] - [Admin] - "
            f"GET_RAW result for [{doc_id}], "
            f"_vv:{json.dumps(vv)} - {self._resultText(result)}"
        )

    OPERATIONS = {
        "GET": opGet,
        "PUT": opPut,
        "DELETE": opDelete,
        "CHANGES": opChanges,
        "CONFLICT": opConflict,
        "PURGE": opPurge,
        "GET_RAW": opGetRaw,
    }
    # Operations that always run once per document as admin,
    # rather than once per test user.
    ADMIN_ONLY = {"PURGE", "GET_RAW"}

    @staticmethod
    def parseOperation(operation):
        """Split e.g. 'CHANGES_ADMIN:bob' into ('CHANGES', True, 'bob')."""
        name, _, params = operation.partition(":")
        is_admin = False
        if name.endswith("_ADMIN"):
            name, is_admin = name[:-len("_ADMIN")], True
        return name, is_admin, params

    def sleep(self, operation):
        sleep_time = 1
        if ":" in operation:
            try:
                sleep_time = int(operation.split(":", 1)[1])
            except ValueError:
                self.logger.warning(
                    f"Invalid sleep time format: {operation}. "
                    f"Using default 1 second."
                )
        self.logger.info(
            f"[success] - [SLEEP] - Sleeping for {sleep_time} seconds"
        )
        time.sleep(sleep_time)

    def runDoc(self, doc):
        doc_id = doc.get("_id")
        if not doc_id:
            return
        for operation in self.operations:
            if operation.startswith("SLEEP"):
                self.sleep(operation)
                continue
            name, is_admin, params = self.parseOperation(operation)
            handler = self.OPERATIONS.get(name)
            if handler is None:
                self.logger.warning(
                    f"[failed] - Unknown operation: {operation}"
                )
                continue
            users = self.sgTestUsers[:1] if name in self.ADMIN_ONLY \
                else self.sgTestUsers
            for user in users:
                try:
                    handler(self, doc_id, doc, user, is_admin, params)
                except Exception as e:  # keep going on unexpected errors
                    self.logger.error(
                        f"[failed] - [{name}] - "
                        f"[{self._who(user, is_admin)}] - "
                        f"Error for [{doc_id}] - {e}"
                    )

    def openJsonFolder(self):
        for filename in sorted(os.listdir(self.jsonFolder)):
            if filename.endswith(".json"):
                with open(os.path.join(self.jsonFolder, filename), "r") as f:
                    self.runDoc(json.load(f))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 sg_sync_function_tester.py <config_file>")
        sys.exit(1)

    workAll = Work(sys.argv[1])
    workAll.checkServerVersion()
    workAll.openJsonFolder()
    workAll.closeLogFile()
