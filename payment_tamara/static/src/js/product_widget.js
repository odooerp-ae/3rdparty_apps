/* Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>) */
/* See LICENSE file for full copyright and licensing details. */
odoo.define('payment_tamara_product_widget.product_widget', function (require) {
    "use strict";

    var ajax = require('web.ajax');

    $(document).ready(function() {
        if ($('.tamara-product-widget').length >0 ){
            ajax.jsonRpc('/product/widget', 'call', {}).then((product_widget)=> {
                    if (product_widget.product_widget){
                        if (window.TamaraProductWidget) { 
                            window.TamaraProductWidget.init({
                              
                            });
                            window.TamaraProductWidget.render()
                        }       
                }
                
            });
        }
    });


    $(document).ready(function() {
        if ($('.tamara-installment-plan-widget').length >0 ){
            ajax.jsonRpc('/product/widget', 'call', {}).then((product_widget)=> {
                    if (product_widget.product_widget){
                        if (window.TamaraInstallmentPlan) { 
                            window.TamaraInstallmentPlan.init({
                              
                            });
                            window.TamaraInstallmentPlan.render()
                        }       
                }
                
            });
        }
    });

});

