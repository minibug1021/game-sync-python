#!/usr/bin/env python3
import logging

import io
from pathlib import Path
from random import randint
from http import HTTPStatus
from dataclasses import dataclass
from flask import request, Blueprint, g

from model.user.user import User
from model.dlc.dlc import DlcList, Dlc
from model.pkmn.pkmn_info import PkmnInfo, PkmnNature
from model.pkmn.pkmn_reader import Pokemon, SaveFile
from model.user.user_manager import UserManager
from model.player.player import PlayerStatus, Player
from model.player.player_manager import PlayerManager
from utility.gsid_utility import GsidUtility
from utility.le_input_output import LEOutputStream
from configuration import Configuration

logger = logging.getLogger(__name__)

@dataclass
class PglRequest:
    p: str
    tok: str
    gsid: str = None
    rom: int = None
    langcode: int = None
    dreamw: int = None

    def __post_init__(self):
        if self.gsid is not None:
            try:
                self.gsid = GsidUtility.stringify_gamesync_id(int(self.gsid))
            except ValueError:
                pass

class PglHandler:

    username = "pokemon"
    password = "2Phfv9MY"
    sleepy_list = set([i for i in range(1, 650)])

    def __init__(self, context):
        self.context = context

        self.configuration = self.context.configuration
        self.dlc_list = self.context.dlc_list
        self.user_manager = self.context.user_manager
        self.player_manager = self.context.player_manager

    def add_handlers(self) -> Blueprint:
        blueprint = Blueprint('pgl', __name__)
        
        @blueprint.before_request
        def before_request_hook():
            return self.authorize_pgl_request()
        
        @blueprint.get('/dsio/gw')
        def pgl_get():
            return self.handle_pgl_get_request()
        
        @blueprint.post('/dsio/gw')
        def pgl_post():
            return self.handle_pgl_post_request()

        return blueprint

    def authorize_pgl_request(self):
        credentials = request.authorization

        if (credentials is None) or (credentials.username != PglHandler.username) or (credentials.password != PglHandler.password):
            logger.debug("Rejecting PGL request because the auth credentials were incorrect")
            return HTTPStatus.UNAUTHORIZED
        
        req = PglRequest(
            p = request.args["p"],
            tok = request.args["tok"],
            gsid = request.args.get("gsid"),
            rom = int(request.args["rom"]) if "rom" in request.args else None,
            langcode = int(request.args["langcode"]) if "langcode" in request.args else None,
            dreamw = int(request.args["dreamw"]) if "dreamw" in request.args else None
        )
        logger.debug(f"Received {req}")

        session = self.user_manager.get_service_session(req.tok, "external")

        if session is None:
            logger.debug("Rejecting PGL request because the service session has expired")
            return HTTPStatus.UNAUTHORIZED
        
        g.pgl_request = req
        g.pgl_user = session.user

    def handle_pgl_get_request(self):
        req: PglRequest = g.pgl_request
        buffer = io.BytesIO()
        output = LEOutputStream(buffer)

        handlers = {
            "sleepily.bitlist": self.handle_get_sleepy_list,
            "account.playstatus": self.handle_get_account_status,
            "savedata.download": self.handle_download_save_data,
            "savedata.getbw": self.handle_memory_link
        }

        handler = handlers.get(req.p)

        if handler is None:
            logger.error(f"Invalid GET request type: {req.p}")
            return HTTPStatus.BAD_REQUEST

        handler(req, output)
        return buffer.getvalue(), 200, {"Content-Type": "application/octet-stream"}
        
    def handle_get_sleepy_list(self, req: PglRequest, output: LEOutputStream):
        
        if not self.player_manager.does_player_exist(req.gsid):
            self.write_status_code(output, 1)
            return
        
        bit_list = bytearray(128)

        for sleepy in self.sleepy_list:
            byte_offset = sleepy // 8
            bit_offset = sleepy % 8

            bit_list[byte_offset] |= 1 << bit_offset

        self.write_status_code(output, 0)
        output.write(bit_list)

    def handle_get_account_status(self, req: PglRequest, output: LEOutputStream):
        player: Player = self.player_manager.player_map.get(req.gsid)

        if player is None:
            self.write_status_code(output, 8)
            return
        
        self.write_status_code(output, 0)
        output.write_short(player.status.value)

    def handle_download_save_data(self, req: PglRequest, output: LEOutputStream):
        player: Player = self.player_manager.player_map.get(req.gsid)
        user = g.pgl_user

        if player is None:
            self.write_status_code(output, 1)
            return
        
        logger.info(f"Player {player.gsid} is downloading save data")

        self.write_status_code(output, 0)

        if player.status == PlayerStatus.AWAKE:
            return
        
        is_version_2 = True if player.rom_code in (22, 23) else False
        encounters = player.encounters
        items = player.items
        decor_list = player.decor

        output.write_int(randint(0, 2**31 - 1))

        for encounter in encounters:
            output.write_short(encounter.species)
            output.write_short(encounter.move)
            output.write(encounter.form)
            output.write(encounter.gender)
            output.write(encounter.animation.value)
            output.write(0)

        output.write_bytes(0, (10 - len(encounters)) * 8)

        output.write_short(player.levels_gained)
        output.write(0)
        output.write(self.get_dlc_index(user, player.musical, "MUSICAL", "musical.bin"))
        output.write(self.get_dlc_index(user, player.cgear_skin, "CGEAR2" if is_version_2 else "CGEAR", "cgear.bin"))
        output.write(self.get_dlc_index(user, player.dex_skin, "ZUKAN", "zukan.bin"))
        output.write(0 if len(decor_list) == 0 else 1)
        output.write(0)

        for item in items:
            output.write_short(item.id)

        output.write_bytes(0, (20 - len(items)) * 2)

        for item in items:
            output.write_short(item.quantity)

        output.write(0, (20 - len(items)))

        for decor in decor_list:
            name_bytes = decor.name.encode("UTF-16-LE")

            output.write_short(decor.id)

            output.write(name_bytes, 0, min(len(name_bytes), 24))
            output.write_bytes(-1, 24 - len(name_bytes))

        for i in range(5 - len(decor_list)):
            output.write_short(0x7E)
            output.write_bytes(0, 24)

        output.write_short(0)

        if is_version_2:
            avenue_visitors = player.avenue_visitors

            for visitor in avenue_visitors:
                name_bytes = visitor.name.encode("UTF-16-LE")
                output.write(name_bytes, 0, min(14, len(name_bytes)))
                output.write_bytes(-1, 16 - len(name_bytes))

                visitor_type = visitor.type.client_id + visitor.personality * 8
                output.write(visitor_type)
                output.write(visitor.shop_type.value + (7 - visitor_type * 2 % 7))
                
                output.write_short(0)
                output.write_int(1)
                output.write(visitor.country_code)
                output.write(visitor.state_province_code)
                output.write(visitor.game_language_code)
                output.write(visitor.game_rom_code)
                output.write(1 if visitor.type.female else 0)
                output.write(0)
                output.write_short(visitor.dreamer_species)

            output.write_bytes(0, (12 - len(avenue_visitors)) * 32)
            output.write_int(0)

    def handle_memory_link(self, req: PglRequest, output: LEOutputStream):
        if not GsidUtility.is_valid_gamesync_id(req.gsid):
            self.write_status_code(output, 8)
            return
        
        player: Player = self.player_manager.player_map.get(req.gsid)
        user = g.pgl_user

        if player is None:
            self.write_status_code(output, 8)
            return
        
        if player.rom_code == 0:
            self.write_status_code(output, 5)
            return
        
        if player.rom_code in (22, 23):
            self.write_status_code(output, 10)
            return
        
        file: Path = player.data_directory / "save.bin"

        if not file.exists():
            self.write_status_code(output, 5)
            return
        
        logger.info(f"User {user.get_redacted_id()} is Memory Linking with player {player.id}")

        self.write_status_code(output, 0)

        output.write(file.read_bytes())

    def handle_pgl_post_request(self):
        req = g.pgl_request
        buffer = io.BytesIO()
        output = LEOutputStream(buffer)

        handlers = {
            "savedata.upload": self.handle_upload_save_data,
            "savedata.download.finish": self.handle_download_save_data_finish,
            "account.create.upload": self.handle_create_account,
            "account.createdata": self.handle_create_data
        }

        handler = handlers.get(req.p)

        if handler is None:
            logger.error(f"Invalid POST request type: {req.p}")
            return '', HTTPStatus.BAD_REQUEST

        handler(req, output)
        return buffer.getvalue(), 200, {"Content-Type": "application/octet-stream"}

    def handle_download_save_data_finish(self, req: PglRequest, output: LEOutputStream):
        player: Player = self.player_manager.player_map.get(req.gsid)

        if player is None:
            self.write_status_code(output, 1)
            return
        
        if self.configuration.clear_player_dream_info_on_wake:
            player.reset_dream_info()

            if not self.player_manager.save_player(player):
                logger.warning(f"Save data failure for player {player.game_sync_id}")
                return HTTPStatus.INTERNAL_SERVER_ERROR
            
        self.write_status_code(output, 0)

    def handle_upload_save_data(self, req: PglRequest, output: LEOutputStream):
        player: Player = self.player_manager.player_map.get(req.gsid)

        if player is None:
            request.stream.read()
            self.write_status_code(output, 1)
            return

        logger.info(f"Player {player.game_sync_id} is uploading save data")

        if player.status != PlayerStatus.AWAKE:
            logger.warning(f"Player {player.game_sync_id} is not AWAKE -- existing dream information will be overwritten!")

        if (player.rom_code != 0) and (req.rom != player.rom_code):
            logger.warning(f"Player {player.game_sync_id}'s game version changed from {player.rom_code} to {req.rom}")

        save_data_bytes = request.get_data()
        if not self.player_manager.store_player_game_save_file(player, save_data_bytes):
            self.write_status_code(output, 4)
            return

        save_path: Path = (player.data_directory / "save.bin")

        save = SaveFile(save_path)

        pkmn_data = save.get_dreamer_pokemon()

        dreamer_info = PkmnInfo(
            pokemon_no        = pkmn_data.natdex,
            pokemon_name      = pkmn_data.species,
            form_no           = pkmn_data.form,
            type1             = pkmn_data.type1,
            type2             = pkmn_data.type2,
            pokemon_nickname  = pkmn_data.nickname,
            oyaname           = pkmn_data.trainer_name,
            level             = pkmn_data.level,
            sex               = pkmn_data.gender,
            personality       = PkmnNature(pkmn_data.nature).name,
            ball_name         = pkmn_data.ball,
            trainer_id        = pkmn_data.trainer_id,
            trainer_secret_id = pkmn_data.trainer_id_secret
        )

        trainer_data = save.trainer()
        player.name = trainer_data.name
        player.num_badges = trainer_data.num_badges

        player.status = PlayerStatus.SLEEPING
        player.rom_code = req.rom
        player.language_code = req.langcode
        player.dreamer_info = dreamer_info

        if not self.player_manager.save_player(player):
            logger.warning(f"Save data failure for player {player.game_sync_id}")
            return HTTPStatus.INTERNAL_SERVER_ERROR
        
        self.write_status_code(output, 0)

    def handle_create_account(self, req: PglRequest, output: LEOutputStream):
        bytes = request.get_data()

        if not GsidUtility.is_valid_gamesync_id(req.gsid):
            self.write_status_code(output, 8)
            return
        
        if self.player_manager.does_player_exist(req.gsid):
            self.write_status_code(output, 2)
            return
        
        player = self.player_manager.register_player(req.gsid, req.rom, req.langcode)

        if player is None:
            self.write_status_code(output, 3)
            return
        
        if not self.player_manager.store_player_game_save_file(player, bytes):
            self.write_status_code(output, 4)
            return
        
        self.write_status_code(output, 0)

    def handle_create_data(self, req: PglRequest, output: LEOutputStream):
        raw_body = request.get_data(as_text=True).replace("\u0000", "")
        game_sync_id = GsidUtility.stringify_gamesync_id(int(raw_body))

        if not GsidUtility.is_valid_gamesync_id(game_sync_id):
            logger.debug(f"[account.createdata] Rejecting invalid Game Sync ID: {game_sync_id} ({raw_body})")
            self.write_status_code(output, 8)
            return
        
        if self.player_manager.does_player_exist(game_sync_id):
            self.write_status_code(output, 2)
            return

        if self.player_manager.register_player(game_sync_id, None) is None:
            self.write_status_code(output, 3)
            return
        
        self.write_status_code(output, 0)

    def write_status_code(self, output: LEOutputStream, status: int):
        output.write_int(status)
        output.write_bytes(0, 124)

    def get_dlc_index(self, user: User, name: str, type: str, custom_file: Path):
        if name == "custom":
            user.set_dlc_override(type, Dlc(custom_file.absolute(),
                                            name, "IRAO", type, 1,
                                            custom_file.stat().st_size, 0, True))
            return 1
        else:
            user.remove_dlc_override(type)
            return self.dlc_list.get_dlc_index("IRAO", type, name)
