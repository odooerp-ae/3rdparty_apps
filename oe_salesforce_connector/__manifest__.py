{
    "name": "Odoo-SalesForce Connector",
    "author": "OdooERP.ae",
    "version": "17.0",
    "category": "Services",
    "website": "https://odooerp.ae",
    "summary": "2 way SalesForce connector Odoo SalesForce Connector odoo salesforce integration crm app",
    "depends": ["sale_management", "product", "crm"],
    "description": """
2-way SalesForce Connector for Odoo
===================================
<keywords>
Odoo SalesForce Connector
salesforce
salesforce connector
odoo salesforce integration
crm app
""",
    "data": [
        "data/crm_stage.xml",
        "data/product_data.xml",
        "security/ir.model.access.csv",
        "wizards/message_view.xml",
        # "views/res_company_view.xml",
        "views/res_partner_view.xml",
        "views/product_templ.xml",
        "views/crm_lead_view.xml",
        "views/opportunity_view.xml",
        "views/schedulers.xml",
        "views/contract_view.xml",
        "views/event_view.xml",
        "views/mail_activity_view.xml",
        "views/sale_order_view.xml",
        "views/salesforce_instance_views.xml",
        "views/ir_attachment.xml",
    ],
    "images": ["static/description/icon.png"],
    "live_test_url": "",
    "currency": "USD",
    "license": "AGPL-3",
    "price": 450.00,
    "installable": True,
    "application": True,
    "auto_install": False,
}
