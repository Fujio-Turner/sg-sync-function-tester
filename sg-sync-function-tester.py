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
    sgAdminPort = "4985"  # New admin port
    sgDb = "sync_gateway"
    sgTestUsers = [{"userName": "bob", "password": "12345", "sgSession": ""}]
    sgAdminUser = ""  # New admin username
    sgAdminPassword = ""  # New admin password
    logPathToWriteTo = ""
    jsonFolder = "jsons"  # Default folder for JSON files
    doGet = True
    doPut = True
    doDelete = True
    doChanges = True
    doPurge = True  # New flag for purge operation

    def __init__(self, config_file):
        # Initialize the class and read the configuration file
        self.readConfig(config_file)
        self.setupLogging()  # Call setupLogging here

    def readConfig(self, config_file):
        # Read the configuration from a JSON file
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
            # Set class attributes based on the configuration file
            self.sgLogName = config.get("logPathToWriteTo", self.logPathToWriteTo)
            self.sgHost = config.get("sgHost", self.sgHost)
            self.sgPort = config.get("sgPort", self.sgPort)
            self.sgAdminPort = config.get("sgAdminPort", self.sgAdminPort)
            self.sgDb = config.get("sgDb", self.sgDb)
            self.sgTestUsers = config.get("sgTestUsers", self.sgTestUsers)
            self.sgAdminUser = config.get("sgAdminUser", self.sgAdminUser)
            self.sgAdminPassword = config.get("sgAdminPassword", self.sgAdminPassword)
            self.jsonFolder = config.get("jsonFolder", self.jsonFolder)  # Read jsonFolder from config
            self.debug = config.get("debug", self.debug)
            self.doGet = config.get("doGet", self.doGet)
            self.doPut = config.get("doPut", self.doPut)
            self.doDelete = config.get("doDelete", self.doDelete)
            self.doChanges = config.get("doChanges", self.doChanges)
            self.doPurge = config.get("doPurge", self.doPurge)  # Read purge flag
        except FileNotFoundError:
            print(f"Configuration file '{config_file}' not found.")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"Configuration file '{config_file}' is not valid JSON.")
            sys.exit(1)

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

    def httpPost(self, url="", jsonData={}, userName="", password=""):
        try:
            headers = {"Content-Type": "application/json"}
            response = requests.post(url, json=jsonData, headers=headers, auth=HTTPBasicAuth(userName, password))
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Error in HTTP POST: {e}")
            return None

    def getChangesFeed(self, userName="", password="", session=""):
        sgUrl = f"{self.sgHost}:{self.sgPort}/{self.sgDb}/_changes"
        request = self.httpGet(sgUrl, userName, password, session)
        return request

    def postPurge(self, docIds):
        sgUrl = f"{self.sgHost}:{self.sgAdminPort}/{self.sgDb}/_purge"
        purgeData = {docId: ["*"] for docId in docIds}
        return self.httpPost(sgUrl, purgeData, self.sgAdminUser, self.sgAdminPassword)

    def validateJsonFiles(self, json_folder):
        # Check if the folder is empty
        if not os.listdir(json_folder):
            self.logger.warning("No JSON files found in the folder.")
            return False
        
        valid_json_files = []
        for filename in os.listdir(json_folder):
            if filename.endswith(".json"):
                file_path = os.path.join(json_folder, filename)
                try:
                    with open(file_path, "r") as f:
                        json_data = json.load(f)
                    valid_json_files.append(json_data)
                except json.JSONDecodeError:
                    self.logger.error(f"File '{filename}' is not valid JSON or is empty.")
                except Exception as e:
                    self.logger.error(f"Error reading file '{filename}': {e}")

        if not valid_json_files:
            self.logger.warning("No valid JSON files found.")
            return False
        
        return valid_json_files

    def openJsonFolder(self):
        json_folder = self.jsonFolder  # Use the folder from the config
        valid_json_data = self.validateJsonFiles(json_folder)
        if not valid_json_data:
            return  # Exit if there are no valid JSON files

        processed_docs = []
        for json_data in valid_json_data:
            doc_id = json_data.get("_id")
            if doc_id:
                processed_docs.append(doc_id)
                for user in self.sgTestUsers:
                    sgUrl = f"{self.sgHost}:{self.sgPort}/{self.sgDb}/{doc_id}"
                    userName = user["userName"]
                    password = user["password"]
                    session = user["sgSession"]

                    sgGetResult = None
                    rev = None
                    if self.doGet:
                        self.logger.info(f"User: {userName} trying to GET: {doc_id} at URL: {sgUrl}")
                        sgGetResult = self.httpGet(sgUrl, userName, password, session)
                        self.logger.info(f"GET result for {doc_id}: {sgGetResult}")
                        if sgGetResult:
                            rev = sgGetResult.get('_rev')

                    putResult = None
                    if self.doPut:
                        if sgGetResult:
                            # Document exists, add timestamp and update
                            sgGetResult['dateTimeStamp'] = datetime.now().isoformat()
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
                        if putResult and putResult.get("rev"):
                            rev = putResult["rev"]

                        # Handle PUT conflicts
                        if putResult and putResult.get("error") == "conflict":
                            self.logger.warning(f"Conflict occurred while updating document {doc_id}. Skipping delete operation.")
                            continue

                    if self.doDelete:
                        # Attempt to delete the document
                        if rev:
                            deleteResult = self.httpDelete(f"{self.sgHost}:{self.sgPort}/{self.sgDb}", 
                                                           doc_id, rev, 
                                                           userName, password, session)
                            self.logger.info(f"DELETE result for {doc_id}: {deleteResult}")

                            # Handle delete forbidden
                            if deleteResult and deleteResult.get("error") == "forbidden":
                                self.logger.warning(f"Unable to delete document {doc_id}. It may be protected or you lack necessary permissions.")
                        else:
                            self.logger.warning(f"Unable to delete {doc_id}: No revision available from GET or PUT operations")

                    if self.doChanges:
                        changesResult = self.getChangesFeed(userName, password, session)
                        self.logger.info(f"Changes feed result for user {userName}: {changesResult}")

        # Perform purge operation after processing all documents
        if self.doPurge:
            if not self.sgAdminUser or not self.sgAdminPassword:
                self.logger.warning("Admin username or password is missing. Skipping purge operation.")
            elif not self.sgAdminPort:
                self.logger.warning("Admin port is not specified. Skipping purge operation.")
            else:
                purgeResult = self.postPurge(processed_docs)
                self.logger.info(f"Purge result: {purgeResult}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: #python3 sg-sync-function-tester.py config_file.json")
        sys.exit(1)

    config_file = sys.argv[1]
    work = WORK(config_file)
    work.openJsonFolder()