function(doc, oldDoc) {

    try {
        a = doc._id.split(":");
    } catch (error) {
        throw({ forbidden: "error: invalid document ID format" });
    }

    if (doc.deleted && doc.deleted == true) {

        requireRole(["editor", "admin"]);

    } else {
        if (a[0] === "order") {

            requireRole(["editor", "admin", "user"]);
            fieldCheck(doc.channels);
            channel(doc.channels);

        } else if (a[0] === "job") {

            requireRole(["manager","editor", "admin"]);
            fieldCheck(doc.channels);
            channel(doc.channels);

        } else {

            throw({forbidden: "error: invalid docType"});

        }
    }
}

function fieldCheck(elementName) {
    // Check if elementName exists in the data object, is not null, not empty, and not an integer
    // channels can not be integers but they can be strings: 100 BAD , "100" GOOD
    if (typeof elementName !== 'undefined' && elementName !== null && elementName !== '' && typeof elementName !== 'number') {
        return true;
    } else {
        throw({forbidden: "error: field '" + elementName + "' has errors"});
    }
}