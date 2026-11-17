function (doc, oldDoc, meta) {
    // Deletes need the "editor" role -> bob (no roles) gets 403 on DELETE.
    if (doc._deleted) {
        requireRole("editor");
        return;
    }
    // Docs flagged locked can only be written by an admin -> bob gets 403 on PUT.
    if (doc.locked === true || (oldDoc && oldDoc.locked === true)) {
        requireAdmin();
    }
    if (!doc.channels) {
        throw({forbidden: "channels field is required"});
    }
    channel(doc.channels);
}
