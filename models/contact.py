# odoo_gohighlevel_connector/models/contact.py
from odoo import api, models


class ResPartner(models.Model):
    _inherit = ["res.partner", "ghl.sync.mixin"]
    _name = "res.partner"

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("ghl_sync_running"):
            return super().create(vals_list)
        partners = super().create(vals_list)
        backend = self.env["odoo.ghl.backend"]
        cfg = backend._get_config()
        if (
            cfg["sync_contacts"]
            and cfg["sync_direction"] in ("odoo_to_ghl", "both")
            and cfg["sync_on"] == "create_update"
        ):
            for partner in partners:
                if not partner.ghl_skip_sync and not partner.is_company:
                    backend.push_contact(partner)
        return partners

    def write(self, vals):
        if self.env.context.get("ghl_sync_running"):
            return super().write(vals)
        res = super().write(vals)
        backend = self.env["odoo.ghl.backend"]
        cfg = backend._get_config()
        # Define fields that should trigger a sync
        synced_fields = {
            "name", "email", "phone", "mobile", "street", "street2", "city",
            "zip", "state_id", "country_id", "category_id", "parent_id",
            "company_name", "user_id", "ghl_skip_sync", "website"
        }
        
        # Check if any synced field is in vals
        if not any(field in vals for field in synced_fields):
            return res

        if (
            cfg["sync_contacts"]
            and cfg["sync_direction"] in ("odoo_to_ghl", "both")
            and cfg["sync_on"] == "create_update"
        ):
            for partner in self:
                if not partner.ghl_skip_sync and not partner.is_company:
                    backend.push_contact(partner)
        return res
