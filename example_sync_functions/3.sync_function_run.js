function(doc, oldDoc) {

    var parts = [];                    
    
    try {
        parts = doc._id.split(":");
    } catch (e) {
        throw({forbidden: "error: invalid document ID format"});
    }

    var type = parts[0];

    // Handle deletion
    if (doc._deleted === true) {
        
        requireRole(["editor", "admin"]);
        return;
    
    }else{

        // Role check
        if (type === "order") {
            requireRole(["editor", "admin", "user"]);
        } else if (type === "job") {
            requireRole(["manager", "editor", "admin"]);
        } else {
            throw({forbidden: "error: invalid docType"});
        }

        // CHANNEL FIELD – CHANGE "channels" TO YOUR ACTUAL FIELD NAME BELOW
        var ch = getChannels("channels");   // ←←← UPDATE THIS (e.g. "city", "tags", etc.)

        if (!ch) {
            // ONLY log when something is wrong — helps catch forgotten field names fast
            console.log("SYNC FUNCTION WARNING: Field 'channels' is missing, null, empty, or has no valid values in document:", doc._id);
            throw({forbidden: "error: required channel field is missing or empty"});
        }

        channel(ch);
    }
}

function getChannels(field) {
    var raw = doc[field];

    if (raw === undefined || raw === null) {
        return false;
    }

    var list = Array.isArray(raw) ? raw : [raw];
    var clean = [];

    for (var i = 0; i < list.length; i++) {
        var item = list[i];
        if (item === null || item === undefined) continue;
        var s = String(item).trim();
        if (s !== "") clean.push(s);
    }

    return clean.length > 0 ? clean : false;
}