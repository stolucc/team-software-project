"""
Handles the generation of Server-Sent Events which notify clients of state
changes.

Steps for adding more SSE on the SERVER SIDE:
    See README.rst in "team-software-project/backend"

Steps for adding more SSE listeners on the CLIENT SIDE:
    See README.md in "team-software-project/frontend"

"""
import sys
import time
import json
from cgi import FieldStorage
import cgitb
from backend.game import Game
from backend.player import Player
from backend.properties import owned_property_positions, Property

cgitb.enable()


def start_sse_stream(output_stream=sys.stdout):
    """Generate a stream of server-sent events according to state changes.

    This function is activated by making a request to the JavaScript
    function "initialiseEventSource()" which is located in "sse.js".
    This operation is performed by the JavaScript waitingGame function,
    and hence, other JavaScript code need only "get" a reference to
    the EventSource object (by calling "getEventSource()" from
    "sse.js").

    Reads in the game id, and repeatedly does each of the following:
        1) Check whose turn it is.
        2) Check if any new players have joined the waiting game lobby.
        3) Check if any of the players' balances have changed in a game.
        4) Check if any of the players' positions have changed in a game.
        5) Check if the specified game's status has changed to "playing".

    """
    # The following headers are compulsory for SSE.
    output_stream.write('Content-Type: text/event-stream\n')
    output_stream.write('Cache-Control: no-cache\n')
    output_stream.write('\n')

    # Read in the game id from standard input (aka. FieldStorage) and create
    # an empty dictionary of current players, positions, balances, new
    # players, new positions, new balances and turn orders. All the "new"
    # dicts will be populated with the most up to date data from the
    # **database**, while non-"new" dicts will be populated only after a
    # comparison between it and the corresponding "new" dict has been made.
    input_data = FieldStorage()
    game_id = input_data.getfirst('game')
    last_game_state = "waiting"
    players = {}
    positions = {}
    balances = {}
    new_players = {}
    new_positions = {}
    new_balances = {}
    turn = None
    turn_order = {}
    push_initial_user_details = True

    # These statements are executed constantly once the first request to this
    # function is made.
    while True:
        # Create a Game object representing the game in the database.
        # This can be thought of as a "pointer" to the appropriate game in the
        # database.
        game = Game(game_id)

        # Go through each player in the game and populate the "new"
        # dictionaries with user_id (aka. player_id) as the key, and
        # username/position/balance/turn-order as the value.
        # These are the latest values retrieved from the database.
        for player in map(Player, game.players):
            new_players[player.uid] = player.username
            new_positions[player.uid] = player.board_position
            new_balances[player.uid] = player.balance
            turn_order[player.uid] = player.turn_position

        # Assign the current (aka. non-new) dictionaries to the value of the
        # "new" (aka. latest) dictionaries, after calling the appropriate
        # comparison function to determine whether an event should be
        # generated.
        turn = check_new_turn(output_stream, turn, game.current_turn,
                              turn_order)
        players = check_new_players(output_stream, players, new_players)
        balances = check_new_balances(output_stream, balances, new_balances)
        positions = check_new_positions(output_stream, positions,
                                        new_positions)

        # Pushes data to update the players info table on game start
        if push_initial_user_details and last_game_state == "playing":
            push_initial_user_details = False
            start_game_push(output_stream, turn_order)

        # Call function to check the current state of this game.
        # A game state may be "waiting" or "playing".
        last_game_state = check_game_playing_status(output_stream, game,
                                                    last_game_state)

        time.sleep(3)

        # Flush standard out which forcefully sends everything that might be
        # buffered in standard out to the client. No need to worry about tech
        # details too much, it's just standard SSE procedure!
        output_stream.flush()


def output_event(output_stream, event, data):
    """Output a sse event as json with the given details.

    An SSE event consists of data and an optional name. The name is the
    identifier that is listened for on the client side (if no name is given,
    the event can be listened for as "message"). Here’s the rough format:

    [event: <event name>]
    data: <event data>
    [data: <continued event data>]
    <blank line>

    Arguments:
        output_stream: The stream to output the sse event to.
        event: The name of the event to output.
        data: The data to be output. This will be serialised using json.dumps.

    Testing strings:
    >>> import sys
    >>> output_event(sys.stdout, 'hello', 'goodbye')
    event: hello
    data: "goodbye"
    <BLANKLINE>

    Testing numbers:
    >>> import sys
    >>> output_event(sys.stdout, 'hello', 3)
    event: hello
    data: 3
    <BLANKLINE>

    Testing dictionaries:
    >>> import sys
    >>> output_event(sys.stdout, 'hello', {3: 4, 5: 'q'})
    event: hello
    data: {"3": 4, "5": "q"}
    <BLANKLINE>

    Testing lists:
    >>> import sys
    >>> output_event(sys.stdout, 'hello', [3, 4, 5, 4])
    event: hello
    data: [3, 4, 5, 4]
    <BLANKLINE>
    """
    output_stream.write(
        'event: {}\n'
        'data: {}\n'
        '\n'.format(event, json.dumps(data, sort_keys=True)))


