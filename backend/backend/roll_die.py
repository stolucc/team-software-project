""" Roll die module """
from random import randint
import json
import sys
from backend.player import Player
from backend.game import Game, get_games
from backend.jail import leave_jail


def roll_dice():

    """Function that returns a number between 1 and 6
       to represent the numbers of a die.
    """
    return randint(1, 6)


def roll_two_dice():
    """Simulates the rolling of two 6-sided dice.

    Returns:
        An int list representing the result of the two dice rolls.

    """
    dice_result = [roll_dice(), roll_dice()]
    return dice_result


def player_roll_dice(source=sys.stdin, output=sys.stdout):
    """Rolls two dice for a player, appends there rolls to the database,
       updates their position and the current game turn.
    """
    output.write('Content-Type: application/json\n\n')
    request = json.load(source)
    player_id = request["user_id"]

    number_of_squares = 40
    pass_go_amount = 200
    games = get_games()

    with Player(player_id) as player:
        for game in games:
            if player.username in games[game]:
                game_id = game
                in_jail = player.jail_state
                break

        with Game(game_id) as game:
            if game.current_turn == player.turn_position:
                rolls = roll_two_dice()
                player.rolls.append(rolls)
                if in_jail == 'not_in_jail':
                    player.board_position += sum(rolls)
                else:
                    if rolls[0] == rolls[1]:
                        player.jail_state = 'not_in_jail'


                if player.board_position >= number_of_squares:
                    player.balance += pass_go_amount
                    player.board_position -= number_of_squares

                json.dump({"your_rolls": rolls}, output)
