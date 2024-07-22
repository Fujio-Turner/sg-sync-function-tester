import json
import os
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import logging
import sys

class WORK:
    # Default configuration values
    debug = False
    sgHost = "http://localhost"
    sgPort = "4984"
    sgAdminPort = "4985"
    sgDb = "sync_gateway"
    sgTestUsers = [{"userName": "bob", "password": "12345", "sgSession": ""}]
    sgAdminUser = ""
    sgAdminPassword = ""
    logPathToWriteTo = ""
    jsonFolder = "jsons"
    operations = []

    def __init__(self, config_file):
        self.readConfig(config_file)
        self.setupLogging()

    def readConfig(self, config_file):
        with open(config_file, "r") as f:
            config = json.load(f)
        self.sgLogName = config.get("logPathToWriteTo", self.logPathToWriteTo)
        self.sgHost = config.get("sgHost", self.sgHost)
        self.sgPort = config.get("sgPort", self.sgPort)
        self.sgAdminPort = config.get("sgAdminPort", self.sgAdminPort)
        self.sgDb = config.get("sgDb", self.sgDb)
        self.sgTestUsers = config.get("sgTestUsers", self.sgTestUsers)
        self.sgAdminUser = config.get("sgAdminUser", self.sgAdminUser)
        self.sgAdminPassword = config.get("sgAdminPassword", self.sgAdminPassword)
        self.jsonFolder = config.get("jsonFolder", self.jsonFolder)
        self.debug = config.get("debug", self.debug)
        self.operations = config.get("operations", self.operations)

    def setupLogging(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{self.sgLogName}_{timestamp}.log"
        logging.basicConfig(
            filename=log_filename,
            level=logging.DEBUG if self.debug else logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger()

    def httpRequest(self, method, url, json_data=None, userName="", password="", session="", is_admin=False):
        try:
            headers = {"Content-Type": "application/json"}
            if session:
                headers["Cookie"] = f"SyncGatewaySession={session}"
            
            if is_admin:
                auth = HTTPBasicAuth(self.sgAdminUser, self.sgAdminPassword)
                url = url.replace(f":{self.sgPort}/", f":{self.sgAdminPort}/")
            else:
                auth = HTTPBasicAuth(userName, password) if userName and password else None

            response = requests.request(method, url, json=json_data, headers=headers, auth=auth)
            response.raise_for_status()
            return response.json() if response.text else None
        except requests.RequestException as e:
            self.logger.error(f"Error in HTTP {method}: {e}")
            return None

    def getChangesFeed(self, userName="", password="", session="", is_admin=False):
        sgUrl = f"{self.sgHost}:{self.sgPort}/{self.sgDb}/_changes"
        return self.httpRequest("GET", sgUrl, userName=userName, password=password, session=session, is_admin=is_admin)

    def postPurge(self, docIds):
        sgUrl = f"{self.sgHost}:{self.sgAdminPort}/{self.sgDb}/_purge"
        purgeData = {docId: ["*"] for docId in docIds}
        return self.httpRequest("POST", sgUrl, json_data=purgeData, is_admin=True)

    def openJsonFolder(self):
        json_folder = self.jsonFolder
        processed_docs = []
        for filename in os.listdir(json_folder):
            if filename.endswith(".json"):
                with open(os.path.join(json_folder, filename), "r") as f:
                    json_data = json.load(f)
                doc_id = json_data.get("_id")
                if doc_id:
                    processed_docs.append(doc_id)
                    rev = None  # Initialize rev to None
                    for operation in self.operations:
                        is_admin = operation.endswith("_ADMIN")
                        op = operation.replace("_ADMIN", "")
                        
                        for user in self.sgTestUsers:
                            sgUrl = f"{self.sgHost}:{self.sgPort}/{self.sgDb}/{doc_id}"
                            userName = user["userName"]
                            password = user["password"]
                            session = user["sgSession"]

                            if op == "GET":
                                self.logger.info(f"User: {'Admin' if is_admin else userName} trying to GET: {doc_id}")
                                result = self.httpRequest("GET", sgUrl, userName=userName, password=password, session=session, is_admin=is_admin)
                                self.logger.info(f"GET result for {doc_id}: {result}")
                                if result:
                                    rev = result.get('_rev')

                            elif op == "PUT":
                                json_data['dateTimeStamp'] = datetime.now().isoformat()
                                result = self.httpRequest("PUT", sgUrl, json_data=json_data, userName=userName, password=password, session=session, is_admin=is_admin)
                                self.logger.info(f"PUT result for {doc_id}: {result}")
                                if result and result.get("rev"):
                                    rev = result["rev"]  # Update rev after PUT

                            elif op == "DELETE":
                                if rev:
                                    delete_url = f"{self.sgHost}:{self.sgPort}/{self.sgDb}/{doc_id}?rev={rev}"
                                    result = self.httpRequest("DELETE", delete_url, userName=userName, password=password, session=session, is_admin=is_admin)
                                    self.logger.info(f"DELETE result for {doc_id}: {result}")
                                else:
                                    self.logger.warning(f"Unable to delete {doc_id}: No revision available")

                            elif op == "CHANGES":
                                result = self.getChangesFeed(userName=userName, password=password, session=session, is_admin=is_admin)
                                self.logger.info(f"Changes feed result for user {'Admin' if is_admin else userName}: {result}")

                            elif op == "PURGE":
                                result = self.postPurge([doc_id])
                                self.logger.info(f"Purge result: {result}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 sg-sync-function-tester.py <config_file>")
        sys.exit(1)

    config_file = sys.argv[1]
    work = WORK(config_file)
    work.openJsonFolder()