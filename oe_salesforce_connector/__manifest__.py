{
    "name": "Odoo-SalesForce Connector",
    "author": "OdooERP.ae",
    "version": "18.0.1.0.0",
    "category": "Services",
    "website": "https://odooerp.ae",
    "summary": "Two-Way Salesforce Connector - Integrate Odoo with Salesforce CRM Effortlessly",
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
    "price": 350.00,
    "installable": True,
    "application": True,
    "auto_install": False,
}
