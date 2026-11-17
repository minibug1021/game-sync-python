"""The Global Link's gateway for the DS (`/dsio/gw` on en.pokemon-gl.com), which handles Game Sync."""
import logging
import random
import struct
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from http import HTTPStatus

from flask import Blueprint, g, request
from flask.typing import ResponseReturnValue

from utils import save_data
from utils.constants import PlayerStatus, is_b2w2
from utils.language import LANGCODES

from ...context import Context
from ...model.avenue.avenue_data import AvenueVisitor
from ...model.pkmn.pkmn_info import PkmnInfo, calculate_is_shiny
from ...model.player.dream_data import DreamEncounter, DreamItem
from ...model.player.player import Player
from ...model.save_file import Pokemon, SaveFile, SaveFileError
from ...paths import RAW_TEXT_DIR
from ...utility import gsid_utility
from ...utility.db_manager import db

logger = logging.getLogger(__name__)

SERVICE = "external"

USERNAME = "pokemon"
PASSWORD = "2Phfv9MY"

HEADER_SIZE = 128
DEFAULT_LANGUAGE = "en"

# Fixed sizes of the data sent when a Pokémon wakes up
MAX_ENCOUNTERS = 10
ENCOUNTER_SIZE = 8
MAX_ITEMS = 20
LOBLOLLY_ITEM_NAME_SIZE = 24  # 12 UTF-16 characters
MAX_VISITORS = 12
VISITOR_SIZE = 32
VISITOR_NAME_SIZE = 16

# Loblolly offers these items. Their names are in raw_text/<language>/loblolly.txt.
LOBLOLLY_ITEM_IDS = (1, 2, 3, 4, 6)


SPECIES_COUNT = 649


