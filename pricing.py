from numpy import uint64 as _uint64
from collections import namedtuple


"""
Defined both the standardized price and the japanese candle. The japanese candle holds
  a range of values for a certain time lapse, stating its minimum, maximum, start and
  prices.

Prices are standardized to integer, but perhaps every price statistic has a different scaling
  mechanism. E.g. satoshis will not have scaling, but dollar/euro conversion will have 6
  digits of scaling for their floats. Those cases are converted to integers (e.g. by zero-pad
  and then point-removal).
"""


StandardizedPrice = _uint64


class Candle(namedtuple('BaseCandle', ('start', 'end', 'min', 'max'))):
    """
    Japanese candles span over intervals and keep a detail of start, end, min and max (standarized)
      prices of an asset in a (somehow neutral or reference) currency.
    """

    def merge(self, price):
        if isinstance(price, int):
            return Candle(start=self.start, end=price, min=min(self.min, price), max=max(self.max, price))
        elif isinstance(price, Candle):
            return Candle(start=min(self.start, price.start), end=max(self.start, price.start),
                          min=min(self.min, price.min), max=max(self.max, price.max))
        else:
            raise TypeError("Only integers or candles can be merged to an existing candle")
