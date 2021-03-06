from ..events import Event
from ..intervals import Interval
from ..sources import Source
from ..pricing import Candle


class Instrument:
    """
    Instruments belong to a connection, and under a specific instrument key.
    They also have a specific granularity (by default 1 minute, and only to
      the extent of being supported by the server) and have activity since
      the specified timestamp, using certain initial bid/ask values.

    The lifecycle of the instrument goes like this:
      - Creation: The constructor must enable the needed components of an
        instrument.
      - dispose(): This method is called on disposal of an instrument, but
        never meant to be used by the instrument directly, but only invoked
        by a parent connection.
      - activate(): This method is called when the connection, actually,
        connects, and also called when the instrument is added to a connection
        (created inside an add_instrument call) and the connection is, actually,
        connected.
      - deactivate(): This method is called when the connection disconnects,
        and also when the instrument is disposed (even if the connection is
        still connected).
    Creating an instrument or calling dispose() are not things meant to be
      invoked directly, but the activate()/deactivate() methods may be. They
      look more like a pause/resume feature.
    """

    def __init__(self, connection, key, stamp, granularity=Interval.MINUTE,
                 initial_bid=None, initial_ask=None):
        self._connection = connection
        self._key = key
        self._granularity = granularity
        self._disposed = False
        self._source = Source(Candle, stamp, granularity, initial_bid, initial_ask)
        self._on_activated = Event()
        self._on_activation_failed = Event()
        self._on_deactivated = Event()
        self._on_disposed = Event()
        # Active operations are a mapping operation_id => operation.
        self._active_operations = {}

    def _activate(self, on_activated, on_failed):
        """
        Attempts an activation. If the activation succeeds, this method must invoke
          the on_activated callback with no arguments. If the activation fails, this
          method must invoke the on_failed callback with the reason as an argument.

        This method is implementation-specific. It is mandatory to implement it somehow.

        :param on_activated: The callback to invoke when the activation succeeded.
        :param on_failed: The callback to invoke when the activation failed.
        """

        raise NotImplemented

    def _deactivate(self, on_deactivated):
        """
        Attempts a disconnection. This is a user-requested disconnection and must invoke
          on_deactivated with no arguments on success.

        This method is implementation-specific. It is mandatory to implement it somehow.

        :param on_deactivated: The callback to invoke when the instrument is deactivated.
        """

        raise NotImplemented

    def _is_active(self):
        """
        Reports whether the instrument is active (and gathering data / iterating).

        This method is implementation-specific. It is mandatory to implement it somehow.

        :return: a boolean answer telling whether the instrument is active.
        """

        raise NotImplemented

    def _dispose(self):
        """
        Performs the actual disposal of the instrument.

        This method is implementation-specific. It is mandatory to implement it somehow.
        """

        raise NotImplemented

    def activate(self):
        """
        Attempts an activation.

        This method invokes a method that must be implemented because it is per-implementation.

        :return: Whether the activation was/will-be made, or not (because it was already active).
        """

        if not self._is_active():
            def on_activated():
                self._on_activated.trigger(self)

            def on_failed(reason):
                self._on_activation_failed.trigger(self, reason)

            self._activate(on_activated, on_failed)
            return True
        else:
            return False

    def deactivate(self):
        """
        Attempts a deactivation.

        This method invokes a method that must be implemented because it is per-implementation.

        :return: Whether the deactivation was/will-be made, or not (because it was already not
          active).
        """

        if self._is_active():
            def on_deactivated():
                self._on_deactivated.trigger(self, None)

            self._deactivate(on_deactivated)
            return True
        else:
            return False

    def dispose(self):
        """
        Attempts a disposal. It will do nothing if the instrument is already disposed.

        This method invokes a method that must be implemented because it is per-implementation.

        :return: Whether the disposal was/will-be made, or not (bcause it was already disposed).
        """

        if not self._disposed:
            self._dispose()
            self._disposed = True
            return True
        else:
            return False

    @property
    def connection(self):
        return self._connection

    @property
    def key(self):
        return self._key

    @property
    def granularity(self):
        return self._granularity

    @property
    def ask_source(self):
        return self._source

    @property
    def active_operations(self):
        return self._active_operations.copy()

    @property
    def on_activated(self):
        return self._on_activated

    @property
    def on_activation_failed(self):
        return self._on_activation_failed

    @property
    def on_deactivated(self):
        return self._on_deactivated

    @property
    def on_disposed(self):
        return self._on_disposed

    @property
    def active(self):
        """
        Reports whether the instrument is active. As long as this property returns True,
          the instrument is gathering data and updating periodically.

        This property invokes a method that must be implemented because it is per-implementation.

        :return: a boolean answer telling whether the instrument is active (running) or not.
        """

        return self._is_active()

    @property
    def disposed(self):
        """
        Reports whether the instrument is disposed. Disposed instruments cannot be used
          (activated) anymore.

        :return: a boolean answer telling whether the instrument is disposed or not.
        """

        return self._disposed
