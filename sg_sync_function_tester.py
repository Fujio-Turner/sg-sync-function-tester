import json
import os
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime
import logging
import sys
import time


# The WORK class represents the main functionality for interacting with Sync Gateway to test the Sync Function
class WORK:
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
    sgAdminPassword = "Administrator"
    logPathToWriteTo = "password"
    jsonFolder = "jsons"
    operations = []

    # Initializes the WORK object with the given configuration file
    def __init__(self, config_file):
        self.readConfig(config_file)
        self.setupLogging()

    # Reads the configuration from the specified file and sets up the object's attributes
    def readConfig(self, config_file):
        try:
            with open(config_file, "r") as f:
                config = json.load(f)
        except FileNotFoundError:
            raise Exception(f"Configuration file '{config_file}' not found.")
        except json.JSONDecodeError:
            raise Exception(f"Configuration file '{config_file}' is not valid JSON.")

        self.sgLogName = config.get("logPathToWriteTo", self.logPathToWriteTo)
        self.sgHost = config.get("sgHost", self.sgHost)
        self.sgPort = config.get("sgPort", self.sgPort)
        self.sgAdminPort = config.get("sgAdminPort", self.sgAdminPort)
        self.sgDb = config.get("sgDb", self.sgDb)
        self.sgDbScope = config.get("sgDbScope", self.sgDbScope)
        self.sgDbCollection = config.get("sgDbCollection", self.sgDbCollection)
        self.sgTestUsers = config.get("sgTestUsers", self.sgTestUsers)
        self.sgAdminUser = config.get("sgAdminUser", self.sgAdminUser)
        self.sgAdminPassword = config.get("sgAdminPassword", self.sgAdminPassword)
        self.jsonFolder = config.get("jsonFolder", self.jsonFolder)
        self.debug = config.get("debug", self.debug)
        self.operations = config.get("operations", self.operations)

    # Sets up logging for the application with ISO 8601 timestamps
    def setupLogging(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"{self.sgLogName}_{timestamp}.log"
        
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG if self.debug else logging.INFO)
        
        formatter = logging.Formatter("%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s", datefmt='%Y-%m-%dT%H:%M:%S')
        
        file_handler = logging.FileHandler(log_filename)
        file_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        
        # Store the file handler so it can be closed later
        self.file_handler = file_handler


    # Closes the log file
    def closeLogFile(self):
        if hasattr(self, 'file_handler'):
            self.file_handler.close()
            self.logger.removeHandler(self.file_handler)

    # Constructs the database URL based on scope and collection
    def constructDbUrl(self):
        if self.sgDbScope == "_default" and self.sgDbCollection == "_default":
            return self.sgDb
        else:
            return f"{self.sgDb}.{self.sgDbScope}.{self.sgDbCollection}"

    # Performs an HTTP request to the Sync Gateway
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
            
            # Handle the case where response might be a dictionary (for testing purposes)
            if isinstance(response, dict):
                return response
            
            response.raise_for_status()
            return response.json() if response.text else None
        except requests.RequestException as e:
            self.logger.error(f"Error in HTTP {method}: {e}")
            return None

    # Retrieves the changes feed from Sync Gateway
    def getChangesFeed(self, userName="", password="", session="", is_admin=False, channels=None):
        sgUrl = f"{self.sgHost}:{self.sgPort}/{self.sgDb}/_changes"
        if channels:
            sgUrl += f"?filter=sync_gateway/bychannel&channels={channels}"
        return self.httpRequest("GET", sgUrl, userName=userName, password=password, session=session, is_admin=is_admin)

    # Performs a purge operation on the specified document IDs
    def postPurge(self, docIds):
        sgUrl = f"{self.sgHost}:{self.sgAdminPort}/{self.sgDb}/_purge"
        purgeData = {docId: ["*"] for docId in docIds}
        result = self.httpRequest("POST", sgUrl, json_data=purgeData, is_admin=True)
        return result.json() if hasattr(result, 'json') else result

    # Processes JSON files in the specified folder and performs operations on them
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
                    rev = None
                    for operation in self.operations:
                        if operation.startswith("SLEEP"):
                            sleep_time = 1  # Default sleep time
                            if ":" in operation:
                                try:
                                    sleep_time = int(operation.split(":")[1])
                                except ValueError:
                                    self.logger.warning(f"Invalid sleep time format: {operation}. Using default 1 second.")
                            self.logger.info(f"[success] - [SLEEP] - Sleeping for {sleep_time} seconds")
                            time.sleep(sleep_time)
                            continue

                        is_admin = operation.endswith("_ADMIN")
                        op = operation.replace("_ADMIN", "")
                        
                        for user in self.sgTestUsers:
                            sgUrl = f"{self.sgHost}:{self.sgPort}/{self.constructDbUrl()}/{doc_id}"
                            userName = user["userName"]
                            password = user["password"]
                            session = user["sgSession"]

                            if op == "GET":
                                try:
                                    result = self.httpRequest("GET", sgUrl, userName=userName, password=password, session=session, is_admin=is_admin)
                                    status = "success" if result else "failed"
                                    self.logger.info(f"[{status}] - [GET] - [{'Admin' if is_admin else userName}] - GET result for [{doc_id}] - {json.dumps(result) if result else 'null'}")
                                    if result:
                                        rev = result.get('_rev')
                                except requests.RequestException:
                                    self.logger.info(f"[failed] - [GET] - [{'Admin' if is_admin else userName}] - GET result for [{doc_id}] - null")

                            elif op == "PUT":
                                try:
                                    # Get the current document first
                                    current_doc = self.httpRequest("GET", sgUrl, userName=userName, password=password, session=session, is_admin=is_admin)
                                    if current_doc and '_rev' in current_doc:
                                        # Update the revision if the document exists
                                        json_data['_rev'] = current_doc['_rev']
                                    
                                    json_data['dateTimeStamp'] = datetime.now().isoformat()
                                    result = self.httpRequest("PUT", sgUrl, json_data=json_data, userName=userName, password=password, session=session, is_admin=is_admin)
                                    status = "success" if result and result.get("ok") else "failed"
                                    self.logger.info(f"[{status}] - [PUT] - [{'Admin' if is_admin else userName}] - PUT result for [{doc_id}] - {json.dumps(result)}")
                                    if result and result.get("rev"):
                                        rev = result["rev"]
                                except requests.RequestException as e:
                                    self.logger.error(f"[failed] - [PUT] - [{'Admin' if is_admin else userName}] - Error in HTTP PUT for [{doc_id}] - {str(e)}")
                                    self.logger.info(f"[failed] - [PUT] - [{'Admin' if is_admin else userName}] - PUT result for [{doc_id}] - null")

                            elif op == "DELETE":
                                try:
                                    # Get the current document first
                                    current_doc = self.httpRequest("GET", sgUrl, userName=userName, password=password, session=session, is_admin=is_admin)
                                    if current_doc and '_rev' in current_doc:
                                        rev = current_doc['_rev']
                                        delete_url = f"{self.sgHost}:{self.sgPort}/{self.constructDbUrl()}/{doc_id}?rev={rev}"
                                        result = self.httpRequest("DELETE", delete_url, userName=userName, password=password, session=session, is_admin=is_admin)
                                        status = "success" if result and result.get("ok") else "failed"
                                        self.logger.info(f"[{status}] - [DELETE] - [{'Admin' if is_admin else userName}] - DELETE result for [{doc_id}] - {json.dumps(result)}")
                                    else:
                                        self.logger.warning(f"[failed] - [DELETE] - [{'Admin' if is_admin else userName}] - Unable to delete [{doc_id}] - Document not found or no revision available")
                                except requests.RequestException as e:
                                    self.logger.error(f"[failed] - [DELETE] - [{'Admin' if is_admin else userName}] - Error in HTTP DELETE for [{doc_id}] - {str(e)}")
                                    self.logger.info(f"[failed] - [DELETE] - [{'Admin' if is_admin else userName}] - DELETE result for [{doc_id}] - null")

                            elif op.startswith("CHANGES"):
                                try:
                                    channels = None
                                    if ":" in op:
                                        channels = op.split(":", 1)[1]
                                    result = self.getChangesFeed(userName=userName, password=password, session=session, is_admin=is_admin, channels=channels)
                                    status = "success" if result else "failed"
                                    result_count = len(result.get("results", [])) if result else 0
                                    self.logger.info(f"[{status}] - [CHANGES] - [{'Admin' if is_admin else userName}] - Changes feed result for [{doc_id}], rows: {result_count} - {json.dumps(result)}")
                                except requests.RequestException as e:
                                    self.logger.error(f"[failed] - [CHANGES] - [{'Admin' if is_admin else userName}] - Error in HTTP CHANGES for [{doc_id}] - {str(e)}")
                                    self.logger.info(f"[failed] - [CHANGES] - [{'Admin' if is_admin else userName}] - Changes feed result for [{doc_id}], rows: 0 - null")

                            elif op == "PURGE":
                                try:
                                    result = self.postPurge([doc_id])
                                    status = "success" if result and result.get("purged") else "failed"
                                    result_str = json.dumps(result) if isinstance(result, dict) else str(result)
                                    self.logger.info(f"[{status}] - [PURGE] - [Admin] - Purge result for [{doc_id}] - {result_str}")
                                except requests.RequestException as e:
                                    self.logger.error(f"[failed] - [PURGE] - [Admin] - Error in HTTP PURGE for [{doc_id}] - {str(e)}")
                                    self.logger.info(f"[failed] - [PURGE] - [Admin] - Purge result for [{doc_id}] - null")

                            elif op == "GET_RAW":
                                try:
                                    raw_url = f"{self.sgHost}:{self.sgAdminPort}/{self.constructDbUrl()}/_raw/{doc_id}"
                                    result = self.httpRequest("GET", raw_url, is_admin=True)
                                    status = "success" if result else "failed"
                                    self.logger.info(f"[{status}] - [GET_RAW] - [Admin] - GET_RAW result for [{doc_id}] - {json.dumps(result) if result else 'null'}")
                                except requests.RequestException as e:
                                    self.logger.error(f"[failed] - [GET_RAW] - [Admin] - Error in HTTP GET_RAW for [{doc_id}] - {str(e)}")
                                    self.logger.info(f"[failed] - [GET_RAW] - [Admin] - GET_RAW result for [{doc_id}] - null")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 sg_sync_function_tester.py <config_file>")
        sys.exit(1)

    config_file = sys.argv[1]
    work = WORK(config_file)
    work.openJsonFolder()
    work.closeLogFile()



'''
HOW TO RUN THE UNIT TEST
python3 -m unittest discover -s test -p "test_sg_sync_function_tester.py"
'''