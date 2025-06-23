/** @odoo-module alias=payment_tabby.website_sale **/
import { WebsiteSale } from '@website_sale/js/website_sale';
import { jsonrpc } from "@web/core/network/rpc_service";

WebsiteSale.include({
    init: function () {
        this._super.apply(this, arguments);
        var self = this;

        // Fetch the website's active pricelist and its currency
        jsonrpc('/website_sale/get_pricelist_available', {}).then((pricelistData) => {
            // Get the currency code from the returned pricelist data
            var currencyCode = pricelistData.currency_id ? pricelistData.currency_id.name : 'SAR'; // Default to 'SAR' if no currency is found
            console.log('pricelistData', pricelistData.currency_id.name)
            console.log('currencyCode', currencyCode)
            jsonrpc('/payment_tabby/get_credentials', {}).then((tabbyData) => {
                var currencyElement = $('.oe_currency_value')[0]; // Get the first matching element (currency value on the page)
                if (currencyElement) {
                    var priceText = currencyElement.innerText || currencyElement.textContent; // Get the price text
                    var price = parseFloat(priceText.replace(',', ''));

                    // Prepare the data for Tabby Promo
                    var data = {
                        selector: '#tabby', // required, content of tabby Promo Snippet will be placed in element with that selector.
                        currency: currencyCode, // dynamically set the currency based on pricelist
                        price: price, // required, price or the product. 2 decimals max for AED|SAR|QAR and 3 decimals max for KWD|BHD.
                        installmentsCount: 4, // Optional, for non-standard plans.
                        lang: 'en', // Optional, language of snippet and popups, if the property is not set, then it is based on the attribute 'lang' of your html tag.
                        source: 'product', // Optional, snippet placement; `product` for product page and `cart` for cart page.
                        publicKey: tabbyData['tabby_public_key'], // required, store Public Key which identifies your account when communicating with tabby.
                        merchantCode: tabbyData['tabby_merchant_code']  // required
                    };
                    console.log('daaaaaa', data)

                    // Initialize the TabbyPromo snippet with the dynamic data
                    new TabbyPromo(data);
                }
            });
        });
    },
})

export default WebsiteSale;
