import warnings
from datetime import date, datetime

from numpy import ndarray, uint64
from .timelapses import Timelapse
from .events import Event
from .pricing import StandardizedPrice, Candle
from .indicator_broadcaster import IndicatorBroadcaster


class Source(Timelapse, IndicatorBroadcaster):
    """
    Source frames are the origin of the data. Internally, they are organized as a sequence of indexed prices
      or candles (depending on the required type: standardized price or candle).

    A type, an initial timestamp (e.g. day of activity) and an interval type is needed for the source frame
      know its context of work. After that, data may be added (either to the next available index or a given
      index that must be at least greater to the next one) and, if discontinuous, it will cause a kind of
      padding or interpolation in the frame data.

    When data is added, it will refresh two types of related (derived) frames:
      - Indicators of this frame.
      - Linked frames (to the current frame - they digest the data).
    """

    class InterpolationWarning(Warning):
        pass

    def __init__(self, dtype, stamp, interval, initial=None):
        """
        Creates a source frame with certain type, initial timestamp, an interval and an initial value.
        :param dtype: Either standardized price or candle.
        :param stamp: The initial time stamp. It will correspond to the sequence index 0.
        :param interval: The required interval.
        :param initial: The initial value for this frame. Usually being dragged from previous period.
          It must NOT be null if we don't plan to provide data for index 0.
        """

        if not interval.allowed_as_source():
            raise ValueError('The given interval is not allowed as source frame interval: %s' % interval)
        if dtype not in (StandardizedPrice, Candle):
            raise ValueError('The source frame type must be either pricing.Candle or pricing.StandardizedPrice')
        if initial is not None:
            if dtype == StandardizedPrice and not isinstance(initial, int):
                raise TypeError("For pricing.StandardizedPrice type, the initial value must be integer")
            elif dtype == Candle and not isinstance(initial, Candle):
                raise TypeError("For pricing.Candle type, the initial value must be a candle instance")
        Timelapse.__init__(self, dtype, None if dtype == Candle else 0, interval, 3600, 1)
        IndicatorBroadcaster.__init__(self, self)
        self._timestamp = stamp
        self._initial = initial
        self._on_refresh_linked_sources = Event()
        self._linked_to = None
        self._linked_last_read_ubound = 0
        self._linked_relative_bin_size = 0

    def _get_timestamp(self):
        """
        Implements the timestamp property by returning the owned timestamp.
        """

        return self._timestamp

    @property
    def on_refresh_indicators(self):
        """
        Indicators will connect to this event to refresh themselves when more data is added.
        """

        return self._on_refresh_indicators

    @property
    def dtype(self):
        """
        The underlying type of this source frame.
        """

        return self._data.dtype

    @property
    def initial(self):
        """
        The initial value of this source frame. When provided, this value is the last
          price (either StandardizedPrice or Candle) from the last period.
        """

        return self._initial

    def _interpolate(self, previous_value, start, end, next_value):
        """
        Causes an interpolation of data in certain index range, and considering
          boundary values.

        IT IS ACTUALLY A BAD PRACTICE TO HAVE TO INTERPOLATE DATA AND
        WILL LEAD TO MISLEADING RESULTS. Perhaps in a future I'm updating
        this part, but even there, it is a bad practice.

        :param previous_value: The left-side value.
        :param start: The start index.
        :param end: The end index (not included).
        :param next_value: The right-side value.
        """

        # We'll state a new reference system where the previous value is at 0,
        #   and the next value is at distance, and we'll fill values from 1 to
        #   distance - 1.
        distance = end - start + 1
        # Iterating from index 1 to index {distance-1}, not including it.
        if isinstance(previous_value, int):
            delta = float(next_value - previous_value)/distance
            for index in range(0, distance - 1):
                self._data[start + index][0] = int(delta * (index + 1) + previous_value)
        elif isinstance(previous_value, Candle):
            delta_start = float(next_value.start - previous_value.start) / distance
            delta_end = float(next_value.end - previous_value.end) / distance
            delta_max = float(next_value.max - previous_value.max) / distance
            delta_min = float(next_value.min - previous_value.min) / distance
            for index in range(0, distance - 1):
                self._data[start + index][0] = Candle(
                    start=int(delta_start * (index + 1) + previous_value.start),
                    end=int(delta_end * (index + 1) + previous_value.end),
                    min=int(delta_min * (index + 1) + previous_value.min),
                    max=int(delta_max * (index + 1) + previous_value.max)
                )

    def _check_input_matching_types(self, data):
        """
        Checks whether the input matches the requirement.
        :param data: The data to check.
        :param many: Whether the data should involve many elements (a numpy array).
        :return:
        """

        if isinstance(data, Candle):
            if self._data.dtype != Candle:
                raise TypeError("Scalar input data must match the required type")
        elif isinstance(data, (int, StandardizedPrice)):
            if self._data.dtype != StandardizedPrice:
                raise TypeError("Scalar input data must match the required type")
        elif not isinstance(data, ndarray):
            raise TypeError("Invalid input data type")

    def _put_and_interpolate(self, push_index, push_data):
        """
        First, it will put the data appropriately. Then it will try an interpolation -if needed- of the data,
          considering the last index, the initial value of this frame, and the first element of the pushed data.

        In the end, the new data (including the interpolated, if the case) will start at index
          self._last_index+1 and will end at index (push_index + {push_data.size or 1}), not
          including that index.
        :param push_index: The index the data is being pushed at.
        :param push_data: The data being pushed.
        """

        # Preliminary: Get the last index of data already put in this frame.
        length = len(self)

        # First, performs the insertion.
        is_ndarray = isinstance(push_data, ndarray)
        if is_ndarray:
            self._data[push_index:push_index+push_data.shape[0]] = push_data[:]
        else:
            self._data[push_index] = push_data

        # Check whether we need to interpolate, and do it.
        left_side = self._initial if length == 0 else self._data[length][0]
        needs_interpolation = push_index - 1 > length
        if needs_interpolation:
            warnings.warn(self.InterpolationWarning("Data is being added at sparse times! It may produce misleading "
                                                    "interpolated data."))
            if length == 0 and left_side is None:
                raise RuntimeError("Cannot add data: interpolation is needed for the required index "
                                   "to push the data into, but an initial value was never set for "
                                   "this frame")
            # Performs the interpolation.
            right_side = self._data[push_index][0] if is_ndarray else push_data
            self._interpolate(left_side, length, push_index, right_side)

    def link(self, source):
        """
        Links this frame to another source, so data can be updated from it into this frame's data.
        It is an error to link to a source with a different interval size or a LOWER date: frames can
          only link to source with a greater date (and back-fill positions in previous time stamps).
        Linking to a source will automatically unlink from the previous source, if any.
        :param source: The source to link to.
        """

        self.unlink()
        if self._data.dtype != Candle:
            raise ValueError("This frame does not use Candle type, so it cannot connect to a source")
        if source.timestamp < self._timestamp:
            raise ValueError("The date of the source attempted to link to is lower than this frame's date")
        if int(source.interval) > int(self.interval):
            raise ValueError("The source to link to must have a lower interval than this frame")
        if int(self.interval) % int(source.interval) != 0:
            raise ValueError("The source's interval is not an exact divisor of this frame's interval")
        if self.interval.round(source.timestamp) != source.timestamp:
            raise ValueError("The specified source has not a date that is aligned to this frame's interval")
        self._linked_to = source._on_refresh_linked_sources
        self._linked_to.register(self._on_linked_refresh)
        self._linked_relative_bin_size = int(self.interval) // int(source.interval)
        # Force the first refresh.
        self._on_linked_refresh(source, 0, len(source))

    def unlink(self):
        """
        Unlinks this frame from its currently linked source.
        :return:
        """

        self._linked_last_read_ubound = 0
        self._linked_relative_bin_size = 0
        if self._linked_to:
            self._linked_to.unregister(self._on_linked_refresh)
            self._linked_to = None

    def _make_candle(self, source_elements):
        """
        Makes a candle out of the given source elements, either by summarizing integers, or candles.
        :param source_elements: The elements to merge into one candle.
        :return: The candle with the merged elements.
        """

        candle = None
        for source_element in source_elements:
            if candle is None:
                if isinstance(source_element, uint64):
                    candle = Candle(source_element, source_element, source_element, source_element)
                elif isinstance(source_element, Candle):
                    candle = source_element
            else:
                candle = candle.merge(source_element)
        return candle

    def _on_linked_refresh(self, source, start, end):
        """
        Handles an update from the linked source considering start date and boundaries.
        It is guaranteed that boundaries will be in the same scale of this frame, but
          it has also be taken into account the start date to use as offset for the
          start and end indices.
        :param source: The linked source.
        :param start: The start index, in the source, of the updated data.
        :param end: The end index (not including), in the source, of the updated data.
        """

        base_index = self.index_for(source.timestamp)
        start = min(start, self._linked_last_read_ubound)
        min_index = start // self._linked_relative_bin_size
        max_index = (end + self._linked_relative_bin_size - 1) // self._linked_relative_bin_size
        for digest_index in range(min_index, max_index):
            source_index = digest_index * self._linked_relative_bin_size
            # We use indices 0 because we know the underlying array is of size 1.
            # From the source, we get a chunk of the relative size. Either a linear
            # array of integers, or a linear array of candles.
            # Now, make the candle out of the elements
            candle = self._make_candle(source._data[source_index:source_index+self._linked_relative_bin_size][:, 0])
            self._data[digest_index + base_index] = candle
        self._linked_last_read_ubound = max(self._linked_last_read_ubound, end)
        # Indicators, and linked frames, of this source frame must also be notified, like in push.
        self._on_refresh_indicators.trigger(self, min_index + base_index, max_index + base_index)
        self._on_refresh_linked_sources.trigger(self, min_index + base_index, max_index + base_index)

    def push(self, data, index=None):
        """
        Adds data, either scalar of the expected type, or a data chunk of the expected type.
        Always, at given index.

        :param data: The data to add.
        :param index: The index to add the data at. By default, the next index. It is allowed
          to update old data, but think it twice: it MAY trigger an update of old data, not account
          for actual data re-interpolation, and cascade the changes forward in unpredictable ways,
          which may involve SEVERAL QUITE COSTLY COMPUTATIONS!!.
        :return:
        """

        if index is None:
            index = len(self)
        elif isinstance(index, (date, datetime)):
            index = self.index_for(index)
        self._check_input_matching_types(data)
        self._put_and_interpolate(index, data)
        # Arrays have length in their shape, while other elements have size=1.
        end = index + (1 if not isinstance(data, ndarray) else data.shape[0])
        self._on_refresh_linked_sources.trigger(self, index, end)
        self._on_refresh_indicators.trigger(self, index, end)
