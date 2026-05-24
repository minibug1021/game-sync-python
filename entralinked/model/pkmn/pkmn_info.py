#!/usr/bin/env python3
from enum import Enum, auto
from dataclasses import dataclass

class PkmnNature(Enum):
    Hardy = 0
    Lonely = auto()
    Brave = auto()
    Adamant = auto()
    Naughty = auto()
    Bold = auto()
    Docile = auto()
    Relaxed = auto()
    Impish = auto()
    Lax = auto()
    Timid = auto()
    Hasty = auto()
    Serious = auto()
    Jolly = auto()
    Naive = auto()
    Modest = auto()
    Mild = auto()
    Quiet = auto()
    Bashful = auto()
    Rash = auto()
    Calm = auto()
    Gentle = auto()
    Sassy = auto()
    Careful = auto()
    Quirky = auto()

@dataclass
class PkmnInfo:
    pokemon_no: int
    pokemon_name: str
    form_no: int
    type1: str
    type2: str
    pokemon_nickname: str
    oyaname: str
    level: int
    sex: int
    personality: PkmnNature
    ball_name: str
    trainer_id: int
    trainer_secret_id: int

    def is_shiny(self):
        p1 = (self.personality >> 16) & 0xFFFF
        p2 = self.personality & 0xFFFF
        return (self.trainer_id ^ self.trainer_secret_id ^ p1 ^ p2) < 8