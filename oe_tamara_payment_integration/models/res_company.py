import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    data_exclude_products = fields.Many2many(
        "product.product", "tamara_exclude_products_rel", string="Exclude Products"
    )
    data_disable_installment = fields.Boolean(string="Disable Installment")
    data_disable_paylater = fields.Boolean(string="Disable Paylater")
    product_widget = fields.Boolean(string="Product Widget ")
    data_payment_type = fields.Selection(
        [("paylater", "Pay Later"), ("installment", "Installment")],
        string="Payment type",
    )
    data_installment_minimum_amount = fields.Float(string="Installment Minimum Amount")
    data_installment_maximum_amount = fields.Float(string="Installment Maximum Amount")
    data_installment_available_amount = fields.Float(
        string="Installment Available Amount"
    )
    data_pay_later_max_amount = fields.Float(string="Pay Later Maximum Amount")
    data_number_of_installments = fields.Selection(
        [
            ("2", "2"),
            ("3", "3"),
            ("4", "4"),
            ("5", "5"),
            ("6", "6"),
            ("12", "12"),
        ],
        string="No of Installments",
    )

