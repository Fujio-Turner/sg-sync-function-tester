function(doc, oldDoc) {
        if(doc.type === "order"){
                channel(doc.owner);
          }else{
               requireRole("backEnd");
                channel(doc.channels);
          }
}