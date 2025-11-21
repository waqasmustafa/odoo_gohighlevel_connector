# odoo_gohighlevel_connector/models/task.py
from odoo import api, models


class ProjectTask(models.Model):
    _inherit = ["project.task", "ghl.sync.mixin"]
    _name = "project.task"

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("ghl_sync_running"):
            return super().create(vals_list)
        tasks = super().create(vals_list)
        backend = self.env["odoo.ghl.backend"]
        cfg = backend._get_config()
        if (
            cfg["sync_tasks"]
            and cfg["sync_direction"] in ("odoo_to_ghl", "both")
            and cfg["sync_on"] == "create_update"
        ):
            for t in tasks:
                if not t.ghl_skip_sync:
                    backend.push_task(t)
        return tasks

    def write(self, vals):
        if self.env.context.get("ghl_sync_running"):
            return super().write(vals)
        res = super().write(vals)
        backend = self.env["odoo.ghl.backend"]
        cfg = backend._get_config()
        # Define fields that should trigger a sync
        synced_fields = {
            "name", "description", "date_deadline", "user_ids",
            "partner_id", "ghl_skip_sync"
        }
        
        # Check if any synced field is in vals
        if not any(field in vals for field in synced_fields):
            return res

        if (
            cfg["sync_tasks"]
            and cfg["sync_direction"] in ("odoo_to_ghl", "both")
            and cfg["sync_on"] == "create_update"
        ):
            for t in self:
                if not t.ghl_skip_sync:
                    backend.push_task(t)
        return res
