import json
import os
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import logging

class WORK:
    # Default configuration values
    debug = False
    sgHost = "http://localhost"
    sgPort = "4984"
    sgDb = "sync_gateway"
    sgTestUsers = [{"userName": "bob", "password": "12345", "sgSession": ""}]
    logPathToWriteTo = ""
    doGet = True
    doPut = True
    doDelete = True
    doChanges = True  # New flag for changes feed

    def __init__(self, config_file):
        # Initialize the class and read the configuration file
        self.readConfig(config_file)
        # Setup logging
        self.setupLogging()

    def readConfig(self, config_file):
        # Read the configuration from a JSON file
        with open(config_file, "r") as f:
            config = json.load(f)
        # Set class attributes based on the configuration file
        self.sgLogName = config.get("logPathToWriteTo", self.logPathToWriteTo)
        self.sgHost = config.get("sgHost", self.sgHost)
        self.sgPort = config.get("sgPort", self.sgPort)
        self.sgDb = config.get("sgDb", self.sgDb)
        self.sgTestUsers = config.get("sgTestUsers", self.sgTestUsers)
        self.debug = config.get("debug", self.debug)
        self.doGet = config.get("doGet", self.doGet)
        self.doPut = config.get("doPut", self.doPut)
        self.doDelete = config.get("doDelete", self.doDelete)
        self.doChanges = config.get("doChanges", self.doChanges)  # Read changes flag

    def setupLogging(self):
        # Setup logging configuration
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{self.sgLogName}_{timestamp}.log"
        logging.basicConfig(
            filename=log_filename,
            level=logging.DEBUG if self.debug else logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )
        self.logger = logging.getLogger()

    def httpGet(self, url="", userName="", password="", session=""):
        try:
            if session:
                headers = {"Cookie": f"SyncGatewaySession={session}"}
                response = requests.get(url, headers=headers)
            else:
                response = requests.get(url, auth=HTTPBasicAuth(userName, password))
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if isinstance(e, requests.HTTPError) and e.response.status_code == 404:
                # Document doesn't exist
                return None
            self.logger.error(f"Error in HTTP GET: {e}")
            return None

    def httpPut(self, url="", jsonData={}, userName="", password="", session=""):
        try:
            headers = {"Content-Type": "application/json"}
            if session:
                headers["Cookie"] = f"SyncGatewaySession={session}"
                response = requests.put(url, json=jsonData, headers=headers)
            else:
                response = requests.put(url, json=jsonData, headers=headers, auth=HTTPBasicAuth(userName, password))
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            if e.response.status_code == 409:
                self.logger.error(f"HTTP 409 Conflict: Document update conflict for URL {url}")
                return {"error": "conflict", "reason": e.response.text}
            else:
                self.logger.error(f"Error in HTTP PUT: {e}")
                return None
        except requests.RequestException as e:
            self.logger.error(f"Error in HTTP PUT: {e}")
            return None

    def httpDelete(self, url="", docId="", rev="", userName="", password="", session=""):
        try:
            delete_url = f"{url}/{docId}?rev={rev}"
            headers = {}
            if session:
                headers["Cookie"] = f"SyncGatewaySession={session}"
                response = requests.delete(delete_url, headers=headers)
            else:
                response = requests.delete(delete_url, auth=HTTPBasicAuth(userName, password))
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            if e.response.status_code == 403:
                self.logger.error(f"HTTP 403 Forbidden: Unable to delete document {docId}. Reason: {e.response.text}")
                return {"error": "forbidden", "reason": e.response.text}
            else:
                self.logger.error(f"Error in HTTP DELETE: {e}")
                return None
        except requests.RequestException as e:
            self.logger.error(f"Error in HTTP DELETE: {e}")
            return None

    def getChangesFeed(self, userName="", password="", session=""):
        sgUrl = f"{self.sgHost}:{self.sgPort}/{self.sgDb}/_changes"
        request = self.httpGet(sgUrl, userName, password, session)
        return request

    def openJsonFolder(self):
        json_folder = "jsons"
        for filename in os.listdir(json_folder):
            if filename.endswith(".json"):
                file_path = os.path.join(json_folder, filename)
                with open(file_path, "r") as f:
                    json_data = json.load(f)
                doc_id = json_data.get("_id")
                if doc_id:
                    for user in self.sgTestUsers:
                        sgUrl = f"{self.sgHost}:{self.sgPort}/{self.sgDb}/{doc_id}"
                        userName = user["userName"]
                        password = user["password"]
                        session = user["sgSession"]

                        sgGetResult = None
                        if self.doGet:
                            self.logger.info(f"User: {userName} trying to GET: {doc_id} at URL: {sgUrl}")
                            sgGetResult = self.httpGet(sgUrl, userName, password, session)
                            self.logger.info(f"GET result for {doc_id}: {sgGetResult}")

                        putResult = None
                        if self.doPut:
                            if sgGetResult:
                                # Document exists, add timestamp and update
                                sgGetResult['dateTimeStamp'] = datetime.now().isoformat()
                                rev = sgGetResult.get('_rev')
                                if rev:
                                    putUrl = f"{sgUrl}?rev={rev}"
                                else:
                                    putUrl = sgUrl
                                putResult = self.httpPut(putUrl, sgGetResult, userName, password, session)
                            else:
                                # Document doesn't exist or GET wasn't performed, create new
                                json_data['dateTimeStamp'] = datetime.now().isoformat()
                                putResult = self.httpPut(sgUrl, json_data, userName, password, session)

                            self.logger.info(f"PUT result for {doc_id}: {putResult}")

                            # Handle PUT conflicts
                            if putResult and putResult.get("error") == "conflict":
                                self.logger.warning(f"Conflict occurred while updating document {doc_id}. Skipping delete operation.")
                                continue

                        if self.doDelete:
                            # Attempt to delete the document
                            if putResult and putResult.get("rev"):
                                deleteResult = self.httpDelete(f"{self.sgHost}:{self.sgPort}/{self.sgDb}", 
                                                               doc_id, putResult["rev"], 
                                                               userName, password, session)
                                self.logger.info(f"DELETE result for {doc_id}: {deleteResult}")

                                # Handle delete forbidden
                                if deleteResult and deleteResult.get("error") == "forbidden":
                                    self.logger.warning(f"Unable to delete document {doc_id}. It may be protected or you lack necessary permissions.")
                            else:
                                self.logger.warning(f"Unable to delete {doc_id}: No revision available after PUT operation")

                        # Perform GET for the _changes feed if enabled
                        if self.doChanges:
                            changesResult = self.getChangesFeed(userName, password, session)
                            self.logger.info(f"Changes feed result for user {userName}: {changesResult}")

if __name__ == "__main__":
    work = WORK("config.json")
    work.openJsonFolder()
