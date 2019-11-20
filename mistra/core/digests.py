from numpy import uint64
from .events import Event
from .pricing import Candle
from .timelapses import Timelapse


class Digest(Timelapse):
    """
    Digests can be connected to source frames to summarize their data: they have an interval size which
      must be BIGGER to the interval size in the referenced source, and the source must have a datetime
      which must also be rounded (i.e. exactly divisible) by the given interval (e.g. if a Source using
      timestamp at date X and time 05:00:00 has an interval size of 1 minute, the allowed intervals
      for a digest are from 1 minute to 1 hour, while 2 hours, 3 hours, 4 hours, ... are disallowed
      because 05:00:00 is not divisible by any of them).
    """

    def __init__(self, source, interval):
        if source is None:
            raise ValueError("The source for the digest must not be None")
        if not interval.allowed_as_digest(source.interval):
            raise ValueError("The chosen digest interval size must be bigger to the source's interval size")
        if source.timestamp != interval.round(source.timestamp):
            raise ValueError("Cannot create a digest for the given interval and source, since the source's start "
                             "date is not rounded to the given interval size for this digest")
        Timelapse.__init__(self, Candle, None, interval, 240, 1)
        self._source = source
        self._source.on_refresh_digests.register(self._on_refresh)
        self._attached = True
        self._relative_bin_size = int(interval) // int(source.interval)
        self._on_refresh_linked_sources = Event()
        self._last_read_ubound = 0

    @property
    def source(self):
        """
        The source this digest is attached to.
        """

        return self._source

    def _get_timestamp(self):
        """
        Implements the timestamp by returning the source's timestamp.
        """

        return self._source.timestamp

    @property
    def attached(self):
        """
        Tells whether this digest is still attached and working, or not.
        """

        return self._attached

    def detach(self):
        """
        Detaches this digest from the source. This digest will be useless since will
          not update its data anymore.
        """

        self._source.on_refresh_digests.unregister(self._on_refresh)
        self._attached = False

    @property
    def on_refresh_linked_sources(self):
        """
        This event notifies linked frames that they must update their data according
          to update triggers in this digest. Frames can link to and unlink from this
          event at will, with no issues.
        """

        return self._on_refresh_linked_sources

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

    def _on_refresh(self, start, end):
        """
        Updates the current digest given its data. It will give the last index the digest will
          have to process until (perhaps the digest has former data already parsed, and so
          it will have to collect less data). Several source indices falling in the same
          digest index will involve a candle merge.
        :param start: The source-scaled index the digest will have to refresh from.
        :param end: The source-scaled end index the digest will have to refresh until (and not
          including).
        """

        start = min(start, self._last_read_ubound)
        min_index = start // self._relative_bin_size
        max_index = (end + self._relative_bin_size - 1) // self._relative_bin_size

        for digest_index in range(min_index, max_index):
            source_index = digest_index * self._relative_bin_size
            # We use indices 0 because we know the underlying array is of size 1.
            # From the source, we get a chunk of the relative size. Either a linear
            # array of integers, or a linear array of candles.
            # Now, make the candle out of the elements
            candle = self._make_candle(self._source[source_index:source_index+self._relative_bin_size][:, 0])
            self._data[digest_index] = candle
        self._last_read_ubound = max(self._last_read_ubound, end)
        self._on_refresh_linked_sources.trigger(self, min_index, max_index)
