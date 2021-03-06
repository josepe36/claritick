dependencies ={

    stripConsole: "normal",

   layers:  [
       {
       name: "dojo.js",
       dependencies: [
           "dijit.dijit",
           "dijit.Menu",
           "dijit.Tree",
           "dijit.Tooltip",
           "dijit.Dialog",
           "dijit.TooltipDialog",
           "dijit.form.Button",
           "dijit.form.CheckBox",
           "dijit.form.MultiSelect",
           "dijit.form.DropDownButton",
           "dijit.form.NumberSpinner",
           "dijit.form.NumberTextBox",
           "dijit.form.Textarea",
           "dijit.form.DateTextBox",
           "dijit.form.TimeTextBox",
           "dijit.form.ValidationTextBox",
           "dijit.form.ComboBox",
           "dijit.form.Slider",
           "dijit.form.FilteringSelect",
           "dijit.layout.ContentPane",
           "dijit.layout.TabContainer",
           "dojo.dnd.Source",
           "dojo.nls.dojo_fr-fr",
           "dojox.fx",
           "dojox.fx.scroll",
           "dojox.validate"
       ]
       }
   ],

   prefixes: [
       [ "dijit", "../dijit" ],
       [ "dojox", "../dojox" ],
   ]

 };
