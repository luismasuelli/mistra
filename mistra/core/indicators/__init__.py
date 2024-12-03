"""
Indicators are a different monster. They handle a growing array of width N, where
  N is a different constant, depending on the indicator class. While row indices
  refer different instants, column indices refer different features the indicators
  may have. All the cells in this (dynamic)xN array will be of float type, and each
  indicator will have to deal with that to the appropriate extent.

Indicators will depend, alternatively, on (or: "be created with"):
  - A source frame (directly).
  - Another indicator(s) (directly) and the underlying frame (indirectly). All the
      indicators MUST have the same interval type (directly or not).

Indicators cannot unlink that dependency [although they should be able to halt (stop
  updating), resume, and dispose (halt forever, and destroy the underlying data in
  an unrecoverable way)] and pick another one, since it gives the appropriate way of
  refreshing the data on other -dependent- indicators. They are tied to the indicators
  or sources they are created from, and those indicators or sources will forward data
  updates to them.

When an indicator is disposed, all the dependent indicators will also dispose.

A quite complex network of indicators may be used. For example: One single moving mean
  of the last 20 time slices / candles / instants can feed a moving variance of the last
  20 time slices / candles / instants (which contains both the variance and the stderr),
  which in turn can feed 5 different Bollinger Bands indicators.
"""
import warnings
from numpy import float64, nan
from ..timelapses import Timelapse


class Indicator(Timelapse):
    """
    Base class for indicators. Indicators depend ultimately on broadcasters, but they have
      to have the same source. Inheritors should have a way to distinguish each provided
      dependency.
    """

    def __init__(self, *broadcasters, chunk_size: int = 3600):
        broadcasters = set(broadcasters)
        intervals = set(broadcaster.interval for broadcaster in broadcasters)
        if len(intervals) != 1:
            raise ValueError("Indicators must receive at least a source and/or several other indicators, "
                             "and they must have the same interval")
        if not isinstance(chunk_size, int) or chunk_size < 0:
            raise ValueError("The chunk_size argument must be a strictly positive integer value")
        elif chunk_size < 60:
            warnings.warn("The chunk size seems to be somewhat small. Ensure this value is big "
                          "enough, especially if a lot of data will be inserted")
        Timelapse.__init__(self, float64, nan, chunk_size, self._initial_width())
        self._interval = intervals.pop()
        self._timestamp = max(broadcaster.timestamp for broadcaster in broadcasters)
        self._max_requested_start = {broadcaster: 0 for broadcaster in broadcasters}
        self._max_requested_end = {broadcaster: 0 for broadcaster in broadcasters}
        self._disposed = False
        # Trigger first refresh
        for broadcaster in broadcasters:
            broadcaster.on_refresh_indicators.register(self._on_dependency_update)
        for broadcaster in broadcasters:
            self._on_dependency_update(broadcaster, 0, len(broadcaster))

    def _get_timestamp(self):
        """
        Implements the timestamp property by returning the owned timestamp.
        """

        return self._timestamp

    def _get_interval(self):
        """
        Implements the interval property by returning the owned interval.
        """

        return self._interval

    def _initial_width(self):
        """
        The width of this indicator's data.
        """

        return 1

    def disposed(self):
        """
        Tells whether the current indicator is disposed (i.e. it will not work anymore, and data cannot
          be retrieved from it).
        """

        return self._disposed

    def __getitem__(self, item):
        """
        Returns data from this indicator.
        :param item: The index or slice to retrieve data at.
        """

        if self._disposed:
            raise RuntimeError("Cannot retrieve indicator data because it is disposed")
        return super().__getitem__(item)

    def dispose(self):
        """
        Clears this indicator from its dependency and broadcasts this call
          towards dependent indicators.
        """

        if not self._disposed:
            self._disposed = True
            self._data = None
            self._broadcasters_read = None
            for broadcaster in self._broadcasters_read.keys():
                broadcaster.on_refresh_indicators.unregister(self._on_dependency_update)
            for callback, receiver in self._on_refresh_indicators:
                receiver.dispose()

    def _on_dependency_update(self, dependency, start, end):
        """
        Processes a data update event. Such event will first be triggered from the source
        :param dependency: The dependency being updated.
        :param start: The internal start index of the dependency being updated.
        :param end: The internal end index of the dependency being updated.
        """

        # The maximum requested read for a dependency is the topmost read index
        #   up to now. Among every maximum requested index, we will get the minimum.
        self._max_requested_end[dependency] = max(end, self._max_requested_end[dependency])
        minimum_requested_end = min(r for r in self._max_requested_end.values())
        # Now we must also consider the minimum of this last index, and the currently requested end.
        current_end = min(minimum_requested_end, end)

        # For the start index (which will be <= than the end index), we still
        #   collect the maximums between the last read and the current start for,
        #   and still get the minimum among them.
        self._max_requested_start[dependency] = max(start, self._max_requested_start[dependency])
        minimum_requested_start = min(r for r in self._max_requested_start.values())
        # Then we also compare, and get minimum of, the minimum requested start, and the current start.
        current_start = min(minimum_requested_start, start)

        # Once we have these indices, we can invoke to refresh the data.
        self._update(current_start, current_end)

        # Then trigger to refresh the indicators.
        self._on_refresh_indicators.trigger(self, current_start, current_end)

    def _update(self, start, end):
        """
        Performs the update. This method must be implemented, account for all the needed dependencies, and also
          accounting for the fact that data may be NaN!
        :param start: The start index being refreshed.
        :param end: The end index (not included) being refreshed.
        """

        raise NotImplemented