def check_new_turn(output_stream, old_turn, new_turn, turn_order):
    """Checks if the turn has changed to a different player and sends an SSE
    event if it has.

    Arguments:
        old_turn: An int representing the current position in the playing
            queue.
        new_turn: An int representing the latest (aka. "new") position in the
            playing queue.
        turn_order: A dictionary representing mapping player ids to the
            player's position in the playing queue.

    Returns:
        An int representing the current position of the playing queue.

    """
    if new_turn != old_turn:
        for uid, turn_pos in turn_order.items():
            if turn_pos == new_turn:
                generate_player_turn_event(output_stream, uid, turn_order)
    return new_turn


def generate_player_turn_event(output_stream, player_id, turn_order):
    """Generates an event for a change of turn in the game.

    Arguments:
        new_turn: An int representing the latest position in the playing
            queue.
        player_id: An int representing the player whose turn it is.

    >>> import sys
    >>> generate_player_turn_event(sys.stdout, 2, {2:0})
    event: playerTurn
    data: [2, 0]
    <BLANKLINE>
    """
    output_event(
        output_stream,
        'playerTurn',
        [player_id, turn_order[player_id]])


def check_new_players(output_stream, old_players, new_players):
    """Checks if a new player joined the game and sends an SSE event if it has.

    Arguments:
        old_players: A dictionary representing the current list of players in
            the game. key = user_id, value = username.
        new_players: A dictionary representing the latest (aka. "new") list
            of players in the game. key = user_id, value = username.

    Returns:
        A dictionary with the latest list of players in the game.

    """
    if new_players != old_players:
        generate_player_join_event(output_stream, old_players, new_players)
    return new_players.copy()


def generate_player_join_event(output_stream, old_players, new_players):
    """Generates an event for a change in the group of players in the game.

    Compares two dictionaries and outputs a playerJoin server-sent event if
    the two dicts differ. Along with the event is JSON containing the
    difference between the two dicts.

    Arguments:
        old_players: A dictionary representing the current list of players.
        new_players: A dictionary representing the latest list of players.

    >>> import sys
    >>> generate_player_join_event(
    ...     sys.stdout,
    ...     {5: 'first_user', 6: 'user_2'},
    ...     {5: 'first_user', 6: 'user_2', 8: 'third'})
    event: playerJoin
    data: ["third"]
    <BLANKLINE>

    >>> import sys
    >>> generate_player_join_event(
    ...     sys.stdout,
    ...     {},
    ...     {5: 'first_user'})
    event: playerJoin
    data: ["first_user"]
    <BLANKLINE>

    """
    if not old_players:
        data = [uname for uid, uname in new_players.items()]
    else:
        data = [
            uname
            for uid, uname in new_players.items()
            if uid not in old_players]
    output_event(output_stream, 'playerJoin', data)


def check_new_balances(output_stream, old_balances, new_balances):
    """Checks if a player's balance changed and sends an SSE event if it has.

    Arguments:
        old_balances: A dictionary representing the current balance
            for each player. key = user_id, value = balance.
        new_balances: A dictionary representing the latest (aka. "new")
            balance for each player. key = user_id, value = balance.

    Returns:
        A dictionary with the latest balance for each player.

    """
    if new_balances != old_balances:
        generate_player_balance_event(output_stream, old_balances,
                                      new_balances)
    return new_balances.copy()


def generate_player_balance_event(output_stream, old_balances, new_balances):
    """Generates an event for a change in the balance of players in the game.

    Compares two dictionaries and outputs a playerBalance server-sent event if
    the two dicts differ. Along with the event is JSON containing the
    difference between the two dicts.

    Arguments:
        old_balances: A dictionary representing the current balance for each
            player.
        new_balances: A dictionary representing the latest balance for each
            player.

    >>> import sys
    >>> generate_player_balance_event(
    ...     sys.stdout,
    ...     {5: 200, 6: 200, 7: 200, 8: 200},
    ...     {5: 200, 6: 200, 7: 200, 8: 400})
    event: playerBalance
    data: [[8, 400, 200]]
    <BLANKLINE>

    >>> import sys
    >>> generate_player_balance_event(
    ...     sys.stdout,
    ...     {},
    ...     {5: 200})
    event: playerBalance
    data: [[5, 200, 0]]
    <BLANKLINE>

    """
    # Send the JSON object which contains the elements that are not in common
    # with the two dictionaries.
    if not old_balances:
        data = [
            [uid, balance, 0]
            for uid, balance in new_balances.items()]
    else:
        data = [
            [uid, balance, ((balance - old_balances[uid])
                            if old_balances[uid] else balance)]
            for uid, balance in new_balances.items()
            if balance != old_balances[uid]]

    output_event(output_stream, 'playerBalance', data)


def check_new_positions(output_stream, old_positions, new_positions):
    """Checks if a player has moved and sends an SSE event if it has.

    Arguments:
        old_positions: A dictionary representing the current position
            for each player. key = user_id, value = position.
        new_positions: A dictionary representing the latest (aka. "new")
            position for each player. key = user_id, value = position.

    Returns:
        A dictionary with the latest positions for each player.

    """
    if new_positions != old_positions:
        generate_player_move_event(output_stream, old_positions, new_positions)
    return new_positions.copy()


