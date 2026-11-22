"""The garden, chest, and decor a new Game Sync ID starts with in the Dream World."""
from itertools import product

from utils.berries import BERRY_COUNT, BERRY_ITEM_IDS
from utils.constants import SHARE_SHELF_ID, WATERINGCAN_ID

STARTING_BERRIES_EACH = 999  # debug data

GARDEN_ROWS = 2
GARDEN_COLUMNS = 3
STARTING_PLOTS = GARDEN_ROWS * GARDEN_COLUMNS

# owned from the start
STARTING_DECOR_IDS = (WATERINGCAN_ID, SHARE_SHELF_ID)


def starting_garden(croft_ids: list[int]) -> list[dict]:
    """Return the garden_plots rows of a new save, STARTING_PLOTS empty plots using the given ids."""
    return [
        {"my_croft_id": croft_id, "x": x + 1, "y": y + 1}
        for croft_id, (y, x) in zip(croft_ids, product(range(GARDEN_ROWS), range(GARDEN_COLUMNS)), strict=True)
    ]


def starting_chest() -> dict:
    """Return the chest_data of a new save, which holds a stack of every Berry."""
    return {
        "cnt": BERRY_COUNT,
        "list": [
            {"pokeitem_id": item_id, "item_cnt": STARTING_BERRIES_EACH, "date": "2000-01-01"}
            for item_id in BERRY_ITEM_IDS
        ],
    }


def starting_decor(my_interior_ids: list[int]) -> list[dict]:
    """Return the owned_decor rows of a new save."""
    return [{"my_interior_id": my_interior_id, "interior_id": decor_id}
            for decor_id, my_interior_id in zip(STARTING_DECOR_IDS, my_interior_ids, strict=True)]
