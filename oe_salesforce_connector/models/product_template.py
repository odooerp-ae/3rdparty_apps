import json
import requests
from datetime import datetime
from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError


class ProductTemplateCust(models.Model):
    _inherit = 'product.template'

    product_variant_id = fields.Many2one('product.product', 'Product', compute='_compute_product_variant_id', store=True)
    x_salesforce_exported = fields.Boolean('Exported To Salesforce', default=False, copy=False)
    x_salesforce_id = fields.Char(related='product_variant_id.x_salesforce_id', string='Salesforce Id', copy=False)
    x_is_updated = fields.Boolean('x_is_updated', default=False, copy=False)

    def sendDataToSf(self, product_dict):
        sf_config = self.env['salesforce.instance'].sudo().search([('company_id', '=', self.env.company.id)], limit=1)
        if not sf_config:
            raise ValidationError("There is no Salesforce instance for this company '%s'." % (self.env.company.name))

        ''' GET ACCESS TOKEN '''
        endpoint = None
        sf_access_token = None
        # realmId = None
        res = None
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

            endpoint = '/services/data/v39.0/sobjects/product2'

            payload = json.dumps(product_dict)
            if self.x_salesforce_id:
                ''' Try Updating it if already exported '''
                res = requests.request('PATCH', sf_config.sf_url + endpoint + '/' + self.x_salesforce_id, headers=headers, data=payload)
                if res.status_code in (200, 201, 204):
                    self.x_is_updated = True
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'product_template',
                            'date_time': datetime.now(),
                            'state': 'success',
                            'message': 'Exported Successfully:- Updated data'
                        })]
                    })
                else:
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'product_template',
                            'date_time': datetime.now(),
                            'state': 'success',
                            'message': 'Enable to Export the Updated data:- Something went Wrong.'
                        })]
                    })
                    return False
            else:
                res = requests.request('POST', sf_config.sf_url + endpoint, headers=headers, data=payload)
                if res.status_code in (200, 201):
                    parsed_resp = json.loads(str(res.text))
                    self.x_salesforce_exported = True
                    self.x_salesforce_id = parsed_resp.get('id')
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'product_template',
                            'date_time': datetime.now(),
                            'state': 'success',
                            'message': 'Exported Successfully'
                        })]
                    })
                else:
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'product_template',
                            'date_time': datetime.now(),
                            'state': 'error',
                            'message': 'Enable to Export Something went Wrong.'
                        })]
                    })
                    return False

    def exportProduct_to_sf(self):
        if len(self) > 1:
            raise UserError(_("Please Select 1 record to Export"))

        ''' PREPARE DICT FOR SENDING TO SALESFORCE '''
        product_dict = {}
        if self.name:
            product_dict['Name'] = self.name
        if self.active:
            product_dict['IsActive'] = 'true'
        else:
            product_dict['IsActive'] = 'false'
        if self.description_sale:
            product_dict['Description'] = self.description_sale
        if self.default_code:
            product_dict['ProductCode'] = self.default_code

        result = self.sendDataToSf(product_dict)
        if result:
            self.x_salesforce_exported = True

    def exportProductTemplate_to_sf(self):
        for prod_temp in self:
            for product in prod_temp.product_variant_ids:
                product.exportProduct_to_sf()
