function addNewClienthost(url,tableID,action,clientid){
    var postdata;
    postdata = dijit.byId('host_id').value;
    // Ajout d un host pour un client 
    if (action === "add") {
        //control if id is not already in the table
        var table = document.getElementById(tableID);
        var rowCount = table.rows.length;
        for(var i=0; i<rowCount; i++) {
            var row = table.rows[i];
            var chkbox = row.cells[2].childNodes[0];
            if(chkbox.value === dijit.byId("host_id").value.split(',')[0]) {
                return;
            }
        }

        dojo.xhrPost({
        headers: { 'X-CSRFToken': dojo.cookie("csrftoken") },
        url: url,
        postData: "host_id="+dijit.byId("host_id").value.split(',')[0] + "&client_id="+ clientid +"&name=" + dijit.byId("machine_name").value,
        handleAs: 'json',
        load: function (data, ioArgs) {

            var table = document.getElementById(tableID);
            var rowCount = table.rows.length;
            var row = table.insertRow(rowCount);

            var cell2 = row.insertCell(0);
            cell2.style.width = "260px";
            cell2.innerHTML = document.getElementById('machine_name').value;

            var cell3 = row.insertCell(1);
            cell3.style.width = "500px";
            cell3.innerHTML = dijit.byId("host_id").value.split(',')[1];
                        
            var cell1 = row.insertCell(2);

            var element1 = document.createElement("input");
            //cell1.style.width = "20px";
            element1.type = "checkbox";
            element1.value = dijit.byId("host_id").value.split(',')[0];
            cell1.appendChild(element1); 
            dijit.byId('add_button').setAttribute('disabled', true);
            document.getElementById('delete_button').style.visibility = "visible"; }});
  }
    // suppression d'un host pour un client
    else {
        var table = document.getElementById(tableID);
        var rowCount = table.rows.length;
        var nbrdel = 0;
        var initialrowcount = rowCount;
        for(var i=0; i<rowCount; i++) {
            var row = table.rows[i];
            var chkbox = row.cells[2].childNodes[0];
            if(null != chkbox && true == chkbox.checked) {                 
            dojo.xhrPost({
                headers: { 'X-CSRFToken': dojo.cookie("csrftoken") },
                url: url,
                postData: "host_id="+chkbox.value + "&client_id="+ clientid +"",
                handleAs: 'text',
                sync: true,
                load: function (data) {} });
            nbrdel = nbrdel + 1;
            table.deleteRow(i);
            rowCount--;
            i--;
    }
   }

         nbrdel = nbrdel ;
         if (nbrdel === initialrowcount) {
            document.getElementById('delete_button').style.visibility = "hidden"
         }
  }
 }
// control si l'host selectionne dans le select est déjas dans la table, gestion du boutton ajouter
function controlifexist(tableID) {
        
        var table = document.getElementById(tableID);
        var rowCount = table.rows.length;
        if (rowCount === 0){dijit.byId('add_button').setAttribute('disabled', false);return}
        for(var i=0; i<rowCount; i++) {
            var row = table.rows[i];
            var chkbox = row.cells[2].childNodes[0];
            if(chkbox.value === dijit.byId("host_id").value.split(',')[0]) {
                dijit.byId('add_button').setAttribute('disabled', true);
                return;
            }
            else {dijit.byId('add_button').setAttribute('disabled', false);}
            };
}
