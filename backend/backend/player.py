"""This module implements the Player class, used to represent individual
players of Monopoly"""

import backend.storage


class Player(object):  # pylint: disable=too-many-instance-attributes
    """The Player class.

    Access (and mutation) to the properties of this class can be done either
    atomically or non-atomically. To *read* a property, normal property
    syntax can be used::

        player = Player(123)
        print(player.username)

    This will create a new player object, which is a reference to the stored
    player indicated by the id 123. The access to the username field will
    send a request to the server.

    To perform actions atomically, encapsulate them in a with statement::

        with Player(123) as player:
            print(player.username)
            player.username += " Jones"
            print(player.username)

    Between each of the lines above, no mutation can happen to the player
    record in storage. If there *is* mutation, an exception will be thrown.

    No mutation is allowed outside of a with statement:

    >>> player = Player(1)
    >>> player.username = "Joe" # doctest: +ELLIPSIS
    Traceback (most recent call last):
    ...
    TypeError: Must be within "with" statement to mutate the Player class

    Args:
        uid (int): The unique id of the player, generated by the database.
    """
    def __init__(self, uid):
        self._uid = uid
        self._in_context = False
        self._username = None
        self._rolls = None
        self._turn_position = None
        self._board_position = None
        self._conn = None
        self._balance = None

    def __enter__(self):
        self._in_context = True
        self._conn = backend.storage.make_connection()
        self._conn.begin()
        with self._conn.cursor() as cursor:
            cursor.execute('SELECT * FROM `players` WHERE `id` = %s;',
                           (self.uid,))
            result = cursor.fetchone()
            self._username = result['username']
            self._balance = result['balance']
            self._turn_position = result['turn_position']
            self._board_position = result['board_position']
            del result
            cursor.execute('SELECT (`roll1`, `roll2`) FROM `rolls` '
                           'WHERE `id` = %s ORDER BY `number`;',
                           (self.uid,))
            self._rolls = [(result['roll1'], result['roll2'])
                           for result in cursor.fetchall()]
        return self

    def __exit__(self, *exc):
        try:
            with self._conn.cursor() as cursor:
                cursor.execute('UPDATE `players` '
                               'SET `username` = %s, '
                               '`balance` = %s, '
                               '`turn_position` = %s, '
                               '`board_position` = %s, '
                               'WHERE `id` = %s;',
                               (self.username, self.balance,
                                self.turn_position, self.board_position,
                                self.uid))
                cursor.executemany('REPLACE INTO `rolls` '
                                   'VALUES (%s, %s, %s, %s);',
                                   ((self.uid, roll1, roll2, i)
                                    for i, (roll1, roll2)
                                    in enumerate(self.rolls)))
            self._conn.commit()
        finally:
            self._in_context = False
            self._conn.close()

    @property
    def uid(self):
        """
        Returns:
            int: the (immutable) unique user id for this player.
        """

        return self._uid

    @property
    def username(self):
        """
        Returns:
            str: the (possibly not unique) username for this player.

        Raises:
            TypeError: if mutated outside of a with statement.
        """
        return backend.storage.request_property(self, self._in_context,
                                                'players', 'username')

    @property
    def balance(self):
        """
        Returns:
            int: the current balance for this player.

        Raises:
            TypeError: if mutated outside of a with statement.
        """
        return backend.storage.request_property(self, self._in_context,
                                                'players', 'balance')

    @property
    def turn_position(self):
        """
        Returns:
            int: the place in the "turn queue" the player is.

        Raises:
            TypeError: if mutated outside of a with statement.
        """
        return backend.storage.request_property(self, self._in_context,
                                                'players', 'turn_position')

    @property
    def board_position(self):
        """
        Returns:
            int: the current position of the player on the board.

        Raises:
            TypeError: if mutated outside of a with statement.
        """
        return backend.storage.request_property(self, self._in_context,
                                                'players', 'board_position')

    @property
    def rolls(self):
        """
        Returns:
            [(int,int)]: the in-order list of rolls the player has received.

        Raises:
            TypeError: if mutated outside of a with statement.
        """
        if self._in_context:
            return self._rolls
        else:
            conn = backend.storage.make_connection()
            try:
                with conn.cursor() as cursor:
                    cursor.execute('SELECT (`roll1`, `roll2`) FROM `rolls` '
                                   'WHERE `id` = %s ORDER BY `num`;',
                                   (self.uid,))
                return [(result['roll1'], result['roll2'])
                        for result in cursor.fetchall()]
            finally:
                conn.close()

    def _set_property(self, name, new_value):
        if self._in_context:
            setattr(self, '_' + name, new_value)
        else:
            raise TypeError('Must be within "with" statement to mutate the '
                            'Player class')

    @username.setter
    def username(self, username):
        self._set_property('username', username)

    @balance.setter
    def balance(self, balance):
        self._set_property('balance', balance)

    @turn_position.setter
    def turn_position(self, turn_position):
        self._set_property('turn_position', turn_position)

    @board_position.setter
    def board_position(self, board_position):
        self._set_property('board_position', board_position)

    @rolls.setter
    def rolls(self, rolls):
        self._set_property('rolls', rolls)


def create_player(username):
    """Create a new player on the server

    Args:
        username(str): the human-readable username for the player.

    Returns:
        int: the player's unique id.
    """
    conn = backend.storage.make_connection()
    try:
        conn.begin()
        with conn.cursor() as cursor:
            cursor.execute('INSERT INTO `players` (`username`) '
                           'VALUES (%s);', (username,))
            cursor.execute('SELECT LAST_INSERT_ID();')
            result = cursor.fetchone()['LAST_INSERT_ID()']
        conn.commit()
        return result
    finally:
        conn.close()
