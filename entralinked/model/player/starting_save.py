"""The empty garden, chest, and Share Shelf a new Game Sync ID starts with in the Dream World."""
from itertools import product

BERRY_ITEM_ID_OFFSET = 148  # Berry n is item n + 148
BERRY_COUNT = 64
STARTING_BERRIES_EACH = 99  # debug data

GARDEN_ROWS = 2
GARDEN_COLUMNS = 3
STARTING_PLOTS = GARDEN_ROWS * GARDEN_COLUMNS


def starting_garden(croft_ids: list[int]) -> dict:
    """Return the crop_data of a new save, with STARTING_PLOTS empty plots using the given ids."""
    return {
        "croft_list": [
            {"my_croft_id": croft_id, "x": x + 1, "y": y + 1}
            for croft_id, (y, x) in zip(croft_ids, product(range(GARDEN_ROWS), range(GARDEN_COLUMNS)), strict=True)
        ]
    }


def starting_chest() -> dict:
    """Return the chest_data of a new save, which holds a stack of every Berry."""
    return {
        "cnt": BERRY_COUNT,
        "list": [
            {"pokeitem_id": berry_id + BERRY_ITEM_ID_OFFSET, "item_cnt": STARTING_BERRIES_EACH, "date": "2000-01-01"}
            for berry_id in range(1, BERRY_COUNT + 1)
        ],
    }


def starting_shelf() -> dict:
    return {"cnt": 0, "share_list": []}