def _sleepy_bit_list() -> bytes:
    """Return the species that may be tucked in, one bit per National Pokédex number."""
    bit_list = bytearray(HEADER_SIZE)
    for species in range(1, SPECIES_COUNT + 1):
        bit_list[species // 8] |= 1 << (species % 8)
    return bytes(bit_list)


SLEEPY_BIT_LIST = _sleepy_bit_list()


class PglStatus(IntEnum):
    """The status code at the start of a response."""

    OK = 0
    UNAUTHORIZED = 1  # the Game Sync ID isn't registered
    DUPLICATE_GAME_SYNC_ID = 2
    REGISTRATION_ERROR = 3
    SAVE_DATA_ERROR = 4  # the uploaded save couldn't be used
    NO_SAVE_DATA = 5
    INVALID_GAME_SYNC_ID = 8  # also makes the game offer to create an account
    NOT_BLACK_OR_WHITE = 10


@dataclass
class PglRequest:
    """The query string of a request."""

    type: str  # p
    token: str  # tok
    gscd: str | None = None  # sent as the numeric gsid
    rom: int | None = None
    langcode: int | None = None


# A handler returns the status and the data that follows the header
Handler = Callable[[PglRequest], tuple[PglStatus, bytes]]


def _optional_int(name: str) -> int | None:
    return int(request.args[name]) if name in request.args else None


def _language(language_code: int | None) -> str:
    """Return the raw_text folder for a cartridge's language."""
    if language_code is None:
        return DEFAULT_LANGUAGE
    return LANGCODES.get(language_code, DEFAULT_LANGUAGE)


def _text_lines(language: str, name: str) -> list[str]:
    return (RAW_TEXT_DIR / language / f"{name}.txt").read_text(encoding="UTF-8").splitlines()


def _padded_name(name: str, max_name_bytes: int, field_size: int) -> bytes:
    """Return a UTF-16 name cut to `max_name_bytes`, padded with 0xFF to `field_size` bytes."""
    name_bytes = name.encode("UTF-16-LE")[:max_name_bytes]
    return name_bytes + b"\xff" * (field_size - len(name_bytes))


def _pkmn_info(pokemon: Pokemon) -> PkmnInfo:
    type1, type2 = pokemon.types

    return PkmnInfo(
        pokemon_no=pokemon.natdex,
        form_no=pokemon.form,
        type1=type1,
        type2=type2,
        pokemon_nickname=pokemon.nickname,
        oyaname=pokemon.trainer_name,
        level=pokemon.level,
        sex=pokemon.gender,
        personality=pokemon.nature,
        ball_name=pokemon.ball,
        is_shiny=calculate_is_shiny(pokemon.trainer_id, pokemon.trainer_id_secret, pokemon.personality_value),
    )


def _encounters(encounters: list[DreamEncounter]) -> bytes:
    """Entree Forest encounters, padded to MAX_ENCOUNTERS."""
    encounters = encounters[:MAX_ENCOUNTERS]
    data = b"".join(struct.pack("<HHBBBB", encounter.species, encounter.move, encounter.form, encounter.gender,
                                encounter.animation, 0)
                    for encounter in encounters)
    return data + bytes((MAX_ENCOUNTERS - len(encounters)) * ENCOUNTER_SIZE)


def _items(items: list[DreamItem]) -> bytes:
    """MAX_ITEMS item ids, then MAX_ITEMS quantities."""
    items = items[:MAX_ITEMS]
    padding = MAX_ITEMS - len(items)
    return (struct.pack(f"<{len(items)}H", *(item.pokeitem_id for item in items)) + bytes(padding * 2)
            + bytes(item.item_cnt for item in items) + bytes(padding))


def _loblolly_items(langcode: int | None) -> bytes:
    """The five Loblolly items, in random order."""
    names = _text_lines(_language(langcode), "loblolly")
    return b"".join(struct.pack("<H", item_id) + _padded_name(names[item_id], LOBLOLLY_ITEM_NAME_SIZE,
                                                              LOBLOLLY_ITEM_NAME_SIZE)
                    for item_id in random.sample(LOBLOLLY_ITEM_IDS, len(LOBLOLLY_ITEM_IDS)))


def _avenue_visitors(visitors: list[AvenueVisitor]) -> bytes:
    """Join Avenue visitors, padded to MAX_VISITORS (Black 2 / White 2 only)."""
    visitors = visitors[:MAX_VISITORS]
    data = b""

    for visitor in visitors:
        visitor_type = visitor.trainer_class + visitor.personality * 8
        data += _padded_name(visitor.name, VISITOR_NAME_SIZE - 2, VISITOR_NAME_SIZE)
        data += struct.pack(
            "<BBhiBBBBBBH",
            visitor_type,
            visitor.shop_type + (7 - visitor_type * 2 % 7),
            0,
            1,
            visitor.country_code,
            visitor.state_province_code,
            visitor.game_language_code,
            visitor.game_rom_code,  # affects the shop's stock
            visitor.female,
            0,
            visitor.dreamer_species,
        )

    return data + bytes((MAX_VISITORS - len(visitors)) * VISITOR_SIZE) + struct.pack("<i", 0)


class PglHandler:
    """Handles GET and POST /dsio/gw."""

    def __init__(self, context: Context) -> None:
        self.configuration = context.configuration
        self.dlc_list = context.dlc_list
        self.user_manager = context.user_manager
        self.player_manager = context.player_manager

        self._get_handlers: dict[str, Handler] = {
            "sleepily.bitlist": self.handle_get_sleepy_list,
            "account.playstatus": self.handle_get_account_status,
            "savedata.download": self.handle_download_save_data,
            "savedata.getbw": self.handle_memory_link,
        }
        self._post_handlers: dict[str, Handler] = {
            "savedata.upload": self.handle_upload_save_data,
            "savedata.download.finish": self.handle_download_save_data_finish,
            "account.create.upload": self.handle_create_account,
            "account.createdata": self.handle_create_data,
        }

    def blueprint(self) -> Blueprint:
        blueprint = Blueprint("pgl", __name__)
        blueprint.before_request(self.authorize_pgl_request)
        blueprint.add_url_rule("/dsio/gw", view_func=self.handle_pgl_request, methods=["GET", "POST"])
        return blueprint

    # -------------------
    # Request handling
    # -------------------

    def authorize_pgl_request(self) -> ResponseReturnValue | None:
        """Authorize a request.

        Check the basic-auth login and the session token, and leave the parsed request
        in `g.pgl_request`.
        """
        credentials = request.authorization

        if credentials is None or credentials.username != USERNAME or credentials.password != PASSWORD:
            logger.debug("Rejecting PGL request because the auth credentials were incorrect")
            return "", HTTPStatus.UNAUTHORIZED

        try:
            gsid = _optional_int("gsid")
            pgl_request = PglRequest(
                type=request.args["p"],
                token=request.args["tok"],
                gscd=gsid_utility.gsid_to_gscd(gsid) if gsid is not None else None,
                rom=_optional_int("rom"),
                langcode=_optional_int("langcode"),
            )
        except (KeyError, ValueError):  # a parameter is missing or isn't a number
            logger.exception("Malformed PGL request")
            return "", HTTPStatus.BAD_REQUEST

        logger.debug("Received %s", pgl_request)
        session = self.user_manager.get_service_session(pgl_request.token, SERVICE)

        if session is None:
            logger.debug("Rejecting PGL request because the service session has expired")
            return "", HTTPStatus.UNAUTHORIZED

        g.pgl_request = pgl_request
        return None

    def handle_pgl_request(self) -> ResponseReturnValue:
        """Hands the request to the handler of its type and sends what that wrote."""
        pgl_request: PglRequest = g.pgl_request
        handlers = self._get_handlers if request.method == "GET" else self._post_handlers
        handler = handlers.get(pgl_request.type)

        if handler is None:
            logger.error("Invalid %s request type: %s", request.method, pgl_request.type)
            return "", HTTPStatus.BAD_REQUEST

        status, payload = handler(pgl_request)
        header = struct.pack("<i", status) + bytes(HEADER_SIZE - 4)
        return header + payload, HTTPStatus.OK, {"Content-Type": "application/octet-stream"}

    # -------------------
    # GET handlers
    # -------------------

    def handle_get_sleepy_list(self, req: PglRequest) -> tuple[PglStatus, bytes]:
        """`sleepily.bitlist`: which species may be tucked in."""
        if req.gscd is None or not db.gscd_exists(req.gscd):
            return PglStatus.UNAUTHORIZED, b""
        return PglStatus.OK, SLEEPY_BIT_LIST

    def handle_get_account_status(self, req: PglRequest) -> tuple[PglStatus, bytes]:
        """`account.playstatus`: whether a Pokémon is asleep, dreaming, or ready to wake."""
        player = self.player_manager.load_player(req.gscd)

        if player is None:
            return PglStatus.INVALID_GAME_SYNC_ID, b""
        return PglStatus.OK, struct.pack("<h", player.play_status)

    def handle_download_save_data(self, req: PglRequest) -> tuple[PglStatus, bytes]:
        """`savedata.download`: send everything the Pokémon brings back when it wakes up."""
        player = self.player_manager.load_player(req.gscd)

        if player is None:
            return PglStatus.UNAUTHORIZED, b""

        logger.info("Player %s is downloading save data", player.gscd)

        if player.play_status == PlayerStatus.AWAKE:
            return PglStatus.OK, b""

        b2w2 = is_b2w2(player.rom_id)
        member = db.read(player.gscd, "player_data")["member"]

        # The game stores the tuck-in count and downloads nothing if it gets the same one
        # twice.
        data = struct.pack("<i", member["sleep_pokemon_count"]) + _encounters(player.encounters)
        data += struct.pack(
            "<hBBBBBB",
            player.levels_gained,
            0,
            self.dlc_list.get_dlc_index("MUSICAL", player.musical),
            self.dlc_list.get_dlc_index("CGEAR2" if b2w2 else "CGEAR", player.cgear_skin),
            self.dlc_list.get_dlc_index("ZUKAN", player.dex_skin),
            1,
            0,  # must be zero
        )
        data += _items(player.items) + _loblolly_items(player.langcode)
        data += struct.pack("<h", 0)

        if b2w2:
            data += _avenue_visitors(player.avenue_visitors)

        return PglStatus.OK, data

    def handle_memory_link(self, req: PglRequest) -> tuple[PglStatus, bytes]:
        """Handle `savedata.getbw`.

        Black 2 / White 2 fetches a Black / White save this way.
        """
        player = self.player_manager.load_player(req.gscd)

        if player is None:
            return PglStatus.INVALID_GAME_SYNC_ID, b""
        if is_b2w2(player.rom_id):
            return PglStatus.NOT_BLACK_OR_WHITE, b""
        return PglStatus.NO_SAVE_DATA, b""

    # -------------------
    # POST handlers
    # -------------------

    def handle_download_save_data_finish(self, req: PglRequest) -> tuple[PglStatus, bytes]:
        """`savedata.download.finish`: the DS has saved what it downloaded."""
        player = self.player_manager.load_player(req.gscd)

        if player is None:
            return PglStatus.UNAUTHORIZED, b""

        save_data.update_member({"is_downloaded": 1}, player.gscd)

        if self.configuration.clear_player_dream_info_on_wake:
            player.reset_dream_info()
            self.player_manager.save_player(player)

        return PglStatus.OK, b""

    def handle_upload_save_data(self, req: PglRequest) -> tuple[PglStatus, bytes]:
        """`savedata.upload`: tuck a Pokémon in."""
        player = self.player_manager.load_player(req.gscd)

        if player is None:
            return PglStatus.UNAUTHORIZED, b""

        logger.info("Player %s is uploading save data", player.gscd)

        if player.play_status != PlayerStatus.AWAKE:
            logger.warning("Player %s is not AWAKE -- existing dream information will be overwritten!", player.gscd)

        try:
            save = SaveFile(request.get_data())
            trainer = save.trainer
            pokemon = save.global_link.pokemon

            if pokemon is None:
                raise SaveFileError("No Pokémon is tucked in")

            dreamer_info = _pkmn_info(pokemon)
            rom_id = req.rom if req.rom is not None else trainer.game
            langcode = req.langcode if req.langcode is not None else trainer.language
            medals, favorite_medal = [], None
            if is_b2w2(rom_id):
                medals, favorite_medal = save.medals.medal_list, save.medals.favorite_medal
        except (SaveFileError, IndexError, ValueError):
            logger.exception("Could not read the save data uploaded by player %s", player.gscd)
            return PglStatus.SAVE_DATA_ERROR, b""

        if player.rom_id is not None and rom_id != player.rom_id:
            logger.warning("Player %s's game version changed from %s to %s", player.gscd, player.rom_id, rom_id)

        player.player_name = trainer.name
        player.country = trainer.country
        player.region = trainer.region
        player.trainer_gender = trainer.gender
        player.player_badge_num = save.num_badges
        player.hours_played = trainer.played_hours
        player.minutes_played = trainer.played_minutes
        player.loblolly_decor = save.global_link.loblolly_decor

        player.play_status = PlayerStatus.PLAY_READY
        player.rom_id = rom_id
        player.langcode = langcode
        player.dreamer_info = dreamer_info
        player.medals = medals
        player.favorite_medal = favorite_medal

        self.player_manager.save_player(player)
        self._record_tuck_in(player)
        return PglStatus.OK, b""

    def handle_create_account(self, req: PglRequest) -> tuple[PglStatus, bytes]:
        """`account.create.upload`: registers the Game Sync ID in the query string."""
        return self._register(req.gscd, req.rom, req.langcode), b""

    def handle_create_data(self, req: PglRequest) -> tuple[PglStatus, bytes]:
        """`account.createdata`: registers the Game Sync ID in the body."""
        raw_body = request.get_data(as_text=True).replace("\u0000", "")

        try:
            gscd = gsid_utility.gsid_to_gscd(int(raw_body))
        except ValueError:
            logger.debug("[account.createdata] Rejecting invalid Game Sync ID: %s", raw_body)
            return PglStatus.INVALID_GAME_SYNC_ID, b""

        return self._register(gscd, None, None), b""

    def _register(self, gscd: str | None, rom_id: int | None, langcode: int | None) -> PglStatus:
        if gscd is None or not gsid_utility.is_valid_gscd(gscd):
            return PglStatus.INVALID_GAME_SYNC_ID
        if db.gscd_exists(gscd):
            return PglStatus.DUPLICATE_GAME_SYNC_ID
        self.player_manager.register_player(gscd, rom_id, langcode)
        return PglStatus.OK

    # -------------------
    # Tuck-in data
    # -------------------

    def _record_tuck_in(self, player: Player) -> None:
        """Update the member fields that the Dream World server keeps about a tuck-in."""
        now = save_data.now_jst_str()
        timestamp = int(datetime.now().timestamp())

        def mark_tucked_in(member: dict) -> None:
            member.update({
                "sleeping_flag":            1,
                "is_downloaded":            0,
                "is_initializing":          0,
                "sleep_pokemon_count":      member.get("sleep_pokemon_count", 0) + 1,
                "pdw_copied_at":            now,
                "last_up_time_strict":      now,
                "last_started_at_timezone": timestamp,
            })

        save_data.change_member(mark_tucked_in, player.gscd)
