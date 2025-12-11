function(doc, oldDoc) {
    var parts;

    try {
        parts = doc._id.split("-");
    } catch (e) {
        throw({forbidden: "Invalid document ID format"});
    }

    // Handle tombstone (deleted document)
    if (doc._deleted === true) {  
        requireRole(["editor", "admin"]);
        return; 
    }

    var docType = parts[0];

    if (docType === "order") {
        requireRole(["editor", "admin", "user"]);

    } else if (docType === "job") {
        requireRole(["manager", "editor", "admin"]);

    } else {
        throw({forbidden: "Invalid docType: " + docType});
    }

    // Validate and assign channels
    if (!doc.channels || !Array.isArray(doc.channels) || doc.channels.length === 0) {
        throw({forbidden: "Document must have non-empty 'channels' array"});
    }

    channel(doc.channels);
}

// Improved fieldCheck – but actually you don't need it for channels if you validate above
// Keep it only if you reuse it for other fields
function requireField(value, fieldName) {
    if (value === undefined || value === null || value === "" || 
        (typeof value === "number") || 
        (Array.isArray(value) && value.length === 0)) {
        throw({forbidden: "Field '" + fieldName + "' is invalid or missing"});
    }
