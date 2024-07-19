Don't want to touch the Sync Gateway Sync Function with a 10 foot pole because who knows whats going to happen to my writes and channel process when you change it.

I wrote this simple python script test the Sync Function of Sync Gateway.

This script will read a folder of invidual JSON files(CBL Documents) and process them as HTTP [GET,PUT and/or DELETE] against your SG endpoint to test your Sync Function

## HOW TO USE

### Step 1. Update the `config.json` with your Sync Gateway hostname , one or CBL test users and other setting you'll want.

### Step 2. Put sample json docs as individual files. Exmaple this JSON `{"_id":"foo","channels":["bob"]}` is saved in this file `foo.json`.  

### Step 3. Run the python code 

```
# python3 sg-sync-function-tester.py config.json
```

**OUTPUT:** It will output a log file of the run: ```sync_gateway_log_{date}_{time}.log```

```
2024-07-19 16:10:39,739 - INFO - User: bob trying to GET: foo at URL: http://localhost:4984/sync_gateway/foo
2024-07-19 16:10:39,750 - INFO - GET result for foo: None
2024-07-19 16:10:39,756 - INFO - PUT result for foo: {'id': 'foo', 'ok': True, 'rev': '1-2b47a02d6e166b6f3ff4a9bb67977777'}
2024-07-19 16:10:39,761 - INFO - Changes feed result for user bob: {'results': [{'seq': 1, 'id': '_user/bob', 'changes': []}, {'seq': 32, 'id': 'foo', 'changes': [{'rev': '1-2b47a02d6e166b6f3ff4a9bb67977777'}]}], 'last_seq': '32'}
```

## EXAMPLES

You can copy and paste the `config.json` file and rename them with the tests and files you want.

```
# python3 sg-sync-function-tester.py test1-folder1.json
# python3 sg-sync-function-tester.py test1-folder2.json
# python3 sg-sync-function-tester.py test2-folder3.json
...etc
```

## config.json

```
{
    "sgHost": "http://localhost",
    "sgPort": "4984",
    "sgAdminPort": "4985",
    "sgDb": "sync_gateway",
    "sgTestUsers": [
        {"userName": "bob", "password": "12345", "sgSession": ""}   ##create a list of pre-made user(s) to process all the json files you want in a folder
    ],
    "sgAdminUser": "Administrator", ##required if you want to Purge
    "sgAdminPassword": "password",  ##required if you want to Purge
    "jsonFolder":"jsons",   #folder of all your individual json files
    "logPathToWriteTo": "sync_gateway_log",
    "debug": false,
    "doGet": true,     ##Get Documents
    "doPut": true,     ##Put Document
    "doDelete": false, ##Delete document
    "doChanges": true, ##get a _changes feed as a user
    "doPurge": false  ##set to true if you want it to removal all the document you just proccessed
}
```

## REQUIRES 
- Python3
- Python Request Library. https://docs.python-requests.org/en/latest/index.html

Works on My Computer Tested & Certified ;-)