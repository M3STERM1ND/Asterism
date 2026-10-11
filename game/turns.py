"""Turn rules: each turn a side either attacks or blocks. The player's stars count only while they are
drawing their spell, and their Block (a Grip rep) only counts on their own turn as their move.

Battle phases, and whose turn each one belongs to:
  select  - the player chooses: a spell, Block, or Rest      player's turn
  player  - Attack: drawing the spell's constellation         player's turn
  guard   - Block: the Grip rep that raises the shield        player's turn
  result  - the attack lands, or the shield is up             player's turn
  strike  - the enemy casts a constellation at the player     enemy's turn
  brace   - the enemy blocks instead                          enemy's turn
  heal    - the enemy heals instead                           enemy's turn
  pause   - a beat to read the outcome                        enemy's turn
  won / lost / checkin / report - the battle is over          nobody's turn
Damage only lands when the whole constellation is drawn.
"""
PLAYER_PHASES = ("select", "player", "guard", "result")
ENEMY_PHASES = ("strike", "brace", "heal", "pause")


def whose_turn(phase):
    """"player", "enemy", or None once the battle is over."""
    if phase in PLAYER_PHASES:
        return "player"
    if phase in ENEMY_PHASES:
        return "enemy"
    return None


def can_attack(phase):
    """Stars only count while the player is drawing a spell."""
    return phase == "player"


def can_block(phase):
    """A Grip rep only counts as the player's Block move, on their own turn."""
    return phase == "guard"
