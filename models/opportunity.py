# odoo_gohighlevel_connector/models/opportunity.py
from odoo import api, fields, models


class CrmLead(models.Model):
    _inherit = ["crm.lead", "ghl.sync.mixin"]
    _name = "crm.lead"

    ghl_pipeline_id = fields.Char("GHL Pipeline ID")
    ghl_stage_id = fields.Char("GHL Stage ID")

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("ghl_sync_running"):
            return super().create(vals_list)
        leads = super().create(vals_list)
        backend = self.env["odoo.ghl.backend"]
        cfg = backend._get_config()
        if (
            cfg["sync_opportunities"]
            and cfg["sync_direction"] in ("odoo_to_ghl", "both")
            and cfg["sync_on"] == "create_update"
        ):
            for lead in leads:
                if not lead.ghl_skip_sync and lead.type == "opportunity":
                    backend.push_opportunity(lead)
        return leads

    def write(self, vals):
        if self.env.context.get("ghl_sync_running"):
            return super().write(vals)
        res = super().write(vals)
        backend = self.env["odoo.ghl.backend"]
        cfg = backend._get_config()
        if (
            cfg["sync_opportunities"]
            and cfg["sync_direction"] in ("odoo_to_ghl", "both")
            and cfg["sync_on"] == "create_update"
        ):
            for lead in self:
                if not lead.ghl_skip_sync and lead.type == "opportunity":
                    backend.push_opportunity(lead)
        return res
