#!/usr/bin/env python3
from dataclasses import dataclass
from enum import Enum, auto
from typing import ClassVar, List

class DreamAnimation(Enum):
    LOOK_AROUND = 0
    WALK_AROUND = auto()
    WALK_LOOK_AROUND = auto()
    WALK_VERTICALLY = auto()
    WALK_HORIZONTALLY = auto()
    WALK_LOOK_HORIZONTALLY = auto()
    SPIN_RIGHT = auto()
    SPIN_LEFT = auto()

@dataclass
class DreamDecor:
    id: int
    name: str

    DEFAULT_DECOR: ClassVar[List] = []

DreamDecor.DEFAULT_DECOR = [
    DreamDecor(1, "Design Table"),
    DreamDecor(2, "Design Stool"),
    DreamDecor(3, "Flower Vase"),
    DreamDecor(4, "Cuddle Rug"),
    DreamDecor(6, "Wall Poster")
]

@dataclass
class DreamEncounter:
    species: int
    move: int
    form: int
    gender: int
    animation: DreamAnimation

@dataclass
class DreamItem:
    id: int
    quantity: int
