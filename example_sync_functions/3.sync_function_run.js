function(doc, oldDoc) {

    let a;
    try {
        a = doc._id.split("-");
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
    if (typeof elementName !== 'undefined' && elementName !== null && elementName !== '' && typeof elementName !== 'number') {
        return true;
    } else {
        throw({forbidden: "error: field '" + elementName + "' has errors"});
    }
}