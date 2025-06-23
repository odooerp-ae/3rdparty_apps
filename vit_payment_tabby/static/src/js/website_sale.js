/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { WebsiteSale } from "@website_sale/js/website_sale";
// import ajax from "web.ajax"; // ✅ Import ajax utility
import { jsonRpc } from "@web/core/network/rpc";

publicWidget.registry.WebsiteSale = WebsiteSale.extend({
    /**
     * Override the _changeCartQuantity function.
     *
     * @param {jQuery} $input
     * @param {number} value
     * @param {jQuery} $dom_optional
     * @param {number} line_id
     * @param {Array} productIDs
     */
    _changeCartQuantity: function ($input, value, $dom_optional, line_id, productIDs) {

        // Optional: Call the original function
        this._super($input, value, $dom_optional, line_id, productIDs);

        jsonRpc("/shop/cart/update_json", "call", {
            line_id: line_id,
            product_id: parseInt($input.data("product-id"), 10),
            set_qty: value,
            display: true,
        }).then((data) => {
            const tabby_currency = $('#info_details').find("#currency");
            const tabby_lang = $('#info_details').find("#lang");

            console.log(tabby_currency.text(), tabby_lang.text());

            new TabbyPromo({
                selector: "#TabbyPromo",
                currency: tabby_currency.text(),
                lang: tabby_lang.text(),
                price: data.amount,
                size: "wide",
                header: true,
            });
        });
    },
});
