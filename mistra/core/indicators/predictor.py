import math
import warnings
from enum import IntEnum
from typing import Tuple
import numpy
from . import Indicator
from ..sources import Source
from ..timelapses import Timelapse
from ..utils.mappers.side_pluckers import SidePlucker


class PredictorAlgorithm:
    """
    A predictor algorithm takes an array of elements
    and makes a prediction. It also provides metadata
    of itself that involves interaction with the data
    provided to the indicator.
    """

    def _get_tail_size(self):
        raise NotImplemented

    @property
    def tail_size(self):
        """
        The tail size is: how many elements does this
        predictor instance requires in order to make
        a predictor. If less than those elements are
        provided, then NaN will be the value of both
        the prediction and the structural error of that
        prediction in particular.
        :return: The tail size.
        """

        return self._get_tail_size()

    def _get_step(self):
        raise NotImplemented

    @property
    def step(self):
        """
        The step is: how many steps in the future will this
        predictor instance actually predict. These objects
        consider X to be expressed in units of time, which
        makes the corresponding Y value a function of time,
        which might be a linear or polynomial expression
        or whatever is needed to make a prediction. In this
        case, the step can be freely chosen.

        Unstructured time-series prediction will typically
        have step=1 (constant), while layered time-series
        prediction (where first is the trend, then the season,
        and finally the stationary data) may predict step=N
        while not considering the stationary part important
        enough to suffer when its "long-term" prediction
        converges to a constant.
        """

        return self._get_step()

    def predict(self, x: numpy.ndarray) -> Tuple[float, float]:
        """
        Makes a prediction. The result of the prediction is
        a tuple making: (prediction, structural_error).
        :param x: The input.
        :return: The prediction and the structural error.
        """

        raise NotImplemented


class Predictor(Indicator):
    """
    This is a one-way predictor. Given a series of values, it predicts
    the next value and also provides a bunch of auxiliary values to
    take a look to (e.g. structural coefficient and some notion of MSE
    or related stuff).
    """

    class Columns(IntEnum):
        PREDICTION = 0
        STRUCTURAL_ERROR_AT_PREDICTION_TIME = 1
        STRUCTURAL_ERROR_AT_PREDICTED_TIME = 2
        PREDICTION_DIFFERENCE = 3
        STANDARD_ERROR = 4

    def __init__(self, timelapse: Timelapse, algorithm: PredictorAlgorithm,
                 side: int = None, moving_stderr_tail_size: int = 20):
        super().__init__(timelapse)

        # First, initialize which data will be read from.
        self._input_data = None
        if isinstance(timelapse, Source):
            if side not in [Source.BID, Source.ASK]:
                raise ValueError("When creating a Predictor indicator from a Source, "
                                 "a side must be chosen and must be either Source.BID "
                                 "or Source.ASK")
            self._input_data = SidePlucker(timelapse, side)
        elif isinstance(timelapse, Indicator):
            if timelapse.width != 1:
                raise ValueError("When creating a Predictor indicator from another indicator, "
                                 "the width of that indicator must be 1. So far, multi-dimensional "
                                 "indicators are not supported yet")
            self._input_data = timelapse
        else:
            raise TypeError("The timelapse must be either a Source or an Indicator")

        # Then, set the predictor instance.
        if not isinstance(algorithm, PredictorAlgorithm) or type(algorithm) == PredictorAlgorithm:
            raise TypeError("The algorithm must be specified and it must be of a strict "
                            "subclass of PredictorAlgorithm")
        self._algorithm = algorithm

        # Finally, the moving STDERR tail size.
        if isinstance(moving_stderr_tail_size, int):
            if moving_stderr_tail_size < 2:
                raise ValueError("The moving standard error tail size must be >= 2")
            if moving_stderr_tail_size < 10:
                warnings.warn("A too small standard deviation tail size was chosen. This will "
                              "work but you might find results less accurate")
        else:
            raise TypeError("The moving standard error tail size must be an integer")
        self._moving_stderr_tail_size = moving_stderr_tail_size

    def _initial_width(self):
        """
        The initial width for the indicator involves columns:
        - The vector for the prediction.
        - The vector for the structural error for the moment where the prediction was done.
        - The vector for the structural error for the moment the prediction was done for.
        - The difference between the actual value and the prediction.
        - The standard deviation, taking a proper tail, considering prediction-actual.
        """

        return 5

    def _update(self, start, end):
        """
        Performs a full update, carefully following all the steps.
        :param start: The start position to update.
        :param end: The end (not included) position to update.
        """

        for index in range(start, end):
            self._update_index(index)

    def _update_index(self, index):
        """
        Performs a per-index update, carefully following all the steps.
        :param index: The index being updated.
        """

        # 1. First, take a tail of data. The tail will end
        #    in the given index. If the index is < the tail
        #    size, we'll do nothing at all here.
        if index < self.prediction_tail_size:
            return
        tail = self._input_data[index + 1 - self.prediction_tail_size:index + 1]
        prediction, structural_error = self._algorithm.predict(tail)
        step = self.step
        # 2. Store the prediction in the array (at time {index}), at column PREDICTION.
        # 3. Store the str. error in the array (at time {index}), at column STRUCTURAL_ERROR_AT_PREDICTION_TIME.
        # 3. Store the str. error in the array (at time {index + step}), at column STRUCTURAL_ERROR_AT_PREDICTED_TIME.
        # 4. Store the difference at time {index}, at column PREDICTION_DIFFERENCE. Value:
        #    (self._data[index, PREDICTION] - self._input_data[index]).
        #    It will be NaN if either value is NaN.
        # 5. Store the standard error at time {index}, at column STANDARD_ERROR. Value:
        #    if there are at least (moving_stderr_tail_size) elements in the tail:
        #        diffs = self._data[index - moving_stderr_tail_size + 1:index + 1]
        #        variance = (diffs ** 2).sum() / (moving_stderr_tail_size - 1)
        #        self._data[index, STANDARD_ERROR] = sqrt(variance)
        #        if any of these values is NaN, this value will be indeed NaN.
        #    otherwise, let it be NaN as default.

    @property
    def prediction_tail_size(self):
        """
        The underlying tail size, according to the algorithm.
        """

        return self._algorithm.tail_size

    @property
    def moving_stderr_tail_size(self):
        """
        The underlying tail size for standard error calculation.
        """

        return self._moving_stderr_tail_size

    @property
    def step(self):
        """
        The distance between the time of the last sample and the
        time, in the future, being predicted.
        """

        return self._algorithm.step