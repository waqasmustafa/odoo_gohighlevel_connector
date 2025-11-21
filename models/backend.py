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

    # ---------------------------------------------------------------
    # Utility for date parsing
    # ---------------------------------------------------------------
    @staticmethod
    def _parse_remote_dt(value):
        if not value:
            return False
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
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

        payload = {
            "locationId": cfg["location_id"],
            "firstName": partner.name,
            "email": partner.email,
            "phone": partner.mobile or partner.phone,
            "address1": partner.street or "",
            "city": partner.city or "",
            "state": partner.state_id and partner.state_id.name or "",
            "postalCode": partner.zip or "",
            "country": partner.country_id and partner.country_id.code or "",
            "type": "customer",
        }

        endpoint = "/contacts/"
        method = "POST"
        if partner.ghl_id:
            endpoint = f"/contacts/{partner.ghl_id}"
            method = "PUT"

        data = self._request(method, endpoint, cfg["api_token"], payload=payload)
        contact = data.get("contact") or data
        ghl_id = contact.get("id")
        updated_at = contact.get("dateUpdated") or contact.get("updatedAt")

        if ghl_id:
            partner.write(
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

            if partner:
                partner.write(vals)
            else:
                vals.update(
                    {
                        "ghl_id": ghl_id,
                        "ghl_remote_updated_at": updated_at,
                        "ghl_last_synced_at": fields.Datetime.now(),
                    }
                )
                Partner.create(vals)

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
            "monetaryValue": lead.planned_revenue or lead.expected_revenue or 0.0,
            "status": "open" if lead.active else "closed",
            "contactId": lead.partner_id and lead.partner_id.ghl_id or None,
        }

        endpoint = "/opportunities/"  # TODO: confirm in your GHL docs
        method = "POST"
        if lead.ghl_id:
            endpoint = f"/opportunities/{lead.ghl_id}"
            method = "PUT"

        data = self._request(method, endpoint, cfg["api_token"], payload=payload)
        opp = data.get("opportunity") or data
        ghl_id = opp.get("id")
        updated_at = opp.get("updatedAt")

        if ghl_id:
            lead.write(
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
            "locationId": cfg["location_id"],
            "limit": limit,
        }
        if cfg["last_opportunity_pull"]:
            params["updatedAt__gt"] = cfg["last_opportunity_pull"]

        Lead = self.env["crm.lead"].sudo()
        latest = cfg["last_opportunity_pull"] and self._parse_remote_dt(
            cfg["last_opportunity_pull"]
        )

        # TODO: adjust endpoint/response once you confirm GHL opportunity API
        data = self._request("GET", "/opportunities/", cfg["api_token"], params=params)
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
                "planned_revenue": o.get("monetaryValue") or 0.0,
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

            if lead:
                lead.write(vals)
            else:
                vals.update(
                    {
                        "ghl_id": ghl_id,
                        "ghl_remote_updated_at": updated_at,
                        "ghl_last_synced_at": fields.Datetime.now(),
                    }
                )
                Lead.create(vals)

        if latest:
            self._save_last_pull(opportunity=latest.isoformat())

    # =================================================================
    # TASKS / NOTES: placeholders (we wire structure)
    # =================================================================
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
        endpoint = "/tasks/"
        method = "POST"
        if task.ghl_id:
            endpoint = f"/tasks/{task.ghl_id}"
            method = "PUT"

        data = self._request(method, endpoint, cfg["api_token"], payload=payload)
        t = data.get("task") or data
        ghl_id = t.get("id")
        updated_at = t.get("updatedAt")
        if ghl_id:
            task.write(
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
            note.write(
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
