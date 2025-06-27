odoo.define('oe_tabby_payment_integration.custom', function (require) {
    'use strict';

    $(document).ready(function () {
        var urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('tabby_error_callback')) {
            $('.tabby_error_alert').show();
        }
    });
    $(document).on('change', 'input[name="delivery_type"]:checked', function(){
        window.location.reload();
    })
});
