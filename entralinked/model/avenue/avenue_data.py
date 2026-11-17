"""Join Avenue visitors (Black 2 and White 2)."""
from dataclasses import dataclass


@dataclass
class AvenueVisitor:
    """Someone who turns up in the player's Join Avenue after a Game Sync."""

    name: str
    # 0 Youngster / Lass, 1 Ace Trainer, 2 Pokémon Ranger, 3 Pokémon Breeder, 4 Scientist,
    # 5 Hiker / Parasol Lady, 6 Roughneck / Nurse, 7 Preschooler
    trainer_class: int
    female: bool
    # 0 raffle, 1 florist, 2 salon, 3 antique, 4 dojo, 5 cafe, 6 market
    shop_type: int
    game_language_code: int
    game_rom_code: int
    country_code: int
    state_province_code: int
    personality: int  # picks the phrases the visitor uses
    dreamer_species: int
