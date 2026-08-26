"""Config flow per Controllo Accessi."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import DOMAIN


class AccessControlConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup iniziale.

    Si chiede qui solo ciò che serve per partire; tessere, varchi, hook e
    soglie si gestiscono dal pannello, dove c'è lo spazio per farlo bene e
    dove le modifiche non richiedono di ricaricare l'integration.
    """

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="Controllo Accessi", data=user_input)

        schema = vol.Schema(
            {
                vol.Optional("person_entities", default=[]): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="person", multiple=True)
                ),
                vol.Optional("nearby_zone"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="zone")
                ),
                vol.Optional("door_lock_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="lock")
                ),
                vol.Optional("door_contact_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="binary_sensor",
                        device_class=["door", "opening", "window"],
                    )
                ),
                vol.Optional("camera_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="camera")
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)
