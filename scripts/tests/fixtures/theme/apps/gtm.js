
// Copyright synthetisch, Testdatei für theme.gtm, kein echter Container.
// Container: GTM-BEISP01

var data = {
"resource": {
  "version":"7",
  "macros":[{"function":"__e"},{"function":"__c","vtp_value":"G-BEISPIEL01"},{"vtp_dataLayerVersion":2,"function":"__v","vtp_name":"ecommerce.value"},{"function":"__smm","vtp_input":["macro",0],"vtp_map":["list",["map","key","purchase","value","kauf"]],"vtp_defaultValue":"andere"}],
  "tags":[
    {"function":"__googtag","priority":10,"vtp_tagId":["macro",1],"tag_id":1},
    {"function":"__gaawe","vtp_eventName":"purchase","vtp_measurementIdOverride":["macro",1],"vtp_eventParameters":["list",["map","name","value","value",["macro",2]]],"tag_id":2},
    {"function":"__awct","vtp_conversionId":"000000000","vtp_conversionLabel":"beispielLabel","vtp_conversionValue":["macro",2],"tag_id":3},
    {"function":"__baut","vtp_tagId":"000000000","vtp_eventType":"PAGE_LOAD","tag_id":4},
    {"function":"__html","once_per_event":true,"vtp_html":"<script>!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){};t=b.createElement(e);t.src=v;}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');fbq('init','100000000000001');fbq('track','PageView');</script>","consent":["list","ad_storage"],"tag_id":5},
    {"function":"__paused","vtp_originalTagType":"html","tag_id":6},
    {"function":"__html","vtp_html":"<script src=\"https://widget.gtm-unbekannt.example/a.js\"></script>","tag_id":7}
  ],
  "predicates":[{"function":"_eq","arg0":["macro",0],"arg1":"gtm.js"},{"function":"_eq","arg0":["macro",0],"arg1":"purchase"},{"function":"_re","arg0":["macro",0],"arg1":"^debug","ignore_case":true}],
  "rules":[
    [["if",0],["add",0,3,4,5]],
    [["if",1],["add",1,2]],
    [["if",2],["block",4]]
  ]
},
"runtime":[]
};
/* Ende des synthetischen Containers */
