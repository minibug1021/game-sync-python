"""Data sent between the Dream World and the Gen5 games."""
from dataclasses import dataclass


@dataclass
class DreamEncounter:
    """A Pokémon waiting in the Entree Forest."""

    species: int
    move: int
    form: int
    gender: int
    # How it moves around: 0 look around, 1 walk around, 2 walk and look around, 3 walk
    # vertically, 4 walk horizontally, 5 walk and look horizontally, 6 spin right, 7 spin left
    animation: int


@dataclass
class DreamItem:
    """A stack of items sent to the Entralink."""

    pokeitem_id: int
    item_cnt: int
