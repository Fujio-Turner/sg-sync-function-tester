# Sync Gateway Sync Function Tester

## PROBLEM

Don't want to touch the Sync Gateway Sync Function with a 10-foot pole because who knows what's going to happen to your writes and channel process when you change it?

## SOLUTION

I wrote this simple Python script to test the Sync Function of Sync Gateway.

## WHAT IT DOES

This script will read a folder of individual JSON files and process them as HTTP [GET, PUT, DELETE, CHANGES, GET_ADMIN, PUT_ADMIN, DELETE_ADMIN , CHANGES_ADMIN and/or PURGE] against your SG endpoint to test your Sync Function as different users.

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

## Operations

The script supports the following operations:

- `GET`: Retrieve a document
- `PUT`: Create or update a document
- `DELETE`: Delete a document
- `CHANGES`: Get the changes feed
- `PURGE`: Purge a document (admin only)
- `SLEEP`: Pause execution for a specified number of seconds

Admin versions of operations are available by appending `_ADMIN` to the operation name (e.g., `GET_ADMIN`, `PUT_ADMIN`).

### SLEEP Operation

The `SLEEP` operation allows you to introduce a delay between other operations. This can be useful for testing time-sensitive scenarios or rate limiting.

- `SLEEP`: Pauses execution for 1 second
- `SLEEP:X`: Pauses execution for X seconds (where X is an integer)

Example usage in the `operations` list(sleeps for 3 seconds):

```json
"operations": [
    "PUT_ADMIN",
    "SLEEP:3",
    "GET",
    "SLEEP",
    "DELETE"
]
```


## EXAMPLES

You can copy and paste the `config.json` file and rename them to run tests. `example_config` folder has below examples.

```sh
python3 sg-sync-function-tester.py 1.user_put-user_get.json
python3 sg-sync-function-tester.py 2.user_put-user_changes.json
python3 sg-sync-function-tester.py 3.admin_put-user_delete.json
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
    "sgAdminUser": "Administrator", // Required if you want to do Admin Operations
    "sgAdminPassword": "password",  // Required if you want to do Admin Operations
    "jsonFolder": "jsons",   // Folder containing all your individual json files
    "logPathToWriteTo": "sync_gateway_log",
    "debug": false,
    "operations": ["GET", "PUT", "DELETE", "CHANGES", "GET_ADMIN", "PUT_ADMIN", "DELETE_ADMIN", "CHANGES_ADMIN","SLEEP:3","PURGE"]  // Specify the order of operations and/or indivdual operations
}
```

### **PRO TIP**
"PURGE" is a great way to clean up data between tests. It literally 100% removes the document from Sync Gateway and the Couchbase Bucket. NOTE: PURGE is a Sync Gateway Admin function. In the config.json, you'll need to add Sync Admin (Couchbase Server RBAC [`Sync Gateway Architect`](https://docs.couchbase.com/server/current/learn/security/roles.html#sync-gateway-configurator) ) credentials for `sgAdminUser` and `sgAdminPassword`. Link here for [Offical Docs for: POST {db}/_purge](https://docs.couchbase.com/sync-gateway/current/rest-api-admin.html#/Document/post_keyspace__purge)


## UNDERSTANDING THE SYNC FUNCTION
Here is a link to understand what the Sync Function can and can not do.
- [Offical Docs for Sync Gateway's Sync Function](https://docs.couchbase.com/sync-gateway/current/sync-function.html#ex-sync-function)

#### Sample Sync Functions:
- [Github.com - sync_gateway Sample](https://github.com/couchbase/sync_gateway/blob/main/examples/database_config/sync-function.json)
- [Github.com - travel-sample Sample](https://github.com/couchbaselabs/mobile-travel-sample/blob/master/sync-gateway-config-travelsample-docker.json#L65)
- [Github.com - todo Sample](https://github.com/couchbaselabs/mobile-training-todo/blob/release/helium/docker/sg-setup/config/sync-function.json#L7)

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
5. **Sleep Operation**: Added a new `SLEEP` operation that allows pausing execution between other operations. This can be useful for testing time-sensitive scenarios or simulating delays.


Works on My Computer - Tested & Certified ;-)