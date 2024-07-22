# Sync Gateway Sync Function Tester

Don't want to touch the Sync Gateway Sync Function with a 10-foot pole because who knows what's going to happen to your writes and channel process when you change it?

I wrote this simple Python script to test the Sync Function of Sync Gateway.

This script will read a folder of individual JSON files (CBL Documents) and process them as HTTP [GET, PUT, DELETE, CHANGES, GET_ADMIN, PUT_ADMIN, DELETE_ADMIN , CHANGES_ADMIN and/or PURGE] against your SG endpoint to test your Sync Function.

## HOW TO USE

**Step 1.** Update the `config.json` with your Sync Gateway hostname, one or more CBL test users, and other settings you want.

**Step 2.** In the folder specified in your config (default is `jsons`), put sample JSON docs as individual files. Example: `{"_id":"foo","channels":["bob"]}` saved in a file `foo.json`.  

**Step 3.** Run the Python code 

```sh
python3 sg-sync-function-tester.py config.json
```

**OUTPUT:** It will output a log file of the run: `sync_gateway_log_{date}_{time}.log`

Example output:
```
2024-07-19 16:10:39,739 - INFO - User: bob trying to GET: foo at URL: http://localhost:4984/sync_gateway/foo
2024-07-19 16:10:39,750 - INFO - GET result for foo: None
2024-07-19 16:10:39,756 - INFO - PUT result for foo: {'id': 'foo', 'ok': True, 'rev': '1-2b47a02d6e166b6f3ff4a9bb67977777'}
2024-07-19 16:10:39,761 - INFO - Changes feed result for user bob: {'results': [{'seq': 1, 'id': '_user/bob', 'changes': []}, {'seq': 32, 'id': 'foo', 'changes': [{'rev': '1-2b47a02d6e166b6f3ff4a9bb67977777'}]}], 'last_seq': '32'}
```

## EXAMPLES

You can copy and paste the `config.json` file and rename them to run tests like: test1:[PUT,GET,CHANGES] or test2:[PUT_ADMIN, DELETE] and specify different files/folders you want to use.

```sh
python3 sg-sync-function-tester.py test1-folder1.json
python3 sg-sync-function-tester.py test1-folder2.json
python3 sg-sync-function-tester.py test2-folder3.json
...etc
```

## config.json

```json
{
    "sgHost": "http://localhost",
    "sgPort": "4984",
    "sgAdminPort": "4985",
    "sgDb": "sync_gateway",
    "sgTestUsers": [
        {"userName": "bob", "password": "12345", "sgSession": ""}
    ],
    "sgAdminUser": "Administrator", // Required if you want to Purge
    "sgAdminPassword": "password",  // Required if you want to Purge
    "jsonFolder": "jsons",   // Folder containing all your individual json files
    "logPathToWriteTo": "sync_gateway_log",
    "debug": false,
    "operations": ["GET", "PUT", "DELETE", "CHANGES", "GET_ADMIN", "PUT_ADMIN", "DELETE_ADMIN", "CHANGES_ADMIN", "PURGE"]  // Specify the order of operations and/or indivdual operations
}
```

### **PRO TIP**
"PURGE" is a great way to clean up data between tests. It literally 100% removes the document from Sync Gateway and the Couchbase Bucket. NOTE: PURGE is a Sync Gateway Admin function. In the config.json, you'll need to add Sync Admin (RBAC `Sync Gateway Architect`) credentials for `sgAdminUser` and `sgAdminPassword`. Link here for [Offical Docs for: POST {db}/_purge](https://docs.couchbase.com/sync-gateway/current/rest-api-admin.html#/Document/post_keyspace__purge)


## REQUIREMENTS 
- A Running Sync Gateway w/ one or more known Sync Gateway USERS (cbl user)
- Python 3
- Python Requests Library: https://docs.python-requests.org/en/latest/index.html

To install the required library:
```sh
pip install requests
```

### Key Changes:
1. **Updated the `operations` Configuration**: Added an `operations` attribute to specify the list of operations to perform.
2. **Dynamic Operation Execution**: The script now executes operations in the order specified in the `operations` array.
3. **Clarified Usage Instructions**: Updated the usage instructions to reflect the new configuration options.
4. **Admin Operations**: Your Sync Function might have certain restrictions at a USER level, but you still need to GET and PUT docs. There are now admin equivalents to the operations.

Works on My Computer - Tested & Certified ;-)