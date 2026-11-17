"""The download server (dls1.nintendowifi.net).

The DS fetches skins and musicals from it after waking a Pokémon up.
"""
import logging
from dataclasses import dataclass
from http import HTTPStatus

from flask import Blueprint, request
from flask.typing import ResponseReturnValue

from ...context import Context
from ...model.dlc.dlc import dlc_list_string
from ...utility.url_encoded_form import decode_form

logger = logging.getLogger(__name__)

SERVICE = "dls1.nintendowifi.net"
@dataclass
class DlsRequest:
    token: str
    action: str
    dlc_type: str = ""  # attr1 without the language
    language: str | None = None  # attr1's suffix
    dlc_index: int | None = None  # attr2
    dlc_name: str | None = None  # contents


class DlsHandler:
    """Handles POST /download."""

    def __init__(self, context: Context) -> None:
        self.dlc_list = context.dlc_list
        self.user_manager = context.user_manager
        self._actions = {
            "list": self.handle_retrieve_dlc_list,
            "contents": self.handle_retrieve_dlc_content,
        }

    def blueprint(self) -> Blueprint:
        """Return the routes of this handler."""
        blueprint = Blueprint("dls", __name__)
        blueprint.add_url_rule("/download", view_func=self.handle_download_request, methods=["POST"])
        return blueprint

    def handle_download_request(self) -> ResponseReturnValue:
        """Handle a download server request."""
        try:
            form = decode_form(request.get_data(as_text=True))
            dlc_type, _, language = form.get("attr1", "").partition("_")  # "CGEAR2_E"
            dls_request = DlsRequest(
                token=form["token"],
                action=form["action"],
                dlc_type=dlc_type,
                language=language or None,
                dlc_index=int(form["attr2"]) if form.get("attr2") else None,
                dlc_name=form.get("contents"),
            )
        except (KeyError, ValueError):
            logger.exception("Malformed DLS request")
            return "", HTTPStatus.BAD_REQUEST

        logger.debug("Received %s", dls_request)
        session = self.user_manager.get_service_session(dls_request.token, SERVICE)

        if session is None:
            logger.debug("Rejecting DLS request because the service session has expired")
            return "", HTTPStatus.UNAUTHORIZED

        handler = self._actions.get(dls_request.action)

        if handler is None:
            logger.error("Invalid DLS request action: %s", dls_request.action)
            return "", HTTPStatus.BAD_REQUEST

        return handler(dls_request)

    def handle_retrieve_dlc_list(self, req: DlsRequest) -> ResponseReturnValue:
        """List the DLC of a type."""
        return dlc_list_string(self.dlc_list.get_dlc_list(req.dlc_type, req.language, req.dlc_index))

    def handle_retrieve_dlc_content(self, req: DlsRequest) -> ResponseReturnValue:
        """Send a DLC file."""
        dlc = self.dlc_list.get_dlc(req.dlc_type, req.dlc_name, req.language)

        if dlc is None:
            return "", HTTPStatus.NOT_FOUND

        return dlc.path.read_bytes()
