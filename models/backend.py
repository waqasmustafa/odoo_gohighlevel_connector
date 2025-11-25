# odoo_gohighlevel_connector/models/backend.py
import logging
from datetime import datetime

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OdooGHLBackend(models.AbstractModel):
    _name = "odoo.ghl.backend"
    _description = "GoHighLevel Sync Backend"

    # ---------------------------------------------------------------
    # Read config from ir.config_parameter
    # ---------------------------------------------------------------
    @api.model
    def _get_config(self):
        ICP = self.env["ir.config_parameter"].sudo()
        return {
            "api_token": ICP.get_param("odoo_ghl.api_token") or "",
            "location_id": ICP.get_param("odoo_ghl.location_id") or "",
            "sync_on": ICP.get_param("odoo_ghl.sync_on", default="create_update"),
            "sync_direction": ICP.get_param(
                "odoo_ghl.sync_direction", default="both"
            ),
            "sync_contacts": ICP.get_param(
                "odoo_ghl.sync_contacts", default="True"
            )
            == "True",
            "sync_opportunities": ICP.get_param(
                "odoo_ghl.sync_opportunities", default="True"
            )
            == "True",
            "sync_tasks": ICP.get_param("odoo_ghl.sync_tasks", default="False")
            == "True",
            "sync_notes": ICP.get_param("odoo_ghl.sync_notes", default="False")
            == "True",
            "last_contact_pull": ICP.get_param("odoo_ghl.last_contact_pull") or None,
            "last_opportunity_pull": ICP.get_param(
                "odoo_ghl.last_opportunity_pull"
            )
            or None,
            "last_task_pull": ICP.get_param("odoo_ghl.last_task_pull") or None,
            "last_note_pull": ICP.get_param("odoo_ghl.last_note_pull") or None,
        }

    @api.model
    def _save_last_pull(
        self, contact=None, opportunity=None, task=None, note=None
    ):
        settings = self.env["res.config.settings"]
        settings._set_last_pull(
            contact=contact, opportunity=opportunity, task=task, note=note
        )

    # ---------------------------------------------------------------
    # HTTP helper
    # ---------------------------------------------------------------
    @api.model
    def _base_headers(self, api_token):
        if not api_token:
            raise UserError(
                _(
                    "GoHighLevel API token is not configured.\n"
                    "Go to Settings → General Settings → GoHighLevel Sync."
                )
            )
        return {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Version": "2021-07-28",
        }

    @api.model
    def _request(self, method, endpoint, api_token, params=None, payload=None):
        base_url = "https://services.leadconnectorhq.com"
        url = f"{base_url}{endpoint}"
        headers = self._base_headers(api_token)

        _logger.info(
            "GHL API %s %s params=%s payload=%s", method, url, params, payload
        )

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params or {},
                json=payload,
                timeout=30,
            )
        except Exception as e:
            _logger.exception("GHL API connection error: %s", e)
            raise UserError(_("Could not connect to GoHighLevel API:\n%s") % e)

        if response.status_code >= 400:
            _logger.error(
                "GHL API error %s %s: %s",
                response.status_code,
                url,
                response.text,
            )
            raise UserError(
                _("GoHighLevel API error %s:\n%s")
                % (response.status_code, response.text)
            )

        if not response.text:
            return {}
        try:
            return response.json()
        except Exception:
            _logger.warning("GHL API non-JSON response: %s", response.text)
            return {}

    @api.model
    def test_api_connection(self, api_token, location_id):
        """Test the API connection with provided credentials."""
        if not api_token or not location_id:
            raise UserError(_("Please enter both API Token and Location ID."))
        
        # Try to fetch 1 contact to verify access
        endpoint = "/contacts/"
        params = {"locationId": location_id, "limit": 1}
        
        try:
            self._request("GET", endpoint, api_token, params=params)
            return True
        except Exception as e:
            raise UserError(_("Connection Failed:\n%s") % str(e))

    # ---------------------------------------------------------------
    # Utility for date parsing
    # ---------------------------------------------------------------
    @staticmethod
    def _parse_remote_dt(value):
        if not value:
            return False
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        except Exception:
            return False

    # =================================================================
    # CONTACTS – PUSH & PULL
    # =================================================================
    @api.model
    def push_contact(self, partner):
        cfg = self._get_config()
        if not cfg["sync_contacts"] or partner.ghl_skip_sync:
            return
        if cfg["sync_direction"] not in ("odoo_to_ghl", "both"):
            return
        
        # Prevent infinite loop
        if self.env.context.get("ghl_sync_running"):
            return

        # Tags
        tags = [t.name for t in partner.category_id]

        # Company Name
        company_name = partner.parent_id.name if partner.parent_id else (partner.company_name or "")

        payload = {
            "locationId": cfg["location_id"],
            "firstName": partner.name,
            "address1": partner.street or "",
            "city": partner.city or "",
            "state": partner.state_id and partner.state_id.name or "",
            "postalCode": partner.zip or "",
            "tags": tags,
            "companyName": company_name,
            "type": "customer",
            "website": partner.website or "",
        }

        if partner.email:
            payload["email"] = partner.email
        if partner.mobile or partner.phone:
            payload["phone"] = partner.mobile or partner.phone

        if partner.country_id and partner.country_id.code:
            payload["country"] = partner.country_id.code

        # Assignee (User Mapping)
        if partner.user_id:
            mapping = self.env["ghl.user.mapping"].search([("odoo_user_id", "=", partner.user_id.id)], limit=1)
            if mapping:
                payload["assignedTo"] = mapping.ghl_user_id

        # Lead Source
        # if partner.source_id: # Assuming you want to sync Odoo Source -> GHL Source (requires string match or mapping)
        #     payload["source"] = partner.source_id.name

        endpoint = "/contacts/"
        method = "POST"
        if partner.ghl_id:
            endpoint = f"/contacts/{partner.ghl_id}"
            method = "PUT"
            if "locationId" in payload:
                del payload["locationId"]

        try:
            data = self._request(method, endpoint, cfg["api_token"], payload=payload)
        except UserError as e:
            # Handle Duplicate Contact (400)
            error_msg = str(e)
            if "This location does not allow duplicated contacts" in error_msg:
                # Extract contactId from error message if possible
                # The error message from GHL is JSON inside the exception string
                import json
                import re
                
                # Try to find JSON part
                match = re.search(r'(\{.*\})', error_msg)
                if match:
                    try:
                        err_json = json.loads(match.group(1))
                        existing_id = err_json.get("meta", {}).get("contactId")
                        if existing_id:
                            _logger.info("Found existing GHL contact %s, linking and updating.", existing_id)
                            partner.with_context(ghl_sync_running=True).write({"ghl_id": existing_id})
                            # Retry as PUT
                            endpoint = f"/contacts/{existing_id}"
                            method = "PUT"
                            if "locationId" in payload:
                                del payload["locationId"]
                            data = self._request(method, endpoint, cfg["api_token"], payload=payload)
                        else:
                            raise e
                    except Exception:
                        raise e
                else:
                    raise e
            else:
                self.env["ghl.sync.queue"].create({
                    "name": partner.name,
                    "model_name": "res.partner",
                    "record_id": partner.id,
                    "action": "push",
                    "error_message": str(e),
                    "state": "failed"
                })
                raise e
        except Exception as e:
            self.env["ghl.sync.queue"].create({
                "name": partner.name,
                "model_name": "res.partner",
                "record_id": partner.id,
                "action": "push",
                "error_message": str(e),
                "state": "failed"
            })
            raise e
        contact = data.get("contact") or data
        ghl_id = contact.get("id")
        updated_at = contact.get("dateUpdated") or contact.get("updatedAt")

        if ghl_id:
            partner.with_context(ghl_sync_running=True).write(
                {
                    "ghl_id": ghl_id,
                    "ghl_remote_updated_at": self._parse_remote_dt(updated_at),
                    "ghl_last_synced_at": fields.Datetime.now(),
                }
            )

    @api.model
    def pull_contacts(self, limit=100):
        cfg = self._get_config()
        if not cfg["sync_contacts"]:
            return
        if cfg["sync_direction"] not in ("ghl_to_odoo", "both"):
            return

        params = {
            "locationId": cfg["location_id"],
            "limit": limit,
        }

        if cfg["last_contact_pull"]:
            params["updatedAt__gt"] = cfg["last_contact_pull"]

        Partner = self.env["res.partner"].sudo()
        latest = cfg["last_contact_pull"] and self._parse_remote_dt(
            cfg["last_contact_pull"]
        )

        data = self._request("GET", "/contacts/", cfg["api_token"], params=params)
        contacts = data.get("contacts") or data.get("items") or []

        for c in contacts:
            ghl_id = c.get("id")
            if not ghl_id:
                continue

            updated_at = self._parse_remote_dt(
                c.get("dateUpdated") or c.get("updatedAt")
            )
            if latest is None or (updated_at and updated_at > latest):
                latest = updated_at

            partner = Partner.search([("ghl_id", "=", ghl_id)], limit=1)

            vals = {
                "name": c.get("contactName")
                or c.get("firstName")
                or c.get("fullNameLowerCase")
                or "Unknown",
                "email": c.get("email"),
                "phone": c.get("phone"),
                "street": c.get("address1"),
                "city": c.get("city"),
                "zip": c.get("postalCode"),
            }

            # Country
            country_code = c.get("country")
            if country_code:
                country = self.env["res.country"].sudo().search(
                    [("code", "=", country_code)], limit=1
                )
                if country:
                    vals["country_id"] = country.id

            # Tags
            ghl_tags = c.get("tags") or []
            if ghl_tags:
                tag_ids = []
                for tag_name in ghl_tags:
                    tag = self.env["res.partner.category"].sudo().search([("name", "=", tag_name)], limit=1)
                    if not tag:
                        tag = self.env["res.partner.category"].sudo().create({"name": tag_name})
                    tag_ids.append(tag.id)
                vals["category_id"] = [(6, 0, tag_ids)]

            # Company (Try to link to existing company by name)
            ghl_company = c.get("companyName")
            if ghl_company:
                company_partner = self.env["res.partner"].sudo().search(
                    [("name", "=", ghl_company), ("is_company", "=", True)], limit=1
                )
                if company_partner:
                    vals["parent_id"] = company_partner.id
                # Optional: Create company if not found? For now, we only link if exists to avoid duplicates.

            if partner:
                partner.with_context(ghl_sync_running=True).write(vals)
            else:
                vals.update(
                    {
                        "ghl_id": ghl_id,
                        "ghl_remote_updated_at": updated_at,
                        "ghl_last_synced_at": fields.Datetime.now(),
                    }
                )
                Partner.with_context(ghl_sync_running=True).create(vals)

        if latest:
            self._save_last_pull(contact=latest.isoformat())

    # =================================================================
    # OPPORTUNITIES – PUSH & PULL (SKELETON)
    # =================================================================
    @api.model
    def push_opportunity(self, lead):
        cfg = self._get_config()
        if not cfg["sync_opportunities"] or lead.ghl_skip_sync:
            return
        if cfg["sync_direction"] not in ("odoo_to_ghl", "both"):
            return

        payload = {
            "locationId": cfg["location_id"],
            "name": lead.name,
            "monetaryValue": lead.expected_revenue or 0.0,
            "status": "open" if lead.active else "closed",
            "status": "open" if lead.active else "closed",
            "contactId": lead.partner_id and lead.partner_id.ghl_id or None,
        }

        # Assignee
        if lead.user_id:
            mapping = self.env["ghl.user.mapping"].search([("odoo_user_id", "=", lead.user_id.id)], limit=1)
            if mapping:
                payload["assignedTo"] = mapping.ghl_user_id

        # Pipeline & Stage
        if lead.stage_id:
            stage_mapping = self.env["ghl.pipeline.mapping"].search([("odoo_stage_id", "=", lead.stage_id.id)], limit=1)
            if stage_mapping:
                payload["pipelineId"] = stage_mapping.ghl_pipeline_id
                payload["pipelineStageId"] = stage_mapping.ghl_stage_id  # Use pipelineStageId not stageId
            else:
                # Raise error if mapping is missing, otherwise GHL will reject with 422
                raise UserError(_(
                    "GoHighLevel Sync Error: No Pipeline Mapping found for Odoo Stage '%s'. "
                    "Please go to GoHighLevel > Configuration > Pipeline Mapping and configure it."
                ) % lead.stage_id.name)

        endpoint = "/opportunities/"  # TODO: confirm in your GHL docs
        method = "POST"
        if lead.ghl_id:
            endpoint = f"/opportunities/{lead.ghl_id}"
            method = "PUT"
            # Remove locationId for PUT requests (GHL rejects it)
            payload.pop("locationId", None)

        try:
            data = self._request(method, endpoint, cfg["api_token"], payload=payload)
        except Exception as e:
            self.env["ghl.sync.queue"].create({
                "name": lead.name,
                "model_name": "crm.lead",
                "record_id": lead.id,
                "action": "push",
                "error_message": str(e),
                "state": "failed"
            })
            raise e
        opp = data.get("opportunity") or data
        ghl_id = opp.get("id")
        updated_at = opp.get("updatedAt")

        if ghl_id:
            lead.with_context(ghl_sync_running=True).write(
                {
                    "ghl_id": ghl_id,
                    "ghl_remote_updated_at": self._parse_remote_dt(updated_at),
                    "ghl_last_synced_at": fields.Datetime.now(),
                }
            )

    @api.model
    def pull_opportunities(self, limit=100):
        cfg = self._get_config()
        if not cfg["sync_opportunities"]:
            return
        if cfg["sync_direction"] not in ("ghl_to_odoo", "both"):
            return

        params = {
            "location_id": cfg["location_id"],
            "limit": limit,
        }
        if cfg["last_opportunity_pull"]:
            params["updatedAt__gt"] = cfg["last_opportunity_pull"]

        Lead = self.env["crm.lead"].sudo()
        latest = cfg["last_opportunity_pull"] and self._parse_remote_dt(
            cfg["last_opportunity_pull"]
        )

        # Use /opportunities/search to list opportunities
        data = self._request("GET", "/opportunities/search", cfg["api_token"], params=params)
        opportunities = data.get("opportunities") or data.get("items") or []

        for o in opportunities:
            ghl_id = o.get("id")
            if not ghl_id:
                continue

            updated_at = self._parse_remote_dt(o.get("updatedAt"))
            if latest is None or (updated_at and updated_at > latest):
                latest = updated_at

            lead = Lead.search([("ghl_id", "=", ghl_id)], limit=1)

            vals = {
                "name": o.get("name"),
                "expected_revenue": o.get("monetaryValue") or 0.0,
                "type": "opportunity",
                "active": o.get("status") != "closed",
            }

            contact_id = o.get("contactId")
            if contact_id:
                partner = self.env["res.partner"].sudo().search(
                    [("ghl_id", "=", contact_id)], limit=1
                )
                if partner:
                    vals["partner_id"] = partner.id

            # Map GHL stage to Odoo stage
            ghl_pipeline_id = o.get("pipelineId")
            ghl_stage_id = o.get("pipelineStageId")
            if ghl_pipeline_id and ghl_stage_id:
                stage_mapping = self.env["ghl.pipeline.mapping"].sudo().search([
                    ("ghl_pipeline_id", "=", ghl_pipeline_id),
                    ("ghl_stage_id", "=", ghl_stage_id)
                ], limit=1)
                if stage_mapping and stage_mapping.odoo_stage_id:
                    vals["stage_id"] = stage_mapping.odoo_stage_id.id

            # Map GHL user to Odoo user
            ghl_assigned_to = o.get("assignedTo")
            if ghl_assigned_to:
                user_mapping = self.env["ghl.user.mapping"].sudo().search([
                    ("ghl_user_id", "=", ghl_assigned_to)
                ], limit=1)
                if user_mapping and user_mapping.odoo_user_id:
                    vals["user_id"] = user_mapping.odoo_user_id.id
                else:
                    # GHL user not mapped, leave unassigned
                    vals["user_id"] = False
            else:
                # No assignment in GHL, unassign in Odoo
                vals["user_id"] = False

            if lead:
                lead.with_context(ghl_sync_running=True).write(vals)
            else:
                vals.update(
                    {
                        "ghl_id": ghl_id,
                        "ghl_remote_updated_at": updated_at,
                        "ghl_last_synced_at": fields.Datetime.now(),
                    }
                )
                Lead.with_context(ghl_sync_running=True).create(vals)

        if latest:
            self._save_last_pull(opportunity=latest.isoformat())

    # =================================================================
    # PIPELINES – FETCH
    # =================================================================
    @api.model
    def get_pipelines(self):
        cfg = self._get_config()
        params = {"locationId": cfg["location_id"]}
        data = self._request("GET", "/opportunities/pipelines", cfg["api_token"], params=params)
        return data.get("pipelines", [])

    # =================================================================
    # USERS – FETCH
    # =================================================================
    @api.model
    def get_users(self):
        cfg = self._get_config()
        params = {"locationId": cfg["location_id"]}
        data = self._request("GET", "/users/", cfg["api_token"], params=params)
        return data.get("users", [])
    @api.model
    def push_task(self, task):
        cfg = self._get_config()
        if not cfg["sync_tasks"] or task.ghl_skip_sync:
            return
        if cfg["sync_direction"] not in ("odoo_to_ghl", "both"):
            return

        # TODO: adjust to actual GHL task API
        payload = {
            "locationId": cfg["location_id"],
            "title": task.name,
            "description": task.description or "",
            "dueDate": task.date_deadline and task.date_deadline.isoformat(),
        }
        
        # Assignee
        if task.user_ids:
            # GHL tasks usually have one assignee, take the first one
            user = task.user_ids[0]
            mapping = self.env["ghl.user.mapping"].search([("odoo_user_id", "=", user.id)], limit=1)
            if mapping:
                payload["assignedTo"] = mapping.ghl_user_id
        
        # Related Contact
        if task.partner_id and task.partner_id.ghl_id:
            payload["contactId"] = task.partner_id.ghl_id
        endpoint = "/tasks/"
        method = "POST"
        if task.ghl_id:
            endpoint = f"/tasks/{task.ghl_id}"
            method = "PUT"

        try:
            data = self._request(method, endpoint, cfg["api_token"], payload=payload)
        except Exception as e:
            self.env["ghl.sync.queue"].create({
                "name": task.name,
                "model_name": "project.task",
                "record_id": task.id,
                "action": "push",
                "error_message": str(e),
                "state": "failed"
            })
            raise e
        t = data.get("task") or data
        ghl_id = t.get("id")
        updated_at = t.get("updatedAt")
        if ghl_id:
            task.with_context(ghl_sync_running=True).write(
                {
                    "ghl_id": ghl_id,
                    "ghl_remote_updated_at": self._parse_remote_dt(updated_at),
                    "ghl_last_synced_at": fields.Datetime.now(),
                }
            )

    @api.model
    def pull_tasks(self):
        cfg = self._get_config()
        if not cfg["sync_tasks"]:
            return
        if cfg["sync_direction"] not in ("ghl_to_odoo", "both"):
            return
        # TODO: implement when GHL task API confirmed

    @api.model
    def push_note(self, note):
        cfg = self._get_config()
        if not cfg["sync_notes"] or note.ghl_skip_sync:
            return
        if cfg["sync_direction"] not in ("odoo_to_ghl", "both"):
            return

        # TODO: adjust to actual GHL notes/comments API
        payload = {
            "locationId": cfg["location_id"],
            "content": note.body or "",
        }
        endpoint = "/notes/"
        method = "POST"
        if note.ghl_id:
            endpoint = f"/notes/{note.ghl_id}"
            method = "PUT"

        data = self._request(method, endpoint, cfg["api_token"], payload=payload)
        n = data.get("note") or data
        ghl_id = n.get("id")
        updated_at = n.get("updatedAt")
        if ghl_id:
            note.with_context(ghl_sync_running=True).write(
                {
                    "ghl_id": ghl_id,
                    "ghl_remote_updated_at": self._parse_remote_dt(updated_at),
                    "ghl_last_synced_at": fields.Datetime.now(),
                }
            )

    @api.model
    def pull_notes(self):
        cfg = self._get_config()
        if not cfg["sync_notes"]:
            return
        if cfg["sync_direction"] not in ("ghl_to_odoo", "both"):
            return
        # TODO: implement when GHL notes API confirmed

    # =================================================================
    # CRONS + MANUAL SYNC BUTTON
    # =================================================================
    @api.model
    def cron_poll_changes(self):
        """Called by cron: incremental polling GHL → Odoo."""
        cfg = self._get_config()
        if cfg["sync_contacts"]:
            self.pull_contacts()
        if cfg["sync_opportunities"]:
            self.pull_opportunities()
        if cfg["sync_tasks"]:
            self.pull_tasks()
        if cfg["sync_notes"]:
            self.pull_notes()

    @api.model
    def cron_nightly_reconciliation(self):
        """Called nightly to reset timestamps and re-poll."""
        self.env["res.config.settings"]._reset_last_pull()
        self.cron_poll_changes()

    @api.model
    def manual_sync_now(self):
        """Called from Settings 'Sync Now' button."""
        self.cron_poll_changes()
