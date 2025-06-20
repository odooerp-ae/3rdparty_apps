from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    x_salesforce_document_id = fields.Char(
        string="Salesforce Document ID",
        index=True,
        help="Stores the Salesforce ContentDocumentId to prevent duplicate uploads.",
    )
