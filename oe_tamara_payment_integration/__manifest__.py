{
    "name": "Odoo - Tamara Payment Connector",
    "summary": "Odoo - Tamara Payment Connector",
    "category": "Accounting",
    "version": "18.0",
    "author": "Oakland OdooERP",
    "license": "AGPL-3",
    "price": "101.0",
    "currency": "USD",
    "website": "https://odooerp.ae",
    "description": "Integrate Tamara 'Buy Now, Pay Later' with your Odoo store. Enable flexible checkout, order synchronization, and customer-friendly installment payments.",
    "depends": ["payment", "account", "website_sale"],
    "data": [
        "views/payment_acquirer.xml",
        "views/payment_tamara_templates.xml",
        "data/tamara_payment_data.xml",
        "views/res_config_settings_views.xml",
        "views/template.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "/oe_tamara_payment_integration/static/src/js/product_widget.js"
        ],
    },
    "images": ["static/description/Banner.gif"],
    "application": True,
    "installable": True,
    "external_dependencies": {"python": ["jwt"]},
}
