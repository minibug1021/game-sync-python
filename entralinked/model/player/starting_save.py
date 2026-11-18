"""The garden, chest, Share Shelf, and decor a new Game Sync ID starts with in the Dream World."""
from itertools import product

from utils.berries import BERRY_COUNT, BERRY_ITEM_IDS
from utils.constants import SHARE_SHELF_ID, WATERINGCAN_ID

STARTING_BERRIES_EACH = 99  # debug data

GARDEN_ROWS = 2
GARDEN_COLUMNS = 3
STARTING_PLOTS = GARDEN_ROWS * GARDEN_COLUMNS

# owned from the start
STARTING_DECOR_IDS = (WATERINGCAN_ID, SHARE_SHELF_ID)


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
            {"pokeitem_id": item_id, "item_cnt": STARTING_BERRIES_EACH, "date": "2000-01-01"}
            for item_id in BERRY_ITEM_IDS
        ],
    }


def starting_shelf() -> dict:
    return {"cnt": 0, "share_list": []}


def starting_decor(my_interior_ids: list[int]) -> list[dict]:
    """Return the my_interior_list of a new save."""
    return [{"my_interior_id": my_interior_id, "interior_id": decor_id}
            for decor_id, my_interior_id in zip(STARTING_DECOR_IDS, my_interior_ids, strict=True)]