def generate_player_move_event(output_stream, old_positions, new_positions):
    """Generates an event for a change in the position of players in the game.

    Compares two dictionaries and outputs a playerMove server-sent event if
    the two dicts differ. Along with the event is JSON containing the
    difference between the two dicts.

    Arguments:
        old_positions: A dictionary representing the current position for each
            player.
        new_players: A dictionary representing the latest position for each
            player.

    >>> import sys
    >>> generate_player_move_event(
    ...     sys.stdout,
    ...     {5: 4, 6: 6, 7: 5, 8: 0},
    ...     {5: 4, 6: 6, 7: 5, 8: 4})
    event: playerMove
    data: [[8, 4, 0]]
    <BLANKLINE>

    >>> import sys
    >>> generate_player_move_event(
    ...     sys.stdout,
    ...     {},
    ...     {5: 4})
    event: playerMove
    data: [[5, 4, 0]]
    <BLANKLINE>

    """
    # Send the JSON object which contains the elements that are not in common
    # with the two dictionaries.
    if not old_positions:
        data = [
            [uid, board_position, 0]
            for uid, board_position in new_positions.items()]
    else:
        data = [
            [uid, board_position, old_positions[uid]]
            for uid, board_position in new_positions.items()
            if board_position != old_positions[uid]]
    output_event(output_stream, 'playerMove', data)


def check_game_playing_status(output_stream, game, last_game_state):
    """Check if the specified game's status is 'playing'.

    Arguments:
        game: The game whose status is being checked.

    """
    if last_game_state == "waiting" and game.state == "playing":
        # Call function to generate appropriate event if game's status is
        # "playing".
        generate_game_start_event(game.uid, output_stream)

    return game.state


def generate_game_start_event(game_id, output_stream):
    """Generate a gameStart event for the appropriate game.

    Sends a gameStart server-sent event, along with data representing the
    game_id.

    Arguments:
        game_id: An int representing the started game's id.

    >>> import sys
    >>> generate_game_start_event(5, sys.stdout)
    event: gameStart
    data: 5
    <BLANKLINE>
    """
    output_event(output_stream, 'gameStart', game_id)


def check_property_ownership(output_stream, game_id, old_properties):
    """Issue events if the ownership of any properties has changed.

    Arguments:
        game_id: The id of the game the events are being issued for.

    Returns:
        The current property ownership data, as a dictionary where the keys
        are property positions, and the values are owner player ids.
    """
    positions = owned_property_positions(game_id)
    new_properties = {}
    for position in positions:
        this_property = Property(position, game_id)
        new_properties[position] = this_property.owner
    if old_properties != new_properties:
        generate_ownership_events(
            output_stream,
            old_properties,
            new_properties)
    return new_properties


def generate_ownership_events(
        output_stream,
        old_ownership,
        new_ownership):
    """Generate an event for properties that have changed owner.

    Include properties that have become owned or unowned.

    Arguments:
        output_stream: The stream to which the events will be written.
        old_ownership: The old ownership data, as a dictionary where the keys
            are property positions and the values are owner ids.
        new_ownership: The new ownership data, in the same format as
            old_ownership.

    >>> import sys
    >>> generate_ownership_events(
    ...     sys.stdout,
    ...     {4: 1, 5: 8},
    ...     {4: 3, 5: 8})
    event: propertyOwnerChanges
    data: {"4": {"newOwner": 3, "oldOwner": 1}}
    <BLANKLINE>

    >>> import sys
    >>> generate_ownership_events(
    ...     sys.stdout,
    ...     {5: 8},
    ...     {4: 3, 5: 8})
    event: propertyOwnerChanges
    data: {"4": {"newOwner": 3, "oldOwner": null}}
    <BLANKLINE>

    >>> import sys
    >>> generate_ownership_events(
    ...     sys.stdout,
    ...     {4: 3, 5: 8},
    ...     {5: 8})
    event: propertyOwnerChanges
    data: {"4": {"newOwner": null, "oldOwner": 3}}
    <BLANKLINE>
    """
    changes = {}
    positions = list(old_ownership.keys()) + list(new_ownership.keys())
    for position in positions:
        old = old_ownership.get(position, None)
        new = new_ownership.get(position, None)
        if old != new:
            changes[position] = {'newOwner': new, 'oldOwner': old}

    output_event(output_stream, 'propertyOwnerChanges', changes)


def start_game_push(output_stream, turn_order):
    """Generates an event for to update the details table at game start.

    Compares two dictionaries and outputs a playerBalance server-sent event if
    the two dicts differ. Along with the event is JSON containing the
    difference between the two dicts.
    """
    generate_player_turn_event(output_stream, next(iter(turn_order)),
                               turn_order)
    generate_player_balance_event(output_stream, {},
                                  {1: 1500, 2: 1500, 3: 1500, 4: 1500})
