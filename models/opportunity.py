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
        # Define fields that should trigger a sync
        synced_fields = {
            "name", "planned_revenue", "expected_revenue", "active",
            "partner_id", "user_id", "stage_id", "ghl_skip_sync"
        }
        
        # Check if any synced field is in vals
        if not any(field in vals for field in synced_fields):
            return res

        if (
            cfg["sync_opportunities"]
            and cfg["sync_direction"] in ("odoo_to_ghl", "both")
            and cfg["sync_on"] == "create_update"
        ):
            for lead in self:
                if not lead.ghl_skip_sync and lead.type == "opportunity":
                    backend.push_opportunity(lead)
        return res
